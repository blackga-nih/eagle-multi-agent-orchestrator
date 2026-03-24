# Plan: Unified Telemetry + Reasoning Capture

## Task Description
Merge the CloudWatch telemetry wiring plan and the consultation-first reasoning capture plan into a single implementation. Both wire into `stream_generator()` at the same hook points (tool_result, complete, error). This plan builds them together — one pass through the streaming pipeline, one set of tests.

## Objective
After this plan is complete:
1. Every chat request emits structured CloudWatch events (`trace.started`, `tool.completed`, `trace.completed`) to `/eagle/app` — visible in the activity panel's CloudWatch tab
2. Tool results include a `reasoning` field capturing why the tool was called and what it determined
3. Reasoning entries accumulate per-session in a `ReasoningLog`, persisted to DynamoDB as `REASONING#{session_id}`
4. Generated documents include an "Appendix: AI Decision Rationale" section
5. `StreamEventType.REASONING` SSE events are emitted to the frontend (activating unused infrastructure)
6. Feedback submissions emit `feedback.submitted` to CloudWatch
7. All telemetry is fire-and-forget — failures never break the main flow

## Problem Statement
Two systems need to be wired into the same streaming pipeline:

**CloudWatch telemetry** — All infrastructure exists (`cloudwatch_emitter.py`, `log_context.py`, `ChatTraceCollector`) but nothing calls it. Log group mismatch: emitter writes to `/eagle/telemetry`, frontend reads from `/eagle/app`. `/eagle/app` has 0 bytes.

**Reasoning capture** — `StreamEventType.REASONING` and `write_reasoning()` exist in `stream_protocol.py` but are never called. Tool results contain no reasoning fields. No session-scoped reasoning accumulator exists. oa-intake skill says "document the rationale" but no code implements it.

**What c418a43 already did** — Supervisor prompt rewritten for 5th grade reading level, short responses, consultation-first tone. `query_contract_matrix` tool registered. Intake form card with fast-path bypass. Bedrock trace emission. The consultation-first prompting is ~70% done.

## Solution Approach
One unified pass through `stream_generator()` handles both concerns at each hook point:

| Hook Point | CloudWatch (observability) | Reasoning (auditability) |
|---|---|---|
| **Request entry** | `emit_trace_started()` | Instantiate `ReasoningLog` |
| **tool_result** | `emit_tool_completed()` | Extract `reasoning` field → accumulate in log → emit REASONING SSE |
| **complete** | `emit_trace_completed()` with tokens/cost/duration | Persist `ReasoningLog` to DynamoDB |
| **error** | `emit_error_occurred()` | (no reasoning on error) |
| **feedback** (main.py) | `emit_feedback_submitted()` | (separate endpoint) |

## Relevant Files

### Modify
- **`server/app/telemetry/cloudwatch_emitter.py`** — Fix log group `/eagle/telemetry` → `/eagle/app`. Add `emit_trace_started()`, `emit_tool_completed()`, `emit_feedback_submitted()`. Update stream naming to use session_id.
- **`server/app/streaming_routes.py`** — Wire both CloudWatch emission and reasoning capture into `stream_generator()` at tool_result, complete, and error hook points.
- **`server/app/main.py`** — Add `emit_feedback_submitted()` call after `write_feedback()`.
- **`server/app/agentic_service.py`** — Add `reasoning` field to `_exec_create_document()`, `_exec_query_compliance_matrix()`, `_exec_search_far()` return dicts.
- **`server/app/tools/contract_matrix.py`** — Add `reasoning` field to `query_contract_matrix` return dict.
- **`client/hooks/use-agent-stream.ts`** — Handle `reasoning` SSE event type in `processEventData()`.
- **`client/components/chat-simple/agent-logs.tsx`** — Render reasoning log entries with distinct styling.
- **`eagle-plugin/agents/supervisor/agent.md`** — Add Phase 1→2→3 consultation gating section (additive, builds on c418a43 changes).

### Create
- **`server/app/reasoning_store.py`** — `ReasoningEntry` dataclass + `ReasoningLog` accumulator with DynamoDB persistence and markdown appendix rendering.
- **`server/tests/test_telemetry_reasoning.py`** — Unified test file covering CloudWatch emission, reasoning accumulation, and document appendix.

