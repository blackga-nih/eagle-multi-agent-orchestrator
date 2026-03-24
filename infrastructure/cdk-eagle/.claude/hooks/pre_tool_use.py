#!/usr/bin/env python3
"""PreToolUse hook stub — delegates to the root hook."""
import json
import sys

def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})
    command = tool_input.get("command", "")

    # Only act on Bash calls that start a server
    if tool_name != "Bash":
        sys.exit(0)

    triggers = ['uvicorn', 'next dev', 'npm run dev', 'npx next', 'node server']
    if not any(t in command for t in triggers):
        sys.exit(0)

    # Delegate to root hook for port cleanup
    import importlib.util
    import os
    root_hook = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '.claude', 'hooks', 'pre_tool_use.py')
    if os.path.exists(root_hook):
        spec = importlib.util.spec_from_file_location("root_hook", root_hook)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.main()
    sys.exit(0)

if __name__ == "__main__":
    main()
