#!/bin/bash
# ── Kill EAGLE dev zombies ────────────────────────────────────────
# Finds and kills anything on ports 8000 (backend) and 3000 (frontend).
# Uses PowerShell Stop-Process as fallback when taskkill fails (common
# on Git Bash / MINGW where taskkill reports "not found" for zombie PIDs).
#
# Usage:  ./kill-dev.sh
#         ./kill-dev.sh 8000       # kill only port 8000
#         ./kill-dev.sh 8000 3000  # explicit ports
# ──────────────────────────────────────────────────────────────────

PORTS="${@:-8000 3000}"
killed=0

for port in $PORTS; do
  pids=$(netstat -ano 2>/dev/null | grep ":${port}" | grep LISTENING | awk '{print $5}' | sort -u | grep -v '^0$' || true)
  if [ -n "$pids" ]; then
    for pid in $pids; do
      echo "Killing PID $pid on port $port"
      # Try taskkill first, fall back to PowerShell Stop-Process
      if taskkill //F //PID "$pid" 2>/dev/null; then
        killed=$((killed + 1))
      elif powershell -Command "Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue" 2>/dev/null; then
        echo "  (killed via PowerShell fallback)"
        killed=$((killed + 1))
      else
        echo "  WARNING: Could not kill PID $pid — may need Task Manager or reboot"
      fi
    done
    sleep 1
  fi
done

# Clean up PID files
rm -f "$(dirname "$0")/server/.uvicorn.pid"

if [ "$killed" -eq 0 ]; then
  echo "No zombie processes found on ports: $PORTS"
else
  echo "Killed $killed process(es)"
fi
