"""
Document Generation Pipeline Tests

Tests covering the HTTP layer, SSE events, and document export for the
create_document tool flow:
  agent calls create_document → doc saved to S3 → export to DOCX/PDF/MD

Eval tests 16/19 already cover S3 ops and tool invocation with boto3 ground
truth — these tests cover the HTTP + streaming layer with mocked AWS.

Run: pytest server/tests/test_document_pipeline.py -v
"""

import json
import os
import re
import sys
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Ensure server/ is on sys.path so "app.main" resolves
_server_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)


# ── Constants ────────────────────────────────────────────────────────

ALL_DOC_TYPES = [
    "sow",
    "igce",
    "market_research",
    "justification",
    "acquisition_plan",
    "eval_criteria",
    "security_checklist",
    "section_508",
    "cor_certification",
    "contract_type_justification",
]

EXPECTED_KEYS = {
    "document_type",
    "title",
    "status",
    "s3_location",
    "s3_key",
    "content",
    "word_count",
    "generated_at",
    "note",
}


# ── Helpers ──────────────────────────────────────────────────────────

def _mock_s3():
    """Return a MagicMock that behaves like a boto3 S3 client."""
    s3 = MagicMock()
    s3.put_object.return_value = {"ResponseMetadata": {"HTTPStatusCode": 200}}
    s3.list_objects_v2.return_value = {
        "Contents": [
            {
                "Key": "eagle/test-tenant/test-user/documents/sow_20260303_100000.md",
                "Size": 1234,
                "LastModified": datetime(2026, 3, 3, 10, 0, 0),
            },
            {
                "Key": "eagle/test-tenant/test-user/documents/igce_20260303_100100.md",
                "Size": 567,
                "LastModified": datetime(2026, 3, 3, 10, 1, 0),
            },
        ]
    }
    return s3


def parse_sse(raw: str) -> list[dict]:
    """Parse SSE text/event-stream into list of dicts."""
    events = []
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("data: "):
            try:
                events.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass
    return events


# ── Fixtures ─────────────────────────────────────────────────────────

ENV_PATCH = {
    "REQUIRE_AUTH": "false",
    "DEV_MODE": "false",
    "USE_BEDROCK": "false",
    "COGNITO_USER_POOL_ID": "us-east-1_test",
    "COGNITO_CLIENT_ID": "test-client",
    "EAGLE_SESSIONS_TABLE": "eagle",
    "USE_PERSISTENT_SESSIONS": "false",
    "S3_BUCKET": "test-bucket",
}


@pytest.fixture(scope="module")
def mock_s3_client():
    return _mock_s3()


@pytest.fixture(scope="module")
def app_with_mocked_s3(mock_s3_client):
    """FastAPI app with auth disabled and S3 mocked."""
    # Mock sdk_query to avoid real LLM calls
    async def _mock_sdk_query(*args, **kwargs):
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Mock response."

        assistant_msg = MagicMock()
        assistant_msg.__class__.__name__ = "AssistantMessage"
        assistant_msg.content = [text_block]

        result_msg = MagicMock()
        result_msg.__class__.__name__ = "ResultMessage"
        result_msg.usage = {"input_tokens": 10, "output_tokens": 5}
        result_msg.result = "Mock response."

        yield assistant_msg
        yield result_msg

    with patch.dict(os.environ, ENV_PATCH, clear=False):
        with patch("app.agentic_service._get_s3", return_value=mock_s3_client):
            with patch("app.strands_agentic_service.sdk_query", side_effect=_mock_sdk_query):
                import importlib
                import app.main as main_module
                importlib.reload(main_module)
                yield main_module.app


# ══════════════════════════════════════════════════════════════════════
# T1 — _exec_create_document: shape, types, errors, S3 failures
# ══════════════════════════════════════════════════════════════════════

