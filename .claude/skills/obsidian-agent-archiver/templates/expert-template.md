---
type: expert
name: "{{title}}"
banner: "[[_assets/banners/expert-banner.png]]"
domain: [adw, database, websocket, frontend]
status: active
created: <% tp.date.now("YYYY-MM-DD") %>
updated: <% tp.date.now("YYYY-MM-DD") %>
human_reviewed: false
tac_original: false
tags: [expert, domain-expertise]
cssclasses: [cards, cards-cover]
---

![[expert-banner.png|banner]]

# {{title}} Expert

## Domain Overview
High-level description of the domain this expert covers.

## Core Insight
> **Key Insight**: The fundamental principle that guides this domain.

## Mental Model

### Key Concepts
| Concept | Definition |
|---------|------------|
| Term 1 | What it means |
| Term 2 | What it means |

### Patterns
1. **Pattern Name**: Description
2. **Pattern Name**: Description

## Expertise Structure
```yaml
overview:
  description: "High-level summary"
  core_insight: "Key principle"
  value_proposition:
    - Benefit 1
    - Benefit 2

key_implementations:
  module_name:
    file: "path/to/file"
    purpose: "What it does"
    key_functions:
      - function_name: "description"
```

## Commands
| Command | Purpose |
|---------|---------|
| `/question` | Ask without changes |
| `/plan` | Domain-aware planning |
| `/self-improve` | Sync expertise with code |

## Related Files
- Expertise YAML: `.claude/commands/experts/{{title}}/expertise.yaml`
- Commands: `.claude/commands/experts/{{title}}/*.md`

## Used In
- ADWs: [[adw-name]]
- Agents: [[agent-name]]

## Changelog
- <% tp.date.now("YYYY-MM-DD") %>: Created
