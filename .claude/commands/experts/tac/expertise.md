---
type: expert-file
parent: "[[tac/_index]]"
file-type: expertise
tac_original: true
human_reviewed: false
tags: [expert-file, mental-model, tac-methodology]
last_updated: 2026-02-25T00:00:00
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
- **Tool access**: The agent can Read, Write, Edit, Grep, Glob, Bash, Task (subagents). Design workflows that leverage these tools.
- **No memory between sessions**: Each conversation starts fresh. The agent relies on what's in its context: CLAUDE.md, expertise files, and what you tell it.
- **Implications**: Write clear, structured files the agent can load. Don't rely on verbal agreements or implied context.
- **Key insight**: The better your written artifacts (CLAUDE.md, expertise files, agent definitions, specs), the better the agent performs. Your documentation IS your codebase's intelligence.

### Tactic 3: Template Engineering

**Create reusable templates that encode your standards.**

- **What to templatize**: File structures, test patterns, command formats, commit messages, PR descriptions, agent definitions.
- **Why it works**: Templates give the agent a concrete pattern to follow. It fills in the blanks rather than inventing from scratch.
- **Template locations**: `.claude/commands/experts/` for expert templates, `.claude/commands/` for slash commands, `.claude/agents/` for agent definitions.
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
- **Agent definition files**: `.claude/agents/{name}.md` with YAML frontmatter (name, model, color, tools, description) + markdown body.
- **Key insight**: Agent `.md` files in `.claude/agents/` are the runtime implementation of this principle. Each file IS one agent, one prompt.

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
- **Agent definitions**: `.claude/agents/*.md` files with YAML frontmatter that configure model, tools, and specialized system prompts.
- **Spec files**: Task-specific plans created for a single workflow, consumed and archived.
- **Context budget**: Every token counts. Redundant content wastes context; missing content causes errors.
- **Hierarchy**: CLAUDE.md (always loaded) > agent definitions (auto-matched) > expertise.md (loaded by command) > spec files (loaded per task).
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
- **Agent definition files**: `.claude/agents/{name}.md` with YAML frontmatter defines runtime agent configuration.
- **Agent frontmatter**: `name`, `description` (includes keyword triggers for auto-matching), `model` (opus/sonnet), `color`, `tools`, optional `skills`.
- **Key insight**: A specialist agent outperforms a generalist on every domain-specific task.

### Lesson 12: Multi-Agent Orchestration

**Coordinating multiple specialized agents to complete complex workflows.**

- **Supervisor pattern**: One orchestrator agent delegates to specialist agents.
- **Handoff protocol**: Clear input/output contracts between agents.
- **Sequential vs parallel**: Use sequential for dependent tasks, parallel for independent tasks.
- **Parallel execution**: Use the Task tool to launch multiple background agents simultaneously. The `/parallel_subagents` command codifies this pattern.
- **Context passing**: Each agent gets only the context it needs, not the full conversation.
- **EAGLE example**: Supervisor agent delegates to intake, legal, market, and tech review agents. Expert agents (14 `.claude/agents/*.md` files) cover all domains.

### Lesson 13: Agent Experts

**The expert system pattern for organizing agent knowledge.**

- **Structure**: `_index.md` (overview) + `expertise.md` (mental model) + command files (actions).
- **Commands**: question (read-only), plan (design), self-improve (learn), plan_build_improve (full workflow), maintenance (validate).
- **Self-improving**: Experts update their own expertise.md after completing tasks (ACT-LEARN-REUSE).
- **Composable**: Multiple experts can be invoked in sequence for cross-domain tasks.
- **Discovery**: `_index.md` lists available commands. Agents can discover expert capabilities.
- **Dual representation**: Each expert domain has both a command-based interface (`.claude/commands/experts/{domain}/`) AND an agent definition (`.claude/agents/{domain}-expert-agent.md`).

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
| Plan-Build-Review | Human gate after build | 4, 5, 1 |
| Plan-Build-Test | Feature with automated test suite | 4, 5, 8 |
| Plan-Build-Test-Review | Full SDLC, highest quality | 4, 5, 1 |
| ACT-LEARN-REUSE | Do work, capture learnings, apply patterns | 5, 3, 8 |
| Expert Bootstrap | Create a new expert from scratch | 3, 6, 2 |
| Hook-Driven Development | Build features triggered by hooks | 4, 7, 5 |
| Spec-to-Implementation | Write spec, agent builds it | 1, 4, 5 |
| Test-First Agentic | Define test, agent implements until green | 5, 1, 4 |
| Context Refresh | Update CLAUDE.md and expertise files | 9, 2, 14 |
| Parallel Agent Sweep | Launch N agents for independent subtasks | 8, 12, 4 |

