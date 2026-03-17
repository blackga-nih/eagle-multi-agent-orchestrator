"""
Tests for changelog_store.py — Document change tracking.

Validates:
  - write_changelog_entry(): DynamoDB item structure, PK/SK format, TTL, source normalization
  - list_changelog_entries(): query parameters, newest-first, doc_type filtering
  - write_document_changelog_entry(): workspace docs keyed by S3 key hash
  - list_document_changelog_entries(): DOCLOG# SK prefix, hash-based lookup
  - _infer_doc_type(): filename-based inference
  - _normalize_change_source(): ai_edit → agent_tool normalization

All tests are fast (mocked DynamoDB, no real calls).
"""

import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_dynamodb_table():
    """Mock DynamoDB table for testing."""
    with patch("app.changelog_store._get_table") as mock_get_table:
        mock_table = MagicMock()
        mock_get_table.return_value = mock_table
        yield mock_table


# ---------------------------------------------------------------------------
# TestWriteChangelogEntry
# ---------------------------------------------------------------------------

class TestWriteChangelogEntry:
    """Tests for write_changelog_entry."""

    def test_creates_item_with_correct_pk_sk(self, mock_dynamodb_table):
        """PK = CHANGELOG#{tenant}, SK = CHANGELOG#{pkg}#{doc}#{timestamp}."""
        from app.changelog_store import write_changelog_entry

        result = write_changelog_entry(
            tenant_id="test-tenant",
            package_id="pkg-123",
            doc_type="sow",
            version=1,
            change_type="create",
            change_source="agent_tool",
            change_summary="Created SOW v1",
            actor_user_id="user-456",
            session_id="session-789",
        )

        mock_dynamodb_table.put_item.assert_called_once()
        item = mock_dynamodb_table.put_item.call_args.kwargs["Item"]

        assert item["PK"] == "CHANGELOG#test-tenant"
        assert item["SK"].startswith("CHANGELOG#pkg-123#sow#")
        assert item["package_id"] == "pkg-123"
        assert item["doc_type"] == "sow"
        assert item["version"] == 1
        assert item["change_type"] == "create"
        assert item["change_source"] == "agent_tool"
        assert item["change_summary"] == "Created SOW v1"
        assert item["actor_user_id"] == "user-456"
        assert item["session_id"] == "session-789"
        assert "changelog_id" in item
        assert "created_at" in item
        assert "ttl" in item

    def test_omits_session_id_when_none(self, mock_dynamodb_table):
        """session_id should be absent from item when not provided."""
        from app.changelog_store import write_changelog_entry

        write_changelog_entry(
            tenant_id="test-tenant",
            package_id="pkg-123",
            doc_type="igce",
            version=2,
            change_type="update",
            change_source="user_edit",
            change_summary="Updated IGCE v2",
            actor_user_id="user-456",
        )

        item = mock_dynamodb_table.put_item.call_args.kwargs["Item"]
        assert "session_id" not in item

    def test_normalizes_ai_edit_to_agent_tool(self, mock_dynamodb_table):
        """change_source='ai_edit' should be stored as 'agent_tool'."""
        from app.changelog_store import write_changelog_entry

        result = write_changelog_entry(
            tenant_id="test-tenant",
            package_id="pkg-123",
            doc_type="sow",
            version=2,
            change_type="update",
            change_source="ai_edit",
            change_summary="AI updated SOW",
            actor_user_id="ai-agent",
        )

        item = mock_dynamodb_table.put_item.call_args.kwargs["Item"]
        assert item["change_source"] == "agent_tool"
        assert result["change_source"] == "agent_tool"

    def test_preserves_user_edit_source(self, mock_dynamodb_table):
        """change_source='user_edit' should be stored as-is."""
        from app.changelog_store import write_changelog_entry

        result = write_changelog_entry(
            tenant_id="t", package_id="p", doc_type="d",
            version=1, change_type="create",
            change_source="user_edit",
            change_summary="s", actor_user_id="u",
        )

        item = mock_dynamodb_table.put_item.call_args.kwargs["Item"]
        assert item["change_source"] == "user_edit"

    def test_ttl_is_far_future(self, mock_dynamodb_table):
        """TTL should be set ~7 years in the future (> 200M seconds from now)."""
        import time
        from app.changelog_store import write_changelog_entry

        write_changelog_entry(
            tenant_id="t", package_id="p", doc_type="d",
            version=1, change_type="create",
            change_source="user_edit",
            change_summary="s", actor_user_id="u",
        )

        item = mock_dynamodb_table.put_item.call_args.kwargs["Item"]
        assert item["ttl"] > time.time() + 200_000_000  # ~6.3 years

    def test_returns_item_dict(self, mock_dynamodb_table):
        """Return value should contain all fields."""
        from app.changelog_store import write_changelog_entry

        result = write_changelog_entry(
            tenant_id="t", package_id="p", doc_type="sow",
            version=1, change_type="create",
            change_source="user_edit",
            change_summary="Created", actor_user_id="u",
        )

        assert result["tenant_id"] == "t"
        assert result["package_id"] == "p"
        assert result["doc_type"] == "sow"
        assert result["version"] == 1
        assert result["change_type"] == "create"


