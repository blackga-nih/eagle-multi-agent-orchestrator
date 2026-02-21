---
type: expert-file
parent: "[[tac/_index]]"
file-type: expertise
tac_original: true
human_reviewed: false
tags: [expert-file, mental-model, tac-methodology]
last_updated: 2026-02-09T00:00:00
---

# TAC Expertise (Complete Mental Model)

> **Tactical Agentic Coding (TAC)** - A methodology for agent-first software development using Claude Code. TAC treats the AI agent as the primary developer and the human as an architect/director.

---

## Part 1: The 8 Fundamental Tactics

### Tactic 1: Stop Coding

**The most important tactic.** You are no longer a programmer. You are a director.

- **Mindset shift**: Stop writing code yourself. Instead, describe what you want to the agent.
- **Your role**: Architect, reviewer, decision-maker. Not typist.
- **Anti-pattern**: Opening files and editing code by hand. If you catch yourself doing this, STOP.
- **Key insight**: Every line you type by hand is a line the agent could have written with better context, fewer bugs, and full test coverage.
- **The rule**: If you're typing code, you're doing it wrong. Type instructions instead.

### Tactic 2: Adopt the Agent's Perspective

**Think like the agent thinks.** Understand its constraints and capabilities.

- **Context window**: The agent has a finite context window. Everything you put in it competes for attention.
- **Tool access**: The agent can Read, Write, Edit, Grep, Glob, Bash. Design workflows that leverage these tools.
- **No memory between sessions**: Each conversation starts fresh. The agent relies on what's in its context: CLAUDE.md, expertise files, and what you tell it.
- **Implications**: Write clear, structured files the agent can load. Don't rely on verbal agreements or implied context.
- **Key insight**: The better your written artifacts (CLAUDE.md, expertise files, specs), the better the agent performs. Your documentation IS your codebase's intelligence.

### Tactic 3: Template Engineering

**Create reusable templates that encode your standards.**

- **What to templatize**: File structures, test patterns, command formats, commit messages, PR descriptions.
- **Why it works**: Templates give the agent a concrete pattern to follow. It fills in the blanks rather than inventing from scratch.
- **Template locations**: `.claude/commands/experts/` for expert templates, `.claude/commands/` for slash commands.
- **Key insight**: A good template is worth a thousand instructions. The agent follows patterns better than prose.
- **Example**: The eval expert's add-test.md is a template. It encodes the 8-point registration checklist so the agent never forgets a step.

### Tactic 4: Stay Out of the Loop

**Design workflows where the agent can complete tasks without asking you questions.**

- **Autonomy-first**: Give the agent enough context to make decisions on its own.
- **Decision frameworks**: Instead of "ask me which option", provide decision criteria in your instructions.
- **Fallback behavior**: Define what to do when uncertain: "If X, do Y. If unsure, default to Z."
- **Anti-pattern**: Commands that require human input at every step. Each interruption breaks agent flow.
- **Key insight**: The best agent workflows are the ones where you press enter once and come back to a completed task.

### Tactic 5: Feedback Loops

**Build feedback directly into your agent workflows.**

- **Validation steps**: After every build step, run tests. After every edit, syntax check.
- **Self-correction**: When a test fails, the agent should diagnose and fix, not just report.
- **Progression**: Plan -> Build -> Validate -> Fix -> Validate -> Done.
- **Built-in checks**: `python -c "import py_compile; ..."` after edits, `pytest` after features, `git diff` before commits.
- **Key insight**: An agent with feedback loops is self-correcting. An agent without them is a one-shot gamble.

### Tactic 6: One Agent, One Prompt

**Each agent should have a single, focused system prompt that defines its role.**

- **Specialization**: A legal review agent should only know legal review. A test agent should only know testing.
- **Prompt boundaries**: The system prompt defines what the agent CAN do and what it CANNOT do.
- **No kitchen sinks**: A prompt that tries to cover everything covers nothing well.
- **Composition over complexity**: Use multiple specialized agents rather than one omniscient agent.
- **Key insight**: Skill files in `.claude/commands/experts/` follow this principle. Each expertise.md is one domain, one focus.

