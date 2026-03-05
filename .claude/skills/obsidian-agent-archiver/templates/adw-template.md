---
type: adw
name: "{{title}}"
banner: "[[_assets/banners/adw-banner.png]]"
mtg_card: "{{mtg_card}}"
mtg_color: "{{mtg_color}}"
mtg_edition: "8th Edition"
mtg_set_code: "8ed"
status: development
pattern: plan_build | plan_build_review | plan_build_review_fix | custom
total_steps: 2
created: <% tp.date.now("YYYY-MM-DD") %>
updated: <% tp.date.now("YYYY-MM-DD") %>
human_reviewed: false
tac_original: false
tags: [adw, workflow]
cssclasses: [cards, cards-cover, cards-2-3]
---

![[adw-banner.png|banner]]

# {{title}}

## Overview
Brief description of this AI Developer Workflow.

## Pattern
> **Type**: `plan_build_review`
> **Steps**: 3 (Plan -> Build -> Review)

## Workflow Diagram
```mermaid
graph LR
    subgraph "{{title}}"
        A[Plan] --> B[Build]
        B --> C[Review]
    end
    style A fill:#D97757,color:#fff
    style B fill:#C26D52,color:#fff
    style C fill:#191919,color:#fff
```

## Agents
| Agent | Role | Step | Status |
|-------|------|------|--------|
| [[plan-agent]] | Creates implementation plan | 1 | Active |
| [[build-agent]] | Implements the plan | 2 | Active |
| [[review-agent]] | Reviews code quality | 3 | Active |

## Input Schema
```json
{
  "prompt": "Feature description",
  "working_dir": "/path/to/project",
  "model": "claude-opus-4-5-20251101"
}
```

## Output Schema
```json
{
  "plan_path": "specs/feature-name.md",
  "build_status": "complete",
  "review_verdict": "PASS"
}
```

## Triggers
- Manual: `start adw: {{title}}: <prompt>`
- API: `POST /adws/start`

## Related
- Skills: [[skill-name]]
- MCP Servers: [[mcp-name]]
- Documentation: [[link]]

## Source Files
- Workflow: `adws/adw_workflows/adw_{{title}}.py`

## Changelog
- <% tp.date.now("YYYY-MM-DD") %>: Created