### No Changes Needed
- `client/app/api/logs/cloudwatch/route.ts` — Already reads from `/eagle/app`
- `client/components/chat-simple/cloudwatch-logs.tsx` — Already renders structured JSON logs
- `server/app/stream_protocol.py` — `REASONING` event type and `write_reasoning()` already exist
- `server/app/telemetry/log_context.py` — Already working, called in `streaming_routes.py`
- `server/app/telemetry/chat_trace_collector.py` — Skip; emitter wrappers handle everything directly

## Implementation Phases

### Phase 1: Foundation (emitter + reasoning store)
Fix CloudWatch log group, add emitter wrappers, create `ReasoningLog` store. No wiring yet.

### Phase 2: Stream Generator Hooks (the core merge)
Single pass through `stream_generator()` — emit CloudWatch events AND extract/accumulate/emit reasoning. This is where the two plans converge into one code change.

### Phase 3: Tool Reasoning Fields
Add `reasoning` key to tool handler return dicts in `agentic_service.py` and `contract_matrix.py`.

### Phase 4: Document Appendix + Feedback
Inject accumulated reasoning into `create_document` output. Add feedback CloudWatch emission.

### Phase 5: Frontend + Prompt + Validation
Wire REASONING SSE into frontend. Add Phase 1→2→3 consultation gating to supervisor prompt. Test everything.

## Step by Step Tasks

### 1. Fix CloudWatch Emitter

In **`server/app/telemetry/cloudwatch_emitter.py`**:

**1a.** Change default log group:
```python
LOG_GROUP = os.getenv("EAGLE_TELEMETRY_LOG_GROUP", "/eagle/app")
```

**1b.** Update stream naming to use session_id when available:
```python
# In emit_telemetry_event(), replace:
stream_name = f"telemetry/{tenant_id}"
# With:
stream_name = f"session/{session_id}" if session_id else f"tenant/{tenant_id}"
```

**1c.** Add convenience wrappers after `emit_trace_completed()`:

```python
def emit_trace_started(
    tenant_id: str,
    user_id: str,
    session_id: str,
    prompt_preview: str = "",
):
    """Emit trace.started when a chat request begins."""
    emit_telemetry_event(
        event_type="trace.started",
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        data={"prompt_preview": prompt_preview[:200]},
    )


def emit_tool_completed(
    tenant_id: str,
    user_id: str,
    session_id: str,
    tool_name: str,
    duration_ms: int = 0,
    success: bool = True,
):
    """Emit tool.completed after a tool call finishes."""
    emit_telemetry_event(
        event_type="tool.completed",
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        data={"tool_name": tool_name, "duration_ms": duration_ms, "success": success},
    )


def emit_feedback_submitted(
    tenant_id: str,
    user_id: str,
    session_id: str,
    feedback_type: str,
    feedback_id: str,
):
    """Emit feedback.submitted after feedback is written to DynamoDB."""
    emit_telemetry_event(
        event_type="feedback.submitted",
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        data={"feedback_type": feedback_type, "feedback_id": feedback_id},
    )
```

### 2. Create ReasoningStore

Create **`server/app/reasoning_store.py`**:

```python
"""Session-scoped reasoning log accumulator with DynamoDB persistence."""
from __future__ import annotations
import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger("eagle.reasoning")

_TABLE_NAME = None
_table = None

def _get_table():
    global _table, _TABLE_NAME
    if _table is None:
        import os
        _TABLE_NAME = os.getenv("DYNAMODB_TABLE", "eagle")
        _table = boto3.resource("dynamodb").Table(_TABLE_NAME)
    return _table


@dataclass
class ReasoningEntry:
    timestamp: str
    event_type: str       # "tool_call", "compliance_check", "recommendation"
    tool_name: str
    reasoning: str        # Why this action was taken
    determination: str    # What was decided
    data: dict
    confidence: str       # "high", "medium", "low"


class ReasoningLog:
    def __init__(self, session_id: str, tenant_id: str, user_id: str):
        self.session_id = session_id
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.entries: list[ReasoningEntry] = []

    def add(
        self,
        event_type: str,
        tool_name: str,
        reasoning: str,
        determination: str,
        data: Optional[dict] = None,
        confidence: str = "high",
    ):
        self.entries.append(ReasoningEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            event_type=event_type,
            tool_name=tool_name,
            reasoning=reasoning,
            determination=determination,
            data=data or {},
            confidence=confidence,
        ))

    def to_json(self) -> list[dict]:
        return [asdict(e) for e in self.entries]

    def to_appendix_markdown(self) -> str:
        if not self.entries:
            return ""
        lines = [
            "\n\n---\n",
            "## Appendix: AI Decision Rationale\n",
            "*This appendix documents the AI-assisted analysis and reasoning "
            "that informed this document. All determinations were made based on "
            "applicable FAR/HHSAR regulations and NCI acquisition policies.*\n",
        ]
        for i, e in enumerate(self.entries, 1):
            ts = e.timestamp[11:19] if len(e.timestamp) > 19 else e.timestamp
            lines.append(f"### {i}. {e.event_type} — {e.tool_name}")
            lines.append(f"**Time:** {ts}  ")
            lines.append(f"**Action:** {e.reasoning}  ")
            lines.append(f"**Determination:** {e.determination}  ")
            if e.confidence:
                lines.append(f"**Confidence:** {e.confidence}  ")
            lines.append("")
        return "\n".join(lines)

    def save(self):
        """Persist to DynamoDB as REASONING#{session_id}."""
        if not self.entries:
            return
        table = _get_table()
        table.put_item(Item={
            "PK": f"SESSION#{self.session_id}",
            "SK": f"REASONING#{self.session_id}",
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "reasoning_entries": json.dumps(self.to_json(), default=str),
            "entry_count": len(self.entries),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

    @classmethod
    def load(cls, session_id: str, tenant_id: str, user_id: str) -> "ReasoningLog":
        """Load from DynamoDB. Returns empty log if not found."""
        log = cls(session_id, tenant_id, user_id)
        try:
            table = _get_table()
            resp = table.get_item(Key={
                "PK": f"SESSION#{session_id}",
                "SK": f"REASONING#{session_id}",
            })
            item = resp.get("Item")
            if item and item.get("reasoning_entries"):
                entries = json.loads(item["reasoning_entries"])
                for e in entries:
                    log.entries.append(ReasoningEntry(**e))
        except Exception:
            logger.debug("Failed to load reasoning log for session=%s", session_id)
        return log
```

### 3. Wire stream_generator() — The Core Merge

In **`server/app/streaming_routes.py`**, modify `stream_generator()`:

**3a.** Add imports at top of file:
```python
import time as _time
from .telemetry.cloudwatch_emitter import (
    emit_trace_started,
    emit_trace_completed,
    emit_tool_completed,
    emit_telemetry_event,
)
from .reasoning_store import ReasoningLog
```

**3b.** At the START of `stream_generator()`, after the `sse_queue` line (before persisting user message):
```python
# --- Telemetry + Reasoning init ---
_trace_start = _time.time()
reasoning_log = ReasoningLog(session_id or "", tenant_id, user_id)

# Fire-and-forget: emit trace.started to CloudWatch
try:
    await asyncio.to_thread(
        emit_trace_started, tenant_id, user_id, session_id or "", message[:200]
    )
except Exception:
    logger.debug("trace.started emission failed (non-fatal)")
```

**3c.** Replace the `tool_result` branch (currently lines 155-161):
```python
elif chunk_type == "tool_result":
    tr_name = chunk.get("name", "")
    if not tr_name:
        logger.debug("Skipping empty-name tool_result: keys=%s", list(chunk.keys()))
        continue
    result_data = chunk.get("result", {})

    # Standard tool_result emission (existing)
    await writer.write_tool_result(sse_queue, tr_name, result_data)
    yield await sse_queue.get()

    # CloudWatch: emit tool.completed
    try:
        await asyncio.to_thread(
            emit_tool_completed, tenant_id, user_id, session_id or "", tr_name
        )
    except Exception:
        pass

    # Reasoning: extract, accumulate, and emit REASONING SSE
    if isinstance(result_data, dict) and "reasoning" in result_data:
        reasoning_data = result_data["reasoning"]
        reasoning_log.add(
            event_type="tool_call",
            tool_name=tr_name,
            reasoning=reasoning_data.get("basis", ""),
            determination=reasoning_data.get("determination", ""),
            data=reasoning_data,
            confidence=reasoning_data.get("confidence", "high"),
        )
        await writer.write_reasoning(sse_queue, json.dumps(reasoning_data))
        yield await sse_queue.get()
```

