"""
overlay.py — Draw MediaPipe Tasks skeleton onto video frames and save output video.
"""

import os
import subprocess
import tempfile
import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision
from pose import MODEL_PATH, POSE_CONNECTIONS, LANDMARKS


def _joint_color(score: int) -> tuple:
    """Traffic-light BGR color based on overall score."""
    if score >= 80:
        return (80, 200, 0)    # green
    elif score >= 50:
        return (0, 165, 255)   # orange
    else:
        return (60, 60, 220)   # red


def _draw_skeleton(frame: np.ndarray, landmarks, color: tuple) -> None:
    """Draw connections and joint dots onto a BGR frame in-place."""
    h, w = frame.shape[:2]
    # All 33 landmarks are in `landmarks` (a list of NormalizedLandmark)
    pts = {i: (int(lm.x * w), int(lm.y * h)) for i, lm in enumerate(landmarks)}
    # Orange BGR (matches "TripperDee" vibe + high visibility on ice/jerseys)
    line_color = (0, 140, 255)
    line_thickness = max(3, int(min(w, h) / 240))
    dot_radius = max(8, int(min(w, h) / 110))
    # Draw connections
    for a, b in POSE_CONNECTIONS:
        if a in pts and b in pts:
            cv2.line(frame, pts[a], pts[b], line_color, line_thickness, cv2.LINE_AA)
    # Draw joints (white outline ring + colored fill for contrast)
    for idx in set(i for pair in POSE_CONNECTIONS for i in pair):
        if idx in pts:
            cv2.circle(frame, pts[idx], dot_radius + 2, (255, 255, 255), -1, cv2.LINE_AA)
            cv2.circle(frame, pts[idx], dot_radius, color, -1, cv2.LINE_AA)


def _make_image_detector():
    base_opts = mp_python.BaseOptions(model_asset_path=MODEL_PATH)
    opts = mp_vision.PoseLandmarkerOptions(
        base_options=base_opts,
        running_mode=mp_vision.RunningMode.IMAGE,
        num_poses=1,
    )
    return mp_vision.PoseLandmarker.create_from_options(opts)


def _make_video_detector():
    base_opts = mp_python.BaseOptions(model_asset_path=MODEL_PATH)
    opts = mp_vision.PoseLandmarkerOptions(
        base_options=base_opts,
        running_mode=mp_vision.RunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    return mp_vision.PoseLandmarker.create_from_options(opts)


def render_overlay(video_path: str, output_path: str, overall_score: int = 75) -> str:
    """
    Draw skeleton overlay on every 3rd frame (interpolate others) for speed.
    Re-encodes to H.264 for browser compatibility.

    Writes to a temp file first and only moves into place after H.264 re-encoding
    so the final URL never serves the intermediate mp4v file (which browsers
    can't play).
    """
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    # Render to a temp path so output_path stays absent until everything is ready
    staging_path = output_path + ".staging.mp4"

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out_writer = cv2.VideoWriter(staging_path, fourcc, fps, (w, h))
    color = _joint_color(overall_score)

    last_landmarks = None
    with _make_video_detector() as detector:
        idx = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            # Only run pose detection every 3rd frame
            if idx % 3 == 0:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                timestamp_ms = int(idx * 1000 / fps)
                result = detector.detect_for_video(mp_img, timestamp_ms)
                last_landmarks = result.pose_landmarks[0] if result.pose_landmarks else None
            if last_landmarks is not None:
                _draw_skeleton(frame, last_landmarks, color)
            out_writer.write(frame)
            idx += 1

    cap.release()
    out_writer.release()

    # Re-encode the staging file to H.264, then atomically move to final path
    _reencode_h264(staging_path)
    os.replace(staging_path, output_path)
    return output_path


def _reencode_h264(path: str) -> None:
    """Re-encode a video file to H.264 in-place using ffmpeg.

    Uses Baseline profile + level 3.1 + yuv420p + even dimensions for the
    widest possible browser support (Safari, Firefox, Chrome, Edge).
    """
    tmp = path + ".tmp.mp4"
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", path,
                "-c:v", "libx264",
                "-profile:v", "baseline",
                "-level", "3.1",
                "-pix_fmt", "yuv420p",
                "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                "-preset", "fast",
                "-crf", "23",
                "-movflags", "+faststart",
                "-an",
                tmp,
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"[overlay] ffmpeg re-encode failed for {path}: {result.stderr[-500:]}", flush=True)
            if os.path.exists(tmp):
                os.remove(tmp)
            return
        os.replace(tmp, path)
        print(f"[overlay] re-encoded to H.264 baseline: {os.path.basename(path)}", flush=True)
    except FileNotFoundError:
        print("[overlay] ffmpeg not installed — videos may not play in all browsers", flush=True)
    except Exception as e:
        print(f"[overlay] re-encode error: {e}", flush=True)
        if os.path.exists(tmp):
            os.remove(tmp)


def extract_key_frame(video_path: str, output_path: str, frame_pct: float = 0.35) -> str:
    """
    Extract a single representative frame (at frame_pct of clip) with skeleton drawn.
    Saves as JPEG. Returns output_path.
    """
    cap = cv2.VideoCapture(video_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    target = int(total * frame_pct)
    cap.set(cv2.CAP_PROP_POS_FRAMES, target)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        return ""

    with _make_image_detector() as detector:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = detector.detect(mp_img)
        if result.pose_landmarks:
            _draw_skeleton(frame, result.pose_landmarks[0], (80, 200, 0))

    cv2.imwrite(output_path, frame)
    return output_path
