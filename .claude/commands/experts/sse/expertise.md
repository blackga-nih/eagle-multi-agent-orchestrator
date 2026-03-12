---
type: expert-file
file-type: expertise
domain: sse
parent: "[[sse/_index]]"
human_reviewed: false
last_updated: "2026-03-09T18:00:00Z"
description: "SSE Expertise (Complete Mental Model)"
allowed-tools: []
tags: [expert, sse, streaming, expertise, mental-model]
---

# SSE Expertise — Complete Mental Model

## Part 1: Stream Protocol (`server/app/stream_protocol.py`)

### StreamEventType Enum

```python
class StreamEventType(str, Enum):
    TEXT = "text"
    REASONING = "reasoning"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    ELICITATION = "elicitation"
    METADATA = "metadata"
    COMPLETE = "complete"
    ERROR = "error"
    HANDOFF = "handoff"
```

### StreamEvent Dataclass

Every SSE event carries agent identity:
- `type: StreamEventType`
- `agent_id: str` — e.g. `"eagle"`
- `agent_name: str` — e.g. `"EAGLE Acquisition Assistant"`
- `content: Optional[str]` — for TEXT, ERROR
- `tool_use: Optional[Dict]` — `{name, input, tool_use_id?}`
- `tool_result: Optional[Dict]` — `{name, result}`
- `timestamp: str` — UTC ISO

Serialization: `.to_dict()` → `.to_json()` → `.to_sse()` → `"data: {json}\n\n"`

### MultiAgentStreamWriter

Helper that pre-fills `agent_id` and `agent_name` on every event:
- `write_text(queue, content)` — TEXT event
- `write_tool_use(queue, tool_name, tool_input, tool_use_id="")` — TOOL_USE event
- `write_tool_result(queue, tool_name, result)` — TOOL_RESULT event
- `write_complete(queue)` — COMPLETE event
- `write_error(queue, error_message)` — ERROR event

The `tool_use` payload shape: `{"name": str, "input": dict, "tool_use_id"?: str}`
The `tool_result` payload shape: `{"name": str, "result": any}`

---

## Part 2: Backend Streaming Pipeline

### Fast-Path Document Generation

Before starting the full agent loop, `sdk_query_streaming()` calls `_maybe_fast_path_document_generation()` (~line 1455). If the user prompt matches a direct doc-generation pattern (SOW, IGCE, AP, etc.), it bypasses the supervisor entirely:

```python
fast_path = await _maybe_fast_path_document_generation(prompt, tenant_id, ...)
if fast_path is not None:
    yield {"type": "tool_use", "name": "create_document"}
    yield {"type": "tool_result", "name": "create_document", "result": result}
    yield {"type": "text", "data": summary}
    yield {"type": "complete", ...}
    return
```

**Key:** Fast-path emits synthetic `tool_use` + `tool_result` events so the frontend renders a document card without the agent ever running.

### Forced Document Reconciliation

After the stream completes (post-`stream_async`), `_ensure_create_document_for_direct_request()` (~line 1646) checks whether the model should have called `create_document` but didn't. If so, it forces the call and emits synthetic `tool_use` + `tool_result` events. This fixes cases where the model produces inline draft text instead of using the document tool.

### stream_async() Architecture

`sdk_query_streaming()` in `strands_agentic_service.py` uses `Agent.stream_async()` — the Strands SDK's native async iterator that handles sync→async bridging internally. No background thread, no `QueueCallbackHandler`.

**Event flow:**
```python
async for event in supervisor.stream_async(prompt):
    # 1. Drain tool results from factory tools
    for tool_result_chunk in _drain_tool_results():
        yield tool_result_chunk

    # 2. Text streaming (TextStreamEvent)
    data = event.get("data")
    if data and isinstance(data, str):
        yield {"type": "text", "data": data}

    # 3. Tool use start (ToolUseStreamEvent)
    current_tool = event.get("current_tool_use")
    if current_tool and isinstance(current_tool, dict):
        tool_id = current_tool.get("toolUseId", "")
        if tool_id and tool_id != _current_tool_id:  # dedup guard
            _current_tool_id = tool_id
            yield {"type": "tool_use", "name": ..., "tool_use_id": tool_id}

    # 4. Bedrock contentBlockStart fallback
    # (same dedup via _current_tool_id)
```

