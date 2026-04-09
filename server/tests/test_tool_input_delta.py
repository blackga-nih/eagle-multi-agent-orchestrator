"""Unit tests for tool_input_delta streaming feature.

Validates the full pipeline: stream_protocol event shape,
sdk_query_streaming capture of contentBlockDelta toolUse.input tokens,
streaming_routes SSE pass-through, and batching behavior.

Run: pytest server/tests/test_tool_input_delta.py -v
"""

import asyncio
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_server_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)

from app.stream_protocol import MultiAgentStreamWriter, StreamEvent, StreamEventType


# ── Helpers ──────────────────────────────────────────────────────────


async def _collect(gen) -> list[dict]:
    """Collect all chunks from an async generator."""
    chunks = []
    async for chunk in gen:
        chunks.append(chunk)
    return chunks


def _tool_use_event(name: str, tool_id: str) -> dict:
    return {"current_tool_use": {"toolUseId": tool_id, "name": name, "input": ""}}


def _tool_input_delta_event(input_text: str) -> dict:
    """Simulate a Bedrock contentBlockDelta with toolUse.input."""
    return {
        "event": {
            "contentBlockDelta": {
                "delta": {
                    "toolUse": {"input": input_text}
                }
            }
        }
    }


def _text_event(text: str) -> dict:
    return {"data": text}


def _agent_result_event() -> dict:
    result = MagicMock()
    result.metrics = MagicMock()
    result.metrics.accumulated_usage = {"inputTokens": 100, "outputTokens": 50}
    result.metrics.tool_metrics = {}
    result.__str__ = lambda self: "Done"
    return {"result": result}


def _base_patches():
    return [
        patch("app.strands_agentic_service.build_skill_tools", return_value=[]),
        patch("app.strands_agentic_service._build_service_tools", return_value=([], {})),
        patch("app.strands_agentic_service.build_supervisor_prompt", return_value="You are EAGLE."),
        patch("app.strands_agentic_service._to_strands_messages", return_value=None),
        patch("app.strands_agentic_service._ensure_create_document_for_direct_request", new_callable=AsyncMock, return_value=None),
    ]


async def _run_with_events(events: list[dict]) -> list[dict]:
    from app.strands_agentic_service import sdk_query_streaming

    async def fake_stream_async(prompt):
        for evt in events:
            yield evt

    mock_agent = MagicMock()
    mock_agent.stream_async = fake_stream_async

    patches = _base_patches() + [
        patch("app.strands_agentic_service.Agent", return_value=mock_agent),
    ]

    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
        return await _collect(sdk_query_streaming(
            prompt="test query",
            tenant_id="test-tenant",
            user_id="test-user",
            tier="advanced",
            session_id="sess-delta-001",
        ))


# ══════════════════════════════════════════════════════════════════════
# T1 — StreamEvent shape for TOOL_INPUT_DELTA
# ══════════════════════════════════════════════════════════════════════


class TestToolInputDeltaEventShape:

    def test_enum_value_exists(self):
        assert StreamEventType.TOOL_INPUT_DELTA.value == "tool_input_delta"

    def test_event_has_metadata_fields(self):
        evt = StreamEvent(
            type=StreamEventType.TOOL_INPUT_DELTA,
            agent_id="eagle",
            agent_name="EAGLE",
            metadata={
                "tool_use_id": "tu-123",
                "delta": '{"content": "# SOW',
                "tool_name": "create_document",
            },
        )
        d = evt.to_dict()
        assert d["type"] == "tool_input_delta"
        assert d["metadata"]["tool_use_id"] == "tu-123"
        assert d["metadata"]["delta"] == '{"content": "# SOW'
        assert d["metadata"]["tool_name"] == "create_document"
        assert "timestamp" in d

    def test_to_sse_format(self):
        evt = StreamEvent(
            type=StreamEventType.TOOL_INPUT_DELTA,
            agent_id="eagle",
            agent_name="EAGLE",
            metadata={"tool_use_id": "tu-1", "delta": "abc", "tool_name": "x"},
        )
        sse = evt.to_sse()
        assert sse.startswith("data: ")
        assert sse.endswith("\n\n")
        payload = json.loads(sse[6:].strip())
        assert payload["type"] == "tool_input_delta"
        assert payload["metadata"]["delta"] == "abc"


