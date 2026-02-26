---
type: expert-file
parent: "[[tac/_index]]"
file-type: expertise
tac_original: true
human_reviewed: false
tags: [expert-file, mental-model, tac-methodology, tac-patterns]
last_updated: 2026-02-19T00:00:00
---

# TAC Expertise (Practical Coding Patterns)

> **How to build with TAC.** This file covers hooks, SSVA, prompting patterns, ecosystem architecture, agent team workflows, and accumulated learnings.
>
> Companion file: `tac-learning-expertise.md` covers TAC theory (8 tactics, lessons 9-27, frameworks, maturity model).

---

## Part 1: Hooks Architecture

### Flat Structure

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

### Dispatcher Pattern

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

### Domain Handlers

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

### Hook Event Reference (12 events)

| Event | Trigger | Use Case |
|-------|---------|----------|
| `PreToolUse` | Before any tool call | Block dangerous commands, validate inputs |
| `PostToolUse` | After any tool call | Log activity, analyze patterns |
| `SessionStart` | Agent session begins | Load env vars, initialize context |
| `Stop` | Agent completes turn | Auto-lint, auto-test, auto-expertise |
| `SubagentStop` | Sub-agent completes | Collect results, relay outputs |
| `PreCompact` | Before context compaction | Save critical state |
| `UserPromptSubmit` | User sends message | Enhance prompts with context |
| `Notification` | Events occur | Alert user, TTS notifications |
| `PreCommit` | Before git commit | Lint, format, validate |
| `PostCommit` | After git commit | Notify, deploy, update |
| `PrePush` | Before git push | Final validation gate |
| `Init` | `claude --init` | Setup hooks, install deps |

### Advanced Hook Patterns

**Stop Hook Filtering**: Only trigger for relevant file types:
```bash
PYTHON_CHANGES=$(git diff --name-only HEAD | grep "\.py$" | wc -l)
if [ "$PYTHON_CHANGES" -eq 0 ]; then exit 0; fi
```

**Hook Chaining**: Forward-only, fail-safe, max 3 levels deep.

**Turn-by-Turn Memory**: Hooks append to session log, loaded at next turn start.

**Setup Hooks with Matchers**: `claude --init` triggers `"matcher": "init"`, `claude --maintenance` triggers `"matcher": "maintenance"` in settings.json.

**SessionStart Env Loading**: Read .env → write to CLAUDE_ENV_FILE for persistence. Never log values.

**Progressive Execution Modes**:
- **Deterministic**: Hooks run scripts, no agent reasoning (for CI/CD)
- **Agentic**: Hooks run + agent analyzes results (for dev oversight)
- **Interactive**: Hooks + AskUserQuestion (for onboarding)

**Hook → Prompt → Report Flow**: Hooks execute deterministically → write to log → agentic prompt reads log and reports. Decouples execution from analysis.

---

## Part 2: SSVA (Specialized Self-Validating Agents)

### The Pattern

```
Focused Agent + Specialized Validation = Trusted Automation
```

Each SSVA:
1. Has **one purpose** (Tactic 6: One Agent, One Prompt)
2. Has **scoped hooks** that validate its specific output
3. Can **self-correct** when a hook blocks with a reason
4. Runs in an **isolated context** (agent vs command)

### Commands vs Agents Decision Table

| Feature | Slash Command | Subagent |
|---------|--------------|----------|
| Context | Runs in current conversation | Isolated context window |
| Parallelism | Sequential only | Can spawn N in parallel |
| Arguments | `$1`, `$2`, `$ARGUMENTS` | Infers from calling prompt |
| Invocation | `/csv-edit file.csv "fix it"` | `"Use @csv-edit-agent to..."` |
| Hooks | Frontmatter scoped | Frontmatter scoped |
| Best for | Direct logic, user-facing tasks | Loops, parallelism, isolation |

**Rule of thumb**: Commands hold the logic. Agents invoke commands and handle orchestration.

### Block/Retry Self-Correction

When a hook blocks an agent's tool call, the block reason becomes the agent's next correction task:

```
Agent: writes output.csv
Hook: BLOCKS — "Missing column 'date'. Add with format YYYY-MM-DD."
Agent: reads block reason → adds date column → retries
Hook: APPROVES
```

**Write block reasons like instructions**, not log lines.

### Pipeline Orchestration

Fail-fast sequential pipeline gating: orchestrator stops if any agent's Stop hook blocks.

```
Agent 1 (normalize) → Hook validates → PASS → Agent 2 (analyze) → Hook validates → PASS → Agent 3 (report)
                                        FAIL → Pipeline stops, reports which agent failed
```

