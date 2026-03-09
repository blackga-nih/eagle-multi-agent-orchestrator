#!/usr/bin/env python3
"""PreToolUse hook: kill stale processes on a port before starting a new server.

Detects uvicorn/next-dev/npm-run-dev commands, extracts the target port
(e.g. --port 8000, -p 3000), and kills any LISTENING processes on that port
before allowing the command to proceed.

On Windows, uvicorn's StatReload creates child processes that inherit the
socket. We use taskkill /F /T (tree kill) to get the whole process tree,
and retry until the port is clear.
"""

import json
import re
import subprocess
import sys
import time


def extract_port(command: str) -> str | None:
    """Extract port number from a server-start command."""
    # --port 8000 or --port=8000
    m = re.search(r'--port[= ](\d+)', command)
    if m:
        return m.group(1)
    # -p 3000
    m = re.search(r'-p\s+(\d+)', command)
    if m:
        return m.group(1)
    # PORT=8000 (env var prefix)
    m = re.search(r'PORT=(\d+)', command)
    if m:
        return m.group(1)
    return None


def is_server_start(command: str) -> bool:
    """Check if command is starting a server process."""
    triggers = ['uvicorn', 'next dev', 'npm run dev', 'npx next', 'node server']
    return any(t in command for t in triggers)


def get_pids_on_port(port: str) -> set[str]:
    """Get all PIDs listening on the given port."""
    pids = set()
    try:
        result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
        for line in result.stdout.splitlines():
            if f":{port} " in line and "LISTENING" in line:
                parts = line.split()
                pid = parts[-1]
                if pid.isdigit() and pid != "0":
                    pids.add(pid)
    except Exception:
        pass
    return pids


def kill_port(port: str) -> None:
    """Kill all processes listening on the given port (Windows).

    Uses /T (tree kill) to catch uvicorn reloader children.
    Retries up to 3 times since Windows process cleanup can be slow.
    """
    for attempt in range(3):
        pids = get_pids_on_port(port)
        if not pids:
            if attempt > 0:
                print(f"[hook] port {port} clear after {attempt + 1} attempt(s)", file=sys.stderr)
            return

        for pid in pids:
            # /T = tree kill (parent + children), /F = force
            subprocess.run(["taskkill", "/F", "/T", "/PID", pid],
                           capture_output=True, timeout=5)
            print(f"[hook] tree-killed PID {pid} on port {port}", file=sys.stderr)

        # Brief pause for Windows to release the port
        time.sleep(1)

    # Final check
    remaining = get_pids_on_port(port)
    if remaining:
        print(f"[hook] WARNING: {len(remaining)} process(es) still on port {port}: {remaining}", file=sys.stderr)
    else:
        print(f"[hook] port {port} cleared", file=sys.stderr)


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})
    command = tool_input.get("command", "")

    # Only act on Bash calls that start a server
    if tool_name != "Bash" or not is_server_start(command):
        sys.exit(0)

    port = extract_port(command)
    if not port:
        sys.exit(0)

    print(f"[hook] server start detected — clearing port {port}", file=sys.stderr)
    kill_port(port)

    sys.exit(0)


if __name__ == "__main__":
    main()
