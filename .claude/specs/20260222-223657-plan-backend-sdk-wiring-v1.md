# Backend SDK Wiring Plan: Wire sdk_query() as Default Orchestration Path

**Date**: 2026-02-22T22:36:57
**Type**: Backend wiring — replace `stream_chat` with `sdk_query` in web layer
**Status**: Plan (not yet implemented)
**Author**: experts:backend:plan
**Precursor**: `.claude/specs/20260222-223455-plan-claude-sdk-sdk-migration-v1.md`

---

## Summary

This is a **pure wiring change** — no new code is written, no logic is invented.
`sdk_agentic_service.sdk_query()` already exists and is fully implemented.
The two web-layer files (`streaming_routes.py` and `main.py`) currently import
`stream_chat` from `agentic_service`. This plan replaces those imports with
`sdk_query` from `sdk_agentic_service`, adapts `stream_generator()` to consume
the async-generator output, and deprecates `stream_chat` in-place with a comment.

`execute_tool` at `agentic_service.py:2181` is **not touched**. The eval suite
imports it directly from that module at `test_eagle_sdk_eval.py:32` and that
import must continue to resolve unchanged.

---

## Scope Map

| File | Change Type | Detail |
|------|-------------|--------|
| `server/app/streaming_routes.py` | Import swap + `stream_generator` rewrite | Replace `stream_chat` call with `sdk_query` async-for loop |
| `server/app/main.py` | Import swap + 3 call sites updated | `api_chat()`, `websocket_chat()`, `/api/tools` route |
| `server/app/agentic_service.py` | Comment only | Add `# DEPRECATED` above `stream_chat` definition |
| `server/tests/test_eagle_sdk_eval.py` | No change | `from agentic_service import execute_tool` (line 32) stays as-is |

---

## Current State (Verified by File Read)

### `streaming_routes.py` (line 26)
```python
from .agentic_service import stream_chat, MODEL, EAGLE_TOOLS
```
`stream_generator()` (lines 34–97) calls `stream_chat()` via callback pattern:
```python
result = await stream_chat(
    messages,
    on_text=on_text,
    on_tool_use=on_tool_use,
    on_tool_result=on_tool_result,
    session_id=session_id,
)
```

### `main.py` (line 37)
```python
from .agentic_service import stream_chat, get_client, MODEL, EAGLE_TOOLS
```
Call sites:
1. `api_chat()` (line 174): `result = await stream_chat(messages, session_id=session_id)`
2. `websocket_chat()` (line 733): `result = await stream_chat(messages, on_text=..., on_tool_use=..., on_tool_result=..., session_id=...)`
3. `/api/tools` (line 635): reads `EAGLE_TOOLS` — no `stream_chat` call but `EAGLE_TOOLS` came from `agentic_service`
4. Health check in `streaming_routes.py` (line 204): reads `MODEL` from `agentic_service`

### `sdk_agentic_service.py` — confirmed exports
- `sdk_query(prompt, tenant_id, user_id, tier, model, skill_names, session_id, max_turns)` — async generator
- `build_skill_agents(model, tier, skill_names)` — returns `dict[str, AgentDefinition]`
- `build_supervisor_prompt(tenant_id, user_id, tier, agent_names)` — returns `str`
- `MODEL` constant — `os.getenv("EAGLE_SDK_MODEL", "haiku")` (distinct from `agentic_service.MODEL`)

**Note**: `sdk_agentic_service.py` does NOT export `EAGLE_TOOLS`. The `EAGLE_TOOLS` list
lives in `agentic_service.py` and describes the legacy Anthropic tool-use schema (tool
dispatch table). The SDK path delegates to skill subagents via `AgentDefinition` — it does
not expose `EAGLE_TOOLS`. The `/api/tools` endpoint and the health check `tools` list must
remain sourced from `agentic_service.EAGLE_TOOLS` even after the wiring change.

---

## Target State

```
main.py
  import: sdk_query from sdk_agentic_service   ← new primary
  import: EAGLE_TOOLS, MODEL from agentic_service  ← kept (non-chat, tools list + health check)

streaming_routes.py
  import: sdk_query from sdk_agentic_service   ← new primary
  import: EAGLE_TOOLS, MODEL from agentic_service  ← kept (health check endpoint)

agentic_service.py
  stream_chat: # DEPRECATED comment added, function body untouched
  execute_tool: untouched
```

---

## Exact Diff: `server/app/streaming_routes.py`

### Change 1 — Import Line (line 26)

