"""Integration wiring tests for canonical package document flow."""

from __future__ import annotations

import asyncio
import json
from unittest import mock

from app.document_service import DocumentResult


def test_exec_create_document_routes_package_mode_to_canonical(monkeypatch):
    """When package_id is present, create_document should use canonical service."""
    from app.agentic_service import _exec_create_document

    class FakeTemplateResult:
        success = False
        error = "template unavailable"

    class FakeTemplateService:
        def __init__(self, tenant_id, user_id, markdown_generators):
            self.markdown_generators = markdown_generators

        def generate_document(self, doc_type, title, data, output_format):
            return FakeTemplateResult()

    def fake_create_package_document_version(**kwargs):
        assert kwargs["package_id"] == "PKG-2026-0001"
        assert kwargs["doc_type"] == "sow"
        return DocumentResult(
            success=True,
            document_id="doc-123",
            package_id=kwargs["package_id"],
            doc_type=kwargs["doc_type"],
            version=1,
            status="draft",
            s3_key="eagle/test-tenant/packages/PKG-2026-0001/sow/v1/Statement-of-Work.md",
        )

    monkeypatch.setattr("app.template_service.TemplateService", FakeTemplateService)
    monkeypatch.setattr(
        "app.document_service.create_package_document_version",
        fake_create_package_document_version,
    )

    mock_s3 = mock.MagicMock()
    monkeypatch.setattr("app.agentic_service._get_s3", lambda: mock_s3)

    result = _exec_create_document(
        {
            "doc_type": "sow",
            "title": "Statement of Work",
            "package_id": "PKG-2026-0001",
        },
        tenant_id="test-tenant",
        session_id="test-tenant#advanced#test-user#sess-123",
    )

    assert result["mode"] == "package"
    assert result["package_id"] == "PKG-2026-0001"
    assert result["document_id"] == "doc-123"
    assert result["version"] == 1
    assert result["s3_key"].startswith("eagle/test-tenant/packages/PKG-2026-0001/")
    mock_s3.put_object.assert_not_called()


def test_stream_generator_passes_package_context_to_sdk(monkeypatch):
    """Streaming route should pass resolved package_context to sdk_query_streaming."""
    from app.streaming_routes import stream_generator

    captured = {}

    async def fake_sdk_query_streaming(**kwargs):
        captured.update(kwargs)
        yield {"type": "complete", "text": "ok", "tools_called": [], "usage": {}}

    monkeypatch.setattr("app.streaming_routes.sdk_query_streaming", fake_sdk_query_streaming)

    package_context = {
        "mode": "package",
        "package_id": "PKG-2026-0001",
    }

    async def _collect():
        events = []
        async for raw in stream_generator(
            message="Create SOW",
            tenant_id="test-tenant",
            user_id="test-user",
            tier="advanced",
            subscription_service=None,
            session_id="sess-123",
            messages=[],
            package_context=package_context,
        ):
            if raw.startswith("data: "):
                events.append(json.loads(raw[6:]))
        return events

    events = asyncio.run(_collect())

    assert any(evt.get("type") == "complete" for evt in events)
    assert captured.get("package_context") == package_context


def test_fast_path_detects_direct_document_request():
    from app.strands_agentic_service import _should_use_fast_document_path

    should_fast_path, doc_type = _should_use_fast_document_path(
        "Generate a Statement of Work for an IT services contract."
    )
    assert should_fast_path is True
    assert doc_type == "sow"


def test_fast_path_skips_research_heavy_prompt():
    from app.strands_agentic_service import _should_use_fast_document_path

    should_fast_path, doc_type = _should_use_fast_document_path(
        "Research FAR requirements and then draft a Statement of Work."
    )
    assert should_fast_path is False
    assert doc_type is None


def test_fast_path_detects_multiline_document_prompt():
    from app.strands_agentic_service import _should_use_fast_document_path

    should_fast_path, doc_type = _should_use_fast_document_path(
        "Generate a\n\nStatement of Work for IT services."
    )
    assert should_fast_path is True
    assert doc_type == "sow"


def test_force_document_creation_for_direct_request_without_tool(monkeypatch):
    from app.strands_agentic_service import _ensure_create_document_for_direct_request

    def fake_exec_create_document(params, tenant_id, session_id):
        assert params["doc_type"] == "sow"
        return {
            "mode": "workspace",
            "document_type": "sow",
            "title": "Statement of Work",
            "status": "saved",
            "s3_key": "eagle/test-tenant/test-user/documents/sow_20260306_120000.md",
            "word_count": 1200,
        }

    monkeypatch.setattr("app.agentic_service._exec_create_document", fake_exec_create_document)

    forced = asyncio.run(
        _ensure_create_document_for_direct_request(
            prompt="Research FAR requirements and then draft a Statement of Work.",
            tenant_id="test-tenant",
            user_id="test-user",
            session_id="sess-123",
            package_context=None,
            tools_called=["knowledge_search", "knowledge_fetch"],
        )
    )
    assert forced is not None
    assert forced["doc_type"] == "sow"


def test_force_document_creation_skips_when_tool_already_called(monkeypatch):
    from app.strands_agentic_service import _ensure_create_document_for_direct_request

    called = {"count": 0}

    def fake_exec_create_document(params, tenant_id, session_id):
        called["count"] += 1
        return {"status": "saved"}

    monkeypatch.setattr("app.agentic_service._exec_create_document", fake_exec_create_document)

    forced = asyncio.run(
        _ensure_create_document_for_direct_request(
            prompt="Generate a Statement of Work for IT services.",
            tenant_id="test-tenant",
            user_id="test-user",
            session_id="sess-123",
            package_context=None,
            tools_called=["create_document"],
        )
    )
    assert forced is None
    assert called["count"] == 0


