---
description: "Full ACT-LEARN-REUSE workflow: plan SSE changes, implement them, validate, and update expertise"
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
argument-hint: [feature description or change to implement]
---

# SSE Expert - Plan Build Improve Workflow

> Full ACT-LEARN-REUSE workflow for SSE streaming development.

## Purpose

Execute the complete SSE development workflow:
1. **PLAN** - Design changes using expertise
2. **VALIDATE (baseline)** - Run syntax checks
3. **BUILD** - Implement the changes
4. **VALIDATE (post)** - Verify end-to-end
5. **REVIEW** - Check event flow integrity
6. **IMPROVE** - Update expertise with learnings

## Usage

```
/experts:sse:plan_build_improve [feature description or change]
```

## Variables

- `TASK`: $ARGUMENTS

---

## Workflow

### Phase 1: PLAN

1. Read `.claude/commands/experts/sse/expertise.md`
2. Read relevant source files
3. Identify affected layers (backend/wire/frontend)
4. Design the change — follow existing patterns

### Phase 2: VALIDATE (baseline)

```bash
# Python syntax
cd server && python -c "import ast; ast.parse(open('app/strands_agentic_service.py').read()); ast.parse(open('app/streaming_routes.py').read()); ast.parse(open('app/stream_protocol.py').read()); print('Python OK')"

# TypeScript
cd client && npx tsc --noEmit 2>&1 | tail -5
```

### Phase 3: BUILD

Implement changes following the patterns in expertise.md:
- **New tool emission**: Use factory function pattern with `_emit_tool_result()`
- **New event type**: Add to `StreamEventType`, `MultiAgentStreamWriter`, frontend `StreamEvent`
- **Frontend parsing**: Add handler in `processEventData()`, update types

### Phase 4: VALIDATE (post)

```bash
# Python syntax re-check
cd server && python -c "import ast; ast.parse(open('app/strands_agentic_service.py').read()); print('OK')"

# TypeScript re-check
cd client && npx tsc --noEmit 2>&1 | tail -5

# Ruff lint on changed files
cd server && python -m ruff check app/strands_agentic_service.py app/streaming_routes.py app/stream_protocol.py --select E,F,W 2>&1 | head -20
```

### Phase 5: REVIEW

Check event flow integrity:
- Every tool that executes should emit a `tool_result`
- Event types match between backend `StreamEventType` and frontend `StreamEventType`
- No empty-name events leak through filters
- Factory tools use `_emit_tool_result()` helper

### Phase 6: IMPROVE

Run self-improve to update expertise:
- Record new patterns
- Document any issues encountered
- Update line numbers if code shifted

---

## Instructions

1. **Read expertise.md FIRST** — it contains all patterns and anti-patterns
2. **Trace the full pipeline** — Don't change one layer without checking others
3. **Test with browser** — SSE changes need end-to-end verification
4. **Check tool_use:tool_result ratio** — Should be 1:1 for full observability
