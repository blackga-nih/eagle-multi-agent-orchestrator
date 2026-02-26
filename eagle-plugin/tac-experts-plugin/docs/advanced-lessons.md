# Advanced Lessons (9-27)

> Building on the 8 tactics, these lessons cover the meta-skills of agentic development (9-14) and applied project patterns (15-27).

---

## Lesson 9: Context Engineering

**The art of curating what goes into the agent's context window.**

- **CLAUDE.md**: The agent's persistent memory. Keep it lean, accurate, and up-to-date.
- **Expertise files**: Domain-specific knowledge the agent loads on demand via slash commands.
- **Spec files**: Task-specific plans created for a single workflow, consumed and archived.
- **Context budget**: Every token counts. Redundant content wastes context; missing content causes errors.
- **Hierarchy**: CLAUDE.md (always loaded) > expertise.md (loaded by command) > spec files (loaded per task).
- **Key principle**: Context engineering is the most important skill in agentic development. The agent is only as good as its context.

### Context Hierarchy

```
Always Loaded (Class 1)
├── CLAUDE.md           ← Project memory, conventions, constraints
├── .claude/settings.json  ← Model, permissions, tool config
└── Git config          ← .gitignore, .gitattributes

On Demand (Class 2)
├── .claude/commands/*.md     ← Slash commands
├── .claude/hooks/*.sh        ← Automated triggers
└── .claude/specs/*.md        ← Task plans

Expert Invocation (Class 3)
├── experts/{domain}/_index.md      ← Expert routing
├── experts/{domain}/expertise.md   ← Domain mental model
└── experts/{domain}/{action}.md    ← Expert commands
```

### Reduce / Delegate Framework

**Reduce**: Keep CLAUDE.md under 200 lines. Don't duplicate content. Don't inline diagrams. Each expert loads its context on invocation, not always-on.

**Delegate**: Domain questions go to experts. Architecture reference goes to docs. Agent definitions go to plugins. Implementation specs go to `.claude/specs/`.

---

## Lesson 10: Prompt Engineering

**Crafting effective prompts for agent system prompts, commands, and instructions.**

- **Be declarative, not procedural**: Tell the agent WHAT, not HOW. "Create a test that validates S3 operations" not "Open the file, go to line 200, add a function..."
- **Use structured formats**: Tables, checklists, and code blocks are parsed better than prose.
- **Constraints over instructions**: "Never modify files outside the test directory" is stronger than "Please be careful."
- **Role definition**: Start system prompts with a clear role. "You are an EAGLE SDK evaluation specialist."
- **Anti-patterns**: Vague instructions, implicit context, assuming the agent remembers previous conversations.

---

## Lesson 11: Specialized Agents

**Creating purpose-built agents for specific domains.**

- **Domain isolation**: Each agent owns one domain. Legal agent, test agent, deployment agent.
- **Skill files**: Encode domain expertise in structured markdown that the agent loads as system prompt.
- **Expert pattern**: The `.claude/commands/experts/` directory structure IS the specialization pattern.
- **Agent definition**: Name, model, system prompt, tools, and handoff rules.
- **Key insight**: A specialist agent outperforms a generalist on every domain-specific task.

---

## Lesson 12: Multi-Agent Orchestration

**Coordinating multiple specialized agents to complete complex workflows.**

- **Supervisor pattern**: One orchestrator agent delegates to specialist agents.
- **Handoff protocol**: Clear input/output contracts between agents.
- **Sequential vs parallel**: Use sequential for dependent tasks, parallel for independent tasks.
- **Context passing**: Each agent gets only the context it needs, not the full conversation.
- **Example**: Supervisor agent delegates to intake, legal, market, and tech review agents.

---

## Lesson 13: Agent Experts

**The expert system pattern for organizing agent knowledge.**

- **Structure**: `_index.md` (overview) + `expertise.md` (mental model) + command files (actions).
- **Commands**: question (read-only), plan (design), self-improve (learn), plan_build_improve (full workflow), maintenance (validate).
- **Self-improving**: Experts update their own expertise.md after completing tasks (ACT-LEARN-REUSE).
- **Composable**: Multiple experts can be invoked in sequence for cross-domain tasks.
- **Discovery**: `_index.md` lists available commands. Agents can discover expert capabilities.

