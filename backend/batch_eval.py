"""
batch_eval.py — Run a folder of clips through the REAL analysis pipeline and
dump every guard decision + score to a CSV, so accuracy can be eyeballed.

The analyzer is robust (it defends itself against bad input) but we don't yet
*know* it's right. This harness closes that evidence gap: point it at a folder
of clips, get one CSV row per clip with the accept/reject decision, the signals
behind it (detection rate, shot-check, continuity), and the scores. Drop an
optional manifest with expected labels and it also reports false-reject /
false-accept rates for the shot guard.

It mirrors `_analyze_video`'s decision logic exactly (see `classify_clip`) but
skips the expensive overlay render — we only want the numbers.

Usage:
  python batch_eval.py CLIPS_DIR [--manifest m.csv] [--out report.csv]
  python batch_eval.py clip1.mp4 clip2.mov            # explicit files

Manifest (optional CSV, header required):
  file,expect,expect_continuous
  good_shot.mp4,shot,yes
  my_vault.mp4,not_shot,yes
  highlight.mp4,not_shot,no

  expect            ∈ {shot, not_shot}   — should the clip be accepted as a shot?
  expect_continuous ∈ {yes, no}          — is it a single continuous take?

Self-contained reporting core (`classify_clip`, `summarize_rows`) is pure and
unit-tested in test_batch_eval.py.
"""
import argparse
import csv
import io
import os
import sys

VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}

# Decision thresholds — kept in lock-step with _analyze_video in main.py.
MIN_FRAMES = 10
MAX_DURATION_S = 60
DETECT_REJECT = 0.1     # below this: no_body_detected
DETECT_POOR = 0.4       # below this: poor_detection

CSV_COLUMNS = [
    "file", "decision", "reason", "warnings",
    "detection_rate", "n_frames", "duration_s",
    "looks_like_shot", "shot_reject", "hip_rise", "wrist_travel",
    "looks_continuous", "cut_count", "pixel_cut_count", "max_jump",
    "overall", "power", "technique", "timing",
]


def _reject(reason):
    return {"decision": "reject", "reason": reason, "warnings": []}


def classify_clip(*, total_frames, fps, width, height, detection_rate, result):
    """Replicate _analyze_video's accept/reject decision. Pure function.

    `result` is the compute_metrics output (dict) or None when metrics weren't
    run (e.g. detection failed earlier). Returns
    {"decision": "accept"|"reject", "reason": str|None, "warnings": [str, ...]}.
    """
    if total_frames < MIN_FRAMES:
        return _reject("video_too_short")
    if total_frames > 0 and fps > 0:
        if total_frames / fps > MAX_DURATION_S:
            return _reject("video_too_long")
    if width == 0 or height == 0:
        return _reject("video_unreadable")
    if detection_rate < DETECT_REJECT:
        return _reject("no_body_detected")
    if detection_rate < DETECT_POOR:
        return _reject("poor_detection")
    if not result:
        return _reject("metrics_failed")

    q = result.get("quality_report", {}) or {}
    if q.get("shot_check", {}).get("reject"):
        return _reject("not_a_hockey_shot")

    warnings = []
    cc = q.get("continuity_check", {}) or {}
    if not cc.get("looks_continuous", True):
        warnings.append("camera_cuts")
    return {"decision": "accept", "reason": None, "warnings": warnings}


def _row_from(name, *, total_frames, fps, width, height, detection_rate, result):
    """Build a flat CSV row dict from the raw signals + decision."""
    decision = classify_clip(total_frames=total_frames, fps=fps, width=width,
                             height=height, detection_rate=detection_rate,
                             result=result)
    q = (result or {}).get("quality_report", {}) or {}
    sc = q.get("shot_check", {}) or {}
    cc = q.get("continuity_check", {}) or {}
    s = (result or {}).get("summary", {}) or {}
    duration = round(total_frames / fps, 2) if (total_frames and fps) else ""
    return {
        "file": name,
        "decision": decision["decision"],
        "reason": decision["reason"] or "",
        "warnings": "|".join(decision["warnings"]),
        "detection_rate": round(detection_rate, 3),
        "n_frames": total_frames,
        "duration_s": duration,
        "looks_like_shot": sc.get("looks_like_shot", ""),
        "shot_reject": sc.get("reject", ""),
        "hip_rise": sc.get("hip_rise", ""),
        "wrist_travel": sc.get("wrist_travel", ""),
        "looks_continuous": cc.get("looks_continuous", ""),
        "cut_count": cc.get("cut_count", ""),
        "pixel_cut_count": cc.get("pixel_cut_count", ""),
        "max_jump": cc.get("max_jump", ""),
        "overall": s.get("overall", ""),
        "power": s.get("power", ""),
        "technique": s.get("technique", ""),
        "timing": s.get("timing", ""),
    }


