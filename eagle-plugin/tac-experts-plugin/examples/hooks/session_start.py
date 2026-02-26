#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["python-dotenv"]
# ///
"""
SessionStart hook — Load environment variables from .env into the Claude session.

Triggered: Every session start, resume, clear, or compact.
Pattern: Context Injection (hooks-architecture.md)

Configuration (settings.json):
{
  "hooks": {
    "SessionStart": [{
      "hooks": [{
        "type": "command",
        "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/session_start.py",
        "timeout": 30
      }]
    }]
  }
}
"""

import json
import os
import sys
from pathlib import Path

try:
    from dotenv import dotenv_values
except ImportError:
    # Graceful fallback if python-dotenv not available
    print(json.dumps({"loaded": 0, "note": "python-dotenv not installed"}))
    sys.exit(0)

# Find .env relative to project directory
project_dir = os.environ.get("CLAUDE_PROJECT_DIR", ".")
env_file = Path(project_dir) / ".env"

if not env_file.exists():
    print(json.dumps({"loaded": 0, "note": f"No .env file at {env_file}"}))
    sys.exit(0)

# Load .env values (never log or display actual values)
env_vars = dotenv_values(str(env_file))

# Write to CLAUDE_ENV_FILE for persistence across the session
claude_env = os.environ.get("CLAUDE_ENV_FILE", "")
if claude_env:
    with open(claude_env, "a") as f:
        for key, value in env_vars.items():
            # Escape single quotes for shell safety
            escaped = value.replace("'", "'\\''") if value else ""
            f.write(f"export {key}='{escaped}'\n")

# Log (append mode for history, keys only — never values)
log_path = Path(project_dir) / "session_start.log"
with open(log_path, "a") as f:
    f.write(f"Loaded {len(env_vars)} vars: {', '.join(env_vars.keys())}\n")

# Return summary to Claude (keys only — NEVER values)
print(json.dumps({
    "loaded": len(env_vars),
    "keys": list(env_vars.keys())
}))
