# Agentic Prompting Patterns

> Patterns for structuring Claude Code commands, agents, hooks, and orchestrators. Based on real implementations from the TAC project series.

---

## The SSVA Pattern

**Specialized Self-Validating Agents** — the core architecture for trusted autonomous work.

```
Focused Agent + Specialized Validation = Trusted Automation
```

Each agent:
1. Has **one purpose** (Tactic 6: One Agent, One Prompt)
2. Has **scoped hooks** that validate its specific output
3. Can **self-correct** when a hook blocks with a reason
4. Runs in an **isolated context** (agent vs command)

---

## Commands vs Agents

| Feature | Slash Command | Subagent |
|---------|--------------|----------|
| Context | Runs in current conversation | Isolated context window |
| Parallelism | Sequential only | Can spawn N in parallel |
| Arguments | `$1`, `$2`, `$ARGUMENTS` | Infers from calling prompt |
| Invocation | `/csv-edit file.csv "fix it"` | `"Use @csv-edit-agent to..."` |
| Hooks | Frontmatter scoped | Frontmatter scoped |
| Best for | Direct logic, user-facing tasks | Loops, parallelism, isolation |

**Rule of thumb**: Commands hold the logic. Agents invoke commands and handle orchestration.

### Agent Delegation Pattern

Agents call commands via `Skill()`:

```markdown
# normalize-csv-agent.md
## Workflow
1. Find all `raw_*.csv` files in the provided directory
2. For each raw CSV file, execute: `Skill(prompt: '/normalize-csv', args: '<file_path>')`
3. Report results
```

This lets the same command be invoked directly by users OR by agents.

---

## Hook Scoping

Hooks can be **global** (settings.json) or **scoped to a command/agent** (frontmatter).

### Global Hooks (settings.json)

```json
{
  "hooks": {
    "Stop": [{
      "hooks": [{"type": "command", "command": "bash .claude/hooks/stop-lint.sh"}]
    }]
  }
}
```

### Scoped Hooks (frontmatter)

```yaml
---
hooks:
  PostToolUse:
    - matcher: "Read|Edit|Write"
      hooks:
        - type: command
          command: "uv run .claude/hooks/validators/csv-single-validator.py"
  Stop:
    - hooks:
        - type: command
          command: "uv run .claude/hooks/validators/csv-validator.py"
---
```

### Hook Placement Heuristic

| Hook Event | When It Fires | Use For |
|-----------|--------------|---------|
| `PostToolUse` | After each tool call | Per-operation validation (catches errors mid-session) |
| `Stop` | When agent completes | Final-state validation (pipeline gating) |
| `PreToolUse` | Before tool call | Security guards, path restrictions |
| `SessionStart` | Session begins | Context injection, state loading |

**Cost tradeoff**: PostToolUse fires on every operation (expensive but immediate). Stop fires once at completion (cheap but late).

---

## The Block/Retry Self-Correction Loop

When a hook blocks, the **reason string becomes Claude's next task**. This is the autonomous self-correction loop.

### Validator Protocol

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas"]
# ///

import json, sys

hook_input = json.loads(sys.stdin.read())
tool_input = hook_input.get("tool_input", {})
file_path = tool_input.get("file_path")

# Validate...
if error_found:
    # BLOCK: reason becomes Claude's next correction task
    print(json.dumps({
        "decision": "block",
        "reason": f"Missing required column 'date' in {file_path}. Add a date column."
    }))
    sys.exit(2)
else:
    # PASS: proceed
    print(json.dumps({}))
    sys.exit(0)
```

### Exit Code Semantics

| Exit Code | Meaning |
|-----------|---------|
| `0` | Pass — proceed |
| `2` | Block — stderr fed back to Claude for self-correction |
| Other | Non-blocking warning |

### Writing Good Block Reasons

```
Bad:  "Validation failed"
Good: "Missing column 'date' in raw_checkings.csv. Add a date column with format YYYY-MM-DD."

