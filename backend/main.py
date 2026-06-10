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
from pose import get_video_meta, run_pose_detection, scene_cut_precheck
import feedback as feedback_mod
from report import render_report, render_session_report
import session as session_mod
from segmenter import suggest_segments
from errors import log_error, recent_errors, clear_errors
BASE_DIR   = Path(__file__).parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "output"
HISTORY_CSV = BASE_DIR / "output" / "history.csv"
FEEDBACK_LOG = BASE_DIR / "output" / "feedback_log.jsonl"
FRONTEND_DIR = BASE_DIR / "frontend"

UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# Storage retention. Uploads are transient and always swept; output history is
# unlimited by default (set HISTORY_MAX_ENTRIES > 0 to cap it, like
# ERROR_LOG_MAX_LINES). Both are read from the environment at boot.
UPLOAD_MAX_AGE_S = int(os.environ.get("UPLOAD_MAX_AGE_S", "3600"))
HISTORY_MAX_ENTRIES = int(os.environ.get("HISTORY_MAX_ENTRIES", "0"))

app = FastAPI(title="Hockey Shot Analyzer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request, exc):
    """Catch-all: record any unhandled error before returning a clean 500.
    HTTPExceptions are handled by FastAPI's own handler and skip this."""
    log_error(
        f"unhandled:{request.method} {request.url.path}",
        exc,
        context={"path": request.url.path, "method": request.method},
    )
    return JSONResponse(status_code=500, content={"detail": "server_error"})

# Serve overlay videos / frames from output dir
app.mount("/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output")
# Serve frontend static assets (js, css) at /static
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/", response_class=FileResponse)
def serve_index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))


@app.post("/analyze")
async def analyze(file: UploadFile = File(...), hand_override: str = Form("")):
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
        return _analyze_video(str(upload_path), file.filename, job_id,
                              hand_override=hand_override)
    finally:
        if upload_path.exists():
            upload_path.unlink()


