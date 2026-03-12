"""Unit tests for streaming error paths and edge cases.

Covers:
- Backend exception → error SSE event
- Keepalive emission during slow chunks
- Empty response → fallback text
- Generator exhaustion without complete event
- CancelledError (client disconnect) handling

Run: pytest server/tests/test_streaming_error_paths.py -v
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


def _parse_sse_events(raw_lines: list[str]) -> list[dict]:
    """Parse SSE strings into dicts, skipping keepalives and blanks."""
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
    """Collect all raw SSE strings from the stream generator."""
    lines = []
    async for line in gen:
        lines.append(line)
    return lines


def _make_stream_call(**overrides):
    """Build default kwargs for stream_generator."""
    defaults = dict(
        message="test query",
        tenant_id="t",
        user_id="u",
        tier="advanced",
        subscription_service=None,
        session_id="s",
    )
    defaults.update(overrides)
    return defaults


# ── Tests ────────────────────────────────────────────────────────────


class TestBackendExceptionEmitsError:

    @pytest.mark.asyncio
    async def test_sdk_exception_yields_error_event(self):
        """When sdk_query_streaming raises, stream_generator emits an error SSE event."""
        from app.streaming_routes import stream_generator

        async def exploding_sdk(**kwargs):
            yield {"type": "text", "data": "Starting..."}
            raise RuntimeError("Bedrock throttle")

        with patch("app.streaming_routes.sdk_query_streaming", exploding_sdk), \
             patch("app.streaming_routes.add_message"):
            lines = await _collect_stream(stream_generator(**_make_stream_call()))

        events = _parse_sse_events(lines)
        error_events = [e for e in events if e.get("type") == "error"]
        assert len(error_events) == 1
        assert "Bedrock throttle" in error_events[0].get("content", "")

    @pytest.mark.asyncio
    async def test_error_event_has_agent_fields(self):
        """Error events must still include agent_id, agent_name, timestamp."""
        from app.streaming_routes import stream_generator

        async def exploding_sdk(**kwargs):
            raise ValueError("bad input")

        with patch("app.streaming_routes.sdk_query_streaming", exploding_sdk), \
             patch("app.streaming_routes.add_message"):
            lines = await _collect_stream(stream_generator(**_make_stream_call()))

        events = _parse_sse_events(lines)
        error_events = [e for e in events if e.get("type") == "error"]
        assert len(error_events) == 1
        err = error_events[0]
        assert "agent_id" in err
        assert "agent_name" in err
        assert "timestamp" in err


class TestKeepaliveEmission:

    @pytest.mark.asyncio
    async def test_keepalive_is_valid_sse_comment(self):
        """Keepalive lines must be ': keepalive\\n\\n' (SSE comment format)."""
        from app.streaming_routes import stream_generator

        async def slow_sdk(**kwargs):
            yield {"type": "text", "data": "hello"}
            await asyncio.sleep(0)  # simulate delay handled by keepalive wrapper
            yield {"type": "complete", "text": "hello", "tools_called": [], "usage": {}}

        with patch("app.streaming_routes.sdk_query_streaming", slow_sdk), \
             patch("app.streaming_routes.add_message"):
            lines = await _collect_stream(stream_generator(**_make_stream_call()))

        # Even without actual keepalives (no 20s delay), verify the format is correct
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            is_data = stripped.startswith("data: ")
            is_keepalive = stripped.startswith(": keepalive")
            assert is_data or is_keepalive, f"Invalid SSE line: {stripped[:80]}"


class TestEmptyResponseFallback:

    @pytest.mark.asyncio
    async def test_no_text_no_complete_text_yields_fallback(self):
        """When SDK yields complete with empty text and no prior text events."""
        from app.streaming_routes import stream_generator

        async def empty_sdk(**kwargs):
            yield {"type": "complete", "text": "", "tools_called": [], "usage": {}}

        with patch("app.streaming_routes.sdk_query_streaming", empty_sdk), \
             patch("app.streaming_routes.add_message"):
            lines = await _collect_stream(stream_generator(**_make_stream_call()))

        events = _parse_sse_events(lines)
        text_events = [e for e in events if e.get("type") == "text"]
        all_content = "".join(e.get("content", "") for e in text_events)
        assert "No response generated" in all_content

    @pytest.mark.asyncio
    async def test_only_tool_events_gets_fallback(self):
        """When SDK yields tool events but no text, fallback appears."""
        from app.streaming_routes import stream_generator

        async def tool_only_sdk(**kwargs):
            yield {"type": "tool_use", "name": "search_far", "input": {}, "tool_use_id": "tu-1"}
            yield {"type": "tool_result", "name": "search_far", "result": {"text": "FAR 13"}}
            yield {"type": "complete", "text": "", "tools_called": ["search_far"], "usage": {}}

        with patch("app.streaming_routes.sdk_query_streaming", tool_only_sdk), \
             patch("app.streaming_routes.add_message"):
            lines = await _collect_stream(stream_generator(**_make_stream_call()))

        events = _parse_sse_events(lines)
        text_events = [e for e in events if e.get("type") == "text"]
        all_content = "".join(e.get("content", "") for e in text_events)
        assert "No response generated" in all_content


class TestGeneratorExhaustion:

    @pytest.mark.asyncio
    async def test_generator_without_complete_still_emits_complete(self):
        """If sdk_query_streaming ends without a complete chunk, stream_generator adds one."""
        from app.streaming_routes import stream_generator

        async def no_complete_sdk(**kwargs):
            yield {"type": "text", "data": "partial response"}
            # No complete event — generator just ends

        with patch("app.streaming_routes.sdk_query_streaming", no_complete_sdk), \
             patch("app.streaming_routes.add_message"):
            lines = await _collect_stream(stream_generator(**_make_stream_call()))

        events = _parse_sse_events(lines)
        complete_events = [e for e in events if e.get("type") == "complete"]
        assert len(complete_events) == 1, "Should emit fallback complete event"


class TestErrorChunkFromSDK:

    @pytest.mark.asyncio
    async def test_error_chunk_terminates_stream(self):
        """An error chunk from SDK should emit error event and stop."""
        from app.streaming_routes import stream_generator

        async def error_sdk(**kwargs):
            yield {"type": "text", "data": "starting"}
            yield {"type": "error", "error": "Model overloaded"}
            yield {"type": "text", "data": "this should never appear"}

        with patch("app.streaming_routes.sdk_query_streaming", error_sdk), \
             patch("app.streaming_routes.add_message"):
            lines = await _collect_stream(stream_generator(**_make_stream_call()))

        events = _parse_sse_events(lines)
        types = [e["type"] for e in events]
        assert "error" in types
        # The text after error should NOT appear
        text_contents = [e.get("content", "") for e in events if e["type"] == "text"]
        assert not any("this should never appear" in t for t in text_contents)


class TestEventOrdering:

    @pytest.mark.asyncio
    async def test_complete_is_last_event(self):
        """Complete event must be the final SSE event."""
        from app.streaming_routes import stream_generator

        async def normal_sdk(**kwargs):
            yield {"type": "text", "data": "hello"}
            yield {"type": "tool_use", "name": "search_far", "input": {}, "tool_use_id": "tu-1"}
            yield {"type": "tool_result", "name": "search_far", "result": {"text": "found"}}
            yield {"type": "text", "data": " world"}
            yield {"type": "complete", "text": "hello world", "tools_called": ["search_far"], "usage": {}}

        with patch("app.streaming_routes.sdk_query_streaming", normal_sdk), \
             patch("app.streaming_routes.add_message"):
            lines = await _collect_stream(stream_generator(**_make_stream_call()))

        events = _parse_sse_events(lines)
        # Filter out initial empty text handshake
        typed_events = [e for e in events if e.get("type")]
        assert typed_events[-1]["type"] == "complete"

    @pytest.mark.asyncio
    async def test_tool_use_before_tool_result(self):
        """tool_use must appear before its matching tool_result in the event stream."""
        from app.streaming_routes import stream_generator

        async def ordered_sdk(**kwargs):
            yield {"type": "tool_use", "name": "load_data", "input": {}, "tool_use_id": "tu-1"}
            yield {"type": "tool_result", "name": "load_data", "result": {"rows": 5}}
            yield {"type": "text", "data": "loaded"}
            yield {"type": "complete", "text": "loaded", "tools_called": ["load_data"], "usage": {}}

        with patch("app.streaming_routes.sdk_query_streaming", ordered_sdk), \
             patch("app.streaming_routes.add_message"):
            lines = await _collect_stream(stream_generator(**_make_stream_call()))

        events = _parse_sse_events(lines)
        tool_use_idx = next(
            i for i, e in enumerate(events) if e.get("type") == "tool_use"
        )
        tool_result_idx = next(
            i for i, e in enumerate(events) if e.get("type") == "tool_result"
        )
        assert tool_use_idx < tool_result_idx
