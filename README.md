# 🏒 Hockey Shot Analyzer

A kid-friendly browser app that analyzes hockey shots from a video clip and gives a personal coaching report — knee bend, hip & shoulder rotation, weight transfer, follow-through, head stability, and release timing. Built with FastAPI + MediaPipe.

## Quick start (Linux / WSL / macOS)

```bash
./run.sh
```

That script installs system deps (ffmpeg, libegl, libgles), creates a Python venv, installs requirements, downloads the MediaPipe pose model, and starts the server on `http://localhost:8000`.

## What it measures

The analyzer refuses to score what it can't see clearly — each metric returns a confidence-gated value, and a quality report tells you when a clip needs to be re-filmed from the side.

- **Knee bend** — minimum knee angle on the shooting side
- **Hip rotation** — 3D angular sweep during the shot window
- **Shoulder rotation** — 3D angular sweep during the shot window
- **Weight transfer** — hip-midpoint travel from load to release
- **Follow-through** — peak wrist height after release
- **Head stability** — head position variance during the shot
- **Release timing** — load → release duration in ms

Composite scores: **Power**, **Technique**, **Timing**, and an overall **Shot Score**.

## Tech

- Python 3.10 · FastAPI · uvicorn
- MediaPipe Tasks PoseLandmarker (Lite)
- OpenCV + NumPy
- ffmpeg (H.264 / yuv420p) for overlay re-encode
- yt-dlp for YouTube clip ingest
- Vanilla HTML/CSS/JS frontend

## Project layout

```
backend/   FastAPI app, pose detection, biomechanics, overlay rendering
frontend/  Static UI (no build step)
run.sh     One-click bootstrap + launch
share.sh   Optional cloudflared tunnel for public sharing
```
