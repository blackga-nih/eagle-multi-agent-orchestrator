---
type: expert-file
file-type: index
domain: {{DOMAIN}}
tags: [expert, {{DOMAIN}}]
---

# {{DOMAIN_TITLE}} Expert

> {{DESCRIPTION}}

## Domain Scope

This expert covers:
- **{{AREA_1}}** — {{AREA_1_DESC}}
- **{{AREA_2}}** — {{AREA_2_DESC}}
- **{{AREA_3}}** — {{AREA_3_DESC}}

## Available Commands

| Command | Purpose |
|---------|---------|
| `/experts:{{DOMAIN}}:question` | Answer {{DOMAIN}} questions without coding |
| `/experts:{{DOMAIN}}:plan` | Plan {{DOMAIN}} implementations |
| `/experts:{{DOMAIN}}:self-improve` | Update expertise with new learnings |
| `/experts:{{DOMAIN}}:plan_build_improve` | Full ACT-LEARN-REUSE workflow |
| `/experts:{{DOMAIN}}:maintenance` | Validate {{DOMAIN}} health and compliance |

## Key Files

| File | Purpose |
|------|---------|
| `expertise.md` | Complete mental model for {{DOMAIN}} |
| `question.md` | Query command for read-only questions |
| `plan.md` | Planning command |
| `self-improve.md` | Expertise update command |
| `plan_build_improve.md` | Full workflow command |
| `maintenance.md` | Validation command |

## Architecture

```
.claude/commands/experts/{{DOMAIN}}/
  |-- _index.md              # This file — expert overview
  |-- expertise.md           # Complete mental model
  |-- question.md            # Read-only Q&A
  |-- plan.md                # Plan using domain knowledge
  |-- self-improve.md        # Update expertise with learnings
  |-- plan_build_improve.md  # Full ACT-LEARN-REUSE workflow
  |-- maintenance.md         # Validate domain health
```

## ACT-LEARN-REUSE Pattern

```
ACT    ->  Apply {{DOMAIN}} expertise to plan and build
LEARN  ->  Update expertise.md with patterns discovered
REUSE  ->  Apply proven patterns to future development
```
