# Fix: Wire Service Tools to Strands Supervisor Agent

## Context

**Problem**: Document generation via chat shows `document_generator ({})` with empty parameters and produces no output.

**Root Cause**: In `strands_agentic_service.py`, the `_build_service_tools()` function (line 587) creates the actual AWS service tools (`create_document`, `s3_document_ops`, `search_far`, etc.), but this function is **never called**. The supervisor agent only receives `skill_tools` (subagents), not the service tools that actually perform operations.

**Evidence from screenshot**:
- Tool shown: `TOOL: DOCUMENT_GENERATOR` with `document_generator ({})`
- Empty params `{}` because model is confused — `document_generator` is a subagent expecting `query: str`, not the `create_document` tool expecting `{doc_type, title, data}`

## Files to Modify

| File | Change |
|------|--------|
| `server/app/strands_agentic_service.py` | Wire `_build_service_tools()` into `sdk_query()` and `sdk_query_streaming()` |

## Implementation Plan

### Step 1: Fix `sdk_query()` (lines 782-807)

**Current code** (lines 782-807):
```python
skill_tools = build_skill_tools(
    tier=tier,
    skill_names=skill_names,
    tenant_id=tenant_id,
    user_id=user_id,
    workspace_id=resolved_workspace_id,
)

system_prompt = build_supervisor_prompt(...)

strands_history = _to_strands_messages(messages) if messages else None

supervisor = Agent(
    model=_model,
    system_prompt=system_prompt,
    tools=skill_tools,  # <-- BUG: Missing service_tools
    callback_handler=None,
    messages=strands_history,
)
```

**Fixed code**:
```python
skill_tools = build_skill_tools(
    tier=tier,
    skill_names=skill_names,
    tenant_id=tenant_id,
    user_id=user_id,
    workspace_id=resolved_workspace_id,
)

# Build service tools (S3, DynamoDB, create_document, search_far, etc.)
service_tools = _build_service_tools(
    tenant_id=tenant_id,
    user_id=user_id,
    session_id=session_id,
)

system_prompt = build_supervisor_prompt(...)

strands_history = _to_strands_messages(messages) if messages else None

supervisor = Agent(
    model=_model,
    system_prompt=system_prompt,
    tools=skill_tools + service_tools,  # <-- FIX: Add service_tools
    callback_handler=None,
    messages=strands_history,
)
```

### Step 2: Fix `sdk_query_streaming()` (lines 880-907)

**Current code** (lines 880-907):
```python
skill_tools = build_skill_tools(
    tier=tier,
    skill_names=skill_names,
    tenant_id=tenant_id,
    user_id=user_id,
    workspace_id=resolved_workspace_id,
)

system_prompt = build_supervisor_prompt(...)

strands_history = _to_strands_messages(messages) if messages else None
chunk_queue: queue.Queue = queue.Queue()

handler = QueueCallbackHandler(chunk_queue)

supervisor = Agent(
    model=_model,
    system_prompt=system_prompt,
    tools=skill_tools,  # <-- BUG: Missing service_tools
    callback_handler=handler,
    messages=strands_history,
)
```

**Fixed code**:
```python
skill_tools = build_skill_tools(
    tier=tier,
    skill_names=skill_names,
    tenant_id=tenant_id,
    user_id=user_id,
    workspace_id=resolved_workspace_id,
)

# Build service tools (S3, DynamoDB, create_document, search_far, etc.)
service_tools = _build_service_tools(
    tenant_id=tenant_id,
    user_id=user_id,
    session_id=session_id,
)

system_prompt = build_supervisor_prompt(...)

strands_history = _to_strands_messages(messages) if messages else None
chunk_queue: queue.Queue = queue.Queue()

handler = QueueCallbackHandler(chunk_queue)

supervisor = Agent(
    model=_model,
    system_prompt=system_prompt,
    tools=skill_tools + service_tools,  # <-- FIX: Add service_tools
    callback_handler=handler,
    messages=strands_history,
)
```

**Note**: We omit `result_queue` and `loop` params for now since the streaming loop doesn't currently handle `tool_result` events. Documents will still be created and saved to S3; streaming document cards can be added in a follow-up.

## Exact Edit Strings

### Edit 1: `sdk_query()` (line 782-807)

**old_string** (unique context includes `callback_handler=None`):
```
    skill_tools = build_skill_tools(
        tier=tier,
        skill_names=skill_names,
        tenant_id=tenant_id,
        user_id=user_id,
        workspace_id=resolved_workspace_id,
    )

    system_prompt = build_supervisor_prompt(
        tenant_id=tenant_id,
        user_id=user_id,
        tier=tier,
        agent_names=[t.__name__ for t in skill_tools],
        workspace_id=resolved_workspace_id,
    )

    # Convert conversation history to Strands format (excludes current prompt)
    strands_history = _to_strands_messages(messages) if messages else None

    supervisor = Agent(
        model=_model,
        system_prompt=system_prompt,
        tools=skill_tools,
        callback_handler=None,
        messages=strands_history,
    )
```

### Edit 2: `sdk_query_streaming()` (line 880-907)

**old_string** (unique context includes `chunk_queue` and `callback_handler=handler`):
```
    skill_tools = build_skill_tools(
        tier=tier,
        skill_names=skill_names,
        tenant_id=tenant_id,
        user_id=user_id,
        workspace_id=resolved_workspace_id,
    )

    system_prompt = build_supervisor_prompt(
        tenant_id=tenant_id,
        user_id=user_id,
        tier=tier,
        agent_names=[t.__name__ for t in skill_tools],
        workspace_id=resolved_workspace_id,
    )

    strands_history = _to_strands_messages(messages) if messages else None
    chunk_queue: queue.Queue = queue.Queue()

    handler = QueueCallbackHandler(chunk_queue)

    supervisor = Agent(
        model=_model,
        system_prompt=system_prompt,
        tools=skill_tools,
        callback_handler=handler,
        messages=strands_history,
    )
```

## Verification

1. **Lint check**: `cd server && ruff check app/strands_agentic_service.py`
2. **Type check**: `cd client && npx tsc --noEmit` (no changes to frontend)
3. **Manual test**:
   - Start backend: `cd server && uvicorn app.main:app --reload --port 8000`
   - Start frontend: `cd client && npm run dev`
   - Chat: "Generate a SOW for CT scanner procurement"
   - Expected: `create_document` tool called with proper params, document saved to S3
4. **Unit tests**: `cd server && python -m pytest tests/ -v -k "strands or document"`

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Service tools conflict with skill tools | Tool names are unique (`create_document` vs `document_generator`) |
| Missing imports | `_build_service_tools` already defined in same file |
| Session ID not available | Already passed to `sdk_query()` and `sdk_query_streaming()` |
| Streaming result_queue setup | Omitted for now; can be added in follow-up |
