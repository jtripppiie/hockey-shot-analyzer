#!/usr/bin/env bash
# run.sh — One-click setup and launch for Hockey Shot Analyzer

set -e
cd "$(dirname "$(realpath "$0")")"

echo ""
echo "========================================"
echo "  🏒  Hockey Shot Analyzer"
echo "========================================"
echo ""

# ── Step 1: Ensure system dependencies are available ──────────────────────────────
MISSING_PKGS=()
python3 -m venv --help &>/dev/null || MISSING_PKGS+=(python3-venv python3-pip)
ldconfig -p | grep -q libGLESv2 || MISSING_PKGS+=(libgles2)
ldconfig -p | grep -q libEGL    || MISSING_PKGS+=(libegl1)
command -v ffmpeg &>/dev/null   || MISSING_PKGS+=(ffmpeg)

if [ ${#MISSING_PKGS[@]} -gt 0 ]; then
  echo "📦 Installing system packages (requires your password once): ${MISSING_PKGS[*]}"
  sudo apt-get install -y "${MISSING_PKGS[@]}"
fi

# ── Step 2: Create virtual environment ────────────────────────────────────────
if [ ! -d ".venv" ]; then
  echo "🔧 Setting up Python environment (first time only)..."
  python3 -m venv .venv
fi

source .venv/bin/activate

# ── Step 3: Install Python packages ───────────────────────────────────────────
if ! python3 -c "import fastapi, cv2, mediapipe, yt_dlp" &>/dev/null; then
  echo "📦 Installing packages (first time only, may take 1-2 minutes)..."
  pip install -q --upgrade pip
  pip install -q -r requirements.txt
fi

# ── Step 4: Download pose model if missing ────────────────────────────────────
MODEL="backend/pose_landmarker.task"
if [ ! -f "$MODEL" ]; then
  echo "🤖 Downloading AI pose model (one time, ~6 MB)..."
  curl -fsSL -o "$MODEL" \
    https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task
  echo "   ✅ Model downloaded."
fi

# ── Step 5: Launch ────────────────────────────────────────────────────────────
echo ""
echo "✅ Everything is ready!"
echo ""
echo "   👉  Open this address in your browser:"
echo "       http://localhost:8000"
echo ""
echo "   (Press Ctrl+C to stop the server)"
echo ""

cd backend
uvicorn main:app --host 0.0.0.0 --port 8000
