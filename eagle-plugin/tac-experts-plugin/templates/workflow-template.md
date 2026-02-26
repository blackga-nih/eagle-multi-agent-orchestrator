---
type: workflow
name: "{{title}}"
status: development
pattern: plan_build | plan_build_review | plan_build_review_fix | custom
total_steps: 2
created: {{DATE}}
updated: {{DATE}}
human_reviewed: false
tac_original: false
tags: [workflow]
---

# {{title}}

## Overview
Brief description of this Agent Team Workflow.

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
| plan-agent | Creates implementation plan | 1 | Active |
| build-agent | Implements the plan | 2 | Active |
| review-agent | Reviews code quality | 3 | Active |

## Input Schema
```json
{
  "prompt": "Feature description",
  "working_dir": "/path/to/project",
  "model": "claude-opus-4-6"
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
- Manual: `start workflow: {{title}}: <prompt>`
- Command: `/experts:{{domain}}:plan_build_improve "{{prompt}}"`

## Related
- Skills: [[skill-name]]
- Experts: [[expert-name]]
- Documentation: [[link]]

## Source Files
- Workflow: `.claude/commands/experts/{{domain}}/plan_build_improve.md`

## Changelog
- {{DATE}}: Created