**3d.** In the `complete` branch, after persisting assistant message and before `write_complete`:
```python
# CloudWatch: emit trace.completed
try:
    _elapsed = int((_time.time() - _trace_start) * 1000)
    await asyncio.to_thread(
        emit_trace_completed,
        {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "session_id": session_id or "",
            "trace_id": f"t-{int(_trace_start * 1000)}",
            "duration_ms": _elapsed,
            "total_input_tokens": chunk.get("usage", {}).get("inputTokens", 0),
            "total_output_tokens": chunk.get("usage", {}).get("outputTokens", 0),
            "tools_called": chunk.get("tools_called", []),
        },
    )
except Exception:
    logger.debug("trace.completed emission failed (non-fatal)")

# Reasoning: persist accumulated log
if reasoning_log.entries:
    try:
        await asyncio.to_thread(reasoning_log.save)
    except Exception:
        logger.debug("reasoning_log save failed (non-fatal)")
```

**3e.** In the `error` branch, after `write_error`:
```python
# CloudWatch: emit error.occurred
try:
    await asyncio.to_thread(
        emit_telemetry_event, "error.occurred", tenant_id,
        {"error": str(chunk.get("error", ""))[:500], "session_id": session_id},
        session_id, user_id,
    )
except Exception:
    pass
```

### 4. Add Reasoning Fields to Tool Handlers

**4a.** In **`server/app/agentic_service.py`**, in `_exec_query_compliance_matrix()`:
After computing the result dict, add:
```python
# Build reasoning chain
reasoning_chain = []
if result.get("method"):
    reasoning_chain.append(f"Value → {result['method']} acquisition")
if result.get("contract_type"):
    reasoning_chain.append(f"Contract type: {result['contract_type']}")
result["reasoning"] = {
    "action": "compliance_determination",
    "basis": "; ".join(reasoning_chain) if reasoning_chain else "Compliance query",
    "determination": f"{result.get('method', 'TBD')} via {result.get('contract_type', 'TBD')}",
    "documents_required": result.get("documents_required", []),
    "confidence": "high",
}
```

**4b.** In `_exec_search_far()`:
After getting results, add:
```python
result["reasoning"] = {
    "action": "regulatory_lookup",
    "basis": f"FAR search for '{query}'",
    "determination": f"Found {len(results)} relevant sections",
    "confidence": "high",
}
```

**4c.** In `_exec_create_document()`:
After generating the document content, add:
```python
result["reasoning"] = {
    "action": "document_generation",
    "basis": f"Generated {doc_type} based on intake context",
    "determination": f"{doc_type} created",
    "confidence": "high",
}
```

Also, before returning, load the reasoning log and append as appendix:
```python
# Append AI reasoning appendix to document content
try:
    from .reasoning_store import ReasoningLog
    rlog = ReasoningLog.load(session_id or "", tenant_id, "")
    if rlog and rlog.entries:
        appendix_md = rlog.to_appendix_markdown()
        if appendix_md and "content" in result:
            result["content"] += appendix_md
except Exception:
    pass  # Non-fatal
```

**4d.** In **`server/app/tools/contract_matrix.py`**, in the `query_contract_matrix` function:
After building the result dict, add:
```python
result["reasoning"] = {
    "action": "vehicle_recommendation",
    "basis": f"Dollar value analysis with {len(result.get('ranked', []))} vehicles scored",
    "determination": f"Top recommendation: {result['ranked'][0]['label'] if result.get('ranked') else 'N/A'}",
    "confidence": "high",
}
```

### 5. Wire Feedback Emission

In **`server/app/main.py`**, in `api_submit_feedback()`:

Add import:
```python
from .telemetry.cloudwatch_emitter import emit_feedback_submitted
```

