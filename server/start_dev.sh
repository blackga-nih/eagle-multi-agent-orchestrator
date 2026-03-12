#!/bin/bash
# ── EAGLE Backend Dev Server ──────────────────────────────────────
# Kills any zombie process on PORT before starting uvicorn.
# Usage:  ./start_dev.sh          (default port 8000)
#         PORT=9000 ./start_dev.sh
# ──────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PORT="${PORT:-8000}"
PIDFILE="$SCRIPT_DIR/.uvicorn.pid"

# ── Load .env ─────────────────────────────────────────────────────
if [ -f "$SCRIPT_DIR/../.env" ]; then
  set -a
  source "$SCRIPT_DIR/../.env"
  set +a
fi

# ── Kill zombies on $PORT ─────────────────────────────────────────
kill_port() {
  local pids
  # Windows/MINGW: netstat -ano gives PID in column 5
  pids=$(netstat -ano 2>/dev/null | grep ":${PORT}" | grep LISTENING | awk '{print $5}' | sort -u | grep -v '^0$' || true)
  if [ -n "$pids" ]; then
    echo "Killing zombie process(es) on port $PORT: $pids"
    for pid in $pids; do
      taskkill //F //PID "$pid" 2>/dev/null || true
    done
    sleep 1
  fi
}

# Also kill from previous PID file
if [ -f "$PIDFILE" ]; then
  old_pid=$(cat "$PIDFILE" 2>/dev/null || true)
  if [ -n "$old_pid" ]; then
    echo "Killing previous uvicorn (PID $old_pid)"
    taskkill //F //PID "$old_pid" 2>/dev/null || true
  fi
  rm -f "$PIDFILE"
fi

kill_port

# ── Start uvicorn ─────────────────────────────────────────────────
cd "$SCRIPT_DIR"
echo "Starting uvicorn on http://127.0.0.1:$PORT (reload enabled, watching app/)"

cleanup() {
  rm -f "$PIDFILE"
  echo "Backend stopped."
}
trap cleanup EXIT INT TERM

python -m uvicorn app.main:app \
  --host 127.0.0.1 \
  --port "$PORT" \
  --reload \
  --reload-dir app &

echo $! > "$PIDFILE"
wait
