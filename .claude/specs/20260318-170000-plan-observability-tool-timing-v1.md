# Plan: API Endpoint & Tool Call Observability

## Problem

Tool calls and API endpoints lack queryable timing data in CloudWatch. The existing telemetry infrastructure collects timing locally (`ChatTraceCollector`, `SpanTracker`) but doesn't emit it in a way that's easy to query, alert on, or visualize. When a user reports "the chat is slow", we can't quickly answer "which tool took 40 seconds?" or "is the /api/chat endpoint timing out?"

## What Exists (Already Working)

| Component | File | What It Does |
|-----------|------|-------------|
| `ChatTraceCollector` | `telemetry/chat_trace_collector.py:92-111` | Tracks `start_tool_span()` / `end_tool_span()` with `duration_ms` |
| `SpanTracker` | `telemetry/span_tracker.py:15-153` | Tracks tool + subagent spans with `on_pre_tool_use` / `on_post_tool_use` hooks |
| `cloudwatch_emitter.py` | `telemetry/cloudwatch_emitter.py:44-105` | Emits structured events to `/eagle/telemetry` log group |
| `log_context.py` | `telemetry/log_context.py:26-74` | Per-request contextvars (tenant_id, user_id, session_id) injected into all logs |
| `JSONFormatter` | `telemetry/log_context.py:57-74` | Structured JSON log format for CloudWatch |
| REST timing | `main.py:238,321` | `start = time.time()` -> `elapsed_ms` in response |
| `agent_status` SSE | `streaming_routes.py:73` | Real-time status text during streaming |
| Langfuse | `telemetry/langfuse_client.py` | Full trace collection with error classification |

## Gaps

| Gap | Impact | Priority |
|-----|--------|----------|
| Tool timing not emitted to CloudWatch | Can't query "which tools are slow" | P0 |
| No `duration_ms` in SSE `complete` event | Frontend can't display total time | P1 |
| No per-endpoint timing logs | Can't identify slow API routes | P1 |
| No CloudWatch custom metrics | Can't set alarms on tool latency | P2 |
| No subagent delegation timing in own logs | Rely entirely on Langfuse for agent breakdown | P2 |

## Implementation Plan

### Step 1: Emit Tool Timing to CloudWatch (Backend)

**Files:** `streaming_routes.py`, `telemetry/cloudwatch_emitter.py`

Wire the existing `SpanTracker` span data into CloudWatch emission at stream completion.

In `streaming_routes.py`, after the stream loop completes (around line 230), emit each completed tool span:

```python
# After stream completes, emit tool timing telemetry
if span_tracker:
    for span in span_tracker.get_completed_spans():
        emit_telemetry_event(
            event_type="tool.timing",
            tenant_id=tenant_id,
            data={
                "tool_name": span.name,
                "duration_ms": span.duration_ms,
                "parent_agent": span.parent_agent,
                "success": span.success,
                "session_id": session_id,
            },
            session_id=session_id,
            user_id=user_id,
        )
```

**CloudWatch Insights query to find slow tools:**
```
filter event_type = "tool.timing"
| stats avg(data.duration_ms) as avg_ms, max(data.duration_ms) as max_ms, count(*) as calls by data.tool_name
| sort max_ms desc
```

### Step 2: Add Request Timing Middleware (Backend)

**File:** `main.py` -- add a FastAPI middleware that logs every request with timing.

```python
@app.middleware("http")
async def request_timing_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = int((time.perf_counter() - start) * 1000)
    logger.info(
        "request_completed",
        extra={
            "endpoint": request.url.path,
            "method": request.method,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    return response
```

**CloudWatch Insights query to find slow endpoints:**
```
filter msg = "request_completed"
| stats avg(duration_ms) as avg_ms, max(duration_ms) as max_ms, count(*) as requests by endpoint
| sort max_ms desc
```

### Step 3: Include `duration_ms` in SSE `complete` Event (Backend + Frontend)

**Backend file:** `streaming_routes.py`

Track `stream_start = time.perf_counter()` at the top of `stream_generator()`. When emitting the `complete` event, include the total duration:

```python
# In stream_generator, at the top:
stream_start = time.perf_counter()

# When emitting complete event:
duration_ms = int((time.perf_counter() - stream_start) * 1000)
await writer.write_complete(sse_queue, metadata={
    **existing_metadata,
    "duration_ms": duration_ms,
})
```

**Frontend file:** `use-agent-stream.ts`

In `processEventData`, extract `duration_ms` from the `complete` event metadata and pass to `onComplete`:

```typescript
if (event.type === 'complete') {
    const durationMs = event.metadata?.duration_ms;
    // Include in onComplete callback
}
```

### Step 4: Add Subagent Timing Emission (Backend)

**File:** `strands_agentic_service.py`

When a subagent completes, emit a `agent.timing` event:

```python
emit_telemetry_event(
    event_type="agent.timing",
    tenant_id=tenant_id,
    data={
        "agent_name": agent_name,
        "duration_ms": duration_ms,
        "tools_called": tools_called,
        "session_id": session_id,
    },
    session_id=session_id,
    user_id=user_id,
)
```

### Step 5 (Future): CloudWatch Custom Metrics

Add `PutMetricData` calls for dashboard/alarm creation:

- `EAGLE/ToolLatency` -- dimension: `ToolName`
- `EAGLE/RequestLatency` -- dimension: `Endpoint`
- `EAGLE/AgentLatency` -- dimension: `AgentName`

Requires adding `cloudwatch:PutMetricData` to the `appRole` IAM policy.

## Validation

```bash
# Backend lint
cd server && ruff check app/main.py app/streaming_routes.py app/telemetry/

# Backend tests
python -m pytest tests/ -v --tb=short \
  --ignore=tests/test_strands_eval.py \
  --ignore=tests/test_eagle_sdk_eval.py

# CloudWatch query to verify emission
filter event_type = "tool.timing" | stats count(*) by data.tool_name | limit 20

# CloudWatch query for request timing
filter msg = "request_completed" | stats avg(duration_ms), max(duration_ms) by endpoint | limit 20
```

## Files to Modify

| File | Change | Priority |
|------|--------|----------|
| `server/app/main.py` | Add request timing middleware | P1 |
| `server/app/streaming_routes.py` | Emit tool timing at stream end + add duration_ms to complete event | P0 |
| `server/app/telemetry/cloudwatch_emitter.py` | Add `tool.timing` and `agent.timing` event types | P0 |
| `server/app/strands_agentic_service.py` | Emit agent.timing when subagent completes | P2 |
| `client/hooks/use-agent-stream.ts` | Extract duration_ms from complete event | P1 |