**Before**:
```python
from .agentic_service import stream_chat, MODEL, EAGLE_TOOLS
```

**After**:
```python
from .agentic_service import MODEL, EAGLE_TOOLS
from .sdk_agentic_service import sdk_query
```

Rationale: `MODEL` and `EAGLE_TOOLS` stay sourced from `agentic_service` because the
health-check route (lines 176–211) references both directly. Only the orchestration
call (`stream_chat`) is replaced.

---

### Change 2 — `stream_generator()` body (lines 34–97)

**Before** (current implementation — callback/queue pattern):
```python
async def stream_generator(
    message: str,
    tenant_context,
    tier,
    subscription_service: SubscriptionService,
) -> AsyncGenerator[str, None]:
    """Generate SSE events using EAGLE's Anthropic SDK streaming.

    The flow is:
      1. Yield a metadata event with agent info (initial connection handshake).
      2. Call agentic_service.stream_chat() with SSE-mapping callbacks.
      3. on_text callbacks → TEXT SSE events (real-time streaming).
      4. on_tool_use callbacks → TOOL_USE SSE events.
      5. on_tool_result callbacks → TOOL_RESULT SSE events.
      6. Yield a COMPLETE event on success, or an ERROR event on failure.
    """
    writer = MultiAgentStreamWriter("eagle", "EAGLE Acquisition Assistant")
    queue: asyncio.Queue[str] = asyncio.Queue()

    # Send initial metadata event (connection acknowledgement)
    await writer.write_text(queue, "")
    yield await queue.get()

    try:
        # Build session_id from tenant context
        session_id = f"{tenant_context.tenant_id}-{tenant_context.user_id}-{tenant_context.session_id}"

        # Build messages list with just the current message
        # (In a full implementation, you'd load conversation history here)
        messages = [{"role": "user", "content": message}]

        # Define SSE-mapping callbacks
        async def on_text(delta: str):
            await writer.write_text(queue, delta)

        async def on_tool_use(tool_name: str, tool_input: dict):
            await writer.write_tool_use(queue, tool_name, tool_input)

        async def on_tool_result(tool_name: str, output: str):
            # Truncate large tool results for SSE display
            display_output = output[:2000] + "..." if len(output) > 2000 else output
            await writer.write_tool_result(queue, tool_name, display_output)

        # Stream chat using EAGLE's Anthropic SDK
        result = await stream_chat(
            messages,
            on_text=on_text,
            on_tool_use=on_tool_use,
            on_tool_result=on_tool_result,
            session_id=session_id,
        )

        # Drain all queued events
        while not queue.empty():
            yield await queue.get()

        # Signal completion
        await writer.write_complete(queue)
        yield await queue.get()

    except Exception as e:
        logger.error("Streaming chat error: %s", str(e), exc_info=True)
        await writer.write_error(queue, str(e))
        yield await queue.get()
```

**After** (sdk_query async-for loop pattern):
```python
async def stream_generator(
    message: str,
    tenant_context,
    tier,
    subscription_service: SubscriptionService,
) -> AsyncGenerator[str, None]:
    """Generate SSE events using EAGLE's Claude Agent SDK orchestration.

    The flow is:
      1. Yield an initial metadata/text event (connection handshake).
      2. Iterate over sdk_query() — an AsyncGenerator of SDK message objects.
      3. SystemMessage  → extract session_id from .data (ignored for SSE output).
      4. AssistantMessage → walk .content list:
           text blocks       → TEXT SSE events
           tool_use blocks   → TOOL_USE SSE events
      5. ResultMessage  → yield COMPLETE event.
      6. On any exception → yield ERROR event.
    """
    from claude_agent_sdk import SystemMessage, AssistantMessage, ResultMessage

    writer = MultiAgentStreamWriter("eagle", "EAGLE Acquisition Assistant")
    queue: asyncio.Queue[str] = asyncio.Queue()

    # Send initial metadata event (connection acknowledgement)
    await writer.write_text(queue, "")
    yield await queue.get()

    try:
        # Derive tenant context fields; guard against None tenant_context
        tenant_id = getattr(tenant_context, "tenant_id", "demo-tenant") or "demo-tenant"
        user_id = getattr(tenant_context, "user_id", "demo-user") or "demo-user"
        session_id = getattr(tenant_context, "session_id", None)

        async for msg in sdk_query(
            prompt=message,
            tenant_id=tenant_id,
            user_id=user_id,
            tier=tier or "advanced",
            session_id=session_id,
        ):
            if isinstance(msg, SystemMessage):
                # SystemMessage carries session metadata — not streamed to client
                pass

            elif isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if block.type == "text":
                        await writer.write_text(queue, block.text)
                        while not queue.empty():
                            yield await queue.get()
                    elif block.type == "tool_use":
                        await writer.write_tool_use(queue, block.name, block.input)
                        while not queue.empty():
                            yield await queue.get()

            elif isinstance(msg, ResultMessage):
                # ResultMessage signals end of SDK turn; flush and complete
                while not queue.empty():
                    yield await queue.get()
                await writer.write_complete(queue)
                yield await queue.get()
                return  # explicit return after COMPLETE

        # If sdk_query exhausts without a ResultMessage, still send COMPLETE
        while not queue.empty():
            yield await queue.get()
        await writer.write_complete(queue)
        yield await queue.get()

    except Exception as e:
        logger.error("Streaming chat error: %s", str(e), exc_info=True)
        await writer.write_error(queue, str(e))
        yield await queue.get()
```

