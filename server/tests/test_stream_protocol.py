"""Unit tests for StreamEvent schema contract (stream_protocol.py).

Validates the SSE event format that the frontend parser depends on.
Every field name and shape checked here must match what Playwright tests
and use-agent-stream.ts expect.

Run: pytest server/tests/test_stream_protocol.py -v
"""

import json
import os
import sys

import pytest

_server_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)

from app.stream_protocol import MultiAgentStreamWriter, StreamEvent, StreamEventType


# ── StreamEvent dataclass tests ──────────────────────────────────────


class TestStreamEventShape:
    """Verify the to_dict() output shape matches frontend expectations."""

    def test_text_event_has_required_fields(self):
        evt = StreamEvent(
            type=StreamEventType.TEXT,
            agent_id="eagle",
            agent_name="EAGLE",
            content="Hello",
        )
        d = evt.to_dict()
        assert d["type"] == "text"
        assert d["agent_id"] == "eagle"
        assert d["agent_name"] == "EAGLE"
        assert d["content"] == "Hello"
        assert "timestamp" in d

    def test_tool_use_event_shape(self):
        evt = StreamEvent(
            type=StreamEventType.TOOL_USE,
            agent_id="eagle",
            agent_name="EAGLE",
            tool_use={"name": "search_far", "input": {"query": "FAR 13"}, "tool_use_id": "tu-1"},
        )
        d = evt.to_dict()
        assert d["type"] == "tool_use"
        assert d["tool_use"]["name"] == "search_far"
        assert d["tool_use"]["input"] == {"query": "FAR 13"}
        assert d["tool_use"]["tool_use_id"] == "tu-1"

    def test_tool_result_event_shape(self):
        evt = StreamEvent(
            type=StreamEventType.TOOL_RESULT,
            agent_id="eagle",
            agent_name="EAGLE",
            tool_result={"name": "search_far", "result": {"text": "FAR Part 13..."}},
        )
        d = evt.to_dict()
        assert d["type"] == "tool_result"
        assert d["tool_result"]["name"] == "search_far"
        assert d["tool_result"]["result"] == {"text": "FAR Part 13..."}

    def test_complete_event_shape(self):
        evt = StreamEvent(
            type=StreamEventType.COMPLETE,
            agent_id="eagle",
            agent_name="EAGLE",
        )
        d = evt.to_dict()
        assert d["type"] == "complete"
        assert d["agent_id"] == "eagle"
        assert "timestamp" in d

    def test_error_event_shape(self):
        evt = StreamEvent(
            type=StreamEventType.ERROR,
            agent_id="eagle",
            agent_name="EAGLE",
            content="Bedrock timeout",
        )
        d = evt.to_dict()
        assert d["type"] == "error"
        assert d["content"] == "Bedrock timeout"

    def test_none_fields_omitted(self):
        evt = StreamEvent(
            type=StreamEventType.TEXT,
            agent_id="eagle",
            agent_name="EAGLE",
            content="hi",
        )
        d = evt.to_dict()
        assert "tool_use" not in d
        assert "tool_result" not in d
        assert "reasoning" not in d
        assert "metadata" not in d
        assert "elicitation" not in d

    def test_to_sse_format(self):
        evt = StreamEvent(
            type=StreamEventType.TEXT,
            agent_id="eagle",
            agent_name="EAGLE",
            content="chunk",
        )
        sse = evt.to_sse()
        assert sse.startswith("data: ")
        assert sse.endswith("\n\n")
        payload = json.loads(sse[6:].strip())
        assert payload["type"] == "text"
        assert payload["content"] == "chunk"

    def test_timestamp_auto_generated(self):
        evt = StreamEvent(
            type=StreamEventType.TEXT,
            agent_id="eagle",
            agent_name="EAGLE",
        )
        assert evt.timestamp is not None
        # ISO 8601 format
        assert "T" in evt.timestamp


# ── MultiAgentStreamWriter tests ─────────────────────────────────────


class TestMultiAgentStreamWriter:
    """Verify the writer produces correct SSE strings in the queue."""

    @pytest.fixture
    def writer(self):
        return MultiAgentStreamWriter("eagle", "EAGLE Acquisition Assistant")

    @pytest.mark.asyncio
    async def test_write_text(self, writer):
        import asyncio
        q = asyncio.Queue()
        await writer.write_text(q, "Hello world")
        sse = await q.get()
        payload = json.loads(sse[6:].strip())
        assert payload["type"] == "text"
        assert payload["content"] == "Hello world"
        assert payload["agent_id"] == "eagle"

    @pytest.mark.asyncio
    async def test_write_tool_use(self, writer):
        import asyncio
        q = asyncio.Queue()
        await writer.write_tool_use(q, "search_far", {"query": "FAR 13"}, tool_use_id="tu-1")
        sse = await q.get()
        payload = json.loads(sse[6:].strip())
        assert payload["type"] == "tool_use"
        assert payload["tool_use"]["name"] == "search_far"
        assert payload["tool_use"]["input"] == {"query": "FAR 13"}
        assert payload["tool_use"]["tool_use_id"] == "tu-1"

    @pytest.mark.asyncio
    async def test_write_tool_use_no_id(self, writer):
        import asyncio
        q = asyncio.Queue()
        await writer.write_tool_use(q, "load_data", {})
        sse = await q.get()
        payload = json.loads(sse[6:].strip())
        assert "tool_use_id" not in payload["tool_use"]

    @pytest.mark.asyncio
    async def test_write_tool_result(self, writer):
        import asyncio
        q = asyncio.Queue()
        await writer.write_tool_result(q, "search_far", {"text": "result"})
        sse = await q.get()
        payload = json.loads(sse[6:].strip())
        assert payload["type"] == "tool_result"
        assert payload["tool_result"]["name"] == "search_far"
        assert payload["tool_result"]["result"] == {"text": "result"}

    @pytest.mark.asyncio
    async def test_write_complete(self, writer):
        import asyncio
        q = asyncio.Queue()
        await writer.write_complete(q)
        sse = await q.get()
        payload = json.loads(sse[6:].strip())
        assert payload["type"] == "complete"

    @pytest.mark.asyncio
    async def test_write_error(self, writer):
        import asyncio
        q = asyncio.Queue()
        await writer.write_error(q, "something broke")
        sse = await q.get()
        payload = json.loads(sse[6:].strip())
        assert payload["type"] == "error"
        assert payload["content"] == "something broke"
