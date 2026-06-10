"""
training.py — turn collected expert feedback into a calibration signal.

This is the "training" loop for a heuristic analyzer. We don't retrain a neural
net; instead we read the append-only feedback log (expert corrections already
captured by Expert Feedback Mode + Measurement Feedback) and report, quantitatively:

  • how well the analyzer's overall score agrees with expert consensus
    (bias, mean error, correlation), and a fitted linear correction
    human ≈ a·ai + b that would minimize that error;
  • which individual metrics experts most often flag as mis-measured.

Everything here is pure and read-only — it computes a report from records you
pass in. Persisting / applying the correction is a separate, opt-in step.

Sport-agnostic: the pole-vault repo ships an identical copy.
"""
from __future__ import annotations

import math
import os
from datetime import datetime

# Below this many usable expert reviews, a fit is statistically meaningless, so
# we report "not enough data yet" rather than a noisy correction. Opt-in via env.
CALIBRATION_MIN_SAMPLES = int(os.environ.get("CALIBRATION_MIN_SAMPLES", "12"))


def fit_linear_calibration(pairs: list[tuple[float, float]]) -> dict | None:
    """Least-squares fit of human ≈ a·ai + b over (ai_score, human_score) pairs.

    Returns {a, b, n, mae_before, mae_after, improvement, correlation} or None
    when a fit is impossible (need ≥2 points spanning ≥2 distinct ai values).
    """
    pts = [(float(a), float(h)) for a, h in pairs
           if a is not None and h is not None]
    n = len(pts)
    if n < 2:
        return None
    xs = [a for a, _ in pts]
    ys = [h for _, h in pts]
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    if sxx == 0:                      # all ai scores identical → slope undefined
        return None
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in pts)
    syy = sum((y - mean_y) ** 2 for y in ys)
    a = sxy / sxx
    b = mean_y - a * mean_x
    mae_before = sum(abs(y - x) for x, y in pts) / n
    mae_after = sum(abs(y - (a * x + b)) for x, y in pts) / n
    corr = (sxy / math.sqrt(sxx * syy)) if syy > 0 else None
    return {
        "a": round(a, 4),
        "b": round(b, 2),
        "n": n,
        "mae_before": round(mae_before, 2),
        "mae_after": round(mae_after, 2),
        "improvement": round(mae_before - mae_after, 2),
        "correlation": round(corr, 3) if corr is not None else None,
    }


def _performance_report(perf: list[dict], min_samples: int) -> dict:
    """Agreement stats between ai_score and human_score over performance feedback."""
    pairs: list[tuple[float, float]] = []
    too_high = too_low = 0
    for r in perf:
        ai = r.get("ai_score")
        hu = r.get("human_score")
        if isinstance(ai, (int, float)) and isinstance(hu, (int, float)):
            pairs.append((ai, hu))
        boxes = r.get("human_checkboxes") or []
        if "ai_score_too_high" in boxes:
            too_high += 1
        if "ai_score_too_low" in boxes:
            too_low += 1

    n = len(pairs)
    ready = n >= min_samples
    deltas = [hu - ai for ai, hu in pairs]          # +ve → AI under-scores
    bias = sum(deltas) / n if n else None
    mae = sum(abs(d) for d in deltas) / n if n else None
    rmse = math.sqrt(sum(d * d for d in deltas) / n) if n else None
    calibration = fit_linear_calibration(pairs) if ready else None

    if not n:
        rec = "No expert reviews with a corrected score yet. Use Expert Feedback Mode on a few clips to start training."
    elif not ready:
        rec = (f"Have {n} expert review{'s' if n != 1 else ''}; collect "
               f"{min_samples - n} more to fit a reliable correction.")
    elif bias is not None and abs(bias) < 3 and (mae is None or mae < 8):
        rec = (f"Analyzer agrees well with experts (bias {bias:+.1f} pts, "
               f"avg error {mae:.1f} pts). No correction needed yet.")
    else:
        direction = "high" if (bias or 0) < 0 else "low"
        rec = (f"Analyzer scores ~{abs(bias):.0f} pts too {direction} on average "
               f"(avg error {mae:.1f} pts). A calibration fit is available to apply.")

    return {
        "n": n,
        "min_samples": min_samples,
        "ready": ready,
        "ai_bias": round(bias, 2) if bias is not None else None,
        "mae": round(mae, 2) if mae is not None else None,
        "rmse": round(rmse, 2) if rmse is not None else None,
        "too_high_count": too_high,
        "too_low_count": too_low,
        "calibration": calibration,
        "recommendation": rec,
    }


def _measurement_report(meas: list[dict]) -> dict:
    """Per-metric reliability from measurement feedback (good/bad/not_measured)."""
    flags: dict[str, dict[str, int]] = {}
    checkbox_counts: dict[str, int] = {}
    label_counts: dict[str, int] = {}
    for r in meas:
        for metric, rating in (r.get("metric_ratings") or {}).items():
            slot = flags.setdefault(metric, {"good": 0, "bad": 0, "not_measured": 0})
            if rating in slot:
                slot[rating] += 1
        for c in (r.get("checkboxes") or []):
            checkbox_counts[c] = checkbox_counts.get(c, 0) + 1
        label = r.get("overall_label")
        if label:
            label_counts[label] = label_counts.get(label, 0) + 1

    metric_flags: dict[str, dict] = {}
    worst_metric = None
    worst_rate = -1.0
    for metric, slot in flags.items():
        total = slot["good"] + slot["bad"] + slot["not_measured"]
        bad_rate = (slot["bad"] / total) if total else 0.0
        metric_flags[metric] = {**slot, "total": total, "bad_rate": round(bad_rate, 3)}
        # Only nominate a "worst" metric once there's a little signal.
        if total >= 3 and bad_rate > worst_rate:
            worst_rate = bad_rate
            worst_metric = metric

    return {
        "n": len(meas),
        "metric_flags": metric_flags,
        "worst_metric": worst_metric,
        "worst_bad_rate": round(worst_rate, 3) if worst_metric else None,
        "checkbox_counts": checkbox_counts,
        "overall_label_counts": label_counts,
    }


def build_calibration_report(records: list[dict],
                             min_samples: int = None) -> dict:
    """Build a full training/calibration report from raw feedback log records.

    `records` is the parsed feedback_log.jsonl (performance + measurement rows).
    """
    if min_samples is None:
        min_samples = CALIBRATION_MIN_SAMPLES
    perf = [r for r in records if r.get("type", "performance") == "performance"]
    meas = [r for r in records if r.get("type") == "measurement"]
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "total_feedback": len(records),
        "performance": _performance_report(perf, min_samples),
        "measurement": _measurement_report(meas),
    }