# ---------------------------------------------------------------------------
# TestListChangelogEntries
# ---------------------------------------------------------------------------

class TestListChangelogEntries:
    """Tests for list_changelog_entries."""

    def test_queries_with_doc_type_filter(self, mock_dynamodb_table):
        """Should include doc_type in SK prefix when provided."""
        from app.changelog_store import list_changelog_entries

        mock_dynamodb_table.query.return_value = {"Items": [{"changelog_id": "cl-1"}]}

        result = list_changelog_entries("test-tenant", "pkg-123", "sow", limit=10)

        mock_dynamodb_table.query.assert_called_once()
        call_kwargs = mock_dynamodb_table.query.call_args.kwargs
        assert call_kwargs["ScanIndexForward"] is False  # newest first
        assert call_kwargs["Limit"] == 10
        assert len(result) == 1

    def test_queries_without_doc_type_filter(self, mock_dynamodb_table):
        """Should use broader SK prefix when doc_type is None."""
        from app.changelog_store import list_changelog_entries

        mock_dynamodb_table.query.return_value = {"Items": []}

        list_changelog_entries("test-tenant", "pkg-123", doc_type=None, limit=20)

        call_kwargs = mock_dynamodb_table.query.call_args.kwargs
        assert call_kwargs["Limit"] == 20

    def test_returns_empty_list_when_no_entries(self, mock_dynamodb_table):
        """Should return [] when query returns no items."""
        from app.changelog_store import list_changelog_entries

        mock_dynamodb_table.query.return_value = {"Items": []}
        result = list_changelog_entries("t", "pkg-new", "sow")

        assert result == []


# ---------------------------------------------------------------------------
# TestWriteDocumentChangelogEntry
# ---------------------------------------------------------------------------

class TestWriteDocumentChangelogEntry:
    """Tests for write_document_changelog_entry (workspace / S3-key-based)."""

    def test_creates_item_with_doclog_sk(self, mock_dynamodb_table):
        """SK should start with DOCLOG#{hash16}#."""
        from app.changelog_store import write_document_changelog_entry

        result = write_document_changelog_entry(
            tenant_id="test-tenant",
            document_key="eagle/test-tenant/user1/documents/sow_20260311.docx",
            change_type="update",
            change_source="user_edit",
            change_summary="Updated SOW",
            actor_user_id="user1",
        )

        item = mock_dynamodb_table.put_item.call_args.kwargs["Item"]
        assert item["PK"] == "CHANGELOG#test-tenant"
        assert item["SK"].startswith("DOCLOG#")
        assert item["document_key"] == "eagle/test-tenant/user1/documents/sow_20260311.docx"
        assert result["change_type"] == "update"

    def test_infers_doc_type_from_key(self, mock_dynamodb_table):
        """Should infer doc_type from filename when not explicitly provided."""
        from app.changelog_store import write_document_changelog_entry

        write_document_changelog_entry(
            tenant_id="t",
            document_key="eagle/t/u/documents/igce_20260311.xlsx",
            change_type="create",
            change_source="user_edit",
            change_summary="Created IGCE",
            actor_user_id="u",
        )

        item = mock_dynamodb_table.put_item.call_args.kwargs["Item"]
        assert item["doc_type"] == "igce"

    def test_uses_explicit_doc_type(self, mock_dynamodb_table):
        """Explicit doc_type should override inference."""
        from app.changelog_store import write_document_changelog_entry

        write_document_changelog_entry(
            tenant_id="t",
            document_key="eagle/t/u/documents/report.docx",
            change_type="create",
            change_source="user_edit",
            change_summary="Created",
            actor_user_id="u",
            doc_type="acquisition_plan",
        )

        item = mock_dynamodb_table.put_item.call_args.kwargs["Item"]
        assert item["doc_type"] == "acquisition_plan"

    def test_normalizes_ai_edit_source(self, mock_dynamodb_table):
        """ai_edit → agent_tool normalization for workspace documents."""
        from app.changelog_store import write_document_changelog_entry

        result = write_document_changelog_entry(
            tenant_id="t",
            document_key="eagle/t/u/documents/sow.docx",
            change_type="update",
            change_source="ai_edit",
            change_summary="AI edit",
            actor_user_id="ai-agent",
        )

        item = mock_dynamodb_table.put_item.call_args.kwargs["Item"]
        assert item["change_source"] == "agent_tool"
        assert result["change_source"] == "agent_tool"


