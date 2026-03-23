#!/usr/bin/env python3
"""
Post-session self-improve queue hook.

Fires on Claude Code Stop event. Maps files changed in the session
to expert domains and writes a queue file so the next session can
prompt the user to run self-improve on affected domains.

Wire-up in .claude/settings.json:
  "Stop": [{"command": "python C:/Users/blackga/Desktop/eagle/sm_eagle/.claude/hooks/post_session_self_improve.py"}]
"""

import sys
import os
import json
import subprocess
from datetime import date

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

REPO_ROOT = "C:/Users/blackga/Desktop/eagle/sm_eagle"
QUEUE_FILE = f"{REPO_ROOT}/.claude/context/self-improve-queue.json"

# File path prefixes → expert domains they affect
DOMAIN_MAP = [
    ("server/app/",                  ["backend", "strands", "sse"]),
    ("server/tests/",                ["eval", "test"]),
    ("client/",                      ["frontend"]),
    ("infrastructure/cdk-eagle/",    ["aws", "deployment"]),
    (".github/workflows/",           ["git"]),
    (".claude/hooks/",               ["hooks"]),
    ("eagle-plugin/",                ["strands", "backend"]),
    ("server/eagle_skill_constants", ["strands", "backend"]),
]

def get_changed_files():
    """Get files changed since last commit (staged + unstaged)."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True, text=True, cwd=REPO_ROOT
        )
        staged = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True, text=True, cwd=REPO_ROOT
        )
        files = set(result.stdout.strip().splitlines() + staged.stdout.strip().splitlines())
        return [f for f in files if f]
    except Exception:
        return []

def map_files_to_domains(files):
    """Return sorted unique list of domains touched by changed files."""
    touched = set()
    for f in files:
        for prefix, domains in DOMAIN_MAP:
            if f.startswith(prefix):
                touched.update(domains)
    return sorted(touched)

def load_existing_queue():
    if os.path.exists(QUEUE_FILE):
        try:
            with open(QUEUE_FILE, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            pass
    return {"domains": [], "history": []}

def write_queue(domains):
    os.makedirs(os.path.dirname(QUEUE_FILE), exist_ok=True)
    existing = load_existing_queue()

    # Merge new domains with any already queued
    all_domains = sorted(set(existing.get("domains", []) + domains))

    # Append to history
    history = existing.get("history", [])
    if domains:
        history.append({
            "date": date.today().isoformat(),
            "domains": domains
        })
        # Keep last 10 history entries
        history = history[-10:]

    queue = {
        "domains": all_domains,
        "last_updated": date.today().isoformat(),
        "history": history,
        "instructions": (
            "Run /parallel_expert_self_improve to update expertise for queued domains. "
            "Domains are cleared from this file once self-improve has run for them."
        )
    }

    with open(QUEUE_FILE, "w", encoding="utf-8") as fh:
        json.dump(queue, fh, indent=2)

    return all_domains

def main():
    files = get_changed_files()
    if not files:
        # No changes — nothing to queue
        sys.exit(0)

    domains = map_files_to_domains(files)
    if not domains:
        sys.exit(0)

    all_queued = write_queue(domains)

    # Print to stderr so it shows as a hook notification, not stdout
    print(
        f"\n[self-improve hook] Queued domains for self-improve: {', '.join(all_queued)}\n"
        f"  Run /parallel_expert_self_improve to update expertise files.\n",
        file=sys.stderr
    )
    sys.exit(0)

if __name__ == "__main__":
    main()
