"""
Tests for training.py — the feedback-driven calibration report.

Self-contained: `python backend/test_training.py` (no pytest). Pure functions,
no file I/O.
"""

import tempfile
from pathlib import Path

import training as T


def test_fit_returns_none_under_two_points():
    assert T.fit_linear_calibration([]) is None
    assert T.fit_linear_calibration([(50, 60)]) is None


def test_fit_returns_none_when_all_ai_equal():
    # No spread in x → slope undefined.
    assert T.fit_linear_calibration([(50, 40), (50, 80)]) is None


def test_fit_recovers_known_linear_relationship():
    # human = 0.5*ai + 30 exactly → fit should recover it, zero residual error.
    pairs = [(ai, 0.5 * ai + 30) for ai in (20, 40, 60, 80, 100)]
    fit = T.fit_linear_calibration(pairs)
    assert abs(fit["a"] - 0.5) < 1e-6
    assert abs(fit["b"] - 30) < 1e-6
    assert fit["mae_after"] == 0.0
    assert fit["correlation"] == 1.0
    assert fit["n"] == 5


def test_fit_improves_on_identity_when_ai_biased():
    # AI is consistently 20 pts too low; calibration should cut error.
    pairs = [(ai, ai + 20) for ai in (30, 40, 50, 60, 70)]
    fit = T.fit_linear_calibration(pairs)
    assert fit["mae_before"] == 20.0
    assert fit["mae_after"] < 0.001
    assert fit["improvement"] > 19


def test_performance_report_not_ready_under_min_samples():
    recs = [{"type": "performance", "ai_score": 50, "human_score": 60}]
    rep = T.build_calibration_report(recs, min_samples=12)
    perf = rep["performance"]
    assert perf["n"] == 1
    assert perf["ready"] is False
    assert perf["calibration"] is None
    assert "more" in perf["recommendation"]


def test_performance_report_ready_computes_bias_and_fit():
    # 12 reviews, AI ~10 pts low on average.
    recs = [{"type": "performance", "ai_score": 40 + i, "human_score": 50 + i}
            for i in range(12)]
    rep = T.build_calibration_report(recs, min_samples=12)
    perf = rep["performance"]
    assert perf["ready"] is True
    assert perf["n"] == 12
    assert abs(perf["ai_bias"] - 10.0) < 1e-6     # human - ai = +10
    assert perf["calibration"] is not None
    assert perf["mae"] == 10.0


def test_performance_report_counts_score_checkboxes():
    recs = [
        {"type": "performance", "ai_score": 80, "human_score": 60,
         "human_checkboxes": ["ai_score_too_high"]},
        {"type": "performance", "ai_score": 30, "human_score": 55,
         "human_checkboxes": ["ai_score_too_low"]},
    ]
    perf = T.build_calibration_report(recs)["performance"]
    assert perf["too_high_count"] == 1
    assert perf["too_low_count"] == 1


def test_measurement_report_aggregates_metric_flags():
    recs = [
        {"type": "measurement", "metric_ratings": {
            "hip_rotation": "bad", "knee_bend": "good"}},
        {"type": "measurement", "metric_ratings": {
            "hip_rotation": "bad", "knee_bend": "good"}},
        {"type": "measurement", "metric_ratings": {
            "hip_rotation": "bad", "knee_bend": "bad"},
         "checkboxes": ["pose_lost"], "overall_label": "off"},
    ]
    meas = T.build_calibration_report(recs)["measurement"]
    assert meas["n"] == 3
    assert meas["metric_flags"]["hip_rotation"]["bad"] == 3
    assert meas["metric_flags"]["hip_rotation"]["bad_rate"] == 1.0
    assert meas["worst_metric"] == "hip_rotation"
    assert meas["checkbox_counts"]["pose_lost"] == 1
    assert meas["overall_label_counts"]["off"] == 1


def test_empty_records_is_safe():
    rep = T.build_calibration_report([])
    assert rep["total_feedback"] == 0
    assert rep["performance"]["n"] == 0
    assert rep["performance"]["calibration"] is None
    assert rep["measurement"]["worst_metric"] is None


def test_legacy_rows_without_type_treated_as_performance():
    recs = [{"ai_score": 50, "human_score": 55}]   # no "type" key
    perf = T.build_calibration_report(recs)["performance"]
    assert perf["n"] == 1


def test_apply_score_noop_when_disabled_or_missing():
    assert T.apply_score(50, None) == 50
    assert T.apply_score(50, {"enabled": False, "a": 2, "b": 0}) == 50
    assert T.apply_score(None, {"enabled": True, "a": 1, "b": 0}) is None


def test_apply_score_maps_and_clamps():
    calib = {"enabled": True, "a": 0.5, "b": 10}
    assert T.apply_score(80, calib) == 50          # 0.5*80+10
    calib_hi = {"enabled": True, "a": 2.0, "b": 0}
    assert T.apply_score(80, calib_hi) == 100      # clamped from 160
    calib_lo = {"enabled": True, "a": 1.0, "b": -50}
    assert T.apply_score(20, calib_lo) == 0        # clamped from -30


def test_apply_to_summary_preserves_overall_consistency():
    # overall is a weighted avg of subs; same affine map keeps it consistent.
    summary = {"overall": 60, "power": 70, "technique": 50, "timing": 60}
    calib = {"enabled": True, "a": 0.8, "b": 12}
    out = T.apply_to_summary(summary, calib)
    assert out["calibrated"] is True
    assert out["raw"]["overall"] == 60
    assert out["overall"] == round(0.8 * 60 + 12)
    assert out["power"] == round(0.8 * 70 + 12)


def test_apply_to_summary_noop_when_disabled():
    summary = {"overall": 60, "power": 70, "technique": 50, "timing": 60}
    assert T.apply_to_summary(summary, None) is summary
    assert T.apply_to_summary(summary, {"enabled": False}) is summary


def test_save_load_clear_calibration_roundtrip():
    d = tempfile.TemporaryDirectory()
    path = Path(d.name) / "calibration.json"
    assert T.load_calibration(path) is None
    saved = T.save_calibration(path, a=0.9, b=5, n=14, correlation=0.7)
    assert saved["enabled"] is True
    loaded = T.load_calibration(path)
    assert loaded["a"] == 0.9 and loaded["b"] == 5 and loaded["n"] == 14
    assert T.clear_calibration(path) is True
    assert T.load_calibration(path) is None
    assert T.clear_calibration(path) is False      # already gone
    d.cleanup()


def _run_all():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"\n{len(tests)} passed")


if __name__ == "__main__":
    _run_all()
