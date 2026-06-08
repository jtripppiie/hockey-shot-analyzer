"""
main.py — FastAPI server for hockey shot analysis.

Endpoints:
  POST /analyze   — upload a video, returns JSON results + saves overlay
  GET  /video/{job_id}  — stream the overlay video
  GET  /frame/{job_id}  — return the key frame JPEG
  GET  /history    — return all past session results (from CSV)
"""

import csv
import json
import logging
import os
import re
import shutil
import time
import subprocess
import threading
import traceback
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from metrics import compute_metrics
from overlay import extract_key_frame, render_overlay
from pose import get_video_meta, run_pose_detection
import feedback as feedback_mod
from report import render_report

BASE_DIR   = Path(__file__).parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "output"
HISTORY_CSV = BASE_DIR / "output" / "history.csv"
FEEDBACK_LOG = BASE_DIR / "output" / "feedback_log.jsonl"
FRONTEND_DIR = BASE_DIR / "frontend"

UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Hockey Shot Analyzer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve overlay videos / frames from output dir
app.mount("/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output")
# Serve frontend static assets (js, css) at /static
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/", response_class=FileResponse)
def serve_index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))


@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    # Validate extension
    allowed = {".mp4", ".mov", ".avi", ".mkv"}
    suffix = Path(file.filename).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(400, f"Unsupported file type: {suffix}")

    job_id = uuid.uuid4().hex[:10]
    upload_path = UPLOAD_DIR / f"{job_id}{suffix}"

    # Save upload
    with open(upload_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        return _analyze_video(str(upload_path), file.filename, job_id)
    finally:
        if upload_path.exists():
            upload_path.unlink()


@app.post("/analyze-youtube")
async def analyze_youtube(
    url: str = Form(...),
    start: str = Form(""),     # "MM:SS" or "SS" or empty
    end: str = Form(""),       # "MM:SS" or "SS" or empty
):
    """Download a YouTube clip (optionally trimmed to start..end) and analyze."""
    if not _looks_like_youtube_url(url):
        raise HTTPException(400, "Not a valid YouTube URL")

    start_sec = _parse_timestamp(start)
    end_sec = _parse_timestamp(end)
    if start_sec is not None and end_sec is not None and end_sec <= start_sec:
        raise HTTPException(400, "End time must be after start time")
    # Implicit max length when both are given
    if start_sec is not None and end_sec is not None and (end_sec - start_sec) > 60:
        raise HTTPException(400, "Clip range too long — please pick <= 60 seconds")

    job_id = uuid.uuid4().hex[:10]
    download_path = UPLOAD_DIR / f"{job_id}_yt.mp4"

    try:
        title = _download_youtube_clip(url, str(download_path), start_sec, end_sec)
    except Exception as e:
        logging.error("YouTube download failed:\n" + traceback.format_exc())
        raise HTTPException(422, f"youtube_download_failed: {e}")

    try:
        display_name = title or "YouTube clip"
        return _analyze_video(str(download_path), display_name, job_id)
    finally:
        if download_path.exists():
            download_path.unlink()


def _analyze_video(video_path: str, display_name: str, job_id: str):
    """Shared analysis pipeline used by both file-upload and YouTube endpoints."""
    overlay_video = OUTPUT_DIR / f"{job_id}_overlay.mp4"
    key_frame     = OUTPUT_DIR / f"{job_id}_frame.jpg"

    try:
        meta = get_video_meta(video_path)

        # ── Validate the clip before running expensive pose detection ──
        if meta["total_frames"] < 10:
            raise HTTPException(422, "video_too_short")
        if meta["total_frames"] > 0 and meta["fps"] > 0:
            duration = meta["total_frames"] / meta["fps"]
            if duration > 60:
                raise HTTPException(422, "video_too_long")
        if meta["width"] == 0 or meta["height"] == 0:
            raise HTTPException(422, "video_unreadable")

        # Run pose detection
        frames = run_pose_detection(video_path)

        # Count how many frames had landmarks detected
        detected = [f for f in frames if f["landmarks"]]
        detection_rate = len(detected) / max(len(frames), 1)

        if detection_rate < 0.1:
            raise HTTPException(422, "no_body_detected")
        if detection_rate < 0.4:
            raise HTTPException(422, "poor_detection")

        # Compute metrics
        result = compute_metrics(frames, fps=meta["fps"])
        if not result:
            raise HTTPException(422, "metrics_failed")

        overall = result["summary"]["overall"]

        # Return scores immediately — render overlay in background thread
        _append_history(display_name, result, job_id)
        _save_job_json(job_id, display_name, meta, result)

        # Copy upload to a temp path for background rendering
        render_src = UPLOAD_DIR / f"{job_id}_render.mp4"
        shutil.copy2(video_path, str(render_src))

        def _render_bg():
            try:
                render_overlay(str(render_src), str(overlay_video), overall_score=overall)
                extract_key_frame(str(render_src), str(key_frame))
            except Exception:
                logging.error("Overlay render failed:\n" + traceback.format_exc())
            finally:
                if render_src.exists():
                    render_src.unlink()

        threading.Thread(target=_render_bg, daemon=True).start()

        return JSONResponse({
            "job_id":     job_id,
            "filename":   display_name,
            "meta":       meta,
            "summary":    result["summary"],
            "metrics":    result["metrics"],
            "quality_report": result.get("quality_report"),
            "video_url":  f"/output/{job_id}_overlay.mp4",
            "frame_url":  f"/output/{job_id}_frame.jpg",
        })

    except HTTPException:
        raise
    except Exception:
        logging.error("Analysis exception:\n" + traceback.format_exc())
        raise HTTPException(500, "server_error")


# ── YouTube helpers ───────────────────────────────────────────────────────────

_YT_RE = re.compile(r"(?:youtube\.com|youtu\.be)/", re.IGNORECASE)


def _looks_like_youtube_url(url: str) -> bool:
    return bool(_YT_RE.search(url or ""))


def _parse_timestamp(s: str):
    """Accept '', 'SS', 'MM:SS', or 'HH:MM:SS' → seconds (float) or None."""
    if not s:
        return None
    s = s.strip()
    if not s:
        return None
    parts = s.split(":")
    try:
        parts = [float(p) for p in parts]
    except ValueError:
        raise HTTPException(400, f"Invalid timestamp: {s}")
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    raise HTTPException(400, f"Invalid timestamp: {s}")


def _download_youtube_clip(url: str, out_path: str, start_sec, end_sec) -> str:
    """Download YouTube video (trimmed if start/end given). Returns video title."""
    import yt_dlp

    ydl_opts = {
        "outtmpl": out_path,
        "format": "best[ext=mp4][height<=1080]/best[height<=1080]/best",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }
    # Use yt-dlp's built-in section download to avoid downloading the full video
    if start_sec is not None or end_sec is not None:
        s = start_sec if start_sec is not None else 0
        e = end_sec if end_sec is not None else 999999
        ydl_opts["download_ranges"] = yt_dlp.utils.download_range_func(None, [(s, e)])
        ydl_opts["force_keyframes_at_cuts"] = True

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        title = info.get("title", "YouTube clip")

    if not Path(out_path).exists():
        # yt-dlp sometimes writes with a different extension; find the actual file
        stem = Path(out_path).with_suffix("")
        candidates = sorted(stem.parent.glob(stem.name + "*"))
        if not candidates:
            raise RuntimeError("Downloaded file not found")
        actual = candidates[0]
        if str(actual) != out_path:
            os.replace(str(actual), out_path)

    return title


@app.get("/history")
def get_history():
    if not HISTORY_CSV.exists():
        return []
    rows = []
    with open(HISTORY_CSV, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


@app.get("/history/{job_id}")
def get_history_item(job_id: str):
    job_file = OUTPUT_DIR / f"{job_id}_result.json"
    if not job_file.exists():
        raise HTTPException(404, "Job not found")
    with open(job_file) as f:
        return json.load(f)


@app.delete("/history/{job_id}")
def delete_history_item(job_id: str):
    # Remove output files
    for suffix in ("_overlay.mp4", "_frame.jpg", "_result.json", "_landmarks.json"):
        p = OUTPUT_DIR / f"{job_id}{suffix}"
        if p.exists():
            p.unlink()
    # Remove from CSV
    _remove_from_csv(job_id)
    return {"deleted": job_id}


@app.delete("/history")
def clear_history():
    # Remove all output files
    for f in OUTPUT_DIR.iterdir():
        if f.is_file() and f.name != "history.csv":
            f.unlink()
    if HISTORY_CSV.exists():
        HISTORY_CSV.unlink()
    return {"cleared": True}


def _remove_from_csv(job_id: str):
    if not HISTORY_CSV.exists():
        return
    with open(HISTORY_CSV, newline="") as f:
        rows = list(csv.DictReader(f))
    rows = [r for r in rows if r.get("job_id") != job_id]
    if not rows:
        HISTORY_CSV.unlink()
        return
    fieldnames = list(rows[0].keys())
    with open(HISTORY_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _save_job_json(job_id: str, filename: str, meta: dict, result: dict):
    job_file = OUTPUT_DIR / f"{job_id}_result.json"
    with open(job_file, "w") as f:
        json.dump({
            "job_id":    job_id,
            "filename":  filename,
            "date":      datetime.now().strftime("%Y-%m-%d %H:%M"),
            "meta":      meta,
            "summary":   result["summary"],
            "metrics":   result["metrics"],
            "quality_report": result.get("quality_report"),
            "video_url": f"/output/{job_id}_overlay.mp4",
            "frame_url": f"/output/{job_id}_frame.jpg",
        }, f)




def _append_history(filename: str, result: dict, job_id: str):
    fieldnames = [
        "job_id", "filename", "date",
        "overall", "power", "technique", "timing",
        "knee_bend", "hip_rotation", "shoulder_rotation", "weight_transfer",
        "follow_through", "head_stability", "release_timing",
    ]
    write_header = not HISTORY_CSV.exists()
    with open(HISTORY_CSV, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        m = result["metrics"]
        s = result["summary"]
        writer.writerow({
            "job_id":   job_id,
            "filename": filename,
            "date":     datetime.now().strftime("%Y-%m-%d %H:%M"),
            "overall":  s["overall"],
            "power":    s["power"],
            "technique": s["technique"],
            "timing":   s["timing"],
            **{k: m[k]["score"] for k in m},
        })


# ── Expert Feedback Mode ──────────────────────────────────────────────────────
@app.post("/feedback")
async def save_feedback_endpoint(payload: dict = Body(...)):
    """Append one expert-feedback entry to the JSONL log."""
    try:
        job_id = payload.get("job_id")
        if not job_id:
            raise HTTPException(400, "job_id required")
        record = feedback_mod.save_feedback(
            OUTPUT_DIR,
            FEEDBACK_LOG,
            job_id=job_id,
            corrected_score=int(payload.get("corrected_score", 0)),
            quality_label=str(payload.get("quality_label", "")),
            checkboxes=list(payload.get("checkboxes", []) or []),
            note=str(payload.get("note", "")),
            reviewer=str(payload.get("reviewer", "")),
            frame_url=str(payload.get("frame_url", "")),
        )
        return JSONResponse({"ok": True, "feedback": record})
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/feedback/{job_id}")
def get_feedback(job_id: str):
    return JSONResponse(feedback_mod.feedback_for_job(FEEDBACK_LOG, job_id))


@app.get("/feedback")
def list_feedback():
    return JSONResponse(feedback_mod.all_feedback(FEEDBACK_LOG))


# ── Measurement-quality Feedback (about the AI, not the player) ──────────────
@app.post("/measurement-feedback")
async def save_measurement_feedback_endpoint(payload: dict = Body(...)):
    """Append one measurement-quality feedback entry (anonymous)."""
    try:
        job_id = payload.get("job_id")
        if not job_id:
            raise HTTPException(400, "job_id required")
        record = feedback_mod.save_measurement_feedback(
            OUTPUT_DIR,
            FEEDBACK_LOG,
            job_id=job_id,
            metric_ratings=dict(payload.get("metric_ratings", {}) or {}),
            checkboxes=list(payload.get("checkboxes", []) or []),
            overall_label=str(payload.get("overall_label", "")),
            note=str(payload.get("note", "")),
            frame_url=str(payload.get("frame_url", "")),
        )
        return JSONResponse({"ok": True, "feedback": record})
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/measurement-feedback/{job_id}")
def get_measurement_feedback(job_id: str):
    return JSONResponse(feedback_mod.measurement_feedback_for_job(FEEDBACK_LOG, job_id))


@app.get("/measurement-feedback")
def list_measurement_feedback():
    return JSONResponse(feedback_mod.all_measurement_feedback(FEEDBACK_LOG))


@app.get("/report/{job_id}", response_class=HTMLResponse)
def html_report(job_id: str, expert: int = 0):
    """Printable HTML report. expert=1 includes the Expert Feedback section."""
    job_file = OUTPUT_DIR / f"{job_id}_result.json"
    if not job_file.exists():
        raise HTTPException(404, "Job not found")
    with open(job_file) as f:
        result = json.load(f)
    fb = feedback_mod.feedback_for_job(FEEDBACK_LOG, job_id) if expert else None
    mfb = feedback_mod.measurement_feedback_for_job(FEEDBACK_LOG, job_id) if expert else None
    html = render_report(result, feedback=fb, measurement_feedback=mfb, expert=bool(expert))
    return HTMLResponse(html)


# ── Frame capture (browser-side canvas → JPEG upload) ────────────────────────
@app.post("/capture-frame")
async def capture_frame(
    job_id: str = Form(...),
    t_sec: float = Form(0.0),
    frame: UploadFile = File(...),
):
    """Save a JPEG captured by the browser (via <canvas>) under output/.
    The frontend POSTs the frame so we never decode video server-side."""
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "", job_id)[:32]
    if not safe_id:
        raise HTTPException(400, "Invalid job_id")
    # Cap pasted MIME / extension; we always store as .jpg
    suffix = ".jpg"
    ts_ms = int(time.time() * 1000)
    out_name = f"{safe_id}_capture_{ts_ms}{suffix}"
    out_path = OUTPUT_DIR / out_name
    # Path-traversal guard (resolved path must live under OUTPUT_DIR)
    if not str(out_path.resolve()).startswith(str(OUTPUT_DIR.resolve())):
        raise HTTPException(400, "Invalid path")
    with open(out_path, "wb") as f:
        shutil.copyfileobj(frame.file, f)
    return JSONResponse({
        "ok": True,
        "frame_url": f"/output/{out_name}",
        "t_sec": float(t_sec),
        "filename": out_name,
    })