**Key:** `_current_tool_id` prevents duplicate emissions when both `current_tool_use` and `contentBlockStart` fire for the same tool invocation.

### result_queue (asyncio.Queue)

Factory tools (`_make_service_tool`, `_make_subagent_tool`, `_make_*_tool`) push results via `result_queue` because Strands `stream_async()` does NOT yield `ToolResultEvent` (it has `is_callback_event = False`).

```python
result_queue: asyncio.Queue = asyncio.Queue()
```

### _drain_tool_results()

Polling helper inside `sdk_query_streaming()`:
```python
def _drain_tool_results() -> list[dict]:
    drained = []
    while True:
        try:
            item = result_queue.get_nowait()
            name = item.get("name")
            if not name:
                continue  # Skip empty-name results (Strands artifacts)
            tools_called.append(name)
            drained.append(item)
        except asyncio.QueueEmpty:
            break
    return drained
```

Called at two points:
1. Top of each iteration of `async for event in stream_async()` — interleaves results with streaming events
2. After the stream completes — final drain for any remaining results

### Tool Result Emission Patterns

Three patterns emit to `result_queue`:

**Pattern A: Service tools** (`_make_service_tool`)
- Calls `TOOL_DISPATCH[tool_name](parsed, tenant_id, ...)`
- Emits: `{"type": "tool_result", "name": tool_name, "result": result}`
- Truncates non-document results > 2000 chars

**Pattern B: Subagent tools** (`_make_subagent_tool`)
- Spawns fresh Agent, runs query, gets raw string
- Emits: `{"type": "tool_result", "name": safe_name, "result": {"report": truncated}}`
- Truncates at 3000 chars

**Pattern C: Standalone factory tools** (`_make_load_data_tool`, `_make_list_skills_tool`, `_make_load_skill_tool`, `_make_compliance_matrix_tool`)
- Call `_emit_tool_result(tool_name, result_str, result_queue, loop)`
- Shared helper parses JSON, truncates large text fields, pushes to queue

**Pattern D: Knowledge tools** (`knowledge_search`, `knowledge_fetch`)
- Wired as service tools via `_SERVICE_TOOL_DEFS` → `_make_service_tool()`
- Dispatch goes through `TOOL_DISPATCH` in `agentic_service.py` → `exec_knowledge_search()` / `exec_knowledge_fetch()` in `tools/knowledge_tools.py`
- Result emission follows Pattern A (service tool), not standalone
- Schema-only entries in `EAGLE_TOOLS` list (for health endpoint reporting)

All patterns use `loop.call_soon_threadsafe(result_queue.put_nowait, ...)` because tools execute in the Strands agent thread (not the asyncio event loop thread).

### _emit_tool_result() Helper

```python
def _emit_tool_result(tool_name, result_str, result_queue, loop):
    if not result_queue or not loop:
        return
    parsed = json.loads(result_str)  # with fallback
    # Truncate large text/content/body fields > 2000 chars
    loop.call_soon_threadsafe(
        result_queue.put_nowait,
        {"type": "tool_result", "name": tool_name, "result": parsed},
    )
```

---

## Part 3: Streaming Routes (`server/app/streaming_routes.py`)

### _sdk_with_keepalive() Wrapper

Wraps `sdk_query_streaming()` to inject SSE keepalive comments (`: keepalive\n\n`) every 20 seconds while waiting for the next chunk. This prevents ALB idle timeout (300s) from killing long-running agent turns.

