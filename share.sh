#!/usr/bin/env bash
# share.sh — Run the Hockey Shot Analyzer and expose it on a public URL
#             via Cloudflare Quick Tunnel (no signup, no token needed).
#
# Usage:  ./share.sh
# Stop:   Ctrl+C  (kills both tunnel and server)

set -e
cd "$(dirname "$(realpath "$0")")"

PORT=8000
LOG_DIR="/tmp"
SERVER_LOG="$LOG_DIR/hockey-server.log"
TUNNEL_LOG="$LOG_DIR/hockey-tunnel.log"

echo ""
echo "========================================"
echo "  🏒  Hockey Shot Analyzer — Public Share"
echo "========================================"
echo ""

# ── Ensure cloudflared is installed ───────────────────────────────────────────
if ! command -v cloudflared &>/dev/null; then
  echo "📦 Installing cloudflared (requires your password once)…"
  ARCH=$(dpkg --print-architecture 2>/dev/null || uname -m)
  case "$ARCH" in
    amd64|x86_64) CF_PKG=cloudflared-linux-amd64.deb ;;
    arm64|aarch64) CF_PKG=cloudflared-linux-arm64.deb ;;
    *) echo "❌ Unsupported arch $ARCH — install cloudflared manually."; exit 1 ;;
  esac
  TMP_DEB=$(mktemp --suffix=.deb)
  curl -fsSL -o "$TMP_DEB" "https://github.com/cloudflare/cloudflared/releases/latest/download/$CF_PKG"
  sudo dpkg -i "$TMP_DEB"
  rm -f "$TMP_DEB"
fi

# ── Make sure the server is running (re-use existing or start a new one) ──────
SERVER_PID=""
if curl -s -o /dev/null -w "%{http_code}" "http://localhost:$PORT/" | grep -q 200; then
  echo "✅ Server already running on port $PORT"
else
  echo "🚀 Starting server on port $PORT…"
  # Reuse run.sh's bootstrap (installs deps, downloads model if needed)
  if [ ! -d ".venv" ] || ! .venv/bin/python -c "import fastapi, cv2, mediapipe, yt_dlp" &>/dev/null; then
    bash run.sh &
    RUN_PID=$!
    # Give run.sh time to finish setup and start uvicorn
    for i in $(seq 1 60); do
      sleep 2
      if curl -s -o /dev/null -w "%{http_code}" "http://localhost:$PORT/" | grep -q 200; then
        break
      fi
    done
    SERVER_PID=$RUN_PID
  else
    source .venv/bin/activate
    cd backend
    nohup uvicorn main:app --host 0.0.0.0 --port "$PORT" > "$SERVER_LOG" 2>&1 &
    SERVER_PID=$!
    cd ..
    for i in $(seq 1 15); do
      sleep 1
      curl -s -o /dev/null -w "%{http_code}" "http://localhost:$PORT/" | grep -q 200 && break
    done
  fi
  if ! curl -s -o /dev/null -w "%{http_code}" "http://localhost:$PORT/" | grep -q 200; then
    echo "❌ Server didn't start — check $SERVER_LOG"
    exit 1
  fi
  echo "✅ Server is up (PID $SERVER_PID, log: $SERVER_LOG)"
fi

# ── Clean up on exit ──────────────────────────────────────────────────────────
TUNNEL_PID=""
cleanup() {
  echo ""
  echo "🛑 Shutting down…"
  [ -n "$TUNNEL_PID" ] && kill "$TUNNEL_PID" 2>/dev/null || true
  [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null || true
  exit 0
}
trap cleanup INT TERM

# ── Start the tunnel ──────────────────────────────────────────────────────────
echo ""
echo "🌐 Opening public Cloudflare tunnel…"
echo "   (this can take 5–15 seconds)"
echo ""

: > "$TUNNEL_LOG"
cloudflared tunnel --url "http://localhost:$PORT" --no-autoupdate > "$TUNNEL_LOG" 2>&1 &
TUNNEL_PID=$!

# Watch the log until we see the public URL
PUBLIC_URL=""
for i in $(seq 1 30); do
  sleep 1
  PUBLIC_URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$TUNNEL_LOG" | head -1)
  [ -n "$PUBLIC_URL" ] && break
done

if [ -z "$PUBLIC_URL" ]; then
  echo "❌ Couldn't grab the public URL from cloudflared. Last log lines:"
  tail -20 "$TUNNEL_LOG"
  cleanup
  exit 1
fi

echo "════════════════════════════════════════════════════════════════"
echo ""
echo "   ✅  Share this link with anyone:"
echo ""
echo "       $PUBLIC_URL"
echo ""
echo "   ⚠️   No password protects this URL. Stop sharing with Ctrl+C."
echo ""
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "📜 Tunnel log: $TUNNEL_LOG"
echo "📜 Server log: $SERVER_LOG"
echo ""

# Keep script alive until user kills it
wait $TUNNEL_PID