### Agent Catalog

| Agent Type | Role | Example |
|-----------|------|---------|
| Supervisor | Orchestrates specialists | EAGLE supervisor with intake/legal/market/tech |
| Domain Expert | Deep expertise + agent definition | `backend-expert-agent.md`, `aws-expert-agent.md` |
| Domain Specialist | Deep expertise in one area | Legal counsel, tech review, market intelligence |
| Tool Agent | Executes specific tool operations | S3 ops, DynamoDB CRUD, CloudWatch queries |
| Eval Agent | Runs and validates test suites | Eval expert running server/tests/test_eagle_sdk_eval.py |
| Builder Agent | Implements features from specs | Plan-build-improve workflow agent |
| Reviewer Agent | Reviews code and provides feedback | `review.md` command, compliance check agents |
| Formatter Agent | Standardizes documentation output | Scribe agent (markdown, Marp PPT, Excalidraw) |
| Browser Agent | Web automation and screenshots | Claude Bowser agent (single instance only) |
| Composer Agent | Assembles blueprints from primitives | TAC expert agent (this expert) |

### EAGLE Agent Inventory (`.claude/agents/`)

14 agent definition files as of 2026-02-25:

| Agent File | Domain | Model |
|-----------|--------|-------|
| `aws-expert-agent.md` | AWS/CDK infrastructure | sonnet |
| `backend-expert-agent.md` | FastAPI backend | sonnet |
| `claude-sdk-expert-agent.md` | Claude Agent SDK | sonnet |
| `cloudwatch-expert-agent.md` | CloudWatch telemetry | sonnet |
| `deployment-expert-agent.md` | Deploy/CI-CD | sonnet |
| `eval-expert-agent.md` | Eval suite | sonnet |
| `frontend-expert-agent.md` | Next.js frontend | sonnet |
| `git-expert-agent.md` | Git workflow | sonnet |
| `hooks-expert-agent.md` | Claude Code hooks | sonnet |
| `tac-expert-agent.md` | TAC methodology/composer | opus |
| `scribe.md` | Documentation formatting | sonnet |
| `claude-bowser-agent.md` | Browser automation | opus |
| `bowser-qa-agent.md` | Browser QA testing | opus |
| `playwright-bowser-agent.md` | Playwright browser tests | opus |

### Command Catalog

#### Expert Commands (per domain)

| Command | Type | Purpose |
|---------|------|---------|
| `question` | Read-only | Answer questions from expertise |
| `plan` | Planning | Design implementations |
| `self-improve` | Learning | Update expertise with findings |
| `plan_build_improve` | Full workflow | ACT-LEARN-REUSE end-to-end |
| `maintenance` | Validation | Check health and compliance |
| `add-{thing}` | Scaffold | Create new instances from templates |

#### Top-Level Commands (`.claude/commands/`)

| Command | Purpose |
|---------|---------|
| `plan.md` | Full plan with phases, acceptance criteria, validation commands |
| `quick-plan.md` | Lightweight plan (sonnet model, simpler format) |
| `build.md` | Execute a plan file top-to-bottom with validation |
| `review.md` | Risk-tiered code review from git diffs (opus model) |
| `fix.md` | Fix identified issues |
| `code-review.md` | Full 30-minute code review presentation (opus, delegates to Scribe) |
| `scribe.md` | Documentation standardizer (markdown, Marp, Excalidraw) |
| `parallel_subagents.md` | Launch N parallel agents via Task tool |
| `question.md` | Read-only research query |
| `check-aws.md` | AWS resource validation |
| `check-envs.md` | Environment variable validation |

### Hook Catalog

Claude Code hook events (Python-based, configured in `settings.json`):

