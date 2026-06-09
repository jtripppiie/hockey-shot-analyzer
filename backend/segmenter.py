"""
segmenter.py — Auto-splice a long stream into individual attempts (SKELETON).

Given the per-frame landmarks for a whole practice stream (the same
`run_pose_detection` output the analyzer already produces), find where each
attempt (slap shot) happens and return a list of cut windows. Each window can
then be trimmed and fed to the existing analyzer as its own job.

This is a SKELETON for the surrounding pipeline (route + window handoff), but the
detection core is now implemented: the dominant-wrist speed signal is smoothed,
true local maxima are picked, and overlapping/again-too-close peaks are removed
by non-max suppression. The numeric constants (PEAK_K, gap, padding, smoothing
width) are reasonable defaults that still need calibration against real
multi-rep clips before being fully trusted (see ROADMAP Phase 3, and the project
rule: accuracy > speed).

Design intent (per ROADMAP):
- Phase 2 uses MANUAL cut points; this module is the Phase 3 auto-suggester.
- Output is always "suggested" cuts. A human confirms/adjusts before analysis,
  so a mis-detected rep is correctable rather than silently wrong.
"""

import math

from metrics import _detect_dominant_hand, _pt3

# Window padding around a detected event, in seconds. A slap shot's load +
# follow-through live on either side of the wrist-speed peak, so we grab a
# generous symmetric window and let the per-clip analyzer find the exact phases.
PRE_EVENT_S = 1.5
POST_EVENT_S = 1.5

# Minimum gap between two accepted events, in seconds. Prevents a single shot's
# multi-frame speed plateau from registering as several reps (enforced by NMS).
MIN_EVENT_GAP_S = 2.0

# A candidate peak must exceed (median + K*MAD) of the speed signal to count as
# a real attempt rather than ambient motion (skating, adjusting, etc.).
PEAK_K = 4.0

# Centered moving-average width for the speed signal, in seconds. Removes
# single-frame jitter so local-maxima picking lands on the real peak.
SMOOTH_S = 0.12

# Drop suggested windows shorter than this (e.g. a peak clamped at a stream
# edge). A real attempt is always longer than this.
MIN_ATTEMPT_S = 0.75


def _wrist_speed_series(frames: list[dict], dom: str, fps: float):
    """Return [(frame_idx, speed), ...] of dominant-wrist speed via central
    difference. Mirrors the release-detection signal in metrics._detect_phases,
    minus the single-clip de-spike (the multi-rep picker handles spikes via the
    statistical peak threshold instead)."""
    wrist_xy = []
    for f in frames:
        lm = f["landmarks"]
        if not lm:
            continue
        w = _pt3(lm, f"{dom}_wrist")
        if w is not None:
            wrist_xy.append((f["frame"], w[0], w[1]))

    speeds = []
    for k in range(1, len(wrist_xy) - 1):
        i_prev, xp, yp = wrist_xy[k - 1]
        i_next, xn, yn = wrist_xy[k + 1]
        dt = max(1, i_next - i_prev) / fps
        speeds.append((wrist_xy[k][0], math.hypot(xn - xp, yn - yp) / dt))
    return speeds


