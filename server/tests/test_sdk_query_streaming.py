"""Unit tests for sdk_query_streaming() event flow.

Mocks Agent.stream_async() to yield controlled event sequences, then
validates the chunk dicts that sdk_query_streaming() produces.

Run: pytest server/tests/test_sdk_query_streaming.py -v
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


# ── Helpers ──────────────────────────────────────────────────────────


async def _collect(gen) -> list[dict]:
    """Collect all chunks from an async generator."""
    chunks = []
    async for chunk in gen:
        chunks.append(chunk)
    return chunks


def _text_event(text: str) -> dict:
    """Simulate a TextStreamEvent from Strands."""
    return {"data": text}


def _tool_use_event(name: str, tool_id: str, tool_input: str = "") -> dict:
    """Simulate a ToolUseStreamEvent from Strands."""
    return {"current_tool_use": {"toolUseId": tool_id, "name": name, "input": tool_input}}


def _content_block_start_event(name: str, tool_id: str) -> dict:
    """Simulate a Bedrock contentBlockStart event (fallback path)."""
    return {
        "event": {
            "contentBlockStart": {
                "start": {
                    "toolUse": {"toolUseId": tool_id, "name": name}
                }
            }
        }
    }


def _agent_result_event(text: str = "Done") -> dict:
    """Simulate an AgentResultEvent."""
    result = MagicMock()
    result.metrics = MagicMock()
    result.metrics.accumulated_usage = {"inputTokens": 100, "outputTokens": 50}
    result.metrics.tool_metrics = {}
    result.__str__ = lambda self: text
    return {"result": result}


# ── Patches ──────────────────────────────────────────────────────────


def _base_patches():
    """Common patches to isolate sdk_query_streaming from real AWS/Agent deps."""
    return [
        patch("app.strands_agentic_service.build_skill_tools", return_value=[]),
        patch("app.strands_agentic_service._build_service_tools", return_value=[]),
        patch("app.strands_agentic_service.build_supervisor_prompt", return_value="You are EAGLE."),
        patch("app.strands_agentic_service._to_strands_messages", return_value=None),
        patch("app.strands_agentic_service._maybe_fast_path_document_generation", new_callable=AsyncMock, return_value=None),
        patch("app.strands_agentic_service._ensure_create_document_for_direct_request", new_callable=AsyncMock, return_value=None),
    ]


async def _run_with_events(events: list[dict]) -> list[dict]:
    """Run sdk_query_streaming with a mocked Agent that yields given events."""
    from app.strands_agentic_service import sdk_query_streaming

    async def fake_stream_async(prompt):
        for evt in events:
            yield evt

    mock_agent = MagicMock()
    mock_agent.stream_async = fake_stream_async

    patches = _base_patches() + [
        patch("app.strands_agentic_service.Agent", return_value=mock_agent),
    ]

    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
        return await _collect(sdk_query_streaming(
            prompt="test query",
            tenant_id="test-tenant",
            user_id="test-user",
            tier="advanced",
            session_id="sess-001",
        ))


# ── Tests ────────────────────────────────────────────────────────────


class TestTextEvents:

    @pytest.mark.asyncio
    async def test_text_events_passthrough(self):
        chunks = await _run_with_events([
            _text_event("Hello "),
            _text_event("world"),
        ])
        text_chunks = [c for c in chunks if c.get("type") == "text"]
        assert len(text_chunks) == 2
        assert text_chunks[0]["data"] == "Hello "
        assert text_chunks[1]["data"] == "world"

    @pytest.mark.asyncio
    async def test_complete_event_has_full_text(self):
        chunks = await _run_with_events([
            _text_event("Hello "),
            _text_event("world"),
        ])
        complete = [c for c in chunks if c.get("type") == "complete"]
        assert len(complete) == 1
        assert "Hello world" in complete[0]["text"]


class TestToolUseEvents:

    @pytest.mark.asyncio
    async def test_tool_use_from_current_tool_use(self):
        chunks = await _run_with_events([
            _tool_use_event("search_far", "tu-1", '{"query": "FAR 13"}'),
            _text_event("Found FAR Part 13."),
        ])
        tool_uses = [c for c in chunks if c.get("type") == "tool_use"]
        assert len(tool_uses) == 1
        assert tool_uses[0]["name"] == "search_far"
        assert tool_uses[0]["tool_use_id"] == "tu-1"

    @pytest.mark.asyncio
    async def test_tool_use_dedup_by_id(self):
        """Same toolUseId yielded twice should only produce one tool_use chunk."""
        chunks = await _run_with_events([
            _tool_use_event("search_far", "tu-1"),
            _tool_use_event("search_far", "tu-1"),  # duplicate
            _text_event("done"),
        ])
        tool_uses = [c for c in chunks if c.get("type") == "tool_use"]
        assert len(tool_uses) == 1

    @pytest.mark.asyncio
    async def test_tool_use_from_content_block_start(self):
        """Bedrock contentBlockStart fallback path."""
        chunks = await _run_with_events([
            _content_block_start_event("knowledge_search", "tu-2"),
            _text_event("Found results."),
        ])
        tool_uses = [c for c in chunks if c.get("type") == "tool_use"]
        assert len(tool_uses) == 1
        assert tool_uses[0]["name"] == "knowledge_search"
        assert tool_uses[0]["tool_use_id"] == "tu-2"

    @pytest.mark.asyncio
    async def test_multiple_tools_tracked_in_complete(self):
        chunks = await _run_with_events([
            _tool_use_event("search_far", "tu-1"),
            _tool_use_event("knowledge_search", "tu-2"),
            _text_event("done"),
        ])
        complete = [c for c in chunks if c.get("type") == "complete"]
        assert len(complete) == 1
        assert "search_far" in complete[0]["tools_called"]
        assert "knowledge_search" in complete[0]["tools_called"]


class TestResultQueue:

    @pytest.mark.asyncio
    async def test_result_queue_drain_yields_tool_result(self):
        """Factory tools push to result_queue; sdk_query_streaming drains them."""
        from app.strands_agentic_service import sdk_query_streaming

        result_item = {"type": "tool_result", "name": "load_data", "result": {"rows": 5}}

        async def fake_stream_async(prompt):
            yield _text_event("loading...")
            # Simulate factory tool pushing to result_queue between events
            yield _text_event("done")

        mock_agent = MagicMock()
        mock_agent.stream_async = fake_stream_async

        patches = _base_patches() + [
            patch("app.strands_agentic_service.Agent", return_value=mock_agent),
        ]

        # We need to inject into the result_queue after it's created.
        # Patch asyncio.Queue to capture the instance.
        real_queue_cls = asyncio.Queue
        captured_queue = None

        class CapturingQueue(real_queue_cls):
            def __init__(self, *args, **kwargs):
                nonlocal captured_queue
                super().__init__(*args, **kwargs)
                captured_queue = self

        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
            with patch("app.strands_agentic_service.asyncio.Queue", CapturingQueue):
                chunks = []
                async for chunk in sdk_query_streaming(
                    prompt="test",
                    tenant_id="t",
                    user_id="u",
                    tier="advanced",
                    session_id="s",
                ):
                    # After first text event, push a result onto the queue
                    if chunk.get("type") == "text" and chunk.get("data") == "loading..." and captured_queue:
                        await captured_queue.put(result_item)
                    chunks.append(chunk)

        tool_results = [c for c in chunks if c.get("type") == "tool_result"]
        assert len(tool_results) >= 1
        assert tool_results[0]["name"] == "load_data"


class TestErrorPaths:

    @pytest.mark.asyncio
    async def test_stream_async_exception_yields_error(self):
        from app.strands_agentic_service import sdk_query_streaming

        async def failing_stream_async(prompt):
            yield _text_event("starting...")
            raise RuntimeError("Bedrock timeout")

        mock_agent = MagicMock()
        mock_agent.stream_async = failing_stream_async

        patches = _base_patches() + [
            patch("app.strands_agentic_service.Agent", return_value=mock_agent),
        ]

        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
            chunks = await _collect(sdk_query_streaming(
                prompt="test",
                tenant_id="t",
                user_id="u",
                tier="advanced",
                session_id="s",
            ))

        error_chunks = [c for c in chunks if c.get("type") == "error"]
        assert len(error_chunks) == 1
        assert "Bedrock timeout" in error_chunks[0]["error"]

    @pytest.mark.asyncio
    async def test_no_text_yields_fallback(self):
        """When model produces no text, complete event should have fallback."""
        chunks = await _run_with_events([
            _tool_use_event("search_far", "tu-1"),
        ])
        complete = [c for c in chunks if c.get("type") == "complete"]
        assert len(complete) == 1
        # Should have some fallback text, not empty
        assert len(complete[0]["text"]) > 0


class TestFastPath:

    @pytest.mark.asyncio
    async def test_fast_path_emits_tool_use_and_result(self):
        from app.strands_agentic_service import sdk_query_streaming

        fast_result = {
            "doc_type": "sow",
            "result": {
                "mode": "workspace",
                "document_type": "sow",
                "title": "Statement of Work",
                "status": "saved",
            },
        }

        patches = _base_patches()
        # Override the fast path mock to return a result
        patches[4] = patch(
            "app.strands_agentic_service._maybe_fast_path_document_generation",
            new_callable=AsyncMock,
            return_value=fast_result,
        )

        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            chunks = await _collect(sdk_query_streaming(
                prompt="Generate a SOW",
                tenant_id="t",
                user_id="u",
                tier="advanced",
                session_id="s",
            ))

        types = [c["type"] for c in chunks]
        assert "tool_use" in types
        assert "tool_result" in types
        assert "complete" in types
        tool_use = next(c for c in chunks if c["type"] == "tool_use")
        assert tool_use["name"] == "create_document"
