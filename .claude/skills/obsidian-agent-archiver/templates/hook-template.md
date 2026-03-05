---
type: hook
name: "{{title}}"
banner: "[[_assets/banners/hook-banner.png]]"
mtg_card: "{{mtg_card}}"
mtg_color: "{{mtg_color}}"
mtg_edition: "8th Edition"
mtg_set_code: "8ed"
status: active
version: 1.0.0
hook_type: Stop | PreToolUse | PostToolUse | Notification
language: python
created: <% tp.date.now("YYYY-MM-DD") %>
updated: <% tp.date.now("YYYY-MM-DD") %>
human_reviewed: false
tac_original: false
tags: [hook]
cssclasses: [cards, cards-cover]
---

![[hook-banner.png|banner]]

# {{title}}

## Purpose
What this hook does and when it triggers.

## Hook Type
> **Type**: `Stop` | `PreToolUse` | `PostToolUse` | `Notification`
> **Trigger**: When Claude attempts to complete / use a tool / etc.

## Configuration
```yaml
# In command frontmatter or settings.json
hooks:
  Stop:
    - hooks:
        - type: command
          command: "uv run \"$CLAUDE_PROJECT_DIR\"/.claude/hooks/{{title}}.py"
```

## Input (stdin)
```json
{
  "hook_type": "Stop",
  "session_id": "...",
  "conversation": [...],
  "tool_use": {...}
}
```

## Output (stdout)
```json
// To BLOCK and retry:
{"decision": "block", "reason": "Validation failed: ..."}

// To ALLOW completion:
{}
```

## Dependencies
```
# requires-python = ">=3.11"
# dependencies = ["package>=version"]
```

## Script Overview
```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Hook description
"""
import json
import sys

def main():
    # Read stdin
    hook_input = json.loads(sys.stdin.read())
    
    # Validation logic
    errors = validate(...)
    
    # Output decision
    if errors:
        print(json.dumps({"decision": "block", "reason": "\n".join(errors)}))
    else:
        print(json.dumps({}))

if __name__ == "__main__":
    main()
```

## Used By
- Commands: [[command-name]]
- Agents: [[agent-name]]
- ADWs: [[adw-name]]

## Source Files
- Hook Script: `.claude/hooks/{{title}}.py`
- Log File: `.claude/hooks/logs/{{title}}.log`

## Changelog
- <% tp.date.now("YYYY-MM-DD") %>: Created




