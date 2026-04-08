"""Tests for 2026-04-08 dev huddle fixes.

Covers:
- Plan 1: Streaming noise reduction (tool_input_delta filtering, tool_input dedup)
- Plan 3: Statement of Need (SON) template generation pipeline
- Plan 4: Package checklist endpoint (backend portion)

Run: pytest server/tests/test_huddle_20260408_fixes.py -v
"""

import asyncio
import json
import os
import sys
from functools import wraps
from unittest.mock import patch

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
    lines = []
    async for line in gen:
        lines.append(line)
    return lines


def async_test(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        return asyncio.run(fn(*args, **kwargs))
    return wrapper


# ══════════════════════════════════════════════════════════════════════
# PLAN 1 — Streaming noise reduction
# ══════════════════════════════════════════════════════════════════════


class TestToolInputDeltaFiltering:
    """tool_input_delta should only pass through for document-creation tools."""

    @async_test
    async def test_create_document_delta_passes_through(self):
        """tool_input_delta for create_document should emit an SSE event."""
        from app.streaming_routes import stream_generator

        async def fake_sdk(**kwargs):
            yield {"type": "tool_use", "name": "create_document", "input": {}, "tool_use_id": "tu-1"}
            yield {"type": "tool_input_delta", "tool_use_id": "tu-1", "delta": '{"content": "# SOW"}', "name": "create_document"}
            yield {"type": "complete", "text": "", "tools_called": ["create_document"], "usage": {}}

        with patch("app.streaming_routes.sdk_query_streaming", fake_sdk), \
             patch("app.streaming_routes.add_message"):
            lines = await _collect_stream(stream_generator(
                message="create a sow",
                tenant_id="t", user_id="u", tier="advanced",
                subscription_service=None, session_id="s",
            ))

        events = _parse_sse_events(lines)
        deltas = [e for e in events if e.get("type") == "tool_input_delta"]
        assert len(deltas) == 1
        assert deltas[0]["metadata"]["tool_name"] == "create_document"

    @async_test
    async def test_update_document_delta_passes_through(self):
        """tool_input_delta for update_document should emit an SSE event."""
        from app.streaming_routes import stream_generator

        async def fake_sdk(**kwargs):
            yield {"type": "tool_use", "name": "update_document", "input": {}, "tool_use_id": "tu-2"}
            yield {"type": "tool_input_delta", "tool_use_id": "tu-2", "delta": "partial", "name": "update_document"}
            yield {"type": "complete", "text": "", "tools_called": ["update_document"], "usage": {}}

        with patch("app.streaming_routes.sdk_query_streaming", fake_sdk), \
             patch("app.streaming_routes.add_message"):
            lines = await _collect_stream(stream_generator(
                message="update doc",
                tenant_id="t", user_id="u", tier="advanced",
                subscription_service=None, session_id="s",
            ))

        events = _parse_sse_events(lines)
        deltas = [e for e in events if e.get("type") == "tool_input_delta"]
        assert len(deltas) == 1

    @async_test
    async def test_knowledge_search_delta_filtered(self):
        """tool_input_delta for knowledge_search should NOT emit (noise reduction)."""
        from app.streaming_routes import stream_generator

        async def fake_sdk(**kwargs):
            yield {"type": "tool_use", "name": "knowledge_search", "input": {}, "tool_use_id": "tu-3"}
            yield {"type": "tool_input_delta", "tool_use_id": "tu-3", "delta": '{"query": "FAR"}', "name": "knowledge_search"}
            yield {"type": "tool_result", "name": "knowledge_search", "result": {"text": "found"}}
            yield {"type": "complete", "text": "done", "tools_called": ["knowledge_search"], "usage": {}}

        with patch("app.streaming_routes.sdk_query_streaming", fake_sdk), \
             patch("app.streaming_routes.add_message"):
            lines = await _collect_stream(stream_generator(
                message="search",
                tenant_id="t", user_id="u", tier="advanced",
                subscription_service=None, session_id="s",
            ))

        events = _parse_sse_events(lines)
        deltas = [e for e in events if e.get("type") == "tool_input_delta"]
        assert len(deltas) == 0, "knowledge_search deltas should be filtered out"

    @async_test
    async def test_compliance_matrix_delta_filtered(self):
        """tool_input_delta for query_compliance_matrix should NOT emit."""
        from app.streaming_routes import stream_generator

        async def fake_sdk(**kwargs):
            yield {"type": "tool_use", "name": "query_compliance_matrix", "input": {}, "tool_use_id": "tu-4"}
            yield {"type": "tool_input_delta", "tool_use_id": "tu-4", "delta": "partial", "name": "query_compliance_matrix"}
            yield {"type": "complete", "text": "done", "tools_called": ["query_compliance_matrix"], "usage": {}}

        with patch("app.streaming_routes.sdk_query_streaming", fake_sdk), \
             patch("app.streaming_routes.add_message"):
            lines = await _collect_stream(stream_generator(
                message="thresholds",
                tenant_id="t", user_id="u", tier="advanced",
                subscription_service=None, session_id="s",
            ))

        events = _parse_sse_events(lines)
        deltas = [e for e in events if e.get("type") == "tool_input_delta"]
        assert len(deltas) == 0, "compliance matrix deltas should be filtered out"

    @async_test
    async def test_web_search_delta_filtered(self):
        """tool_input_delta for web_search should NOT emit."""
        from app.streaming_routes import stream_generator

        async def fake_sdk(**kwargs):
            yield {"type": "tool_use", "name": "web_search", "input": {}, "tool_use_id": "tu-5"}
            yield {"type": "tool_input_delta", "tool_use_id": "tu-5", "delta": "q", "name": "web_search"}
            yield {"type": "complete", "text": "", "tools_called": ["web_search"], "usage": {}}

        with patch("app.streaming_routes.sdk_query_streaming", fake_sdk), \
             patch("app.streaming_routes.add_message"):
            lines = await _collect_stream(stream_generator(
                message="market research",
                tenant_id="t", user_id="u", tier="advanced",
                subscription_service=None, session_id="s",
            ))

        events = _parse_sse_events(lines)
        deltas = [e for e in events if e.get("type") == "tool_input_delta"]
        assert len(deltas) == 0


class TestToolInputDedup:
    """tool_input without a matching tool_use_id should NOT emit a duplicate card."""

    @async_test
    async def test_tool_input_with_valid_id_emits(self):
        """tool_input with a matching tool_use_id should patch the existing card."""
        from app.streaming_routes import stream_generator

        async def fake_sdk(**kwargs):
            yield {"type": "tool_use", "name": "search_far", "input": {}, "tool_use_id": "tu-10"}
            yield {"type": "tool_input", "name": "search_far", "input": {"query": "FAR 13"}}
            yield {"type": "tool_result", "name": "search_far", "result": {"text": "done"}}
            yield {"type": "complete", "text": "ok", "tools_called": ["search_far"], "usage": {}}

        with patch("app.streaming_routes.sdk_query_streaming", fake_sdk), \
             patch("app.streaming_routes.add_message"):
            lines = await _collect_stream(stream_generator(
                message="search",
                tenant_id="t", user_id="u", tier="advanced",
                subscription_service=None, session_id="s",
            ))

        events = _parse_sse_events(lines)
        tool_uses = [e for e in events if e.get("type") == "tool_use"]
        # Should have 2 tool_use events: initial + patched input
        assert len(tool_uses) == 2
        # Both should carry the same tool_use_id
        ids = [e["tool_use"]["tool_use_id"] for e in tool_uses]
        assert ids[0] == "tu-10"
        assert ids[1] == "tu-10"

    @async_test
    async def test_tool_input_without_id_does_not_emit(self):
        """tool_input when ID queue is exhausted should be silently dropped."""
        from app.streaming_routes import stream_generator

        async def fake_sdk(**kwargs):
            # No preceding tool_use — the ID queue will be empty
            yield {"type": "tool_input", "name": "search_far", "input": {"query": "orphan"}}
            yield {"type": "text", "data": "done"}
            yield {"type": "complete", "text": "done", "tools_called": [], "usage": {}}

        with patch("app.streaming_routes.sdk_query_streaming", fake_sdk), \
             patch("app.streaming_routes.add_message"):
            lines = await _collect_stream(stream_generator(
                message="test",
                tenant_id="t", user_id="u", tier="advanced",
                subscription_service=None, session_id="s",
            ))

        events = _parse_sse_events(lines)
        tool_uses = [e for e in events if e.get("type") == "tool_use"]
        assert len(tool_uses) == 0, "tool_input without matching ID should not create a card"


# ══════════════════════════════════════════════════════════════════════
# PLAN 3 — Statement of Need template generation
# ══════════════════════════════════════════════════════════════════════


class TestSONDocTypeLabels:
    """son_products and son_services must be registered in the generation pipeline."""

    def test_son_products_in_labels(self):
        from app.tools.create_document_support import _DOC_TYPE_LABELS
        assert "son_products" in _DOC_TYPE_LABELS
        assert "Products" in _DOC_TYPE_LABELS["son_products"]

    def test_son_services_in_labels(self):
        from app.tools.create_document_support import _DOC_TYPE_LABELS
        assert "son_services" in _DOC_TYPE_LABELS
        assert "Services" in _DOC_TYPE_LABELS["son_services"]

    def test_son_products_has_system_prompt(self):
        from app.tools.create_document_support import _DOC_TYPE_SYSTEM_PROMPTS
        assert "son_products" in _DOC_TYPE_SYSTEM_PROMPTS
        prompt = _DOC_TYPE_SYSTEM_PROMPTS["son_products"]
        assert "Statement of Need" in prompt
        assert "Products" in prompt
        assert "FAR Part 11" in prompt

    def test_son_services_has_system_prompt(self):
        from app.tools.create_document_support import _DOC_TYPE_SYSTEM_PROMPTS
        assert "son_services" in _DOC_TYPE_SYSTEM_PROMPTS
        prompt = _DOC_TYPE_SYSTEM_PROMPTS["son_services"]
        assert "Statement of Need" in prompt
        assert "Services" in prompt
        assert "FAR Part 11" in prompt

    def test_son_products_prompt_has_required_sections(self):
        from app.tools.create_document_support import _DOC_TYPE_SYSTEM_PROMPTS
        prompt = _DOC_TYPE_SYSTEM_PROMPTS["son_products"]
        for section in [
            "DESCRIPTION OF NEED",
            "PRODUCT SPECIFICATIONS",
            "DELIVERY REQUIREMENTS",
            "ESTIMATED COST",
            "APPROVALS",
        ]:
            assert section in prompt, f"Missing required section: {section}"

    def test_son_services_prompt_has_required_sections(self):
        from app.tools.create_document_support import _DOC_TYPE_SYSTEM_PROMPTS
        prompt = _DOC_TYPE_SYSTEM_PROMPTS["son_services"]
        for section in [
            "DESCRIPTION OF NEED",
            "SERVICE REQUIREMENTS",
            "PERIOD OF PERFORMANCE",
            "PERFORMANCE STANDARDS",
            "APPROVALS",
        ]:
            assert section in prompt, f"Missing required section: {section}"


class TestSONGeneratorFunctions:
    """Generator functions must exist and be wired into the dispatch map."""

    def test_son_products_generator_exists(self):
        from app.tools.create_document_support import _generate_son_products
        assert callable(_generate_son_products)

    def test_son_services_generator_exists(self):
        from app.tools.create_document_support import _generate_son_services
        assert callable(_generate_son_services)

    def test_son_products_in_document_generation_imports(self):
        """The dispatch map in document_generation.py should include son_products."""
        from app.tools.document_generation import exec_create_document
        # Read the source to verify the generator is wired
        import inspect
        source = inspect.getsource(exec_create_document)
        assert "son_products" in source

    def test_son_services_in_document_generation_imports(self):
        from app.tools.document_generation import exec_create_document
        import inspect
        source = inspect.getsource(exec_create_document)
        assert "son_services" in source


class TestSONDocTypeValidation:
    """son_products and son_services should be recognized as valid doc types."""

    def test_son_products_is_valid(self):
        from app.doc_type_registry import is_valid_doc_type
        assert is_valid_doc_type("son_products") is True

    def test_son_services_is_valid(self):
        from app.doc_type_registry import is_valid_doc_type
        assert is_valid_doc_type("son_services") is True

    def test_son_normalizes_from_hyphen(self):
        from app.doc_type_registry import normalize_doc_type
        assert normalize_doc_type("son-products") == "son_products"
        assert normalize_doc_type("son-services") == "son_services"


# ══════════════════════════════════════════════════════════════════════
# PLAN 4 — Package checklist endpoint
# ══════════════════════════════════════════════════════════════════════


class TestPackageChecklistEndpoint:
    """The /api/packages/{id}/checklist endpoint must return document items."""

    def test_checklist_function_exists(self):
        from app.package_store import get_package_checklist
        assert callable(get_package_checklist)

    def test_checklist_route_registered(self):
        """The checklist route must be registered on the packages router."""
        from app.routers.packages import router
        paths = [r.path for r in router.routes]
        assert any("checklist" in p for p in paths)


class TestPackageSessionLinking:
    """Packages must support optional session_id linking."""

    def test_create_package_accepts_session_id(self):
        """create_package function signature must accept session_id."""
        import inspect
        from app.package_store import create_package
        sig = inspect.signature(create_package)
        assert "session_id" in sig.parameters

    def test_session_id_is_optional(self):
        """session_id should default to None."""
        import inspect
        from app.package_store import create_package
        sig = inspect.signature(create_package)
        param = sig.parameters["session_id"]
        assert param.default is None
