# Agent Guide — Hockey Shot Analyzer

Fast-start context for AI coding sessions. Read this first; the architecture
decisions below are intentional and should not be undone without discussion.

## Current state

- **Last shipped features:**
  1. Expert Feedback Mode (orange panel, desktop-only, `Ctrl/Cmd+Shift+F`).
  2. Measurement Feedback (blue sub-panel, scores the *analyzer*, not the athlete).
  3. Browser-side Frame Capture (📸 button → `/capture-frame` → JPEG attached to JSONL row → embedded in Expert report).
  4. Athletic progress scene (rink + player + pucks animation) replacing the plain spinner during analysis.
  5. Lighter, semi-transparent pose overlay (smaller dots, `cv2.addWeighted` blend at 0.65) so the underlying video shows through the skeleton.
- **App version constant:** `APP_VERSION = "0.2.0-expert-feedback"` in
  `backend/feedback.py`.
- **Sibling repo:** `pole-vault-analyzer` (mirrored structure, same patterns).
  A related repo `pdf-compliance-analyzer` exists for compliance work.

## Run it

```bash
cd backend
source ../.venv/bin/activate
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

- **Port:** `8000`
- **Cloudflare tunnel:** `https://recall-permitted-acts-sandra.trycloudflare.com`
  (Quick Tunnel — name changes every restart. Run with
  `cloudflared tunnel --url http://localhost:8000`.)
- **Frontend:** static files in `frontend/`, served by FastAPI. No build step.

The MediaPipe pose model lives at `backend/pose_landmarker.task` and is the
only large local asset (gitignored).

## Stack

- Python 3.10, FastAPI, uvicorn (WSL Ubuntu 22.04 dev box)
- MediaPipe Tasks PoseLandmarker, OpenCV, ffmpeg (CLI, used for video re-encode)
- Vanilla HTML/CSS/JS frontend — no bundler, no framework
- Append-only JSONL log: `output/feedback_log.jsonl`

## Design decisions (keep these)

1. **One JSONL log, two shapes** — Performance and Measurement feedback share
   `output/feedback_log.jsonl` with a `"type": "performance" | "measurement"`
   discriminator. Legacy rows without `type` are treated as performance.
2. **Desktop-only Expert Mode gate** — Dual guard: JS `matchMedia(
   "(hover: hover) and (pointer: fine) and (min-width: 1024px)")` plus a CSS
   `@media` rule. localStorage key `expertMode = "1"`. Keyboard:
   `Ctrl/Cmd+Shift+F`.
3. **Browser-side frame capture** — The Capture button draws the current
   `<video id="overlayVideo">` frame onto a `<canvas>` and POSTs the resulting
   JPEG to `/capture-frame`. We **do not** decode video server-side; this keeps
   the endpoint trivial and avoids an ffmpeg shellout per click.
4. **HTML printable reports, not PDF libs** — `backend/report.py` renders an
   HTML page sized for letter/A4. Users print via browser (Ctrl+P → Save as
   PDF). No WeasyPrint / ReportLab.
5. **Path-traversal guard on `/capture-frame`** — `job_id` is stripped to
   `[a-zA-Z0-9_-]{1,32}`. The resolved output path is verified to live under
   `OUTPUT_DIR`.
6. **Skeleton overlay is intentionally subtle** — the renderer draws into a
   copy of the frame and blends back at 65 % (`cv2.addWeighted(overlay, 0.65,
   frame, 0.35, 0, dst=frame)`). Dot/line sizes are deliberately small
   (`dot_radius = max(3, min(w,h)/240)`). Don't crank these back up without a
   reason — users complained the old solid overlay smothered the player.
7. **Progress UI is a sport-themed scene, not a spinner** — hockey shows a
   rink with a player firing pucks toward a goal (pure CSS keyframes). Vault
   shows a runway scene where the vaulter's `left` position is driven by a
   `--pct` custom property set by `setProgress()`. Both respect
   `prefers-reduced-motion`.

## Hot files

| Path | Purpose |
|------|---------|
| `backend/main.py` | All FastAPI routes; `/feedback`, `/measurement-feedback`, `/capture-frame`, `/report/{job_id}` |
| `backend/feedback.py` | JSONL schema + `save_feedback` / `save_measurement_feedback`; constants `CHECKBOX_KEYS`, `MEASUREMENT_CHECKBOX_KEYS`, `METRIC_RATINGS`, `OVERALL_MEASUREMENT_LABELS` |
| `backend/report.py` | `render_report(... expert=False)` HTML template; captured frames render as `<img class='fb-frame'>` inside fb-card / mfb-card |
| `backend/overlay.py` | `_draw_skeleton()` (alpha-blended) + H.264 re-encode pipeline |
| `frontend/app.js` | `currentJob` global; `captureFrame(prefix)`, `submitFeedback()`, `submitMeasurementFeedback()`, `setProgress()` (also writes `--pct` to `#progressScene`), `_refreshExpertVisibility()` |
| `frontend/index.html` | Markup ids: `overlayVideo`, `progressScene`, `fbFrameUrl`, `fbFramePreview`, `mfbFrameUrl`, `mfbFramePreview`, `mfbOverall`, `mfbMetricGrid`, `mfbCheckGrid` |
| `frontend/style.css` | `.scene`, `.scene-character`, `.scene-puck`, `@keyframes puck-shoot`, `.frame-preview`, `.fb-frame` |

## Conventions

- **Commits:** author `jtripppiie <jtripppiie@users.noreply.github.com>`. The
  Git CLI is authed; gh is authed as `jtripppiie` via SSH.
- **No comments unless WHY is non-obvious.** Don't add docstrings just to fill
  space. Don't reference the task/PR in code comments.
- **When restarting servers, never `pkill -f uvicorn`.** That kills the live
  hockey + vault servers on 8000/8001 and breaks both Cloudflare tunnels. Use
  a port-specific pattern, e.g. `pkill -f "port 8790"`.
- **SCSS-only theme edits** when adjusting styling — never edit compiled CSS
  directly (this repo currently uses plain `style.css`; the SCSS note applies
  to projects that have a SCSS pipeline).

## Common gotchas

- `currentJob` may be `null` before a clip is analyzed — guard at the top of
  any action.
- Captured frames cache-bust by appending `?t=Date.now()` in the `<img src>`,
  since FastAPI's `StaticFiles` sets long cache headers in dev.
- The feedback log can grow indefinitely — there is intentionally no rotation.
  If you add one, gate behind a feature flag.