### Tactic 7: Zero-Touch Deployment

**Automate everything from commit to deployment.**

- **CI/CD integration**: Agent should be able to commit, push, create PRs, and trigger pipelines.
- **No manual steps**: If there's a manual step in your pipeline, automate it or give the agent a tool for it.
- **Verification**: Agent should verify deployments, not just trigger them.
- **Key insight**: The deployment pipeline is an extension of the agent's capability. Gaps in automation are gaps in agent power.

### Tactic 8: Prioritize Agentics

**When choosing between approaches, always prefer the more agentic option.**

- **Agentic > Manual**: If something can be done by an agent, do it with an agent.
- **Automated > Scripted > Manual**: Prefer fully automated over scripted over manual.
- **Invest in tooling**: Every tool you build for the agent pays dividends across all future tasks.
- **Key insight**: Time spent making the agent more capable is the highest-leverage work you can do. One hour of tooling saves ten hours of manual work.

### 8 Tactics Memory Aid

```
S.A.T.S.F.O.Z.P
1. Stop Coding
2. Adopt Agent's Perspective
3. Template Engineering
4. Stay Out of the Loop
5. Feedback Loops
6. One Agent, One Prompt
7. Zero-Touch
8. Prioritize Agentics
```

---

## Part 2: Advanced Lessons (9-14)

### Lesson 9: Context Engineering

**The art of curating what goes into the agent's context window.**

- **CLAUDE.md**: The agent's persistent memory. Keep it lean, accurate, and up-to-date.
- **Expertise files**: Domain-specific knowledge the agent loads on demand via slash commands.
- **Spec files**: Task-specific plans created for a single workflow, consumed and archived.
- **Context budget**: Every token counts. Redundant content wastes context; missing content causes errors.
- **Hierarchy**: CLAUDE.md (always loaded) > expertise.md (loaded by command) > spec files (loaded per task).
- **Key principle**: Context engineering is the most important skill in agentic development. The agent is only as good as its context.

### Lesson 10: Prompt Engineering

**Crafting effective prompts for agent system prompts, commands, and instructions.**

- **Be declarative, not procedural**: Tell the agent WHAT, not HOW. "Create a test that validates S3 operations" not "Open the file, go to line 200, add a function..."
- **Use structured formats**: Tables, checklists, and code blocks are parsed better than prose.
- **Constraints over instructions**: "Never modify files outside the test directory" is stronger than "Please be careful."
- **Role definition**: Start system prompts with a clear role. "You are an EAGLE SDK evaluation specialist."
- **Anti-patterns**: Vague instructions, implicit context, assuming the agent remembers previous conversations.

### Lesson 11: Specialized Agents

**Creating purpose-built agents for specific domains.**

- **Domain isolation**: Each agent owns one domain. Legal agent, test agent, deployment agent.
- **Skill files**: Encode domain expertise in structured markdown that the agent loads as system prompt.
- **Expert pattern**: The `.claude/commands/experts/` directory structure IS the specialization pattern.
- **Agent definition**: Name, model, system prompt, tools, and handoff rules.
- **Key insight**: A specialist agent outperforms a generalist on every domain-specific task.

### Lesson 12: Multi-Agent Orchestration

**Coordinating multiple specialized agents to complete complex workflows.**

- **Supervisor pattern**: One orchestrator agent delegates to specialist agents.
- **Handoff protocol**: Clear input/output contracts between agents.
- **Sequential vs parallel**: Use sequential for dependent tasks, parallel for independent tasks.
- **Context passing**: Each agent gets only the context it needs, not the full conversation.
- **EAGLE example**: Supervisor agent delegates to intake, legal, market, and tech review agents.

### Lesson 13: Agent Experts

**The expert system pattern for organizing agent knowledge.**

