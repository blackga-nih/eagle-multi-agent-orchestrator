#!/bin/bash
# ── EAGLE Full Dev Environment ────────────────────────────────────
# Starts backend (port 8000) + frontend (port 3000) together.
# Ctrl+C kills BOTH cleanly — no zombies.
#
# Usage:  ./start-dev.sh
#         ./start-dev.sh --backend-only
#         ./start-dev.sh --frontend-only
# ──────────────────────────────────────────────────────────────────
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
PIDS=()

# ── Parse args ────────────────────────────────────────────────────
RUN_BACKEND=true
RUN_FRONTEND=true
for arg in "$@"; do
  case "$arg" in
    --backend-only)  RUN_FRONTEND=false ;;
    --frontend-only) RUN_BACKEND=false ;;
  esac
done

# ── Cleanup on exit ───────────────────────────────────────────────
cleanup() {
  echo ""
  echo "Shutting down..."
  for pid in "${PIDS[@]}"; do
    taskkill //F //PID "$pid" 2>/dev/null || \
      powershell -Command "Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue" 2>/dev/null || \
      kill "$pid" 2>/dev/null || true
  done
  # Also sweep the ports to catch any children
  for port in $BACKEND_PORT $FRONTEND_PORT; do
    local_pids=$(netstat -ano 2>/dev/null | grep ":${port}" | grep LISTENING | awk '{print $5}' | sort -u | grep -v '^0$' || true)
    for p in $local_pids; do
      taskkill //F //PID "$p" 2>/dev/null || \
        powershell -Command "Stop-Process -Id $p -Force -ErrorAction SilentlyContinue" 2>/dev/null || true
    done
  done
  rm -f "$ROOT_DIR/server/.uvicorn.pid"
  echo "All processes stopped."
}
trap cleanup EXIT INT TERM

# ── Kill zombies helper ──────────────────────────────────────────
kill_port() {
  local port=$1
  local pids
  pids=$(netstat -ano 2>/dev/null | grep ":${port}" | grep LISTENING | awk '{print $5}' | sort -u | grep -v '^0$' || true)
  if [ -n "$pids" ]; then
    echo "Killing zombie(s) on port $port: $pids"
    for pid in $pids; do
      # taskkill often fails on Git Bash/MINGW — PowerShell fallback
      if ! taskkill //F //PID "$pid" 2>/dev/null; then
        powershell -Command "Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue" 2>/dev/null || true
      fi
    done
    sleep 1
  fi
}

# ── Load .env ─────────────────────────────────────────────────────
if [ -f "$ROOT_DIR/.env" ]; then
  set -a
  source "$ROOT_DIR/.env"
  set +a
fi

# ── AWS SSO pre-check ────────────────────────────────────────────
# Ensures SSO session is valid before starting services that need AWS.
# Uses AWS_PROFILE from .env (defaults to "eagle").
_aws_profile="${AWS_PROFILE:-eagle}"
if ! AWS_PROFILE="$_aws_profile" aws sts get-caller-identity &>/dev/null; then
  echo ""
  echo "⚠  AWS SSO session expired or missing for profile '$_aws_profile'"
  echo "   Running: aws sso login --profile $_aws_profile"
  echo ""
  AWS_PROFILE="$_aws_profile" aws sso login --profile "$_aws_profile"
  if ! AWS_PROFILE="$_aws_profile" aws sts get-caller-identity &>/dev/null; then
    echo "ERROR: AWS SSO login failed. Backend will start but CloudWatch/DynamoDB/S3 calls will fail."
  else
    echo "✓ AWS SSO session active"
  fi
else
  echo "✓ AWS SSO session active ($_aws_profile)"
fi

# ── Backend ───────────────────────────────────────────────────────
if [ "$RUN_BACKEND" = true ]; then
  kill_port "$BACKEND_PORT"
  echo "Starting backend on http://127.0.0.1:$BACKEND_PORT"
  (cd "$ROOT_DIR/server" && python -m uvicorn app.main:app \
    --host 127.0.0.1 \
    --port "$BACKEND_PORT" \
    --reload \
    --reload-dir app) &
  PIDS+=($!)
  echo $! > "$ROOT_DIR/server/.uvicorn.pid"
fi

# ── Frontend ──────────────────────────────────────────────────────
if [ "$RUN_FRONTEND" = true ]; then
  kill_port "$FRONTEND_PORT"
  echo "Starting frontend on http://localhost:$FRONTEND_PORT"
  (cd "$ROOT_DIR/client" && npm run dev -- --port "$FRONTEND_PORT") &
  PIDS+=($!)
fi

# ── Wait ──────────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════"
echo "  EAGLE Dev Environment Running"
if [ "$RUN_BACKEND" = true ]; then
  echo "  Backend:  http://127.0.0.1:$BACKEND_PORT"
fi
if [ "$RUN_FRONTEND" = true ]; then
  echo "  Frontend: http://localhost:$FRONTEND_PORT"
fi
echo "  Press Ctrl+C to stop all"
echo "══════════════════════════════════════════════"
echo ""

wait
