# Agent Guide — Hockey Shot Analyzer

Fast-start context for AI coding sessions. Read this first; the architecture
decisions below are intentional and should not be undone without discussion.

## Current state

- **Last shipped features:**
  1. **Compact dashboard upload + results UI (June 2026)** — light upload and coach-report results screens, mirrored with `pole-vault-analyzer` so the apps feel like the same tool family. Headings/body now use `Nunito Sans`; upload uses a wide 1420px three-column desktop layout with image-led sport art on the left, a compact combined upload/YouTube card in the center, and one-column guidance cards on the right. The old on-page filming tips are hidden from the upload flow; the header has **History**, an icon-only **Settings** gear, and **Recording Tips**. Settings is available from upload/progress/results/history topbars; desktop opens a modal, mobile uses the same overlay as a full-screen page. Settings contains Player Profile local-only personalization (`profileAccent`, `profileHandOverride`) under `hockeyPlayerProfile.v1`. Name, age, position, and custom photo upload are intentionally not collected. The shooting-hand override is UI/local-storage only for now; it does not affect analyzer scoring until backend dominant-hand override work is added separately. First launch shows `onboardingOverlay` once (`hockeyOnboardingSeen.v1`) with Customize/Skip. `Recording Tips` opens an embedded YouTube search iframe in `tipsOverlay` and clears `iframe.src` on close so it restarts each time. Results screen has a focused hero with banded score label (`Elite Form` / `Solid Foundation` / `Building Up` / `Early Days` / `Just Starting`), one-line tagline derived from strongest+weakest measured metric, a compact readout (`measuredCount`, `priorityLabel`, `filenameLabel`), phase timeline (Setup→Load→Release→Follow-Through), and a `metric-grid` sorted weakest-first with the top opportunity flagged via a `metric-priority` orange pill. Coach’s Report split into strengths / focus / drills. Progress scene is an ice-rink palette with a helmeted player + 3 flying pucks (`puck-fly` keyframe). Tokens live under `:root` (`--d-*` dark palette, `--l-*` light palette, accents, `--font-head`, `--font-body`, `--page-width`, `--page-width-wide`). **Hard rule:** all existing element IDs (`overallNum`, `sub-power`, `sub-technique`, `sub-timing`, `powerNum`, `techniqueNum`, `timingNum`, `metricGrid`, `coachStrengths`, etc.) are preserved verbatim — do not rename without grepping `app.js` first.
  2. Expert Feedback Mode (orange panel, desktop-only, `Ctrl/Cmd+Shift+F`).
  3. Measurement Feedback (blue sub-panel, scores the *analyzer*, not the athlete).
  4. Browser-side Frame Capture (📸 button → `/capture-frame` → JPEG attached to JSONL row → embedded in Expert report).
  5. Athletic progress scene (rink + player + pucks animation) replacing the plain spinner during analysis.
  6. Lighter, semi-transparent pose overlay (smaller dots, `cv2.addWeighted` blend at 0.65) so the underlying video shows through the skeleton.
  7. **Practice Sessions** — group multiple analyzed clips into a named session and see averages + first-vs-last trends per metric. Backend `backend/session.py` (sport-agnostic `summarize_session`, JSON-per-session under `output/session_*.json`); UI in the **Sessions** topbar button (`sessionsSection`). Session reports render via `report.py::render_session_report`.
  8. **Multi-rep segmenter** (`backend/segmenter.py`) — smoothing + true local-maxima + non-max suppression to suggest attempt windows in a multi-shot clip (replaces the old greedy peak-pick). Constants still need calibration against real multi-rep footage.
  9. **Centralized error logging** — append-only `output/error_log.jsonl` via `backend/errors.py` (`log_error` / `recent_errors`). A global `@app.exception_handler(Exception)` catches escaped route errors; the browser forwards uncaught JS errors to `POST /client-error`; `GET /errors` returns the newest entries. Viewable in-app under **Settings → Diagnostics** (`#diagnostics`, `loadErrors()`).
  10. **Self-contained tests** (`backend/test_session.py`) — runnable via plain `python test_session.py` (no pytest/httpx needed); covers session round-trip, summary averages/trends, and segmenter peak detection.
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
2. **Results-only Expert Mode gate** — Dual guard: JS `matchMedia(
  "(hover: hover) and (pointer: fine) and (min-width: 1024px)")` plus a CSS
  `@media` rule. Expert Mode is in-memory only (`expertModeOn`), never
  persisted. It is only visible on `body[data-screen="results"]`; upload,
  progress, history, settings, and refresh disable it. Keyboard:
  `Ctrl/Cmd+Shift+F`; the `🧑‍🏫 Expert Mode ✕` badge disables it.
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
8. **Joint angles use MediaPipe `pose_world_landmarks`, not image
   coordinates** — `backend/pose.py::run_pose_detection` captures both the
   image-space landmarks (`x, y, z, v`) AND the metric world landmarks
   (`wx, wy, wz`, hip-centred meters) on every frame, and EMA-smooths both.
   `angle_3pts_3d()` computes joint angles from `wx/wy/wz`, so the angle at
   a joint is rotation-invariant w.r.t. the camera (a slightly off-axis
   camera no longer flattens a knee bend). `_measure_knee_bend` and
   `_measure_rotation_angle` use the world path (rotation falls back to
   image+z via `_pt3` if world coords are missing for legacy data). The
   original 2D `angle_3pts` is kept for follow-through height, head
   stability, release timing, and weight transfer — those genuinely *want*
   image-plane measurements. If you add a new joint-angle metric, default to
   `angle_3pts_3d`. If you add a new vertical-lean metric, **do not** use
   world Y without first verifying the orientation convention against a
   sample clip — image Y is safer until then.
