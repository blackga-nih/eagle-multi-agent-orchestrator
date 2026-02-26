#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""
Setup Maintenance hook — Deterministic dependency updates and health checks.

Triggered: `claude --maintenance`
Pattern: Progressive Execution Modes → Deterministic layer

This hook is the SOURCE OF TRUTH for maintenance tasks.
The agentic /maintenance command reads this hook's log and adds supervision.

Configuration (settings.json):
{
  "hooks": {
    "Setup": [{
      "matcher": "maintenance",
      "hooks": [{
        "type": "command",
        "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/setup_maintenance.py",
        "timeout": 60
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
log_path = Path(project_dir) / "setup.maintenance.log"
actions = []
failures = []
db_stats = {}


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


# ── 1. Backend dependency upgrade ───────────────────────
backend_dir = Path(project_dir) / "apps" / "backend"
if backend_dir.exists():
    run(["uv", "sync", "--upgrade"], cwd=str(backend_dir), label="Backend: uv sync --upgrade")

# ── 2. Frontend dependency update ───────────────────────
frontend_dir = Path(project_dir) / "apps" / "frontend"
if frontend_dir.exists():
    run(["npm", "update"], cwd=str(frontend_dir), label="Frontend: npm update")

# ── 3. Database health check ────────────────────────────
db_path = backend_dir / "starter.db"
if db_path.exists():
    try:
        import sqlite3

        conn = sqlite3.connect(str(db_path))

        # VACUUM to reclaim space
        conn.execute("VACUUM")
        actions.append("[OK] Database: VACUUM")

        # Integrity check
        result = conn.execute("PRAGMA integrity_check").fetchone()
        integrity = result[0] if result else "unknown"
        actions.append(f"[OK] Database: integrity={integrity}")

        # Table statistics
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        for (table_name,) in tables:
            count = conn.execute(f"SELECT COUNT(*) FROM [{table_name}]").fetchone()[0]
            db_stats[table_name] = count

        conn.close()
    except Exception as e:
        failures.append(f"[FAIL] Database: {str(e)[:200]}")

# ── Log results (append mode for history) ───────────────
with open(log_path, "a") as f:
    f.write(f"\n--- Maintenance {datetime.now().isoformat()} ---\n")
    for a in actions:
        f.write(f"  {a}\n")
    for fail in failures:
        f.write(f"  {fail}\n")
    if db_stats:
        f.write("  Database tables:\n")
        for table, count in db_stats.items():
            f.write(f"    {table}: {count} rows\n")

# ── Return summary to Claude ────────────────────────────
print(
    json.dumps(
        {
            "summary": f"{len(actions)} succeeded, {len(failures)} failed",
            "actions": actions,
            "failures": failures,
            "db_stats": db_stats,
        }
    )
)

sys.exit(1 if failures else 0)
