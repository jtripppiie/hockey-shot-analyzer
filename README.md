# 🏒 Hockey Shot Analyzer

Upload a video of one of your hockey shots. The app draws a stick-figure skeleton over you and gives you a score (0–100) for power, technique, and timing — plus tips and drills to get better. **Built so a twelve-year-old can run it on their own laptop, change stuff, and share their version on GitHub.**

> 🥅 **New to coding? Start here:** jump straight to **[The Young Coder's Playbook](#-the-young-coders-playbook)** at the bottom — it explains *everything* (installing VS Code, every git command, undoing mistakes, changing colors and icons, how the scoring math works, adding your own features, and putting it on the internet) one slow shift at a time, with hockey analogies. You don't need to know anything yet. 🏒

---

## What you need before you start

**A laptop running one of these:**
- Windows 10/11 (with **WSL** — see the box below)
- macOS (any modern Mac)
- Linux (Ubuntu 22.04 or newer)

> **On Windows?** This app needs Linux tools. Open PowerShell **as Administrator** and run `wsl --install`, restart your computer, then open the new **"Ubuntu"** app from the Start menu. From now on, type all the commands in this README inside that Ubuntu window. ([Microsoft's WSL guide](https://learn.microsoft.com/en-us/windows/wsl/install) if you get stuck.)

**Free disk space:** about 2 GB.

**Internet:** the first time you run it, it downloads ~30 MB of stuff.

**Three programs.** Don't worry — `./run.sh` installs the last two for you. You only need to install the first one yourself:

| Program | What it does | How to check you have it | If you don't have it |
|---|---|---|---|
| **git** | Downloads code from GitHub | `git --version` | Linux/WSL: `sudo apt install git` · Mac: `brew install git` |
| **Python 3.10+** | Runs the analyzer | `python3 --version` | Linux/WSL: `sudo apt install python3 python3-venv python3-pip` · Mac: `brew install python@3.11` |
| **ffmpeg** | Re-encodes the video with the skeleton drawn on | `ffmpeg -version` | Linux/WSL: `sudo apt install ffmpeg` · Mac: `brew install ffmpeg` |

> "sudo" means "do this as an admin." It'll ask for your password the first time.

---

## Step 1 — Make your own copy on GitHub (a "fork")

A fork is **your own copy** of someone else's project. You can change it however you want without touching the original.

1. Make a GitHub account at https://github.com if you don't have one.
2. Go to https://github.com/jtripppiie/hockey-shot-analyzer
3. Click the **Fork** button (top right). Accept the defaults and click **Create fork**.
4. You now have a copy at `https://github.com/YOUR-USERNAME/hockey-shot-analyzer`. Keep that tab open — you'll need the URL in the next step.

---

## Step 2 — Download your fork to your computer ("clone")

Open a terminal (Ubuntu app on Windows, Terminal on Mac/Linux) and type:

```bash
cd ~
git clone https://github.com/YOUR-USERNAME/hockey-shot-analyzer.git
cd hockey-shot-analyzer
```

Replace `YOUR-USERNAME` with your actual GitHub username. You should now see a folder called `hockey-shot-analyzer` in your home directory.

> **First-time git setup** — git will eventually ask who you are. Run these once (use your real GitHub email):
> ```bash
> git config --global user.name "Your Name"
> git config --global user.email "you@example.com"
> ```

---

## Step 3 — Run it

```bash
./run.sh
```

The first time, this takes a few minutes. It will:
1. Install `ffmpeg` and a couple of graphics libraries (asks for your password once)
2. Make a `.venv/` folder with all the Python libraries it needs (see the full list below)
3. Download the pose-detection model (~6 MB)
4. Start the server

When you see `Uvicorn running on http://0.0.0.0:8000`, open a web browser and go to:

**http://localhost:8000**

Drop in a video of a hockey shot, or paste a YouTube link. Wait 10–30 seconds. Done.

**To stop it:** go back to the terminal and press **Ctrl+C**.

---

## How to film a good clip

The app will tell you when a clip is bad, but here's how to get full results every time:

- ✅ **Side-on:** phone perpendicular to where you're shooting (not behind you, not in front)
- ✅ **Camera at hip height:** not down at ice level, not up in the stands — extreme up/down angles warp every joint reading
- ✅ **Whole body in the picture:** head to skates, with a bit of space around you
- ✅ **Just one player:** no teammates skating through the shot
- ✅ **One shot per clip:** trim it down — load through follow-through is enough
- ✅ **Good light:** even rink lights or daylight, no silhouettes
- ✅ **Best quality:** 1080p at 60 fps if your phone can do it (720p at 30 fps is fine too)

Slightly off-axis is now much more forgiving than it used to be: as of the
3D-joint-angle update, joint angles (knee bend, body rotation) are computed
from MediaPipe's metric **world** coordinates rather than from the 2D image
projection, so a camera that's 10–20° off true side-on no longer flattens
the knee bend or inflates the rotation score. A true side-on shot is still
ideal, but it isn't make-or-break the way it once was.

The **Recording Tips** button opens side-view filming examples inside the app.
On desktop it opens as a modal; on mobile it uses a full-screen page-style view
with large touch targets. Closing and reopening it restarts the embedded video.

## 👤 Player Profile (optional)

The gear button opens **Player Profile** settings. On desktop it opens as a
modal; on mobile it behaves like a full-screen settings page. The panel is
local-only and stores accent color plus an optional shooting-hand override. The
override defaults to auto-detect and does not affect scoring yet; it is saved
locally for the next implementation slice.

Everything is optional. Skip the profile entirely and the analyzer behaves as
before. Click **Clear** in the profile panel to wipe the saved values, or
**Start Fresh** to clear local app settings/history and return to defaults.

---

## What it measures

| Metric | What it means |
|---|---|
| **Knee bend** | How deep you load on your shooting-side leg |
| **Hip rotation** | How far your hips rotate through the shot |
| **Shoulder rotation** | How far your shoulders rotate through the shot |
| **Weight transfer** | How much your hips slide from back to front leg |
| **Follow-through** | How high your hands finish |
| **Head stability** | Whether you keep your head still or jerk it |
| **Release timing** | How long load → release takes (in milliseconds) |

Each one gets a score 0–100 and a grade: `great`, `good`, `ok`, `needs work`, or `unmeasured`. You also get a coaching tip and a drill for every metric. The results quality banner shows analyzer confidence — **High**, **Moderate**, or **Limited** — based on measured metric coverage and camera/phase warnings.

**Big scores:** Power · Technique · Timing · Overall Shot Score.

---

## 🧑‍🏫 Expert Feedback Mode (desktop only)

A hidden mode that lets a coach, parent, or trainer **privately correct the AI's score** and record what really happened on the ice. The collected feedback is saved as clean training data so we can improve scoring rules — or train a better model — later. **The kid/player never sees any of this.**

### How to turn it on

On a desktop or laptop browser (with a real keyboard), press:

**`Ctrl + Shift + F`** &nbsp;(or `⌘ + Shift + F` on Mac)

You'll see a small orange `🧑‍🏫 Expert Mode ✕` badge appear, and an **Expert Feedback** panel will show up below the Coach's Report on the current results page. Press the shortcut again or click the badge to turn it off. Expert Mode is intentionally temporary: refresh, upload, loading, history, and settings all turn it off.

> **Desktop only by design.** The panel won't render on phones, tablets, or anything narrower than ~1024px / without a mouse. That's enforced both in JavaScript and CSS — even with "Request desktop site" on mobile, the form stays hidden.

If an upload or analysis error happens, the error panel always offers **Try Again**, **Refresh App**, and **Escape** so you can recover without getting trapped.

### What you fill in for each shot

- **Corrected overall score** (0–100 slider)
- **Shot quality**: Poor · Needs Work · Decent · Good · Excellent
- **13 checkboxes** — head dropped, knee drive strong/weak, weight transfer good/weak, follow-through good/short, blade-puck contact, balance issue, camera angle made AI unreliable, AI score too high/low, etc.
- **Coach notes** — a free-text box: *"what the AI missed"*
- **Reviewer name** (optional, e.g. *Coach Mike*, *Dad*)

### Where it saves

Every entry appends one line to:

```
output/feedback_log.jsonl
```

JSONL means: **one JSON object per line**, append-only. Each entry includes the AI's full scores + metrics + the human correction + a `score_delta`, the video metadata (fps, resolution, duration), a unique `feedback_id`, a timestamp, and the app version. **The same clip can receive multiple feedback entries** (coach + parent + trainer) — nothing is ever overwritten.

The file is `.gitignore`d so private feedback never ends up in your fork.

### Two report styles

Each analyzed clip can be exported as a printable HTML report (Ctrl+P → Save as PDF works on every browser):

- **Player report** — `/report/{job_id}` &nbsp; AI score, sub-scores, shot breakdown, coaching tips. **No feedback shown.**
- **Expert report** — `/report/{job_id}?expert=1` &nbsp; same plus all the Expert Feedback entries with AI-vs-human deltas and reviewer notes.

The expert panel has buttons for both after a shot is analyzed. Saved clips also
show the same report actions from **History** → open a clip.

### What "training" means here (and what it doesn't)

There's **no neural network retraining itself in the background.** The analyzer scores shots with fixed biomechanics rules (joint angles → power / technique / timing), so "training" it really means **calibrating** those scores against expert corrections — nudging the AI's number up or down until it lines up with what real coaches actually said. That whole loop lives in **Settings → Training & Calibration** and is walked through step-by-step in the **🎓 Training & Calibration** section further down. It only ever switches on when *you* click **Apply**, and you can **Revert** to the untouched scores at any moment. One coach's opinion ≠ ground truth — which is exactly why the loop refuses to offer a correction until it has collected a dozen reviews.

### Inspect the data later

```bash
# Count entries
wc -l output/feedback_log.jsonl

# Show all corrections where the AI overshot by more than 15 points
python3 -c "
import json
for line in open('output/feedback_log.jsonl'):
    r = json.loads(line)
    d = r.get('score_delta')
    if d is not None and d < -15:
        print(f'{r[\"clip_filename\"]:30}  AI={r[\"ai_score\"]:>3}  Human={r[\"human_score\"]:>3}  (delta {d:+d})  by {r[\"reviewer\"]}')
"

# Most-flagged AI failure modes
python3 -c "
import json, collections
c = collections.Counter()
for line in open('output/feedback_log.jsonl'):
    c.update(json.loads(line)['human_checkboxes'])
for k, n in c.most_common():
    print(f'{n:4}  {k}')
"
```

### 🛠️ Measurement Feedback (about the AI, not the player)

Underneath the Expert Feedback form is a second sub-section: **Measurement Feedback**. It answers a *different* question — not "how did the player shoot?" but "how well did the analyzer **measure** this shot?"

This is what gets saved (anonymously — no reviewer name):

- **Per-metric thumbs**: for every metric the AI computed (knee bend, hip rotation, shoulder rotation, weight transfer, follow-through, head stability, release timing), pick 👍 good / 👎 bad / ⊘ didn't measure / — skip.
- **Overall measurement quality**: Way off · Off · Roughly right · Good · Spot on.
- **Analyzer flags** (7 hockey-specific checkboxes): pose tracking lost the player, wrong release/load frame detected, camera angle made measurement unreliable, sub-scores don't match what I see, coaching tip irrelevant, analyzer worked well overall.
- **Optional note** about analyzer behaviour.

Measurement entries land in the **same** `output/feedback_log.jsonl` file but carry `"type": "measurement"` so you can filter cleanly:

```bash
# Per-metric thumbs-down rate across all measurement feedback:
python3 -c "
import json, collections
thumb = collections.Counter()
bad = collections.Counter()
for line in open('output/feedback_log.jsonl'):
    r = json.loads(line)
    if r.get('type') != 'measurement': continue
    for k, v in (r.get('metric_ratings') or {}).items():
        thumb[k] += 1
        if v == 'bad': bad[k] += 1
for k, n in thumb.most_common():
    print(f'{k:24} {bad[k]:>3}/{n:<3}  thumbs-down rate = {bad[k]/n:.0%}')
"
```

Measurement feedback also appears in the **Expert report** (blue panel under the orange Expert Feedback section). It does **not** appear in the player report.

New endpoints:

```
POST /measurement-feedback               Save one measurement-quality entry
GET  /measurement-feedback/{job_id}      List measurement entries for a clip
GET  /measurement-feedback               List all measurement entries
```

### 📸 Capture a frame with your feedback

Next to **Save feedback** (in both the orange and blue sub-sections) there's a **📸 Capture current frame** button. It grabs whatever frame the overlay video is paused on, sends the JPEG to the server, and attaches the resulting URL to the next feedback row you save.

Why this exists: when a coach writes "the AI marked release too early — see how the puck is already 3 feet off the blade," the screenshot proves it. Captured frames also render inside the Expert HTML report so a printed PDF carries the visual evidence.

How it works under the hood: the browser draws the current `<video>` frame onto a `<canvas>`, calls `canvas.toBlob()`, and POSTs it to `/capture-frame`. No server-side ffmpeg, no extra dependency. Files land in `output/{job_id}_capture_{timestamp}.jpg` and the URL is stored in the JSONL row's `frame_url` field.

New endpoint:

```
POST /capture-frame                      Save a JPEG captured by the browser
                                         (multipart: job_id, t_sec, frame)
```

---

## 🎓 Training & Calibration — teach it from your feedback

Once a few coaches have used **Expert Feedback Mode** (above), the app can turn those corrections into a **calibration** for its own scoring — so the number it shows lines up with what real coaches actually said. Open the **Settings** gear and expand **Training & Calibration**.

> **This is not machine-learning retraining.** Nothing learns in the background. The analyzer scores shots with fixed biomechanics rules, and calibration simply learns *one straight-line correction* — e.g. "the AI runs about 6 points high, so pull every score down a bit" — and lays it on top. It's small, transparent, and 100 % reversible.

### The short version

1. Use **Expert Feedback Mode** on some clips and give each one a **corrected overall score**. (Just opening the panel isn't enough — you have to move the score slider and click **Save feedback**.)
2. Do that on **at least 12 clips** (the default — see the readiness gate below). Each saved correction fills the progress bar in Training & Calibration.
3. When the bar reads **✓ ready to calibrate**, a green **Apply this correction to scoring** button appears. Click it.
4. From then on, every new analysis shows the **corrected** scores, and a green **● Calibration active** banner sits in the panel.
5. Changed your mind? Click **Revert to raw scoring** any time — the original scoring comes straight back.

### What the panel shows you

Even before it's ready to calibrate, the panel is a live report card on the analyzer:

| What you see | What it means |
|---|---|
| **`X / 12` expert reviews** progress bar | How many corrected scores you've saved vs. how many are needed to calibrate |
| **avg bias (pts)** | On average, how far *off* the AI is. `+5` means it scores 5 points **too low**; `−5` means 5 points **too high** |
| **avg error (pts)** | The typical size of the miss in either direction (mean absolute error) |
| **agreement (r)** | How well the AI's ranking of shots matches the coaches' (correlation, −1…1; closer to 1 is better) |
| **Fitted correction** | The exact straight-line fix it would apply: `score → a·score + b`, plus how much it shrinks the average error |
| **Expert flags** | How many times reviewers ticked "AI score too high" / "too low" |
| **Least-trusted measurement** | The single metric coaches most often thumbs-down in **Measurement Feedback** — your best clue about which rule to fix next |

### How the math works (it's just a line)

Calibration fits the best straight line through your `(AI score, coach score)` points by least squares — `coach ≈ a · AI + b`. Turning it on runs **every** score (overall *and* power, technique, timing) through that same line and clamps each result to 0–100. Because the overall score is a weighted average of the three sub-scores, putting all of them through the *same* line keeps everything consistent. The original numbers aren't thrown away — they're stashed under a `raw` field in the result, and the adjusted scores are flagged with `"calibrated": true`. The correction also flows through everywhere the score appears: the History list, the saved result JSON, and the printable reports.

### The readiness gate (why 12?)

With only two or three reviews, a "correction" is basically noise — one grumpy coach could swing it wildly. So the app refuses to fit a line until it has at least **`CALIBRATION_MIN_SAMPLES`** corrected scores (default **12**). Want a stricter or looser threshold? Set the environment variable before launching:

```bash
CALIBRATION_MIN_SAMPLES=20 ./run.sh
```

Until the gate clears, the panel tells you exactly how many more reviews it needs — and `Apply` will politely refuse.

### Where it's stored

When you click **Apply**, the fitted correction is written to:

```
output/calibration.json
```

It's a tiny file — `{enabled, a, b, n, mae_before, mae_after, correlation, fitted_at}` — and like everything in `output/`, it's **gitignored** and never leaves your machine. **Revert** simply deletes it and scoring snaps back to raw. Adding more reviews and clicking **Re-fit from latest** overwrites it with a fresh fit.

### The endpoints behind it (advanced)

```
GET  /training/report     Agreement stats, fitted correction, per-metric reliability (read-only)
POST /training/apply      Fit + enable the correction (refuses until the readiness gate clears)
POST /training/revert     Delete the correction, return to raw scoring
```

`GET /training/report` is pure and read-only — it never changes scoring, so you can hit it any time to watch the numbers improve as feedback rolls in. Scores only ever change after an explicit **Apply**.

---

## Python libraries it installs

`./run.sh` installs everything in `.venv/` automatically. If you're curious what's in there, it's listed in `requirements.txt`:

- **fastapi** — the web server framework
- **uvicorn** — runs the FastAPI server
- **mediapipe** — Google's pose-detection model
- **opencv-python** — video frame handling
- **numpy** — math
- **yt-dlp** — downloads YouTube clips
- **python-multipart** — handles file uploads

You never need to install these by hand — `./run.sh` does it.

---

## Step 4 — Make a change

Open the folder in your code editor ([VS Code](https://code.visualstudio.com/) is free and great):

```bash
code .
```

Try editing `frontend/index.html` — change the title from "Hockey Shot Analyzer" to your team name. Save. Refresh the browser (you might need to stop the server with Ctrl+C and re-run `./run.sh`).

The cool files to mess with:
- `frontend/index.html` — what the page looks like
- `frontend/style.css` — colors, fonts, spacing
- `frontend/app.js` — what happens when you click things
- `backend/metrics.py` — the **scoring math and coaching tips**. Change the tips for your team!

---

## Step 5 — Save your change with git (a "commit")

Every time you make a change you want to keep:

```bash
git status                          # shows what files you changed
git add .                           # stage every change
git commit -m "describe what you did"
```

Example messages: `"changed title to Lightning"`, `"new coaching tip for knee bend"`.

A commit is a savepoint. You can always go back to any commit later.

---

## Step 6 — Push your changes to GitHub

To upload your commits to your fork on GitHub:

```bash
git push
```

That's it. Refresh your fork's page on github.com and you'll see your commits there.

---

## Working on a "branch" (safer for experiments)

A branch lets you try something without breaking the main version. **Always use branches for big changes.**

```bash
# Start a new branch off of main:
git checkout -b try-new-colors

# ...make some changes, commit them as usual...
git add .
git commit -m "trying purple buttons"

# Push the branch to GitHub:
git push -u origin try-new-colors
```

On GitHub, you'll now see a yellow banner offering to **"Compare & pull request"** — click it to merge your branch into `main` when you're happy. To go back to the main version:

```bash
git checkout main
```

To delete a branch you don't need anymore:

```bash
git branch -d try-new-colors           # locally
git push origin --delete try-new-colors  # on GitHub
```

---

## Getting updates from the original project

If the original `jtripppiie/hockey-shot-analyzer` gets new features and you want them:

```bash
# Tell git where the original lives (only do this once):
git remote add upstream https://github.com/jtripppiie/hockey-shot-analyzer.git

# Whenever you want to pull in updates:
git fetch upstream
git merge upstream/main
git push
```

If git complains about conflicts (you and the original both changed the same line), it'll mark the file with `<<<<<<<` and `>>>>>>>`. Open the file, pick which version you want, delete the markers, save, then:
```bash
git add .
git commit -m "merged upstream"
git push
```

---

## Share it with the world (optional)

To give a friend a link they can click to use your version, without them installing anything:

```bash
./share.sh
```

This opens a free [Cloudflare tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/trycloudflare/) and prints a `https://something.trycloudflare.com` URL. **Anyone with the URL can use the app — only share it with people you trust.** Press **Ctrl+C** in the terminal to take it down.

---

## Stop / clean up

```bash
# Stop the server cleanly:
fuser -k 8000/tcp
pkill -f 'cloudflared tunnel'

# Wipe analyzed clips and the score history (does NOT touch the venv or model):
rm -rf backend/uploads backend/output backend/history.csv

# Nuclear option — start completely fresh:
rm -rf .venv backend/pose_landmarker.task backend/uploads backend/output backend/history.csv
./run.sh
```

---

## When something goes wrong

| Problem | Fix |
|---|---|
| `git: command not found` | Install git (see the table at the top). |
| `python3: command not found` | Install Python 3.10+ (see the table at the top). |
| `Address already in use` | Something else is using port 8000. Run `fuser -k 8000/tcp` then try again. |
| `ffmpeg: command not found` | Linux/WSL: `sudo apt install ffmpeg` · Mac: `brew install ffmpeg`. |
| Model download fails | Re-run `./run.sh` — it retries. If still broken, check your internet. |
| Page takes forever after upload | Your clip is too big. Trim it under 30 seconds and under 100 MB. |
| Every metric says "Needs a side-view clip" | Camera was facing you head-on. Re-film from the side. |
| "This doesn't look like a hockey shot" | The clip didn't show a grounded shooting motion (a planted player snapping the puck) — e.g. a still clip, the wrong sport, or someone jumping. Upload a side-on clip of a single shot from wind-up through follow-through. |
| "This clip looks like it contains camera cuts" | The clip appears to be a montage or highlight reel with multiple scenes spliced together, which throws off the analysis. Upload a single continuous attempt — one shot, one camera, no edits. |
| `Permission denied: ./run.sh` | Run `chmod +x run.sh share.sh` once. |
| `git push` asks for a password | GitHub requires a **personal access token** instead of your password — make one at https://github.com/settings/tokens and paste it when prompted. |
| `Ctrl+Shift+F` does nothing | Expert Feedback Mode only works on the results page and is desktop-only (≥1024px width + a real keyboard/mouse) — see the Expert Feedback section above. |
| Expert form vanishes after reload | Expected. Expert Mode is temporary and never persisted; re-toggle it from the results page with `Ctrl+Shift+F`. |

---

## What's in the project

```
backend/         FastAPI app, pose detection, biomechanics, overlay rendering
  main.py        HTTP endpoints (/analyze, /analyze-youtube, /suggest-segments, /analyze-segment, /history, /feedback, /report, /sessions, /training, /errors)
  pose.py        MediaPipe wrapper + smoothing
  metrics.py     Scoring math and coaching tips
  overlay.py     Skeleton drawing + H.264 re-encode
  feedback.py    Expert Feedback Mode — JSONL append-only correction log
  report.py      Printable HTML report (player + expert modes) + session report
  session.py     Practice Sessions — group clips, averages + trends
  segmenter.py   Multi-rep attempt detection (smoothing + local maxima + NMS)
  errors.py      Centralized append-only error log (output/error_log.jsonl)
  test_session.py  Self-contained tests (python test_session.py)
  test_errors.py   Error-log tests: clear + opt-in cap (python test_errors.py)
  test_segment.py  Segment-trim tests (python test_segment.py; needs ffmpeg)
frontend/        The web page (no build step — just HTML/CSS/JS)
output/
  history.csv          summary row per analyzed clip
  feedback_log.jsonl   one line per expert feedback entry (gitignored)
  error_log.jsonl      one line per logged error (backend + browser)
  session_*.json       one file per saved practice session
  {job_id}_*.{mp4,jpg,json}   overlay video, key frame, full result
run.sh           One-click setup and launch (port 8000)
share.sh         Optional public URL via cloudflared
requirements.txt The Python libraries
```

## Tech behind the scenes

Python 3.10 · FastAPI · uvicorn · MediaPipe Tasks PoseLandmarker (Lite) · OpenCV · NumPy · ffmpeg (H.264/yuv420p) · yt-dlp · vanilla HTML/CSS/JS.

## A few UI details worth knowing

- **Animated progress scene** — while a clip is being analyzed, the page shows a small rink scene: a player on the left fires a continuous stream of pucks toward a goalie net on the right. The plain progress bar underneath still tracks the actual percentage. The scene respects `prefers-reduced-motion` and falls back to a static drawing for users with motion sensitivity.
- **Semi-transparent skeleton** — the pose overlay is drawn onto a copy of each frame and blended back at 65 % opacity, with smaller dot/line sizes than before. The underlying video stays visible *through* the skeleton so you can still see the puck, the stick, and the player's gear.
- **Frame-capture button** — see the Expert Feedback section above. Each captured frame is also embedded into the Expert report.

## 🩺 Diagnostics (built-in error log)

Everything that goes wrong — a failed YouTube download, a video the pose model
can't read, or even a JavaScript error in your browser — gets recorded to a
single append-only file, `output/error_log.jsonl`. You don't have to open a
terminal to see them: open the **Settings** gear and expand **Diagnostics** to
view the most recent errors (newest first), each with a source badge
(backend/browser), where it happened, and an expandable traceback.

Under the hood:

```
POST /client-error      Browser posts an uncaught JS error here (auto, throttled)
GET  /errors?limit=50   Most recent logged errors, newest first
POST /errors/clear      Wipe the error log (Diagnostics has a Clear-log button)
```

Backend code logs through one helper (`errors.log_error(...)`), a global
exception handler catches anything that escapes a route, and the frontend's
global error handlers forward uncaught browser errors automatically. The
**Clear log** button in Diagnostics asks for confirmation, then calls
`POST /errors/clear` and reports how many entries were removed. The log is
append-only and not rotated by default; set the `ERROR_LOG_MAX_LINES`
environment variable to a positive integer to keep only the newest N entries.
It is `.gitignore`d.

## 🎬 Multi-attempt clips

Got several shots in one video? On the upload screen, use **“Got several shots
in one clip? Find attempts →”**. The clip is scanned (`POST /suggest-segments`)
and a **Suggested Attempts** screen lists each detected attempt with its
timestamps and a confidence bar. Pick one and **Analyze this attempt**
(`POST /analyze-segment`) trims just that window with a frame-accurate ffmpeg
cut and scores it as its own clip — no re-uploading between attempts. If the
segmenter can't confidently find separate attempts, it says so and points you
back to single-clip analysis.

## 📋 Practice Sessions

The **Sessions** button groups several analyzed clips into one named practice
session so you can see **averages** and **first-vs-last trends** for power,
technique, and timing across the session — handy for tracking a single practice
or a week of reps. Each session is stored as `output/session_*.json`.

## For AI coding agents (Copilot, Claude, etc.)

If you're an AI assistant being asked to extend this repo, read [AGENTS.md](AGENTS.md) **first**. It's a short fast-start brief covering the port, the live Cloudflare tunnel, the architectural decisions that should not be casually undone (one JSONL log with a `type` discriminator, desktop-only Expert Mode dual guard, browser-side frame capture, HTML-not-PDF reports), the path-traversal guard on `/capture-frame`, and the gotchas (don't `pkill -f uvicorn` — it kills the sibling vault server too).

---

# 🥅 The Young Coder's Playbook

> **Hey! This part is for you.** 👋 If you've never written code before, that's
> totally fine — everybody starts at center ice not knowing how to skate. This
> playbook walks you through *everything*, one slow shift at a time. Read the
> parts you need, skip the parts you don't, and come back when you're stuck.
> Nobody learns a slapshot on the first try. You've got this. 🏒

**Jump to a drill:**

1. [Set up VS Code (your locker room)](#1-set-up-vs-code-your-locker-room)
2. [The 9 git commands you'll actually use](#2-the-9-git-commands-youll-actually-use)
3. [Branches: practice rinks where you can't break anything](#3-branches-practice-rinks-where-you-cant-break-anything)
4. [OOPS! How to undo any mistake](#4-oops-how-to-undo-any-mistake)
5. [Pull, merge, and rebase (getting other people's changes)](#5-pull-merge-and-rebase-getting-other-peoples-changes)
6. [Fixing a merge conflict (two people, one line)](#6-fixing-a-merge-conflict-two-people-one-line)
7. [Shortcuts that make you fast](#7-shortcuts-that-make-you-fast)
8. [How the scoring actually works (the secret math)](#8-how-the-scoring-actually-works-the-secret-math)
9. [Change the colors](#9-change-the-colors)
10. [Change the icons](#10-change-the-icons)
11. [Add a brand-new feature (full walkthrough)](#11-add-a-brand-new-feature-full-walkthrough)
12. [Put it on the internet with Google Cloud](#12-put-it-on-the-internet-with-google-cloud)
13. [Set up a robot helper (GitHub Actions)](#13-set-up-a-robot-helper-github-actions)
14. [Ask the AI for help (good prompts to copy)](#14-ask-the-ai-for-help-good-prompts-to-copy)
15. [The "I'm totally stuck" checklist](#15-the-im-totally-stuck-checklist)

---

## 1. Set up VS Code (your locker room)

**VS Code** is the program where you'll read and change the code. Think of it as
your locker room: all your gear in one place.

1. Download it free from **https://code.visualstudio.com** and install it.
2. Open your project in it. In your terminal, inside the project folder, type:
   ```bash
   code .
   ```
   That little `.` means "this folder." VS Code pops open with all the files on
   the left. (On Windows, run this inside your **Ubuntu** window.)

### The extensions to install

Extensions are like upgrades for your skates. Click the **squares icon** on the
far left (Extensions), search for each of these, and click **Install**:

| Extension | What it does for you |
|---|---|
| **Python** (Microsoft) | Understands the `.py` files, runs them, shows red squiggles when something's wrong |
| **Pylance** (Microsoft) | Auto-complete for Python — it finishes your sentences |
| **GitHub Copilot** | The AI helper. Type a comment like `# add a new tip` and it suggests the code |
| **Live Preview** (Microsoft) | Shows your web page changes instantly |
| **GitLens** | Makes the git history easy to see — who changed what, when |

> **Pro move:** press `Ctrl+\`` (the key above Tab) to open a terminal *inside*
> VS Code. Now you never have to leave the locker room.

---

## 2. The 9 git commands you'll actually use

**git** is a time machine for your code. It remembers every version, so you can
always go back. Here are the only commands you need at first:

```bash
git status                 # What did I change? (check this ALL the time)
git add .                  # Put my changes on the bench, ready to save
git commit -m "message"    # Save a checkpoint with a note about what you did
git push                   # Upload your checkpoints to GitHub
git pull                   # Download the newest version from GitHub
git log --oneline          # See your list of saved checkpoints
git checkout -b name       # Start a new practice rink (branch)
git checkout main          # Go back to the main rink
git restore filename       # Undo changes to a file (see drill #4)
```

**The rhythm of coding** is just three steps, over and over, like a line change:

```bash
# 1. Make a change in VS Code, save it (Ctrl+S)
git add .
git commit -m "made the title say Lightning"
git push
```

That's it. Change → `add` → `commit` → `push`. Forward, pass, shoot. 🏒

> **What's a good commit message?** Say *what you did* in a few words:
> `"changed buttons to green"`, `"new tip for follow-through"`,
> `"fixed the typo on the home page"`. Future-you will thank you.

---

## 3. Branches: practice rinks where you can't break anything

A **branch** is a copy of the project where you can try wild ideas. If it works,
you keep it. If it's a disaster, you throw the whole rink away and the *real*
project never knew. **Always make a branch before a big experiment.**

```bash
git checkout -b rainbow-buttons     # make + jump to a new branch
# ...mess around, commit as usual...
git push -u origin rainbow-buttons  # save the branch to GitHub
```

Like it? Go to your project on github.com and click the green
**"Compare & pull request"** button to bring it into `main`.

Hate it? Just leave it and go back to safety:

```bash
git checkout main                   # back to the real project, untouched
git branch -D rainbow-buttons       # delete the bad branch (capital -D = "yes, for sure")
```

The main branch is the game; branches are practice. Never test new plays during
a real game. 🥅

---

## 4. OOPS! How to undo any mistake

**This is the most important section.** You *cannot* permanently break things
with git — there's almost always an undo. Find your "oops" below:

| Your "oops" | The fix |
|---|---|
| I changed a file and want it back the way it was (didn't commit yet) | `git restore thefile.js` |
| I changed *lots* of files and want ALL of them back | `git restore .` |
| I did `git add` but want to un-add (un-bench) it | `git restore --staged thefile.js` |
| I made a commit but the message is wrong | `git commit --amend -m "better message"` |
| My last commit was a mistake — undo it but keep my changes | `git reset --soft HEAD~1` |
| My last commit was a mistake — undo it AND the changes | `git reset --hard HEAD~1` ⚠️ throws away work |
| I deleted a file by accident | `git restore thefile.js` (if not committed) |
| I want to go back to exactly how GitHub has it | `git fetch origin && git reset --hard origin/main` ⚠️ |
| **I REALLY messed up and don't know what happened** | `git reflog` — see below ⤵️ |

### The magic rewind: `git reflog`

`git reflog` is git's *security camera*. It records every single move you made,
even the ones you thought you erased. Run it:

```bash
git reflog
```

You'll see a list like:

```
a1b2c3d HEAD@{0}: reset: moving to HEAD~1
e4f5g6h HEAD@{1}: commit: the work I thought I lost
```

See that `e4f5g6h`? That's the checkpoint you panicked about. Bring it back:

```bash
git checkout e4f5g6h
```

**Nothing is ever truly gone.** Breathe. The camera saw it. 📹

> ⚠️ The commands marked ⚠️ throw away changes you haven't pushed. When in
> doubt, **commit first** (`git add . && git commit -m "wip"`) — a saved
> checkpoint can always be recovered, but unsaved changes can't.

---

## 5. Pull, merge, and rebase (getting other people's changes)

When the original project gets cool new features and you want them, you "pull"
them in. There are two styles. Here's the difference, in hockey terms:

### `git pull` / merge — taping two highlight reels together

```bash
git pull origin main
```

This grabs the new stuff and **merges** it with yours. It makes a little
"merge commit" — like splicing two video clips together with a transition. Your
history shows both reels joining up. **This is the safe default. Use it.**

Getting updates from the *original* project you forked from:

```bash
# Tell git where the original lives — only ONCE, ever:
git remote add upstream https://github.com/jtripppiie/hockey-shot-analyzer.git

# Then any time you want their updates:
git fetch upstream
git merge upstream/main
git push
```

### `git rebase` — re-recording your plays on top of the new game tape

```bash
git pull --rebase origin main
```

Rebase takes *your* commits, sets them aside, grabs everybody else's new
commits, and then **re-plays yours on top** — so your history looks like one
clean straight line instead of a Y-shaped merge. It's tidier, but trickier.

**Which should you use?**
- 🟢 **Learning / just want it to work:** use `git pull` (merge). Always fine.
- 🔵 **Want a clean, straight history and you're comfortable:** `git pull --rebase`.

> **Golden rule of rebase:** only rebase commits you *haven't pushed yet*.
> Rebasing stuff other people already have is like changing a game's score
> after everyone went home — it confuses everybody. When unsure, merge.

If a rebase gets scary and you want out, this always works:

```bash
git rebase --abort     # forget the whole thing, nothing changed
```

---

## 6. Fixing a merge conflict (two people, one line)

A **conflict** happens when you AND someone else changed *the exact same line*.
Git can't guess who's right, so it asks you. Don't panic — this is normal.

Git marks the spot in the file like this:

```
<<<<<<< HEAD
  <h1>My Awesome Title</h1>
=======
  <h1>The Original Title</h1>
>>>>>>> upstream/main
```

Read it like this:
- Between `<<<<<<<` and `=======` is **your** version.
- Between `=======` and `>>>>>>>` is **their** version.

**To fix it:** decide which one you want (or combine them), then **delete all
three marker lines** (`<<<<<<<`, `=======`, `>>>>>>>`) so only the line you want
is left. For example, keep yours:

```
  <h1>My Awesome Title</h1>
```

Then save the file and finish up:

```bash
git add .
git commit -m "fixed the conflict, kept my title"
git push
```

> VS Code makes this even easier: it highlights conflicts and shows buttons —
> **Accept Current Change**, **Accept Incoming Change**, **Accept Both**. Click
> the one you want and it cleans up the markers for you. 🎯

---

## 7. Shortcuts that make you fast

### Git nicknames (aliases)

Tired of typing `git checkout`? Teach git short nicknames — do this once:

```bash
git config --global alias.co checkout
git config --global alias.br branch
git config --global alias.st status
git config --global alias.cm "commit -m"
git config --global alias.lg "log --oneline --graph --all"
```

Now `git st` means `git status`, and `git cm "my note"` saves a checkpoint.
`git lg` draws a cool map of all your branches.

### VS Code shortcuts

| Keys | What it does |
|---|---|
| `Ctrl+S` | Save the file (do this constantly) |
| `Ctrl+Z` | Undo your last typing |
| `Ctrl+\`` | Open/close the terminal |
| `Ctrl+F` | Find a word in this file |
| `Ctrl+Shift+F` | Find a word in **every** file |
| `Ctrl+P` | Jump to any file by typing its name |
| `Ctrl+/` | Comment out the line (turn it off without deleting) |

> You don't have to memorize these. Pick two, use them till they're automatic,
> then learn two more. That's how pros build muscle memory.

---

## 8. How the scoring actually works (the secret math)

Ever wonder how the app turns a video into a number? No magic — just five steps.
Here's the whole play, start to finish:

**Step 1 — Find the body.** Google's "MediaPipe" model looks at every frame and
drops 33 dots on your body: shoulders, elbows, wrists, hips, knees, ankles. Like
a connect-the-dots that follows you around. (`backend/pose.py`)

**Step 2 — Measure angles, not pictures.** The app connects three dots to measure
a *joint angle* — for example hip → knee → ankle tells it how bent your knee is.
It uses the model's "3D world" dots so the score doesn't get fooled if your
camera is a little off to the side. (`backend/metrics.py`, `angle_3pts_3d`)

**Step 3 — Score each measurement 0–100 with a "good zone."** Every measurement
has an *ideal range*. Inside the range = 100 points. Outside it, the score slides
down toward 0. Here's the actual rule for knee bend, in plain English:

```python
# from backend/metrics.py
score = _score_band(val, 0.15, 0.40, 0.0, 0.7)
#                         ↑     ↑    ↑    ↑
#                    ideal_lo  │  hard_lo │
#                          ideal_hi    hard_hi
```

That says: "A knee bend between **0.15 and 0.40** is perfect (100). Less than 0
or more than 0.7 is as bad as it gets (0). In between, slide the score." A
straight, stiff leg scores low; a deep, loaded leg scores high. 🦵

**Step 4 — Turn scores into letter grades.** Each number becomes a word so it's
friendly:

```python
if score >= 85:  "great"
if score >= 70:  "good"
if score >= 50:  "ok"
else:            "needs work"
```

**Step 5 — Mix them into the three big scores.** Power, Technique, and Timing are
each a *weighted blend* — some ingredients matter more, like a recipe:

```python
power     = hip_rotation×0.35 + shoulder_rotation×0.25 + weight_transfer×0.25 + knee_bend×0.15
technique = knee_bend×0.30 + follow_through×0.35 + head_stability×0.35
timing    = release_timing×0.65 + follow_through×0.35
```

And the **Overall Shot Score** blends those three:

```python
overall = power×0.40 + technique×0.35 + timing×0.25
```

So Power counts the most (40%), then Technique (35%), then Timing (25%).

**Want to change how it scores?** Open `backend/metrics.py`. Change a weight
(make `timing` count more!), widen a "good zone," or rewrite a coaching tip in
your own words. Save, restart `./run.sh`, and analyze a clip to see your new
rules in action. **This file is the brain of the whole app** — and now you know
how it thinks. 🧠

---

## 9. Change the colors

All the colors live in one spot at the very top of
[`frontend/style.css`](frontend/style.css), inside a block called `:root`. They
have nicknames called *variables* (the things starting with `--`). Change a
nickname once and it updates everywhere it's used — like changing your whole
team's jersey color with one switch.

```css
:root {
  --blue:    #C8102E;   /* the main accent — buttons, highlights (this is Capitals red) */
  --d-bg:     #020D1C;   /* the dark background on the upload screen */
  --d-surface:#041E42;   /* the navy cards */
  --green:   #16A34A;   /* the "great score" color */
}
```

Those `#C8102E` things are **hex color codes**. Want to find your own? Go to
[Google's color picker](https://www.google.com/search?q=color+picker), pick a
color, and copy its hex code (it looks like `#FF6600`). Paste it in, save, and
refresh the browser.

> **Try this:** change `--blue` to `#6D28D9` (purple) and watch every button turn
> purple at once. That's the power of variables. 💜

---

## 10. Change the icons

The little pictures (⚙ gear, 📸 camera, ✕ close) are just **emoji typed right
into the HTML**. To change one, open
[`frontend/index.html`](frontend/index.html), find the emoji, and replace it
with a different one.

For example, the settings gear is here:

```html
<button id="settingsBtn" class="icon-btn" ...>⚙</button>
```

Change that `⚙` to `🛠️` or `🎛️` and save. Done! (On Mac press
`Ctrl+Cmd+Space` for the emoji picker; on Windows press `Windows + .`)

The big "upload" arrow is a drawing called an **SVG** (also in `index.html`).
That one's trickier to change — leave it for later, or ask the AI to help (see
drill #14).

---

## 11. Add a brand-new feature (full walkthrough)

Let's add a real feature together: **a button that picks a random hockey fact.**
This touches all three layers, so you'll learn how the app fits together.

**First, make a branch** (drill #3) so you can't break anything:

```bash
git checkout -b random-fact-button
```

**Step A — Add the button** in `frontend/index.html`. Find the results area and
drop this in somewhere visible:

```html
<button onclick="showHockeyFact()" class="btn-ghost">🏒 Random hockey fact</button>
<p id="factText"></p>
```

**Step B — Make it do something** in `frontend/app.js`. Add this function at the
bottom:

```javascript
function showHockeyFact() {
  const facts = [
    "A hockey puck is frozen before games so it doesn't bounce.",
    "The fastest slapshot ever recorded was over 108 mph!",
    "Pucks are made of vulcanized rubber.",
  ];
  const pick = facts[Math.floor(Math.random() * facts.length)];
  document.getElementById("factText").textContent = pick;
}
```

**Step C — Try it.** Restart the server (`Ctrl+C`, then `./run.sh`), refresh the
browser, and click your button. A random fact appears! 🎉

**Step D — Save your win:**

```bash
git add .
git commit -m "added a random hockey fact button"
git push -u origin random-fact-button
```

That's the whole loop of building a feature: **HTML** (what you see) → **app.js**
(what it does) → test → commit. Every feature, big or small, is just this same
shift repeated. Now try changing the facts to your own! 

> Want a feature that needs *math or video* (like a new score)? That lives in the
> **backend** Python files (`backend/metrics.py`). Same idea, different rink —
> ask the AI to walk you through it (drill #14).

---

## 12. Put it on the internet with Google Cloud

Want a real, always-on web address (not just the temporary `./share.sh` link) so
anyone can use your app? **Google Cloud Run** can host it. This part needs a
grown-up's help (it asks for a credit card, though it's free for small use).

This repo already includes a [`Dockerfile`](Dockerfile) — a recipe that packs
the whole app into a box Google can run. Here's the play:

1. **Install the Google Cloud tool** (`gcloud`): follow
   https://cloud.google.com/sdk/docs/install
2. **Log in and pick a project:**
   ```bash
   gcloud auth login
   gcloud config set project YOUR-PROJECT-ID
   ```
3. **Ship it** — this one command builds the box and puts it online:
   ```bash
   gcloud run deploy hockey-shot-analyzer \
     --source . \
     --region us-central1 \
     --allow-unauthenticated \
     --memory 2Gi
   ```
4. When it finishes, it prints a `https://...run.app` web address. **That's your
   app, live on the internet.** Share it! 🌎

> **Why `--memory 2Gi`?** The pose-detection AI needs room to think. With less
> memory it can run out and crash on bigger videos.
>
> **Heads up:** files saved on Cloud Run (analyzed clips, history) disappear when
> it restarts — that's normal for this kind of hosting. The analyzer still works
> perfectly; it just doesn't keep a permanent history in the cloud. That's a
> great "next feature" to learn about later (it's called a database). 💾

---

## 13. Set up a robot helper (GitHub Actions)

A **GitHub Action** is a robot that runs every time you push code. We've set one
up that runs all the app's tests automatically — so if you ever break something,
GitHub tells you with a red ❌ instead of you finding out the hard way.

It's already in the repo at
[`.github/workflows/tests.yml`](.github/workflows/tests.yml). You don't have to
do anything — it just works. Here's what happens:

1. You `git push` your code.
2. GitHub spins up a fresh computer, installs the app, and runs every test.
3. On your repo's **Actions** tab (top of the GitHub page) you'll see a ✅
   (everything passed) or ❌ (something broke — click it to see what).

Think of it as a goalie that checks every shot you take *before* it counts. If
the robot is happy, your code is healthy. 🥅

> Want to see it run? Make any tiny change, push it, then watch the **Actions**
> tab on github.com light up. It's strangely satisfying.

---

## 14. Ask the AI for help (good prompts to copy)

You have **GitHub Copilot** in VS Code (drill #1). It's like having a coach on
the bench. The secret to getting good help is **asking clearly**. Here are
copy-paste prompts that work great — open Copilot Chat and try them:

**When you don't understand some code:**
> "Explain what the `compute_metrics` function in `backend/metrics.py` does, like
> I'm 10 years old."

**When you want to build something:**
> "I want to add a button on the results page that shows the date the video was
> analyzed. Walk me through every file I need to change, step by step."

**When you see a scary red error:**
> "I got this error when I ran the app: [paste the whole error here]. What does it
> mean and how do I fix it?"

**When you want to change how it looks:**
> "In `frontend/style.css`, how do I make all the buttons have rounded corners and
> a drop shadow? Show me exactly what to change."

**When git confuses you:**
> "I ran `git rebase` and now I'm confused and scared. How do I safely get back to
> where I was before?"

**Tips for great prompts:**
- 🎯 **Be specific.** "Make a button" is vague. "Make a green button on the
  results page that says 'New Shot' and reloads the page" gets you real code.
- 📋 **Paste the whole error**, not just part of it. Errors have clues at the bottom.
- 🐢 **Ask it to go slow:** add "explain each step" or "like I'm a beginner."
- ❓ **It's okay to say "I don't understand, try again simpler."** The AI never
  gets annoyed.

---

## 15. The "I'm totally stuck" checklist

Coding feels frustrating sometimes — *for everyone, even pros*. When you're
stuck, run down this list before giving up:

1. **Did you save?** Press `Ctrl+S`. (Half of all "it's not working" is an
   unsaved file.) 💾
2. **Did you restart the server?** Press `Ctrl+C` in the terminal, then
   `./run.sh` again.
3. **Did you refresh the browser?** Press `Ctrl+Shift+R` (a hard refresh that
   ignores old cached stuff).
4. **Read the error out loud.** Errors look scary but the *last line* usually
   says exactly what's wrong in almost-plain English.
5. **Check the [troubleshooting table](#when-something-goes-wrong)** higher up in
   this README — your problem might already be there.
6. **Ask Copilot** — paste the error (drill #14).
7. **Undo and try again** — `git restore .` puts everything back so you can take a
   fresh shot (drill #4).
8. **Take a break.** Seriously. Go shoot some pucks. Half the time the answer
   pops into your head once you stop staring at it. 🏒

> **The #1 secret of every programmer:** they get stuck *constantly*, and they
> just keep trying things. Being stuck doesn't mean you're bad at this — it means
> you're doing it. Every bug you beat makes you better. Now get out there. 🥅