# ══════════════════════════════════════════════════════════════════════
# T2 — MultiAgentStreamWriter.write_tool_input_delta()
# ══════════════════════════════════════════════════════════════════════


class TestWriteToolInputDelta:

    @pytest.fixture
    def writer(self):
        return MultiAgentStreamWriter("eagle", "EAGLE Acquisition Assistant")

    @pytest.mark.asyncio
    async def test_write_tool_input_delta(self, writer):
        q = asyncio.Queue()
        await writer.write_tool_input_delta(q, "tu-1", "chunk of JSON", tool_name="create_document")
        sse = await q.get()
        payload = json.loads(sse[6:].strip())
        assert payload["type"] == "tool_input_delta"
        assert payload["metadata"]["tool_use_id"] == "tu-1"
        assert payload["metadata"]["delta"] == "chunk of JSON"
        assert payload["metadata"]["tool_name"] == "create_document"
        assert payload["agent_id"] == "eagle"

    @pytest.mark.asyncio
    async def test_write_tool_input_delta_no_name(self, writer):
        q = asyncio.Queue()
        await writer.write_tool_input_delta(q, "tu-2", "data")
        sse = await q.get()
        payload = json.loads(sse[6:].strip())
        assert payload["metadata"]["tool_name"] == ""


# ══════════════════════════════════════════════════════════════════════
# T3 — sdk_query_streaming captures tool input deltas
# ══════════════════════════════════════════════════════════════════════


class TestToolInputDeltaCapture:

    @pytest.mark.asyncio
    async def test_small_deltas_batched(self):
        """Deltas under 150 chars should be accumulated, not emitted individually."""
        chunks = await _run_with_events([
            _tool_use_event("create_document", "tu-1"),
            _tool_input_delta_event('{"doc_type":'),
            _tool_input_delta_event('"sow"}'),
            _text_event("done"),
        ])
        deltas = [c for c in chunks if c.get("type") == "tool_input_delta"]
        # Total input is < 150 chars → flushed once (at stream end or tool switch)
        assert len(deltas) <= 1
        if deltas:
            assert deltas[0]["tool_use_id"] == "tu-1"
            assert '{"doc_type":' in deltas[0]["delta"]

    @pytest.mark.asyncio
    async def test_large_delta_flushed_at_threshold(self):
        """Accumulated input exceeding 150 chars should trigger a flush."""
        long_content = "x" * 200
        chunks = await _run_with_events([
            _tool_use_event("create_document", "tu-1"),
            _tool_input_delta_event(long_content),
            _text_event("done"),
        ])
        deltas = [c for c in chunks if c.get("type") == "tool_input_delta"]
        assert len(deltas) >= 1
        combined = "".join(d["delta"] for d in deltas)
        assert combined == long_content

    @pytest.mark.asyncio
    async def test_delta_associated_with_correct_tool_id(self):
        """Deltas should carry the tool_use_id of the current tool."""
        chunks = await _run_with_events([
            _tool_use_event("create_document", "tu-abc"),
            _tool_input_delta_event("A" * 160),  # triggers flush
            _text_event("done"),
        ])
        deltas = [c for c in chunks if c.get("type") == "tool_input_delta"]
        for d in deltas:
            assert d["tool_use_id"] == "tu-abc"

    @pytest.mark.asyncio
    async def test_delta_has_tool_name(self):
        """Deltas should include the tool name."""
        chunks = await _run_with_events([
            _tool_use_event("create_document", "tu-1"),
            _tool_input_delta_event("Z" * 200),
            _text_event("done"),
        ])
        deltas = [c for c in chunks if c.get("type") == "tool_input_delta"]
        assert len(deltas) >= 1
        assert deltas[0]["name"] == "create_document"

    @pytest.mark.asyncio
    async def test_buffer_flushed_on_tool_switch(self):
        """When a new tool starts, remaining buffer from previous tool is flushed."""
        chunks = await _run_with_events([
            _tool_use_event("create_document", "tu-1"),
            _tool_input_delta_event("partial input"),
            _tool_use_event("search_far", "tu-2"),
            _text_event("done"),
        ])
        deltas = [c for c in chunks if c.get("type") == "tool_input_delta"]
        # The "partial input" buffer should be flushed before tool switch
        assert any("partial input" in d["delta"] for d in deltas)

    @pytest.mark.asyncio
    async def test_no_deltas_without_tool(self):
        """Tool input deltas without a prior tool_use should be dropped."""
        chunks = await _run_with_events([
            _tool_input_delta_event("orphan data"),
            _text_event("done"),
        ])
        deltas = [c for c in chunks if c.get("type") == "tool_input_delta"]
        assert len(deltas) == 0

    @pytest.mark.asyncio
    async def test_multiple_flush_cycles(self):
        """Multiple batches should be produced for very long input."""
        chunks = await _run_with_events([
            _tool_use_event("create_document", "tu-1"),
            _tool_input_delta_event("A" * 160),  # flush 1
            _tool_input_delta_event("B" * 160),  # flush 2
            _text_event("done"),
        ])
        deltas = [c for c in chunks if c.get("type") == "tool_input_delta"]
        combined = "".join(d["delta"] for d in deltas)
        assert "A" * 160 in combined
        assert "B" * 160 in combined


