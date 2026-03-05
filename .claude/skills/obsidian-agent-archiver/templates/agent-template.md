---
type: agent
name: "{{title}}"
banner: "[[_assets/banners/agent-banner.png]]"
mtg_card: "{{mtg_card}}"
mtg_color: "{{mtg_color}}"
mtg_edition: "8th Edition"
mtg_set_code: "8ed"
status: active
version: 1.0.0
model: claude-opus-4-5-20251101
tools: [Read, Write, Edit, Bash, Glob, Grep]
created: <% tp.date.now("YYYY-MM-DD") %>
updated: <% tp.date.now("YYYY-MM-DD") %>
human_reviewed: false
tac_original: false
tags: [agent]
cssclasses: [cards, cards-cover]
---

![[agent-banner.png|banner]]

# {{title}}

## Purpose
One paragraph describing what this agent does and when to use it.

## System Prompt
```
You are a [role] agent responsible for [task].

## Instructions
- Guiding principle 1
- Guiding principle 2

## Workflow
1. First action
2. Second action
3. Final action

## Report
Return results in this format...
```

## Configuration
| Property | Value |
|----------|-------|
| Model | `claude-opus-4-5-20251101` |
| Max Tokens | 4096 |
| Temperature | 0.7 |

## Tools Available
| Tool | Purpose |
|------|---------|
| `Read` | Read file contents |
| `Write` | Create new files |
| `Edit` | Modify existing files |
| `Bash` | Execute commands |

## Skills Used
| Skill | Purpose |
|-------|---------|
| [[skill-name]] | Description |

## Part of ADWs
- [[adw-name]]

## Source Files
- Agent Definition: `.claude/agents/{{title}}.md`

## Changelog
- <% tp.date.now("YYYY-MM-DD") %>: Created