- **Structure**: `_index.md` (overview) + `expertise.md` (mental model) + command files (actions).
- **Commands**: question (read-only), plan (design), self-improve (learn), plan_build_improve (full workflow), maintenance (validate).
- **Self-improving**: Experts update their own expertise.md after completing tasks (ACT-LEARN-REUSE).
- **Composable**: Multiple experts can be invoked in sequence for cross-domain tasks.
- **Discovery**: `_index.md` lists available commands. Agents can discover expert capabilities.

### Lesson 14: Codebase Singularity

**The end state where the codebase fully describes itself to the agent.**

- **Self-describing**: Every component has documentation the agent can find and understand.
- **Self-maintaining**: Experts self-improve, hooks auto-trigger, tests auto-run.
- **Self-extending**: The agent can add new experts, commands, and tests using existing patterns as templates.
- **Convergence**: As the codebase becomes more self-describing, agent performance asymptotically approaches human-level on all tasks.
- **Key insight**: The codebase singularity is not a destination, it's a direction. Every improvement moves you closer.

---

## Part 3: Reference Catalogs

### ADW (Agentic Development Workflow) Patterns

ADWs are standardized workflows that combine TAC tactics into repeatable processes.

| ADW | Description | Key Tactics |
|-----|-------------|-------------|
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
| Eval Agent | Runs and validates test suites | Eval expert running server/tests/test_eagle_sdk_eval.py |
| Builder Agent | Implements features from specs | Plan-build-improve workflow agent |
| Reviewer Agent | Reviews code and provides feedback | PR review, compliance check agents |

### Command Catalog

Standard commands available across experts:

| Command | Type | Purpose |
|---------|------|---------|
| `question` | Read-only | Answer questions from expertise |
| `plan` | Planning | Design implementations |
| `self-improve` | Learning | Update expertise with findings |
| `plan_build_improve` | Full workflow | ACT-LEARN-REUSE end-to-end |
| `maintenance` | Validation | Check health and compliance |
| `add-{thing}` | Scaffold | Create new instances from templates |

### Hook Catalog

| Hook Type | Trigger | Purpose |
|-----------|---------|---------|
| PreCommit | Before git commit | Lint, format, validate |
| PostCommit | After git commit | Notify, deploy, update |
| PrePush | Before git push | Final validation gate |
| Stop | Agent completes turn | Auto-actions after agent response |
| Notification | External event | React to CI/CD, alerts |

### Scale Reference

| Component | Typical Count | Notes |
|-----------|--------------|-------|
| Experts | 3-10 per project | One per major domain |
| Commands per Expert | 5-7 | Standard set + domain-specific |
| Hooks | 5-15 | Flat structure, one file per hook |
| Skills/Prompts | 5-20 | One per agent role |
| ADW Patterns | 5-10 | Reusable across experts |

---

## Part 4: Core Frameworks Summary

### PITER Framework

**P**lan - **I**mplement - **T**est - **E**valuate - **R**efine

A sequential framework for feature development:

```
PLAN       Define what to build, write spec
IMPLEMENT  Agent builds the feature
TEST       Run tests, validate behavior
EVALUATE   Assess quality, check compliance
REFINE     Iterate based on evaluation
```

- Used for: New feature development, major refactors
- Tactic alignment: Stop Coding (1), Feedback Loops (5), Stay Out Loop (4)

### R&D Framework

**R**esearch - **D**evelop

A lightweight two-phase framework for exploration:

```
RESEARCH   Investigate the codebase, read docs, understand patterns
DEVELOP    Build the solution informed by research
```

- Used for: Bug investigation, unfamiliar codebases, exploratory work
- Tactic alignment: Adopt Agent's Perspective (2), Stop Coding (1)

### ACT-LEARN-REUSE Framework

The core TAC improvement cycle:

```
ACT    ->  Execute the task (build, test, deploy)
LEARN  ->  Capture what worked and what didn't (update expertise.md)
REUSE  ->  Apply patterns to future tasks (template, reference)
```

