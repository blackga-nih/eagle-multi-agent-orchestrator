# TAC-Compliant Hooks Architecture

> Hooks extend agent behavior with automated triggers. TAC mandates a flat, discoverable structure.

---

## Flat Structure

TAC hooks use a flat file structure, not nested directories:

```
.claude/hooks/
  |-- pre-commit.sh          # Runs before git commit
  |-- post-commit.sh         # Runs after git commit
  |-- pre-push.sh            # Runs before git push
  |-- stop-dispatcher.sh     # Main stop hook entry point
  |-- stop-lint.sh           # Stop hook: lint changed files
  |-- stop-test.sh           # Stop hook: run affected tests
  |-- stop-expertise.sh      # Stop hook: update expertise
```

**Why flat**: The agent can Glob for `*.sh` and immediately understand all hooks. Nesting creates discovery overhead.

---

## Claude Code Hook Events (12 Events)

| Event | Can Block? | Use Case |
|-------|-----------|----------|
| SessionStart | No (inject context) | Load git state, open issues, session memory |
| SessionEnd | No | Cleanup, metrics summary |
| UserPromptSubmit | Yes (modify/reject) | Input validation, prompt enrichment |
| PreToolUse | Yes (deny tool) | Security guards, path restrictions |
| PostToolUse | No | Auto-lint on file write, metrics |
| PostToolUseFailure | No | Error tracking, retry hints |
| PermissionRequest | No | Logging permission decisions |
| Notification | No | Forward to Slack, TTS |
| SubagentStart | No | Track agent team coordination |
| SubagentStop | No | Aggregate subagent results |
| Stop | No | Turn-by-turn memory, auto-actions |
| PreCompact | No | Backup context before compression |

### Hook I/O

**Input** (JSON via stdin):
```json
{
  "session_id": "abc-123",
  "session_dir": "/path/to/.claude/sessions/abc-123",
  "transcript_path": "/path/to/transcript.jsonl"
}
```

**Output** (JSON via stdout):
```json
{
  "hookSpecificOutput": {
    "additionalContext": "Injected context for agent"
  }
}
```

**Blocking output** (PreToolUse only):
```json
{
  "hookSpecificOutput": {
    "permissionDecision": "deny",
    "message": "Reason for denial"
  }
}
```

---

## Dispatcher Pattern

The dispatcher is the orchestrator for stop hooks:

```bash
#!/bin/bash
# stop-dispatcher.sh — Routes to domain handlers based on context

CHANGED_FILES=$(git diff --name-only HEAD 2>/dev/null)

# Route to domain handlers
if echo "$CHANGED_FILES" | grep -q "test_"; then
    bash .claude/hooks/stop-test.sh
fi

if echo "$CHANGED_FILES" | grep -q "expertise.md"; then
    bash .claude/hooks/stop-expertise.sh
fi

# Always run lint
bash .claude/hooks/stop-lint.sh
```

**Key properties**:
- Single entry point for all stop hooks
- Routes based on changed files or context
- Domain handlers are independent and composable
- Non-fatal: individual handler failures don't block others

---

## Domain Handlers

Each handler owns one concern:

```bash
#!/bin/bash
# stop-test.sh — Run tests for changed test files

CHANGED_TESTS=$(git diff --name-only HEAD | grep "test_" | head -5)
for test_file in $CHANGED_TESTS; do
    python -c "import py_compile; py_compile.compile('$test_file', doraise=True)"
done
```

**Conventions**:
- Name: `stop-{domain}.sh`
- Single responsibility
- Idempotent (safe to run multiple times)
- Non-blocking (exit 0 even on non-critical failures)
- Logs to stdout for agent visibility

---