**Key behavioural notes**:
- The SSE event contract (`TEXT`, `TOOL_USE`, `COMPLETE`, `ERROR`) is **unchanged** —
  `MultiAgentStreamWriter` produces the same SSE format as before.
- `TOOL_RESULT` events are not directly emitted by the SDK path because the SDK handles
  tool execution internally inside subagents. If the supervisor surfaces a tool result
  as a text block, it will arrive as an `AssistantMessage` text block.
- Queue draining happens eagerly after every `AssistantMessage` block to avoid
  holding events in memory and to preserve the streaming feel for the client.
- `tier` defaults to `"advanced"` if the subscription service provides `None`
  (matches the `TIER_BUDGETS` default in `sdk_agentic_service.py`).

---

## Exact Diff: `server/app/main.py`

### Change 1 — Import Line (line 37)

**Before**:
```python
from .agentic_service import stream_chat, get_client, MODEL, EAGLE_TOOLS
```

**After**:
```python
from .agentic_service import get_client, MODEL, EAGLE_TOOLS
from .sdk_agentic_service import sdk_query
```

**Why keep `get_client`, `MODEL`, `EAGLE_TOOLS` from `agentic_service`**:
- `get_client` — not used directly in current main.py routes but imported; keep to avoid breaking
  other callers if any. Remove in a follow-up cleanup once confirmed unused.
- `MODEL` — referenced at `main.py:757` in `record_request_cost(model=result.get("model", MODEL))`
  inside `websocket_chat()`. The fallback constant must stay.
- `EAGLE_TOOLS` — referenced at `main.py:635` in the `/api/tools` route; this is the
  tool schema list for the legacy Anthropic tool-use format. Keeping it ensures the
  tools endpoint continues to work without depending on `sdk_agentic_service`.

---

### Change 2 — `api_chat()` route (lines 173–223)

The `/api/chat` REST endpoint currently calls `stream_chat()` which accumulates a
complete response dict `{text, usage, model, tools_called}`. `sdk_query()` is an
async generator — it does not return a dict. A small adapter is needed.

**Before** (lines 173–223, simplified):
```python
    try:
        result = await stream_chat(messages, session_id=session_id)
        # ... result["text"], result["usage"], result["model"], result["tools_called"]
```

**After**:
```python
    try:
        # Collect sdk_query() output into a result dict compatible with existing response model
        from claude_agent_sdk import AssistantMessage, ResultMessage
        full_text = []
        usage = {}
        tools_called = []
        model_used = MODEL

        async for msg in sdk_query(
            prompt=req.message,
            tenant_id=tenant_id,
            user_id=user_id,
            tier=user.tier or "advanced",
            session_id=session_id,
        ):
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if block.type == "text":
                        full_text.append(block.text)
                    elif block.type == "tool_use":
                        tools_called.append(block.name)
            elif isinstance(msg, ResultMessage):
                if hasattr(msg, "usage") and msg.usage:
                    usage = msg.usage

        result = {
            "text": "".join(full_text),
            "usage": usage,
            "model": model_used,
            "tools_called": tools_called,
        }
        # ... rest of response construction unchanged
```

**Shape compatibility**: The existing `EagleChatResponse` model and the code that
follows still reads `result["text"]`, `result["usage"]`, `result.get("model", MODEL)`,
and `result.get("tools_called", [])` — all preserved by the adapter above.

---

### Change 3 — `websocket_chat()` route (lines 713–739)

**Before** (lines 733–738):
```python
                result = await stream_chat(
                    messages,
                    on_text=on_text,
                    on_tool_use=on_tool_use,
                    on_tool_result=on_tool_result,
                    session_id=session_id,
                )
```