### Standard Expert Files

| File | Purpose | Required |
|------|---------|----------|
| `_index.md` | Expert overview and command listing | Yes |
| `expertise.md` | Complete domain mental model | Yes |
| `question.md` | Read-only Q&A | Recommended |
| `plan.md` | Domain-aware planning | Recommended |
| `self-improve.md` | Expertise update (LEARN step) | Recommended |
| `plan_build_improve.md` | Full ACT-LEARN-REUSE workflow | Recommended |
| `maintenance.md` | Health validation | Recommended |
| `{domain-specific}.md` | Domain extensions (e.g., `cdk-scaffold`) | Optional |

### When to Create a New Expert

- You've asked the same domain question 3+ times
- A domain has non-obvious patterns that agents keep getting wrong
- You need accumulated knowledge across sessions (not just one-off context)

### Expert Golden Rules

1. Never edit expertise files manually — run `/experts:{domain}:self-improve`
2. Run self-improve after significant changes to that domain's code
3. Each expert validates its knowledge against the actual codebase, not assumptions

---

## Lesson 14: Codebase Singularity

**The end state where the codebase fully describes itself to the agent.**

- **Self-describing**: Every component has documentation the agent can find and understand.
- **Self-maintaining**: Experts self-improve, hooks auto-trigger, tests auto-run.
- **Self-extending**: The agent can add new experts, commands, and tests using existing patterns as templates.
- **Convergence**: As the codebase becomes more self-describing, agent performance asymptotically approaches human-level on all tasks.
- **Key insight**: The codebase singularity is not a destination, it's a direction. Every improvement moves you closer.

---

# Post-14 Project Lessons (15-27)

> Applied patterns from real projects that extend TAC beyond the foundational 14 lessons.

---

## Lesson 15: Hooks Mastery

**Deterministic hook lifecycle control + sub-agents.**

Master Claude Code's 13 hook lifecycle events to add deterministic or non-deterministic control over agent behavior. Orchestrate teams with meta-agents that use hooks as their coordination layer.

- **Key pattern**: Hook lifecycle events (PreToolUse, PostToolUse, Stop, etc.) as control points
- **Application**: Build deterministic guardrails that fire before/after every tool call
- **Insight**: Hooks are the bridge between "agent does whatever" and "agent does exactly what's allowed"

---

## Lesson 16: Multi-Agent Observability

**Real-time hook event tracking and visualization.**

Capture all Claude Code hook events across multiple concurrent agents and stream them via HTTP/WebSocket into SQLite for live dashboarding and observability.

- **Key pattern**: Event capture → stream → store → visualize pipeline
- **Application**: Monitor parallel agent teams in real-time
- **Insight**: You can't improve what you can't observe — observability is the prerequisite for agent team optimization

---

## Lesson 17: Damage Control

**PreToolUse hook defense-in-depth.**

Block dangerous bash/edit/write commands and protect sensitive files using pattern-based rules in PreToolUse hooks that exit with 0 (allow), 2 (block), or JSON (ask).

- **Key pattern**: Exit code protocol — 0=allow, 2=block, JSON=ask-user
- **Application**: Protect production configs, credentials, and critical paths
- **Insight**: Defense-in-depth means multiple layers of protection, not one big wall

---

## Lesson 18: Install and Maintain

**Deterministic + Agentic + Interactive (DAI) pattern.**

Combine deterministic hooks (fast/predictable), agentic prompts (supervised/diagnostic), and interactive prompts (asks/adapts) to create living documentation that executes.

- **Key pattern**: DAI — three execution modes for different reliability needs
- **Application**: Self-installing projects, maintenance runbooks that actually run
- **Insight**: The best documentation is documentation that can execute itself

---

## Lesson 19: Specialized Self-Validating Agents (SSVA)

**Agent + scoped hook = trusted automation.**

Build hyper-focused agents that autonomously validate their own work using specialized hooks embedded in prompts, subagents, and skills. Block/retry self-correction increases trust enough for zero-touch operation.

