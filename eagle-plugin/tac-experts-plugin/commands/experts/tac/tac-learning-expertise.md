---
type: expert-file
parent: "[[tac/_index]]"
file-type: expertise
tac_original: true
human_reviewed: false
tags: [expert-file, mental-model, tac-methodology, tac-learning]
last_updated: 2026-02-19T00:00:00
---

# TAC Learning Expertise (Methodology Reference)

> **Tactical Agentic Coding (TAC)** — A methodology for agent-first software development using Claude Code. TAC treats the AI agent as the primary developer and the human as an architect/director.
>
> Companion file: `expertise.md` covers practical coding patterns. This file covers TAC theory and lesson progression.

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

- **Be declarative, not procedural**: Tell the agent WHAT, not HOW.
- **Use structured formats**: Tables, checklists, and code blocks are parsed better than prose.
- **Constraints over instructions**: "Never modify files outside the test directory" is stronger than "Please be careful."
- **Role definition**: Start system prompts with a clear role.
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
- **Agent teams**: Claude Agent SDK enables native multi-agent coordination, superseding script-based orchestration.

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

## Part 3: Post-14 Project Lessons (15-27)

> These lessons come from applied TAC projects in `Desktop/tac/`. Each represents a concrete implementation of TAC principles beyond the core curriculum.

### Lesson 15: Hooks Mastery

**Source**: `claude-code-hooks-mastery` (2 agents, 15 hooks, 1 command)

Hooks as first-class architecture components, not afterthoughts. Covers all 12 Claude Code hook events with production implementations. Introduces the meta-agent pattern for team validation — one agent that validates the output of other agents via hooks.

- **Key pattern**: Hook surface area defines agent capability boundary
- **Learning**: The more hooks you write, the more autonomous the agent becomes. Hooks are the feedback loop infrastructure.
- **Components**: PreToolUse guards, PostToolUse loggers, SubagentStop collectors, SessionStart initializers

### Lesson 16: Multi-Agent Observability

**Source**: `claude-code-hooks-multi-agent-observability` (1 agent, 17 hooks, 4 skills)

Real-time monitoring of agent teams via hook event tracking. WebSocket-based dashboard shows agent actions as they happen. Agent teams need telemetry the way microservices need distributed tracing.

- **Key pattern**: Observability as emergent hook behavior — don't build a monitoring system, let hooks emit events
- **Learning**: If you can't see what your agents are doing, you can't improve them. Observability is the prerequisite for zero-touch.
- **Components**: Event emitters, WebSocket servers, dashboard UI, metric collectors

### Lesson 17: Damage Control

**Source**: `claude-code-damage-control` (1 skill)

Defense-in-depth protection via layered PreToolUse hooks. Trust boundaries are enforced at the hook level, not the prompt level. No amount of prompt engineering replaces a well-placed guard hook.

- **Key pattern**: Layered security — multiple independent guards, each catching different categories
- **Learning**: Prompts suggest behavior; hooks enforce it. Safety-critical systems need both.
- **Components**: Command blockers, path validators, resource guards, escalation handlers

### Lesson 18: Install & Maintain

**Source**: `install-and-maintain` (3 hooks)

One-command onboarding for new engineers. Progressive execution modes: deterministic (hooks run scripts), agentic (hooks run + agent analyzes), interactive (hooks + AskUserQuestion for onboarding).

- **Key pattern**: Deterministic hooks + agentic prompts = living documentation that executes itself
- **Learning**: Three-tier execution (deterministic/agentic/interactive) serves different contexts — CI needs deterministic, dev needs agentic, onboarding needs interactive.
- **Components**: SessionStart env loader, setup init hook, setup maintenance hook, HIL install command

### Lesson 19: SSVA Finance Review

**Source**: `agentic-finance-review` (1 hook)

Specialized Self-Validating Agents — the core architecture for trusted autonomous work. Each agent has one purpose, scoped hooks that validate its specific output, and can self-correct when a hook blocks with a reason.

- **Key pattern**: Agent + scoped hook = trusted automation. Block/retry self-correction loop.
- **Learning**: Write block reasons like instructions, not log lines: "Missing column 'date'. Add with format YYYY-MM-DD." not "Validation failed"
- **Components**: Scoped validators, portable `uv run --script` checks, fail-fast pipeline gating

### Lesson 20: Beyond MCP

**Source**: `beyond-mcp`

Trade-offs between tool integration approaches: MCP Servers vs CLI wrappers vs File System Scripts vs Skills. Choose based on a frequency/complexity matrix.

- **Key pattern**: MCP for stateful sessions, CLI for one-shots, skills for reusable packaged capabilities
- **Learning**: Don't default to MCP for everything — each integration approach has a sweet spot. Match the tool to the usage pattern.
- **Decision matrix**: High frequency + stateful → MCP | Low frequency + one-shot → CLI | Reusable + domain → Skill

### Lesson 21: Bowser

**Source**: `bowser` (1 command, 3 skills)

4-layer composable browser automation stack. Just recipes compose agent + command + hook + skill layers for UI testing and web interaction.

- **Key pattern**: Browser automation as an agentic pipeline — layers compose: Just → Command → Agent → Skill
- **Learning**: Separate the "what to test" (command) from "how to browse" (skill) from "when to run" (just recipe).
- **Components**: claude-bowser skill, playwright-bowser skill, hop-automate command, QA agent

