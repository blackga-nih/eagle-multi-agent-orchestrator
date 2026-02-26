#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""
Setup Init hook — Deterministic project initialization.

Triggered: `claude --init` or `claude --init-only`
Pattern: Progressive Execution Modes → Deterministic layer

This hook is the SOURCE OF TRUTH for project setup.
The agentic /install command reads this hook's log and adds supervision.

Configuration (settings.json):
{
  "hooks": {
    "Setup": [{
      "matcher": "init",
      "hooks": [{
        "type": "command",
        "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/setup_init.py",
        "timeout": 120
      }]
    }]
  }
}
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

project_dir = os.environ.get("CLAUDE_PROJECT_DIR", ".")
log_path = Path(project_dir) / "setup.init.log"
actions = []
failures = []


def run(cmd, cwd=None, label=""):
    """Run a command, log result, return success."""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd or project_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            actions.append(f"[OK] {label}")
            return True
        else:
            failures.append(f"[FAIL] {label}: {result.stderr[:200]}")
            return False
    except Exception as e:
        failures.append(f"[FAIL] {label}: {str(e)[:200]}")
        return False


# ── 1. Backend dependencies ─────────────────────────────
backend_dir = Path(project_dir) / "apps" / "backend"
if backend_dir.exists():
    run(["uv", "sync"], cwd=str(backend_dir), label="Backend: uv sync")

# ── 2. Frontend dependencies ────────────────────────────
frontend_dir = Path(project_dir) / "apps" / "frontend"
if frontend_dir.exists():
    run(["npm", "install"], cwd=str(frontend_dir), label="Frontend: npm install")

# ── 3. Database initialization ──────────────────────────
init_db = backend_dir / "init_db.py"
if init_db.exists():
    run(
        ["uv", "run", "python", "init_db.py"],
        cwd=str(backend_dir),
        label="Database: initialized",
    )

# ── 4. Environment variables ────────────────────────────
env_sample = Path(project_dir) / ".env.sample"
env_file = Path(project_dir) / ".env"
if env_sample.exists() and not env_file.exists():
    import shutil
    shutil.copy(str(env_sample), str(env_file))
    actions.append("[OK] Environment: copied .env.sample → .env")

# ── Log results (append mode for history) ───────────────
with open(log_path, "a") as f:
    f.write(f"\n--- Init {datetime.now().isoformat()} ---\n")
    for a in actions:
        f.write(f"  {a}\n")
    for fail in failures:
        f.write(f"  {fail}\n")

# ── Return summary to Claude ────────────────────────────
print(
    json.dumps(
        {
            "summary": f"{len(actions)} succeeded, {len(failures)} failed",
            "actions": actions,
            "failures": failures,
        }
    )
)

# Exit non-zero if any failures
sys.exit(1 if failures else 0)
