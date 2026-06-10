# Next Steps — Hockey Shot Analyzer

Status as of 2026-06-10. The app is ~90–95% to a shippable v1. Core pipeline,
UI, robustness guards, feedback→calibration loop, diagnostics, and tests are all
in place and green. What remains is mostly *evidence* and a few small polish
items — not new features.

## ✅ Verified working (2026-06-10)

- All 14 backend test suites pass (both repos): `session`, `errors`, `segment`,
  `cleanup`, `training`, `real_clips`, `batch_eval`.
- Both servers boot clean (36 routes) and return `200` on `/`, `/errors`,
  `/history`.
- `batch_eval.py` runs the full pose → metrics → guard pipeline end-to-end on a
  folder of clips and emits a real accuracy report.
- Guard logic validated 6/6 on the clean labeled landmark fixtures
  (`backend/fixtures/*.landmarks.json.gz` via `test_real_clips.py`).

## 🎯 Highest-value next step — measured accuracy on a real corpus

This is the one real gap before calling it "final." The guards (#11/#12/#15 in
`AGENTS.md`) and the heuristic score bands were calibrated on a handful of clips.
We need true false-reject / false-accept rates across a realistic spread.

**Do this:**

1. Collect ~20–30 **original** clips (NOT the overlay re-renders in `output/` —
   those have the skeleton baked in and degrade pose detection). Include:
   - ~20 real hockey shots (varied angle, lighting, handedness).
   - A few deliberate negatives: a non-shot (skating/stickhandling only), a
     wrong-sport clip, a montage with cuts, a too-short (<10 frame) clip.
2. Put them in an `eval/clips/` folder.
3. Label them in `eval/manifest.csv` (format is documented in
   `backend/batch_eval.py`):
   ```csv
   file,expect,expect_continuous
   real_shot_01.mp4,shot,yes
   stickhandling_only.mp4,not_shot,yes
   montage.mp4,not_shot,no
   ```
   - `expect` ∈ `{shot, not_shot}` — should the clip be accepted?
   - `expect_continuous` ∈ `{yes, no}` — single continuous take?
4. Run:
   ```bash
   cd backend && source ../.venv/bin/activate
   python batch_eval.py ../eval/clips --manifest ../eval/manifest.csv --out ../eval/report.csv
   ```
5. Read the printed summary: shot-guard accuracy, false-reject/false-accept
   rates (with the offending filenames), continuity accuracy, and the score
   distribution.
6. **Only then** tune any guard threshold that shows a bad rate. Thresholds live
   in `backend/metrics.py` (`SHOT_*`, `CUT_JUMP`) and `backend/pose.py`
   (`PRECHECK_*`). Do not tune against the `output/` overlay clips — those
   numbers are noisy artifacts, not ground truth.

## 🔧 Smaller polish (optional, low-risk)

- **Heuristic scoring depth** — the calibration loop only adjusts overall/sub
  scores affinely, not per-metric threshold bands. Fine for v1; revisit if the
  corpus shows a metric is systematically off.
- **Stable public URL** — the Cloudflare Quick Tunnel name changes every
  restart. For a real demo/deploy, use a named tunnel.
- **Retention caps are opt-in** — `HISTORY_MAX_ENTRIES` and `ERROR_LOG_MAX_LINES`
  default to unlimited. Set them in the deploy env if disk is a concern.

## 📌 Working agreements (so this stays consistent)

- Mirror every cross-app change verbatim in `pole-vault-analyzer` except
  sport-specific values (colors, copy, asset names, localStorage keys).
- Edit `frontend/*` directly (no build step); verify in a cache-busted browser.
- Preserve all existing element IDs — grep `app.js` before renaming.
- Never `pkill -f uvicorn` globally; use a port-specific pattern.
