#!/usr/bin/env python3
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
if data.get("tool_name") != "Bash" or "uvicorn" not in data.get("tool_input", {}).get("command", ""):
    sys.exit(0)
import subprocess
subprocess.run(["taskkill", "/F", "/IM", "uvicorn.exe"], capture_output=True)
sys.exit(0)