# ══════════════════════════════════════════════════════════════════════
# T4 — streaming_routes passes tool_input_delta through SSE
# ══════════════════════════════════════════════════════════════════════


def _parse_sse_events(raw_lines: list[str]) -> list[dict]:
    events = []
    for line in raw_lines:
        line = line.strip()
        if line.startswith("data: "):
            try:
                events.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass
    return events


async def _collect_stream(gen) -> list[str]:
    lines = []
    async for line in gen:
        lines.append(line)
    return lines


class TestStreamingRoutesToolInputDelta:

    @pytest.mark.asyncio
    async def test_tool_input_delta_passed_through(self):
        """tool_input_delta chunks should appear as SSE events."""
        from app.streaming_routes import stream_generator

        async def fake_sdk(**kwargs):
            yield {"type": "tool_use", "name": "create_document", "input": {}, "tool_use_id": "tu-1"}
            yield {"type": "tool_input_delta", "tool_use_id": "tu-1", "delta": "some json", "name": "create_document"}
            yield {"type": "complete", "text": "", "tools_called": ["create_document"], "usage": {}}

        with patch("app.streaming_routes.sdk_query_streaming", fake_sdk), \
             patch("app.streaming_routes.add_message"):
            lines = await _collect_stream(stream_generator(
                message="create a sow",
                tenant_id="t",
                user_id="u",
                tier="advanced",
                subscription_service=None,
                session_id="s",
            ))

        events = _parse_sse_events(lines)
        delta_events = [e for e in events if e.get("type") == "tool_input_delta"]
        assert len(delta_events) == 1
        assert delta_events[0]["metadata"]["delta"] == "some json"
        assert delta_events[0]["metadata"]["tool_use_id"] == "tu-1"
        assert delta_events[0]["metadata"]["tool_name"] == "create_document"

    @pytest.mark.asyncio
    async def test_empty_delta_filtered(self):
        """Empty delta strings should not produce SSE events."""
        from app.streaming_routes import stream_generator

        async def fake_sdk(**kwargs):
            yield {"type": "tool_input_delta", "tool_use_id": "tu-1", "delta": "", "name": "x"}
            yield {"type": "complete", "text": "", "tools_called": [], "usage": {}}

        with patch("app.streaming_routes.sdk_query_streaming", fake_sdk), \
             patch("app.streaming_routes.add_message"):
            lines = await _collect_stream(stream_generator(
                message="test",
                tenant_id="t",
                user_id="u",
                tier="advanced",
                subscription_service=None,
                session_id="s",
            ))

        events = _parse_sse_events(lines)
        delta_events = [e for e in events if e.get("type") == "tool_input_delta"]
        assert len(delta_events) == 0
