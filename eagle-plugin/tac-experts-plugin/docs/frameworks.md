# Core Frameworks

> TAC provides four frameworks for different development situations.

---

## PITER Framework

**P**lan - **I**mplement - **T**est - **E**valuate - **R**efine

A sequential framework for feature development:

```
PLAN       Define what to build, write spec
IMPLEMENT  Agent builds the feature
TEST       Run tests, validate behavior
EVALUATE   Assess quality, check compliance
REFINE     Iterate based on evaluation
```

- **Used for**: New feature development, major refactors
- **Tactic alignment**: Stop Coding (1), Feedback Loops (5), Stay Out Loop (4)
- **When to use**: You know what you want to build and need a structured path

---

## R&D Framework

**R**esearch - **D**evelop

A lightweight two-phase framework for exploration:

```
RESEARCH   Investigate the codebase, read docs, understand patterns
DEVELOP    Build the solution informed by research
```

- **Used for**: Bug investigation, unfamiliar codebases, exploratory work
- **Tactic alignment**: Adopt Agent's Perspective (2), Stop Coding (1)
- **When to use**: You don't fully understand the problem yet

---

## ACT-LEARN-REUSE Framework

The core TAC improvement cycle. This is the **default operating mode**.

```
ACT    ->  Execute the task (build, test, deploy)
LEARN  ->  Capture what worked and what didn't (update expertise.md)
REUSE  ->  Apply patterns to future tasks (template, reference)
```

- **Used for**: Every task. This is the default operating cycle.
- **Tactic alignment**: Feedback Loops (5), Template Engineering (3), Prioritize Agentics (8)
- **Implementation**: `self-improve` command is the LEARN step. `plan` command is the REUSE step.
- **When to use**: Always. After every significant task, capture learnings.

### The Self-Improving Loop

```
Task Complete
    │
    ▼
Run self-improve
    │
    ▼
expertise.md updated
    │
    ▼
Next task loads updated expertise
    │
    ▼
Better performance
    │
    ▼
Run self-improve...
```

---

## Core Four

The four essential files/directories for any Claude Code project:

| Component | Path | Purpose | Always Loaded |
|-----------|------|---------|--------------|
| Project Memory | `CLAUDE.md` | Project-level agent instructions | Yes |
| Slash Commands | `.claude/commands/` | Agent actions, workflows | On invocation |
| Expert System | `.claude/commands/experts/` | Domain knowledge system | On invocation |
| Settings | `.claude/settings.json` | Tool permissions, model config | Yes |

### Minimum Viable Agentic Codebase

```
my-project/
├── CLAUDE.md                         # Describe your project
├── .claude/
│   ├── settings.json                 # Configure Claude Code
│   ├── commands/
│   │   └── plan.md                   # At least one command
│   └── commands/experts/
│       └── {your-domain}/            # At least one expert
│           ├── _index.md
│           ├── expertise.md
│           ├── question.md
│           ├── plan.md
│           ├── self-improve.md
│           ├── plan_build_improve.md
│           └── maintenance.md
└── src/                              # Your actual code
```

### Graduation Path

```
1. Start with CLAUDE.md only
2. Add .claude/commands/ as you find repeating workflows
3. Add .claude/commands/experts/ when domain knowledge accumulates
4. Add .claude/hooks/ when you want automated behavior
5. Approach Codebase Singularity (Lesson 14)
```

---

## Framework Selection Guide

| Situation | Framework | Reasoning |
|-----------|-----------|-----------|
| Building a new feature | PITER | Structured, sequential, complete |
| Investigating a bug | R&D | Need research before action |
| Standard task | ACT-LEARN-REUSE | Default cycle, captures knowledge |
| Setting up a new project | Core Four | Establish the foundation first |
| Unfamiliar codebase | R&D → ACT-LEARN-REUSE | Research first, then iterate |
| Optimizing performance | R&D → PITER | Profile first, then structured fix |
| Adding a new domain | Expert Bootstrap workflow | From templates, structured creation |