9. **Upload header owns optional helpers** — filming guidance is now a
  topbar **Recording Tips** button that opens `tipsOverlay`, not an in-flow tips card. The legacy
  `<details id="filmingTips" class="tips-card">` remains in `index.html` but
  `.tips-card` is hidden so the upload screen fits laptop-height viewports.
  The optional player personalization fields live in `<details id="playerProfile" class="ctx-card profile-card">`
  inside `settingsOverlay` and are toggled by `openSettings()`. `Start Fresh`
  clears localStorage, preserves the onboarding-seen flag, and returns the app
  to defaults.
10. **All errors land in one JSONL log** — `backend/errors.py` is the single
   choke point: `log_error(where, exc=None, *, message=None, context=None,
   severity="error", source="backend")` appends one capped, JSON-safe row to
   `output/error_log.jsonl` and never raises. Backend catches call it with the
   exception; the frontend's global `error` / `unhandledrejection` handlers POST
   to `/client-error` (source `frontend`). All `/client-error` fields are
   untrusted and length-capped in `errors.py`. There is intentionally no log
   rotation (matches the feedback log). Prefer `log_error` over ad-hoc
   `logging.error` so failures are actually reviewable in **Settings →
   Diagnostics**.

| Path | Purpose |
|------|---------|
| `backend/main.py` | All FastAPI routes; `/feedback`, `/measurement-feedback`, `/capture-frame`, `/report/{job_id}`, `/sessions*`, `/client-error`, `/errors`; global `@app.exception_handler(Exception)` |
| `backend/feedback.py` | JSONL schema + `save_feedback` / `save_measurement_feedback`; constants `CHECKBOX_KEYS`, `MEASUREMENT_CHECKBOX_KEYS`, `METRIC_RATINGS`, `OVERALL_MEASUREMENT_LABELS`; `APP_VERSION` |
| `backend/errors.py` | Centralized append-only error log (`output/error_log.jsonl`); `log_error`, `recent_errors`; field caps + `_safe_context` |
| `backend/session.py` | Practice Sessions store + sport-agnostic `summarize_session` (averages + first-vs-last trends) |
| `backend/segmenter.py` | Multi-rep attempt detection (smoothing + local maxima + NMS); `suggest_segments`, `events_to_windows` |
| `backend/test_session.py` | Self-contained tests for session + segmenter (`python test_session.py`) |
| `backend/report.py` | `render_report(... expert=False)` HTML template; captured frames render as `<img class='fb-frame'>` inside fb-card / mfb-card |
| `backend/overlay.py` | `_draw_skeleton()` (alpha-blended) + H.264 re-encode pipeline |
| `frontend/app.js` | `currentJob` global; `captureFrame(prefix)`, `submitFeedback()`, `submitMeasurementFeedback()`, `setProgress()` (also writes `--pct` to `#progressScene`), `_refreshExpertVisibility()`, settings/tips/onboarding helpers (`openSettings`, `closeSettings`, `openRecordingTips`, `closeRecordingTips`, `acceptOnboardingCustomize`, `skipOnboarding`), player profile helpers (`clearPlayerProfile`, `startFresh`), sessions helpers (`showSessions`, `openSessionDetail`), error reporter (`reportClientError`) + Diagnostics (`loadErrors`) |
| `frontend/index.html` | Markup ids: `settingsOverlay`, `tipsOverlay`, `onboardingOverlay`, `playerProfile`, `settingsBtn`, `profileAccent`, `profileHandOverride`, `tipsVideo`, `overlayVideo`, `progressScene`, `measuredCount`, `priorityLabel`, `filenameLabel`, `fbFrameUrl`, `fbFramePreview`, `mfbFrameUrl`, `mfbFramePreview`, `mfbOverall`, `mfbMetricGrid`, `mfbCheckGrid`, `sessionsSection`, `diagnostics`, `errorList` |
| `frontend/style.css` | Upload layout tokens (`--page-width`, `--page-width-wide`), `.app-modal`, `.app-dialog`, `.icon-btn`, `.hero-art-shell`, `.profile-card`, `.scene`, `.scene-character`, `.scene-puck`, `@keyframes puck-shoot`, `.frame-preview`, `.fb-frame`, `.session-*`, `.diag-card`, `.err-row` |

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