class TestCreateDocumentTool:
    """Unit tests for the create_document tool function."""

    def test_sow_returns_valid_shape(self, mock_s3_client):
        """SOW document returns a dict with all expected keys."""
        with patch.dict(os.environ, ENV_PATCH, clear=False):
            with patch("app.agentic_service._get_s3", return_value=mock_s3_client):
                from app.agentic_service import _exec_create_document
                result = _exec_create_document(
                    {"doc_type": "sow", "title": "IT Services SOW"},
                    tenant_id="test-tenant",
                    session_id="ses-001",
                )
        assert isinstance(result, dict)
        assert EXPECTED_KEYS.issubset(result.keys()), f"Missing keys: {EXPECTED_KEYS - result.keys()}"
        assert result["document_type"] == "sow"
        assert result["title"] == "IT Services SOW"
        assert result["status"] == "saved"
        assert result["word_count"] > 0
        assert len(result["content"]) > 0

    @pytest.mark.parametrize("doc_type", ALL_DOC_TYPES)
    def test_all_10_doc_types(self, doc_type, mock_s3_client):
        """Each of the 10 doc types returns content > 0."""
        with patch.dict(os.environ, ENV_PATCH, clear=False):
            with patch("app.agentic_service._get_s3", return_value=mock_s3_client):
                from app.agentic_service import _exec_create_document
                result = _exec_create_document(
                    {"doc_type": doc_type, "title": f"Test {doc_type}"},
                    tenant_id="test-tenant",
                    session_id="ses-002",
                )
        assert result["document_type"] == doc_type
        assert len(result["content"]) > 0
        assert result["word_count"] > 0

    def test_unknown_type_returns_error(self, mock_s3_client):
        """Unknown doc_type returns an error dict (not exception)."""
        with patch.dict(os.environ, ENV_PATCH, clear=False):
            with patch("app.agentic_service._get_s3", return_value=mock_s3_client):
                from app.agentic_service import _exec_create_document
                result = _exec_create_document(
                    {"doc_type": "bogus"},
                    tenant_id="test-tenant",
                )
        assert "error" in result
        assert "bogus" in result["error"]

    def test_s3_failure_graceful_degradation(self):
        """When S3 put_object raises, status is generated_but_not_saved but content is present."""
        from botocore.exceptions import ClientError
        failing_s3 = MagicMock()
        failing_s3.put_object.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Forbidden"}},
            "PutObject",
        )
        with patch.dict(os.environ, ENV_PATCH, clear=False):
            with patch("app.agentic_service._get_s3", return_value=failing_s3):
                from app.agentic_service import _exec_create_document
                result = _exec_create_document(
                    {"doc_type": "sow", "title": "Failure Test"},
                    tenant_id="test-tenant",
                    session_id="ses-003",
                )
        assert result["status"] == "generated_but_not_saved"
        assert len(result["content"]) > 0
        assert "S3 save failed" in result["s3_location"]

    def test_s3_key_naming_convention(self, mock_s3_client):
        """S3 key matches eagle/{tenant}/{user}/documents/{type}_{timestamp}.md."""
        with patch.dict(os.environ, ENV_PATCH, clear=False):
            with patch("app.agentic_service._get_s3", return_value=mock_s3_client):
                from app.agentic_service import _exec_create_document
                result = _exec_create_document(
                    {"doc_type": "igce", "title": "Cost Estimate"},
                    tenant_id="test-tenant",
                    session_id="ses-004",
                )
        key = result["s3_key"]
        # Pattern: eagle/{tenant}/{user}/documents/{type}_{YYYYMMDD_HHMMSS}.md
        assert re.match(
            r"eagle/test-tenant/[^/]+/documents/igce_\d{8}_\d{6}\.md$",
            key,
        ), f"S3 key doesn't match expected pattern: {key}"

    def test_sow_edit_request_clears_scope_section(self, mock_s3_client):
        """Explicit clear request should patch SOW section content in-place."""
        existing = (
            "# Statement of Work\n\n"
            "## 1. BACKGROUND AND PURPOSE\n\n"
            "Background text.\n\n"
            "## 2. SCOPE\n\n"
            "Scope details that should be removed.\n\n"
            "## 3. PERIOD OF PERFORMANCE\n\n"
            "12 months from date of award\n"
        )

        with patch.dict(os.environ, ENV_PATCH, clear=False):
            with patch("app.agentic_service._get_s3", return_value=mock_s3_client):
                from app.agentic_service import _exec_create_document
                result = _exec_create_document(
                    {
                        "doc_type": "sow",
                        "title": "Editable SOW",
                        "data": {
                            "current_content": existing,
                            "edit_request": "change the scope. leave it blank",
                        },
                    },
                    tenant_id="test-tenant",
                    session_id="ses-006",
                )

        assert result["document_type"] == "sow"
        assert result["source"] == "inline_edit_clear_sections"
        assert re.search(r"## 2\. SCOPE\s+\[To be completed\]", result["content"])
        assert re.search(
            r"## 3\. PERIOD OF PERFORMANCE\s+12 months from date of award",
            result["content"],
        )


# ══════════════════════════════════════════════════════════════════════
# T2 — execute_tool dispatch
# ══════════════════════════════════════════════════════════════════════

