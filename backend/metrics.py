"""
metrics.py — Compute shot metrics from per-frame pose data.

Design goals (rewrite vs v1):
  • No fake numbers. If a metric can't be measured reliably (camera angle wrong,
    landmarks occluded), score is None and the UI shows "couldn't measure".
  • Real biomechanics. Hip & shoulder rotation are measured in 3D angular
    rotation (degrees), not 2D pixel drift. Release timing is in milliseconds,
    independent of clip fps.
  • Handedness auto-detected from wrist motion. Every per-side metric uses the
    dominant side, so a left-handed shooter isn't penalized.
  • Shot phases (load → release → follow-through) are detected from the data
    itself (knee-bend minimum + wrist peak speed), not assumed by clip position.
  • Tighter scoring so a perfect score actually means something. A casual
    standing posture no longer scores 84/100 on knee bend.
"""

from __future__ import annotations

import math
import numpy as np
from pose import angle_3pts, angle_3pts_3d


# ── Visibility / quality thresholds ──────────────────────────────────────────
# A landmark is "visible" if MediaPipe's visibility score is >= this.
VIS_THRESH = 0.5

# A metric is "reliable" only if at least this fraction of the frames it needs
# had all required landmarks visible. Below this we return score=None and a
# reason string instead of a guess.
MIN_VISIBLE_FRACTION = 0.6


# ── Scoring helper ───────────────────────────────────────────────────────────
def _score_band(val: float, ideal_lo: float, ideal_hi: float,
                hard_lo: float, hard_hi: float) -> int:
    """
    Smooth piecewise scoring with a flat plateau inside [ideal_lo, ideal_hi]
    and linear falloff to 0 at hard_lo / hard_hi.

    This replaces the old logic that gave very high scores far outside the
    optimal window (e.g. a standing-straight knee scored 84).
    """
    if val is None or math.isnan(val):
        return 0
    if ideal_lo <= val <= ideal_hi:
        return 100
    if val < ideal_lo:
        if val <= hard_lo:
            return 0
        return int(round(100 * (val - hard_lo) / (ideal_lo - hard_lo)))
    # val > ideal_hi
    if val >= hard_hi:
        return 0
    return int(round(100 * (hard_hi - val) / (hard_hi - ideal_hi)))


def _score_lower_better(val: float, ideal_max: float, hard_max: float) -> int:
    """For metrics where lower=better (head jitter). 0..ideal_max → 100, hard_max → 0."""
    if val is None or math.isnan(val):
        return 0
    if val <= ideal_max:
        return 100
    if val >= hard_max:
        return 0
    return int(round(100 * (hard_max - val) / (hard_max - ideal_max)))


def _grade(score: int | None) -> str:
    if score is None:    return "unmeasured"
    if score >= 85:      return "great"
    if score >= 70:      return "good"
    if score >= 50:      return "ok"
    return "needs work"


# ── Geometry helpers ─────────────────────────────────────────────────────────
def _pt3(lm: dict, key: str) -> np.ndarray | None:
    """Return [x,y,z] for a landmark if visible enough, else None."""
    p = lm.get(key)
    if not p or p.get("v", 0) < VIS_THRESH:
        return None
    return np.array([p["x"], p["y"], p.get("z", 0.0)])


def _pt3w(lm: dict, key: str) -> np.ndarray | None:
    """Return MediaPipe **world** coords [wx, wy, wz] in meters (hip-centred)
    for a landmark if visible enough and world coords are present, else None.

    Use for any direction / rotation computation that should be camera-pose
    invariant (joint rotations around the body's own axes)."""
    p = lm.get(key)
    if not p or p.get("v", 0) < VIS_THRESH or "wx" not in p:
        return None
    return np.array([p["wx"], p["wy"], p["wz"]])


def _angle_between(v1: np.ndarray, v2: np.ndarray) -> float:
    n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
    if n1 < 1e-8 or n2 < 1e-8:
        return float("nan")
    cos = float(np.dot(v1, v2) / (n1 * n2))
    return math.degrees(math.acos(max(-1.0, min(1.0, cos))))


