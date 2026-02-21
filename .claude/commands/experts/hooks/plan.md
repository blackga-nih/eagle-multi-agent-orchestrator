---
type: expert-file
parent: "[[hooks/_index]]"
file-type: command
command-name: "plan"
human_reviewed: false
tags: [expert-file, command, planning, hooks]
---

# Hooks Expert - Plan Mode

> Create hook implementation plans informed by the 7 patterns and 12 events.

## Purpose
Plan hook implementations using proven patterns from the hooks expertise. Produces a spec file with the hook architecture, settings.json configuration, and implementation steps.

## Usage
```
/experts:hooks:plan [user_request]
```

## Allowed Tools
`Read`, `Glob`, `Grep`, `Task`, `Write`

---

## Planning Framework

### Step 1: Event Selection

Which of the 12 events does this need?

| Need | Events |
|------|--------|
| Block dangerous ops | PreToolUse |
| Validate outputs | PostToolUse |
| Inject context | SessionStart |
| Track sessions | SessionStart + SessionEnd |
| Monitor agents | SubagentStart + SubagentStop |
| Audio feedback | Stop + Notification |
| Full observability | All 12 |
| Memory/logging | Stop (turn_end matcher) |

### Step 2: Pattern Selection

Which of the 7 patterns apply?

| Pattern | When |
|---------|------|
| Tool Blocking | Security, safety guards |
| Context Injection | Dev context at start |
| Event Forwarding | Dashboards, analytics |
| PostToolUse Validation | Linting, type checking |
| Stop Hook Guard | TTS, transcript capture |
| Dispatcher Routing | Multi-domain projects |
| TTS Notification | Audio announcements |

### Step 3: Architecture Decision

| Question | Options |
|----------|---------|
| Scope? | Global (~/.claude) vs Project (.claude) |
| Routing? | Direct (simple) vs Dispatcher (scalable) |
| Observability? | Local logging vs Server pipeline |
| Dependencies? | uv (Python) vs Node vs Shell |

### Step 4: Validation Strategy

How to verify hooks work:
- [ ] Hook runs without error (exit code 0)
- [ ] Hook completes within 60 second timeout
- [ ] Blocking hooks correctly deny operations
- [ ] Context injection appears in session
- [ ] Events reach observability server

---

## Plan Output Format

```markdown
# Hook Implementation Plan: {Title}

## Events Required
| Event | Purpose | Pattern |
|-------|---------|---------|
| {event} | {why} | {which pattern} |

## Architecture
- **Scope**: {Global | Project | Both}
- **Routing**: {Direct | Dispatcher}
- **Language**: {Python | Shell | Node}
- **Runner**: {uv run | node | bash}

## settings.json
```json
{
  "hooks": {
    // Exact configuration
  }
}
```

## Files to Create
| File | Purpose |
|------|---------|
| `.claude/hooks/{name}.py` | {description} |

## Implementation Steps
1. {Step 1}
2. {Step 2}
3. {Step 3}

## Validation
- [ ] {test 1}
- [ ] {test 2}
```

---

## Examples

### Example 1: "Add security hooks"
**Events**: PreToolUse
**Pattern**: Tool Blocking
**Plan**: Create `pre_tool_use.py` with BLOCKED_PATTERNS list

### Example 2: "Add full observability"
**Events**: All 12
**Pattern**: Event Forwarding + Dispatcher
**Plan**: Create `send_event.py` + server + dashboard

### Example 3: "Add TTS when Claude finishes"
**Events**: Stop, Notification
**Pattern**: TTS Notification + Stop Hook Guard
**Plan**: Global hooks in `~/.claude/hooks/` with ElevenLabs