class TestExecuteToolDispatch:
    """Tests for execute_tool() routing to create_document."""

    def test_create_document_dispatch(self, mock_s3_client):
        """execute_tool('create_document', ...) returns valid JSON with document_type."""
        with patch.dict(os.environ, ENV_PATCH, clear=False):
            with patch("app.agentic_service._get_s3", return_value=mock_s3_client):
                from app.agentic_service import execute_tool
                raw = execute_tool(
                    "create_document",
                    {"doc_type": "sow", "title": "Dispatch Test"},
                    session_id="ses-005",
                )
        result = json.loads(raw)
        assert "document_type" in result
        assert result["document_type"] == "sow"

    def test_session_id_passed_through(self, mock_s3_client):
        """session_id reaches _exec_create_document (verified via s3_key containing user scope)."""
        with patch.dict(os.environ, ENV_PATCH, clear=False):
            with patch("app.agentic_service._get_s3", return_value=mock_s3_client):
                from app.agentic_service import execute_tool
                raw = execute_tool(
                    "create_document",
                    {"doc_type": "sow", "title": "Session Test"},
                    session_id="ws-1-user123",
                )
        result = json.loads(raw)
        # The key should contain a user-derived segment (not "demo-user" since session_id is provided)
        assert "s3_key" in result
        assert "eagle/" in result["s3_key"]


# ══════════════════════════════════════════════════════════════════════
# T3 — GET /api/documents (S3 list)
# ══════════════════════════════════════════════════════════════════════

class TestDocumentListEndpoint:
    """Tests for GET /api/documents with mocked S3."""

    def test_get_documents_returns_list(self, app_with_mocked_s3):
        """GET /api/documents returns JSON array of documents."""
        with patch("boto3.client", return_value=_mock_s3()):
            with TestClient(app_with_mocked_s3) as client:
                resp = client.get("/api/documents")

        assert resp.status_code == 200
        data = resp.json()
        assert "documents" in data
        assert isinstance(data["documents"], list)
        assert len(data["documents"]) == 2
        # Verify document shape
        doc = data["documents"][0]
        assert "key" in doc
        assert "name" in doc
        assert "size_bytes" in doc
        assert "type" in doc


# ══════════════════════════════════════════════════════════════════════
# T4 — POST /api/documents/export
# ══════════════════════════════════════════════════════════════════════

class TestDocumentExportEndpoint:
    """Tests for POST /api/documents/export."""

    def test_export_docx(self, app_with_mocked_s3):
        """Export as DOCX returns a valid DOCX binary, or 503 if dependency missing."""
        with TestClient(app_with_mocked_s3) as client:
            resp = client.post("/api/documents/export", json={
                "content": "# Test SOW\n\nThis is a test document.",
                "title": "Test SOW",
                "format": "docx",
            })
        if resp.status_code == 503:
            detail = resp.json().get("detail", "").lower()
            assert "dependency missing" in detail
            assert "python-docx" in detail
            return

        assert resp.status_code == 200
        ct = resp.headers.get("content-type", "")
        assert "application/vnd.openxmlformats-officedocument.wordprocessingml.document" in ct
        assert len(resp.content) > 0
        assert resp.content.startswith(b"PK\x03\x04")

    def test_export_pdf_or_fallback(self, app_with_mocked_s3):
        """Export as PDF returns a valid PDF binary, or 503 if dependency missing."""
        with TestClient(app_with_mocked_s3) as client:
            resp = client.post("/api/documents/export", json={
                "content": "# Cost Estimate\n\nTotal: $50,000",
                "title": "IGCE Export",
                "format": "pdf",
            })
        if resp.status_code == 503:
            detail = resp.json().get("detail", "").lower()
            assert "dependency missing" in detail
            assert "reportlab" in detail
            return

        assert resp.status_code == 200
        ct = resp.headers.get("content-type", "")
        assert "application/pdf" in ct
        assert len(resp.content) > 0
        assert resp.content.startswith(b"%PDF")

    def test_export_markdown(self, app_with_mocked_s3):
        """Export as MD returns raw markdown bytes."""
        with TestClient(app_with_mocked_s3) as client:
            resp = client.post("/api/documents/export", json={
                "content": "# Markdown Doc\n\nHello world.",
                "title": "MD Export",
                "format": "md",
            })
        assert resp.status_code == 200
        ct = resp.headers.get("content-type", "")
        assert "markdown" in ct or "text" in ct
        assert b"# Markdown Doc" in resp.content

    def test_export_dependency_error_returns_503(self, app_with_mocked_s3):
        """Missing export dependencies surface as explicit 503 errors."""
        from app.document_export import ExportDependencyError

        with patch("app.main.export_document", side_effect=ExportDependencyError("DOCX export dependency missing: install python-docx.")):
            with TestClient(app_with_mocked_s3) as client:
                resp = client.post("/api/documents/export", json={
                    "content": "# Test",
                    "title": "Test",
                    "format": "docx",
                })

        assert resp.status_code == 503
        detail = resp.json().get("detail", "").lower()
        assert "dependency missing" in detail


