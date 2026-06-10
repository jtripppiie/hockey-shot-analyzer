# Agent Guide — Hockey Shot Analyzer

Fast-start context for AI coding sessions. Read this first; the architecture
decisions below are intentional and should not be undone without discussion.

## Current state

- **Last shipped features:**
  1. **Compact dashboard upload + results UI (June 2026)** — light upload and coach-report results screens, mirrored with `pole-vault-analyzer` so the apps feel like the same tool family. Headings/body now use `Nunito Sans`; upload uses a wide 1420px three-column desktop layout with image-led sport art on the left, a compact combined upload/YouTube card in the center, and one-column guidance cards on the right. The old on-page filming tips are hidden from the upload flow; the header has **History**, an icon-only **Settings** gear, and **Recording Tips**. Settings is available from upload/progress/results/history topbars; desktop opens a modal, mobile uses the same overlay as a full-screen page. Settings contains Player Profile local-only personalization (`profileAccent`, `profileHandOverride`) under `hockeyPlayerProfile.v1`. Name, age, position, and custom photo upload are intentionally not collected. The shooting-hand override (`profileHandOverride`: `auto`/`left`/`right`) is sent with every analyze request (`_submitAnalyze` injects `hand_override` from `hockeyPlayerProfile.v1`); when set to left/right it forces the shooting hand in `compute_metrics(..., hand_override=...)` instead of auto-detecting from wrist motion, and the result's `quality_report.dominant_hand_source` becomes `"override"` (otherwise `"auto"`). The `/analyze`, `/analyze-youtube`, and `/analyze-segment` routes all accept the optional `hand_override` form field. First launch shows `onboardingOverlay` once (`hockeyOnboardingSeen.v1`) with Customize/Skip. `Recording Tips` opens an embedded YouTube search iframe in `tipsOverlay` and clears `iframe.src` on close so it restarts each time. Results screen has a focused hero with banded score label (`Elite Form` / `Solid Foundation` / `Building Up` / `Early Days` / `Just Starting`), one-line tagline derived from strongest+weakest measured metric, a compact readout (`measuredCount`, `priorityLabel`, `filenameLabel`), phase timeline (Setup→Load→Release→Follow-Through), and a `metric-grid` sorted weakest-first with the top opportunity flagged via a `metric-priority` orange pill. Coach’s Report split into strengths / focus / drills. Progress scene is an ice-rink palette with a helmeted player + 3 flying pucks (`puck-fly` keyframe). Tokens live under `:root` (`--d-*` dark palette, `--l-*` light palette, accents, `--font-head`, `--font-body`, `--page-width`, `--page-width-wide`). **Hard rule:** all existing element IDs (`overallNum`, `sub-power`, `sub-technique`, `sub-timing`, `powerNum`, `techniqueNum`, `timingNum`, `metricGrid`, `coachStrengths`, etc.) are preserved verbatim — do not rename without grepping `app.js` first.
  2. Expert Feedback Mode (orange panel, desktop-only, `Ctrl/Cmd+Shift+F`).
  3. Measurement Feedback (blue sub-panel, scores the *analyzer*, not the athlete).
  4. Browser-side Frame Capture (📸 button → `/capture-frame` → JPEG attached to JSONL row → embedded in Expert report).
  5. Athletic progress scene (rink + player + pucks animation) replacing the plain spinner during analysis.
  6. Lighter, semi-transparent pose overlay (smaller dots, `cv2.addWeighted` blend at 0.65) so the underlying video shows through the skeleton.
  7. **Practice Sessions** — group multiple analyzed clips into a named session and see averages + first-vs-last trends per metric. Backend `backend/session.py` (sport-agnostic `summarize_session`, JSON-per-session under `output/session_*.json`); UI in the **Sessions** topbar button (`sessionsSection`). Session reports render via `report.py::render_session_report`.
  8. **Multi-rep segmenter, wired into the UI** (`backend/segmenter.py` + routes) — smoothing + true local-maxima + non-max suppression to suggest attempt windows in a multi-shot clip (replaces the old greedy peak-pick). Exposed via `POST /suggest-segments` (caches the source as `uploads/{seg_job}_multi.*`, returns windows in seconds + confidence) and `POST /analyze-segment` (frame-accurate ffmpeg trim of one window via `_trim_clip`, then `_analyze_video`). Frontend: opt-in **“Find attempts →”** on upload → `findSegments()` → **Suggested Attempts** screen (`segmentsSection`, `renderSegments()`) → per-attempt `analyzeSegment()`. The wrist-speed release spike is sharp (the peak sits ~20+ MAD above the median, unlike the pole-vault apex at ~2 MAD), so `PEAK_K=4.0` holds without an absolute-prominence floor; validated by `test_segmenter_detects_shots_amid_stickhandling` (a noisy multi-shot fixture). Do **not** copy the pole repo's lower `PEAK_K`/`MIN_PROMINENCE` here — it would invite false peaks from stickhandling.
  9. **Centralized error logging** — append-only `output/error_log.jsonl` via `backend/errors.py` (`log_error` / `recent_errors` / `clear_errors`). A global `@app.exception_handler(Exception)` catches escaped route errors; the browser forwards uncaught JS errors to `POST /client-error`; `GET /errors` returns the newest entries; `POST /errors/clear` wipes the log. Viewable in-app under **Settings → Diagnostics** (`#diagnostics`, `loadErrors()`), with a confirm-guarded **Clear log** button (`clearErrors()`).
  10. **Self-contained tests** (`backend/test_session.py`, `backend/test_errors.py`, `backend/test_segment.py`) — runnable via plain `python test_*.py` (no pytest/httpx needed); cover session round-trip, summary averages/trends, segmenter peak detection, the error log (`clear_errors` + the opt-in `ERROR_LOG_MAX_LINES` cap), and the `_trim_clip` / suggest→trim segment round-trip.
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
   untrusted and length-capped in `errors.py`. The error log is append-only and
   not rotated by default, but rotation is opt-in: set `ERROR_LOG_MAX_LINES` to
   a positive integer and `errors._enforce_cap` trims to the newest N entries
   after each write (the feedback log is never capped — it holds human
   corrections). Prefer `log_error` over ad-hoc
   `logging.error` so failures are actually reviewable in **Settings →
   Diagnostics**.