def _peak_threshold(speeds: list[tuple]) -> float:
    """median + PEAK_K * MAD of the speed values. Robust to the big spikes we're
    actually trying to find."""
    vals = sorted(s for _, s in speeds)
    if not vals:
        return float("inf")
    med = vals[len(vals) // 2]
    mad = sorted(abs(v - med) for v in vals)[len(vals) // 2]
    if mad <= 0:
        return float("inf")
    return med + PEAK_K * mad


def _smooth(speeds: list[tuple], win: int) -> list[tuple]:
    """Centered moving average over the speed values, preserving frame indices.
    `win` is forced odd and >= 1; win <= 1 is a no-op."""
    n = len(speeds)
    if win <= 1 or n == 0:
        return speeds
    if win % 2 == 0:
        win += 1
    half = win // 2
    vals = [s for _, s in speeds]
    out = []
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        window = vals[lo:hi]
        out.append((speeds[i][0], sum(window) / len(window)))
    return out


def find_events(frames: list[dict], fps: float) -> list[dict]:
    """Find candidate attempt events in a long stream.

    Returns a list of {"frame": peak_idx, "score": speed, "confidence": 0..1}
    ordered by frame. Pipeline: dominant-wrist speed → moving-average smoothing →
    local-maxima above a robust (median + K*MAD) threshold → non-max suppression
    by a minimum frame gap → confidence calibrated against the strongest peak.
    """
    dom = _detect_dominant_hand([f for f in frames if f.get("landmarks")])
    if not dom:
        return []

    speeds = _wrist_speed_series(frames, dom, fps)
    if not speeds:
        return []

    speeds = _smooth(speeds, int(round(SMOOTH_S * fps)))
    thr = _peak_threshold(speeds)
    if not math.isfinite(thr):
        return []
    gap_frames = int(round(MIN_EVENT_GAP_S * fps))

    # True local maxima above threshold: strictly greater than the previous
    # sample and >= the next, so a rising-then-flat peak is caught once.
    candidates = []
    for k in range(1, len(speeds) - 1):
        idx, s = speeds[k]
        if s < thr:
            continue
        if s > speeds[k - 1][1] and s >= speeds[k + 1][1]:
            candidates.append({"frame": idx, "score": s})

    # Non-max suppression: take peaks strongest-first, reject any that fall
    # within gap_frames of an already-accepted (stronger) peak.
    candidates.sort(key=lambda c: c["score"], reverse=True)
    accepted: list[dict] = []
    for c in candidates:
        if all(abs(c["frame"] - a["frame"]) >= gap_frames for a in accepted):
            accepted.append(c)

    # Calibrate confidence: how far above threshold relative to the strongest
    # accepted peak. strongest → 1.0, exactly-at-threshold → 0.0.
    smax = max((a["score"] for a in accepted), default=thr)
    span = smax - thr
    for a in accepted:
        a["confidence"] = round((a["score"] - thr) / span, 3) if span > 0 else 1.0

    accepted.sort(key=lambda a: a["frame"])
    return accepted


def events_to_windows(events: list[dict], fps: float, total_frames: int) -> list[dict]:
    """Convert detected events into clamped [start_frame, end_frame] cut windows.

    Overlapping windows (two events closer than the padding) are merged into one
    clip, and windows shorter than MIN_ATTEMPT_S (e.g. a peak clamped at a stream
    edge) are dropped. Returns {"start", "end", "event", "confidence"} dicts;
    these are SUGGESTED cuts the UI lets the user confirm/adjust before analysis.
    """
    pre = int(round(PRE_EVENT_S * fps))
    post = int(round(POST_EVENT_S * fps))
    min_len = int(round(MIN_ATTEMPT_S * fps))

    raw = []
    for ev in sorted(events, key=lambda e: e["frame"]):
        start = max(0, ev["frame"] - pre)
        end = min(total_frames - 1, ev["frame"] + post)
        raw.append({"start": start, "end": end, "event": ev["frame"],
                    "confidence": ev.get("confidence", 0.0)})

    # Merge overlapping/adjacent windows; the merged window keeps the event +
    # confidence of its strongest contributor.
    merged: list[dict] = []
    for w in raw:
        if merged and w["start"] <= merged[-1]["end"]:
            prev = merged[-1]
            prev["end"] = max(prev["end"], w["end"])
            if w["confidence"] > prev["confidence"]:
                prev["event"] = w["event"]
                prev["confidence"] = w["confidence"]
        else:
            merged.append(dict(w))

    return [w for w in merged if (w["end"] - w["start"]) >= min_len]


def suggest_segments(frames: list[dict], fps: float, total_frames: int) -> list[dict]:
    """Top-level convenience: stream landmarks → suggested cut windows.

    This is the single entry point the /session/{id}/segment route will call.
    SKELETON wiring; the heavy lifting in find_events/events_to_windows is the
    part that needs tuning + validation.
    """
    events = find_events(frames, fps)
    return events_to_windows(events, fps, total_frames)
