"""
Tests for the multi-attempt segment path: _trim_clip (frame-accurate ffmpeg cut
backing /analyze-segment) and the suggest_segments → _trim_clip round-trip that
turns a multi-rep clip into individually trimmable attempts.

Self-contained: runs with plain `python backend/test_segment.py` (no pytest).
Requires ffmpeg on PATH (the app already depends on it); the test generates its
own throwaway clip and skips gracefully if ffmpeg is unavailable.
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import segmenter as SEG
from pose import get_video_meta


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _make_clip(path: Path, seconds: int = 6, fps: int = 30) -> None:
    """Generate a solid-color test clip of known duration with ffmpeg."""
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi",
         "-i", f"color=c=green:s=320x240:d={seconds}:r={fps}",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)],
        capture_output=True, text=True, check=True,
    )


def _duration_s(path: Path) -> float:
    meta = get_video_meta(str(path))
    fps = meta["fps"] or 30.0
    return meta["total_frames"] / fps


def _shot_frames(n, peaks):
    """Synthetic multi-rep stream: dominant wrist lurches at each peak frame."""
    import random
    random.seed(7)
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


def test_trim_clip_produces_requested_duration():
    if not _ffmpeg_available():
        print("  skip test_trim_clip_produces_requested_duration (no ffmpeg)")
        return
    from main import _trim_clip
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "src.mp4"
        dst = Path(d) / "cut.mp4"
        _make_clip(src, seconds=6)
        _trim_clip(str(src), str(dst), 1.0, 3.0)
        assert dst.exists() and dst.stat().st_size > 0
        # 2.0s window, allow a little container/keyframe slack
        assert abs(_duration_s(dst) - 2.0) < 0.4


def test_trim_clip_raises_on_bad_source():
    if not _ffmpeg_available():
        print("  skip test_trim_clip_raises_on_bad_source (no ffmpeg)")
        return
    from main import _trim_clip
    with tempfile.TemporaryDirectory() as d:
        dst = Path(d) / "out.mp4"
        raised = False
        try:
            _trim_clip(str(Path(d) / "nope.mp4"), str(dst), 0.0, 1.0)
        except RuntimeError:
            raised = True
        assert raised
        assert not dst.exists()


def test_suggest_then_trim_round_trip():
    """The windows suggest_segments returns must be trimmable into real clips —
    the same flow /analyze-segment performs per attempt."""
    if not _ffmpeg_available():
        print("  skip test_suggest_then_trim_round_trip (no ffmpeg)")
        return
    from main import _trim_clip
    fps, total = 30.0, 360
    frames = _shot_frames(total, peaks=(50, 170, 290))
    windows = SEG.suggest_segments(frames, fps, total)
    assert len(windows) == 3
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "multi.mp4"
        _make_clip(src, seconds=int(total / fps) + 1, fps=int(fps))
        for i, w in enumerate(windows):
            start = w["start"] / fps
            end = w["end"] / fps
            assert end > start
            dst = Path(d) / f"attempt_{i}.mp4"
            _trim_clip(str(src), str(dst), start, end)
            assert dst.exists() and dst.stat().st_size > 0
            # trimmed length is within slack of the requested window
            assert abs(_duration_s(dst) - (end - start)) < 0.5


def _run_all():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"\n{len(tests)} passed")


if __name__ == "__main__":
    _run_all()
