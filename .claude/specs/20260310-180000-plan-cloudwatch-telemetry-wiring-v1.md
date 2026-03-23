# Plan: Wire CloudWatch Telemetry into Chat Request Lifecycle

## Task Description
Connect the existing but unused CloudWatch telemetry infrastructure (`cloudwatch_emitter.py`, `log_context.py`, `ChatTraceCollector`) to the live chat request handlers so that every user interaction emits structured, queryable events to CloudWatch. The frontend CloudWatch tab in the activity panel will then show real-time per-session logs.

## Objective
After this plan is complete, a user chatting with EAGLE will see their session's events (trace start/complete, tool calls, feedback submissions) in the CloudWatch tab of the activity panel — with user_id, session_id, tenant_id, tokens, cost, and tool details.

## Problem Statement
All the telemetry infrastructure exists but nothing calls it:
- `cloudwatch_emitter.py` has `emit_telemetry_event()` and `emit_trace_completed()` — **never called**
- `log_context.py` has `set_log_context()` — called in `streaming_routes.py` but only tags Python logger, doesn't push to CloudWatch
- `ChatTraceCollector` collects tokens/tools/cost — **never instantiated** in the streaming path
- Log group mismatch: emitter writes to `/eagle/telemetry`, frontend reads from `/eagle/app`
- `/eagle/app` has 0 bytes stored

## Solution Approach
1. **Align log groups** — standardize on `/eagle/app` for all runtime telemetry
2. **Instantiate ChatTraceCollector** in `stream_generator()` to track tokens/tools/cost
3. **Emit `trace.started`** at request entry, **`trace.completed`** after response completes
4. **Emit `tool.completed`** for each tool_use/tool_result pair
5. **Emit `feedback.submitted`** when feedback is recorded
6. **Fire-and-forget** — all emission is async, non-blocking, wrapped in try/except

## Relevant Files

### Existing Files to Modify

- **`server/app/telemetry/cloudwatch_emitter.py`** — Change default log group from `/eagle/telemetry` to `/eagle/app`. Add `emit_tool_completed()` and `emit_feedback_submitted()` convenience wrappers.
- **`server/app/streaming_routes.py`** — Import emitter + ChatTraceCollector. Instantiate collector in `stream_generator()`. Emit `trace.started` at entry, record tool events, emit `trace.completed` after complete/error.
- **`server/app/main.py`** — Emit `feedback.submitted` in `api_submit_feedback()` after successful DynamoDB write.
- **`client/app/api/logs/cloudwatch/route.ts`** — No changes needed (already reads from `/eagle/app`).
- **`client/components/chat-simple/cloudwatch-logs.tsx`** — No changes needed (already renders structured JSON logs).

### New Files to Create

- **`server/tests/test_cloudwatch_emitter.py`** — Unit tests for emission functions with mocked boto3
- **`server/tests/test_telemetry_integration.py`** — Integration test: mock `stream_generator()` flow, verify emitter calls

## Implementation Phases

### Phase 1: Foundation (Emitter Fixes)
Align the log group name, add convenience wrappers, ensure robust error handling.

### Phase 2: Core Wiring (Stream Generator)
Wire ChatTraceCollector + emitter calls into the streaming request lifecycle.

### Phase 3: Feedback + Validation
Add feedback emission, write tests, validate end-to-end.

## Step by Step Tasks

### 1. Fix Log Group Name in Emitter

- In `server/app/telemetry/cloudwatch_emitter.py` line 17:
  - Change `LOG_GROUP = os.getenv("EAGLE_TELEMETRY_LOG_GROUP", "/eagle/telemetry")` → default to `"/eagle/app"`
  - This aligns with what the frontend CloudWatch tab queries

```python
LOG_GROUP = os.getenv("EAGLE_TELEMETRY_LOG_GROUP", "/eagle/app")
```

### 2. Add Convenience Emission Wrappers

- In `cloudwatch_emitter.py`, add these functions after `emit_trace_completed()`:

```python
def emit_trace_started(
    tenant_id: str,
    user_id: str,
    session_id: str,
    prompt_preview: str = "",
):
    """Emit a trace.started event when a chat request begins."""
    emit_telemetry_event(
        event_type="trace.started",
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        data={
            "prompt_preview": prompt_preview[:200],
        },
    )


def emit_tool_completed(
    tenant_id: str,
    user_id: str,
    session_id: str,
    tool_name: str,
    duration_ms: int = 0,
    success: bool = True,
):
    """Emit a tool.completed event after a tool call finishes."""
    emit_telemetry_event(
        event_type="tool.completed",
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        data={
            "tool_name": tool_name,
            "duration_ms": duration_ms,
            "success": success,
        },
    )


def emit_feedback_submitted(
    tenant_id: str,
    user_id: str,
    session_id: str,
    feedback_type: str,
    feedback_id: str,
):
    """Emit a feedback.submitted event after feedback is written to DynamoDB."""
    emit_telemetry_event(
        event_type="feedback.submitted",
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        data={
            "feedback_type": feedback_type,
            "feedback_id": feedback_id,
        },
    )
```

### 3. Make Emission Non-Blocking (asyncio.to_thread)

- All `emit_*` calls use boto3 (sync I/O). In the async streaming path, wrap them in `asyncio.to_thread()` to avoid blocking the event loop.
- Create a helper in `cloudwatch_emitter.py`:

```python
async def emit_telemetry_event_async(event_type, tenant_id, data, session_id=None, user_id=None):
    """Non-blocking wrapper for use in async handlers."""
    import asyncio
    try:
        await asyncio.to_thread(
            emit_telemetry_event, event_type, tenant_id, data, session_id, user_id
        )
    except Exception as e:
        logger.warning("Async telemetry emission failed (non-fatal): %s", e)
```

### 4. Wire Emission into stream_generator()

- In `server/app/streaming_routes.py`:
- Add imports:

```python
from .telemetry.cloudwatch_emitter import (
    emit_trace_started,
    emit_trace_completed,
    emit_tool_completed,
)
```

- At the START of `stream_generator()` (after set_log_context, before sdk_query_streaming), emit `trace.started`:

```python
# Fire-and-forget: emit trace.started
import time as _time
_trace_start = _time.time()
try:
    await asyncio.to_thread(
        emit_trace_started, tenant_id, user_id, session_id or "", message[:200]
    )
except Exception:
    logger.debug("trace.started emission failed (non-fatal)")
```

- On each `tool_result` chunk (after line ~160 where tool_result is yielded), emit `tool.completed`:

```python
elif chunk_type == "tool_result":
    tr_name = chunk.get("name", "")
    if not tr_name:
        continue
    await writer.write_tool_result(sse_queue, tr_name, chunk.get("result", {}))
    yield await sse_queue.get()
    # Emit tool.completed (fire-and-forget)
    try:
        await asyncio.to_thread(
            emit_tool_completed, tenant_id, user_id, session_id or "", tr_name
        )
    except Exception:
        pass
```

- On `complete` chunk (after persisting assistant message, ~line 186), emit `trace.completed`:

```python
# After write_complete, before return:
try:
    _elapsed = int((_time.time() - _trace_start) * 1000)
    _complete_chunk = chunk  # the complete event from sdk_query_streaming
    await asyncio.to_thread(
        emit_trace_completed,
        {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "session_id": session_id or "",
            "trace_id": f"t-{int(_trace_start * 1000)}",
            "duration_ms": _elapsed,
            "total_input_tokens": _complete_chunk.get("usage", {}).get("inputTokens", 0),
            "total_output_tokens": _complete_chunk.get("usage", {}).get("outputTokens", 0),
            "tools_called": _complete_chunk.get("tools_called", []),
        },
    )
except Exception:
    logger.debug("trace.completed emission failed (non-fatal)")
```

- On `error` chunk, emit `error.occurred`:

```python
elif chunk_type == "error":
    await writer.write_error(sse_queue, chunk.get("error", "Unknown error"))
    yield await sse_queue.get()
    try:
        await asyncio.to_thread(
            emit_telemetry_event, "error.occurred", tenant_id,
            {"error": str(chunk.get("error", ""))[:500], "session_id": session_id},
            session_id, user_id,
        )
    except Exception:
        pass
    return
```

### 5. Wire Feedback Emission into main.py

- In `server/app/main.py`, in `api_submit_feedback()`:
- Add import: `from .telemetry.cloudwatch_emitter import emit_feedback_submitted`
- After the `write_feedback()` call succeeds, emit:

