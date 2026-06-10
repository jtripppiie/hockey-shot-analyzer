"""
pose.py — MediaPipe Tasks pose detection on a video file.
Returns per-frame landmark data as a list of dicts.
"""

import os
import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision

# Path to the downloaded .task model (sits next to this file)
MODEL_PATH = os.path.join(os.path.dirname(__file__), "pose_landmarker.task")

# Landmark indices we care about (MediaPipe 33-point body model)
LANDMARKS = {
    "nose":             0,
    "left_shoulder":   11, "right_shoulder":  12,
    "left_elbow":      13, "right_elbow":     14,
    "left_wrist":      15, "right_wrist":     16,
    "left_hip":        23, "right_hip":       24,
    "left_knee":       25, "right_knee":      26,
    "left_ankle":      27, "right_ankle":     28,
}

# MediaPipe pose connections (pairs of landmark indices to draw lines between)
POSE_CONNECTIONS = [
    (11,12),(11,13),(13,15),(12,14),(14,16),  # arms
    (11,23),(12,24),(23,24),                   # torso
    (23,25),(25,27),(24,26),(26,28),           # legs
    (0,11),(0,12),                             # head
]


def _make_detector():
    base_opts = mp_python.BaseOptions(model_asset_path=MODEL_PATH)
    opts = mp_vision.PoseLandmarkerOptions(
        base_options=base_opts,
        running_mode=mp_vision.RunningMode.VIDEO,
        num_poses=1,
        # Slightly stricter than defaults: we'd rather drop a frame than have
        # the analysis silently use bad landmarks. The metrics layer handles
        # missing frames cleanly via the confidence gate.
        min_pose_detection_confidence=0.6,
        min_pose_presence_confidence=0.6,
        min_tracking_confidence=0.6,
    )
    return mp_vision.PoseLandmarker.create_from_options(opts)