```python
async def _sdk_with_keepalive():
    pending_task = None
    while True:
        if pending_task is None:
            pending_task = asyncio.create_task(aiter.__anext__())
        done, _ = await asyncio.wait({pending_task}, timeout=KEEPALIVE_INTERVAL)
        if done:
            chunk = pending_task.result()
            pending_task = None
            yield chunk
        else:
            yield {"type": "_keepalive"}  # → ": keepalive\n\n"
```

**Key:** The `pending_task` is reused across timeout iterations to avoid losing chunks. Only cleared when the task actually completes.

### stream_generator() async generator

Iterates chunks from `_sdk_with_keepalive()` (which wraps `sdk_query_streaming()`) and converts to SSE via `MultiAgentStreamWriter`:

```python
async for chunk in gen:
    chunk_type = chunk.get("type")

    if chunk_type == "text":
        await writer.write_text(sse_queue, chunk["data"])

    elif chunk_type == "tool_use":
        tool_input = chunk.get("input", {})
        if isinstance(tool_input, str):
            tool_input = json.loads(tool_input)  # with fallback
        await writer.write_tool_use(
            sse_queue, chunk["name"], tool_input,
            tool_use_id=chunk.get("tool_use_id", ""),
        )

    elif chunk_type == "tool_result":
        tr_name = chunk.get("name", "")
        if not tr_name:
            logger.debug("Skipping empty-name tool_result")
            continue
        await writer.write_tool_result(sse_queue, tr_name, chunk.get("result", {}))

    elif chunk_type == "complete":
        # If no text was streamed, use complete_text as fallback
        if not full_response_parts and complete_text:
            full_response_parts.append(complete_text)
            await writer.write_text(sse_queue, complete_text)

        # Guaranteed fallback: never send blank response to frontend
        if not full_response_parts:
            await writer.write_text(sse_queue, "[No response generated. Please try again.]")

        # Persist to DynamoDB, then emit COMPLETE
        await writer.write_complete(sse_queue)
```

**Key guards:**
- Empty-name tool_result events are filtered out (Strands raw callback artifacts)
- Blank response fallback ensures the frontend always receives at least one TEXT event
- `complete_text` field from the complete chunk is used if no text was streamed during the response
- Fallback COMPLETE is emitted even if the generator exhausts without an explicit complete event (lines 187-195)

### SSE Wire Format

Each event is a single line: `data: {json}\n\n`

Example tool_use:
```
data: {"type":"tool_use","agent_id":"eagle","agent_name":"EAGLE Acquisition Assistant","tool_use":{"name":"search_far","input":{"query":"sole source"},"tool_use_id":"tooluse_abc123"},"timestamp":"2026-03-09T12:00:00+00:00"}
```

Example tool_result:
```
data: {"type":"tool_result","agent_id":"eagle","agent_name":"EAGLE Acquisition Assistant","tool_result":{"name":"search_far","result":{"query":"sole source","results_count":15,"clauses":[...]}},"timestamp":"2026-03-09T12:00:01+00:00"}
```

---

## Part 4: Frontend Event Parsing

### Types (`client/types/stream.ts`)

```typescript
interface StreamEvent {
  type: StreamEventType;  // 'text'|'tool_use'|'tool_result'|'complete'|'error'|...
  agent_id: string;
  agent_name: string;
  timestamp: string;
  content?: string;
  tool_use?: ToolUse;
  tool_result?: ToolResult;
  metadata?: Record<string, any>;
}

interface ToolUse {
  name: string;
  input: Record<string, any>;
  tool_use_id?: string;
}

interface ToolResult {
  name: string;
  result: any;
}
```

### parseStreamEvent()

Simple JSON.parse wrapper — returns `StreamEvent | null`.

---

## Part 5: Frontend SSE Consumer (`client/hooks/use-agent-stream.ts`)

### ServerToolResult Interface

```typescript
interface ServerToolResult {
  toolName: string;
  result: { success: boolean; result: unknown; error?: string };
}
```

### processEventData() — Event Routing

Inside `sendQuery()`:

1. **text** → `accumulatedText += content` → `onMessage(message)`
2. **tool_use** → `onToolUse({toolName, input, toolUseId, isClientSide, ...})`
   - Client-side tools (`think`, `code`, `editor`) execute immediately
   - Server-side tools just notify UI (tool card appears)
3. **tool_result** → `serverToolResults.push({toolName, result: {success: true, result: tr.result}})`
   - Also checks for `create_document` results → `onDocumentGenerated()`
4. **complete** → `onComplete(serverToolResults)`
   - Triggers result merge in `simple-chat-interface.tsx`

### Key: Results accumulated as plain JS array, merged atomically at `onComplete`

This avoids React state batching issues — `serverToolResults` is a local variable, not React state.

---

## Part 6: Tool Card State Merge (`simple-chat-interface.tsx`)

### onComplete Handler

```typescript
onComplete: (toolResults?: ServerToolResult[]) => {
    // Build lookup: toolName → results (FIFO order)
    const resultsByName = new Map<string, ServerToolResult[]>();
    for (const tr of toolResults) {
        const arr = resultsByName.get(tr.toolName) ?? [];
        arr.push(tr);
        resultsByName.set(tr.toolName, arr);
    }

    // Merge into toolCallsByMsg by matching toolName
    const finalized = calls.map(tc => {
        if (tc.isClientSide) return tc;
        const pending = resultsByName.get(tc.toolName);
        const matched = pending?.shift();  // FIFO
        if (matched) {
            return { ...tc, status: 'done', result: matched.result };
        }
        // No result — mark done without result
        return { ...tc, status: 'done' };
    });
}
```

**Important:** Match is by `toolName` (FIFO), NOT by `tool_use_id`. If a tool is called twice, the first result goes to the first card, second to the second.

---

## Part 7: Tool Card UI (`tool-use-display.tsx`)

### canExpand Logic

```typescript
const hasResult = status === 'done' && result && typeof result === 'object';
const reportText = hasResult ? result.result?.report : undefined;
const resultText = hasResult && !reportText ? JSON.stringify(result.result) : null;
const canExpand = (status === 'done' || status === 'error') && (resultText || reportText || errorText);
```

**The chevron ▾ only appears when `canExpand` is true** — meaning the tool card has actual result data.

### Tool Meta Mapping

```typescript
const TOOL_META: Record<string, {icon: string; label: string}> = {
    search_far: { icon: '...', label: 'Searching FAR/DFARS' },
    // ... 20+ entries
};
// Fallback: { icon: '...', label: toolName.replace(/_/g, ' ') }
```

### Expanded View

- **reportText** (subagent): Rendered as Markdown via ReactMarkdown
- **resultText** (service/standalone): Rendered as formatted JSON
- **docData** (create_document): Special document card component

---

## Part 8: Common Issues and Patterns

### patterns_that_work

- Factory functions for tools that need result_queue access — same pattern as `_make_service_tool` (discovered: 2026-03-09)
- `_emit_tool_result()` shared helper avoids code duplication across 4 standalone tools
- `loop.call_soon_threadsafe()` bridges sync Strands thread → async event loop
- Empty-name filter in both `_drain_tool_results()` and `streaming_routes.py` catches Strands artifacts
- FIFO name-matching in `onComplete` handles multiple calls to same tool
- Fast-path document generation bypasses full agent loop for obvious doc requests, emitting synthetic tool_use/tool_result (discovered: 2026-03-09)
- `_ensure_create_document_for_direct_request()` reconciles missed create_document calls after stream ends
- `_sdk_with_keepalive()` reuses pending_task across timeout iterations to prevent chunk loss (discovered: 2026-03-09)
- Blank response fallback in streaming_routes guarantees at least one TEXT event before COMPLETE
- Agent result extraction at stream end (`event["result"]` with `hasattr(metrics)`) recovers final text when no text deltas were streamed

### patterns_to_avoid