| Hook Event | Timing | Can Block? | Purpose |
|-----------|--------|------------|---------|
| PreToolUse | Before tool executes | Yes (deny) | Security guards, write guards |
| PostToolUse | After tool succeeds | No | Lint-on-save, observability |
| PostToolUseFailure | After tool fails | No | Error tracking |
| SessionStart | Session begins | No (inject context) | Env loading, git state |
| SessionEnd | Session ends | No | Cleanup |
| UserPromptSubmit | User sends prompt | Yes (modify/reject) | Prompt validation |
| Stop | Response complete | No | Turn memory, TTS, summaries |
| SubagentStart | Subagent spawned | No | Agent tracking |
| SubagentStop | Subagent finishes | No | Transcript capture |
| PreCompact | Context compaction | No | Transcript backup |
| PermissionRequest | Permission needed | No | Permission routing |
| Notification | User interaction needed | No | Alert routing |

### Scale Reference (EAGLE project actuals, 2026-02-25)

| Component | Count | Notes |
|-----------|-------|-------|
| Expert Domains | 10 | frontend, backend, aws, claude-sdk, deployment, cloudwatch, eval, git, tac, hooks |
| Agent Definitions | 14 | `.claude/agents/*.md` files |
| Top-Level Commands | 11 | `.claude/commands/*.md` files |
| Commands per Expert | 5-7 | Standard set + domain-specific |
| Spec Files | 26 | `.claude/specs/*.md` (chronological audit trail) |
| Eval Tests | 38 | 3 layers in test_eagle_sdk_eval.py |
| Test Files | 6 | server/tests/test_*.py |
| EAGLE Plugin Agents | 8 | eagle-plugin/agents/ (supervisor + 7 specialists) |
| EAGLE Plugin Skills | 5 | eagle-plugin/skills/ |
| MCP Servers | 1 | Atlassian (settings.json) |

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

### Core Five

The five essential structural components for a mature Claude Code project:

| Component | Location | Purpose | Always Loaded |
|-----------|----------|---------|--------------|
| Project Memory | `CLAUDE.md` | Project-level agent instructions | Yes |
| Settings | `.claude/settings.json` | Tool permissions, hooks, MCP servers | Yes |
| Slash Commands | `.claude/commands/` | On-demand agent actions | On invocation |
| Expert System | `.claude/commands/experts/` | Domain knowledge + self-improvement | On invocation |
| Agent Definitions | `.claude/agents/` | Specialized agent configurations | Auto-matched by description keywords |

- The first four establish the minimum viable agentic codebase ("Core Four").
- Agent definitions (`.claude/agents/`) are the fifth layer that enables multi-agent orchestration and keyword-based auto-dispatch.

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

### Python-Based Hook System

TAC hooks are now Python scripts configured in `.claude/settings.json`, not shell scripts. Each hook receives JSON via stdin and returns JSON via stdout.

```
.claude/hooks/
  |-- pre_tool_use.py       # PreToolUse: security guards, write guards
  |-- post_tool_use.py      # PostToolUse: lint-on-save, observability
  |-- session_start.py      # SessionStart: context injection, env loading
  |-- stop.py               # Stop: turn memory, TTS, summaries
  |-- subagent_stop.py      # SubagentStop: transcript capture
  |-- send_event.py         # Universal: event forwarding to observability
  |-- utils/                # Only allowed subfolder
  |   |-- constants.py      # Session/log management
  |   |-- dispatcher.py     # Pattern-based routing
  |-- validators/           # Stop hook validators
```

**Why flat**: The agent can Glob for `*.py` and immediately understand all hooks. Nesting beyond `utils/` and `validators/` creates discovery overhead.

### settings.json Configuration

Hooks are registered in `.claude/settings.json` under the `hooks` key:

```json
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "",
      "hooks": [{"type": "command", "command": "python .claude/hooks/pre_tool_use.py"}]
    }],
    "Stop": [{
      "matcher": "turn_end",
      "hooks": [{"type": "command", "command": "python .claude/hooks/stop.py --on-turn"}]
    }]
  }
}
```

### Matcher System

| Matcher | Scope | Example |
|---------|-------|---------|
| `""` (empty) | All events of this type | Catch-all handler |
| `"Bash"` | Only Bash tool calls | PreToolUse for shell commands |
| `"Write"` | Only Write tool calls | PostToolUse for file validation |
| `"turn_end"` | Only turn completions | Stop hook for turn memory |

### Dispatcher Pattern

```python
# utils/dispatcher.py
PRE_TOOL_HANDLERS = {
    "Bash": [("dangerous_pattern", "dev.dangerous_blocker", "handle")],
    "Write": [(".env", "dev.env_write_guard", "handle")],
}
POST_TOOL_HANDLERS = {
    "Write": [(".py", "dev.ruff_linter", "handle")],
    "Edit":  [(".py", "dev.ruff_linter", "handle")],
}
```

