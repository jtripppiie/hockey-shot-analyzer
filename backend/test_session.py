"""
Tests for session.py (multi-rep model + summarize_session) and the segmenter's
peak-picking. Self-contained: runs with plain `python backend/test_session.py`
(no pytest required), and is also pytest-compatible.

All session I/O is redirected to a temp dir so the real output/ folder is never
touched.
"""

import tempfile
from pathlib import Path

import session as S
import segmenter as SEG
import metrics as M


def _use_tmp_output():
    """Point session storage at a fresh temp dir; return it (caller keeps ref)."""
    tmp = tempfile.TemporaryDirectory()
    S.OUTPUT_DIR = Path(tmp.name)
    return tmp


def test_session_round_trip():
    keep = _use_tmp_output()
    s = S.create_session("Round-trip")
    sid = s["session_id"]
    assert s["label"] == "Round-trip"
    assert s["job_ids"] == []

    assert S.load_session(sid)["session_id"] == sid
    S.add_job(sid, "job-a")
    S.add_job(sid, "job-b")
    S.add_job(sid, "job-a")  # duplicate ignored, order preserved
    assert S.load_session(sid)["job_ids"] == ["job-a", "job-b"]

    assert any(x["session_id"] == sid for x in S.list_sessions())
    assert S.delete_session(sid) is True
    assert S.load_session(sid) is None
    assert S.delete_session(sid) is False
    keep.cleanup()


def _jobs(*triples):
    """Build result-json-shaped jobs from (overall, power, technique, timing)."""
    out = []
    for i, (o, p, t, ti) in enumerate(triples):
        out.append({
            "job_id": f"j{i}",
            "date": f"10:0{i}",
            "summary": {"overall": o, "power": p, "technique": t, "timing": ti},
        })
    return out


def test_summarize_averages_and_trends():
    session = {"session_id": "x", "label": "L", "created": "2026-06-09 10:00"}
    jobs = _jobs((55, 40, 70, 50), (62, 55, 68, 55), (70, 65, 66, 72))
    summ = S.summarize_session(session, jobs)

    assert summ["attempt_count"] == 3
    # averages = rounded means
    assert summ["averages"]["overall"] == round((55 + 62 + 70) / 3)
    assert summ["averages"]["power"] == round((40 + 55 + 65) / 3)
    assert summ["averages"]["technique"] == round((70 + 68 + 66) / 3)

    trends = summ["trends"]
    # first-vs-last deltas: power +25 (improved most), technique -4 (only regress)
    assert "+25" in trends["power"] and "▲" in trends["power"]
    assert "-4" in trends["technique"] and "▼" in trends["technique"]
    assert trends["most_improved"].startswith("power")
    assert trends["needs_work"].startswith("technique")


def test_summarize_single_attempt_has_no_trends():
    session = {"session_id": "x", "label": "L", "created": "2026-06-09 10:00"}
    summ = S.summarize_session(session, _jobs((60, 50, 50, 50)))
    assert summ["averages"]["overall"] == 60  # average still computed
    assert summ["trends"] == {}               # need >= 2 attempts for a trend


def test_summarize_empty_session():
    summ = S.summarize_session({"session_id": "x", "label": "L", "created": ""}, [])
    assert summ["attempt_count"] == 0
    assert summ["averages"] == {}
    assert summ["trends"] == {}


def _shot_frames(n, peaks, fps_jitter_seed=1):
    """Synthetic stream: dominant (right) wrist lurches at each `peaks` frame."""
    import random
    random.seed(fps_jitter_seed)
    frames = []
    for i in range(n):
        x = 0.5 + random.uniform(-0.004, 0.004)
        for c in peaks:
            if abs(i - c) < 6:
                x = 0.5 + 0.18 * (1 - abs(i - c) / 6)
        frames.append({"frame": i, "landmarks": {
            "right_wrist": {"x": x, "y": 0.5, "v": 1.0},
            "right_shoulder": {"x": 0.4, "y": 0.4, "v": 1.0},
            "left_shoulder": {"x": 0.6, "y": 0.4, "v": 1.0},
            "right_hip": {"x": 0.45, "y": 0.7, "v": 1.0},
            "left_hip": {"x": 0.55, "y": 0.7, "v": 1.0},
            "right_elbow": {"x": 0.45, "y": 0.45, "v": 1.0},
        }})
    return frames