### Portable Validators

Use `uv run --script` with PEP 723 inline deps for zero-install portable validators:

```python
# /// script
# dependencies = ["pandas"]
# ///
import pandas as pd
# ... validation logic
```

---

## Part 3: Agentic Prompting Patterns

### CLAUDE.md as Variable Registry

One source of truth for shared constants — paths, API endpoints, table names. Agents and hooks both read from CLAUDE.md.

### Session Initialization (prime.md)

One command loads all agents/commands/hooks context:

```markdown
# /prime — Load full project context
Read CLAUDE.md, glob .claude/agents/*.md, glob .claude/commands/*.md, glob .claude/hooks/*.{py,sh}
Report: "Loaded N agents, M commands, K hooks. Ready."
```

### Two-Tier Tool Restriction

1. **Global**: `settings.json` allowlist (applies to all agents)
2. **Per-command**: `allowed-tools` frontmatter narrows further

### Deterministic + Generative Hybrid

Scripts for baseline, agent for novel output. Hooks handle the deterministic part; the agentic prompt handles analysis and creative work.

### 4 Abstraction Layers

```
Command  →  Logic (what to do)
Agent    →  Isolation (separate context window)
Orchestrator  →  Pipeline (chain agents)
Just     →  Reusability (compose everything)
```

### Living Documentation

Scripts are the source of truth; agents provide supervision. Docs that execute themselves — README instructions backed by `just` recipes that actually run the steps.

### External Doc Scraping

`ai_docs/README.md` indexes URLs → docs-scraper agent fetches + caches as markdown. Freshness check with `find -mtime -1`.

### Reset Pattern

Remove all generated artifacts for clean testing: idempotent `just reset` + `just init`.

---

## Part 4: Claude Code Ecosystem Graph

### Component-Centric View

```
Claude Code Project
|
|-- CLAUDE.md                         [Class 1: Foundation]
|   |-- Project description
|   |-- Key conventions
|   |-- File references
|
|-- .claude/
|   |-- settings.json                 [Class 1: Foundation]
|   |   |-- Model preferences
|   |   |-- Allowed tools
|   |   |-- Permission overrides
|   |
|   |-- commands/                     [Class 2: Out-Loop]
|   |   |-- {command}.md              Slash commands
|   |   |-- experts/                  [Class 3: Orchestration]
|   |       |-- {domain}/
|   |           |-- _index.md         Expert overview
|   |           |-- expertise.md      Mental model
|   |           |-- question.md       Read-only Q&A
|   |           |-- plan.md           Planning command
|   |           |-- self-improve.md   Learning command
|   |           |-- plan_build_improve.md  Full workflow
|   |           |-- maintenance.md    Validation command
|   |
|   |-- agents/                       [Class 3: Orchestration]
|   |   |-- {agent-name}.md           Specialized sub-agents
|   |
|   |-- skills/                       [Class 2: Out-Loop]
|   |   |-- {skill-name}/SKILL.md     Packaged capabilities
|   |
|   |-- hooks/                        [Class 2: Out-Loop]
|   |   |-- {hook}.py or {hook}.sh    Lifecycle event handlers
|   |
|   |-- specs/                        [Ephemeral]
|       |-- {feature}-spec.md         Task-specific plans
|
|-- Source Code                       [Target of agent actions]
```

### Layer Architecture

#### Class 1: Foundation Layer
Always in context, rarely changes, high impact per token.
- `CLAUDE.md`, `.claude/settings.json`, Git config

#### Class 2: Out-Loop Layer
Loaded on demand, enables autonomy (Tactic 4), implements feedback (Tactic 5).
- Slash commands, hooks, skills, specs

#### Class 3: Orchestration Layer
Self-improving, composable across domains, approaches codebase singularity.
- Expert system, specialized agents

### Pattern Index

| Pattern | Layer | Tactics | Description |
|---------|-------|---------|-------------|
| Expert System | Class 3 | 3, 6, 13 | Structured knowledge + commands per domain |
| Hook Dispatcher | Class 2 | 4, 5, 7 | Auto-trigger domain handlers |
| Spec-Driven Build | Class 2 | 1, 4, 5 | Write spec, agent implements |
| Self-Improving Expert | Class 3 | 5, 3, 14 | Expert updates own knowledge |
| Template Scaffold | Class 2 | 3, 6 | Create instances from templates |
| Context Hierarchy | Class 1-3 | 9, 2 | CLAUDE.md > expertise > spec layering |
| Feedback Validation | Class 2 | 5, 4 | Build-test-fix loops in commands |
| Agent Team Handoff | Class 3 | 6, 12 | Orchestrator delegates to specialist agents |
| SSVA Pipeline | Class 2-3 | 5, 6, 19 | Agent + scoped hook = trusted automation |
| Progressive Modes | Class 2 | 4, 18 | Deterministic → Agentic → Interactive |
| Defense-in-Depth | Class 2 | 5, 17 | Layered PreToolUse guard hooks |