def evaluate_clip(video_path, hand_override=None):
    """Run the real pipeline on one video and return a CSV row dict.

    Imports the heavy modules lazily so the pure core (classify_clip,
    summarize_rows) and its tests don't need MediaPipe / OpenCV installed.
    """
    from pose import get_video_meta, run_pose_detection, scene_cut_precheck
    from metrics import compute_metrics

    name = os.path.basename(video_path)
    meta = get_video_meta(video_path)
    total_frames = meta.get("total_frames", 0)
    fps = meta.get("fps", 0) or 0
    width = meta.get("width", 0)
    height = meta.get("height", 0)

    # Cheap meta gates first — don't run pose on an unusable clip.
    if total_frames < MIN_FRAMES or width == 0 or height == 0 or \
            (total_frames > 0 and fps > 0 and total_frames / fps > MAX_DURATION_S):
        return _row_from(name, total_frames=total_frames, fps=fps, width=width,
                         height=height, detection_rate=0.0, result=None)

    frames = run_pose_detection(video_path)
    detected = [f for f in frames if f.get("landmarks")]
    detection_rate = len(detected) / max(len(frames), 1)

    result = None
    # Mirror production: only run precheck + metrics once detection clears.
    if detection_rate >= DETECT_POOR:
        precheck = scene_cut_precheck(video_path)
        result = compute_metrics(frames, fps=fps, hand_override=hand_override,
                                 precheck_cuts=precheck.get("pixel_cuts", 0))

    return _row_from(name, total_frames=len(frames), fps=fps, width=width,
                     height=height, detection_rate=detection_rate, result=result)


# ── Aggregation / reporting (pure) ────────────────────────────────────────────

