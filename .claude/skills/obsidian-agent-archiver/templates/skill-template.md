---
type: skill
name: "{{title}}"
banner: "[[_assets/banners/skill-banner.png]]"
mtg_card: "{{mtg_card}}"
mtg_color: "{{mtg_color}}"
mtg_edition: "8th Edition"
mtg_set_code: "8ed"
status: active
version: 1.0.0
dependencies: []
created: <% tp.date.now("YYYY-MM-DD") %>
updated: <% tp.date.now("YYYY-MM-DD") %>
human_reviewed: false
tac_original: false
tags: [skill]
cssclasses: [cards, cards-cover]
---

![[skill-banner.png|banner]]

# {{title}}

## Description
What this skill does (max 200 chars for Claude discovery).

> **Trigger**: When Claude should automatically invoke this skill.

## SKILL.md Definition
```yaml
---
name: {{title}}
description: Brief description for Claude
dependencies: python>=3.8
---
```

## Instructions
1. First step
2. Second step
3. Final step

## Prompts
| Prompt | Purpose |
|--------|---------|
| [[prompt-name]] | What it generates |

## Scripts
| Script | Language | Purpose |
|--------|----------|---------|
| [[script-name]] | Python | What it does |

## Usage Example
**Input:**
```
Example input
```

**Output:**
```
Expected output
```

## Used By
- Agents: [[agent-name]]
- ADWs: [[adw-name]]

## Source Location
- Skill File: `.claude/skills/{{title}}/SKILL.md`
- Scripts: `.claude/skills/{{title}}/scripts/`

## Changelog
- <% tp.date.now("YYYY-MM-DD") %>: Created
