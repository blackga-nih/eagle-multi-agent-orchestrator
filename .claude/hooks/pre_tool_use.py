#!/usr/bin/env python3
"""PreToolUse hook: kill stale uvicorn/port-8000 processes before starting a new server."""

import json
import subprocess
import sys


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})
    command = tool_input.get("command", "")

    # Only act on Bash calls that launch uvicorn
    if tool_name != "Bash" or "uvicorn" not in command:
        sys.exit(0)

    print("[hook] uvicorn launch detected — clearing stale processes on port 8000", file=sys.stderr)

    # 1. Kill uvicorn by process name
    subprocess.run(["taskkill", "/F", "/IM", "uvicorn.exe"], capture_output=True)

    # 2. Kill any process holding port 8000
    try:
        result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
        killed = set()
        for line in result.stdout.splitlines():
            if ":8000 " in line and "LISTENING" in line:
                parts = line.split()
                pid = parts[-1]
                if pid.isdigit() and pid not in killed:
                    subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
                    killed.add(pid)
                    print(f"[hook] killed PID {pid}", file=sys.stderr)
    except Exception as exc:
        print(f"[hook] port scan failed: {exc}", file=sys.stderr)

    # Allow the original command to proceed
    sys.exit(0)


if __name__ == "__main__":
    main()
