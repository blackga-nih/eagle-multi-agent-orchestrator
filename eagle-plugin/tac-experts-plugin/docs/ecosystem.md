# Claude Code Ecosystem Graph

> The three-class layer architecture that organizes all Claude Code components.

---

## Component-Centric View

```
Claude Code Project
│
├── CLAUDE.md                         [Class 1: Foundation]
│   ├── Project description
│   ├── Key conventions
│   └── File references
│
├── .claude/
│   ├── settings.json                 [Class 1: Foundation]
│   │   ├── Model preferences
│   │   ├── Allowed tools
│   │   └── Permission overrides
│   │
│   ├── commands/                     [Class 2: Out-Loop]
│   │   ├── {command}.md              Slash commands
│   │   └── experts/                  [Class 3: Orchestration]
│   │       └── {domain}/
│   │           ├── _index.md         Expert overview
│   │           ├── expertise.md      Mental model
│   │           ├── question.md       Read-only Q&A
│   │           ├── plan.md           Planning command
│   │           ├── self-improve.md   Learning command
│   │           ├── plan_build_improve.md  Full workflow
│   │           └── maintenance.md    Validation command
│   │
│   ├── hooks/                        [Class 2: Out-Loop]
│   │   ├── pre-commit.sh
│   │   ├── stop-dispatcher.sh
│   │   └── stop-{domain}.sh
│   │
│   ├── agents/                       [Class 3: Orchestration]
│   │   └── {agent-name}.md          Agent definitions
│   │
│   ├── skills/                       [Class 2: Out-Loop]
│   │   └── {skill-name}/            Skill definitions
│   │
│   └── specs/                        [Ephemeral]
│       └── {feature}-spec.md         Task-specific plans
│
└── Source Code                       [Target of agent actions]
    ├── app/
    ├── tests/
    └── frontend/
```

---

## Layer Architecture

### Class 1: Foundation Layer

Components that are always loaded and define the project baseline.

| Component | File | Purpose |
|-----------|------|---------|
| Project Memory | `CLAUDE.md` | Always-on agent instructions |
| Settings | `.claude/settings.json` | Tool permissions, model config |
| Git Config | `.gitignore`, `.gitattributes` | Repository conventions |

**Properties**: Always in context, rarely changes, high impact per token.

### Class 2: Out-Loop Layer

Components that extend agent capability without requiring human interaction.

| Component | File Pattern | Purpose |
|-----------|-------------|---------|
| Slash Commands | `.claude/commands/*.md` | On-demand agent actions |
| Hooks | `.claude/hooks/*.sh` | Automated triggers |
| Skills | `.claude/skills/` | Reusable capabilities |
| Specs | `.claude/specs/*.md` | Task-specific context |

**Properties**: Loaded on demand, enables autonomy (Tactic 4), implements feedback (Tactic 5).

### Class 3: Orchestration Layer

Components that enable multi-domain, self-improving agent behavior.

| Component | File Pattern | Purpose |
|-----------|-------------|---------|
| Expert Index | `experts/{domain}/_index.md` | Expert discovery and routing |
| Expertise | `experts/{domain}/expertise.md` | Domain mental models |
| Expert Commands | `experts/{domain}/{action}.md` | Domain-specific actions |
| Agent Definitions | `.claude/agents/{name}.md` | Autonomous agent specs |

**Properties**: Self-improving (ACT-LEARN-REUSE), composable across domains, approaches codebase singularity (Lesson 14).

---

## Pattern Index

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
| Progressive Modes | Class 1-2 | 4, 5, 7 | Deterministic → Agentic → Interactive |
| Hook → Prompt → Report | Class 2 | 5, 7 | Hook executes, agent analyzes log |
| Living Documentation | Class 1-2 | 7, 8 | Docs that execute themselves |
| HIL Onboarding | Class 2 | 4, 5 | Interactive install with AskUserQuestion |

---

## Building Your Ecosystem

### Phase 1: Foundation (Day 1)
```
Create CLAUDE.md
Create .claude/settings.json
You now have a Class 1 project.
```

### Phase 2: Commands (Week 1)
```
Add .claude/commands/plan.md
Add .claude/commands/build.md
You now have Class 2 capabilities.
```

### Phase 3: First Expert (Week 2)
```
Add .claude/commands/experts/{domain}/
  - All 7 standard files from templates
Run /experts:tac:maintenance --experts to validate
You now have Class 3 capabilities.
```

### Phase 4: Setup Hooks (Week 3)
```
Add .claude/hooks/setup_init.py          (deterministic install)
Add .claude/hooks/setup_maintenance.py   (deterministic maintenance)
Add .claude/hooks/session_start.py       (env var loading)
Configure settings.json with Setup matchers
Add /install, /maintenance commands      (agentic wrappers)
You now have progressive execution modes.
```

### Phase 5: Behavioral Hooks (Week 3-4)
```
Add .claude/hooks/stop-dispatcher.sh
Add domain handlers
You now have automated behavior.
```

### Phase 6: Multiple Experts (Month 1)
```
Bootstrap experts for each major domain
Run self-improve after significant work
Run maintenance weekly
You're approaching Codebase Singularity.
```

---

## Frontmatter Schemas

### Expert Index (`_index.md`)
```yaml
---
type: expert-file
file-type: index
domain: {domain-name}
tags: [expert, {domain}]
---
```

### Expert Knowledge (`expertise.md`)
```yaml
---
type: expert-file
parent: "[[{domain}/_index]]"
file-type: expertise
human_reviewed: false
tags: [expert-file, mental-model]
last_updated: YYYY-MM-DDTHH:MM:SS
---
```

### Command Files (`question.md`, `plan.md`, etc.)
```yaml
---
description: "One-line description of command purpose"
allowed-tools: Read, Glob, Grep
argument-hint: [optional arg description]
model: opus  # optional
---
```

### Agent Definitions (`.claude/agents/`)
```yaml
---
name: {kebab-case-name}
description: Description with trigger keywords. Keywords - kw1, kw2.
model: opus
color: green | orange | cyan | purple
tools: Read, Glob, Grep, Write, Edit, Bash
skills:
  - skill-name  # optional
---
```