## settings.json Configuration

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [{
          "type": "command",
          "command": "uv run .claude/hooks/pre_tool_use.py"
        }]
      }
    ],
    "Stop": [
      {
        "matcher": "turn_end",
        "hooks": [{
          "type": "command",
          "command": "bash .claude/hooks/stop-dispatcher.sh"
        }]
      }
    ]
  }
}
```

**Matcher system**: Empty string = all events, `"Bash"` = Bash tool only, `"turn_end"` = turn completions.

---

## Advanced Patterns

### Stop Hook Filtering

```bash
# Only run if agent modified Python files
PYTHON_CHANGES=$(git diff --name-only HEAD | grep "\.py$" | wc -l)
if [ "$PYTHON_CHANGES" -eq 0 ]; then
    echo "No Python changes, skipping"
    exit 0
fi
```

### Hook Chaining

```
stop-dispatcher.sh
  |-> stop-lint.sh (always)
  |-> stop-test.sh (if test files changed)
  |     |-> Runs pytest for changed files
  |-> stop-expertise.sh (if expertise files changed)
```

**Rules**: Forward-only (no cycles), fail-safe (chain continues on failure), depth limit 3.

### Turn-by-Turn Memory

```bash
#!/bin/bash
# stop-memory.sh — Append turn summary to session log

MEMORY_FILE=".claude/session-memory.md"
echo "## Turn $(date +%H:%M:%S)" >> "$MEMORY_FILE"
git diff --stat HEAD >> "$MEMORY_FILE" 2>/dev/null
echo "" >> "$MEMORY_FILE"
```

### Stop Hook Guard

```bash
# Prevent recursive hook execution
if [ -n "$stop_hook_active" ]; then exit 0; fi
export stop_hook_active=1
```

---

## 7 Hook Patterns Summary

| Pattern | Event | Purpose |
|---------|-------|---------|
| Tool Blocking | PreToolUse | Deny dangerous operations |
| Context Injection | SessionStart | Enrich agent context |
| Event Forwarding | Any | Send to observability server |
| PostToolUse Validation | PostToolUse | Auto-lint after file write |
| Stop Hook Guard | Stop | Prevent recursive execution |
| Dispatcher Routing | Stop | Route to domain handlers |
| TTS Notification | Notification | Text-to-speech alerts |

---

## Setup Hooks (Install & Maintenance)

Claude Code provides `Setup` hook events triggered by `--init` and `--maintenance` CLI flags. These enable **deterministic project setup** separate from agentic sessions.

### Setup Event Configuration

```json
{
  "hooks": {
    "Setup": [
      {
        "matcher": "init",
        "hooks": [{
          "type": "command",
          "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/setup_init.py",
          "timeout": 120
        }]
      },
      {
        "matcher": "maintenance",
        "hooks": [{
          "type": "command",
          "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/setup_maintenance.py",
          "timeout": 60
        }]
      }
    ]
  }
}
```

**Matchers**: `"init"` fires on `claude --init` / `claude --init-only`. `"maintenance"` fires on `claude --maintenance`.

### Setup Init Hook (Deterministic Install)

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///

import subprocess, json, sys

log_path = "setup.init.log"
actions = []

# 1. Backend dependencies
subprocess.run(["uv", "sync"], cwd="apps/backend/", check=True)
actions.append("Backend: uv sync")

# 2. Frontend dependencies
subprocess.run(["npm", "install"], cwd="apps/frontend/", check=True)
actions.append("Frontend: npm install")

# 3. Database initialization
subprocess.run(["uv", "run", "python", "init_db.py"], cwd="apps/backend/", check=True)
actions.append("Database: initialized")

# Log results (append mode for history)
with open(log_path, "a") as f:
    f.write(f"\n--- Init ---\n")
    for a in actions:
        f.write(f"  [OK] {a}\n")

# Return summary to Claude
print(json.dumps({"summary": f"{len(actions)} actions completed", "actions": actions}))
```

### Setup Maintenance Hook

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///

import subprocess, json, sqlite3

actions = []

# 1. Upgrade dependencies
subprocess.run(["uv", "sync", "--upgrade"], cwd="apps/backend/")
actions.append("Backend: dependencies upgraded")

subprocess.run(["npm", "update"], cwd="apps/frontend/")
actions.append("Frontend: dependencies updated")

