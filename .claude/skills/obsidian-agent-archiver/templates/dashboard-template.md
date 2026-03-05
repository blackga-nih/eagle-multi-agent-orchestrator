---
type: dashboard
banner: "[[_assets/banners/dashboard-banner.png]]"
cssclasses: [cards, cards-cover, cards-2-3]
human_reviewed: false
tac_original: false
---

![[dashboard-banner.png|banner]]

# AI Agent Knowledge Base

> Central hub for ADWs, Agents, Skills, and AI infrastructure.

## Quick Navigation

| [[01-ADWs/_ADW-Index\|ADWs]] | [[02-Agents/_Agent-Index\|Agents]] | [[03-Skills/_Skill-Index\|Skills]] |
|:---:|:---:|:---:|
| AI Developer Workflows | Agent Definitions | Reusable Capabilities |

| [[04-MCP-Servers/_MCP-Index\|MCP Servers]] | [[05-Prompts/_Prompt-Index\|Prompts]] | [[06-Scripts/_Script-Index\|Scripts]] |
|:---:|:---:|:---:|
| External Connections | Prompt Templates | Code & Automation |

| [[07-Experts/_Expert-Index\|Experts]] |
|:---:|
| Domain Expertise |

---

## Recent Activity

```dataview
TABLE WITHOUT ID
  link(file.link, file.name) as "Item",
  type as "Type",
  status as "Status",
  file.mday as "Modified"
FROM "AI-Agent-KB"
WHERE type != null AND file.name != "_Dashboard"
SORT file.mday DESC
LIMIT 10
```

---

## Statistics

### By Type
```dataview
TABLE WITHOUT ID
  type as "Type",
  length(rows) as "Count"
FROM "AI-Agent-KB"
WHERE type != null
GROUP BY type
```

### Active Items
```dataview
TABLE WITHOUT ID
  link(file.link, file.name) as "Name",
  type as "Type"
FROM "AI-Agent-KB"
WHERE status = "active"
SORT type ASC
```
