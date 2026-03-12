---
description: "Update SSE expertise with learnings from implementations, debugging, or streaming changes"
allowed-tools: Read, Write, Edit, Grep, Glob
argument-hint: [component] [outcome: success|failed|partial]
---

# SSE Expert - Self-Improve Mode

> Update expertise.md with learnings from SSE development and debugging.

## Purpose

After implementing SSE changes or debugging streaming issues, run self-improve to:
- Record what worked (patterns_that_work)
- Record what to avoid (patterns_to_avoid)
- Document issues encountered (common_issues)
- Add tips for future SSE development

This is the **LEARN** step in ACT-LEARN-REUSE.

## Usage

```
/experts:sse:self-improve tool-observability success
/experts:sse:self-improve event-parsing failed
/experts:sse:self-improve chevron-fix partial
```

## Variables

- `COMPONENT`: $1 (component or area changed)
- `OUTCOME`: $2 (success | failed | partial)

## Allowed Tools

`Read`, `Write`, `Edit`, `Grep`, `Glob`

---

## Workflow

### Phase 1: Gather Information

1. Read current `.claude/commands/experts/sse/expertise.md`
2. Read recent changes:
   - `server/app/strands_agentic_service.py` — emission changes
   - `server/app/streaming_routes.py` — routing changes
   - `server/app/stream_protocol.py` — protocol changes
   - `client/hooks/use-agent-stream.ts` — parsing changes
   - `client/components/chat-simple/tool-use-display.tsx` — UI changes
3. Git log for recent commits:
   ```bash
   git log --oneline -10
   ```

### Phase 2: Analyze Outcome

Based on OUTCOME:

**success**: What pattern worked? Any reusable approach?
**failed**: What broke? What to avoid? Root cause?
**partial**: What worked vs. what didn't? Remaining issues?

### Phase 3: Update expertise.md

Add entries to Part 8 (Common Issues and Patterns):
- `patterns_that_work` — new working patterns
- `patterns_to_avoid` — new anti-patterns
- `common_issues` — new issues and solutions
- `tips` — useful debugging tips

Update other Parts if code structure changed.

### Phase 4: Update timestamp

Update the `last_updated` field in the frontmatter.

---

## Instructions

1. **Run after every significant SSE change**
2. **Be specific** — Include file names, function names, concrete patterns
3. **Don't overwrite** — Append to existing learnings
4. **Update line numbers** if code shifted