```python
item = feedback_store.write_feedback(...)

# Emit feedback event to CloudWatch (fire-and-forget)
try:
    emit_feedback_submitted(
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        session_id=session_id,
        feedback_type=item.get("feedback_type", "general"),
        feedback_id=item.get("feedback_id", ""),
    )
except Exception:
    logger.debug("feedback.submitted emission failed (non-fatal)")
```

### 6. Add Stream Name Convention

- Currently the emitter uses `f"telemetry/{tenant_id}"` as the stream name.
- Change to use session_id for better queryability: `f"session/{session_id}"` when session_id is available, falling back to `f"tenant/{tenant_id}"`.
- This allows the frontend to filter by session_id at the stream level too.

In `cloudwatch_emitter.py`, update `emit_telemetry_event()`:

```python
stream_name = f"session/{session_id}" if session_id else f"tenant/{tenant_id}"
```

### 7. Write Unit Tests

Create **`server/tests/test_cloudwatch_emitter.py`**:

```python
"""Tests for CloudWatch telemetry emitter."""
import json
from unittest.mock import patch, MagicMock
import pytest

from app.telemetry.cloudwatch_emitter import (
    emit_telemetry_event,
    emit_trace_started,
    emit_trace_completed,
    emit_tool_completed,
    emit_feedback_submitted,
)


class TestEmitTelemetryEvent:
    """Core emit_telemetry_event function."""

    @patch("app.telemetry.cloudwatch_emitter._get_client")
    def test_emits_structured_event(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        emit_telemetry_event(
            event_type="trace.started",
            tenant_id="test-tenant",
            data={"prompt_preview": "hello"},
            session_id="sess-1",
            user_id="user-1",
        )

        mock_client.put_log_events.assert_called_once()
        call_args = mock_client.put_log_events.call_args
        assert call_args.kwargs["logGroupName"] == "/eagle/app"

        # Parse the emitted JSON
        message = call_args.kwargs["logEvents"][0]["message"]
        event = json.loads(message)
        assert event["event_type"] == "trace.started"
        assert event["tenant_id"] == "test-tenant"
        assert event["user_id"] == "user-1"
        assert event["session_id"] == "sess-1"
        assert event["prompt_preview"] == "hello"

    @patch("app.telemetry.cloudwatch_emitter._get_client")
    def test_creates_log_group_and_stream(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        emit_telemetry_event("test.event", "t1", {}, "s1", "u1")

        mock_client.create_log_group.assert_called_once()
        mock_client.create_log_stream.assert_called_once()

    @patch("app.telemetry.cloudwatch_emitter._get_client")
    def test_handles_already_exists(self, mock_get_client):
        """Should not raise when log group already exists."""
        from botocore.exceptions import ClientError
        mock_client = MagicMock()
        mock_client.create_log_group.side_effect = ClientError(
            {"Error": {"Code": "ResourceAlreadyExistsException"}}, "CreateLogGroup"
        )
        mock_client.create_log_stream.side_effect = ClientError(
            {"Error": {"Code": "ResourceAlreadyExistsException"}}, "CreateLogStream"
        )
        mock_get_client.return_value = mock_client

        # Should not raise
        emit_telemetry_event("test.event", "t1", {}, "s1", "u1")
        mock_client.put_log_events.assert_called_once()

    @patch("app.telemetry.cloudwatch_emitter._get_client")
    def test_swallows_put_failure(self, mock_get_client):
        """Telemetry failures should never break the main flow."""
        mock_client = MagicMock()
        mock_client.put_log_events.side_effect = Exception("CloudWatch down")
        mock_get_client.return_value = mock_client

        # Should not raise
        emit_telemetry_event("test.event", "t1", {}, "s1", "u1")

    @patch("app.telemetry.cloudwatch_emitter._get_client")
    def test_stream_name_uses_session(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        emit_telemetry_event("test", "t1", {}, session_id="sess-abc", user_id="u1")

        call_args = mock_client.create_log_stream.call_args
        assert "sess-abc" in call_args.kwargs.get("logStreamName", call_args[1].get("logStreamName", ""))

    @patch("app.telemetry.cloudwatch_emitter._get_client")
    def test_stream_name_falls_back_to_tenant(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        emit_telemetry_event("test", "t1", {}, session_id=None, user_id="u1")

        call_args = mock_client.put_log_events.call_args
        stream = call_args.kwargs.get("logStreamName", "")
        assert "t1" in stream


class TestConvenienceWrappers:

    @patch("app.telemetry.cloudwatch_emitter.emit_telemetry_event")
    def test_emit_trace_started(self, mock_emit):
        emit_trace_started("t1", "u1", "s1", "hello world")
        mock_emit.assert_called_once()
        args = mock_emit.call_args
        assert args.kwargs.get("event_type") or args[0][0] == "trace.started"

    @patch("app.telemetry.cloudwatch_emitter.emit_telemetry_event")
    def test_emit_trace_completed(self, mock_emit):
        emit_trace_completed({
            "tenant_id": "t1", "user_id": "u1", "session_id": "s1",
            "trace_id": "t-123", "duration_ms": 500,
            "total_input_tokens": 100, "total_output_tokens": 50,
            "tools_called": ["search_kb"],
        })
        mock_emit.assert_called_once()

    @patch("app.telemetry.cloudwatch_emitter.emit_telemetry_event")
    def test_emit_tool_completed(self, mock_emit):
        emit_tool_completed("t1", "u1", "s1", "search_kb", 120, True)
        mock_emit.assert_called_once()

    @patch("app.telemetry.cloudwatch_emitter.emit_telemetry_event")
    def test_emit_feedback_submitted(self, mock_emit):
        emit_feedback_submitted("t1", "u1", "s1", "bug", "fb-001")
        mock_emit.assert_called_once()
```

