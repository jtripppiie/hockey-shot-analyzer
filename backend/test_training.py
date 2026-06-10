"""
Tests for training.py — the feedback-driven calibration report.

Self-contained: `python backend/test_training.py` (no pytest). Pure functions,
no file I/O.
"""

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


def _run_all():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"\n{len(tests)} passed")


if __name__ == "__main__":
    _run_all()
