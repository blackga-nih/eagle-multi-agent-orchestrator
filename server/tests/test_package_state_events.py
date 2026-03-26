"""Unit tests for package state_update SSE event emission.

Tests that manage_package create/update operations emit correct state_update
chunks, and that the streaming route forwards them as SSE metadata events.

Run: pytest server/tests/test_package_state_events.py -v
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


MOCK_CHECKLIST = {
    "required": ["sow", "igce", "market_research", "acquisition_plan"],
    "completed": ["sow"],
    "missing": ["igce", "market_research", "acquisition_plan"],
    "complete": False,
}

MOCK_PACKAGE = {
    "package_id": "PKG-2026-0001",
    "title": "CT Scanner Procurement",
    "status": "drafting",
    "requirement_type": "products",
    "estimated_value": 500000,
    "acquisition_method": "negotiated",
    "contract_type": "ffp",
    "contract_vehicle": None,
}


# ── Tests: _emit_package_state ───────────────────────────────────────


class TestEmitPackageState:

    def _drain_queue_via_loop(self, loop, queue):
        """Run the event loop briefly to process call_soon_threadsafe callbacks, then drain."""
        # _emit_package_state uses loop.call_soon_threadsafe(queue.put_nowait, ...),
        # so we must run the loop to execute the scheduled callbacks.
        loop.call_soon(loop.stop)
        loop.run_forever()
        events = []
        while not queue.empty():
            events.append(queue.get_nowait())
        return events

    def test_emit_package_state_no_package_id_is_noop(self):
        """When tool_result has no package_id, nothing should be queued."""
        from app.strands_agentic_service import _emit_package_state

        loop = asyncio.new_event_loop()
        queue = asyncio.Queue()

        _emit_package_state(
            tool_result={},  # no package_id
            tool_name="create_document",
            tenant_id="test-tenant",
            result_queue=queue,
            loop=loop,
        )

        events = self._drain_queue_via_loop(loop, queue)
        assert len(events) == 0, "Queue should be empty when no package_id in result"
        loop.close()

    def test_emit_package_state_document_ready(self):
        """create_document should emit both document_ready and checklist_update."""
        from app.strands_agentic_service import _emit_package_state

        loop = asyncio.new_event_loop()
        queue = asyncio.Queue()

        with patch("app.package_store.get_package_checklist", return_value=MOCK_CHECKLIST):
            _emit_package_state(
                tool_result={"package_id": "PKG-2026-0001", "doc_type": "sow"},
                tool_name="create_document",
                tenant_id="test-tenant",
                result_queue=queue,
                loop=loop,
            )

        events = self._drain_queue_via_loop(loop, queue)

        state_types = [e.get("state_type") for e in events]
        assert "document_ready" in state_types, "Should emit document_ready for create_document"
        assert "checklist_update" in state_types, "Should always emit checklist_update"

        doc_ready = next(e for e in events if e["state_type"] == "document_ready")
        assert doc_ready["package_id"] == "PKG-2026-0001"
        assert doc_ready["doc_type"] == "sow"
        assert doc_ready["progress_pct"] == 25  # 1 of 4 = 25%

        loop.close()

    def test_emit_package_state_checklist_update_on_manage_package(self):
        """manage_package should emit checklist_update with package metadata."""
        from app.strands_agentic_service import _emit_package_state

        loop = asyncio.new_event_loop()
        queue = asyncio.Queue()

        with patch("app.package_store.get_package_checklist", return_value=MOCK_CHECKLIST):
            _emit_package_state(
                tool_result={"package_id": "PKG-2026-0001"},
                tool_name="manage_package",
                tenant_id="test-tenant",
                result_queue=queue,
                loop=loop,
            )

        events = self._drain_queue_via_loop(loop, queue)

        # manage_package should emit checklist_update (not document_ready)
        state_types = [e.get("state_type") for e in events]
        assert "checklist_update" in state_types
        assert "document_ready" not in state_types

        checklist_evt = next(e for e in events if e["state_type"] == "checklist_update")
        assert checklist_evt["checklist"] == MOCK_CHECKLIST
        assert checklist_evt["progress_pct"] == 25

        loop.close()


# ── Tests: _build_end_of_turn_state ──────────────────────────────────


class TestBuildEndOfTurnState:

    def test_returns_checklist_update(self):
        """Should return one checklist_update dict with package metadata."""
        from app.strands_agentic_service import _build_end_of_turn_state

        mock_ctx = MagicMock()
        mock_ctx.package_id = "PKG-2026-0001"

        with patch("app.package_store.get_package_checklist", return_value=MOCK_CHECKLIST), \
             patch("app.package_store.get_package", return_value=MOCK_PACKAGE):
            result = _build_end_of_turn_state(mock_ctx, "test-tenant")

        assert len(result) == 1
        evt = result[0]
        assert evt["type"] == "state_update"
        assert evt["state_type"] == "checklist_update"
        assert evt["package_id"] == "PKG-2026-0001"
        assert evt["checklist"] == MOCK_CHECKLIST
        assert evt["progress_pct"] == 25
        assert evt["phase"] == "drafting"
        assert evt["title"] == "CT Scanner Procurement"

    def test_returns_empty_when_no_context(self):
        """Should return empty list when package_context is None."""
        from app.strands_agentic_service import _build_end_of_turn_state

        result = _build_end_of_turn_state(None, "test-tenant")
        assert result == []

    def test_returns_empty_when_no_package_id(self):
        """Should return empty list when package_context has no package_id."""
        from app.strands_agentic_service import _build_end_of_turn_state

        mock_ctx = MagicMock()
        mock_ctx.package_id = None

        result = _build_end_of_turn_state(mock_ctx, "test-tenant")
        assert result == []


# ── Tests: _build_state_updates ──────────────────────────────────────


class TestBuildStateUpdates:

    def test_create_document_emits_both_events(self):
        """create_document should produce document_ready + checklist_update."""
        from app.strands_agentic_service import _build_state_updates

        with patch("app.package_store.get_package_checklist", return_value=MOCK_CHECKLIST):
            events = _build_state_updates(
                tool_result={"package_id": "PKG-2026-0001", "doc_type": "igce"},
                tool_name="create_document",
                tenant_id="test-tenant",
            )

        assert len(events) == 2
        assert events[0]["state_type"] == "document_ready"
        assert events[0]["doc_type"] == "igce"
        assert events[1]["state_type"] == "checklist_update"

    def test_no_package_id_returns_empty(self):
        """No package_id in tool_result → empty list."""
        from app.strands_agentic_service import _build_state_updates

        events = _build_state_updates(
            tool_result={"doc_type": "sow"},
            tool_name="create_document",
            tenant_id="test-tenant",
        )
        assert events == []


# ── Tests: SSE streaming route forwards state_update ─────────────────


class TestStreamingRouteForwardsStateUpdate:

    @pytest.mark.asyncio
    async def test_state_update_chunk_becomes_metadata_sse_event(self):
        """A state_update chunk from the SDK should appear as a metadata SSE event."""
        from app.streaming_routes import stream_generator

        async def fake_sdk(**kwargs):
            yield {
                "type": "state_update",
                "state_type": "checklist_update",
                "package_id": "PKG-2026-0001",
                "checklist": MOCK_CHECKLIST,
                "progress_pct": 25,
            }
            yield {"type": "text", "data": "Package created."}
            yield {"type": "complete", "text": "Package created.", "tools_called": ["manage_package"], "usage": {}}

        with patch("app.streaming_routes.sdk_query_streaming", fake_sdk), \
             patch("app.streaming_routes.add_message"):
            lines = await _collect_stream(stream_generator(
                message="create a package",
                tenant_id="t",
                user_id="u",
                tier="advanced",
                subscription_service=None,
                session_id="s",
            ))

        events = _parse_sse_events(lines)
        metadata_events = [e for e in events if e.get("type") == "metadata"]

        assert len(metadata_events) >= 1, f"Expected at least 1 metadata event, got {len(metadata_events)}"

        state_evt = next(
            (e for e in metadata_events if e.get("metadata", {}).get("state_type") == "checklist_update"),
            None,
        )
        assert state_evt is not None, f"No checklist_update metadata event found in: {metadata_events}"
        assert state_evt["metadata"]["package_id"] == "PKG-2026-0001"
        assert state_evt["metadata"]["checklist"] == MOCK_CHECKLIST
        assert state_evt["metadata"]["progress_pct"] == 25

    @pytest.mark.asyncio
    async def test_multiple_state_updates_all_forwarded(self):
        """Multiple state_update chunks should each become metadata SSE events."""
        from app.streaming_routes import stream_generator

        async def fake_sdk(**kwargs):
            yield {
                "type": "state_update",
                "state_type": "checklist_update",
                "package_id": "PKG-2026-0001",
                "checklist": MOCK_CHECKLIST,
                "progress_pct": 25,
            }
            yield {
                "type": "state_update",
                "state_type": "document_ready",
                "package_id": "PKG-2026-0001",
                "doc_type": "sow",
            }
            yield {"type": "text", "data": "done"}
            yield {"type": "complete", "text": "done", "tools_called": [], "usage": {}}

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
        metadata_events = [e for e in events if e.get("type") == "metadata"]
        state_types = [e.get("metadata", {}).get("state_type") for e in metadata_events]

        assert "checklist_update" in state_types
        assert "document_ready" in state_types