def test_segmenter_finds_each_peak_once():
    frames = _shot_frames(210, peaks=(40, 110, 175))
    events = SEG.find_events(frames, 30.0)
    assert len(events) == 3
    found = sorted(e["frame"] for e in events)
    # each detected peak lands within a few frames of the injected peak
    for got, want in zip(found, (40, 110, 175)):
        assert abs(got - want) <= 4
    # confidences are calibrated into [0, 1]
    assert all(0.0 <= e["confidence"] <= 1.0 for e in events)


def test_segmenter_no_false_peak_on_flat_stream():
    frames = _shot_frames(120, peaks=())  # only jitter, no real shot
    assert SEG.find_events(frames, 30.0) == []


def _stickhandling_multishot(n=300, shots=(70, 160, 250)):
    """Between shots the dominant wrist drifts (stickhandling) which inflates the
    speed MAD; at each shot frame it spikes sharply (the release). Mirrors the
    pole repo's noisy-approach fixture, but for hockey's sharp wrist-speed signal:
    the release peak sits well above the median even with the drift, so the
    PEAK_K=4 threshold still isolates each real shot.
    """
    import math, random
    random.seed(3)
    frames = []
    for i in range(n):
        x = 0.5 + 0.06 * math.sin(i / 9.0) + random.uniform(-0.02, 0.02)
        y = 0.5 + 0.04 * math.cos(i / 7.0)
        for c in shots:
            if abs(i - c) < 5:
                x = 0.5 + 0.22 * (1 - abs(i - c) / 5)  # sharp release spike
        frames.append({"frame": i, "landmarks": {
            "right_wrist":    {"x": x,   "y": y,   "v": 1.0},
            "right_shoulder": {"x": 0.4, "y": 0.4, "v": 1.0},
            "left_shoulder":  {"x": 0.6, "y": 0.4, "v": 1.0},
        }})
    return frames