**After**:
```python
                # Collect sdk_query output; fire WebSocket callbacks during collection
                from claude_agent_sdk import AssistantMessage, ResultMessage
                full_text = []
                ws_usage = {}
                ws_tools_called = []

                async for msg in sdk_query(
                    prompt=user_message,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    tier=user.tier or "advanced",
                    session_id=session_id,
                ):
                    if isinstance(msg, AssistantMessage):
                        for block in msg.content:
                            if block.type == "text":
                                full_text.append(block.text)
                                await on_text(block.text)
                            elif block.type == "tool_use":
                                ws_tools_called.append(block.name)
                                await on_tool_use(block.name, block.input)
                    elif isinstance(msg, ResultMessage):
                        if hasattr(msg, "usage") and msg.usage:
                            ws_usage = msg.usage

                result = {
                    "text": "".join(full_text),
                    "usage": ws_usage,
                    "model": MODEL,
                    "tools_called": ws_tools_called,
                }
```

**Note**: `on_tool_result` callbacks are not fired on the SDK path because tool results
are handled internally by subagents. The `on_tool_result` callback defined in the
WebSocket handler (lines 724–731) can remain in code but will not be called. It does
not need to be removed.

---

## Exact Change: `server/app/agentic_service.py`

**Location**: Line 2221 — the `async def stream_chat(...)` definition.

**Change**: Add a single deprecation comment line immediately above `async def stream_chat`.

**Before** (line 2221):
```python
async def stream_chat(
```

**After**:
```python
# DEPRECATED: use sdk_query() from sdk_agentic_service instead. Kept for reference only.
async def stream_chat(
```

**No other changes to `agentic_service.py`.** `execute_tool` (line 2181), `get_client`
(line 2206), `MODEL`, and `EAGLE_TOOLS` all remain intact and importable.

---

## Eval Suite Compatibility

| Import | File | Line | Status After This Change |
|--------|------|------|--------------------------|
| `from agentic_service import execute_tool` | `test_eagle_sdk_eval.py` | 32 | **Still valid** — `execute_tool` untouched |
| `agentic_service.MODEL` | `test_eagle_sdk_eval.py` (indirect) | various | **Still valid** — `MODEL` constant untouched |
| `from sdk_agentic_service import ...` | `test_eagle_sdk_eval.py` | ~2910 | **Still valid** — `sdk_agentic_service` not modified |

---

## SDK Message Type Reference

The following types are confirmed present in `claude_agent_sdk` (verified via `dir(claude_agent_sdk)`):

| Type | Import | Used In |
|------|--------|---------|
| `SystemMessage` | `from claude_agent_sdk import SystemMessage` | `stream_generator` — detect session_id |
| `AssistantMessage` | `from claude_agent_sdk import AssistantMessage` | both generators — extract text/tool_use blocks |
| `ResultMessage` | `from claude_agent_sdk import ResultMessage` | both generators — trigger COMPLETE event |
| `TextBlock` | Block type check: `block.type == "text"` | implicit via `block.type` attribute |
| `ToolUseBlock` | Block type check: `block.type == "tool_use"` | implicit via `block.type` attribute |

Imports are done inline (`from claude_agent_sdk import ...` inside the generator/route body)
to avoid top-level import cost at module load. This is consistent with the existing pattern
in `main.py` (e.g., `import boto3` inline in S3 route handlers).

---

## Implementation Order

Execute changes in this order to minimise the blast radius at each step:

1. **`agentic_service.py`** — add deprecation comment (1-line, zero risk, confirms git diff
   is minimal)
2. **`streaming_routes.py`** — swap import + rewrite `stream_generator()` (SSE path)
3. **`main.py`** — swap import + update 3 call sites (REST + WebSocket paths)
4. Run validation ladder

---

## Validation Commands

### Level 1 — Lint (must pass before anything else)
```bash
# From server/
ruff check app/
# Expect: no errors
```

### Level 1 — Type check (Python syntax validation)
```bash
python -c "import py_compile; py_compile.compile('server/app/streaming_routes.py', doraise=True)"
python -c "import py_compile; py_compile.compile('server/app/main.py', doraise=True)"
python -c "import py_compile; py_compile.compile('server/app/agentic_service.py', doraise=True)"
```

### Level 2 — Unit tests (eval suite must not regress on execute_tool tests)
```bash
# From server/
python -m pytest tests/ -v -k "not test_28"
# Tests 16-20 (execute_tool direct calls) must all pass
```