---

## Part 5: Agent Team Patterns

> Agent teams (Claude Agent SDK) replace ADW Python scripts for orchestration. The workflow patterns remain the same; the execution mechanism changes from subprocess to native SDK coordination.

### Workflow Catalog

| Workflow | Description | Key Tactics |
|----------|-------------|-------------|
| Plan-Build-Validate | Design, implement, test in sequence | 4, 5, 8 |
| ACT-LEARN-REUSE | Do work, capture learnings, apply patterns | 5, 3, 8 |
| Expert Bootstrap | Create a new expert from scratch | 3, 6, 2 |
| Hook-Driven Development | Build features triggered by hooks | 4, 7, 5 |
| Spec-to-Implementation | Write spec, agent builds it | 1, 4, 5 |
| Test-First Agentic | Define test, agent implements until green | 5, 1, 4 |
| Context Refresh | Update CLAUDE.md and expertise files | 9, 2, 14 |

### Agent Catalog

| Agent Type | Role | Example |
|-----------|------|---------|
| Supervisor | Orchestrates specialists | EAGLE supervisor with intake/legal/market/tech |
| Domain Specialist | Deep expertise in one area | Legal counsel, tech review, market intelligence |
| Tool Agent | Executes specific tool operations | S3 ops, DynamoDB CRUD, CloudWatch queries |
| Eval Agent | Runs and validates test suites | Eval expert running test suite |
| Builder Agent | Implements features from specs | Plan-build-improve workflow agent |
| Reviewer Agent | Reviews code and provides feedback | PR review, compliance check agents |
| Scout Agent | Read-only codebase analysis | Codebase exploration, context gathering |
| Meta Agent | Creates and manages other agents | Agent CRUD, team composition |

### Command Catalog

| Command | Type | Purpose |
|---------|------|---------|
| `question` | Read-only | Answer questions from expertise |
| `plan` | Planning | Design implementations |
| `self-improve` | Learning | Update expertise with findings |
| `plan_build_improve` | Full workflow | ACT-LEARN-REUSE end-to-end |
| `maintenance` | Validation | Check health and compliance |
| `add-{thing}` | Scaffold | Create new instances from templates |

### Scale Reference

| Component | Typical Count | Notes |
|-----------|--------------|-------|
| Experts | 3-10 per project | One per major domain |
| Commands per Expert | 5-7 | Standard set + domain-specific |
| Hooks | 5-15 | Flat structure, one file per hook |
| Skills | 5-20 | One per agent capability |
| Agents | 3-10 | One per specialized role |
| Workflow Patterns | 5-10 | Reusable across experts |

---

## Learnings