- Used for: Every task. This is the default operating cycle.
- Tactic alignment: Feedback Loops (5), Template Engineering (3), Prioritize Agentics (8)
- Implementation: `self-improve` command is the LEARN step. `plan` command is the REUSE step.

### Core Four

The four essential files for any Claude Code project:

| File | Purpose | Always Loaded |
|------|---------|--------------|
| `CLAUDE.md` | Project-level agent instructions | Yes |
| `.claude/commands/` | Slash commands for agent actions | On invocation |
| `.claude/commands/experts/` | Expert knowledge system | On invocation |
| `.claude/settings.json` | Claude Code configuration | Yes |

- These four establish the minimum viable agentic codebase.
- Everything else builds on top of this foundation.

### 8 Tactics Memory Aid (Expanded)

```
Tactic  Mnemonic     One-Liner
------  ----------   ------------------------------------------
1       STOP         Don't type code, type instructions
2       ADOPT        Think like the agent, design for its constraints
3       TEMPLATE     Encode patterns in reusable templates
4       STAY OUT     Let the agent work without interruption
5       FEEDBACK     Build validation into every workflow
6       ONE:ONE      One agent, one focused prompt
7       ZERO-TOUCH   Automate from commit to deploy
8       PRIORITIZE   Always choose the more agentic option
```

---

## Part 5: TAC-Compliant Hooks Architecture

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

---

## Part 6: Advanced Hook Patterns

### Stop Hook Filtering

Filter which stop hooks run based on context:

```bash
# Only run if agent modified Python files
PYTHON_CHANGES=$(git diff --name-only HEAD | grep "\.py$" | wc -l)
if [ "$PYTHON_CHANGES" -eq 0 ]; then
    echo "No Python changes, skipping test hooks"
    exit 0
fi
```