After the `write_feedback()` call succeeds:
```python
# CloudWatch: emit feedback.submitted (fire-and-forget)
try:
    emit_feedback_submitted(
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        session_id=session_id or "",
        feedback_type=item.get("feedback_type", "general"),
        feedback_id=item.get("feedback_id", ""),
    )
except Exception:
    logger.debug("feedback.submitted emission failed (non-fatal)")
```

### 6. Wire Frontend — REASONING SSE Events

**6a.** In **`client/hooks/use-agent-stream.ts`**, in `processEventData()`, add after the `bedrock_trace` handler:

```typescript
// Handle reasoning events — AI decision rationale from tool results
if (event.type === 'reasoning') {
  const reasoningContent = event.reasoning || event.content || '';
  const reasoningLog: AuditLogEntry = {
    ...event,
    id: `reasoning-${eventCountRef.current++}`,
    type: 'reasoning',
    content: reasoningContent,
  };
  setLogs(prev => [...prev, reasoningLog]);
}
```

**6b.** In **`client/components/chat-simple/agent-logs.tsx`**, add rendering for `reasoning` type entries:
- Use a distinct visual: light purple/indigo background, brain or lightbulb icon
- Show the parsed reasoning JSON fields (action, basis, determination, confidence)
- Keep it collapsed by default, expandable on click

**6c.** In **`client/types/stream.ts`**, ensure `reasoning` is in the `AuditLogEntry.type` union if not already.

### 7. Supervisor Prompt — Phase Gating (Additive)

In **`eagle-plugin/agents/supervisor/agent.md`**, add a new section after the existing "CONSULTATION-FIRST FLOW" content (which was already partially added by c418a43). This is **additive** — don't replace anything:

```markdown
---

PHASE GATING

Phase 1 — UNDERSTAND (consultation)
- Ask 2-3 short questions per turn. Never more.
- Give a recommendation with each question: "I'd suggest X — does that work?"
- Call query_compliance_matrix after each substantive answer.
- Do NOT generate documents during this phase.

Phase 2 — CONFIRM (summary)
- When you have enough context, present a 5-line summary:
  "Here's what I have:
  - Requirement: [X]
  - Value: [$Y] → [FAR Part]
  - Timeline: [Z]
  - Documents needed: [list]
  Ready to generate?"
- Wait for user confirmation.

Phase 3 — GENERATE (documents)
- Only after user confirms.
- One document at a time. Brief preview.
- "Good? Next document?" before continuing.

SKIP TO PHASE 2 if user provides complete intake form JSON or uploads documents.
SKIP TO PHASE 3 if user says "generate", "create", "draft", or "make the [doc]."
```

### 8. Write Tests

Create **`server/tests/test_telemetry_reasoning.py`**:

```python
"""Unified tests for CloudWatch telemetry emission and reasoning capture."""
import json
from unittest.mock import patch, MagicMock
import pytest

# ── CloudWatch Emitter Tests ─────────────────────────────────────

class TestCloudWatchEmitter:

    @patch("app.telemetry.cloudwatch_emitter._get_client")
    def test_emits_to_eagle_app_log_group(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        from app.telemetry.cloudwatch_emitter import emit_telemetry_event
        emit_telemetry_event("trace.started", "t1", {"msg": "hi"}, "s1", "u1")
        call_args = mock_client.put_log_events.call_args
        assert call_args.kwargs["logGroupName"] == "/eagle/app"

    @patch("app.telemetry.cloudwatch_emitter._get_client")
    def test_stream_name_uses_session_id(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        from app.telemetry.cloudwatch_emitter import emit_telemetry_event
        emit_telemetry_event("test", "t1", {}, session_id="sess-abc", user_id="u1")
        call_args = mock_client.create_log_stream.call_args
        stream = call_args.kwargs.get("logStreamName", call_args[1].get("logStreamName", ""))
        assert "sess-abc" in stream

    @patch("app.telemetry.cloudwatch_emitter._get_client")
    def test_stream_name_falls_back_to_tenant(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        from app.telemetry.cloudwatch_emitter import emit_telemetry_event
        emit_telemetry_event("test", "t1", {}, session_id=None, user_id="u1")
        call_args = mock_client.put_log_events.call_args
        stream = call_args.kwargs.get("logStreamName", "")
        assert "t1" in stream

    @patch("app.telemetry.cloudwatch_emitter._get_client")
    def test_handles_already_exists(self, mock_get_client):
        from botocore.exceptions import ClientError
        mock_client = MagicMock()
        mock_client.create_log_group.side_effect = ClientError(
            {"Error": {"Code": "ResourceAlreadyExistsException"}}, "CreateLogGroup"
        )
        mock_client.create_log_stream.side_effect = ClientError(
            {"Error": {"Code": "ResourceAlreadyExistsException"}}, "CreateLogStream"
        )
        mock_get_client.return_value = mock_client
        from app.telemetry.cloudwatch_emitter import emit_telemetry_event
        emit_telemetry_event("test", "t1", {}, "s1", "u1")
        mock_client.put_log_events.assert_called_once()

    @patch("app.telemetry.cloudwatch_emitter._get_client")
    def test_swallows_put_failure(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.put_log_events.side_effect = Exception("CloudWatch down")
        mock_get_client.return_value = mock_client
        from app.telemetry.cloudwatch_emitter import emit_telemetry_event
        emit_telemetry_event("test", "t1", {}, "s1", "u1")  # Should not raise

    @patch("app.telemetry.cloudwatch_emitter.emit_telemetry_event")
    def test_emit_trace_started(self, mock_emit):
        from app.telemetry.cloudwatch_emitter import emit_trace_started
        emit_trace_started("t1", "u1", "s1", "hello world")
        mock_emit.assert_called_once()

    @patch("app.telemetry.cloudwatch_emitter.emit_telemetry_event")
    def test_emit_tool_completed(self, mock_emit):
        from app.telemetry.cloudwatch_emitter import emit_tool_completed
        emit_tool_completed("t1", "u1", "s1", "search_far", 120, True)
        mock_emit.assert_called_once()

    @patch("app.telemetry.cloudwatch_emitter.emit_telemetry_event")
    def test_emit_feedback_submitted(self, mock_emit):
        from app.telemetry.cloudwatch_emitter import emit_feedback_submitted
        emit_feedback_submitted("t1", "u1", "s1", "bug", "fb-001")
        mock_emit.assert_called_once()


# ── Reasoning Log Tests ──────────────────────────────────────────

class TestReasoningLog:

    def test_add_entry(self):
        from app.reasoning_store import ReasoningLog
        log = ReasoningLog("sess-1", "tenant-1", "user-1")
        log.add("compliance_check", "query_compliance_matrix",
                "Value $85K triggers simplified", "FAR 13.5")
        assert len(log.entries) == 1
        assert log.entries[0].tool_name == "query_compliance_matrix"

    def test_to_json_includes_timestamp(self):
        from app.reasoning_store import ReasoningLog
        log = ReasoningLog("sess-1", "tenant-1", "user-1")
        log.add("tool_call", "search_far", "Looking up FAR 13.5", "Found 3 sections")
        result = log.to_json()
        assert len(result) == 1
        assert "timestamp" in result[0]
        assert result[0]["tool_name"] == "search_far"

    def test_to_appendix_markdown(self):
        from app.reasoning_store import ReasoningLog
        log = ReasoningLog("sess-1", "tenant-1", "user-1")
        log.add("compliance_check", "query_compliance_matrix",
                "$85K → simplified", "FAR 13.5", confidence="high")
        log.add("document_generation", "create_document",
                "Generating SOW from intake", "SOW v1 created")
        md = log.to_appendix_markdown()
        assert "AI Decision Rationale" in md
        assert "FAR 13.5" in md
        assert "SOW v1 created" in md

    def test_empty_log_no_appendix(self):
        from app.reasoning_store import ReasoningLog
        log = ReasoningLog("sess-1", "tenant-1", "user-1")
        assert log.to_appendix_markdown() == ""

    @patch("app.reasoning_store._get_table")
    def test_save_to_dynamodb(self, mock_table_fn):
        from app.reasoning_store import ReasoningLog
        mock_tbl = MagicMock()
        mock_table_fn.return_value = mock_tbl
        log = ReasoningLog("sess-1", "tenant-1", "user-1")
        log.add("tool_call", "search_far", "test", "test result")
        log.save()
        mock_tbl.put_item.assert_called_once()
        item = mock_tbl.put_item.call_args.kwargs["Item"]
        assert item["PK"] == "SESSION#sess-1"
        assert item["SK"] == "REASONING#sess-1"

    @patch("app.reasoning_store._get_table")
    def test_load_from_dynamodb(self, mock_table_fn):
        from app.reasoning_store import ReasoningLog
        mock_tbl = MagicMock()
        mock_tbl.get_item.return_value = {
            "Item": {
                "PK": "SESSION#sess-1",
                "SK": "REASONING#sess-1",
                "reasoning_entries": json.dumps([{
                    "timestamp": "2026-03-10T18:00:00Z",
                    "event_type": "tool_call",
                    "tool_name": "search_far",
                    "reasoning": "test",
                    "determination": "found",
                    "data": {},
                    "confidence": "high",
                }]),
            }
        }
        mock_table_fn.return_value = mock_tbl
        log = ReasoningLog.load("sess-1", "tenant-1", "user-1")
        assert len(log.entries) == 1

    @patch("app.reasoning_store._get_table")
    def test_load_missing_returns_empty(self, mock_table_fn):
        from app.reasoning_store import ReasoningLog
        mock_tbl = MagicMock()
        mock_tbl.get_item.return_value = {}
        mock_table_fn.return_value = mock_tbl
        log = ReasoningLog.load("no-exist", "t1", "u1")
        assert len(log.entries) == 0

    @patch("app.reasoning_store._get_table")
    def test_save_empty_log_is_noop(self, mock_table_fn):
        from app.reasoning_store import ReasoningLog
        mock_tbl = MagicMock()
        mock_table_fn.return_value = mock_tbl
        log = ReasoningLog("sess-1", "t1", "u1")
        log.save()
        mock_tbl.put_item.assert_not_called()


# ── Document Appendix Tests ──────────────────────────────────────

class TestDocumentAppendix:

    def test_appendix_renders_entries(self):
        from app.reasoning_store import ReasoningLog
        log = ReasoningLog("s1", "t1", "u1")
        log.add("compliance_check", "query_compliance_matrix",
                "$85K triggers simplified", "FAR 13.5", confidence="high")
        md = log.to_appendix_markdown()
        assert "Appendix: AI Decision Rationale" in md
        assert "compliance_check" in md
        assert "$85K triggers simplified" in md

    def test_appendix_empty_when_no_entries(self):
        from app.reasoning_store import ReasoningLog
        log = ReasoningLog("s1", "t1", "u1")
        assert log.to_appendix_markdown() == ""
```