### Lesson 22: Agent Sandboxes

**Source**: `agent-sandboxes` + `agent-sandbox-skill` (1 skill)

E2B isolated execution environments for untrusted agent work. Ephemeral compute containers that spin up, execute agent tasks, and tear down — keeping the host system safe.

- **Key pattern**: Isolation is infrastructure, not convention. Don't trust prompts to stay in bounds — use containers.
- **Learning**: Sandboxes enable running untrusted code, testing destructive operations, and parallel agent execution without interference.

### Lesson 23: Fork Repository

**Source**: `fork-repository-skill` (1 skill)

Spawn new terminal windows with other AI assistants. Repository as the unit of agent delegation — fork a repo, assign an agent, merge back.

- **Key pattern**: Repository-level agent delegation across tool boundaries
- **Learning**: Agent teams can cross repository and even AI-provider boundaries. The filesystem is the integration layer.

### Lesson 24: R&D Deep Dive

**Source**: `rd-framework-context-window-mastery` (2 hooks, 1 command)

The R&D framework applied to context engineering itself. Four levels of context engineering: naive (dump everything), selective (curate), structured (hierarchy), and dynamic (agent-managed).

- **Key pattern**: Context engineering is recursive — apply R&D to your own context strategy
- **Learning**: The context sweet spot is 40-60% of the window. Below 40% = starved agent. Above 60% = diminishing returns.

### Lesson 25: 7 Prompt Levels

**Source**: `seven-levels-agentic-prompt-formats` (2 hooks, 1 command)

Prompt complexity scales with automation maturity. Seven levels: (1) plain text, (2) structured workflow, (3) tool-using, (4) delegation, (5) closed-loop, (6) meta-prompt, (7) self-improving.

- **Key pattern**: Match prompt format to maturity level — don't write Level 7 prompts for In-Loop work
- **Learning**: The stakeholder trifecta (you, team, agents) determines which prompt level you need. Most projects should aim for Level 5 (closed-loop).

### Lesson 26: The O-Agent

**Source**: `multi-agent-orchestration-the-o-agent` (10 hooks, 1 skill)

Production orchestrator with PostgreSQL persistence and WebSocket streaming. Single orchestrator with dynamic specialist dispatch. Claude Agent SDK agent teams supersede ADW Python scripts.

- **Key pattern**: Single interface pattern — one orchestrator agent commands all specialist agents via CRUD
- **Learning**: Agent teams are the modern replacement for ADW subprocess orchestration. Native SDK coordination beats script-based chaining.
- **Three pillars**: Agent Management (CRUD), Task Routing (classify → delegate), Observability (hooks → dashboard)

### Lesson 27: Domain-Specific Agents

**Source**: `building-domain-specific-agents` (3 hooks, 1 command)

Custom agents built for specific domains. The Pong Agent pattern — specialized agents that bounce tasks between themselves. Agent evolution from generic to specialized through accumulated context.

- **Key pattern**: Agent specialization via narrowed tools + focused system prompt + domain context
- **Learning**: Default Claude Code has 15+ tools consuming context. Strip unnecessary tools for focused agents. A domain agent with 3 tools outperforms a generic agent with 15.

---

## Part 4: Core Frameworks Summary

### PITER Framework

**P**lan - **I**mplement - **T**est - **E**valuate - **R**efine

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

**R**educe - **D**elegate

```
REDUCE     Minimize what's in context. CLAUDE.md under 200 lines.
           Don't duplicate content. Each expert loads on demand.
DELEGATE   Route to the right expert/agent/spec.
           Domain questions → expert. Architecture → docs/.
```

- Used for: Context engineering, exploration, unfamiliar codebases
- Tactic alignment: Adopt Agent's Perspective (2), Stop Coding (1)

### ACT-LEARN-REUSE Framework

The core TAC improvement cycle:

```
ACT    →  Execute the task (build, test, deploy)
LEARN  →  Capture what worked and what didn't (update expertise.md)
REUSE  →  Apply patterns to future tasks (template, reference)
```

- Used for: Every task. This is the default operating cycle.
- Implementation: `self-improve` command is the LEARN step. `plan` command is the REUSE step.

### Core Four

The four essential elements for any Claude Code project:

| Element | File | Always Loaded |
|---------|------|--------------|
| Project Memory | `CLAUDE.md` | Yes |
| Slash Commands | `.claude/commands/` | On invocation |
| Expert System | `.claude/commands/experts/` | On invocation |
| Settings | `.claude/settings.json` | Yes |

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

## Part 5: Maturity Model

```
In-Loop        →  Human directs every step
Out-Loop       →  Agent completes autonomously, human reviews
Zero-Touch     →  Fully automated from trigger to deploy
```

**Graduation path**: In-Loop (3+ successes) → Template as command → Add validation → Out-Loop → Zero-Touch

| Level | Human Role | Agent Role | Trigger |
|-------|-----------|------------|---------|
| In-Loop | Directs each step | Assists | Human types command |
| Out-Loop | Reviews final result | Completes end-to-end | Slash command or agent team |
| Zero-Touch | Notified of result | Plans, builds, tests, ships | Cron, webhook, or event |