**Filtering strategies**:
- File extension filtering (only trigger for relevant file types)
- Directory filtering (only trigger for specific paths)
- Content filtering (only trigger if specific patterns changed)
- Time filtering (don't trigger if last run was < N seconds ago)

### Hook Chaining

Hooks can trigger other hooks in sequence:

```
stop-dispatcher.sh
  |-> stop-lint.sh (always)
  |-> stop-test.sh (if test files changed)
  |     |-> Runs pytest for changed files
  |     |-> If tests fail, triggers stop-fix.sh
  |-> stop-expertise.sh (if expertise files changed)
        |-> Validates frontmatter
        |-> Checks for broken references
```

**Chaining rules**:
- Forward-only: hooks should not create cycles
- Fail-safe: chain continues even if one handler fails
- Depth limit: max 3 levels of chaining to prevent runaway
- Logging: each handler logs its invocation for debugging

### Turn-by-Turn Memory

Using hooks to maintain agent context across turns:

```bash
#!/bin/bash
# stop-memory.sh — Append turn summary to session log

MEMORY_FILE=".claude/session-memory.md"

# Append timestamp and summary of changes
echo "## Turn $(date +%H:%M:%S)" >> "$MEMORY_FILE"
git diff --stat HEAD >> "$MEMORY_FILE" 2>/dev/null
echo "" >> "$MEMORY_FILE"
```

**Pattern**: The session memory file is loaded into context at the start of each turn, giving the agent awareness of what happened in previous turns within the same session.

**Important**: Session memory is ephemeral (per-session). Permanent learnings go into expertise.md via self-improve.

---

## Part 7: Claude Code Ecosystem Graph

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
|   |   |   |-- {domain}/
|   |   |   |   |-- _index.md         Expert overview
|   |   |   |   |-- expertise.md      Mental model
|   |   |   |   |-- question.md       Read-only Q&A
|   |   |   |   |-- plan.md           Planning command
|   |   |   |   |-- self-improve.md   Learning command
|   |   |   |   |-- plan_build_improve.md  Full workflow
|   |   |   |   |-- maintenance.md    Validation command
|   |
|   |-- hooks/                        [Class 2: Out-Loop]
|   |   |-- pre-commit.sh
|   |   |-- stop-dispatcher.sh
|   |   |-- stop-{domain}.sh
|   |
|   |-- specs/                        [Ephemeral]
|       |-- {feature}-spec.md         Task-specific plans
|
|-- Source Code                       [Target of agent actions]
|   |-- app/
|   |-- tests/
|   |-- frontend/
```

### Layer Architecture

#### Class 1: Foundation Layer

Components that are always loaded and define the project baseline.

| Component | File | Purpose |
|-----------|------|---------|
| Project Memory | `CLAUDE.md` | Always-on agent instructions |
| Settings | `.claude/settings.json` | Tool permissions, model config |
| Git Config | `.gitignore`, `.gitattributes` | Repository conventions |

**Properties**: Always in context, rarely changes, high impact per token.

#### Class 2: Out-Loop Layer

Components that extend agent capability without requiring human interaction.

| Component | File Pattern | Purpose |
|-----------|-------------|---------|
| Slash Commands | `.claude/commands/*.md` | On-demand agent actions |
| Hooks | `.claude/hooks/*.sh` | Automated triggers |
| Specs | `.claude/specs/*.md` | Task-specific context |

**Properties**: Loaded on demand, enables autonomy (Tactic 4), implements feedback (Tactic 5).

#### Class 3: Orchestration Layer

Components that enable multi-domain, self-improving agent behavior.

| Component | File Pattern | Purpose |
|-----------|-------------|---------|
| Expert Index | `experts/{domain}/_index.md` | Expert discovery and routing |
| Expertise | `experts/{domain}/expertise.md` | Domain mental models |
| Expert Commands | `experts/{domain}/{action}.md` | Domain-specific actions |

**Properties**: Self-improving (ACT-LEARN-REUSE), composable across domains, approaches codebase singularity (Lesson 14).

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
| Multi-Agent Handoff | Class 3 | 6, 12 | Supervisor delegates to specialists |

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

### patterns_to_avoid
- Deep directory nesting for hooks (breaks agent discovery)
- Kitchen-sink system prompts (violates One Agent One Prompt)
- Manual steps in agent workflows (breaks Stay Out of the Loop)
- Expertise files without self-improve command (knowledge decays)
- Vague hook block reasons like "Validation failed" — write the reason as a clear correction instruction (agentic-finance-review, 2026-02-18)
- Global hooks for agent-specific validation — scope hooks to the agent frontmatter instead (agentic-finance-review, 2026-02-18)
- Logging or displaying env variable values in hooks — only validate existence with pattern matching (install-and-maintain, 2026-02-18)
- Agentic commands that RE-EXECUTE what the hook already did — the prompt should READ the log, not re-run commands (install-and-maintain, 2026-02-18)

### common_issues
- Context window overflow: too many expertise files loaded simultaneously
- Stale expertise: expertise.md not updated after significant changes
- Hook cycles: stop hooks triggering other stop hooks recursively
- Missing frontmatter: commands without allowed-tools or description metadata

### tips
- Start every new domain with the Expert Bootstrap ADW
- Run maintenance commands weekly to catch drift
- Keep CLAUDE.md under 200 lines; move details to expertise files
- Use the Core Four checklist when setting up new projects
- Use PostToolUse hooks for per-operation validation (immediate catch), Stop hooks for final-state validation (pipeline gating)
- Write block reasons like instructions, not log lines: "Missing column 'date'. Add with format YYYY-MM-DD." not "Validation failed"
- The 4 abstraction layers: Command (logic) → Agent (isolation) → Orchestrator (pipeline) → Just (reusability)
- Setup hooks always append to log files (not overwrite) — enables trend analysis across maintenance runs
- For progressive modes: always support deterministic-only for CI/CD, agentic for dev oversight, interactive for onboarding