**Key properties**:
- Single entry point per event type
- Routes based on tool name and input patterns
- Domain handlers are independent and composable
- Non-fatal: individual handler failures don't block others

### Hook Blocking

To block a tool call from PreToolUse:

```python
import json, sys

data = json.load(sys.stdin)
command = data.get("tool_input", {}).get("command", "")
if "rm -rf" in command:
    print(json.dumps({
        "hookSpecificOutput": {
            "permissionDecision": "deny",
            "reason": "Blocked: rm -rf is not allowed"
        }
    }))
sys.exit(0)
```

---

## Part 6: Advanced Hook Patterns

### Stop Hook Guard

Prevent infinite loops when Stop hooks trigger Claude to continue:

```python
import os, sys

GUARD = "stop_hook_active"
if os.environ.get(GUARD):
    sys.exit(0)  # Already running, skip
os.environ[GUARD] = "1"
try:
    handle_stop(data)
finally:
    del os.environ[GUARD]
```

### Agent-Specific Hooks

Agents can define their own hooks in YAML frontmatter:

```markdown
---
name: builder
model: opus
hooks:
  PostToolUse:
    - matcher: "Write"
      hooks: [{ type: "command", command: "ruff check {file}" }]
---
```

### Context Injection (SessionStart)

Load development context at session start:

```python
def handle(session_data):
    context = [f"Branch: {get_git_branch()}", f"Uncommitted: {get_uncommitted_files()}"]
    return {"hookSpecificOutput": {"additionalContext": "\n".join(context)}}
```

### Turn-by-Turn Memory (Stop)

Capture learnings at each turn boundary using the Stop hook with `turn_end` matcher. Session memory is ephemeral (per-session). Permanent learnings go into expertise.md via self-improve.

### Builder/Validator Pattern