Bad:  "HTML error"
Good: "Dashboard index.html references plot_01.png but file not found in assets/. Generate the graph first."
```

The reason is literally Claude's next prompt. Write it like a clear instruction.

---

## Pipeline Orchestration

Sequential pipeline with fail-fast gating:

```markdown
# review-finances.md (orchestrator)
## Workflow
1. Setup directory structure
2. Run @normalize-csv-agent        ← each agent has Stop hooks
3. Run @categorize-csv-agent       ← if blocked, pipeline stops here
4. Run @merge-accounts-agent
5. Run /accumulate-csvs
6. Run @graph-agent (monthly)
7. Run @graph-agent (cumulative)
8. Run @generative-ui-agent
9. Open browser to view dashboard
```

**Key rule**: "Do NOT proceed to next agent if current fails."

Stop hooks enforce this — if a validator blocks at step 3, step 4 never runs.

---

## Portable Validators (uv run --script)

PEP 723 inline script metadata — zero-install validators:

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas", "beautifulsoup4", "lxml"]
# ///
```

Benefits:
- No `requirements.txt` or `pip install` step
- `uv` creates an isolated venv automatically
- Each validator is a single self-contained file
- Hook command is just: `uv run path/to/validator.py`

---

## CLAUDE.md as Variable Registry

Minimal CLAUDE.md — just shared variables:

```markdown
# Project Context
## Variables
ROOT_OPERATIONS_DIR: apps/data/2026/
```

Commands reference variables:

```markdown
## Variables
ROOT_DIR: CLAUDE.md: ROOT_OPERATIONS_DIR
MONTH_DIR: ROOT_DIR/dataset_{MONTH}/
```

**Pattern**: One source of truth. No variable duplication across commands.

---

## Session Initialization (prime.md)

Load all project context at session start:

```markdown
# prime.md
## Workflow
1. Read specs/init.md
2. Read .claude/agents/*
3. Read .claude/commands/*
4. Read .claude/hooks/*
5. Read justfile
6. Run git ls-files
7. Report: "Project context loaded. Ready."
```

**When to use**: At the start of any session where you need full project awareness.

---

## Two-Tier Tool Restriction

### Tier 1: Global (settings.json)

```json
{
  "permissions": {
    "allow": ["Bash(uv run:*)", "Bash(python:*)", "Read", "Write", "Edit"]
  }
}
```

### Tier 2: Per-Command (frontmatter)

```yaml
---
allowed-tools: Glob, Grep, Read
---
```

The per-command restriction narrows the global allowlist. A command with `allowed-tools: Read` cannot Write even if settings.json allows it.

---

## Deterministic + Generative Hybrid

Use scripts for predictable output, agents for creative output:

```markdown
# graph-agent.md
## Phase 1: Standard Graphs
Execute: `uv run scripts/generate_graphs.py <dir>`
# → 8 deterministic, reproducible graphs

## Phase 2: Novel Graphs
Analyze the data and generate creative visualizations
not covered by the standard graphs.
# → Agent-generated, unique per run
```

**Why**: Scripts give you reproducible baselines. Agents give you creative insights. Together: reliable + novel.

---

## 4 Abstraction Layers (Justfile)

```
Layer 1 — Command (Logic)         /normalize-csv file.csv
Layer 2 — Agent (Isolation)       "Use @normalize-csv-agent to..."
Layer 3 — Orchestrator (Pipeline) /review-finances january *.csv
Layer 4 — Just (Reusability)      just review-january
```

Each layer adds a capability:
- **Command**: The actual prompt + validation logic
- **Agent**: Isolated context + parallelism
- **Orchestrator**: Sequential pipeline + fail-fast gating
- **Just**: Named recipes + default arguments + composition

---

## Progressive Execution Modes

Every workflow should support three execution modes. The deterministic hook always runs; the prompt adds supervision or interaction.

```
DETERMINISTIC          AGENTIC               INTERACTIVE
claude --init          claude --init          claude --init
                       "/install"             "/install true"
───────────            ───────────            ──────────────
Hook runs              Hook runs              Hook runs
Exit                   + Read log             + Ask questions
                       + Analyze              + Adapt to answers
                       + Report               + Report
```

