---
description: "Query SSE streaming, event parsing, tool observability, or get answers without making changes"
allowed-tools: Read, Glob, Grep, Bash
---

# SSE Expert - Question Mode

> Read-only command to query SSE streaming knowledge without making any changes.

## Purpose

Answer questions about the EAGLE SSE pipeline — stream protocol, event types, tool observability, frontend parsing, tool card rendering — **without making any code changes**.

## Usage

```
/experts:sse:question [question]
```

## Allowed Tools

`Read`, `Glob`, `Grep`, `Bash` (read-only commands only)

## Question Categories

### Category 1: Stream Protocol Questions

Questions about SSE event types, format, and wire protocol.

**Examples**:
- "What event types does the SSE stream support?"
- "What's the shape of a tool_use event?"
- "How does MultiAgentStreamWriter format events?"

**Resolution**:
1. Read `.claude/commands/experts/sse/expertise.md` → Part 1
2. If needed, read `server/app/stream_protocol.py`

---

### Category 2: Backend Streaming Questions

Questions about how events are generated and queued.

**Examples**:
- "How does stream_async() event routing work?"
- "How does result_queue work in sdk_query_streaming?"
- "How do tool_result events get from tools to the SSE stream?"

**Resolution**:
1. Read `.claude/commands/experts/sse/expertise.md` → Part 2
2. If needed, read `server/app/strands_agentic_service.py`

---

### Category 3: Tool Observability Questions

Questions about tool_result emission and the chevron/expand UI.

**Examples**:
- "Why doesn't a tool card show a chevron?"
- "How do factory tools emit results?"
- "What's the difference between service tools and standalone tools?"

**Resolution**:
1. Read `.claude/commands/experts/sse/expertise.md` → Parts 2, 7, 8
2. If needed, read the relevant tool factory function

---

### Category 4: Frontend Parsing Questions

Questions about how the frontend consumes SSE events.

**Examples**:
- "How does use-agent-stream parse events?"
- "How are tool results merged into tool cards?"
- "What controls the canExpand logic?"

**Resolution**:
1. Read `.claude/commands/experts/sse/expertise.md` → Parts 4, 5, 6, 7
2. If needed, read `client/hooks/use-agent-stream.ts` or `client/components/chat-simple/tool-use-display.tsx`

---

## Workflow

1. Read `.claude/commands/experts/sse/expertise.md`
2. Classify question into category
3. Read relevant source files if expertise.md doesn't fully answer
4. Provide formatted answer with source references

## Instructions

1. **Read expertise.md first** - All knowledge is stored there
2. **Never modify files** - This is a read-only command
3. **Be specific** - Reference exact files, functions, and line numbers
4. **Trace the full pipeline** - SSE questions often span backend → wire → frontend