### patterns_that_work
- Expert system pattern (index + expertise + commands) scales cleanly across domains
- Flat hook structure with dispatcher enables easy discovery and composition
- ACT-LEARN-REUSE as default workflow captures institutional knowledge
- Frontmatter in command files enables tool discovery and metadata
- SSVA (Specialized Self-Validating Agents): scoped hooks per agent/command, not global (agentic-finance-review, 2026-02-18)
- Block/retry self-correction: hook reason string becomes Claude's next correction task (agentic-finance-review, 2026-02-18)
- `uv run --script` with PEP 723 inline deps for zero-install portable validators (agentic-finance-review, 2026-02-18)
- Agents for parallelism + isolation, Commands for logic: Skill() delegation pattern (agentic-finance-review, 2026-02-18)
- Deterministic script + generative agent hybrid: scripts for baseline, agent for novel output (agentic-finance-review, 2026-02-18)
- Fail-fast sequential pipeline gating: orchestrator stops if any agent's Stop hook blocks (agentic-finance-review, 2026-02-18)
- CLAUDE.md as minimal variable registry: one source of truth for shared constants (agentic-finance-review, 2026-02-18)
- Two-tier tool restriction: global settings.json allowlist + per-command allowed-tools narrowing (agentic-finance-review, 2026-02-18)
- prime.md session initialization: one command loads all agents/commands/hooks context (agentic-finance-review, 2026-02-18)
- Progressive Execution Modes: Deterministic (hooks) → Agentic (hook+prompt) → Interactive (hook+questions) — 3 tiers for install/maintenance (install-and-maintain, 2026-02-18)
- Hook → Prompt → Report flow: hooks execute deterministically → write to log → agentic prompt reads log and reports — decouples execution from analysis (install-and-maintain, 2026-02-18)
- Living Documentation: scripts are the source of truth, agents provide supervision — docs that execute themselves (install-and-maintain, 2026-02-18)
- Setup hooks with matchers: `claude --init` triggers `"matcher": "init"`, `claude --maintenance` triggers `"matcher": "maintenance"` in settings.json (install-and-maintain, 2026-02-18)
- SessionStart hook for env var loading: read .env → write to CLAUDE_ENV_FILE for persistence — never log values (install-and-maintain, 2026-02-18)
- Human-in-the-loop (HIL) install: AskUserQuestion for onboarding — questions determine which branches of deterministic script to run (install-and-maintain, 2026-02-18)
- External doc scraping: ai_docs/README.md indexes URLs → docs-scraper agent fetches + caches as markdown — freshness check with `find -mtime -1` (install-and-maintain, 2026-02-18)
- Reset recipe: remove all generated artifacts for clean install testing — idempotent just reset + just init (install-and-maintain, 2026-02-18)
- Agent team orchestration via Claude Agent SDK: native multi-agent coordination replaces subprocess chaining (the-o-agent, 2026-02-19)
- Defense-in-depth PreToolUse guard chains: multiple independent guards, each catching different categories (damage-control, 2026-02-19)
- 4-layer browser automation: Just → Command → Agent → Skill composition (bowser, 2026-02-19)
- E2B sandboxes for untrusted agent execution: ephemeral containers for isolation (agent-sandboxes, 2026-02-19)
- Repository-level agent delegation: fork repo, assign agent, merge back (fork-repository, 2026-02-19)
- MCP for stateful, CLI for one-shot, skills for reusable: match tool integration to usage pattern (beyond-mcp, 2026-02-19)
- Prompt format progression matches maturity level: don't write Level 7 prompts for In-Loop work (seven-levels, 2026-02-19)
- Context window mastery via recursive R&D: sweet spot is 40-60% of window (rd-deep-dive, 2026-02-19)
- Agent specialization via narrowed tools: 3 focused tools outperform 15 generic tools (domain-agents, 2026-02-19)

### patterns_to_avoid
- Deep directory nesting for hooks (breaks agent discovery)
- Kitchen-sink system prompts (violates One Agent One Prompt)
- Manual steps in agent workflows (breaks Stay Out of the Loop)
- Expertise files without self-improve command (knowledge decays)
- Vague hook block reasons like "Validation failed" — write the reason as a clear correction instruction (agentic-finance-review, 2026-02-18)
- Global hooks for agent-specific validation — scope hooks to the agent frontmatter instead (agentic-finance-review, 2026-02-18)
- Logging or displaying env variable values in hooks — only validate existence with pattern matching (install-and-maintain, 2026-02-18)
- Agentic commands that RE-EXECUTE what the hook already did — the prompt should READ the log, not re-run commands (install-and-maintain, 2026-02-18)
- ADW Python scripts for orchestration — use agent teams instead (the-o-agent, 2026-02-19)
- Single-repo isolation when agent work crosses boundaries — use fork-repository pattern (fork-repository, 2026-02-19)
- Defaulting to MCP for all tool integrations — match the approach to usage frequency/complexity (beyond-mcp, 2026-02-19)

### common_issues
- Context window overflow: too many expertise files loaded simultaneously
- Stale expertise: expertise.md not updated after significant changes
- Hook cycles: stop hooks triggering other stop hooks recursively
- Missing frontmatter: commands without allowed-tools or description metadata

### tips
- Start every new domain with the Expert Bootstrap workflow
- Run maintenance commands weekly to catch drift
- Keep CLAUDE.md under 200 lines; move details to expertise files
- Use the Core Four checklist when setting up new projects
- Use PostToolUse hooks for per-operation validation (immediate catch), Stop hooks for final-state validation (pipeline gating)
- Write block reasons like instructions, not log lines: "Missing column 'date'. Add with format YYYY-MM-DD." not "Validation failed"
- The 4 abstraction layers: Command (logic) → Agent (isolation) → Orchestrator (pipeline) → Just (reusability)
- Setup hooks always append to log files (not overwrite) — enables trend analysis across maintenance runs
- For progressive modes: always support deterministic-only for CI/CD, agentic for dev oversight, interactive for onboarding
- Hook surface area defines agent capability — more hooks = more autonomous agents
- Observability is the prerequisite for zero-touch — if you can't see it, you can't automate it