def test_forced_document_creation_carries_document_context(monkeypatch):
    from app.strands_agentic_service import _ensure_create_document_for_direct_request

    captured = {}

    def fake_exec_create_document(params, tenant_id, session_id):
        captured["params"] = params
        return {
            "mode": "workspace",
            "document_type": "sow",
            "title": params.get("title", ""),
            "status": "saved",
            "s3_key": "eagle/test-tenant/test-user/documents/sow_20260310_000000.md",
            "word_count": 200,
        }

    monkeypatch.setattr("app.agentic_service._exec_create_document", fake_exec_create_document)

    prompt = (
        "You are assisting with edits to an acquisition document in EAGLE.\n\n"
        "[DOCUMENT CONTEXT]\n\n"
        "Title: Statement of Work\n\n"
        "Type: sow\n\n"
        "Current Content Excerpt:\n"
        "## 2. SCOPE\n[To be completed]\n\n## 3. PERIOD OF PERFORMANCE\n12 months from date of award\n\n"
        "[USER REQUEST]\n\n"
        "make section 3 cleared too\n\n"
        "Instruction: If the user requests substantive edits or section completion, use create_document and return the updated draft."
    )

    forced = asyncio.run(
        _ensure_create_document_for_direct_request(
            prompt=prompt,
            tenant_id="test-tenant",
            user_id="test-user",
            session_id="sess-ctx-1",
            package_context=None,
            tools_called=[],
        )
    )

    assert forced is not None
    assert captured["params"]["title"] == "Statement of Work"
    assert captured["params"]["doc_type"] == "sow"
    assert captured["params"]["data"]["edit_request"] == "make section 3 cleared too"
    assert "## 3. PERIOD OF PERFORMANCE" in captured["params"]["data"]["current_content"]


def test_sdk_query_streaming_fast_path_emits_document_events(monkeypatch):
    from app.strands_agentic_service import sdk_query_streaming

    def fake_exec_create_document(params, tenant_id, session_id):
        assert params["doc_type"] == "sow"
        return {
            "mode": "workspace",
            "document_type": "sow",
            "title": "Statement of Work",
            "status": "saved",
            "s3_key": "eagle/test-tenant/test-user/documents/sow_20260306_120000.md",
            "word_count": 1200,
        }

    monkeypatch.setattr("app.agentic_service._exec_create_document", fake_exec_create_document)

    async def _collect():
        chunks = []
        async for chunk in sdk_query_streaming(
            prompt="Generate a Statement of Work for IT services at NCI.",
            tenant_id="test-tenant",
            user_id="test-user",
            tier="advanced",
            session_id="sess-123",
        ):
            chunks.append(chunk)
        return chunks

    chunks = asyncio.run(_collect())
    types = [c.get("type") for c in chunks]
    assert "tool_use" in types
    assert "tool_result" in types
    assert "complete" in types


def test_extract_document_context_from_prompt():
    from app.strands_agentic_service import _extract_document_context_from_prompt

    prompt = (
        "You are assisting with edits to an acquisition document in EAGLE.\n\n"
        "[DOCUMENT CONTEXT]\n\n"
        "Title: Statement of Work\n\n"
        "Type: sow\n\n"
        "Current Content Excerpt:\n"
        "## 1. BACKGROUND\n...\n## 2. SCOPE\nOriginal scope text.\n\n"
        "[ORIGIN SESSION CONTEXT]\n\n"
        "prior chat\n\n"
        "[USER REQUEST]\n\n"
        "change the scope. leave it blank\n\n"
        "Instruction: If the user requests substantive edits or section completion, "
        "use create_document and return the updated draft."
    )

    parsed = _extract_document_context_from_prompt(prompt)
    assert parsed["title"] == "Statement of Work"
    assert parsed["document_type"] == "sow"
    assert "## 2. SCOPE" in parsed["current_content"]
    assert parsed["user_request"] == "change the scope. leave it blank"


def test_make_service_tool_infers_doc_context_for_create_document(monkeypatch):
    import app.agentic_service as agentic_service
    from app.strands_agentic_service import _make_service_tool

    captured = {}

    def fake_create_document(params, tenant_id, session_id):
        captured["params"] = params
        captured["tenant_id"] = tenant_id
        captured["session_id"] = session_id
        return {"status": "saved", "document_type": "sow", "title": params.get("title", "")}

    monkeypatch.setitem(agentic_service.TOOL_DISPATCH, "create_document", fake_create_document)

    prompt = (
        "[DOCUMENT CONTEXT]\n\n"
        "Title: Statement of Work\n\n"
        "Type: sow\n\n"
        "Current Content Excerpt:\n"
        "## 2. SCOPE\nOriginal scope text.\n\n"
        "[USER REQUEST]\n\n"
        "change the scope. leave it blank\n\n"
        "Instruction: If the user requests substantive edits or section completion, "
        "use create_document and return the updated draft."
    )

    tool_fn = _make_service_tool(
        tool_name="create_document",
        description="test",
        tenant_id="test-tenant",
        user_id="test-user",
        session_id="sess-321",
        package_context=None,
        result_queue=None,
        loop=None,
        prompt_context=prompt,
    )

    tool_fn("{}")

    assert captured["tenant_id"] == "test-tenant"
    assert captured["params"]["doc_type"] == "sow"
    assert captured["params"]["title"] == "Statement of Work"
    assert captured["params"]["data"]["edit_request"] == "change the scope. leave it blank"
    assert "## 2. SCOPE" in captured["params"]["data"]["current_content"]
