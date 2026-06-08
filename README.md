# 🏒 Hockey Shot Analyzer

Upload a video of one of your hockey shots. The app draws a stick-figure skeleton over you and gives you a score (0–100) for power, technique, and timing — plus tips and drills to get better. **Built so a twelve-year-old can run it on their own laptop, change stuff, and share their version on GitHub.**

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
- ✅ **Whole body in the picture:** head to skates, with a bit of space around you
- ✅ **Just one player:** no teammates skating through the shot
- ✅ **One shot per clip:** trim it down — load through follow-through is enough
- ✅ **Good light:** even rink lights or daylight, no silhouettes
- ✅ **Best quality:** 1080p at 60 fps if your phone can do it (720p at 30 fps is fine too)

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

Each one gets a score 0–100 and a grade: `great`, `good`, `ok`, `needs work`, or `unmeasured`. You also get a coaching tip and a drill for every metric.

**Big scores:** Power · Technique · Timing · Overall Shot Score.

---

## 🧑‍🏫 Expert Feedback Mode (desktop only)

A hidden mode that lets a coach, parent, or trainer **privately correct the AI's score** and record what really happened on the ice. The collected feedback is saved as clean training data so we can improve scoring rules — or train a better model — later. **The kid/player never sees any of this.**

### How to turn it on

On a desktop or laptop browser (with a real keyboard), press:

**`Ctrl + Shift + F`** &nbsp;(or `⌘ + Shift + F` on Mac)

You'll see a small orange `🧑‍🏫 EXPERT MODE` badge appear in the header, and an **Expert Feedback** panel will show up below the Coach's Report on every analyzed shot. Press the shortcut again to turn it off — the preference is remembered per-browser in `localStorage`.

> **Desktop only by design.** The panel won't render on phones, tablets, or anything narrower than ~1024px / without a mouse. That's enforced both in JavaScript and CSS — even with "Request desktop site" on mobile, the form stays hidden.

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

The expert panel has buttons for both — just click them after a shot is analyzed.

### What we DON'T do (yet)

The model **does not retrain itself** from corrections. We collect clean data first, hand-curate it, then later use it to tune scoring weights or train a better model. One coach's opinion ≠ ground truth.

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
| `Permission denied: ./run.sh` | Run `chmod +x run.sh share.sh` once. |
| `git push` asks for a password | GitHub requires a **personal access token** instead of your password — make one at https://github.com/settings/tokens and paste it when prompted. |
| `Ctrl+Shift+F` does nothing | You're on a touch device or a narrow window. Expert Feedback Mode is desktop-only (≥1024px width + a real keyboard/mouse) — see the Expert Feedback section above. |
| Expert form vanishes after reload | It's remembered in `localStorage` per-browser. If you cleared site data, press the shortcut again. |

---

## What's in the project

```
backend/         FastAPI app, pose detection, biomechanics, overlay rendering
  main.py        HTTP endpoints (/analyze, /analyze-youtube, /history, /feedback, /report)
  pose.py        MediaPipe wrapper + smoothing
  metrics.py     Scoring math and coaching tips
  overlay.py     Skeleton drawing + H.264 re-encode
  feedback.py    Expert Feedback Mode — JSONL append-only correction log
  report.py      Printable HTML report (player + expert modes)
frontend/        The web page (no build step — just HTML/CSS/JS)
output/
  history.csv          summary row per analyzed clip
  feedback_log.jsonl   one line per expert feedback entry (gitignored)
  {job_id}_*.{mp4,jpg,json}   overlay video, key frame, full result
run.sh           One-click setup and launch (port 8000)
share.sh         Optional public URL via cloudflared
requirements.txt The Python libraries
```

## Tech behind the scenes

Python 3.10 · FastAPI · uvicorn · MediaPipe Tasks PoseLandmarker (Lite) · OpenCV · NumPy · ffmpeg (H.264/yuv420p) · yt-dlp · vanilla HTML/CSS/JS.