# ── Handedness & phase detection ─────────────────────────────────────────────
def _detect_dominant_hand(frames: list[dict]) -> str | None:
    """
    The hand that moves further during the clip is the shooting (bottom) hand.
    Returns 'left' / 'right' / None.
    """
    spans = {}
    for side in ("left", "right"):
        ys, xs = [], []
        for f in frames:
            lm = f["landmarks"]
            if not lm: continue
            w = lm.get(f"{side}_wrist")
            if not w or w.get("v", 0) < VIS_THRESH: continue
            xs.append(w["x"]); ys.append(w["y"])
        if len(xs) < 5:
            spans[side] = 0.0
            continue
        spans[side] = float(np.ptp(xs) + np.ptp(ys))
    if not spans or max(spans.values()) < 0.05:
        return None
    return max(spans, key=spans.get)


def _detect_camera_view(frames: list[dict]) -> dict:
    """
    Decide if the camera is side / front / back / angled.

    Method: at frames where both shoulders are visible, compute the ratio
    |shoulder_dx_2d| / shoulder_3d_distance. Side view → small ratio
    (shoulders foreshorten to a line); front/back view → ratio near 1.
    Also use the sign of the cross product of the shoulder line and torso
    vector to distinguish facing-left vs facing-right side views.
    """
    ratios = []
    facings = []  # +1 facing left (in image), -1 facing right
    for f in frames:
        lm = f["landmarks"]; 
        if not lm: continue
        ls, rs = _pt3(lm, "left_shoulder"), _pt3(lm, "right_shoulder")
        lh, rh = _pt3(lm, "left_hip"), _pt3(lm, "right_hip")
        if ls is None or rs is None: continue
        dx = abs(ls[0] - rs[0])
        d3 = float(np.linalg.norm(ls - rs))
        if d3 < 1e-4: continue
        ratios.append(dx / d3)
        if lh is not None and rh is not None:
            # Z is depth — front shoulder has smaller z. In a side view, one
            # shoulder is clearly in front of the other.
            facings.append(1 if ls[2] > rs[2] else -1)

    if not ratios:
        return {"view": "unknown", "confidence": 0.0, "side_view_quality": 0.0}

    avg_ratio = float(np.mean(ratios))
    if avg_ratio < 0.45:
        view = "side"
        side_quality = 1.0 - avg_ratio / 0.45  # 0..1
    elif avg_ratio < 0.7:
        view = "angled"
        side_quality = 0.4
    else:
        view = "front_or_back"
        side_quality = 0.0

    return {
        "view": view,
        "confidence": round(min(1.0, len(ratios) / 10.0), 2),
        "side_view_quality": round(side_quality, 2),
        "avg_shoulder_ratio": round(avg_ratio, 3),
    }