| Agent | Tools | Purpose |
|-------|-------|---------|
| **Builder** | Write, Edit | Execute tasks, PostToolUse validates |
| **Validator** | Read, Grep, Glob only | Read-only verification of builder output |

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
|   |   |-- Hook configuration
|   |   |-- MCP server connections
|   |   |-- Permissions
|   |
|   |-- agents/                       [Class 3: Orchestration]
|   |   |-- {domain}-expert-agent.md  Agent definitions (14 files)
|   |   |-- scribe.md                 Formatter agent
|   |   |-- claude-bowser-agent.md    Browser automation agent
|   |
|   |-- commands/                     [Class 2: Out-Loop]
|   |   |-- plan.md                   Plan command
|   |   |-- build.md                  Build command
|   |   |-- review.md                 Review command
|   |   |-- code-review.md            Full code review presentation
|   |   |-- scribe.md                 Documentation formatter
|   |   |-- parallel_subagents.md     Parallel agent launcher
|   |   |-- {other}.md               Additional slash commands
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
|   |   |-- pre_tool_use.py           Python hook scripts
|   |   |-- post_tool_use.py
|   |   |-- stop.py
|   |   |-- utils/                    Dispatcher, constants
|   |
|   |-- specs/                        [Ephemeral]
|       |-- {timestamp}-{type}-{slug}-v{N}.md   Versioned plans
|
|-- Source Code                       [Target of agent actions]
|   |-- server/app/                   FastAPI backend
|   |-- client/                       Next.js frontend
|   |-- infrastructure/cdk-eagle/     CDK stacks
|   |-- eagle-plugin/                 Agent/skill definitions
```

### Layer Architecture

#### Class 1: Foundation Layer

Components that are always loaded and define the project baseline.

| Component | File | Purpose |
|-----------|------|---------|
| Project Memory | `CLAUDE.md` | Always-on agent instructions |
| Settings | `.claude/settings.json` | Hooks, MCP servers, permissions |
| Git Config | `.gitignore`, `.gitattributes` | Repository conventions |

**Properties**: Always in context, rarely changes, high impact per token.

#### Class 2: Out-Loop Layer

Components that extend agent capability without requiring human interaction.

| Component | File Pattern | Purpose |
|-----------|-------------|---------|
| Slash Commands | `.claude/commands/*.md` | On-demand agent actions |
| Hooks | `.claude/hooks/*.py` | Automated lifecycle triggers (Python) |
| Specs | `.claude/specs/*.md` | Task-specific context (versioned) |

**Properties**: Loaded on demand, enables autonomy (Tactic 4), implements feedback (Tactic 5).

#### Class 3: Orchestration Layer

Components that enable multi-domain, self-improving, multi-agent behavior.

| Component | File Pattern | Purpose |
|-----------|-------------|---------|
| Agent Definitions | `.claude/agents/*.md` | Runtime agent configs with model/tools/keywords |
| Expert Index | `experts/{domain}/_index.md` | Expert discovery and routing |
| Expertise | `experts/{domain}/expertise.md` | Domain mental models |
| Expert Commands | `experts/{domain}/{action}.md` | Domain-specific actions |

**Properties**: Self-improving (ACT-LEARN-REUSE), composable across domains, auto-matched by description keywords, approaches codebase singularity (Lesson 14).

### Pattern Index

| Pattern | Layer | Tactics | Description |
|---------|-------|---------|-------------|
| Expert System | Class 3 | 3, 6, 13 | Structured knowledge + commands per domain |
| Agent Definition | Class 3 | 6, 11, 12 | `.claude/agents/*.md` with frontmatter config |
| Parallel Agent Sweep | Class 3 | 8, 12, 4 | Task tool launches N background agents |
| Hook Dispatcher | Class 2 | 4, 5, 7 | Auto-trigger domain handlers via settings.json |
| Spec-Driven Build | Class 2 | 1, 4, 5 | Write spec, agent implements via `/build` |
| Self-Improving Expert | Class 3 | 5, 3, 14 | Expert updates own knowledge |
| Template Scaffold | Class 2 | 3, 6 | Create instances from templates |
| Context Hierarchy | Class 1-3 | 9, 2 | CLAUDE.md > agents > expertise > spec layering |
| Feedback Validation | Class 2 | 5, 4 | Build-test-fix loops in commands |
| Multi-Agent Handoff | Class 3 | 6, 12 | Supervisor delegates to specialists |
| Scribe Delegation | Class 2-3 | 3, 8 | Code-review delegates to Scribe for formatting |
| File Traceability | Class 2 | 3, 7 | `{timestamp}-{type}-{slug}-v{N}.{ext}` naming |

---

## Part 8: Eval Architecture

### EAGLE Eval Suite Structure

The eval suite (`server/tests/test_eagle_sdk_eval.py`) has 38 tests across 3 layers:

| Range | Layer | Focus |
|-------|-------|-------|
| Tests 1-6 | SDK Patterns | Sessions, resume, context, traces, cost, subagents |
| Tests 7-15 | Skill Validation | OA intake, legal, market, tech, public, doc gen, supervisor chain |
| Tests 16-20 | Layer 1: AWS Infrastructure | S3 ops, DynamoDB CRUD, CloudWatch logs, doc gen, CW E2E |
| Tests 21-27 | UC Workflows | Micro-purchase, option exercise, contract mod, CO review, close-out, shutdown, scoring |
| Test 28 | SDK Architecture | Skill-to-subagent orchestration via AgentDefinition |
| Tests 29-33 | Layer 2: Requirements Matrix | Canonical acquisition scenario correctness |
| Tests 34-38 | Layer 3: SDK Path AWS Integration | Full SDK-to-MCP-to-AWS tool path validation |

### Additional Test Files

| File | Tests | Focus |
|------|-------|-------|
| `test_eagle_sdk_eval.py` | 38 | Full eval suite (3 layers) |
| `test_chat_endpoints.py` | 18 | REST vs SSE streaming endpoint comparison |
| `test_agent_sdk.py` | 3 | Claude Agent SDK basic patterns |
| `test_bedrock_hello.py` | 4 | Bedrock connectivity |
| `test_bedrock_tools.py` | 1 | Bedrock tool use |
| `test_bedrock_bearer.py` | 1 | Bedrock bearer auth |
| **Total** | **65** | Across 6 test files |

---

## Learnings

### patterns_that_work
- Expert system pattern (index + expertise + commands) scales cleanly across domains
- Flat hook structure with dispatcher enables easy discovery and composition
- ACT-LEARN-REUSE as default workflow captures institutional knowledge
- Frontmatter in command files enables tool discovery and metadata
- Agent `.md` files with YAML frontmatter (name, model, color, tools, description) are the standard for agent definitions — `.claude/agents/` directory is the runtime agent registry (EAGLE, 2026-02-25)
- Dual representation: each expert domain has both command-based interface AND agent definition — commands for logic, agents for isolation/parallelism (EAGLE, 2026-02-25)
- Parallel agent execution via Task tool: `/parallel_subagents` command launches N agents simultaneously for independent subtasks (EAGLE, 2026-02-25)
- Description keyword matching: agent `.md` description field contains keywords that enable auto-dispatch (e.g., "backend", "fastapi", "tool dispatch" triggers backend-expert-agent) (EAGLE, 2026-02-25)
- Model tiering in agent definitions: opus for complex/creative tasks (TAC composer, code review, browser), sonnet for domain-specific expert work (EAGLE, 2026-02-25)
- Scribe delegation pattern: code-review command generates content then delegates to Scribe agent for formatting — separates analysis from presentation (EAGLE, 2026-02-25)
- File traceability convention: `{YYYYMMDD}-{HHMMSS}-{type}-{slug}-v{N}.{ext}` with chronological audit trail, never overwrite (EAGLE, 2026-02-25)
- Hooks expert as a standalone domain: the hooks system is complex enough to warrant its own expert with dedicated expertise.md (EAGLE, 2026-02-25)
- 3-layer eval architecture: SDK patterns (1-6) + skill validation (7-28) + AWS integration layers (16-38) gives comprehensive coverage without monolithic test files (EAGLE, 2026-02-25)
- MCP server integration in settings.json: Atlassian MCP for Jira/Confluence integration without custom code (EAGLE, 2026-02-25)
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
- Shell-based hooks (.sh) when Python hooks (.py) with settings.json configuration are available — Python hooks get JSON stdin/stdout and matcher support (EAGLE, 2026-02-25)
- Counting tests or expert domains in expertise files without verifying against codebase — numbers go stale fast (EAGLE, 2026-02-25)
- Referencing "Core Four" when the project has evolved to "Core Five" (agents directory is now essential) (EAGLE, 2026-02-25)
- Vague hook block reasons like "Validation failed" — write the reason as a clear correction instruction (agentic-finance-review, 2026-02-18)
- Global hooks for agent-specific validation — scope hooks to the agent frontmatter instead (agentic-finance-review, 2026-02-18)
- Logging or displaying env variable values in hooks — only validate existence with pattern matching (install-and-maintain, 2026-02-18)
- Agentic commands that RE-EXECUTE what the hook already did — the prompt should READ the log, not re-run commands (install-and-maintain, 2026-02-18)

### common_issues
- Context window overflow: too many expertise files loaded simultaneously
- Stale expertise: expertise.md not updated after significant changes (this file was 16 days stale before this update)
- Hook cycles: stop hooks triggering other stop hooks recursively — use `stop_hook_active` env guard
- Missing frontmatter: commands without allowed-tools or description metadata
- Agent definition drift: agent `.md` files referencing outdated file paths or line numbers in expertise (e.g., `TOOL_DISPATCH at line ~2167` may shift)
- Expert count mismatch: documentation says N experts but codebase has N+1 after new domain added (hooks expert was the 10th)

### tips
- Start every new domain with the Expert Bootstrap ADW
- Run maintenance commands weekly to catch drift
- Keep CLAUDE.md under 200 lines; move details to expertise files
- Use the Core Five checklist when setting up new projects (CLAUDE.md, settings.json, commands/, experts/, agents/)
- Use PostToolUse hooks for per-operation validation (immediate catch), Stop hooks for final-state validation (pipeline gating)
- Write block reasons like instructions, not log lines: "Missing column 'date'. Add with format YYYY-MM-DD." not "Validation failed"
- The 4 abstraction layers: Command (logic) → Agent (isolation) → Orchestrator (pipeline) → Just (reusability)
- Setup hooks always append to log files (not overwrite) — enables trend analysis across maintenance runs
- For progressive modes: always support deterministic-only for CI/CD, agentic for dev oversight, interactive for onboarding
- When self-improving, always verify counts against codebase (Glob for `*.md`, Grep for `def test_`) rather than trusting existing documentation
- Use model tiering: opus for creative/complex tasks, sonnet for routine domain work — defined in agent frontmatter
- For parallel execution: use `/parallel_subagents` command with explicit count, ensure agents are stateless and self-contained
