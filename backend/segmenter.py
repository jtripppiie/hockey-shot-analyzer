"""
segmenter.py — Auto-splice a long stream into individual attempts (SKELETON).

Given the per-frame landmarks for a whole practice stream (the same
`run_pose_detection` output the analyzer already produces), find where each
attempt (slap shot) happens and return a list of cut windows. Each window can
then be trimmed and fed to the existing analyzer as its own job.

This is a SKELETON. The signal it uses — dominant-wrist speed peaks — is the
same idea the single-clip release detector in `metrics._detect_phases` uses,
generalized to find MULTIPLE peaks across a long recording. The peak-picking and
window math here are intentionally simple/conservative placeholders with TODOs;
they must be tuned and validated against real multi-rep clips before being
trusted (see ROADMAP Phase 3, and the project rule: accuracy > speed).

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
# multi-frame speed plateau from registering as several reps.
MIN_EVENT_GAP_S = 2.0

# A candidate peak must exceed (median + K*MAD) of the speed signal to count as
# a real attempt rather than ambient motion (skating, adjusting, etc.).
PEAK_K = 4.0


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


def find_events(frames: list[dict], fps: float) -> list[dict]:
    """Find candidate attempt events in a long stream.

    Returns a list of {"frame": peak_idx, "score": speed, "confidence": 0..1}
    ordered by frame. SKELETON: greedy peak-pick with a refractory gap. Replace
    with a proper local-maxima + non-max-suppression pass when tuning.
    """
    dom = _detect_dominant_hand([f for f in frames if f.get("landmarks")])
    if not dom:
        return []

    speeds = _wrist_speed_series(frames, dom, fps)
    if not speeds:
        return []

    thr = _peak_threshold(speeds)
    gap_frames = int(round(MIN_EVENT_GAP_S * fps))

    # TODO(Phase 3): true local-maxima detection + non-max suppression instead of
    # this greedy "above threshold and far enough from last accepted" scan.
    # TODO(Phase 3): smooth the speed series first (short moving average) to avoid
    # picking jitter, mirroring the single-clip detector.
    events = []
    last_idx = None
    for frame_idx, speed in speeds:
        if speed < thr:
            continue
        if last_idx is not None and (frame_idx - last_idx) < gap_frames:
            # Keep the stronger of the two within the refractory window.
            if speed > events[-1]["score"]:
                events[-1] = {"frame": frame_idx, "score": speed, "confidence": 0.0}
                last_idx = frame_idx
            continue
        events.append({"frame": frame_idx, "score": speed, "confidence": 0.0})
        last_idx = frame_idx

    # TODO(Phase 3): map raw speed → calibrated 0..1 confidence for the UI.
    return events


def events_to_windows(events: list[dict], fps: float, total_frames: int) -> list[dict]:
    """Convert detected events into clamped [start_frame, end_frame] cut windows.

    Returns a list of {"start", "end", "event"} dicts. These are SUGGESTED cuts;
    the UI lets the user confirm/adjust before each window is trimmed and sent to
    the analyzer (Phase 3).
    """
    pre = int(round(PRE_EVENT_S * fps))
    post = int(round(POST_EVENT_S * fps))
    windows = []
    for ev in events:
        start = max(0, ev["frame"] - pre)
        end = min(total_frames - 1, ev["frame"] + post)
        windows.append({"start": start, "end": end, "event": ev["frame"]})

    # TODO(Phase 3): merge overlapping windows (two close events → one clip) and
    # drop windows shorter than a sane minimum attempt length.
    return windows


def suggest_segments(frames: list[dict], fps: float, total_frames: int) -> list[dict]:
    """Top-level convenience: stream landmarks → suggested cut windows.

    This is the single entry point the /session/{id}/segment route will call.
    SKELETON wiring; the heavy lifting in find_events/events_to_windows is the
    part that needs tuning + validation.
    """
    events = find_events(frames, fps)
    return events_to_windows(events, fps, total_frames)