### When to Use Each Mode

| Mode | When | Example |
|------|------|---------|
| Deterministic | CI/CD, automated pipelines | `claude --init-only` in GitHub Actions |
| Agentic | Developer oversight, diagnostics | `claude --init "/install"` for supervised setup |
| Interactive | Onboarding, first-time setup | `claude --init "/install true"` with AskUserQuestion |

### Building Progressive Commands

```markdown
# /install
## Variables
MODE: $1

## Workflow
1. Execute `/prime` (understand codebase)
2. If MODE="true", delegate to `/install-hil` (interactive)
3. Otherwise, read `.claude/hooks/setup.init.log`
4. Analyze successes and failures
5. Write results to `app_docs/install_results.md`
6. Report: Status, What Worked, What Failed, Next Steps
```

The command adds intelligence on top of the deterministic hook. It never replaces the hook.

---

## Human-in-the-Loop (HIL) Pattern

For interactive onboarding, use `AskUserQuestion` to adapt execution:

```markdown
# /install-hil
## 5 Interactive Questions
1. **Database**: Fresh install / Keep existing / Skip
2. **Dependencies**: Full / Minimal / Skip if cached
3. **Environment Check**: Validate .env? Yes / No
4. **Environment Variables**: Set up? Yes (with questions) / Skip
5. **Documentation**: Scrape external docs? All / Choose / Skip

## Execution
Based on responses:
- Database=Fresh → DROP + CREATE
- Database=Keep → MIGRATE
- Database=Skip → nothing

## Security Rules
- NEVER read actual environment variable values
- NEVER log or display variable values
- NEVER write values to .env (user does it manually)
- Only validate existence: `grep -q "^VAR=.\+" .env`
```

**Key pattern**: Questions determine which branches of the deterministic script to run. The LLM provides guidance but scripts do the work.

---

## Living Documentation Pattern

Make documentation execute itself. The script is the source of truth; the agent provides supervision.

```
The script is the source of truth.
Agents provide supervision and context-aware guidance.
Result: Living documentation that actually executes.
```

### Implementation

1. **Hook** runs deterministic script → writes to log file (append mode)
2. **Command** reads log → analyzes → reports
3. **README** describes the pattern humans can understand
4. **Justfile** exposes named recipes for all three modes

The documentation (README + commands + hooks) is always in sync because it IS the implementation.

### Log-Based Analysis

```markdown
# /maintenance (agentic wrapper)
## Workflow
1. Execute `/prime`
2. Read `.claude/hooks/setup.maintenance.log`
3. Parse each action line for [OK] or [FAIL]
4. Write results to `app_docs/maintenance_results.md`
5. Report: Status, What Was Updated, Issues Found, Next Steps
```

Hooks always write structured logs. Agents always read and analyze logs. This decouples execution from analysis.

---

## External Documentation Scraping

Cache external docs locally for offline agent access:

```markdown
# ai_docs/README.md (index of external docs)
- cc_hooks.md: https://code.claude.com/docs/en/hooks
- just_quickstart.md: https://just.systems/man/en/quick-start.html
```

```markdown
# docs-scraper agent
## Tools: WebFetch, Write
## Workflow
1. Fetch URL using WebFetch
2. Process/reformat to markdown
3. Save to ai_docs/{filename}.md
4. Verify completeness
```

During interactive install, the agent checks freshness (`find -mtime -1`) and only re-scrapes stale docs. Scraping runs in parallel via subagent spawning.

---

## Reset Pattern (Clean State)

Every project should have a reset recipe for testing the install flow:

```just
# Remove all generated artifacts for clean install testing
reset:
    rm -rf apps/backend/.venv
    rm -rf apps/frontend/node_modules
    rm -f apps/backend/starter.db
    rm -f setup.init.log setup.maintenance.log
    echo "Clean state. Run: just init"
```

**Why**: You can't test install automation without a clean starting point. Reset + install should always produce the same result (idempotent).