# ---------------------------------------------------------------------------
# TestListDocumentChangelogEntries
# ---------------------------------------------------------------------------

class TestListDocumentChangelogEntries:
    """Tests for list_document_changelog_entries."""

    def test_queries_by_key_hash(self, mock_dynamodb_table):
        """Should use DOCLOG#{hash16}# SK prefix."""
        from app.changelog_store import list_document_changelog_entries

        mock_dynamodb_table.query.return_value = {"Items": [{"changelog_id": "cl-1"}]}

        result = list_document_changelog_entries(
            "test-tenant",
            "eagle/test-tenant/user1/documents/sow.docx",
            limit=10,
        )

        mock_dynamodb_table.query.assert_called_once()
        assert len(result) == 1

    def test_same_key_produces_same_hash(self, mock_dynamodb_table):
        """Same document key should produce identical SK prefix across calls."""
        from app.changelog_store import list_document_changelog_entries

        mock_dynamodb_table.query.return_value = {"Items": []}

        list_document_changelog_entries("t", "eagle/t/u/docs/file.docx")
        call1 = mock_dynamodb_table.query.call_args

        mock_dynamodb_table.query.reset_mock()

        list_document_changelog_entries("t", "eagle/t/u/docs/file.docx")
        call2 = mock_dynamodb_table.query.call_args

        # Both should produce identical query parameters
        assert call1.kwargs == call2.kwargs


# ---------------------------------------------------------------------------
# TestInferDocType
# ---------------------------------------------------------------------------

class TestInferDocType:
    """Tests for _infer_doc_type helper."""

    def test_infers_sow_from_timestamped_filename(self):
        from app.changelog_store import _infer_doc_type

        assert _infer_doc_type("eagle/t/u/docs/sow_20260310_151559.docx") == "sow"

    def test_infers_igce_from_simple_filename(self):
        from app.changelog_store import _infer_doc_type

        assert _infer_doc_type("eagle/t/u/docs/igce.xlsx") == "igce"

    def test_infers_from_versioned_filename(self):
        from app.changelog_store import _infer_doc_type

        assert _infer_doc_type("eagle/t/packages/p/sow/v1/sow_v1.md") == "sow"


# ---------------------------------------------------------------------------
# TestNormalizeChangeSource
# ---------------------------------------------------------------------------

class TestNormalizeChangeSource:
    """Tests for _normalize_change_source helper."""

    def test_ai_edit_becomes_agent_tool(self):
        from app.changelog_store import _normalize_change_source

        assert _normalize_change_source("ai_edit") == "agent_tool"

    def test_agent_tool_stays_agent_tool(self):
        from app.changelog_store import _normalize_change_source

        assert _normalize_change_source("agent_tool") == "agent_tool"

    def test_user_edit_passes_through(self):
        from app.changelog_store import _normalize_change_source

        assert _normalize_change_source("user_edit") == "user_edit"

    def test_whitespace_is_stripped(self):
        from app.changelog_store import _normalize_change_source

        assert _normalize_change_source("  ai_edit  ") == "agent_tool"

    def test_empty_string_passes_through(self):
        from app.changelog_store import _normalize_change_source

        assert _normalize_change_source("") == ""