- **Key pattern**: Agent + hook = SSVA with block/retry self-correction
- **Application**: Finance review, compliance checking, any domain needing verified output
- **Insight**: Self-validation is what separates "useful assistant" from "trusted autonomous agent"

---

## Lesson 20: Beyond MCP

**MCP vs. CLI vs. File System Scripts vs. Skills trade-offs.**

Explore 4 concrete approaches to building reusable, context-preserving toolsets for AI agents. MCP's context-loss cost becomes a bottleneck at scale; alternatives may serve better.

- **Key pattern**: Four-way comparison of tool delivery mechanisms
- **Application**: Choose the right tool delivery for each use case
- **Insight**: MCP isn't always the answer — CLI tools, file scripts, and skills each have sweet spots

---

## Lesson 21: Browser Automation (Bowser)

**Four-layer composable stack: Just → Command → Subagent → Skill.**

Build repeatable agentic browser automation by layering justfile recipes (reusability), commands (orchestration), subagents (parallel execution), and skills (capability).

- **Key pattern**: Four composable layers, each adding capability
- **Application**: QA testing, web scraping, UI validation, smoke tests
- **Insight**: Browser automation becomes reliable when you compose simple layers, not build monoliths

---

## Lesson 22: Agent Sandboxes

**E2B isolated sandbox forks for parallel agents.**

Achieve isolation, scale, and agency by running parallel agent forks in fully isolated, gated E2B sandboxes where agents have full control over their environment.

- **Key pattern**: Fork-and-gate — each agent gets a full isolated environment
- **Application**: Parallel experimentation, safe code execution, multi-variant testing
- **Insight**: True agent autonomy requires true isolation — sandboxes make fearless delegation possible

---

## Lesson 23: Fork Repository Skill

**Skill auto-discovery + multi-terminal parallelization.**

Create Claude Code skills that automatically spawn parallel terminal windows to delegate work, branch execution, or run the same command against multiple tools/models in isolation.

- **Key pattern**: One skill → N parallel terminals → aggregated results
- **Application**: Multi-model comparison, parallel builds, distributed testing
- **Insight**: Skills that can fork themselves create multiplicative productivity gains

---

## Lesson 24: R&D Framework — Context Window Mastery

**Reduce & Delegate (R&D) context engineering.**

Master the 4-level R&D framework (Measure → Reduce → Delegate → Agentic) to find the optimal context sweet spot where your agent performs at maximum capability.

- **Key pattern**: Four levels of context optimization, each building on the last
- **Application**: Any project where agent performance degrades with context bloat
- **Insight**: Context engineering is a continuous optimization, not a one-time setup

---

## Lesson 25: Seven Levels of Agentic Prompt Formats

**Hierarchical prompt escalation (Level 1-7).**

Build prompts across 7 levels of escalating complexity — from static high-level prompts through workflow/control-flow/state-machine to goal-oriented and agentic orchestration patterns.

- **Key pattern**: Level 1 (static) → Level 7 (fully agentic orchestration)
- **Application**: Match prompt complexity to task complexity
- **Insight**: Most tasks need Level 2-3 prompts; Level 6-7 are for true orchestration challenges

---

## Lesson 26: Multi-Agent Orchestration — The O-Agent

**Web-based orchestration platform with full observability.**

Deploy a production PostgreSQL-backed platform where a natural-language orchestrator agent manages multiple specialized agents with real-time streaming, cost tracking, and full observability.

- **Key pattern**: Central orchestrator + specialized workers + shared state store
- **Application**: Complex multi-domain tasks requiring coordination
- **Insight**: Production agent orchestration needs the same infrastructure as production services — persistence, observability, cost tracking

---

## Lesson 27: Building Domain-Specific Agents

**Custom Agent SDK specialization (Pong → Echo → Calculator).**

Start with basic Claude SDK setup (Pong Agent), add custom tools with parameters (Echo Agent), then build interactive REPLs with multi-tool orchestration and conversation memory (Calculator Agent).

- **Key pattern**: Progressive specialization — start simple, add tools, add memory
- **Application**: Any new agent domain — start with a ping, add tools, add state
- **Insight**: The best way to learn agent building is progressive complexity, not big-bang architecture
