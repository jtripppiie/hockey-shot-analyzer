"""
Tests for errors.py — the centralized error log: append, clear_errors, and the
opt-in ERROR_LOG_MAX_LINES rotation cap.

Self-contained: runs with plain `python backend/test_errors.py` (no pytest), and
is also pytest-compatible. All log I/O goes to a temp file so the real
output/error_log.jsonl is never touched.
"""

import json
import logging
import os
import tempfile
from pathlib import Path

import errors as E

# errors.log_error mirrors every entry to stderr via logging; silence it so the
# test output stays readable (we assert on the file, not the log stream).
logging.disable(logging.CRITICAL)


def _tmp_log():
    d = tempfile.TemporaryDirectory()
    return d, Path(d.name) / "error_log.jsonl"


def test_log_error_appends_one_line_per_call():
    keep, path = _tmp_log()
    E.log_error("unit", message="first", log_path=path)
    E.log_error("unit", message="second", log_path=path)
    lines = [l for l in path.read_text().splitlines() if l.strip()]
    assert len(lines) == 2
    assert json.loads(lines[0])["message"] == "first"
    assert json.loads(lines[1])["message"] == "second"
    keep.cleanup()


def test_log_error_captures_exception_type_and_traceback():
    keep, path = _tmp_log()
    try:
        raise ValueError("boom")
    except ValueError as exc:
        rec = E.log_error("where", exc, log_path=path)
    assert rec["error_type"] == "ValueError"
    assert rec["message"] == "boom"
    assert "ValueError" in rec["traceback"]
    keep.cleanup()


def test_clear_errors_returns_count_and_removes_file():
    keep, path = _tmp_log()
    for i in range(4):
        E.log_error("unit", message=f"e{i}", log_path=path)
    removed = E.clear_errors(log_path=path)
    assert removed == 4
    assert not path.exists()
    keep.cleanup()


def test_clear_errors_on_missing_log_is_zero():
    keep, path = _tmp_log()
    assert not path.exists()
    assert E.clear_errors(log_path=path) == 0
    keep.cleanup()


def test_recent_errors_newest_first_and_tolerates_bad_lines():
    keep, path = _tmp_log()
    E.log_error("unit", message="old", log_path=path)
    E.log_error("unit", message="new", log_path=path)
    with open(path, "a") as f:
        f.write("{not valid json\n")  # malformed line must be skipped
    rows = E.recent_errors(limit=10, log_path=path)
    assert [r["message"] for r in rows] == ["new", "old"]
    keep.cleanup()


def test_cap_disabled_by_default_keeps_all_entries():
    keep, path = _tmp_log()
    os.environ.pop("ERROR_LOG_MAX_LINES", None)
    for i in range(12):
        E.log_error("unit", message=f"e{i}", log_path=path)
    lines = [l for l in path.read_text().splitlines() if l.strip()]
    assert len(lines) == 12
    keep.cleanup()


def test_cap_trims_to_newest_n_when_flag_set():
    keep, path = _tmp_log()
    os.environ["ERROR_LOG_MAX_LINES"] = "5"
    try:
        for i in range(12):
            E.log_error("unit", message=f"e{i}", log_path=path)
        lines = [l for l in path.read_text().splitlines() if l.strip()]
        assert len(lines) == 5
        msgs = [json.loads(l)["message"] for l in lines]
        assert msgs == [f"e{i}" for i in range(7, 12)]  # newest five
    finally:
        os.environ.pop("ERROR_LOG_MAX_LINES", None)
    keep.cleanup()


def test_cap_ignores_invalid_flag_value():
    keep, path = _tmp_log()
    os.environ["ERROR_LOG_MAX_LINES"] = "not-a-number"
    try:
        for i in range(8):
            E.log_error("unit", message=f"e{i}", log_path=path)
        lines = [l for l in path.read_text().splitlines() if l.strip()]
        assert len(lines) == 8  # invalid flag → treated as disabled
    finally:
        os.environ.pop("ERROR_LOG_MAX_LINES", None)
    keep.cleanup()


def _run_all():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"\n{len(tests)} passed")


if __name__ == "__main__":
    _run_all()
