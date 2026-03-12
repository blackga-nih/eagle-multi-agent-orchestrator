---
description: "Plan SSE streaming changes — new event types, tool observability, frontend parsing — using expertise context"
allowed-tools: Read, Write, Glob, Grep, Bash
argument-hint: [feature description or change to plan]
---

# SSE Expert - Plan Mode

> Create detailed plans for SSE streaming changes informed by expertise.

## Purpose

Generate a plan for modifying the streaming pipeline, adding event types, fixing tool observability, or changing frontend event parsing, using:
- Expertise from `.claude/commands/experts/sse/expertise.md`
- Current SSE architecture and patterns
- End-to-end event flow awareness

## Usage

```
/experts:sse:plan [feature description or change]
```

## Variables

- `TASK`: $ARGUMENTS

## Allowed Tools

`Read`, `Write`, `Glob`, `Grep`, `Bash`

---

## Workflow

### Phase 1: Load Context

1. Read `.claude/commands/experts/sse/expertise.md` for:
   - Stream protocol and event types
   - Two-queue architecture
   - Tool result emission patterns
   - Frontend parsing flow
   - Known issues and patterns_to_avoid

2. Read relevant source files based on TASK scope

### Phase 2: Analyze Current State

Identify which layers of the pipeline are affected:
- Backend only (new event type, emission fix)
- Frontend only (parsing, UI rendering)
- Full-stack (new event type end-to-end)

### Phase 3: Generate Plan

```markdown
# SSE Plan: {TASK}

## Overview
- Change Type: New Event | Fix Emission | Frontend Parse | Full-Stack
- Layers Affected: Backend | Wire | Frontend
- Files Modified: {list}

## Changes by Layer

### Backend (`server/`)
| File | Change |
|------|--------|
| stream_protocol.py | {if new event type} |
| strands_agentic_service.py | {if emission change} |
| streaming_routes.py | {if routing change} |

### Frontend (`client/`)
| File | Change |
|------|--------|
| types/stream.ts | {if new type} |
| hooks/use-agent-stream.ts | {if new handler} |
| components/chat-simple/*.tsx | {if UI change} |

## Validation
1. Syntax check (Python + TypeScript)
2. Browser test: capture SSE events, verify tool_use:tool_result ratio
3. Visual check: tool cards show chevrons
```

### Phase 4: Save Plan

Write plan to `.claude/specs/sse-{feature}.md`

---

## Instructions

1. **Always read expertise.md first**
2. **Trace the full pipeline** — Backend emission → streaming_routes → SSE wire → frontend parse → UI render
3. **Check patterns_to_avoid** — Don't repeat known mistakes (e.g., `**kwargs` wrapper)
4. **Include browser verification** — SSE changes must be tested end-to-end