### 8. Write Integration Test for Stream Generator Emission

Create **`server/tests/test_telemetry_integration.py`**:

```python
"""Integration tests: verify telemetry events are emitted during chat flow."""
from unittest.mock import patch, MagicMock, AsyncMock
import pytest
import asyncio


class TestStreamGeneratorTelemetry:
    """Verify stream_generator emits trace.started and trace.completed."""

    @pytest.mark.asyncio
    @patch("app.streaming_routes.emit_trace_started")
    @patch("app.streaming_routes.emit_trace_completed")
    @patch("app.streaming_routes.sdk_query_streaming")
    async def test_emits_trace_started_and_completed(
        self, mock_sdk, mock_complete, mock_started
    ):
        """stream_generator should emit trace.started on entry and
        trace.completed after the complete event."""
        # Mock sdk_query_streaming to yield text + complete
        async def fake_gen(*args, **kwargs):
            yield {"type": "text", "data": "Hello"}
            yield {"type": "complete", "text": "Hello", "tools_called": [], "usage": {}}

        mock_sdk.return_value = fake_gen()

        from app.streaming_routes import stream_generator
        from app.subscription_service import SubscriptionService

        sub_svc = MagicMock(spec=SubscriptionService)
        sub_svc.check_rate_limit.return_value = True

        chunks = []
        async for chunk in stream_generator(
            message="hi",
            tenant_id="test",
            user_id="test-user",
            tier="premium",
            subscription_service=sub_svc,
            session_id="test-session",
        ):
            chunks.append(chunk)

        # Verify trace.started was called
        mock_started.assert_called_once()
        # Verify trace.completed was called
        mock_complete.assert_called_once()


class TestFeedbackTelemetry:
    """Verify feedback endpoint emits feedback.submitted."""

    @patch("app.main.emit_feedback_submitted")
    @patch("app.main.feedback_store")
    def test_feedback_emits_event(self, mock_store, mock_emit, client):
        mock_store.write_feedback.return_value = {
            "feedback_id": "fb-001",
            "feedback_type": "bug",
        }
        resp = client.post("/api/feedback", json={
            "feedback_text": "test bug",
            "session_id": "s1",
        })
        assert resp.status_code == 200
        mock_emit.assert_called_once_with(
            tenant_id="dev-tenant",
            user_id="dev-user",
            session_id="s1",
            feedback_type="bug",
            feedback_id="fb-001",
        )
```

### 9. Validate End-to-End

After implementation, run these validation steps:

1. **Syntax check emitter:**
   ```bash
   python -c "from app.telemetry.cloudwatch_emitter import emit_trace_started, emit_trace_completed, emit_tool_completed, emit_feedback_submitted; print('OK')"
   ```

