---
type: prompt
name: "{{title}}"
banner: "[[_assets/banners/prompt-banner.png]]"
version: 1.0.0
created: <% tp.date.now("YYYY-MM-DD") %>
updated: <% tp.date.now("YYYY-MM-DD") %>
human_reviewed: false
tac_original: false
tags: [prompt]
cssclasses: [cards, cards-cover]
---

![[prompt-banner.png|banner]]

# {{title}}

## Purpose
What task does this prompt accomplish?

## Variables
| Variable | Type | Description |
|----------|------|-------------|
| `{{var}}` | string | Description |

## Prompt Content
```
Your prompt template here with {{variables}}
```

## Example Usage
**Input:**
```
Example input values
```

**Output:**
```
Expected output
```

## Part of Skills
- [[Skill-Name]]

## Source Files
- Prompt File: `.claude/prompts/{{title}}.md`

## Changelog
- <% tp.date.now("YYYY-MM-DD") %>: Created
