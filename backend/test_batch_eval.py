"""
test_batch_eval.py — Self-contained tests for the batch-eval harness.

The pure core (classify_clip, summarize_rows, guard-accuracy) is tested with
synthetic rows; the end-to-end classification is validated by replaying the
real-footage landmark fixtures through compute_metrics + classify_clip, so the
harness's accept/reject decision provably matches the production guards.

Run: python test_batch_eval.py   (no pytest needed)
"""
import gzip
import json
import os

import batch_eval as B
import metrics as M

FIXDIR = os.path.join(os.path.dirname(__file__), "fixtures")

# Same provenance as test_real_clips.py. Maps each fixture to whether the
# harness should ACCEPT it as a hockey shot.
EXPECT_ACCEPT = {
    "hk_real_brady":    True,
    "hk_real_sideview": True,
    "montage_slap":     False,   # airborne fake + scene cuts
    "pv_real_known":    False,   # wrong sport
    "pv_real_14ft":     False,   # wrong sport
}


def _load(clip):
    with gzip.open(os.path.join(FIXDIR, f"{clip}.landmarks.json.gz"), "rt") as fh:
        return json.load(fh)


# ── Pure classify_clip gates ──────────────────────────────────────────────────

def test_rejects_too_short():
    d = B.classify_clip(total_frames=5, fps=30, width=640, height=480,
                        detection_rate=1.0, result={"quality_report": {}})
    assert d["decision"] == "reject" and d["reason"] == "video_too_short"


def test_rejects_too_long():
    d = B.classify_clip(total_frames=3000, fps=30, width=640, height=480,
                        detection_rate=1.0, result={"quality_report": {}})
    assert d["reason"] == "video_too_long"


def test_rejects_unreadable():
    d = B.classify_clip(total_frames=100, fps=30, width=0, height=0,
                        detection_rate=1.0, result={"quality_report": {}})
    assert d["reason"] == "video_unreadable"


def test_rejects_no_body():
    d = B.classify_clip(total_frames=100, fps=30, width=640, height=480,
                        detection_rate=0.05, result=None)
    assert d["reason"] == "no_body_detected"


def test_rejects_poor_detection():
    d = B.classify_clip(total_frames=100, fps=30, width=640, height=480,
                        detection_rate=0.3, result=None)
    assert d["reason"] == "poor_detection"


def test_accepts_clean_shot():
    res = {"quality_report": {"shot_check": {"reject": False},
                              "continuity_check": {"looks_continuous": True}}}
    d = B.classify_clip(total_frames=100, fps=30, width=640, height=480,
                        detection_rate=0.95, result=res)
    assert d["decision"] == "accept" and d["warnings"] == []


def test_accepts_but_warns_on_cuts():
    res = {"quality_report": {"shot_check": {"reject": False},
                              "continuity_check": {"looks_continuous": False}}}
    d = B.classify_clip(total_frames=100, fps=30, width=640, height=480,
                        detection_rate=0.95, result=res)
    assert d["decision"] == "accept" and "camera_cuts" in d["warnings"]


def test_rejects_not_a_shot():
    res = {"quality_report": {"shot_check": {"reject": True}}}
    d = B.classify_clip(total_frames=100, fps=30, width=640, height=480,
                        detection_rate=0.95, result=res)
    assert d["reason"] == "not_a_hockey_shot"


# ── End-to-end on real-footage fixtures ───────────────────────────────────────

def test_fixtures_classify_as_expected():
    for clip, should_accept in EXPECT_ACCEPT.items():
        data = _load(clip)
        result = M.compute_metrics(data["frames"], fps=data["fps"])
        n = len(data["frames"])
        decision = B.classify_clip(total_frames=n, fps=data["fps"],
                                   width=100, height=100, detection_rate=1.0,
                                   result=result)
        got_accept = decision["decision"] == "accept"
        assert got_accept is should_accept, (
            f"{clip}: expected accept={should_accept}, got "
            f"{decision['decision']} ({decision['reason']})")


# ── Aggregation + guard accuracy ──────────────────────────────────────────────

def _row(file, decision, reason="", warnings="", overall="", looks_continuous=""):
    return {"file": file, "decision": decision, "reason": reason,
            "warnings": warnings, "overall": overall, "power": "", "technique": "",
            "timing": "", "looks_continuous": looks_continuous}


def test_summarize_counts_and_reasons():
    rows = [
        _row("a.mp4", "accept", overall=70),
        _row("b.mp4", "accept", overall=80, warnings="camera_cuts"),
        _row("c.mp4", "reject", reason="not_a_hockey_shot"),
        _row("d.mp4", "reject", reason="not_a_hockey_shot"),
        _row("e.mp4", "reject", reason="poor_detection"),
    ]
    s = B.summarize_rows(rows)
    assert s["total"] == 5 and s["accepted"] == 2 and s["rejected"] == 3
    assert s["reject_reasons"]["not_a_hockey_shot"] == 2
    assert s["warnings"]["camera_cuts"] == 1
    assert s["scores"]["overall"]["mean"] == 75.0


def test_guard_accuracy_confusion():
    rows = [
        _row("good1.mp4", "accept"),   # expected shot -> correct
        _row("good2.mp4", "reject", reason="not_a_hockey_shot"),  # expected shot -> FALSE REJECT
        _row("vault.mp4", "reject", reason="not_a_hockey_shot"),  # expected not_shot -> correct
        _row("sneaky.mp4", "accept"),  # expected not_shot -> FALSE ACCEPT
    ]
    manifest = {
        "good1.mp4": {"expect": "shot"},
        "good2.mp4": {"expect": "shot"},
        "vault.mp4": {"expect": "not_shot"},
        "sneaky.mp4": {"expect": "not_shot"},
    }
    sg = B.summarize_rows(rows, manifest)["shot_guard"]
    assert sg["labeled"] == 4
    assert sg["false_reject"] == 1 and sg["false_reject_files"] == ["good2.mp4"]
    assert sg["false_accept"] == 1 and sg["false_accept_files"] == ["sneaky.mp4"]
    assert sg["accuracy"] == 0.5
    assert sg["false_reject_rate"] == 0.5
    assert sg["false_accept_rate"] == 0.5


def test_continuity_accuracy():
    rows = [
        _row("cont.mp4", "accept", looks_continuous=True),    # expect yes -> ok
        _row("cut.mp4", "accept", looks_continuous=False, warnings="camera_cuts"),  # expect no -> ok
        _row("miss.mp4", "accept", looks_continuous=True),    # expect no -> mismatch
    ]
    manifest = {
        "cont.mp4": {"expect_continuous": "yes"},
        "cut.mp4": {"expect_continuous": "no"},
        "miss.mp4": {"expect_continuous": "no"},
    }
    cg = B.summarize_rows(rows, manifest)["continuity_guard"]
    assert cg["labeled"] == 3 and cg["correct"] == 2 and cg["wrong"] == 1
    assert cg["mismatch_files"] == ["miss.mp4"]


def test_format_summary_runs():
    rows = [_row("a.mp4", "accept", overall=70)]
    text = B.format_summary(B.summarize_rows(rows))
    assert "1 clips" in text and "accepted" in text


def _run_all():
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
        passed += 1
    print(f"\n{passed} passed")


if __name__ == "__main__":
    _run_all()