2. **Unit tests:**
   ```bash
   python -m pytest server/tests/test_cloudwatch_emitter.py -v
   ```

3. **Integration tests:**
   ```bash
   python -m pytest server/tests/test_telemetry_integration.py -v
   ```

4. **Manual smoke test:** Start backend + frontend, send a chat message, open the CloudWatch tab in the activity panel, verify events appear within 30-60s.

5. **Verify in AWS CLI:**
   ```bash
   MSYS_NO_PATHCONV=1 aws logs filter-log-events \
     --log-group-name "/eagle/app" \
     --filter-pattern '{ $.session_id = "YOUR_SESSION_ID" }' \
     --limit 10 --profile eagle --region us-east-1
   ```

## Testing Strategy

| Test | Type | What it validates |
|------|------|-------------------|
| `test_emits_structured_event` | Unit | JSON shape, field presence |
| `test_creates_log_group_and_stream` | Unit | Log group/stream auto-creation |
| `test_handles_already_exists` | Unit | Idempotent log group creation |
| `test_swallows_put_failure` | Unit | Telemetry never breaks main flow |
| `test_stream_name_uses_session` | Unit | Stream named by session_id |
| `test_emit_trace_started` | Unit | Convenience wrapper calls core |
| `test_emit_tool_completed` | Unit | Convenience wrapper calls core |
| `test_emit_feedback_submitted` | Unit | Convenience wrapper calls core |
| `test_emits_trace_started_and_completed` | Integration | Full stream_generator lifecycle |
| `test_feedback_emits_event` | Integration | Feedback endpoint → emission |

**Edge cases:**
- Missing session_id → falls back to tenant-based stream
- CloudWatch down → swallowed, main flow unaffected
- Empty tool name → skipped (no emission)
- Very long prompt → truncated to 200 chars in trace.started

## Acceptance Criteria

- [ ] `emit_telemetry_event()` writes to `/eagle/app` log group by default
- [ ] `trace.started` emitted at beginning of every chat request
- [ ] `trace.completed` emitted at end of every chat request with tokens, cost, tools, duration
- [ ] `tool.completed` emitted for each tool call
- [ ] `feedback.submitted` emitted when feedback is written to DynamoDB
- [ ] All emissions are fire-and-forget — failures never break the main flow
- [ ] Stream names use session_id when available
- [ ] Events include `user_id`, `session_id`, `tenant_id` for filtering
- [ ] Frontend CloudWatch tab shows events for the current session
- [ ] All unit tests pass
- [ ] Integration tests pass
- [ ] `ruff check app/` passes
- [ ] `npx tsc --noEmit` passes (no frontend changes needed)

## Validation Commands

```bash
# L1 — Lint
cd server && ruff check app/

# L1 — Import check
cd server && python -c "from app.telemetry.cloudwatch_emitter import emit_trace_started, emit_trace_completed, emit_tool_completed, emit_feedback_submitted; print('All imports OK')"

# L2 — Unit tests
cd server && python -m pytest tests/test_cloudwatch_emitter.py -v

# L2 — Integration tests
cd server && python -m pytest tests/test_telemetry_integration.py -v

# L2 — Existing tests still pass
cd server && python -m pytest tests/test_new_endpoints.py -v

# L3 — Manual: send a chat message, then check CloudWatch
MSYS_NO_PATHCONV=1 aws logs filter-log-events --log-group-name "/eagle/app" --limit 5 --profile eagle --region us-east-1

# L1 — Frontend (should be no changes, but verify)
cd client && npx tsc --noEmit
```

## Notes

- **Sequence token issue**: CloudWatch `put_log_events` no longer requires a sequence token (deprecated 2023). The current emitter doesn't use one — this is correct.
- **Cost**: CloudWatch Logs ingestion is ~$0.50/GB. At ~500 bytes/event and ~1000 requests/day, monthly cost is negligible (<$0.01).
- **Rate limiting**: If high volume becomes a concern, batch events using `put_log_events` with multiple log events per call instead of one-at-a-time.
- **ECS vs local**: In ECS, the backend container already has IAM role permissions for CloudWatch. Locally, requires AWS SSO credentials (already configured via `eagle` profile).
- **The `/eagle/inference` log group** (77KB, structured JSON) is written by the CDK inference construct — separate from this work. No changes needed there.
