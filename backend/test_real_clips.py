"""
test_real_clips.py — Regression net over REAL footage.

The guard thresholds (SHOT_MOTION_REJECT, SHOT_AIRBORNE_REJECT, CUT_JUMP, …)
were hand-calibrated on a handful of real YouTube clips. To stop those
thresholds from silently drifting out of calibration, we keep the *extracted
pose landmarks* of those clips as compact fixtures (backend/fixtures/*.json.gz)
and assert that compute_metrics still classifies each one correctly.

Landmarks only — no video is committed (the .mp4s stay on YouTube). Each fixture
is the gzipped output of pose.run_pose_detection rounded to 4 decimals.

Provenance (youtube.com/watch?v=<id>):
  hk_real_brady     iB_Fzjt5Vv4  real wrist shot, side view  → accepted
  hk_real_sideview  vC72_ncgbXc  real slap-shot tutorial     → accepted
  montage_slap      cCtRjybtDFs  multi-scene highlight reel  → rejected + cut
  pv_real_known     ZTBKeORXLDM  pole vault (wrong sport)    → rejected
  pv_real_14ft      kWFFsgg9p5g  pole vault (wrong sport)    → rejected

Run: python test_real_clips.py   (self-contained; no pytest needed)
"""
import gzip
import json
import os

import metrics as M

FIXDIR = os.path.join(os.path.dirname(__file__), "fixtures")

# Expected guard classification per clip. Values verified by hand against the
# source footage; if a threshold change flips one of these, that's a signal to
# re-check the calibration, not to blindly update the expectation.
EXPECT = {
    "hk_real_brady":    dict(looks_like_shot=True,  shot_reject=False, continuous=True),
    "hk_real_sideview": dict(looks_like_shot=True,  shot_reject=False, continuous=True),
    "montage_slap":     dict(looks_like_shot=False, shot_reject=True,  continuous=False),
    "pv_real_known":    dict(looks_like_shot=False, shot_reject=True,  continuous=True),
    "pv_real_14ft":     dict(looks_like_shot=False, shot_reject=True,  continuous=True),
}


def _load(clip):
    with gzip.open(os.path.join(FIXDIR, f"{clip}.landmarks.json.gz"), "rt") as fh:
        return json.load(fh)


def _check(clip):
    data = _load(clip)
    res = M.compute_metrics(data["frames"], fps=data["fps"])
    q = res["quality_report"]
    sc = q["shot_check"]
    cc = q["continuity_check"]
    exp = EXPECT[clip]
    assert sc["looks_like_shot"] is exp["looks_like_shot"], (
        f"{clip}: looks_like_shot={sc['looks_like_shot']} "
        f"(hip_rise={sc['hip_rise']}, wrist_travel={sc['wrist_travel']})")
    assert sc["reject"] is exp["shot_reject"], (
        f"{clip}: shot reject={sc['reject']} "
        f"(hip_rise={sc['hip_rise']}, wrist_travel={sc['wrist_travel']})")
    assert cc["looks_continuous"] is exp["continuous"], (
        f"{clip}: continuous={cc['looks_continuous']} "
        f"(cut_count={cc['cut_count']}, max_jump={cc['max_jump']})")


def test_real_brady_is_accepted():        _check("hk_real_brady")
def test_real_sideview_is_accepted():     _check("hk_real_sideview")
def test_montage_is_rejected_and_cut():   _check("montage_slap")
def test_vault_known_wrong_sport():       _check("pv_real_known")
def test_vault_14ft_wrong_sport():        _check("pv_real_14ft")


def test_montage_continuity_independent_of_shot_guard():
    # The montage is the case the continuity guard exists for: even setting aside
    # the airborne-fake that the shot guard catches, the scene cuts must show up.
    data = _load("montage_slap")
    cc = M.compute_metrics(data["frames"], fps=data["fps"])["quality_report"]["continuity_check"]
    assert cc["cut_count"] >= 1
    assert cc["max_jump"] > M.CUT_JUMP


def _run_all():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"\n{len(tests)} passed")


if __name__ == "__main__":
    _run_all()