11. **Wrong-sport / not-a-shot guard** — `compute_metrics` checks that a clip
   actually shows a *grounded* hockey shot via two signals in
   `backend/metrics.py`: `_hip_rise(valid)` (peak hip rise above median — near
   zero for a planted shooter, large for a jump/vault) and
   `_wrist_travel(valid, dom)` (dominant-wrist span — large for a real shot,
   near zero for a static clip). `quality_report["shot_check"]` carries
   `{hip_rise, wrist_travel, looks_like_shot, reject}`. Thresholds:
   `SHOT_GROUNDED_WARN=0.14` / `SHOT_AIRBORNE_REJECT=0.20` (hips) and
   `SHOT_MOTION_WARN=0.18` / `SHOT_MOTION_REJECT=0.06` (wrist). Outside the warn
   band, a prominent "This doesn't look like a hockey shot…" message is
   **inserted at the front** of `quality_report["warnings"]` (still scored).
   When `reject` is set (airborne *or* too static), `_analyze_video` raises
   `HTTPException(422, "not_a_hockey_shot")` (shared by `/analyze`,
   `/analyze-youtube`, `/analyze-segment`); the frontend maps it via
   `ERROR_MESSAGES["not_a_hockey_shot"]`. This mirrors the pole-vault repo's
   `sport_check`, but uses grounded-shot signals rather than vault rise.
   Calibrated on real shot footage (hip rise ~0.05, wrist travel ~0.56) vs a
   pole-vault clip (rise ~0.25, travel ~1.14); thresholds are conservative.
   Regression tests: `test_shot_check_passes_grounded_shot` /
   `test_shot_check_rejects_airborne_clip` /
   `test_shot_check_rejects_static_clip` in `test_session.py`.

