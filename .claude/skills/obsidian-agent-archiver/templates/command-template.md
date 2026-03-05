---
type: command
name: "{{title}}"
source_repo: "{{source_repo}}"
source_path: "{{source_path}}"
status: active
created: <% tp.date.now("YYYY-MM-DD") %>
updated: <% tp.date.now("YYYY-MM-DD") %>
human_reviewed: false
tac_original: false
tags: [command]
cssclasses: [ai-agent-kb]
---

# {{title}}

> **Note**: This template is for REFERENCE ONLY. The sync process copies source content VERBATIM with minimal frontmatter additions. See `/ecosystem:copy-to-obsidian` for details.

## Purpose
What this slash command does and when to use it.

## Usage
```bash
/{{title}} <required-arg> [optional-arg]
```

## Arguments
| Argument | Required | Description |
|----------|----------|-------------|
| `$1` | Yes | First argument description |
| `$2` | No | Optional argument description |

## Variables
| Variable | Source | Description |
|----------|--------|-------------|
| `VARIABLE_NAME` | CLAUDE.md | Description |

## Frontmatter
```yaml
---
description: Brief description for command palette
argument-hint: <arg1> [arg2]
model: claude-sonnet-4-20250514
hooks:
  Stop:
    - hooks:
        - type: command
          command: "uv run validator.py"
---
```

## Instructions

- Focus on understanding the command workflow, not implementation details
- Run with `--help` or check examples to see available options
- Read only essential configuration (frontmatter, CLAUDE.md variables)
- Each invocation follows the workflow steps below
- Outputs are generated in the specified format
- Do NOT modify source files - focus on the command's purpose

## Workflow

1. **Parse arguments** - Extract positional args and flags
2. **Validate inputs** - Check required files/paths exist
3. **Execute logic** - Run the main command workflow
4. **Generate output** - Format results per Output Format section
5. **Run hooks** - Any Stop hooks validate before completion

## Output Format
```
Expected output structure
```

## Hooks
| Hook | Type | Purpose |
|------|------|---------|
| Stop | Validator | Validates output before completion |

## Related
- Commands: [[related-command]]
- Agents: [[agent-name]]
- Part of ADWs: [[adw-name]]
- Part of Agentic Prompts: [[agentic-prompt-name]]

## Source Files
- Command: `.claude/commands/{{title}}.md`

## Changelog
- <% tp.date.now("YYYY-MM-DD") %>: Created