### Level 2 — Confirm execute_tool import still resolves
```bash
python -c "
import sys; sys.path.insert(0, 'server'); sys.path.insert(0, 'server/app')
from agentic_service import execute_tool
print('execute_tool import OK:', execute_tool)
"
```

### Level 2 — Confirm sdk_query import resolves from streaming_routes
```bash
python -c "
import sys; sys.path.insert(0, 'server'); sys.path.insert(0, 'server/app')
from app.sdk_agentic_service import sdk_query
print('sdk_query import OK:', sdk_query)
"
```

### Level 2 — Confirm no remaining stream_chat in active web imports
```bash
grep -n "stream_chat" server/app/main.py server/app/streaming_routes.py
# Expected output: empty (no matches)
```

### Level 3 — E2E smoke test (frontend + backend flows)
```bash
just smoke
# Expect: 22 passed
```

### Level 2 — Targeted eval: SDK architecture test
```bash
just eval-quick 28
# Test 28 exercises the full skill→subagent path via sdk_query
# Expected: PASS
```

### Level 2 — AWS tool eval (execute_tool dependency tests)
```bash
just eval-aws
# Tests 16-20: S3, DynamoDB, CloudWatch, document generation, E2E verification
# Expected: all PASS
```

---

## Acceptance Criteria

All of the following must be true before the migration is considered complete:

| Criterion | Validation Command | Pass Condition |
|-----------|-------------------|----------------|
| No `stream_chat` in active web imports | `grep -n "stream_chat" server/app/main.py server/app/streaming_routes.py` | Empty output |
| `execute_tool` import still resolves | `python -c "from agentic_service import execute_tool"` | No ImportError |
| Ruff lint passes | `ruff check app/` | Exit 0, no errors |
| Unit tests pass (excl. test 28) | `pytest tests/ -k "not test_28"` | All green |
| Test 28 passes (skill→subagent E2E) | `just eval-quick 28` | PASS |
| AWS tool tests pass (tests 16–20) | `just eval-aws` | All PASS |
| Smoke test passes | `just smoke` | 22 passed |

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `sdk_query()` yields no `ResultMessage` on timeout | Low | SSE stream hangs | Fallback `COMPLETE` emit after generator exhausts (included in plan) |
| `AssistantMessage.content` is empty list | Low | No SSE events emitted | Guard with `if block.type in ("text", "tool_use")` — no special handling needed |
| `tenant_context` is `None` in `stream_generator` | Medium | AttributeError on `.tenant_id` | `getattr(tenant_context, "tenant_id", "demo-tenant") or "demo-tenant"` guard (included in plan) |
| `user.tier` is `None` from Cognito | Low | `TIER_BUDGETS.get(None)` returns `None` → budget error | `tier or "advanced"` fallback (included in plan) |
| `EAGLE_TOOLS` no longer imported in `sdk_agentic_service` | N/A (known) | `/api/tools` would break | Plan keeps `EAGLE_TOOLS` sourced from `agentic_service` in both files |
| Pre-existing: `stream_chat` still called from WebSocket | Resolved by Change 3 | Double-import confusion | Change 3 replaces the WebSocket call site explicitly |

---

## Non-Goals

- **Do not delete `agentic_service.py`** — `execute_tool` and `EAGLE_TOOLS` are still live dependencies.
- **Do not remove `stream_chat` function body** — comment only; the function must remain callable for
  any external callers not covered by this audit.
- **Do not change the SSE event schema** — `TEXT / TOOL_USE / TOOL_RESULT / COMPLETE / ERROR` remain
  unchanged from the client's perspective.
- **Do not modify `sdk_agentic_service.py`** — it is already fully implemented.
- **Do not modify any test files** — the eval suite is a verification tool, not a migration target.

---

## File Change Summary

| File | Lines Changed | Nature |
|------|--------------|--------|
| `server/app/streaming_routes.py` | ~60 lines (import + `stream_generator` body) | Replace callback pattern with async-for SDK loop |
| `server/app/main.py` | ~3 lines (import) + ~40 lines across 2 route handlers | Swap import; replace `stream_chat` calls with SDK adapter |
| `server/app/agentic_service.py` | 1 line (comment) | Deprecation comment above `stream_chat` |
| `server/tests/test_eagle_sdk_eval.py` | 0 lines | No changes |

Total estimated changed lines: ~104 (excluding blank lines and comments).

---

*Scribe | 2026-02-22T22:36:57 | plan v1 | Format: markdown | Source: experts:backend:plan*
