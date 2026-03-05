---
type: script
name: "{{title}}"
banner: "[[_assets/banners/script-banner.png]]"
language: python
version: 1.0.0
created: <% tp.date.now("YYYY-MM-DD") %>
updated: <% tp.date.now("YYYY-MM-DD") %>
human_reviewed: false
tac_original: false
tags: [script]
cssclasses: [cards, cards-cover]
---

![[script-banner.png|banner]]

# {{title}}

## Purpose
What does this script do?

## Dependencies
```
package>=version
```

## Usage
```bash
python scripts/{{title}}.py --arg value
```

## Input/Output
**Input:** Description of expected input
**Output:** Description of output

## Part of Skills
- [[Skill-Name]]

## Source Files
- Script: `scripts/{{title}}.py`

## Changelog
- <% tp.date.now("YYYY-MM-DD") %>: Created