12. **Continuity / scene-cut guard** — A montage clip (multiple scenes spliced
   together) teleports the whole body between cuts, which can fake a hip rise
   and break phase detection — and was the one failure mode real uploads kept
   hitting (a 19s slap-shot montage false-accepted on the *vault* side because a
   cut faked a 0.42 "rise"). `_scene_cuts(frames)` in `backend/metrics.py`
   measures the per-frame jump of the body centre (hip midpoint) in **torso
   lengths** (shoulder-mid → hip-mid), which is scale/zoom invariant, and counts
   jumps above `CUT_JUMP=1.0` as cuts (skipping frame-index gaps, which are
   tracking dropouts not cuts). `quality_report["continuity_check"]` carries
   `{cut_count, max_jump, looks_continuous}`. If `cut_count >= 1`, a "This clip
   looks like it contains camera cuts…" warning is **inserted at the front** of
   `warnings`. **WARN only, never a hard reject** — with only 3 real samples a
   fast legit pan could spike, so we tell the user rather than block. Calibrated
   on real continuous footage (max jump ≤0.55 torso-lengths/frame) vs a montage
   (1.2+ at each cut) — `CUT_JUMP=1.0` separates with ~2× margin. The helper is
   sport-agnostic and mirrored verbatim in the pole repo. Regression tests:
   `test_continuity_passes_continuous_clip` /
   `test_continuity_flags_montage_cut` in `test_session.py`.

13. **Real-footage regression corpus** — The guards above (shot/sport,
   continuity) were calibrated against real YouTube clips; to keep them from
   silently regressing, those clips are frozen as gzipped landmark fixtures in
   `backend/fixtures/*.landmarks.json.gz` (pose already run, so no MediaPipe at
   test time) and replayed through `compute_metrics` by
   `backend/test_real_clips.py`. Fixture schema:
   `{clip, fps, n_frames, detection_rate, frames:[{frame, landmarks}]}` (coords
   rounded 4dp, world coords included). Each clip has an `EXPECT` row asserting
   its guard classification (e.g. `montage_slap` → shot=False, continuous=False;
   `hk_real_brady` → shot=True, continuous=True). The same five fixtures live in
   both repos with sport-appropriate expectations — notably
   `test_continuity_catches_montage_sport_guard_misses` on the pole side proves
   the two guards are complementary (the montage fools `sport_check` but the
   continuity guard still catches it). Fixtures are **git-tracked** (not ignored)
   so the corpus travels with the code; run `python test_real_clips.py`.

14. **False-reject telemetry** — To tell genuine non-shots from over-tight
   thresholds, every rejection path in `_analyze_video` logs an **`info`**-level
   entry via `log_error` (from `backend/errors.py`) *before* raising the 422,
   capturing the signal values behind the decision: `reject:no_body_detected` /
   `reject:poor_detection` (with `detection_rate`), `reject:not_a_hockey_shot`
   (with the full `shot_check` + `continuity_check`). Accepted-but-flagged clips
   log `warn:camera_cuts` with the `continuity_check`. These are `severity:info`
   (not errors), share the append-only `output/error_log.jsonl`, and surface in
   **Settings → Diagnostics** — so a stream of rejects a real user expected to
   score becomes visible without changing behaviour. Mirrored in the pole repo
   (`reject:not_a_pole_vault`, `sport_check`).