### 9. Validate

Run validation in order:

```bash
# L1 — Python syntax check
cd server && python -c "from app.telemetry.cloudwatch_emitter import emit_trace_started, emit_trace_completed, emit_tool_completed, emit_feedback_submitted; print('Emitter OK')"
cd server && python -c "from app.reasoning_store import ReasoningLog, ReasoningEntry; print('ReasoningStore OK')"

# L1 — Lint
cd server && ruff check app/

# L1 — TypeScript
cd client && npx tsc --noEmit

# L2 — Unified tests
cd server && python -m pytest tests/test_telemetry_reasoning.py -v

# L2 — Existing tests unbroken
cd server && python -m pytest tests/test_new_endpoints.py tests/test_feedback_store.py -v

# L3 — Manual smoke test
# 1. Start backend + frontend
# 2. Send a chat message, open CloudWatch tab → verify events appear
# 3. Start intake consultation → verify agent logs show reasoning entries
# 4. Generate a document → verify appendix section
# 5. Submit feedback (Ctrl+J) → verify feedback.submitted in CloudWatch

# L3 — AWS CLI verification
MSYS_NO_PATHCONV=1 aws logs filter-log-events \
  --log-group-name "/eagle/app" \
  --filter-pattern '{ $.event_type = "trace.started" }' \
  --limit 5 --profile eagle --region us-east-1
```

## Acceptance Criteria

