# Context Engineering

> The art of curating what goes into the agent's context window. The most important skill in agentic development.

---

## The Core Principle

**The agent is only as good as its context.**

Every token in the context window competes for attention. Redundant content wastes budget. Missing content causes errors. The goal is to provide exactly the right information at the right time.

---

## Context Hierarchy

```
Layer 1: Always Loaded (Foundation)
├── CLAUDE.md              ← Project conventions, constraints, key files
├── .claude/settings.json  ← Model config, permissions
└── Git config             ← .gitignore, .gitattributes

Layer 2: On Demand (Out-Loop)
├── .claude/commands/*.md        ← Invoked via slash commands
├── .claude/hooks/*.sh           ← Triggered by events
└── .claude/specs/*.md           ← Loaded for specific tasks

Layer 3: Expert Invocation (Orchestration)
├── experts/{domain}/_index.md      ← Routing and discovery
├── experts/{domain}/expertise.md   ← Domain mental model
└── experts/{domain}/{action}.md    ← Expert commands
```

**Rule**: Each layer loads on top of the previous. Layer 1 is always present. Layers 2 and 3 load only when needed.

---

## CLAUDE.md Guidelines

CLAUDE.md is the most important file in an agentic codebase. It's always loaded, so every token counts.

### Keep It Under 200 Lines

```
Good:
  "DynamoDB single-table: SESSION#, MSG#, USAGE#, COST#, SUB#"

Bad:
  [50 lines explaining DynamoDB access patterns that belong in expertise.md]
```

### Reference, Don't Duplicate

```
Good:
  "Agent/skill source of truth → eagle-plugin/ (not server code)"

Bad:
  [Inline copy of all agent definitions]
```

### Structure for Scanning

Use tables, not paragraphs. Agents parse structured content better than prose.

```
Good:
  | Signal | Primitive | Location |
  |--------|-----------|----------|
  | Frontend task | /experts:frontend:plan | .claude/commands/experts/frontend/ |

Bad:
  When working on frontend tasks, you should use the frontend expert
  which is located in the commands experts frontend directory...
```

### Include Validation Commands

The agent needs to know how to verify its own work.

```
Good:
  **Validate**: `ruff check app/ && python -m pytest tests/ -v`

Bad:
  "Make sure to test your changes"
```

---

## Reduce / Delegate Framework

### Reduce

Minimize what's always loaded:
- CLAUDE.md stays under 200 lines
- Don't duplicate plugin content — reference it
- Don't inline architecture diagrams — point to docs/
- Each expert loads its context on invocation, not always-on

### Delegate

Route information to the right layer:
- Domain questions → `/experts:{domain}:question`
- Architecture reference → `docs/` directory
- Agent/skill definitions → plugin directories (auto-loaded by runtime)
- Implementation specs → `.claude/specs/`
- Meeting context → `docs/development/meeting-transcripts/`

---

## Three CLAUDE.md Styles

Different projects benefit from different CLAUDE.md organizations:

### Option A: Enterprise Agent Platform
Identity-first. Starts with what the system IS, then TAC directives, then architecture.
Best for: Large teams, formal projects.

### Option B: Mission Control
Domain-first. Ground rules up front, stack-at-a-glance table, agent hierarchy.
Best for: Domain-heavy projects, acquisition/legal/regulated.

### Option C: Full-Stack TAC Blueprint
Composable primitives. Primitive map table, validation ladder, maturity tracker.
Best for: Multi-stack projects, TAC-native teams.

See `templates/claude-md/` for complete examples of all three styles.

---

## File Traceability

Every generated artifact gets a timestamp prefix: `yyyymmdd-hhmmss-{slug}.md`.

| Artifact | Destination | Example |
|----------|-------------|---------|
| Expert plans | `.claude/specs/` | `20260217-143000-backend-batch-export.md` |
| Context docs | `.claude/context/` | `20260217-150000-cognito-research.md` |
| Eval results | `server/tests/` | `20260217-160000-eval-accuracy.md` |

**Rules**:
- Old plans are never overwritten — each run creates a new timestamped file
- Filenames use lowercase kebab-case after the timestamp
- Domain name included for quick filtering

---

## Context Budget Planning

| Content Type | Approximate Tokens | Load Time |
|-------------|-------------------|-----------|
| CLAUDE.md (200 lines) | 2,000-3,000 | Always |
| Expert expertise.md | 3,000-8,000 | On command |
| Spec file | 1,000-5,000 | On task |
| Source file (medium) | 1,000-3,000 | On read |

**Budget rule**: CLAUDE.md + settings should use < 5% of context. Leave 95%+ for the actual task.