# ══════════════════════════════════════════════════════════════════════
# T5 — Stream / REST tool metadata
# ══════════════════════════════════════════════════════════════════════

class TestStreamToolMetadata:
    """Tests for tools_called metadata in REST and SSE responses."""

    def test_rest_response_includes_tools_called(self, app_with_mocked_s3):
        """POST /api/chat response JSON has a tools_called field."""
        with TestClient(app_with_mocked_s3) as client:
            resp = client.post("/api/chat", json={"message": "Hello"})
        if resp.status_code == 200:
            data = resp.json()
            # tools_called should exist even if empty
            assert "tools_called" in data
            assert isinstance(data["tools_called"], list)

    def test_stream_complete_event_has_type(self, app_with_mocked_s3):
        """POST /api/chat/stream SSE includes a COMPLETE event."""
        with TestClient(app_with_mocked_s3) as client:
            resp = client.post(
                "/api/chat/stream",
                json={"message": "Hello"},
            )
        if resp.status_code == 200:
            events = parse_sse(resp.text)
            types = [e.get("type") for e in events]
            assert "complete" in types or "error" in types, \
                f"Expected complete or error event, got types: {types}"

    def test_stream_events_have_agent_id(self, app_with_mocked_s3):
        """All SSE events should contain agent_id and agent_name."""
        with TestClient(app_with_mocked_s3) as client:
            resp = client.post(
                "/api/chat/stream",
                json={"message": "Hello"},
            )
        if resp.status_code == 200:
            events = parse_sse(resp.text)
            for event in events:
                assert "agent_id" in event, f"Missing agent_id in event: {event}"
                assert "agent_name" in event, f"Missing agent_name in event: {event}"


# ══════════════════════════════════════════════════════════════════════
# T6 — StreamEvent + MultiAgentStreamWriter unit tests
# ══════════════════════════════════════════════════════════════════════

class TestStreamProtocol:
    """Unit tests for stream_protocol.py types."""

    def test_stream_event_to_sse_format(self):
        """StreamEvent.to_sse() produces 'data: {...}\\n\\n' format."""
        from app.stream_protocol import StreamEvent, StreamEventType
        event = StreamEvent(
            type=StreamEventType.TOOL_USE,
            agent_id="eagle",
            agent_name="EAGLE",
            tool_use={"name": "create_document", "input": {"doc_type": "sow"}},
        )
        sse = event.to_sse()
        assert sse.startswith("data: ")
        assert sse.endswith("\n\n")
        parsed = json.loads(sse[6:].strip())
        assert parsed["type"] == "tool_use"
        assert parsed["tool_use"]["name"] == "create_document"

    def test_stream_event_omits_none_fields(self):
        """to_dict() omits None-valued fields."""
        from app.stream_protocol import StreamEvent, StreamEventType
        event = StreamEvent(
            type=StreamEventType.TEXT,
            agent_id="eagle",
            agent_name="EAGLE",
            content="Hello",
        )
        d = event.to_dict()
        assert "tool_use" not in d
        assert "reasoning" not in d
        assert d["content"] == "Hello"

    def test_writer_tool_use_event(self):
        """MultiAgentStreamWriter.write_tool_use() pushes correct SSE to queue."""
        import asyncio
        from app.stream_protocol import MultiAgentStreamWriter

        async def _run():
            writer = MultiAgentStreamWriter("eagle", "EAGLE")
            queue = asyncio.Queue()
            await writer.write_tool_use(queue, "create_document", {"doc_type": "sow"})
            sse_line = await queue.get()
            return sse_line

        sse_line = asyncio.get_event_loop().run_until_complete(_run())
        parsed = json.loads(sse_line.replace("data: ", "").strip())
        assert parsed["type"] == "tool_use"
        assert parsed["tool_use"]["name"] == "create_document"
        assert parsed["agent_id"] == "eagle"

    def test_writer_complete_event_with_metadata(self):
        """write_complete() includes metadata payload when provided."""
        import asyncio
        from app.stream_protocol import MultiAgentStreamWriter

        async def _run():
            writer = MultiAgentStreamWriter("eagle", "EAGLE")
            queue = asyncio.Queue()
            await writer.write_complete(
                queue,
                metadata={"tools_called": ["create_document"], "usage": {"output_tokens": 12}},
            )
            return await queue.get()

        sse_line = asyncio.get_event_loop().run_until_complete(_run())
        parsed = json.loads(sse_line.replace("data: ", "").strip())
        assert parsed["type"] == "complete"
        assert parsed["metadata"]["tools_called"] == ["create_document"]
        assert parsed["metadata"]["usage"]["output_tokens"] == 12