- **DO NOT wrap @tool with a generic `**kwargs` wrapper** — Strands generates tool schema from function signature; `**kwargs` produces empty schema and the model won't know what parameters to send
- **DO NOT override `_tool_spec`** on wrapped tools — breaks the Strands tool registry and can affect ALL tools in the agent
- **DO NOT use module-level @tool singletons** for tools that need per-request state (result_queue, loop) — use factory functions instead
- **DO NOT emit tool_result from stream_async event handling** — stream events fire during streaming, before the tool actually executes; use result_queue pattern instead
- **DO NOT discard the pending_task in keepalive wrapper** — if `asyncio.wait` times out, the task is still running; discarding it loses the chunk. Reuse `pending_task` on next iteration.
- **DO NOT assume `_load_plugin_config()` returns DynamoDB manifest shape** — it may lack `data` key. Always load bundled `plugin.json` first as fallback (bug fixed 2026-03-09).

### common_issues

- **Missing chevron on tool card**: Tool doesn't emit `tool_result` → no result data → `canExpand` is false. Fix: ensure the tool's factory function calls `_emit_tool_result()`.
- **Empty-name tool_result events**: Strands raw callbacks emit artifacts with no tool name. Fix: filter in `_drain_tool_results()` and `streaming_routes.py`.
- **Duplicate tool_use events**: Both `current_tool_use` and `contentBlockStart` fire for the same tool. Fix: `_current_tool_id` dedup guard in stream event handler.
- **tool_result not matched to card**: Name mismatch between tool_use name and tool_result name. Fix: ensure both use the same `tool_name` / `safe_name`.
- **Zombie server processes**: Stale uvicorn processes keep LISTENING sockets, serving old code. Fix: `taskkill /F /T /PID` with tree kill flag.

### tips

- Test SSE events by capturing raw stream in browser DevTools Network tab → EventStream
- Count `tool_use` vs `tool_result` events — should be 1:1 for full observability
- Tool result data must be JSON-serializable; `_emit_tool_result` handles parsing
- Large results (>2000 chars in text/content/body fields) are auto-truncated
- Subagent reports are truncated at 3000 chars
- Fast-path events are synthetic — they don't come from stream_async, so they won't appear in Strands callback logs
- `_ensure_create_document_for_direct_request` only fires if `create_document` is NOT already in `tools_called`

---

## Part 9: Test Coverage

### Backend Tests (pytest, `server/tests/`)

| File | Tests | Coverage |
|------|-------|---------|
| `test_stream_protocol.py` | 14 | StreamEvent dataclass, to_dict/to_json/to_sse serialization, MultiAgentStreamWriter methods, all event types |
| `test_sdk_query_streaming.py` | 10 | stream_async event flow, result_queue drain, _current_tool_id dedup, fast-path doc generation, forced doc reconciliation, empty-text fallback |
| `test_streaming_routes.py` | 7 | stream_generator SSE formatting, keepalive injection, tool_use/tool_result routing, empty-name filtering, complete event guards |
| `test_streaming_error_paths.py` | 9 | Exception handling, CancelledError disconnect, error event propagation, malformed chunk resilience, fallback COMPLETE on generator exhaust |

**Total: 40 backend tests**

### E2E Tests (Playwright, `client/tests/`)

| File | Coverage |
|------|---------|
| `validate-sse-pipeline.spec.ts` | StreamEvent schema validation, tool_use/tool_result pairing, rendering verification, FIFO ordering, session persistence |
| `validate-uc-simple-acquisition.spec.ts` | Full UC quality + SSE event flow + tool card rendering for simple acquisition scenario |

### Coverage Gaps (as of 2026-03-09)

- No unit tests for `_sdk_with_keepalive()` wrapper timeout/reuse behavior
- No unit tests for knowledge_search/knowledge_fetch tool dispatch through service tools
- No pytest coverage for `_load_plugin_config()` fallback chain
- No E2E test for fast-path document generation (bypasses agent entirely)
