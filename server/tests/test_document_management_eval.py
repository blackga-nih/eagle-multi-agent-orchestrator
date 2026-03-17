"""
Document Management E2E Evaluation — Tool Dispatch Layer.

Exercises the full document lifecycle through execute_tool():
  1. create_document → generates a DOCX artifact
  2. edit_docx_document → applies AI text edits to the DOCX
  3. document_changelog_search → queries changelog entries
  4. get_latest_document → retrieves latest version + recent changes

All tests run against mocked S3/DynamoDB (no AWS credentials needed).
Suitable for MVP1 eval Tier 1.

Also validates:
  - Input validation and error handling at the dispatch layer
  - Session ID → tenant/user extraction
  - Dataclass conversion (dict → DocxEdit/DocxCheckboxEdit)
  - Changelog entry serialization
"""

import io
import json
import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SESSION_ID = "test-tenant#advanced#test-user#sess-001"
TENANT_ID = "test-tenant"
USER_ID = "test-user"


def _build_sample_docx(paragraphs: list[tuple[str, str]] | None = None) -> bytes:
    """Build a minimal DOCX in memory."""
    from docx import Document

    doc = Document()
    if paragraphs is None:
        paragraphs = [
            ("Heading 1", "Statement of Work"),
            ("Normal", "The contractor shall provide IT services."),
            ("Heading 2", "Scope"),
            ("Normal", "This contract covers cloud hosting and maintenance."),
            ("Heading 2", "Period of Performance"),
            ("Normal", "12 months from date of award."),
        ]
    for style_name, text in paragraphs:
        doc.add_paragraph(text, style=style_name)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _build_sample_xlsx() -> bytes:
    """Build a minimal XLSX in memory."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Cost Estimate"
    ws.append(["Item", "Qty", "Unit Price", "Total"])
    ws.append(["Cloud Hosting", 12, 5000, "=B2*C2"])
    ws.append(["Maintenance", 12, 2000, "=B3*C3"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


SAMPLE_DOCX_BYTES = None  # lazily initialized


def _get_sample_docx() -> bytes:
    global SAMPLE_DOCX_BYTES
    if SAMPLE_DOCX_BYTES is None:
        SAMPLE_DOCX_BYTES = _build_sample_docx()
    return SAMPLE_DOCX_BYTES


# ---------------------------------------------------------------------------
# 1. _exec_edit_docx_document — input validation
# ---------------------------------------------------------------------------

class TestExecEditDocxDocumentValidation:
    """Validation tests for _exec_edit_docx_document via direct handler call."""

    def test_rejects_missing_edits_and_checkbox_edits(self):
        from app.tool_dispatch import _exec_edit_docx_document

        result = _exec_edit_docx_document(
            {"document_key": "eagle/t/u/documents/sow.docx"},
            TENANT_ID, SESSION_ID,
        )
        assert "error" in result

    def test_rejects_non_array_edits(self):
        from app.tool_dispatch import _exec_edit_docx_document

        result = _exec_edit_docx_document(
            {"document_key": "eagle/t/u/documents/sow.docx", "edits": "not-an-array"},
            TENANT_ID, SESSION_ID,
        )
        assert "error" in result
        assert "array" in result["error"]

    def test_rejects_edit_missing_search_text(self):
        from app.tool_dispatch import _exec_edit_docx_document

        result = _exec_edit_docx_document(
            {
                "document_key": "eagle/t/u/documents/sow.docx",
                "edits": [{"search_text": "", "replacement_text": "new"}],
            },
            TENANT_ID, SESSION_ID,
        )
        assert "error" in result
        assert "search_text" in result["error"]

    def test_rejects_non_dict_edit_entry(self):
        from app.tool_dispatch import _exec_edit_docx_document

        result = _exec_edit_docx_document(
            {
                "document_key": "eagle/t/u/documents/sow.docx",
                "edits": ["not-a-dict"],
            },
            TENANT_ID, SESSION_ID,
        )
        assert "error" in result
        assert "object" in result["error"]

    def test_rejects_checkbox_edit_without_boolean_checked(self):
        from app.tool_dispatch import _exec_edit_docx_document

        result = _exec_edit_docx_document(
            {
                "document_key": "eagle/t/u/documents/sow.docx",
                "checkbox_edits": [{"label_text": "Task", "checked": "yes"}],
            },
            TENANT_ID, SESSION_ID,
        )
        assert "error" in result
        assert "boolean" in result["error"]

    def test_rejects_checkbox_edit_missing_label(self):
        from app.tool_dispatch import _exec_edit_docx_document

        result = _exec_edit_docx_document(
            {
                "document_key": "eagle/t/u/documents/sow.docx",
                "checkbox_edits": [{"label_text": "", "checked": True}],
            },
            TENANT_ID, SESSION_ID,
        )
        assert "error" in result
        assert "label_text" in result["error"]


# ---------------------------------------------------------------------------
# 2. _exec_edit_docx_document — happy path with mocked S3
# ---------------------------------------------------------------------------

class TestExecEditDocxDocumentHappyPath:
    """Full flow: dispatch handler → service → mocked S3."""

    @patch("app.document_ai_edit_service._get_s3")
    @patch("app.document_ai_edit_service.write_document_changelog_entry")
    def test_applies_text_edit_via_dispatch(self, mock_changelog, mock_get_s3):
        from app.tool_dispatch import _exec_edit_docx_document

        docx_bytes = _get_sample_docx()
        mock_s3 = MagicMock()
        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=MagicMock(return_value=docx_bytes)),
        }
        mock_get_s3.return_value = mock_s3

        result = _exec_edit_docx_document(
            {
                "document_key": f"eagle/{TENANT_ID}/{USER_ID}/documents/sow.docx",
                "edits": [
                    {
                        "search_text": "cloud hosting and maintenance",
                        "replacement_text": "cloud infrastructure and DevOps support",
                    },
                ],
            },
            TENANT_ID, SESSION_ID,
        )

        assert result.get("success") is True
        assert result["mode"] == "workspace_docx_edit"
        assert result["edits_applied"] >= 1
        assert "cloud infrastructure" in (result.get("content") or "")
        mock_s3.put_object.assert_called_once()
        mock_changelog.assert_called_once()

    @patch("app.document_ai_edit_service._get_s3")
    @patch("app.document_ai_edit_service.write_document_changelog_entry")
    def test_returns_missing_for_unmatched_edits(self, mock_changelog, mock_get_s3):
        from app.tool_dispatch import _exec_edit_docx_document

        docx_bytes = _get_sample_docx()
        mock_s3 = MagicMock()
        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=MagicMock(return_value=docx_bytes)),
        }
        mock_get_s3.return_value = mock_s3

        result = _exec_edit_docx_document(
            {
                "document_key": f"eagle/{TENANT_ID}/{USER_ID}/documents/sow.docx",
                "edits": [
                    {"search_text": "text that does not exist anywhere", "replacement_text": "new"},
                ],
            },
            TENANT_ID, SESSION_ID,
        )

        assert "error" in result
        assert "No DOCX edits" in result["error"]

    @patch("app.document_ai_edit_service._get_s3")
    @patch("app.document_ai_edit_service.write_document_changelog_entry")
    def test_multiple_edits_applied(self, mock_changelog, mock_get_s3):
        from app.tool_dispatch import _exec_edit_docx_document

        docx_bytes = _get_sample_docx()
        mock_s3 = MagicMock()
        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=MagicMock(return_value=docx_bytes)),
        }
        mock_get_s3.return_value = mock_s3

        result = _exec_edit_docx_document(
            {
                "document_key": f"eagle/{TENANT_ID}/{USER_ID}/documents/sow.docx",
                "edits": [
                    {"search_text": "Statement of Work", "replacement_text": "SOW v2"},
                    {"search_text": "12 months", "replacement_text": "24 months"},
                ],
            },
            TENANT_ID, SESSION_ID,
        )

        assert result.get("success") is True
        assert result["edits_applied"] == 2


# ---------------------------------------------------------------------------
# 3. _exec_edit_docx_document — via execute_tool() (full dispatch path)
# ---------------------------------------------------------------------------

class TestEditDocxViaExecuteTool:
    """Tests the complete execute_tool() → _exec_edit_docx_document path."""

    @patch("app.document_ai_edit_service._get_s3")
    @patch("app.document_ai_edit_service.write_document_changelog_entry")
    def test_execute_tool_edit_docx(self, mock_changelog, mock_get_s3):
        from app.tool_dispatch import execute_tool

        docx_bytes = _get_sample_docx()
        mock_s3 = MagicMock()
        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=MagicMock(return_value=docx_bytes)),
        }
        mock_get_s3.return_value = mock_s3

        raw = execute_tool("edit_docx_document", {
            "document_key": f"eagle/{TENANT_ID}/{USER_ID}/documents/sow.docx",
            "edits": [
                {"search_text": "IT services", "replacement_text": "cloud services"},
            ],
        }, SESSION_ID)

        result = json.loads(raw)
        assert result.get("success") is True
        assert result["edits_applied"] >= 1

    def test_execute_tool_edit_docx_validation_error(self):
        from app.tool_dispatch import execute_tool

        raw = execute_tool("edit_docx_document", {
            "document_key": "eagle/t/u/documents/sow.docx",
        }, SESSION_ID)

        result = json.loads(raw)
        assert "error" in result


# ---------------------------------------------------------------------------
# 4. _exec_document_changelog_search
# ---------------------------------------------------------------------------

class TestExecDocumentChangelogSearch:
    """Tests for document_changelog_search dispatch handler."""

    def test_rejects_missing_package_id(self):
        from app.tool_dispatch import _exec_document_changelog_search

        result = _exec_document_changelog_search({}, TENANT_ID)
        assert "error" in result
        assert "package_id" in result["error"]

    @patch("app.changelog_store._get_table")
    def test_returns_entries_for_package(self, mock_get_table):
        from app.tool_dispatch import _exec_document_changelog_search

        mock_table = MagicMock()
        mock_table.query.return_value = {
            "Items": [
                {
                    "changelog_id": "cl-1",
                    "change_type": "create",
                    "change_source": "agent_tool",
                    "change_summary": "Created SOW v1",
                    "doc_type": "sow",
                    "version": 1,
                    "actor_user_id": "test-user",
                    "created_at": "2026-03-17T00:00:00Z",
                },
                {
                    "changelog_id": "cl-2",
                    "change_type": "update",
                    "change_source": "agent_tool",
                    "change_summary": "AI edited SOW scope section",
                    "doc_type": "sow",
                    "version": 2,
                    "actor_user_id": "ai-agent",
                    "created_at": "2026-03-17T01:00:00Z",
                },
            ]
        }
        mock_get_table.return_value = mock_table

        result = _exec_document_changelog_search(
            {"package_id": "PKG-001", "doc_type": "sow", "limit": 10},
            TENANT_ID,
        )

        assert result["package_id"] == "PKG-001"
        assert result["doc_type"] == "sow"
        assert result["count"] == 2
        assert result["entries"][0]["change_type"] == "create"
        assert result["entries"][1]["change_summary"] == "AI edited SOW scope section"

    @patch("app.changelog_store._get_table")
    def test_returns_empty_for_no_entries(self, mock_get_table):
        from app.tool_dispatch import _exec_document_changelog_search

        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": []}
        mock_get_table.return_value = mock_table

        result = _exec_document_changelog_search(
            {"package_id": "PKG-NEW"},
            TENANT_ID,
        )

        assert result["count"] == 0
        assert result["entries"] == []

    @patch("app.changelog_store._get_table")
    def test_via_execute_tool(self, mock_get_table):
        from app.tool_dispatch import execute_tool

        mock_table = MagicMock()
        mock_table.query.return_value = {
            "Items": [{"change_type": "create", "change_summary": "test"}]
        }
        mock_get_table.return_value = mock_table

        raw = execute_tool("document_changelog_search", {
            "package_id": "PKG-001",
        }, SESSION_ID)

        result = json.loads(raw)
        assert result["count"] == 1


# ---------------------------------------------------------------------------
# 5. _exec_get_latest_document
# ---------------------------------------------------------------------------

class TestExecGetLatestDocument:
    """Tests for get_latest_document dispatch handler."""

    def test_rejects_missing_package_id(self):
        from app.tool_dispatch import _exec_get_latest_document

        result = _exec_get_latest_document({"doc_type": "sow"}, TENANT_ID)
        assert "error" in result

    def test_rejects_missing_doc_type(self):
        from app.tool_dispatch import _exec_get_latest_document

        result = _exec_get_latest_document({"package_id": "PKG-001"}, TENANT_ID)
        assert "error" in result

    @patch("app.changelog_store._get_table")
    @patch("app.stores.document_store.get_document")
    def test_returns_document_and_changelog(self, mock_get_doc, mock_get_table):
        from app.tool_dispatch import _exec_get_latest_document

        mock_get_doc.return_value = {
            "doc_type": "sow",
            "version": 2,
            "title": "Statement of Work",
            "status": "draft",
            "created_at": "2026-03-17T01:00:00Z",
            "s3_key": "eagle/test-tenant/packages/PKG-001/sow/v2/sow_v2.docx",
        }

        mock_table = MagicMock()
        mock_table.query.return_value = {
            "Items": [
                {
                    "change_type": "update",
                    "change_summary": "AI edited scope",
                    "actor_user_id": "ai-agent",
                    "created_at": "2026-03-17T01:00:00Z",
                },
            ]
        }
        mock_get_table.return_value = mock_table

        result = _exec_get_latest_document(
            {"package_id": "PKG-001", "doc_type": "sow"},
            TENANT_ID,
        )

        assert result["document"]["doc_type"] == "sow"
        assert result["document"]["version"] == 2
        assert result["document"]["title"] == "Statement of Work"
        assert len(result["recent_changes"]) == 1
        assert result["recent_changes"][0]["change_type"] == "update"

    @patch("app.stores.document_store.get_document")
    def test_returns_error_when_no_document(self, mock_get_doc):
        from app.tool_dispatch import _exec_get_latest_document

        mock_get_doc.return_value = None

        result = _exec_get_latest_document(
            {"package_id": "PKG-EMPTY", "doc_type": "sow"},
            TENANT_ID,
        )

        assert "error" in result
        assert "No sow document" in result["error"]

    @patch("app.changelog_store._get_table")
    @patch("app.stores.document_store.get_document")
    def test_via_execute_tool(self, mock_get_doc, mock_get_table):
        from app.tool_dispatch import execute_tool

        mock_get_doc.return_value = {
            "doc_type": "igce",
            "version": 1,
            "title": "IGCE",
            "status": "draft",
            "created_at": "2026-03-17T00:00:00Z",
            "s3_key": "eagle/test-tenant/packages/PKG-001/igce/v1/igce.xlsx",
        }
        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": []}
        mock_get_table.return_value = mock_table

        raw = execute_tool("get_latest_document", {
            "package_id": "PKG-001",
            "doc_type": "igce",
        }, SESSION_ID)

        result = json.loads(raw)
        assert result["document"]["doc_type"] == "igce"
        assert result["recent_changes"] == []


# ---------------------------------------------------------------------------
# 6. Document Lifecycle — end-to-end through dispatch layer
# ---------------------------------------------------------------------------

class TestDocumentLifecycleE2E:
    """Multi-step lifecycle: generate → edit → query changelog → get latest.

    Exercises the tool dispatch layer as the supervisor agent would,
    with mocked S3/DynamoDB backends.
    """

    @patch("app.document_ai_edit_service._get_s3")
    @patch("app.document_ai_edit_service.write_document_changelog_entry")
    @patch("app.changelog_store._get_table")
    def test_workspace_document_lifecycle(self, mock_get_table, mock_write_changelog, mock_get_s3):
        """Simulate: create DOCX → AI edit → verify changelog search works."""
        from app.tool_dispatch import execute_tool

        # -- Step 1: We have a DOCX in S3 (simulating create_document output)
        docx_bytes = _get_sample_docx()
        doc_key = f"eagle/{TENANT_ID}/{USER_ID}/documents/sow_20260317_120000.docx"

        mock_s3 = MagicMock()
        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=MagicMock(return_value=docx_bytes)),
        }
        mock_get_s3.return_value = mock_s3

        # -- Step 2: AI edits the document via edit_docx_document
        raw = execute_tool("edit_docx_document", {
            "document_key": doc_key,
            "edits": [
                {"search_text": "IT services", "replacement_text": "cloud migration services"},
            ],
        }, SESSION_ID)

        edit_result = json.loads(raw)
        assert edit_result.get("success") is True, f"Edit failed: {edit_result}"
        assert edit_result["edits_applied"] >= 1
        assert edit_result["mode"] == "workspace_docx_edit"

        # Verify S3 put was called with updated bytes
        put_call = mock_s3.put_object.call_args
        assert put_call is not None
        assert put_call.kwargs["Key"] == doc_key

        # Verify changelog was written
        mock_write_changelog.assert_called_once()
        changelog_call = mock_write_changelog.call_args
        assert changelog_call.kwargs["tenant_id"] == TENANT_ID
        assert changelog_call.kwargs["document_key"] == doc_key
        assert changelog_call.kwargs["change_type"] == "update"

        # -- Step 3: Search changelog for the package
        mock_table = MagicMock()
        mock_table.query.return_value = {
            "Items": [
                {
                    "change_type": "update",
                    "change_source": "agent_tool",
                    "change_summary": "Applied 1 AI DOCX edit(s)",
                    "doc_type": "sow",
                    "version": 0,
                    "actor_user_id": USER_ID,
                    "created_at": "2026-03-17T12:00:01Z",
                },
            ]
        }
        mock_get_table.return_value = mock_table

        raw = execute_tool("document_changelog_search", {
            "package_id": "PKG-001",
            "doc_type": "sow",
        }, SESSION_ID)

        changelog_result = json.loads(raw)
        assert changelog_result["count"] == 1
        assert changelog_result["entries"][0]["change_source"] == "agent_tool"

    @patch("app.document_ai_edit_service._get_s3")
    @patch("app.document_ai_edit_service.write_document_changelog_entry")
    def test_edit_preserves_docx_structure(self, mock_write_changelog, mock_get_s3):
        """Verify the edited DOCX is still a valid document with correct content."""
        from app.tool_dispatch import execute_tool
        from app.document_ai_edit_service import extract_docx_preview_payload

        docx_bytes = _get_sample_docx()
        doc_key = f"eagle/{TENANT_ID}/{USER_ID}/documents/sow.docx"

        # Capture the bytes written to S3
        captured_bytes = {}

        mock_s3 = MagicMock()
        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=MagicMock(return_value=docx_bytes)),
        }

        def capture_put(**kwargs):
            captured_bytes["body"] = kwargs.get("Body", b"")

        mock_s3.put_object.side_effect = capture_put
        mock_get_s3.return_value = mock_s3

        raw = execute_tool("edit_docx_document", {
            "document_key": doc_key,
            "edits": [
                {"search_text": "Scope", "replacement_text": "Project Scope"},
                {"search_text": "12 months", "replacement_text": "18 months"},
            ],
        }, SESSION_ID)

        result = json.loads(raw)
        assert result.get("success") is True

        # Re-extract preview from the saved bytes
        updated_bytes = captured_bytes.get("body")
        assert updated_bytes is not None
        assert len(updated_bytes) > 0

        payload = extract_docx_preview_payload(updated_bytes)
        assert payload["preview_mode"] == "docx_blocks"
        content = payload["content"]
        assert "Project Scope" in content
        assert "18 months" in content
        assert "Scope" not in content or "Project Scope" in content


# ---------------------------------------------------------------------------
# 7. Session ID extraction tests
# ---------------------------------------------------------------------------

class TestSessionExtraction:
    """Verify tenant_id and user_id are correctly extracted from session IDs."""

    def test_composite_session_extracts_tenant(self):
        from app.tool_dispatch import _extract_tenant_id

        assert _extract_tenant_id("nci-oa#premium#co-officer#sess-1") == "nci-oa"

    def test_composite_session_extracts_user(self):
        from app.tool_dispatch import _extract_user_id

        assert _extract_user_id("nci-oa#premium#co-officer#sess-1") == "co-officer"

    def test_none_session_defaults(self):
        from app.tool_dispatch import _extract_tenant_id, _extract_user_id

        assert _extract_tenant_id(None) == "demo-tenant"
        assert _extract_user_id(None) == "demo-user"

    def test_edit_docx_uses_session_user_for_key_check(self):
        """edit_docx_document should derive user_id from session for access control."""
        from app.tool_dispatch import _exec_edit_docx_document

        # Access denied: session says user is "test-user" but key says "other-user"
        result = _exec_edit_docx_document(
            {
                "document_key": "eagle/test-tenant/other-user/documents/sow.docx",
                "edits": [{"search_text": "a", "replacement_text": "b"}],
            },
            TENANT_ID,
            "test-tenant#advanced#test-user#sess-001",
        )
        assert "error" in result
        assert "denied" in result["error"].lower()


# ---------------------------------------------------------------------------
# 8. Tool registration verification
# ---------------------------------------------------------------------------

class TestToolRegistration:
    """Verify the 3 document tools are properly registered."""

    def test_edit_docx_document_in_dispatch(self):
        from app.tool_dispatch import TOOL_DISPATCH

        assert "edit_docx_document" in TOOL_DISPATCH

    def test_document_changelog_search_in_dispatch(self):
        from app.tool_dispatch import TOOL_DISPATCH

        assert "document_changelog_search" in TOOL_DISPATCH

    def test_get_latest_document_in_dispatch(self):
        from app.tool_dispatch import TOOL_DISPATCH

        assert "get_latest_document" in TOOL_DISPATCH

    def test_edit_docx_needs_session(self):
        from app.tool_dispatch import TOOLS_NEEDING_SESSION

        assert "edit_docx_document" in TOOLS_NEEDING_SESSION

    def test_changelog_search_does_not_need_session(self):
        from app.tool_dispatch import TOOLS_NEEDING_SESSION

        assert "document_changelog_search" not in TOOLS_NEEDING_SESSION

    def test_get_latest_does_not_need_session(self):
        from app.tool_dispatch import TOOLS_NEEDING_SESSION

        assert "get_latest_document" not in TOOLS_NEEDING_SESSION

    def test_unknown_tool_returns_error(self):
        from app.tool_dispatch import execute_tool

        raw = execute_tool("nonexistent_tool", {}, SESSION_ID)
        result = json.loads(raw)
        assert "error" in result
        assert "Unknown tool" in result["error"]
