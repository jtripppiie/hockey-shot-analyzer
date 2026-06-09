# Roadmap — Live Capture → Auto-Splice → Session Report

Status: planning. This document captures the agreed direction for evolving the
analyzer from "upload one pre-trimmed clip" to "plug a laptop in, stream video,
auto-detect each rep (slap shot / vault), and produce a session report."

Applies to both sibling apps (`hockey-shot-analyzer`, `pole-vault-analyzer`),
which share structure and patterns.

---

## Vision

```
Laptop + camera (live stream)
  → Rep detector (find each shot / jump)
  → Auto-splice into N clips
  → Existing analyzer (per clip: pose → metrics → score)
  → Session report (N attempts + trends)
```

The user plugs a laptop into a camera, records a practice session, and the app
segments the stream into individual attempts, scores each with the existing
analyzer, and aggregates them into one session report with per-rep scores and
trends.

---

## What already exists (reused as-is)

- **Per-rep analysis** — `pose.run_pose_detection` → `metrics.compute_metrics`
  → scores. This is exactly the "analyze one clip" box and works on any trimmed
  segment.
- **Report rendering** — `report.render_report` produces a printable per-job
  report (HTML, print-to-PDF).
- **Phase detection** — `metrics._detect_phases` (Setup → Load → Release →
  Follow-Through) already finds the shot moment *within* a clip. The same signal
  is most of what's needed to find shots within a longer stream.
- **Background overlay render** — already decoupled from scoring; reuses analysis
  landmarks (no second detection pass).

## What is genuinely new

1. **Capture** (easy) — browser `getUserMedia` + `MediaRecorder` for the laptop
   webcam. No backend change required for v1: record → POST the blob to the
   existing `/analyze`.
2. **Auto-segmentation** (the real new work) — detect "a rep just happened" in a
   continuous stream. Approach: run pose on the whole stream, derive a motion
   signal (e.g. wrist velocity spikes for slap shots; takeoff/peak pattern for
   vault), find rep boundaries via windowing + peak detection (conceptually
   similar to the existing de-spike logic in `_detect_phases`). Each detected
   event → trim a window (e.g. −1.5s to +1.5s around release) → feed the existing
   analyzer.
3. **Session / batch report** (moderate) — a new report shape: N attempts per
   session, per-attempt scores, plus trend lines (e.g. "release timing improved
   across reps 1→8"). Per-attempt rendering already exists; this is an
   aggregation layer.

---

## Reality checks (constraints to respect)

- **Near-live, not real-time.** Scoring is inference-bound (~8s/clip on CPU, no
  GPU in WSL). Realistic v1 is **record session → segment → batch-analyze →
  report**, NOT instant per-rep feedback during the stream.
- **Segmentation accuracy is critical.** A missed or mis-cut rep = a bad/missing
  report row. Per the project's hard rule (**accuracy > speed**), the splicer
  must be conservative and v1 should allow a manual confirm/adjust step for cut
  points.
- **Hardware unlocks live.** "Plug into a laptop" with a real GPU is exactly
  where the GPU delegate (which fails in WSL: `GL_INVALID_ENUM`) would finally
  pay off — for throughput and for getting closer to real-time.
- **Validate any detection-path change against actual metric VALUES**, not just
  detection counts. (A prior 1280px detector-input downscale was reverted after
  it shifted real-clip scores — timing 35→0, weight_transfer None→100.)

---

## Build order

### Phase 1 — In-app camera capture (foundation, low risk)
- Browser `getUserMedia` + `MediaRecorder` in `frontend/`.
- Record → produce a video blob → POST to existing `/analyze`.
- No backend change for v1.
- Deliverable: user can record a single attempt in-app instead of selecting a
  file. Unblocks everything below.

### Phase 2 — Manual multi-rep session
- Record a longer session; let the user mark cut points (manual trim UI).
- Analyze each segment via the existing analyzer.
- New **session report**: list of attempts + per-attempt scores.
- Proves the batch-report path WITHOUT trusting auto-detection yet.

### Phase 3 — Auto-segmentation
- Run pose over the full stream; derive the motion signal and auto-suggest cut
  points (wrist-velocity peaks for hockey; takeoff/peak for vault).
- User confirms/adjusts suggested cuts (keeps a human in the loop for accuracy).
- Feed confirmed segments to the analyzer → session report.

### Phase 4 — Toward live (needs real GPU hardware)
- Wire and test the MediaPipe GPU delegate on the deployment/laptop GPU.
- Stream-time or near-stream-time scoring; incremental report updates.

---

## Open questions / decisions to revisit

- Session report format: same printable HTML pattern as `report.py`, extended to
  multiple attempts + trend charts? (Likely yes, to stay dependency-free.)
- Where to store a multi-rep session (currently one job = one upload). Need a
  session id grouping N job ids.
- Camera/recording UX: countdown, framing guide, max session length, storage of
  raw session video (large) vs. discard after segmentation.
- Segmentation tuning + validation set: need several real multi-rep clips at
  different resolutions/angles to tune and validate the splicer conservatively.

---

## Related notes

- Architecture decisions and current state live in `AGENTS.md` (read first).
- The two apps are mirrored; build features in lockstep where the slice applies
  to both.