def _detect_phases(frames: list[dict], dom: str | None, fps: float) -> dict:
    """
    Detect load, release, and follow-through frames using actual signals.
      - release: frame with peak dominant-wrist speed (most reliable signal).
      - load:    frame with minimum knee angle BEFORE release (the wind-up).
                 If no knee data exists before release, falls back to the
                 frame ~0.3s before release.
      - follow:  ~150ms after release.
    Constraining load < release < follow prevents the analyser from picking
    a deep knee bend during the follow-through stride as the "load" phase.
    """
    if dom is None:
        return {"load": None, "release": None, "follow": None}

    knee_angles = []  # (frame_idx, angle)
    wrist_xy = []     # (frame_idx, x, y)
    for f in frames:
        lm = f["landmarks"]
        if not lm: continue
        hip = _pt3(lm, f"{dom}_hip"); knee = _pt3(lm, f"{dom}_knee"); ankle = _pt3(lm, f"{dom}_ankle")
        if hip is not None and knee is not None and ankle is not None:
            knee_angles.append((f["frame"], angle_3pts(
                {"x":hip[0],"y":hip[1]}, {"x":knee[0],"y":knee[1]},
                {"x":ankle[0],"y":ankle[1]})))
        w = _pt3(lm, f"{dom}_wrist")
        if w is not None:
            wrist_xy.append((f["frame"], w[0], w[1]))

    # ── 1. Release = peak wrist speed (central difference) ─────────────
    # First drop single-frame landmark teleports: a wrist point that sits far
    # off the straight line between its neighbours is tracking noise, not real
    # motion, and would otherwise spike the speed and steal the release. Then
    # the release is the peak of a short moving average of wrist speed, so the
    # sustained true release wins over any residual jitter.
    release_idx = None
    ABS_TELEPORT = 0.12  # normalized: >12% of frame off the neighbour midline = noise
    if len(wrist_xy) >= 3:
        resid = []
        for k in range(1, len(wrist_xy) - 1):
            _, xp, yp = wrist_xy[k-1]
            _, xn, yn = wrist_xy[k+1]
            _, xk, yk = wrist_xy[k]
            mx, my = (xp + xn) / 2, (yp + yn) / 2
            resid.append(math.hypot(xk - mx, yk - my))
        srt = sorted(resid)
        med_r = srt[len(srt) // 2]
        mad_r = sorted(abs(r - med_r) for r in resid)[len(resid) // 2]
        thr_stat = med_r + 6.0 * mad_r if mad_r > 0 else float("inf")
        clean = [wrist_xy[0]]
        for k in range(1, len(wrist_xy) - 1):
            r = resid[k-1]
            if r > ABS_TELEPORT or r > thr_stat:
                continue  # teleport — skip this point
            clean.append(wrist_xy[k])
        clean.append(wrist_xy[-1])
        wrist_xy = clean

    if len(wrist_xy) >= 3:
        speeds = []
        for k in range(1, len(wrist_xy) - 1):
            i_prev, xp, yp = wrist_xy[k-1]
            i_next, xn, yn = wrist_xy[k+1]
            dt = max(1, i_next - i_prev) / fps
            speed = math.hypot(xn - xp, yn - yp) / dt
            speeds.append((wrist_xy[k][0], speed))
        if speeds:
            vals = [s for _, s in speeds]
            smoothed = []
            for k in range(len(vals)):
                lo = max(0, k - 1); hi = min(len(vals), k + 2)
                smoothed.append(sum(vals[lo:hi]) / (hi - lo))
            best_k = max(range(len(smoothed)), key=lambda k: smoothed[k])
            release_idx = speeds[best_k][0]

    # ── 2. Load = deepest knee bend BEFORE release ─────────────────────
    load_idx = None
    if knee_angles and release_idx is not None:
        pre = [t for t in knee_angles if t[0] < release_idx]
        if pre:
            load_idx = min(pre, key=lambda t: t[1])[0]
        else:
            # No knee data before release — fall back to ~0.3s pre-release
            load_idx = max(0, release_idx - int(round(0.3 * fps)))
    elif knee_angles:
        load_idx = min(knee_angles, key=lambda t: t[1])[0]

    follow_idx = None
    if release_idx is not None:
        follow_idx = release_idx + int(round(0.15 * fps))

    return {"load": load_idx, "release": release_idx, "follow": follow_idx}


# ── Individual metric functions ──────────────────────────────────────────────
# Each returns (value_or_None, score_or_None, reason_if_unmeasured)

def _measure_knee_bend(frames, dom, phases):
    """Deepest knee bend (degrees) during the load→release window. Smaller =
    deeper bend. Ideal 80–105°.

    Restricting to the load→release window keeps a deep crouch during the
    follow-through stride (or a post-shot squat) from being scored as the
    load. Computed from MediaPipe **world** landmarks (hip-centred meters) so
    the angle is the true joint angle rather than its projection in the image
    plane — robust to camera yaw / tilt."""
    if dom is None or phases["load"] is None:
        return None, None, "Couldn't find the load phase"
    load_i = phases["load"]
    rel_i = phases["release"]

    def _in_window(i):
        return i >= load_i and (rel_i is None or i <= rel_i)

    angles = []
    window_frames = 0
    for f in frames:
        if not _in_window(f["frame"]): continue
        window_frames += 1
        lm = f["landmarks"]
        if not lm: continue
        hip = lm.get(f"{dom}_hip"); knee = lm.get(f"{dom}_knee"); ankle = lm.get(f"{dom}_ankle")
        if not (hip and knee and ankle): continue
        angles.append(angle_3pts_3d(hip, knee, ankle))
    coverage = len(angles) / max(1, window_frames)
    if not angles or coverage < MIN_VISIBLE_FRACTION:
        return None, None, f"Knees only visible in {int(coverage*100)}% of the shot window"
    val = float(min(angles))
    # Ideal 80-105°, hard 50° and 160°
    score = _score_band(val, 80, 105, 50, 160)
    return val, score, None


def _measure_rotation_angle(frames, side_a: str, side_b: str, label: str,
                            phases: dict | None = None):
    """
    Generic 3D rotation: angle (degrees) swept by the vector from joint A to
    joint B between the load frame and the release frame. Used for hips and
    shoulders.

    Restricting to load\u2192release rather than the whole clip prevents the
    analyser from inflating the value with pre-stance jitter or follow-through
    over-rotation \u2014 we measure the rotation that actually powered the shot.

    Uses MediaPipe **world** landmarks (hip-centred meters) when available so
    the swept angle is the true 3D rotation around the body's vertical axis
    rather than the projection onto the camera plane. Falls back to image+z
    coords for legacy data.
    """
    # Pick the measurement window
    start_i = (phases or {}).get("load")
    end_i = (phases or {}).get("release")
    if start_i is not None and end_i is not None and end_i > start_i:
        window = [f for f in frames if start_i <= f["frame"] <= end_i]
    else:
        window = frames  # fallback: full clip

    vecs = []
    for f in window:
        lm = f["landmarks"]
        if not lm: continue
        a = _pt3w(lm, side_a) if _pt3w(lm, side_a) is not None else _pt3(lm, side_a)
        b = _pt3w(lm, side_b) if _pt3w(lm, side_b) is not None else _pt3(lm, side_b)
        if a is None or b is None: continue
        v = b - a
        if np.linalg.norm(v) < 1e-4: continue
        vecs.append(v)

    coverage = len(vecs) / max(1, len(window))
    if coverage < MIN_VISIBLE_FRACTION or len(vecs) < 3:
        return None, None, f"{label} only visible in {int(coverage*100)}% of the shot window"

    # Reference = first vector in window (load frame). Max sweep from there.
    ref = vecs[0]
    max_sweep = 0.0
    for v in vecs[1:]:
        a = _angle_between(ref, v)
        if not math.isnan(a) and a > max_sweep:
            max_sweep = a
    val = float(max_sweep)
    # Wrist shot ~40-70°, snap ~60-100°, slap ~90-140°. Reward anything in
    # that whole spectrum; only penalise basically-no-rotation or full reversal.
    score = _score_band(val, 40, 130, 8, 170)
    return val, score, None


def _measure_follow_through(frames, dom, phases):
    """
    How high above shoulder the wrist finishes, in body-height-normalized units.
    Measured at follow-through frame; falls back to peak after release.
    """
    if dom is None or phases["release"] is None:
        return None, None, "Couldn't find the release"
    release_i = phases["release"]
    follow_i = phases["follow"] or release_i + 1

    # Use peak wrist-above-shoulder height in the window [release, end]
    best = None
    used = 0; needed = 0
    for f in frames:
        i = f["frame"]
        if i < release_i: continue
        needed += 1
        lm = f["landmarks"]
        if not lm: continue
        w = _pt3(lm, f"{dom}_wrist"); s = _pt3(lm, f"{dom}_shoulder")
        if w is None or s is None: continue
        used += 1
        # Image coords: smaller y = higher
        rise = s[1] - w[1]
        if best is None or rise > best:
            best = rise

    if best is None or used < 2:
        return None, None, "Couldn't see the follow-through clearly"
    val = float(best)
    # Ideal 0.15–0.40 normalized units, hard 0 (no rise) and 0.7 (off-camera)
    score = _score_band(val, 0.15, 0.40, 0.0, 0.7)
    return val, score, None


def _measure_head_stability(frames, phases):
    """
    Std-dev of nose position during the load → follow window, scaled by
    detected body height (shoulder→hip) so it's resolution-independent.
    """
    if phases["load"] is None or phases["release"] is None:
        return None, None, "Couldn't find load/release"
    start = phases["load"]; end = (phases["follow"] or phases["release"] + 5)
    xs, ys, body_heights = [], [], []
    seen = 0; needed = 0
    for f in frames:
        i = f["frame"]
        if i < start or i > end: continue
        needed += 1
        lm = f["landmarks"]
        if not lm: continue
        nose = _pt3(lm, "nose")
        ls = _pt3(lm, "left_shoulder")
        if ls is None: ls = _pt3(lm, "right_shoulder")
        lh = _pt3(lm, "left_hip")
        if lh is None: lh = _pt3(lm, "right_hip")
        if nose is None or ls is None or lh is None: continue
        seen += 1
        xs.append(nose[0]); ys.append(nose[1])
        body_heights.append(abs(ls[1] - lh[1]))

    if seen < 4:
        return None, None, "Head not visible enough during the shot"
    body = float(np.median(body_heights)) or 0.1
    jitter = float((np.std(xs) + np.std(ys)) / 2 / body)  # fraction of body height
    # Ideal < 0.04 body-heights of jitter (very still). Hard cutoff 0.20.
    score = _score_lower_better(jitter, 0.04, 0.20)
    return jitter, score, None


def _measure_release_timing(frames, dom, phases, fps):
    """Time (ms) from load (min knee) to release (peak wrist speed)."""
    if dom is None or phases["load"] is None or phases["release"] is None:
        return None, None, "Couldn't detect load → release sequence"
    dframes = phases["release"] - phases["load"]
    if dframes <= 0:
        return None, None, "Release appears to happen before load — try a clip showing the full motion"
    val_ms = float(dframes * 1000.0 / fps)
    # Elite quick release ~150-350ms. Slow telegraph >800ms.
    score = _score_band(val_ms, 150, 350, 50, 1200)
    return val_ms, score, None


def _measure_weight_transfer(frames, dom, phases):
    """
    Hip-midpoint horizontal displacement from load to release frame, normalized
    by stance width (ankle-to-ankle distance). Real weight transfer = hips
    moving toward the target. <0.2 = pushing with arms only; >0.6 = strong drive.
    """
    if phases["load"] is None or phases["release"] is None:
        return None, None, "Need load + release to measure weight transfer"

    def hip_x(i):
        if i is None or i >= len(frames): return None
        lm = frames[i]["landmarks"]
        if not lm: return None
        lh = _pt3(lm, "left_hip"); rh = _pt3(lm, "right_hip")
        if lh is None or rh is None: return None
        return float((lh[0] + rh[0]) / 2)

    def stance(i):
        if i is None or i >= len(frames): return None
        lm = frames[i]["landmarks"]
        if not lm: return None
        la = _pt3(lm, "left_ankle"); ra = _pt3(lm, "right_ankle")
        if la is None or ra is None: return None
        d = float(abs(la[0] - ra[0]))
        return d if d > 0.02 else None

    # Map phase index to frame array index
    def by_frame(target):
        for idx, f in enumerate(frames):
            if f["frame"] == target: return idx
        return None

    li = by_frame(phases["load"]); ri = by_frame(phases["release"])
    x_load = hip_x(li); x_rel = hip_x(ri)
    width = stance(li) or stance(ri)
    if x_load is None or x_rel is None or width is None:
        return None, None, "Couldn't see hips + ankles clearly at load/release"
    val = abs(x_rel - x_load) / width
    score = _score_band(val, 0.35, 0.9, 0.0, 1.6)
    return float(val), score, None


# ── Main entry ───────────────────────────────────────────────────────────────
def compute_metrics(frames: list[dict], fps: float = 60.0,
                    hand_override: str | None = None) -> dict:
    """
    Returns dict with:
      metrics:        {key: {value, score|None, grade, status, reason?, tip,
                             coaching, confidence}}
      summary:        {overall, power, technique, timing}  (scores are over the
                       reliable metrics only)
      quality_report: {camera_view, dominant_hand, phases, warnings: [...]}

    `hand_override` ("left"|"right") forces the shooting hand instead of
    auto-detecting it from wrist motion; anything else falls back to auto.
    """
    valid = [f for f in frames if f.get("landmarks")]
    if len(valid) < 5:
        return {}

    override = hand_override if hand_override in ("left", "right") else None
    detected_dom = _detect_dominant_hand(valid)
    dom = override or detected_dom
    hand_source = "override" if override else "auto"
    cam = _detect_camera_view(valid)
    phases = _detect_phases(valid, dom, fps)

    warnings = []
    if dom is None:
        warnings.append("Couldn't tell which is the shooting hand — wrist motion is unclear.")
    if cam["view"] == "front_or_back":
        warnings.append("Camera appears front- or back-on. For best results, film from the side (15–45° angle).")
    elif cam["view"] == "angled":
        warnings.append("Camera is at a steep angle. A side view (player perpendicular to camera) gives much better results.")
    elif cam["view"] == "unknown":
        warnings.append("Couldn't determine camera angle.")
    if phases["release"] is None:
        warnings.append("Couldn't find the moment of release. Try a clip that shows the full shot motion.")

    # ── Measure each metric ──
    raw_results = {
        "knee_bend":         _measure_knee_bend(valid, dom, phases),
        "hip_rotation":      _measure_rotation_angle(valid, f"{dom}_hip", f"{'left' if dom == 'right' else 'right'}_hip", "Hips", phases) if dom else (None, None, "No dominant hand detected"),
        "shoulder_rotation": _measure_rotation_angle(valid, "left_shoulder", "right_shoulder", "Shoulders", phases),
        "follow_through":    _measure_follow_through(valid, dom, phases),
        "head_stability":    _measure_head_stability(valid, phases),
        "release_timing":    _measure_release_timing(valid, dom, phases, fps),
        "weight_transfer":   _measure_weight_transfer(valid, dom, phases),
    }

    # Camera-angle penalty: if not a side view, derate the metrics that need
    # depth information. Better to mark them unmeasured than to lie.
    needs_side_view = {"hip_rotation", "shoulder_rotation", "weight_transfer"}
    if cam["view"] in ("front_or_back", "unknown"):
        for k in needs_side_view:
            v, _, _ = raw_results[k]
            raw_results[k] = (v, None, "Needs a side-view clip to measure accurately")

    scored = {}
    for key, (val, score, reason) in raw_results.items():
        if score is None:
            scored[key] = {
                "value":      None if val is None else round(val, 3),
                "score":      None,
                "grade":      "unmeasured",
                "status":     "unmeasured",
                "reason":     reason or "Not enough data to score this reliably.",
                "tip":        None,
                "coaching":   _coaching_unmeasured(key, reason),
                "confidence": 0.0,
            }
        else:
            scored[key] = {
                "value":      round(val, 3),
                "score":      score,
                "grade":      _grade(score),
                "status":     "ok",
                "tip":        _tip(key, score),
                "coaching":   _coaching_detail(key, score),
                "confidence": 1.0,
            }

    # ── Composite scores: only count reliable metrics ──
    def weighted(parts):
        total_w = 0.0; total = 0.0
        for key, w in parts:
            s = scored.get(key, {}).get("score")
            if s is None: continue
            total += w * s; total_w += w
        return int(round(total / total_w)) if total_w > 0 else None

    power     = weighted([("hip_rotation", 0.35), ("shoulder_rotation", 0.25),
                          ("weight_transfer", 0.25), ("knee_bend", 0.15)])
    technique = weighted([("knee_bend", 0.30), ("follow_through", 0.35),
                          ("head_stability", 0.35)])
    timing    = weighted([("release_timing", 0.65), ("follow_through", 0.35)])

    # Overall = weighted avg of the three composites that exist
    sub_parts = [("power", power, 0.40), ("technique", technique, 0.35), ("timing", timing, 0.25)]
    nonnull = [(v, w) for _, v, w in sub_parts if v is not None]
    overall = int(round(sum(v*w for v, w in nonnull) / sum(w for _, w in nonnull))) if nonnull else None

    measured_count = sum(1 for m in scored.values() if m["score"] is not None)

    return {
        "metrics": scored,
        "summary": {
            "overall":   overall,
            "power":     power,
            "technique": technique,
            "timing":    timing,
        },
        "quality_report": {
            "camera_view":     cam["view"],
            "side_view_quality": cam.get("side_view_quality", 0.0),
            "dominant_hand":   dom,
            "dominant_hand_source": hand_source,
            "phases":          phases,
            "measured_metrics": measured_count,
            "total_metrics":   len(scored),
            "warnings":        warnings,
        },
    }


# ─── Coaching text (kept similar to v1, plus weight_transfer) ────────────────
COACHING = {
    "knee_bend": {
        "label": "Knee Bend",
        "why":  "Your knees are the springs of your shot. The deeper you load them, the more power you can pop up through your hips and into the puck.",
        "great":      {"tip": "Excellent knee bend — really loading those springs.",
                       "drill": "Keep it up! 30-sec wall sits before practice will keep your legs primed for deep bends."},
        "good":       {"tip": "Good bend. Try dropping another inch for an even stronger load.",
                       "drill": "'Load and hold': get into shot stance, drop knees an extra inch, hold 2 sec, then explode. 10 reps dry."},
        "ok":         {"tip": "Bend your knees deeper during the load phase to build more power.",
                       "drill": "Place a puck on the ice in front of your skates. Get your hips low enough that you could touch it without bending at the waist. Knees out, weight on the balls of your feet."},
        "needs work": {"tip": "Almost standing straight up — focus on a deep knee bend before you release.",
                       "drill": "Off-ice in front of a mirror: lower until your thighs are nearly parallel to the floor. 3 sets of 10 slow squats to build the habit."},
    },
    "hip_rotation": {
        "label": "Hip Rotation",
        "why":  "Hips are the engine. They rotate first; the upper body follows. Pro shooters get most of their velocity from this chain, not from arm strength.",
        "great":      {"tip": "Great hip rotation — you're using your full body.",
                       "drill": "Try 'lead with the hip' — feel your front hip pointing at the net BEFORE your stick touches the puck."},
        "good":       {"tip": "Good hip drive. Try initiating the rotation a touch earlier.",
                       "drill": "Without a stick: load hips back, then snap them forward fast. Feel the pull in your core. Now add the stick and match that hip speed."},
        "ok":         {"tip": "Rotate your hips more toward the target — that's where extra power lives.",
                       "drill": "'Hip snap' drill: stick behind your back across your hips. Load sideways, snap to face the target as fast as you can. 20 reps."},
        "needs work": {"tip": "You're shooting mostly with your arms. Drive the hips through.",
                       "drill": "Hold puck position with stick, freeze your arms, ONLY rotate your hips. Feel how much power that alone makes. Then combine. Biggest power change you can make."},
    },
    "shoulder_rotation": {
        "label": "Shoulder Rotation",
        "why":  "Shoulders follow hips in the power chain. A full shoulder turn adds arc to your swing — more acceleration on the puck and a more deceptive release.",
        "great":      {"tip": "Excellent shoulder turn — smooth upper-body chain.",
                       "drill": "Try 'late shoulder' — delay your shoulder turn slightly so it fires after the hips. Makes the shot look like a pass until the last instant."},
        "good":       {"tip": "Good rotation. Make sure it follows your hip turn, not leads it.",
                       "drill": "Film from above if you can. Your back shoulder should fully open toward the target at follow-through."},
        "ok":         {"tip": "Let your shoulders rotate more freely through the shot.",
                       "drill": "'Towel drill': hold a towel behind your back at shoulder height. On your shot it should whip around in front. If it stays behind, your shoulders aren't turning."},
        "needs work": {"tip": "Your shoulders are barely turning — likely a rigid top hand.",
                       "drill": "Loosen your top-hand grip slightly and let your arm pull through naturally. Slow-motion shots focusing ONLY on the shoulder completing its turn."},
    },
    "follow_through": {
        "label": "Follow-Through",
        "why":  "Follow-through controls direction. Stopping your stick at contact is like stopping a golf swing halfway — you lose both power and accuracy.",
        "great":      {"tip": "Great follow-through — stick finishes pointed at the target.",
                       "drill": "Pick a specific spot on the net (top corner, five-hole) and consciously finish pointing exactly there. Sharpens placement."},
        "good":       {"tip": "Good extension. Try finishing even higher toward the target.",
                       "drill": "Tape a string across the top of the net opening. Your follow-through should bring your stick above that line."},
        "ok":         {"tip": "Let your arms fully extend after release for better accuracy.",
                       "drill": "'Long stick' drill: imagine your stick is 2 feet longer. Extend your arms to reach that imaginary endpoint."},
        "needs work": {"tip": "You're decelerating at contact — very common, very fixable.",
                       "drill": "Shoot at an empty net while saying 'through the net' out loud as you fire. The cue tells your brain to accelerate PAST the puck. 20 shots."},
    },
    "head_stability": {
        "label": "Head Stability",
        "why":  "Moving your head pulls your whole upper body off-axis. Eyes locked on contact = stable platform for everything else to rotate around.",
        "great":      {"tip": "Excellent head steadiness — great focus through the shot.",
                       "drill": "Advanced: 'eyes up early' — watch the puck contact, then shift eyes to target spot just before release."},
        "good":       {"tip": "Good head position. A little more stillness will sharpen accuracy.",
                       "drill": "Have a friend watch your head and call out 'move' if it shifts. Awareness is half the fix."},
        "ok":         {"tip": "Try to keep your head steady and eyes on the target.",
                       "drill": "'Still head' drill: balance a small sticker on top of your helmet. If it slides during the shot, head's moving too much."},
        "needs work": {"tip": "Head movement usually means rushing or peeking at the net too early.",
                       "drill": "Shoot at a blank wall with eyes glued to the puck contact point. Don't look at the wall at all. 30 shots."},
    },
    "release_timing": {
        "label": "Release Timing",
        "why":  "A quick release — load to fire — is what makes shots dangerous. A slow release lets goalies read and set. Elite is compact and snappy.",
        "great":      {"tip": "Very fast release — that's a goalie's nightmare.",
                       "drill": "Work on a 'moving release' — shoot off one stride without stopping to load. Keep that same timing in motion."},
        "good":       {"tip": "Good release speed. A sharper wrist snap at the end can shave more time.",
                       "drill": "Add a wrist snap at the very end. Compresses the final phase and makes the puck exit faster."},
        "ok":         {"tip": "Your release is slow enough that a goalie has time to react.",
                       "drill": "'1-fire' count drill: say '1' on load, 'fire' on release. Make the gap as short as possible. Target: under 300 ms."},
        "needs work": {"tip": "You're telegraphing the shot with a long load phase.",
                       "drill": "Partner passing drill: shoot within 1 second of receiving the puck. Trains your body to compress the load-to-fire sequence. Start slow, speed up."},
    },
    "weight_transfer": {
        "label": "Weight Transfer",
        "why":  "Real shot power doesn't come from your arms — it comes from your weight moving from your back foot to your front foot during the release. No weight shift = no leg drive = no real power.",
        "great":      {"tip": "Strong weight transfer — you're driving with your legs.",
                       "drill": "Now train it under pressure: shoot while a partner shoves you sideways. Maintain the weight shift even when off-balance."},
        "good":       {"tip": "Good drive. Try pushing even more onto your front foot at release.",
                       "drill": "'Stomp' drill: deliberately stomp your front foot at the moment of release. Exaggerates the weight transfer until it's natural."},
        "ok":         {"tip": "Weight transfer is small — you're shooting from a static base.",
                       "drill": "Set two cones a stride apart. Start over the back cone, finish over the front cone. The shot fires between them. 15 reps focusing only on the leg drive."},
        "needs work": {"tip": "Almost no weight transfer — you're shooting with arms only, losing most of your power.",
                       "drill": "Off-ice: stand sideways, shift 90% of weight to back foot (load), then explosively push to front foot. Do this 20 times WITHOUT a stick to feel the leg drive. Then add the stick."},
    },
}


def _tier(score: int) -> str:
    if score >= 85: return "great"
    if score >= 70: return "good"
    if score >= 50: return "ok"
    return "needs work"


def _tip(key: str, score: int) -> str:
    return COACHING[key][_tier(score)]["tip"]


def _coaching_detail(key: str, score: int) -> dict:
    tier = _tier(score)
    c = COACHING[key]
    return {
        "label": c["label"],
        "why":   c["why"],
        "tip":   c[tier]["tip"],
        "drill": c[tier]["drill"],
        "tier":  tier,
    }


def _coaching_unmeasured(key: str, reason: str | None) -> dict:
    c = COACHING.get(key, {})
    return {
        "label": c.get("label", key),
        "why":   c.get("why", ""),
        "tip":   reason or "Couldn't measure this reliably.",
        "drill": "Re-film from the side (player perpendicular to the camera), full body in frame, good lighting. Then this metric will score.",
        "tier":  "unmeasured",
    }
