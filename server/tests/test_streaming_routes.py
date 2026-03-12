"""Unit tests for streaming_routes.py SSE formatting and behavior.

Mocks sdk_query_streaming() at the route level to test:
- SSE wire format
- Keepalive emission
- Empty-name tool_result filtering
- Tool input JSON parsing
- Fallback text on empty response

Run: pytest server/tests/test_streaming_routes.py -v
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


# ── Tests ────────────────────────────────────────────────────────────


class TestSSEFormat:

    @pytest.mark.asyncio
    async def test_all_output_is_valid_sse_or_keepalive(self):
        """Every yielded string must be 'data: {...}\\n\\n' or ': keepalive\\n\\n'."""
        from app.streaming_routes import stream_generator

        async def fake_sdk(**kwargs):
            yield {"type": "text", "data": "hello"}
            yield {"type": "complete", "text": "hello", "tools_called": [], "usage": {}}

        with patch("app.streaming_routes.sdk_query_streaming", fake_sdk), \
             patch("app.streaming_routes.add_message"):
            lines = await _collect_stream(stream_generator(
                message="hi",
                tenant_id="t",
                user_id="u",
                tier="advanced",
                subscription_service=None,
                session_id="s",
            ))

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            assert stripped.startswith("data: ") or stripped.startswith(": keepalive"), \
                f"Invalid SSE line: {stripped[:100]}"

    @pytest.mark.asyncio
    async def test_events_have_agent_id_and_timestamp(self):
        from app.streaming_routes import stream_generator

        async def fake_sdk(**kwargs):
            yield {"type": "text", "data": "hello"}
            yield {"type": "complete", "text": "hello", "tools_called": [], "usage": {}}

        with patch("app.streaming_routes.sdk_query_streaming", fake_sdk), \
             patch("app.streaming_routes.add_message"):
            lines = await _collect_stream(stream_generator(
                message="hi",
                tenant_id="t",
                user_id="u",
                tier="advanced",
                subscription_service=None,
                session_id="s",
            ))

        events = _parse_sse_events(lines)
        for evt in events:
            assert "agent_id" in evt, f"Missing agent_id in {evt}"
            assert "timestamp" in evt, f"Missing timestamp in {evt}"


class TestEmptyNameFilter:

    @pytest.mark.asyncio
    async def test_empty_name_tool_result_filtered(self):
        """tool_result with empty name should be silently dropped."""
        from app.streaming_routes import stream_generator

        async def fake_sdk(**kwargs):
            yield {"type": "tool_use", "name": "search_far", "input": {}, "tool_use_id": "tu-1"}
            yield {"type": "tool_result", "name": "", "result": {}}  # empty name — should be filtered
            yield {"type": "tool_result", "name": "search_far", "result": {"text": "FAR 13..."}}
            yield {"type": "text", "data": "done"}
            yield {"type": "complete", "text": "done", "tools_called": ["search_far"], "usage": {}}

        with patch("app.streaming_routes.sdk_query_streaming", fake_sdk), \
             patch("app.streaming_routes.add_message"):
            lines = await _collect_stream(stream_generator(
                message="query",
                tenant_id="t",
                user_id="u",
                tier="advanced",
                subscription_service=None,
                session_id="s",
            ))

        events = _parse_sse_events(lines)
        tool_results = [e for e in events if e.get("type") == "tool_result"]
        # Only the named result should pass through
        assert len(tool_results) == 1
        assert tool_results[0]["tool_result"]["name"] == "search_far"


class TestToolInputParsing:

    @pytest.mark.asyncio
    async def test_string_input_parsed_to_json(self):
        from app.streaming_routes import stream_generator

        async def fake_sdk(**kwargs):
            yield {"type": "tool_use", "name": "search_far", "input": '{"query": "FAR 13"}', "tool_use_id": "tu-1"}
            yield {"type": "text", "data": "done"}
            yield {"type": "complete", "text": "done", "tools_called": ["search_far"], "usage": {}}

        with patch("app.streaming_routes.sdk_query_streaming", fake_sdk), \
             patch("app.streaming_routes.add_message"):
            lines = await _collect_stream(stream_generator(
                message="q",
                tenant_id="t",
                user_id="u",
                tier="advanced",
                subscription_service=None,
                session_id="s",
            ))

        events = _parse_sse_events(lines)
        tool_uses = [e for e in events if e.get("type") == "tool_use"]
        assert len(tool_uses) == 1
        assert tool_uses[0]["tool_use"]["input"] == {"query": "FAR 13"}

    @pytest.mark.asyncio
    async def test_invalid_json_input_wrapped(self):
        from app.streaming_routes import stream_generator

        async def fake_sdk(**kwargs):
            yield {"type": "tool_use", "name": "search_far", "input": "not-json", "tool_use_id": "tu-1"}
            yield {"type": "text", "data": "done"}
            yield {"type": "complete", "text": "done", "tools_called": ["search_far"], "usage": {}}

        with patch("app.streaming_routes.sdk_query_streaming", fake_sdk), \
             patch("app.streaming_routes.add_message"):
            lines = await _collect_stream(stream_generator(
                message="q",
                tenant_id="t",
                user_id="u",
                tier="advanced",
                subscription_service=None,
                session_id="s",
            ))

        events = _parse_sse_events(lines)
        tool_uses = [e for e in events if e.get("type") == "tool_use"]
        assert len(tool_uses) == 1
        assert tool_uses[0]["tool_use"]["input"] == {"raw": "not-json"}


class TestFallbackText:

    @pytest.mark.asyncio
    async def test_no_text_emits_fallback(self):
        """When SDK yields complete with no prior text, a fallback message appears."""
        from app.streaming_routes import stream_generator

        async def fake_sdk(**kwargs):
            yield {"type": "complete", "text": "", "tools_called": [], "usage": {}}

        with patch("app.streaming_routes.sdk_query_streaming", fake_sdk), \
             patch("app.streaming_routes.add_message"):
            lines = await _collect_stream(stream_generator(
                message="q",
                tenant_id="t",
                user_id="u",
                tier="advanced",
                subscription_service=None,
                session_id="s",
            ))

        events = _parse_sse_events(lines)
        text_events = [e for e in events if e.get("type") == "text"]
        # Should have at least one text event with fallback content
        all_content = " ".join(e.get("content", "") for e in text_events)
        assert "No response generated" in all_content or len(all_content) > 0


class TestToolUsePassthrough:

    @pytest.mark.asyncio
    async def test_tool_use_id_passed_through(self):
        from app.streaming_routes import stream_generator

        async def fake_sdk(**kwargs):
            yield {"type": "tool_use", "name": "search_far", "input": {}, "tool_use_id": "tu-abc-123"}
            yield {"type": "text", "data": "done"}
            yield {"type": "complete", "text": "done", "tools_called": ["search_far"], "usage": {}}

        with patch("app.streaming_routes.sdk_query_streaming", fake_sdk), \
             patch("app.streaming_routes.add_message"):
            lines = await _collect_stream(stream_generator(
                message="q",
                tenant_id="t",
                user_id="u",
                tier="advanced",
                subscription_service=None,
                session_id="s",
            ))

        events = _parse_sse_events(lines)
        tool_uses = [e for e in events if e.get("type") == "tool_use"]
        assert len(tool_uses) == 1
        assert tool_uses[0]["tool_use"]["tool_use_id"] == "tu-abc-123"


class TestChecklistMetadataPush:
    """Tests for forced checklist_update metadata on complete in package mode."""

    def _make_package_context(self, package_id="pkg-001"):
        """Create a PackageContext in package mode."""
        from app.package_context_service import PackageContext
        return PackageContext(
            mode="package",
            package_id=package_id,
            package_title="Test AP",
            required_documents=["SOW", "IGCE", "AP"],
            completed_documents=["SOW"],
        )

    @pytest.mark.asyncio
    async def test_checklist_update_emitted_on_complete_in_package_mode(self):
        """When package_context.is_package_mode, complete should emit checklist_update metadata."""
        from app.streaming_routes import stream_generator

        fake_checklist = {
            "required": ["SOW", "IGCE", "AP"],
            "completed": ["SOW"],
            "missing": ["IGCE", "AP"],
            "complete": False,
        }

        async def fake_sdk(**kwargs):
            yield {"type": "text", "data": "done"}
            yield {"type": "complete", "text": "done", "tools_called": [], "usage": {}}

        with patch("app.streaming_routes.sdk_query_streaming", fake_sdk), \
             patch("app.streaming_routes.add_message"), \
             patch("app.package_store.get_package_checklist", return_value=fake_checklist):
            lines = await _collect_stream(stream_generator(
                message="hi",
                tenant_id="t",
                user_id="u",
                tier="advanced",
                subscription_service=None,
                session_id="s",
                package_context=self._make_package_context(),
            ))

        events = _parse_sse_events(lines)
        metadata_events = [
            e for e in events
            if e.get("type") == "metadata"
            and isinstance(e.get("metadata"), dict)
            and e["metadata"].get("state_type") == "checklist_update"
        ]
        assert len(metadata_events) == 1, f"Expected 1 checklist_update metadata, got {len(metadata_events)}"
        md = metadata_events[0]["metadata"]
        assert md["package_id"] == "pkg-001"
        assert md["checklist"] == fake_checklist
        assert md["progress_pct"] == 33  # 1/3 = 33%

    @pytest.mark.asyncio
    async def test_no_checklist_metadata_without_package_context(self):
        """When package_context is None, no checklist_update metadata should be emitted."""
        from app.streaming_routes import stream_generator

        async def fake_sdk(**kwargs):
            yield {"type": "text", "data": "done"}
            yield {"type": "complete", "text": "done", "tools_called": [], "usage": {}}

        with patch("app.streaming_routes.sdk_query_streaming", fake_sdk), \
             patch("app.streaming_routes.add_message"):
            lines = await _collect_stream(stream_generator(
                message="hi",
                tenant_id="t",
                user_id="u",
                tier="advanced",
                subscription_service=None,
                session_id="s",
                package_context=None,
            ))

        events = _parse_sse_events(lines)
        metadata_events = [
            e for e in events
            if e.get("type") == "metadata"
            and isinstance(e.get("metadata"), dict)
            and e["metadata"].get("state_type") == "checklist_update"
        ]
        assert len(metadata_events) == 0, "No checklist_update expected without package context"

    @pytest.mark.asyncio
    async def test_no_checklist_metadata_in_workspace_mode(self):
        """PackageContext in workspace mode (is_package_mode=False) should not emit checklist."""
        from app.streaming_routes import stream_generator
        from app.package_context_service import PackageContext

        workspace_ctx = PackageContext(mode="workspace")

        async def fake_sdk(**kwargs):
            yield {"type": "text", "data": "done"}
            yield {"type": "complete", "text": "done", "tools_called": [], "usage": {}}

        with patch("app.streaming_routes.sdk_query_streaming", fake_sdk), \
             patch("app.streaming_routes.add_message"):
            lines = await _collect_stream(stream_generator(
                message="hi",
                tenant_id="t",
                user_id="u",
                tier="advanced",
                subscription_service=None,
                session_id="s",
                package_context=workspace_ctx,
            ))

        events = _parse_sse_events(lines)
        metadata_events = [
            e for e in events
            if e.get("type") == "metadata"
            and isinstance(e.get("metadata"), dict)
            and e["metadata"].get("state_type") == "checklist_update"
        ]
        assert len(metadata_events) == 0, "No checklist_update expected in workspace mode"