def extract_frames(video_path: str):
    """Yield (frame_index, frame_bgr) from a video file."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")
    idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        yield idx, frame
        idx += 1
    cap.release()


def get_video_meta(video_path: str) -> dict:
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    return {"fps": fps, "total_frames": total, "width": w, "height": h}


# Pixel scene-cut pre-check tuning. A "cut" is a frame whose grayscale
# difference from the previous frame is both wildly prominent relative to the
# clip's own motion (>= PRECHECK_MAD_K median-absolute-deviations above the
# median diff) AND large in absolute terms (PRECHECK_ABS_FLOOR), so a static
# clip's pixel noise can't manufacture phantom cuts. Calibrated on real
# footage: continuous clips peak at ~12 MAD, a spliced montage spikes to ~68
# MAD at each splice. This is an independent corroborating signal to the
# pose-based body-teleport detector in metrics.py — it still flags cuts even
# when pose tracking drops out at the splice. WARN-only; never a hard reject.
PRECHECK_MAD_K = 14.0
PRECHECK_ABS_FLOOR = 0.04


def scene_cut_precheck(video_path: str, downscale: int = 64) -> dict:
    """
    Cheap pixel-level scene-cut detector (no pose). Decodes the clip at a small
    grayscale resolution and looks for abrupt frame-to-frame jumps that betray a
    hard cut between spliced scenes.

    Returns {"pixel_cuts": int, "peak_prominence": float} — peak_prominence is
    the largest single-frame jump expressed in MADs above the median (0.0 when
    the clip is too short to judge).
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return {"pixel_cuts": 0, "peak_prominence": 0.0}
    prev = None
    diffs = []
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        g = cv2.cvtColor(cv2.resize(frame, (downscale, downscale)),
                         cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
        if prev is not None:
            diffs.append(float(np.mean(np.abs(g - prev))))
        prev = g
    cap.release()

    if len(diffs) < 8:
        return {"pixel_cuts": 0, "peak_prominence": 0.0}

    arr = np.asarray(diffs)
    med = float(np.median(arr))
    mad = float(np.median(np.abs(arr - med))) or 1e-6
    is_cut = (arr > med + PRECHECK_MAD_K * mad) & (arr > PRECHECK_ABS_FLOOR)
    peak_prom = (float(arr.max()) - med) / mad
    return {"pixel_cuts": int(is_cut.sum()), "peak_prominence": round(peak_prom, 1)}


def run_pose_detection(video_path: str, sample_every: int = 1,
                       smooth_alpha: float = 0.5) -> list[dict]:
    """
    Run MediaPipe Tasks PoseLandmarker on every Nth frame.

    sample_every=1 processes every frame (best accuracy, ~30fps clip ≈ 1s of
    compute per second of video). Use 2 or 3 only if clips are long.

    smooth_alpha is the EMA weight for the *new* sample (0..1). 1.0 disables
    smoothing; 0.5 is a mild filter that knocks out per-frame jitter without
    softening fast motion much. Set to ~0.3 for very jittery clips.
    Smoothing is applied per-landmark on x,y,z (not visibility).

    Returns list of {frame, landmarks: {name: {x,y,z,v}}} (one entry per
    processed frame; landmarks=None when no pose was found that frame).
    """
    meta = get_video_meta(video_path)
    fps = meta["fps"] or 30.0
    results = []
    prev_lm: dict | None = None  # for EMA smoothing

    with _make_detector() as detector:
        for idx, frame_bgr in extract_frames(video_path):
            if idx % sample_every != 0:
                continue
            rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            timestamp_ms = int(idx * 1000 / fps)
            detection = detector.detect_for_video(mp_img, timestamp_ms)

            frame_data = {"frame": idx, "landmarks": None}
            if detection.pose_landmarks:
                lm = detection.pose_landmarks[0]
                # MediaPipe also returns metric, root-centered world landmarks
                # (origin = hip midpoint, units = meters). Joint angles
                # computed from these are far less sensitive to camera yaw /
                # tilt than the image-space x,y projection — a true joint
                # angle is the same regardless of where the camera sits.
                wlm = (detection.pose_world_landmarks[0]
                       if detection.pose_world_landmarks else None)
                cur = {}
                for name, i in LANDMARKS.items():
                    entry = {
                        "x": lm[i].x,
                        "y": lm[i].y,
                        "z": lm[i].z,
                        "v": lm[i].visibility if hasattr(lm[i], "visibility") else 1.0,
                    }
                    if wlm is not None:
                        entry["wx"] = wlm[i].x
                        entry["wy"] = wlm[i].y
                        entry["wz"] = wlm[i].z
                    cur[name] = entry
                # EMA smoothing — only when both prev and current have the same
                # landmark visible. Big visibility drops indicate occlusion, so
                # we re-initialise the filter instead of blending in stale data.
                if prev_lm is not None and 0.0 < smooth_alpha < 1.0:
                    for name, p in cur.items():
                        q = prev_lm.get(name)
                        if not q: continue
                        if p["v"] < 0.3 or q["v"] < 0.3: continue
                        p["x"] = smooth_alpha * p["x"] + (1 - smooth_alpha) * q["x"]
                        p["y"] = smooth_alpha * p["y"] + (1 - smooth_alpha) * q["y"]
                        p["z"] = smooth_alpha * p["z"] + (1 - smooth_alpha) * q["z"]
                        if "wx" in p and "wx" in q:
                            p["wx"] = smooth_alpha * p["wx"] + (1 - smooth_alpha) * q["wx"]
                            p["wy"] = smooth_alpha * p["wy"] + (1 - smooth_alpha) * q["wy"]
                            p["wz"] = smooth_alpha * p["wz"] + (1 - smooth_alpha) * q["wz"]
                prev_lm = cur
                frame_data["landmarks"] = cur
            else:
                # Don't smooth across detection gaps
                prev_lm = None

            results.append(frame_data)
    return results


def angle_3pts(a: dict, b: dict, c: dict) -> float:
    """
    Return the angle (degrees) at vertex b formed by vectors b→a and b→c.
    Accepts landmark dicts with x, y keys.
    """
    va = np.array([a["x"] - b["x"], a["y"] - b["y"]])
    vc = np.array([c["x"] - b["x"], c["y"] - b["y"]])
    cos_angle = np.dot(va, vc) / (np.linalg.norm(va) * np.linalg.norm(vc) + 1e-8)
    return float(np.degrees(np.arccos(np.clip(cos_angle, -1.0, 1.0))))


def angle_3pts_3d(a: dict, b: dict, c: dict) -> float:
    """Joint angle (degrees) at vertex b computed from MediaPipe **world**
    landmarks (wx, wy, wz in meters, hip-centered).

    Use this for any joint-angle metric (knee bend, elbow extension,
    shoulder/hip/knee body line, shoulder-line vs hip-line rotation, etc.).
    Joint angles are intrinsic to the body and are invariant to camera yaw
    and tilt — so reading them from world landmarks instead of image-space
    x,y removes most perspective error.

    Falls back to the 2D `angle_3pts` (image x,y) when world coords are
    missing on any of the three landmarks, so legacy callers keep working.
    """
    if not all("wx" in p for p in (a, b, c)):
        return angle_3pts(a, b, c)
    va = np.array([a["wx"] - b["wx"], a["wy"] - b["wy"], a["wz"] - b["wz"]])
    vc = np.array([c["wx"] - b["wx"], c["wy"] - b["wy"], c["wz"] - b["wz"]])
    denom = np.linalg.norm(va) * np.linalg.norm(vc)
    if denom < 1e-8:
        return angle_3pts(a, b, c)
    cos_angle = float(np.dot(va, vc) / denom)
    return float(np.degrees(np.arccos(np.clip(cos_angle, -1.0, 1.0))))
