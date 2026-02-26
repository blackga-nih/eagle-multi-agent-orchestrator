# The 8 Fundamental Tactics

> TAC — Tactical Agentic Coding. A methodology for agent-first software development.

## Memory Aid: S.A.T.S.F.O.Z.P

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

## Tactic 1: Stop Coding

**The most important tactic.** You are no longer a programmer. You are a director.

- **Mindset shift**: Stop writing code yourself. Instead, describe what you want to the agent.
- **Your role**: Architect, reviewer, decision-maker. Not typist.
- **Anti-pattern**: Opening files and editing code by hand. If you catch yourself doing this, STOP.
- **Key insight**: Every line you type by hand is a line the agent could have written with better context, fewer bugs, and full test coverage.
- **The rule**: If you're typing code, you're doing it wrong. Type instructions instead.

---

## Tactic 2: Adopt the Agent's Perspective

**Think like the agent thinks.** Understand its constraints and capabilities.

- **Context window**: The agent has a finite context window. Everything you put in it competes for attention.
- **Tool access**: The agent can Read, Write, Edit, Grep, Glob, Bash. Design workflows that leverage these tools.
- **No memory between sessions**: Each conversation starts fresh. The agent relies on what's in its context: CLAUDE.md, expertise files, and what you tell it.
- **Implications**: Write clear, structured files the agent can load. Don't rely on verbal agreements or implied context.
- **Key insight**: The better your written artifacts (CLAUDE.md, expertise files, specs), the better the agent performs. Your documentation IS your codebase's intelligence.

---

## Tactic 3: Template Engineering

**Create reusable templates that encode your standards.**

- **What to templatize**: File structures, test patterns, command formats, commit messages, PR descriptions.
- **Why it works**: Templates give the agent a concrete pattern to follow. It fills in the blanks rather than inventing from scratch.
- **Template locations**: `.claude/commands/experts/` for expert templates, `.claude/commands/` for slash commands.
- **Key insight**: A good template is worth a thousand instructions. The agent follows patterns better than prose.
- **Example**: The eval expert's add-test.md is a template. It encodes an 8-point registration checklist so the agent never forgets a step.

---

## Tactic 4: Stay Out of the Loop

**Design workflows where the agent can complete tasks without asking you questions.**

- **Autonomy-first**: Give the agent enough context to make decisions on its own.
- **Decision frameworks**: Instead of "ask me which option", provide decision criteria in your instructions.
- **Fallback behavior**: Define what to do when uncertain: "If X, do Y. If unsure, default to Z."
- **Anti-pattern**: Commands that require human input at every step. Each interruption breaks agent flow.
- **Key insight**: The best agent workflows are the ones where you press enter once and come back to a completed task.

---

## Tactic 5: Feedback Loops

**Build feedback directly into your agent workflows.**

- **Validation steps**: After every build step, run tests. After every edit, syntax check.
- **Self-correction**: When a test fails, the agent should diagnose and fix, not just report.
- **Progression**: Plan -> Build -> Validate -> Fix -> Validate -> Done.
- **Built-in checks**: `python -c "import py_compile; ..."` after edits, `pytest` after features, `git diff` before commits.
- **Key insight**: An agent with feedback loops is self-correcting. An agent without them is a one-shot gamble.

### Validation Ladder

```
Level 1 — Lint          ruff check (Python) / tsc --noEmit (TypeScript)
Level 2 — Unit          pytest tests/ (backend) / vitest (frontend)
Level 3 — E2E           playwright test (frontend flows)
Level 4 — Infra         cdk synth --quiet (CDK compiles)
Level 5 — Integration   docker compose up --build (full stack)
Level 6 — Eval          CloudWatch dashboard post-deploy metrics
```

| Change Type | Minimum Level |
|-------------|---------------|
| Typo / copy fix | Level 1 |
| Backend logic | Level 1 + 2 |
| Frontend UI | Level 1 + 3 |
| CDK change | Level 1 + 4 |
| Cross-stack feature | Level 1-5 |
| Production deploy | Level 1-6 |

---

## Tactic 6: One Agent, One Prompt

**Each agent should have a single, focused system prompt that defines its role.**

- **Specialization**: A legal review agent should only know legal review. A test agent should only know testing.
- **Prompt boundaries**: The system prompt defines what the agent CAN do and what it CANNOT do.
- **No kitchen sinks**: A prompt that tries to cover everything covers nothing well.
- **Composition over complexity**: Use multiple specialized agents rather than one omniscient agent.
- **Key insight**: Skill files in `.claude/commands/experts/` follow this principle. Each expertise.md is one domain, one focus.

---

## Tactic 7: Zero-Touch Deployment

**Automate everything from commit to deployment.**

- **CI/CD integration**: Agent should be able to commit, push, create PRs, and trigger pipelines.
- **No manual steps**: If there's a manual step in your pipeline, automate it or give the agent a tool for it.
- **Verification**: Agent should verify deployments, not just trigger them.
- **Key insight**: The deployment pipeline is an extension of the agent's capability. Gaps in automation are gaps in agent power.

---

## Tactic 8: Prioritize Agentics

**When choosing between approaches, always prefer the more agentic option.**

- **Agentic > Manual**: If something can be done by an agent, do it with an agent.
- **Automated > Scripted > Manual**: Prefer fully automated over scripted over manual.
- **Invest in tooling**: Every tool you build for the agent pays dividends across all future tasks.
- **Key insight**: Time spent making the agent more capable is the highest-leverage work you can do. One hour of tooling saves ten hours of manual work.