def test_segmenter_detects_shots_amid_stickhandling():
    # Regression: between-shot stickhandling inflates the speed MAD, but the
    # sharp release spike still clears PEAK_K=4 — every real shot is found once.
    frames = _stickhandling_multishot()
    sp = SEG._smooth(SEG._wrist_speed_series(frames, "right", 30.0),
                     int(round(SEG.SMOOTH_S * 30.0)))
    vals = sorted(v for _, v in sp)
    med = vals[len(vals) // 2]
    mad = sorted(abs(v - med) for v in vals)[len(vals) // 2]
    peak = max(v for _, v in sp)
    # The hockey signal is sharp: the peak is many MAD above the median (unlike
    # the pole apex, which is only ~2 MAD up). This is why PEAK_K=4 holds.
    assert (peak - med) / mad > 8.0

    events = SEG.find_events(frames, 30.0)
    assert len(events) == 3
    for got, want in zip(sorted(e["frame"] for e in events), (70, 160, 250)):
        assert abs(got - want) <= 4


def test_events_to_windows_merges_overlaps():
    # two events 20 frames apart with 45-frame padding → windows overlap → merge
    events = [{"frame": 50, "confidence": 0.8}, {"frame": 70, "confidence": 1.0}]
    windows = SEG.events_to_windows(events, 30.0, total_frames=300)
    assert len(windows) == 1
    assert windows[0]["confidence"] == 1.0  # keeps strongest contributor


def _grounded_shot_frames(n=90):
    """A planted shooter: hips steady, dominant (right) wrist sweeps a real arc."""
    import math
    frames = []
    for i in range(n):
        p = i / (n - 1)
        wx = 0.40 + 0.45 * p                       # wrist sweeps across the body
        wy = 0.55 - 0.20 * math.sin(math.pi * p)   # small lift through the shot
        frames.append({"frame": i, "landmarks": {
            "right_wrist":    {"x": wx,   "y": wy,  "v": 1.0},
            "right_shoulder": {"x": 0.40, "y": 0.40, "v": 1.0},
            "left_shoulder":  {"x": 0.60, "y": 0.40, "v": 1.0},
            "right_hip":      {"x": 0.45, "y": 0.70, "v": 1.0},
            "left_hip":       {"x": 0.55, "y": 0.70, "v": 1.0},
            "right_knee":     {"x": 0.45, "y": 0.85, "v": 1.0},
            "right_ankle":    {"x": 0.45, "y": 0.97, "v": 1.0},
        }})
    return frames


def test_shot_check_passes_grounded_shot():
    res = M.compute_metrics(_grounded_shot_frames(), fps=30.0)
    sc = res["quality_report"]["shot_check"]
    assert sc["looks_like_shot"] is True
    assert sc["reject"] is False


def test_shot_check_rejects_airborne_clip():
    # A jump/vault: hips sit grounded then spike upward for a brief airborne
    # window (wrist still moves) → not a grounded shot.
    frames = []
    for i in range(90):
        lift = 0.30 if 40 <= i <= 55 else 0.0   # brief airborne burst
        frames.append({"frame": i, "landmarks": {
            "right_wrist":    {"x": 0.40 + 0.45 * (i / 89.0), "y": 0.50 - lift, "v": 1.0},
            "right_shoulder": {"x": 0.40, "y": 0.40 - lift, "v": 1.0},
            "left_shoulder":  {"x": 0.60, "y": 0.40 - lift, "v": 1.0},
            "right_hip":      {"x": 0.45, "y": 0.70 - lift, "v": 1.0},
            "left_hip":       {"x": 0.55, "y": 0.70 - lift, "v": 1.0},
        }})
    res = M.compute_metrics(frames, fps=30.0)
    sc = res["quality_report"]["shot_check"]
    assert sc["looks_like_shot"] is False
    assert sc["reject"] is True
    assert any("doesn't look like a hockey shot" in w
               for w in res["quality_report"]["warnings"])


def test_shot_check_rejects_static_clip():
    # A still person: barely any wrist motion → no shooting action.
    frames = []
    for i in range(60):
        jit = 0.01 * ((i % 4) - 1.5)
        frames.append({"frame": i, "landmarks": {
            "right_wrist":    {"x": 0.50 + jit, "y": 0.55, "v": 1.0},
            "right_shoulder": {"x": 0.40, "y": 0.40, "v": 1.0},
            "left_shoulder":  {"x": 0.60, "y": 0.40, "v": 1.0},
            "right_hip":      {"x": 0.45, "y": 0.70, "v": 1.0},
            "left_hip":       {"x": 0.55, "y": 0.70, "v": 1.0},
        }})
    res = M.compute_metrics(frames, fps=30.0)
    sc = res["quality_report"]["shot_check"]
    assert sc["looks_like_shot"] is False
    assert sc["reject"] is True


def test_continuity_passes_continuous_clip():
    res = M.compute_metrics(_grounded_shot_frames(), fps=30.0)
    cc = res["quality_report"]["continuity_check"]
    assert cc["cut_count"] == 0
    assert cc["looks_continuous"] is True


def test_continuity_flags_montage_cut():
    # A montage: a single mid-clip frame teleports the whole body by ~1.5 torso
    # lengths (a hard camera cut), which a continuous attempt never does.
    frames = _grounded_shot_frames(90)
    for i in range(45, 90):                 # second "scene": body shifted down
        for k, p in frames[i]["landmarks"].items():
            p["y"] += 0.45                  # torso ~0.30 → jump ~1.5 lengths
    res = M.compute_metrics(frames, fps=30.0)
    cc = res["quality_report"]["continuity_check"]
    assert cc["cut_count"] >= 1
    assert cc["looks_continuous"] is False
    assert cc["max_jump"] > M.CUT_JUMP
    assert any("camera cuts" in w for w in res["quality_report"]["warnings"])


def _run_all():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"\n{len(tests)} passed")


if __name__ == "__main__":
    _run_all()
