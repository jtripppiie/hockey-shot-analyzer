"""Expert Feedback Mode — JSONL append-only log of human corrections.

Each call to `save_feedback` appends one line; the same job_id can have multiple
entries (e.g. coach + parent reviewing the same clip). Nothing is overwritten.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

APP_VERSION = "0.2.0-expert-feedback"

# Canonical checkbox set — keep in sync with the frontend form.
# Order is preserved in the log for stable analysis later.
CHECKBOX_KEYS = [
    "head_dropped",
    "good_head_position",
    "knee_drive_strong",
    "knee_drive_weak",
    "weight_transfer_good",
    "weight_transfer_weak",
    "follow_through_good",
    "follow_through_short",
    "blade_puck_contact_good",
    "balance_issue",
    "camera_angle_unreliable",
    "ai_score_too_high",
    "ai_score_too_low",
]

QUALITY_LABELS = {"poor", "needs_work", "decent", "good", "excellent"}


def _result_for(output_dir: Path, job_id: str) -> dict | None:
    p = output_dir / f"{job_id}_result.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def save_feedback(
    output_dir: Path,
    log_path: Path,
    *,
    job_id: str,
    corrected_score: int,
    quality_label: str,
    checkboxes: list[str],
    note: str,
    reviewer: str = "",
) -> dict[str, Any]:
    """Append one feedback entry to the JSONL log and return the stored record.

    Raises ValueError on invalid input.
    """
    if not (0 <= int(corrected_score) <= 100):
        raise ValueError("corrected_score must be 0–100.")
    if quality_label not in QUALITY_LABELS:
        raise ValueError(f"quality_label must be one of {sorted(QUALITY_LABELS)}.")
    unknown = [c for c in checkboxes if c not in CHECKBOX_KEYS]
    if unknown:
        raise ValueError(f"Unknown checkbox keys: {unknown}")

    result = _result_for(output_dir, job_id)
    ai_summary = (result or {}).get("summary") or {}
    ai_metrics = (result or {}).get("metrics") or {}
    meta = (result or {}).get("meta") or {}
    filename = (result or {}).get("filename") or ""

    record = {
        "feedback_id": uuid.uuid4().hex[:12],
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "job_id": job_id,
        "clip_filename": filename,
        "video_path": (result or {}).get("video_url"),
        "video_meta": {
            "fps": meta.get("fps"),
            "width": meta.get("width"),
            "height": meta.get("height"),
            "total_frames": meta.get("total_frames"),
            "duration_sec": (
                meta["total_frames"] / meta["fps"]
                if meta.get("total_frames") and meta.get("fps")
                else None
            ),
        },
        "ai_score": ai_summary.get("overall"),
        "ai_summary": ai_summary,
        "ai_metrics": {
            k: {"score": v.get("score"), "value": v.get("value"), "grade": v.get("grade")}
            for k, v in ai_metrics.items()
        },
        "human_score": int(corrected_score),
        "human_quality_label": quality_label,
        "human_checkboxes": [c for c in CHECKBOX_KEYS if c in checkboxes],  # canonical order
        "human_note": (note or "").strip(),
        "reviewer": (reviewer or "").strip(),
        "score_delta": (
            int(corrected_score) - ai_summary.get("overall", 0)
            if ai_summary.get("overall") is not None
            else None
        ),
        "app_version": APP_VERSION,
    }

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def feedback_for_job(log_path: Path, job_id: str) -> list[dict]:
    if not log_path.exists():
        return []
    out: list[dict] = []
    with log_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("job_id") == job_id:
                out.append(rec)
    return out


def all_feedback(log_path: Path) -> list[dict]:
    if not log_path.exists():
        return []
    out: list[dict] = []
    with log_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out