@app.post("/analyze-youtube")
async def analyze_youtube(
    url: str = Form(...),
    start: str = Form(""),     # "MM:SS" or "SS" or empty
    end: str = Form(""),       # "MM:SS" or "SS" or empty
    hand_override: str = Form(""),
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
        log_error("analyze-youtube:download", e, context={"url": url})
        raise HTTPException(422, f"youtube_download_failed: {e}")

    try:
        display_name = title or "YouTube clip"
        return _analyze_video(str(download_path), display_name, job_id,
                              hand_override=hand_override)
    finally:
        if download_path.exists():
            download_path.unlink()


def _analyze_video(video_path: str, display_name: str, job_id: str,
                   hand_override: str | None = None):
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
            log_error("reject:no_body_detected", severity="info",
                      message="rejected: no body detected",
                      context={"job_id": job_id, "detection_rate": round(detection_rate, 3),
                               "n_frames": len(frames)})
            raise HTTPException(422, "no_body_detected")
        if detection_rate < 0.4:
            log_error("reject:poor_detection", severity="info",
                      message="rejected: poor detection",
                      context={"job_id": job_id, "detection_rate": round(detection_rate, 3),
                               "n_frames": len(frames)})
            raise HTTPException(422, "poor_detection")

        # Pixel-level scene-cut pre-check (no pose): an independent corroborating
        # signal to the pose-based body-teleport detector. It still catches
        # splices when pose tracking drops out at the cut, so we run it on the
        # raw video and feed its count into compute_metrics.
        precheck = scene_cut_precheck(video_path)

        # Compute metrics
        result = compute_metrics(frames, fps=meta["fps"], hand_override=hand_override,
                                 precheck_cuts=precheck["pixel_cuts"])
        if not result:
            raise HTTPException(422, "metrics_failed")
        q = result["quality_report"]
        if q.get("shot_check", {}).get("reject"):
            # Telemetry: record the signal values behind every rejection so we
            # can tell genuine non-shots from over-tight thresholds (a clip a
            # real user expected to score). Viewable in Settings → Diagnostics.
            log_error("reject:not_a_hockey_shot", severity="info",
                      message="rejected: not a hockey shot",
                      context={"job_id": job_id, "shot_check": q.get("shot_check"),
                               "continuity_check": q.get("continuity_check")})
            raise HTTPException(422, "not_a_hockey_shot")

        # Warn-only continuity: log when an accepted clip still trips the cut
        # detector, so a stream of false alarms (or real montages) is visible.
        cc = q.get("continuity_check", {})
        if not cc.get("looks_continuous", True):
            log_error("warn:camera_cuts", severity="info",
                      message="flagged: clip looks discontinuous (camera cuts)",
                      context={"job_id": job_id, "continuity_check": cc})

        overall = result["summary"]["overall"]

        # Return scores immediately — render overlay in background thread
        try:
            _append_history(display_name, result, job_id)
            _enforce_history_cap()
        except Exception as e:
            log_error("append_history", e, context={"job_id": job_id})
        try:
            _save_job_json(job_id, display_name, meta, result)
        except Exception as e:
            log_error("save_job_json", e, context={"job_id": job_id})

        # Copy upload to a temp path for background rendering
        render_src = UPLOAD_DIR / f"{job_id}_render.mp4"
        shutil.copy2(video_path, str(render_src))

        def _render_bg():
            try:
                render_overlay(str(render_src), str(overlay_video),
                               overall_score=overall, frames_landmarks=frames)
                extract_key_frame(str(render_src), str(key_frame))
            except Exception as e:
                log_error("overlay_render", e, context={"job_id": job_id})
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
    except Exception as e:
        log_error("analyze_video", e, context={"job_id": job_id, "filename": display_name})
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


def _trim_clip(src: str, dst: str, start_sec: float, end_sec: float) -> None:
    """Trim [start_sec, end_sec] out of src into dst, re-encoding for
    frame-accurate cuts. Raises RuntimeError if ffmpeg fails."""
    dur = max(0.1, end_sec - start_sec)
    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-ss", f"{start_sec:.3f}",
            "-i", src,
            "-t", f"{dur:.3f}",
            "-c:v", "libx264", "-preset", "veryfast", "-an",
            dst,
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or not Path(dst).exists():
        raise RuntimeError(f"ffmpeg trim failed: {result.stderr[-300:]}")


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
    _delete_job_artifacts(job_id)
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


# ── Multi-rep sessions (SKELETON) ─────────────────────────────────────────────
# Group several analyzed attempts into one session + (eventually) a combined
# session report with per-rep scores and trends.
# See docs/ROADMAP-live-capture-session-report.md (Phase 2/3) and session.py /
# segmenter.py. These routes are wired and usable; the analytics + segmentation
# they lean on are still stubbed.

@app.post("/session")
def create_session(label: str = Form("")):
    """Create a new, empty multi-rep session."""
    return session_mod.create_session(label)


@app.get("/sessions")
def list_sessions():
    """List all sessions, newest first."""
    return session_mod.list_sessions()


@app.get("/session/{session_id}")
def get_session(session_id: str):
    s = session_mod.load_session(session_id)
    if s is None:
        raise HTTPException(404, "Session not found")
    return s


@app.post("/session/{session_id}/attempt")
def add_session_attempt(session_id: str, job_id: str = Form(...)):
    """Attach an already-analyzed attempt (job) to a session.

    Phase 2 flow: the client analyzes each trimmed segment via /analyze as usual,
    then registers the resulting job_id here in attempt order.
    """
    s = session_mod.add_job(session_id, job_id)
    if s is None:
        raise HTTPException(404, "Session not found")
    return s


@app.post("/session/{session_id}/segment")
def segment_session(session_id: str, job_id: str = Form(...)):
    """Suggest cut windows for a long recording (Phase 3 auto-splice).

    Takes the job_id of an analyzed *full stream* and returns suggested
    [start, end] frame windows for each detected attempt. SKELETON: returns
    suggestions only — a human confirms/adjusts before each window is trimmed and
    analyzed. The segmenter's peak-picking is not yet tuned (see segmenter.py).
    """
    if session_mod.load_session(session_id) is None:
        raise HTTPException(404, "Session not found")
    # TODO(Phase 3): locate the stream's source video for this job_id. For now we
    # re-run pose on the stored upload; later, cache landmarks from the original
    # analysis instead of recomputing.
    stream_src = UPLOAD_DIR / f"{job_id}.mp4"
    if not stream_src.exists():
        raise HTTPException(404, "Stream video not found for job")
    meta = get_video_meta(str(stream_src))
    frames = run_pose_detection(str(stream_src))
    windows = suggest_segments(frames, meta["fps"], meta["total_frames"])
    return {"session_id": session_id, "fps": meta["fps"],
            "total_frames": meta["total_frames"], "suggested": windows}


@app.get("/session/{session_id}/report")
def session_report(session_id: str, format: str = "json"):
    """Aggregate the session's attempts into a session-level summary.

    SKELETON: returns the summarize_session() shape (attempts + stubbed
    averages/trends). ``?format=html`` renders the printable session report.
    """
    s = session_mod.load_session(session_id)
    if s is None:
        raise HTTPException(404, "Session not found")
    jobs = []
    for jid in s.get("job_ids", []):
        jf = OUTPUT_DIR / f"{jid}_result.json"
        if jf.exists():
            with open(jf) as f:
                jobs.append(json.load(f))
    summary = session_mod.summarize_session(s, jobs)
    if format == "html":
        return HTMLResponse(render_session_report(summary))
    return summary


@app.delete("/session/{session_id}")
def delete_session(session_id: str):
    if not session_mod.delete_session(session_id):
        raise HTTPException(404, "Session not found")
    return {"deleted": session_id}


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


# ── Error logging (browser-side reports + viewer) ────────────────────────────
@app.post("/client-error")
async def client_error(payload: dict = Body(...)):
    """Record a browser-side error. The frontend's global error handler POSTs
    here; all fields are treated as untrusted and length-capped in errors.py."""
    where = str(payload.get("where") or "client")[:200]
    message = str(payload.get("message") or "")
    context = {
        "url":        str(payload.get("url") or "")[:300],
        "user_agent": str(payload.get("user_agent") or "")[:300],
        "line":       payload.get("line"),
        "column":     payload.get("column"),
    }
    stack = payload.get("stack")
    if stack:
        context["stack"] = str(stack)[:4000]
    log_error(f"frontend:{where}", message=message, context=context,
              severity="error", source="frontend")
    return JSONResponse({"ok": True})


@app.get("/errors")
def get_errors(limit: int = 50):
    """Return the most recent logged errors (newest first) for review."""
    return recent_errors(limit)


@app.post("/errors/clear")
def clear_error_log():
    """Delete the error log. Returns how many entries were removed."""
    removed = clear_errors()
    return JSONResponse({"ok": True, "removed": removed})


# ── Multi-attempt segmenting ─────────────────────────────────────────────────
def _sweep_old_uploads(max_age_s: int = None) -> int:
    """Best-effort cleanup of stale files in uploads/.

    Uploads are transient: every analyze path deletes its upload as soon as the
    request finishes (see /analyze's `finally`), background render copies are
    removed by the render thread, and cached multi-rep sources are short-lived.
    Anything left in uploads/ older than max_age_s is therefore an orphan from a
    crashed or interrupted request, so we remove it. A live request's files are
    seconds old, never an hour, so this can't race an in-flight analysis.
    Returns the number of files removed. Never raises.
    """
    if max_age_s is None:
        max_age_s = UPLOAD_MAX_AGE_S
    now = time.time()
    removed = 0
    try:
        entries = list(UPLOAD_DIR.iterdir())
    except OSError:
        return 0
    for p in entries:
        try:
            if p.is_file() and now - p.stat().st_mtime > max_age_s:
                p.unlink()
                removed += 1
        except OSError:
            pass
    return removed


def _delete_job_artifacts(job_id: str) -> None:
    """Remove every output file belonging to one job (overlay, frame, result,
    landmarks, captured frames). job_id is sanitized; never raises."""
    safe = re.sub(r"[^a-zA-Z0-9_-]", "", job_id)[:32]
    if not safe:
        return
    for p in OUTPUT_DIR.glob(f"{safe}_*"):
        try:
            if p.is_file():
                p.unlink()
        except OSError:
            pass


def _enforce_history_cap(max_entries: int = None) -> int:
    """Opt-in retention: keep only the newest `max_entries` history rows and
    delete the output artifacts of any job pruned out (overlay videos are the
    bulk of disk use). Off by default (HISTORY_MAX_ENTRIES <= 0) so existing
    deployments keep unlimited history; set HISTORY_MAX_ENTRIES to bound disk
    growth, mirroring ERROR_LOG_MAX_LINES. Returns rows removed. Never raises."""
    if max_entries is None:
        max_entries = HISTORY_MAX_ENTRIES
    if max_entries <= 0 or not HISTORY_CSV.exists():
        return 0
    try:
        with open(HISTORY_CSV, newline="") as f:
            rows = list(csv.DictReader(f))
    except OSError:
        return 0
    if len(rows) <= max_entries:
        return 0
    keep = rows[-max_entries:]          # newest rows are appended last
    drop = rows[:-max_entries]
    for r in drop:
        jid = r.get("job_id")
        if jid:
            _delete_job_artifacts(jid)
    try:
        fieldnames = list(rows[0].keys())
        with open(HISTORY_CSV, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(keep)
    except OSError:
        pass
    return len(drop)


@app.on_event("startup")
def _startup_cleanup() -> None:
    """Sweep stale uploads (and apply any history cap) once at boot."""
    try:
        n = _sweep_old_uploads()
        if n:
            log_error("startup:swept_uploads", severity="info",
                      message=f"removed {n} stale upload file(s) at startup",
                      context={"removed": n})
        _enforce_history_cap()
    except Exception as e:  # never block startup on cleanup
        log_error("startup_cleanup", e)


@app.post("/suggest-segments")
async def suggest_segments_route(file: UploadFile = File(...)):
    """Run pose detection on a multi-attempt clip and return suggested cut
    windows (in seconds). The source is cached so each suggested attempt can be
    analyzed via /analyze-segment without re-uploading."""
    allowed = {".mp4", ".mov", ".avi", ".mkv"}
    suffix = Path(file.filename).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(400, f"Unsupported file type: {suffix}")

    _sweep_old_uploads()
    seg_job = uuid.uuid4().hex[:10]
    src = UPLOAD_DIR / f"{seg_job}_multi{suffix}"
    with open(src, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        meta = get_video_meta(str(src))
        fps = meta.get("fps") or 0
        total = meta.get("total_frames") or 0
        if total < 10 or fps <= 0:
            raise HTTPException(422, "video_unreadable")
        frames = run_pose_detection(str(src))
        windows = suggest_segments(frames, fps, total)
        segments = [{
            "index":      i,
            "start_sec":  round(w["start"] / fps, 2),
            "end_sec":    round(w["end"] / fps, 2),
            "event_sec":  round(w["event"] / fps, 2),
            "confidence": round(float(w.get("confidence", 0.0)), 3),
        } for i, w in enumerate(windows)]
        return JSONResponse({
            "seg_job":  seg_job,
            "filename": file.filename,
            "fps":      fps,
            "duration": round(total / fps, 2),
            "count":    len(segments),
            "segments": segments,
        })
    except HTTPException:
        if src.exists():
            src.unlink()
        raise
    except Exception as e:
        if src.exists():
            src.unlink()
        log_error("suggest_segments", e, context={"filename": file.filename})
        raise HTTPException(500, "server_error")


@app.post("/analyze-segment")
async def analyze_segment(
    seg_job: str = Form(...),
    start_sec: float = Form(...),
    end_sec: float = Form(...),
    label: str = Form(""),
    hand_override: str = Form(""),
):
    """Trim one suggested attempt out of a cached multi-rep source and analyze
    it as its own clip."""
    safe = re.sub(r"[^a-zA-Z0-9_-]", "", seg_job)[:32]
    if not safe:
        raise HTTPException(400, "Invalid seg_job")
    matches = sorted(UPLOAD_DIR.glob(f"{safe}_multi.*"))
    if not matches:
        raise HTTPException(404, "segment_source_expired")
    if end_sec <= start_sec:
        raise HTTPException(400, "End time must be after start time")

    src = matches[0]
    job_id = uuid.uuid4().hex[:10]
    trimmed = UPLOAD_DIR / f"{job_id}{src.suffix}"
    display_name = label.strip() or f"Attempt @ {start_sec:.0f}s"
    try:
        _trim_clip(str(src), str(trimmed), float(start_sec), float(end_sec))
        return _analyze_video(str(trimmed), display_name, job_id,
                              hand_override=hand_override)
    finally:
        if trimmed.exists():
            trimmed.unlink()



