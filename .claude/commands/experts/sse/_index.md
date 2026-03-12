---
type: expert-file
file-type: index
domain: sse
tags: [expert, sse, streaming, tool-use, tool-result, event-stream, observability]
---

# SSE Expert

> EAGLE Server-Sent Events specialist for streaming protocol, tool observability, event parsing, and frontend event consumption.

## Domain Scope

This expert covers:
- **Stream Protocol** - `server/app/stream_protocol.py` — `StreamEvent`, `MultiAgentStreamWriter`, SSE event types
- **Streaming Routes** - `server/app/streaming_routes.py` — SSE endpoint, event dispatching, tool_result forwarding
- **Streaming Core** - `server/app/strands_agentic_service.py` — `stream_async()`, `result_queue`, `_drain_tool_results()`
- **Tool Result Emission** - Factory tools (`_make_*_tool`), `_make_service_tool`, `_make_subagent_tool` — `_emit_tool_result()`
- **Frontend Parsing** - `client/types/stream.ts` — `StreamEvent`, `ToolUse`, `ToolResult` types
- **Frontend Consumer** - `client/hooks/use-agent-stream.ts` — SSE reader, `processEventData()`, `ServerToolResult` accumulation
- **Tool Card UI** - `client/components/chat-simple/tool-use-display.tsx` — `canExpand`, chevron, result rendering
- **State Merge** - `client/components/chat-simple/simple-chat-interface.tsx` — `onComplete` result merge into `toolCallsByMsg`

## Available Commands

| Command | Purpose |
|---------|---------|
| `/experts:sse:question` | Answer SSE/streaming questions without coding |
| `/experts:sse:plan` | Plan SSE or streaming changes using expertise context |
| `/experts:sse:self-improve` | Update expertise after implementations |
| `/experts:sse:plan_build_improve` | Full ACT-LEARN-REUSE workflow |
| `/experts:sse:maintenance` | Validate SSE pipeline health end-to-end |

## Key Files

| File | Purpose |
|------|---------|
| `expertise.md` | Complete mental model for SSE domain |
| `question.md` | Query command for read-only questions |
| `plan.md` | Planning command for SSE changes |
| `self-improve.md` | Expertise update command |
| `plan_build_improve.md` | Full workflow command |
| `maintenance.md` | Validation and health check command |

## Architecture

```
Backend (Python)                              Frontend (TypeScript)
─────────────────                             ────────────────────
Agent.stream_async(prompt)                    use-agent-stream.ts
  │ (native async iterator)                     │
  ├─ TextStreamEvent → text chunk               ├─ fetch('/api/invoke')
  ├─ ToolUseStreamEvent → tool_use chunk        │   └─ ReadableStream
  ├─ contentBlockStart (fallback) → tool_use    │
  │   dedup: _current_tool_id guard             ├─ processEventData(line)
  │                                             │   ├─ text → accumulatedText
  ├─ Tool execution (inside agent loop)         │   ├─ tool_use → onToolUse()
  │   ├─ _make_service_tool                     │   ├─ tool_result → serverToolResults[]
  │   │   └─ result_queue.put(tool_result)      │   └─ complete → onComplete()
  │   ├─ _make_subagent_tool                    │
  │   │   └─ result_queue.put(tool_result)      ├─ onComplete(serverToolResults)
  │   └─ _make_*_tool (factories)               │   └─ merge into toolCallsByMsg
  │       └─ _emit_tool_result()                │       by name (FIFO)
  │           └─ result_queue.put()             │
  │                                             └─ tool-use-display.tsx
sdk_query_streaming()                              ├─ canExpand = status + result
  │                                                ├─ chevron ▾ when canExpand
  ├─ async for event in stream_async()             └─ expanded: JSON or markdown
  ├─ _drain_tool_results() → yield tool_result
  └─ yield {complete, text, tools_called, usage}
       │
streaming_routes.py
  │
  ├─ stream_generator(async gen)
  │   ├─ text → writer.write_text()
  │   ├─ tool_use → writer.write_tool_use(name, input, id)
  │   ├─ tool_result → writer.write_tool_result(name, result)
  │   ├─ _keepalive → ": keepalive\n\n" (every 20s)
  │   └─ complete → writer.write_complete()
  │
  └─ SSE: "data: {json}\n\n"
```

## SSE Event Types

| Type | Backend Origin | Frontend Handler | UI Effect |
|------|---------------|-----------------|-----------|
| `text` | `stream_async()` TextStreamEvent | `accumulatedText` → `onMessage` | Streaming text bubble |
| `tool_use` | `stream_async()` ToolUseStreamEvent | `onToolUse` → tool card (pending) | Tool card appears |
| `tool_result` | `result_queue` via `_drain_tool_results` | `serverToolResults[]` → `onComplete` merge | Chevron + expandable result |
| `complete` | End of `sdk_query_streaming` | `onComplete(toolResults)` | Finalize message + merge results |
| `error` | Exception handler | `onError` | Error display |

## ACT-LEARN-REUSE Pattern

```
ACT    ->  Modify streaming, add event types, fix tool observability
LEARN  ->  Update expertise.md with patterns and issues
REUSE  ->  Apply patterns to future SSE development
```
