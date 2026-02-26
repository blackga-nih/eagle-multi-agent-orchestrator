#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
#
# PreToolUse Guard Hook — Block dangerous commands, protect sensitive files.
# Demonstrates the Tool Blocking pattern (TAC Lesson 17: Damage Control).
#
# Configure in settings.json:
# {
#   "hooks": {
#     "PreToolUse": [
#       {
#         "matcher": "Bash",
#         "hooks": [{
#           "type": "command",
#           "command": "uv run .claude/hooks/pretooluse_guard.py"
#         }]
#       }
#     ]
#   }
# }

import json
import re
import sys

# ── Configuration ──────────────────────────────────────
# Patterns that should be BLOCKED (dangerous commands)
BLOCKED_COMMANDS = [
    r"rm\s+-rf\s+/",           # rm -rf / (root deletion)
    r"rm\s+-rf\s+~",           # rm -rf ~ (home deletion)
    r"DROP\s+TABLE",           # SQL DROP TABLE
    r"DROP\s+DATABASE",        # SQL DROP DATABASE
    r">\s*/dev/sd",            # Writing to raw disk
    r"mkfs\.",                 # Format filesystem
    r":(){ :\|:& };:",        # Fork bomb
    r"chmod\s+-R\s+777\s+/",  # Recursive 777 on root
]

# Files/paths that should be PROTECTED (deny writes)
PROTECTED_PATHS = [
    r"\.env$",                 # Environment files
    r"credentials",            # Credential files
    r"\.pem$",                 # Private keys
    r"\.key$",                 # Private keys
    r"id_rsa",                 # SSH keys
    r"\.sqlite$",             # Production databases
    r"/etc/",                  # System config
]

# ── Hook Logic ─────────────────────────────────────────
def main():
    hook_input = json.loads(sys.stdin.read())
    tool_name = hook_input.get("tool_name", "")
    tool_input = hook_input.get("tool_input", {})

    # Guard: only check Bash, Write, and Edit tools
    if tool_name not in ("Bash", "Write", "Edit"):
        allow()
        return

    if tool_name == "Bash":
        command = tool_input.get("command", "")
        check_command(command)
    else:
        file_path = tool_input.get("file_path", "")
        check_path(file_path)


def check_command(command: str):
    """Check a Bash command against blocked patterns."""
    for pattern in BLOCKED_COMMANDS:
        if re.search(pattern, command, re.IGNORECASE):
            block(f"Dangerous command blocked: matches pattern '{pattern}'. "
                  f"Command was: {command[:100]}")
            return
    allow()


def check_path(file_path: str):
    """Check a file path against protected patterns."""
    for pattern in PROTECTED_PATHS:
        if re.search(pattern, file_path, re.IGNORECASE):
            block(f"Protected file: '{file_path}' matches restriction '{pattern}'. "
                  f"This file cannot be modified by the agent.")
            return
    allow()


def allow():
    """Allow the tool call to proceed."""
    print(json.dumps({}))
    sys.exit(0)


def block(reason: str):
    """Block the tool call with a reason."""
    print(json.dumps({
        "decision": "block",
        "reason": reason
    }))
    sys.exit(2)


if __name__ == "__main__":
    main()
