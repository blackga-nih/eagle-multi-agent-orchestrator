#!/usr/bin/env python3
"""PreToolUse hook for Bash commands.

Handlers:
  1. uvicorn launch — auto-clears stale processes on the target port before starting a new server
"""

import json
import re
import subprocess
import sys


def _extract_port(command):
    """Extract --port N from a command string. Returns port as string, or '8000' as default."""
    match = re.search(r'--port\s+(\d+)', command)
    return match.group(1) if match else "8000"


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

    port = _extract_port(command)
    print(f"[hook] uvicorn launch detected — clearing stale processes on port {port}", file=sys.stderr)

    # Kill any process holding the target port
    try:
        result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
        killed = set()
        for line in result.stdout.splitlines():
            if f":{port} " in line and "LISTENING" in line:
                parts = line.split()
                pid = parts[-1]
                if pid.isdigit() and pid not in killed:
                    subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
                    killed.add(pid)
                    print(f"[hook] killed PID {pid} on port {port}", file=sys.stderr)
        if not killed:
            print(f"[hook] port {port} is free", file=sys.stderr)
    except Exception as exc:
        print(f"[hook] port scan failed: {exc}", file=sys.stderr)

    # Allow the original command to proceed
    sys.exit(0)


if __name__ == "__main__":
    main()
