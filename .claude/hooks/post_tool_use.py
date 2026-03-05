#!/usr/bin/env python3
"""PostToolUse hook: strip Co-Authored-By Claude Sonnet from any git commit made by Claude.

Fires after Bash tool calls that include git commit/cherry-pick operations.
Amends HEAD in-place to remove the Co-Authored-By: Claude Sonnet trailer.
Safe to run mid-session — skips if HEAD message is already clean or if a
rebase/cherry-pick sequence is in progress (CHERRY_PICK_HEAD file present).
"""

import json
import os
import re
import subprocess
import sys


_CLAUDE_TRAILER_PAT = re.compile(
    r"[\r\n]+Co-Authored-By: Claude Sonnet[^\r\n]*<noreply@anthropic\.com>[^\r\n]*",
    re.IGNORECASE,
)

_COMMIT_OPS = ("git commit", "git cherry-pick", "git merge")


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    if data.get("tool_name") != "Bash":
        sys.exit(0)

    command: str = data.get("tool_input", {}).get("command", "")
    if not any(op in command for op in _COMMIT_OPS):
        sys.exit(0)

    # Skip if a multi-step cherry-pick/rebase sequence is in progress —
    # amending mid-sequence rewrites SHAs that git needs to track.
    git_dir = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        capture_output=True, text=True, encoding="utf-8",
    ).stdout.strip()
    if git_dir:
        for marker in ("CHERRY_PICK_HEAD", "rebase-merge", "rebase-apply"):
            if os.path.exists(os.path.join(git_dir, marker)):
                sys.exit(0)

    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%B"],
            capture_output=True, text=True, encoding="utf-8",
        )
        if result.returncode != 0 or not result.stdout:
            sys.exit(0)

        original = result.stdout
        cleaned = _CLAUDE_TRAILER_PAT.sub("", original).rstrip() + "\n"

        if cleaned == original:
            sys.exit(0)  # nothing to strip

        amend = subprocess.run(
            ["git", "commit", "--amend", "-F", "-"],
            input=cleaned, text=True, encoding="utf-8",
            capture_output=True,
        )
        if amend.returncode == 0:
            print("[hook] stripped Co-Authored-By: Claude Sonnet from commit", file=sys.stderr)
        else:
            print(f"[hook] amend failed: {amend.stderr.strip()}", file=sys.stderr)

    except Exception as exc:
        print(f"[hook] post-commit strip error: {exc}", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
