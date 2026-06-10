"""
Tests for the storage-retention helpers in main.py: stale-upload sweeping, the
opt-in history cap, and per-job artifact deletion.

Self-contained: runs with plain `python backend/test_cleanup.py` (no pytest).
All file I/O is redirected to a temp dir so the real uploads/ and output/ are
never touched. Importing main pulls in MediaPipe; filter stderr if noisy.
"""

import csv
import logging
import os
import tempfile
import time
from pathlib import Path

import main as M

logging.disable(logging.CRITICAL)


def _redirect(tmp: Path):
    """Point main's storage globals at a temp dir and return originals."""
    up = tmp / "uploads"
    out = tmp / "output"
    up.mkdir()
    out.mkdir()
    saved = (M.UPLOAD_DIR, M.OUTPUT_DIR, M.HISTORY_CSV)
    M.UPLOAD_DIR = up
    M.OUTPUT_DIR = out
    M.HISTORY_CSV = out / "history.csv"
    return saved


def _restore(saved):
    M.UPLOAD_DIR, M.OUTPUT_DIR, M.HISTORY_CSV = saved


def _touch(path: Path, age_s: float = 0.0):
    path.write_bytes(b"x")
    if age_s:
        old = time.time() - age_s
        os.utime(path, (old, old))


def test_sweep_removes_only_stale_uploads():
    d = tempfile.TemporaryDirectory()
    saved = _redirect(Path(d.name))
    try:
        fresh = M.UPLOAD_DIR / "abc123_render.mp4"
        stale = M.UPLOAD_DIR / "old_multi.mp4"
        stale2 = M.UPLOAD_DIR / "orphan_upload.mov"
        _touch(fresh, age_s=0)
        _touch(stale, age_s=7200)
        _touch(stale2, age_s=7200)
        removed = M._sweep_old_uploads(max_age_s=3600)
        assert removed == 2
        assert fresh.exists()
        assert not stale.exists()
        assert not stale2.exists()
    finally:
        _restore(saved)
        d.cleanup()


def test_sweep_handles_empty_dir():
    d = tempfile.TemporaryDirectory()
    saved = _redirect(Path(d.name))
    try:
        assert M._sweep_old_uploads(max_age_s=3600) == 0
    finally:
        _restore(saved)
        d.cleanup()


def test_delete_job_artifacts_removes_all_job_files_only():
    d = tempfile.TemporaryDirectory()
    saved = _redirect(Path(d.name))
    try:
        jid = "deadbeef01"
        keep_jid = "deadbeef02"
        for name in (f"{jid}_overlay.mp4", f"{jid}_frame.jpg",
                     f"{jid}_result.json", f"{jid}_capture_123.jpg"):
            _touch(M.OUTPUT_DIR / name)
        survivor = M.OUTPUT_DIR / f"{keep_jid}_overlay.mp4"
        _touch(survivor)
        M._delete_job_artifacts(jid)
        assert not any(M.OUTPUT_DIR.glob(f"{jid}_*"))
        assert survivor.exists()
    finally:
        _restore(saved)
        d.cleanup()


def test_delete_job_artifacts_sanitizes_id():
    d = tempfile.TemporaryDirectory()
    saved = _redirect(Path(d.name))
    try:
        victim = M.OUTPUT_DIR / "safe_overlay.mp4"
        _touch(victim)
        # A traversal-y id must not escape OUTPUT_DIR or wipe unrelated files.
        M._delete_job_artifacts("../../etc/passwd")
        assert victim.exists()
    finally:
        _restore(saved)
        d.cleanup()


def _write_history(rows):
    fieldnames = ["job_id", "filename", "date", "overall"]
    with open(M.HISTORY_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def test_history_cap_disabled_by_default():
    d = tempfile.TemporaryDirectory()
    saved = _redirect(Path(d.name))
    try:
        _write_history([{"job_id": f"j{i}", "filename": "f", "date": "d",
                         "overall": i} for i in range(10)])
        assert M._enforce_history_cap(max_entries=0) == 0
        with open(M.HISTORY_CSV, newline="") as f:
            assert len(list(csv.DictReader(f))) == 10
    finally:
        _restore(saved)
        d.cleanup()


def test_history_cap_trims_and_deletes_pruned_artifacts():
    d = tempfile.TemporaryDirectory()
    saved = _redirect(Path(d.name))
    try:
        rows = [{"job_id": f"job{i}", "filename": "f", "date": "d",
                 "overall": i} for i in range(6)]
        _write_history(rows)
        for r in rows:
            _touch(M.OUTPUT_DIR / f"{r['job_id']}_overlay.mp4")
        dropped = M._enforce_history_cap(max_entries=2)
        assert dropped == 4
        with open(M.HISTORY_CSV, newline="") as f:
            kept = list(csv.DictReader(f))
        kept_ids = [r["job_id"] for r in kept]
        assert kept_ids == ["job4", "job5"]          # newest tail kept
        for i in range(4):
            assert not (M.OUTPUT_DIR / f"job{i}_overlay.mp4").exists()
        for i in (4, 5):
            assert (M.OUTPUT_DIR / f"job{i}_overlay.mp4").exists()
    finally:
        _restore(saved)
        d.cleanup()


def test_history_cap_noop_when_under_limit():
    d = tempfile.TemporaryDirectory()
    saved = _redirect(Path(d.name))
    try:
        _write_history([{"job_id": "a", "filename": "f", "date": "d",
                         "overall": 1}])
        assert M._enforce_history_cap(max_entries=50) == 0
    finally:
        _restore(saved)
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