def _to_bool(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in ("yes", "true", "1", "shot", "y")
    return None


def summarize_rows(rows, manifest=None):
    """Aggregate a list of CSV row dicts into a summary dict.

    If `manifest` (file -> {"expect": "shot"|"not_shot",
    "expect_continuous": "yes"|"no"}) is given, also computes shot-guard and
    continuity-guard accuracy (false-reject / false-accept rates).
    """
    total = len(rows)
    accepted = [r for r in rows if r["decision"] == "accept"]
    rejected = [r for r in rows if r["decision"] == "reject"]

    reason_counts = {}
    for r in rejected:
        reason_counts[r["reason"]] = reason_counts.get(r["reason"], 0) + 1

    warn_counts = {}
    for r in accepted:
        for w in (r["warnings"].split("|") if r["warnings"] else []):
            warn_counts[w] = warn_counts.get(w, 0) + 1

    def _stat(key):
        vals = [r[key] for r in accepted if isinstance(r.get(key), (int, float))]
        if not vals:
            return None
        return {"mean": round(sum(vals) / len(vals), 1),
                "min": min(vals), "max": max(vals), "n": len(vals)}

    summary = {
        "total": total,
        "accepted": len(accepted),
        "rejected": len(rejected),
        "reject_reasons": reason_counts,
        "warnings": warn_counts,
        "scores": {k: _stat(k) for k in ("overall", "power", "technique", "timing")},
    }

    if manifest:
        summary["shot_guard"] = _guard_accuracy(rows, manifest)
        summary["continuity_guard"] = _continuity_accuracy(rows, manifest)
    return summary


def _guard_accuracy(rows, manifest):
    """Confusion stats for the accept/reject (shot) guard against expectations."""
    tp = fp = tn = fn = unlabeled = 0
    false_rejects, false_accepts = [], []
    for r in rows:
        exp = manifest.get(r["file"], {}).get("expect")
        if exp not in ("shot", "not_shot"):
            unlabeled += 1
            continue
        accepted = r["decision"] == "accept"
        if exp == "shot":
            if accepted:
                tp += 1
            else:
                fn += 1
                false_rejects.append(r["file"])
        else:  # not_shot
            if accepted:
                fp += 1
                false_accepts.append(r["file"])
            else:
                tn += 1
    labeled = tp + fp + tn + fn
    return {
        "labeled": labeled, "unlabeled": unlabeled,
        "true_accept": tp, "true_reject": tn,
        "false_reject": fn, "false_accept": fp,
        "false_reject_rate": round(fn / (tp + fn), 3) if (tp + fn) else None,
        "false_accept_rate": round(fp / (fp + tn), 3) if (fp + tn) else None,
        "accuracy": round((tp + tn) / labeled, 3) if labeled else None,
        "false_reject_files": false_rejects,
        "false_accept_files": false_accepts,
    }


def _continuity_accuracy(rows, manifest):
    """How often the continuity warning matches the expected continuity."""
    correct = wrong = unlabeled = 0
    mismatches = []
    for r in rows:
        exp = _to_bool(manifest.get(r["file"], {}).get("expect_continuous"))
        if exp is None:
            unlabeled += 1
            continue
        got = r.get("looks_continuous")
        if got == "":
            unlabeled += 1
            continue
        if bool(got) == exp:
            correct += 1
        else:
            wrong += 1
            mismatches.append(r["file"])
    labeled = correct + wrong
    return {
        "labeled": labeled, "unlabeled": unlabeled,
        "correct": correct, "wrong": wrong,
        "accuracy": round(correct / labeled, 3) if labeled else None,
        "mismatch_files": mismatches,
    }


# ── Manifest + CLI ────────────────────────────────────────────────────────────

def load_manifest(path):
    """Read a manifest CSV into {file: {expect, expect_continuous}}."""
    out = {}
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            fname = (row.get("file") or "").strip()
            if not fname:
                continue
            out[fname] = {
                "expect": (row.get("expect") or "").strip().lower() or None,
                "expect_continuous": (row.get("expect_continuous") or "").strip().lower() or None,
            }
    return out


def write_csv(rows, dest):
    with open(dest, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def format_summary(summary):
    """Render the aggregate summary as a human-readable text block."""
    buf = io.StringIO()
    p = lambda *a: print(*a, file=buf)
    p("=" * 56)
    p(f"  {summary['total']} clips · "
      f"{summary['accepted']} accepted · {summary['rejected']} rejected")
    p("=" * 56)
    if summary["reject_reasons"]:
        p("Reject reasons:")
        for reason, n in sorted(summary["reject_reasons"].items(), key=lambda x: -x[1]):
            p(f"  {n:3d}  {reason}")
    if summary["warnings"]:
        p("Warnings (accepted but flagged):")
        for w, n in sorted(summary["warnings"].items(), key=lambda x: -x[1]):
            p(f"  {n:3d}  {w}")
    p("Score distribution (accepted clips):")
    for k in ("overall", "power", "technique", "timing"):
        st = summary["scores"].get(k)
        if st:
            p(f"  {k:10s} mean {st['mean']:5.1f}  range {st['min']}–{st['max']}  (n={st['n']})")
        else:
            p(f"  {k:10s} —")
    sg = summary.get("shot_guard")
    if sg and sg["labeled"]:
        p("-" * 56)
        p(f"Shot guard vs. {sg['labeled']} labeled clips:")
        p(f"  accuracy            {sg['accuracy']}")
        p(f"  false-reject rate   {sg['false_reject_rate']}  "
          f"({sg['false_reject']} real shots wrongly rejected)")
        p(f"  false-accept rate   {sg['false_accept_rate']}  "
          f"({sg['false_accept']} non-shots wrongly accepted)")
        if sg["false_reject_files"]:
            p(f"  false rejects: {', '.join(sg['false_reject_files'])}")
        if sg["false_accept_files"]:
            p(f"  false accepts: {', '.join(sg['false_accept_files'])}")
    cg = summary.get("continuity_guard")
    if cg and cg["labeled"]:
        p(f"Continuity guard vs. {cg['labeled']} labeled: accuracy {cg['accuracy']}"
          + (f"  (mismatches: {', '.join(cg['mismatch_files'])})" if cg["mismatch_files"] else ""))
    return buf.getvalue()


def _gather_clips(paths):
    """Expand directories into the video files they contain."""
    clips = []
    for path in paths:
        if os.path.isdir(path):
            for name in sorted(os.listdir(path)):
                if os.path.splitext(name)[1].lower() in VIDEO_EXTS:
                    clips.append(os.path.join(path, name))
        elif os.path.isfile(path):
            clips.append(path)
        else:
            print(f"  ! skipping (not found): {path}", file=sys.stderr)
    return clips


def main(argv=None):
    ap = argparse.ArgumentParser(description="Batch-evaluate clips through the analyzer.")
    ap.add_argument("paths", nargs="+", help="Clip folder(s) and/or video file(s).")
    ap.add_argument("--manifest", help="CSV of expected labels (file,expect,expect_continuous).")
    ap.add_argument("--out", default="batch_report.csv", help="Output CSV path.")
    ap.add_argument("--hand", choices=["left", "right"], help="Force shooting hand.")
    args = ap.parse_args(argv)

    clips = _gather_clips(args.paths)
    if not clips:
        print("No clips found.", file=sys.stderr)
        return 1
    manifest = load_manifest(args.manifest) if args.manifest else None

    rows = []
    for i, clip in enumerate(clips, 1):
        name = os.path.basename(clip)
        print(f"[{i}/{len(clips)}] {name} …", file=sys.stderr)
        try:
            row = evaluate_clip(clip, hand_override=args.hand)
        except Exception as e:
            print(f"  ! error: {e}", file=sys.stderr)
            row = _row_from(name, total_frames=0, fps=0, width=0, height=0,
                            detection_rate=0.0, result=None)
            row["reason"] = "error"
        rows.append(row)
        print(f"    -> {row['decision']}"
              + (f" ({row['reason']})" if row['reason'] else "")
              + (f"  overall={row['overall']}" if row['overall'] != "" else ""),
              file=sys.stderr)

    write_csv(rows, args.out)
    print(f"\nWrote {len(rows)} rows -> {args.out}\n", file=sys.stderr)
    print(format_summary(summarize_rows(rows, manifest)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