15. **Pixel scene-cut pre-check** — An independent, pose-free corroboration of
   the continuity guard (#12). `scene_cut_precheck(video_path)` in
   `backend/pose.py` decodes the raw clip at 64×64 grayscale and flags frames
   whose frame-to-frame mean abs-difference is both ≥ `PRECHECK_MAD_K=14` MADs
   above the clip's median *and* ≥ `PRECHECK_ABS_FLOOR=0.04` (absolute floor so
   pixel noise on a near-static clip can't manufacture cuts). `_analyze_video`
   runs it on the upload and passes `pixel_cuts` into `compute_metrics` as
   `precheck_cuts`; `looks_continuous` now requires **both** detectors clear
   (`cut_count == 0 and precheck_cuts == 0`), and `continuity_check` gains a
   `pixel_cut_count` field. The value: it still catches splices when pose
   tracking drops out *at* the cut (a montage drops ~28% of frames) — verified
   live, where the pixel check found **3** cuts on a montage the pose detector
   scored at 2. Calibrated on real footage (continuous clips peak ~12 MAD, a
   montage spikes ~68 MAD). **WARN only.** Sport-agnostic, mirrored verbatim in
   the pole repo. Regression tests: `test_precheck_flags_montage_cut` /
   `test_precheck_ignores_continuous_motion` in `test_segment.py`.

16. **Bounded disk: stale-upload sweep + opt-in history cap** — `output/` and
   `uploads/` grew without bound (every analyzed clip leaves an overlay video,
   the bulk of disk use). Two retention helpers in `backend/main.py`:
   (a) `_sweep_old_uploads(max_age_s=UPLOAD_MAX_AGE_S)` deletes any file in
   `uploads/` older than `UPLOAD_MAX_AGE_S` (env, default 3600s). Uploads are
   transient — `/analyze`'s `finally` deletes each one, the render thread
   removes its `_render.mp4` copy, multi-rep sources are short-lived — so
   anything older than an hour is a crash orphan (a live request's files are
   seconds old, never racing the sweep). This **generalizes the old
   `_sweep_old_multi`** (which only caught `*_multi.*`); the `/suggest-segments`
   call site now calls `_sweep_old_uploads()`. (b) `_enforce_history_cap(
   max_entries=HISTORY_MAX_ENTRIES)` keeps only the newest N history rows and
   deletes the pruned jobs' output artifacts via the new `_delete_job_artifacts(
   job_id)` (sanitized-id glob `{job}_*`, which also catches `_capture_*.jpg`
   frames the old delete route missed). **Off by default** (`HISTORY_MAX_ENTRIES`
   <= 0 → unlimited, no behavior change for existing deployments), mirroring the
   `ERROR_LOG_MAX_LINES` opt-in pattern. Both run once at boot via an
   `@app.on_event("startup")` hook (`_startup_cleanup`, info-logs swept count to
   Diagnostics); the cap also runs after each `_append_history`. Session reports
   already tolerate missing job files (`if jf.exists()`), so pruning is safe.
   `DELETE /history/{job_id}` now also routes through `_delete_job_artifacts`.
   Sport-agnostic, mirrored verbatim in the pole repo. Regression tests in
   `backend/test_cleanup.py` (`python test_cleanup.py`).

17. **Upload size cap (DoS guard)** — `/analyze` and `/suggest-segments` used to
   stream the whole upload to disk with `shutil.copyfileobj` and *no* size
   limit; the duration guard in `_analyze_video` only fires *after* a full
   upload + pose run, so a multi-GB file could exhaust disk/memory first. Two
   layers now cap it, both keyed off `MAX_UPLOAD_BYTES` (env, default 500 MB; a
   60s phone clip is well under this; set `0` to disable): (a) an
   `@app.middleware("http")` (`_limit_upload_size`) early-rejects any POST whose
   `Content-Length` exceeds the cap with `413 {"detail":"file_too_large"}`,
   before the body is spooled; (b) `_save_upload(file, dest, max_bytes=None)`
   streams the upload in 1 MB chunks and is the **backstop** when the header is
   absent or lies — on overflow it deletes the partial file and raises
   `HTTPException(413, "file_too_large")`. Both `/analyze` and
   `/suggest-segments` now call `_save_upload` instead of `shutil.copyfileobj`.
   The frontend maps `file_too_large` via `ERROR_MESSAGES`. **Default 500 MB is
   deliberately generous** so legit 1080p/4K clips aren't rejected — the goal is
   to stop pathological uploads, not to be strict. Sport-agnostic, mirrored
   verbatim in the pole repo. Regression tests: `test_save_upload_*` in
   `backend/test_cleanup.py`.

18. **Feedback-driven calibration ("training")** — The analyzer is heuristic
   (joint-angle threshold bands → weighted power/technique/timing → overall), so
   "training" is a **calibration loop**, not a neural retrain. Expert Feedback
   Mode + Measurement Feedback already capture corrections in
   `output/feedback_log.jsonl` (`ai_score` vs `human_score`, `score_delta`,
   per-metric good/bad ratings), but nothing read them back. `backend/training.py`
   closes the loop with **pure, read-only** functions: `fit_linear_calibration(
   pairs)` least-squares-fits `human ≈ a·ai + b` over (ai_score, human_score)
   pairs (returns `{a, b, n, mae_before, mae_after, improvement, correlation}`,
   or `None` when <2 points or no x-spread), and `build_calibration_report(
   records, min_samples=CALIBRATION_MIN_SAMPLES)` returns a `{performance,
   measurement}` report: AI bias (mean `human-ai`), MAE/RMSE, correlation, the
   fitted correction, `ai_score_too_high/low` checkbox counts, plus per-metric
   reliability from measurement feedback (`worst_metric` by bad-rate). A
   **readiness gate** (`CALIBRATION_MIN_SAMPLES`, env, default 12) reports "need
   N more reviews" rather than a noisy fit. Exposed via `GET /training/report`
   (reads `feedback_mod.all_feedback`); surfaced in **Settings → Training &
   Calibration** (`#training`, `loadTraining()` → `_renderTraining()`): a
   reviews-progress bar, bias/error/agreement stat tiles, the fitted-correction
   line, expert flags, and least-trusted metric. **Opt-in apply:** once the
   readiness gate clears, `POST /training/apply` fits the correction and
   persists it to `output/calibration.json` (`{enabled, a, b, n, mae_before,
   mae_after, correlation, fitted_at}` via `training.save_calibration`);
   `_analyze_video` then loads it once per analysis and routes the summary
   through `apply_to_summary(summary, calib)` — an affine `a·score+b` clamped to
   0–100, applied to overall + every sub-score so `overall` stays the
   weighted-avg of the subs (raw scores stashed under `summary["raw"]`,
   `summary["calibrated"]=True`). This propagates to the history CSV, job JSON,
   and the returned JSON (all read from `result["summary"]`). `POST
   /training/revert` deletes the file (`clear_calibration`) and returns to raw
   scoring; `GET /training/report` includes the live state under `applied`. The
   UI renders a green "Calibration active" banner + Revert button when applied,
   and an "Apply this correction" button when ready. Sport-agnostic, mirrored
   verbatim in the pole repo. Tests: `backend/test_training.py`
   (`python test_training.py`).