### CloudWatch Telemetry
- [ ] `emit_telemetry_event()` writes to `/eagle/app` by default
- [ ] `trace.started` emitted at beginning of every chat request
- [ ] `trace.completed` emitted at end with tokens, cost, duration, tools
- [ ] `tool.completed` emitted for each tool call
- [ ] `feedback.submitted` emitted when feedback is written to DynamoDB
- [ ] `error.occurred` emitted on stream errors
- [ ] Stream names use `session/{session_id}` when available
- [ ] Frontend CloudWatch tab shows events for the current session

### Reasoning Capture
- [ ] Tool handlers return `reasoning` field (compliance matrix, search_far, create_document, contract_matrix)
- [ ] `ReasoningLog` accumulates entries per session
- [ ] `ReasoningLog.save()` persists to DynamoDB as `REASONING#{session_id}`
- [ ] `ReasoningLog.to_appendix_markdown()` produces formatted appendix
- [ ] Generated documents include "Appendix: AI Decision Rationale" when reasoning exists
- [ ] `StreamEventType.REASONING` events are emitted via SSE
- [ ] Frontend agent logs display reasoning entries

### Cross-cutting
- [ ] All emissions are fire-and-forget — failures never break the main flow
- [ ] Events include `user_id`, `session_id`, `tenant_id` for filtering
- [ ] All unit tests pass
- [ ] `ruff check app/` passes
- [ ] `npx tsc --noEmit` passes
- [ ] Existing tests still pass

## Validation Commands

```bash
# L1 — Lint
cd server && ruff check app/

# L1 — Imports
cd server && python -c "from app.telemetry.cloudwatch_emitter import emit_trace_started, emit_tool_completed, emit_feedback_submitted; from app.reasoning_store import ReasoningLog; print('All imports OK')"

# L1 — TypeScript
cd client && npx tsc --noEmit

# L2 — Tests
cd server && python -m pytest tests/test_telemetry_reasoning.py -v

# L2 — Existing tests
cd server && python -m pytest tests/ -v --ignore=tests/test_eagle_sdk_eval.py

# L3 — CloudWatch verification
MSYS_NO_PATHCONV=1 aws logs filter-log-events --log-group-name "/eagle/app" --limit 5 --profile eagle --region us-east-1
```

## Notes

### What was cut from the original plans
- **`ChatTraceCollector` instantiation** — The CloudWatch plan mentioned it but the emitter wrappers handle everything directly. Skip the collector.
- **oa-intake SKILL.md changes** — Supervisor prompt already enforces short responses (c418a43). Changing both creates conflicting instructions. Defer.
- **Separate test files** — Merged into one `test_telemetry_reasoning.py` instead of two.
- **`emit_telemetry_event_async` wrapper** — Not needed; `asyncio.to_thread()` is called directly at each hook point.

### What was added vs original plans
- **Intake form fast-path reasoning** — `_fast_intake_form_response()` in `strands_agentic_service.py` bypasses the LLM entirely. The reasoning log handles this gracefully: no tool calls = no reasoning entries = no appendix. No special handling needed.
- **`query_contract_matrix` reasoning** — c418a43 added this as a Strands `@tool` (not via `TOOL_DISPATCH`). Reasoning field must be added in `contract_matrix.py` directly.
- **Phase gating** — Simplified to an additive section in supervisor prompt. c418a43 already did the heavy lifting on tone/style.

### Backward Compatibility
- Documents without reasoning log → no appendix (graceful degradation)
- Old sessions without reasoning entries → load returns empty log
- Frontend without reasoning handler → events are ignored (SSE parser skips unknown types)
- CloudWatch failures → swallowed, main flow unaffected

### Cost
- CloudWatch Logs: ~$0.50/GB ingestion. At ~500 bytes/event, 1000 requests/day → <$0.01/month
- DynamoDB reasoning entries: ~500 bytes each, 5-15 per session, 1000 sessions/month → ~7.5MB/month (negligible)

### Supersedes
This plan supersedes:
- `20260310-180000-plan-cloudwatch-telemetry-wiring-v1.md`
- `20260310-183000-plan-consultation-first-reasoning-capture-v1.md`