# 2. Database maintenance
conn = sqlite3.connect("apps/backend/starter.db")
conn.execute("VACUUM")
result = conn.execute("PRAGMA integrity_check").fetchone()
actions.append(f"Database: integrity={result[0]}")
conn.close()

print(json.dumps({"summary": f"{len(actions)} maintenance actions", "actions": actions}))
```

---

## SessionStart Hook (Environment Loading)

Load environment variables at session start for cross-session persistence:

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["python-dotenv"]
# ///

import json, os, sys
from dotenv import dotenv_values

env_file = os.path.join(os.environ.get("CLAUDE_PROJECT_DIR", "."), ".env")
env_vars = dotenv_values(env_file) if os.path.exists(env_file) else {}

# Write to CLAUDE_ENV_FILE for session persistence
claude_env = os.environ.get("CLAUDE_ENV_FILE", "")
if claude_env:
    with open(claude_env, "a") as f:
        for key, value in env_vars.items():
            escaped = value.replace("'", "'\\''") if value else ""
            f.write(f"export {key}='{escaped}'\n")

print(json.dumps({"loaded": len(env_vars), "keys": list(env_vars.keys())}))
```

Configuration:
```json
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
```

**Security**: Never log or display env variable values. Only validate existence with pattern matching (e.g., `grep -q "^VAR=.\+"`).

---

## Progressive Execution Modes

Three execution modes for install/maintenance, each building on the previous:

```
┌──────────────────────────────────────────────────────┐
│ DETERMINISTIC │ AGENTIC        │ INTERACTIVE          │
│ (hooks only)  │ (hook + prompt)│ (hook + questions)   │
├──────────────────────────────────────────────────────┤
│ claude --init │ claude --init  │ claude --init        │
│               │ "/install"     │ "/install true"      │
├──────────────────────────────────────────────────────┤
│ Fast          │ Supervised     │ Asks Questions       │
│ Predictable   │ Diagnostic     │ Adapts               │
│ CI-friendly   │ Reports        │ Context-aware        │
└──────────────────────────────────────────────────────┘
```

**Key insight**: The deterministic hook ALWAYS runs first. The agentic prompt reads the hook's log and adds supervision. The interactive prompt adds human-in-the-loop questions.

### Justfile Pattern

```just
# Deterministic — hook only (CI/CD)
init:
    claude --model opus --init

# Agentic — hook + prompt (supervised)
init-agentic:
    claude --model opus --init "/install"

# Interactive — hook + questions (onboarding)
init-interactive:
    claude --model opus --init "/install true"
```

---

## Hook → Prompt → Report Flow

The foundational pattern for combining deterministic execution with agentic analysis:

```
Hook (deterministic)     →  Log File        →  Prompt (agentic)
─────────────────────       ──────────          ───────────────
uv sync                     setup.init.log      Read log
npm install                                     Analyze results
init_db.py                                      Report status
```

**The script is the source of truth. The agent provides supervision and context-aware guidance.**

### Agentic Wrapper Command

```markdown
# /install
## Workflow
1. Execute `/prime` (understand codebase)
2. Read `.claude/hooks/setup.init.log`
3. Analyze successes and failures
4. Write results to `app_docs/install_results.md`
5. Report: Status, What Worked, What Failed, Next Steps
```

Result: **Living documentation that actually executes** — deterministic scripts ensure repeatability, agents ensure comprehension.

---

## Best Practices

- **Performance**: Hooks must complete within 60 seconds (Setup hooks: 120s)
- **Safety**: Always include `stop_hook_active` guard on Stop hooks
- **Dependencies**: Use `uv run` for Python hooks (fast startup)
- **Failure**: Never let hook failures block Claude's core operation
- **Testing**: Test hooks in isolation before configuring in settings.json
- **Structure**: Flat at root, only `utils/` subfolder allowed
- **Security**: Never log, display, or read actual env variable values in hooks
- **Logging**: Setup hooks should append to log files (not overwrite) for history
- **Modes**: Always support deterministic-only for CI/CD, agentic for dev oversight