19. **Batch-eval accuracy harness** — The guards (#11/#12/#15) and the heuristic
   scores were calibrated on a handful of clips; nothing measured the
   false-reject / false-accept rate across a realistic spread. `backend/
   batch_eval.py` closes that evidence gap: point it at a folder of clips
   (`python batch_eval.py CLIPS_DIR [--manifest m.csv] [--out report.csv]`) and
   it runs each through the **real** pipeline (pose → `scene_cut_precheck` →
   `compute_metrics`) **minus the overlay render**, writing one CSV row per clip
   with the accept/reject decision, the signals behind it (`detection_rate`,
   `shot_check`, `continuity_check`), and the scores. The decision logic lives in
   a pure, unit-tested `classify_clip(...)` that mirrors `_analyze_video`'s
   gates **exactly** (frame/duration/readable → detection 0.1/0.4 → metrics →
   `shot_check.reject` → continuity warn) — if you change a gate in `main.py`,
   change it here too. An optional manifest (`file,expect,expect_continuous`;
   `expect ∈ {shot, not_shot}`) makes `summarize_rows` compute shot-guard
   confusion (false-reject/accept rates, accuracy) and continuity accuracy, with
   the offending filenames listed. The pure core (`classify_clip`,
   `summarize_rows`, `_guard_accuracy`) needs no MediaPipe/OpenCV — heavy imports
   are lazy inside `evaluate_clip` — so `test_batch_eval.py` runs everywhere and
   also **replays the frozen real-footage fixtures** through
   `compute_metrics + classify_clip` to prove the harness's accept/reject matches
   the production guards. Sport-mirrored to the pole repo (`sport_check` /
   `looks_like_vault` / `vault_rise`, reject `not_a_pole_vault`, `expect ∈
   {vault, not_vault}`; the montage is *accepted-with-cut-warning* there, since
   the vault sport guard doesn't catch it). Tests: `backend/test_batch_eval.py`
   (`python test_batch_eval.py`).

| Path | Purpose |
|------|---------|
| `backend/main.py` | All FastAPI routes; `/feedback`, `/measurement-feedback`, `/capture-frame`, `/report/{job_id}`, `/sessions*`, `/suggest-segments`, `/analyze-segment`, `/client-error`, `/errors`, `/errors/clear`, `/training/report`; `_save_upload` / `_trim_clip` / `_sweep_old_uploads` / `_enforce_history_cap` / `_delete_job_artifacts` helpers; `_limit_upload_size` middleware; `@app.on_event("startup")` cleanup; global `@app.exception_handler(Exception)` |
| `backend/feedback.py` | JSONL schema + `save_feedback` / `save_measurement_feedback`; constants `CHECKBOX_KEYS`, `MEASUREMENT_CHECKBOX_KEYS`, `METRIC_RATINGS`, `OVERALL_MEASUREMENT_LABELS`; `APP_VERSION` |
| `backend/errors.py` | Centralized append-only error log (`output/error_log.jsonl`); `log_error`, `recent_errors`; field caps + `_safe_context` |
| `backend/session.py` | Practice Sessions store + sport-agnostic `summarize_session` (averages + first-vs-last trends) |
| `backend/segmenter.py` | Multi-rep attempt detection (smoothing + local maxima + NMS); `suggest_segments`, `events_to_windows`; surfaced via `/suggest-segments` + `/analyze-segment` |
| `backend/training.py` | Feedback-driven calibration (pure/read-only): `fit_linear_calibration`, `build_calibration_report`; surfaced via `GET /training/report` + Settings → Training & Calibration |
| `backend/batch_eval.py` | Accuracy harness: runs a clip folder through the real pipeline (no render) → CSV of decisions+signals+scores; pure `classify_clip`/`summarize_rows` + manifest-based guard confusion (`python batch_eval.py CLIPS_DIR`) |
| `backend/test_session.py` | Self-contained tests for session + segmenter (`python test_session.py`) |
| `backend/test_errors.py` | Self-contained tests for the error log: `clear_errors`, `recent_errors`, opt-in `ERROR_LOG_MAX_LINES` cap (`python test_errors.py`) |
| `backend/test_segment.py` | Self-contained tests for `_trim_clip` + suggest→trim round-trip + `scene_cut_precheck` (needs ffmpeg; `python test_segment.py`) |
| `backend/test_cleanup.py` | Self-contained tests for storage retention: `_sweep_old_uploads`, `_enforce_history_cap`, `_delete_job_artifacts`, plus the `_save_upload` size cap (`python test_cleanup.py`) |
| `backend/test_training.py` | Self-contained tests for calibration: `fit_linear_calibration` recovery/bias, readiness gate, per-metric flags (`python test_training.py`) || `backend/test_real_clips.py` | Replays frozen real-footage fixtures through `compute_metrics`, asserting guard classifications (`python test_real_clips.py`) |
| `backend/test_batch_eval.py` | Self-contained tests for the accuracy harness: `classify_clip` gates, `summarize_rows`/guard-confusion, + fixture replay proving harness matches production guards (`python test_batch_eval.py`) |
| `backend/fixtures/*.landmarks.json.gz` | Git-tracked gzipped landmark fixtures (real YouTube clips, pose pre-run) backing `test_real_clips.py` |
| `backend/report.py` | `render_report(... expert=False)` HTML template; captured frames render as `<img class='fb-frame'>` inside fb-card / mfb-card |
| `backend/overlay.py` | `_draw_skeleton()` (alpha-blended) + H.264 re-encode pipeline |
... `currentJob` global; `captureFrame(prefix)`, `submitFeedback()`, `submitMeasurementFeedback()`, `setProgress()` (also writes `--pct` to `#progressScene`), `_refreshExpertVisibility()`, settings/tips/onboarding helpers (`openSettings`, `closeSettings`, `openRecordingTips`, `closeRecordingTips`, `acceptOnboardingCustomize`, `skipOnboarding`), player profile helpers (`clearPlayerProfile`, `startFresh`), sessions helpers (`showSessions`, `openSessionDetail`), segmenter helpers (`findSegments`, `renderSegments`, `analyzeSegment`), error reporter (`reportClientError`) + Diagnostics (`loadErrors`, `clearErrors`) |
| `frontend/index.html` | Markup ids: `settingsOverlay`, `tipsOverlay`, `onboardingOverlay`, `playerProfile`, `settingsBtn`, `profileAccent`, `profileHandOverride`, `tipsVideo`, `overlayVideo`, `progressScene`, `measuredCount`, `priorityLabel`, `filenameLabel`, `fbFrameUrl`, `fbFramePreview`, `mfbFrameUrl`, `mfbFramePreview`, `mfbOverall`, `mfbMetricGrid`, `mfbCheckGrid`, `sessionsSection`, `segmentsSection`, `segFileInput`, `segmentsList`, `segmentsLede`, `diagnostics`, `errorList` |
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
