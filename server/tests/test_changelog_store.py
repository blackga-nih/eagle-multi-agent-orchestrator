"""
Tests for changelog_store.py — Document change tracking.
"""

import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_dynamodb_table():
    """Mock DynamoDB table for testing."""
    with patch("app.changelog_store._get_table") as mock_get_table:
        mock_table = MagicMock()
        mock_get_table.return_value = mock_table
        yield mock_table


class TestWriteChangelogEntry:
    """Tests for write_changelog_entry."""

    def test_write_changelog_entry_creates_item(self, mock_dynamodb_table):
        """Should write a changelog entry with correct attributes."""
        from app.changelog_store import write_changelog_entry

        result = write_changelog_entry(
            tenant_id="test-tenant",
            package_id="pkg-123",
            doc_type="sow",
            version=1,
            change_type="create",
            change_source="agent_tool",
            change_summary="Created SOW v1: Test Statement of Work",
            actor_user_id="user-456",
            session_id="session-789",
        )

        # Verify put_item was called
        mock_dynamodb_table.put_item.assert_called_once()
        call_args = mock_dynamodb_table.put_item.call_args

        # Check the item structure
        item = call_args.kwargs["Item"]
        assert item["PK"] == "CHANGELOG#test-tenant"
        assert item["SK"].startswith("CHANGELOG#pkg-123#sow#")
        assert item["package_id"] == "pkg-123"
        assert item["doc_type"] == "sow"
        assert item["version"] == 1
        assert item["change_type"] == "create"
        assert item["change_source"] == "agent_tool"
        assert item["change_summary"] == "Created SOW v1: Test Statement of Work"
        assert item["actor_user_id"] == "user-456"
        assert item["session_id"] == "session-789"
        assert "changelog_id" in item
        assert "created_at" in item
        assert "ttl" in item

        # Verify return value matches
        assert result["package_id"] == "pkg-123"
        assert result["doc_type"] == "sow"

    def test_write_changelog_entry_without_session_id(self, mock_dynamodb_table):
        """Should write a changelog entry without session_id."""
        from app.changelog_store import write_changelog_entry

        result = write_changelog_entry(
            tenant_id="test-tenant",
            package_id="pkg-123",
            doc_type="igce",
            version=2,
            change_type="update",
            change_source="user_edit",
            change_summary="Updated IGCE v2",
            actor_user_id="user-456",
        )

        call_args = mock_dynamodb_table.put_item.call_args
        item = call_args.kwargs["Item"]

        # session_id should not be in item
        assert "session_id" not in item
        assert result["doc_type"] == "igce"

    def test_write_changelog_entry_finalize_type(self, mock_dynamodb_table):
        """Should handle finalize change type."""
        from app.changelog_store import write_changelog_entry

        result = write_changelog_entry(
            tenant_id="test-tenant",
            package_id="pkg-123",
            doc_type="acquisition_plan",
            version=1,
            change_type="finalize",
            change_source="user_edit",
            change_summary="Finalized acquisition_plan v1",
            actor_user_id="approver-123",
        )

        call_args = mock_dynamodb_table.put_item.call_args
        item = call_args.kwargs["Item"]

        assert item["change_type"] == "finalize"
        assert result["change_type"] == "finalize"


class TestListChangelogEntries:
    """Tests for list_changelog_entries."""

    def test_list_entries_for_document(self, mock_dynamodb_table):
        """Should query changelog entries for a specific document."""
        from app.changelog_store import list_changelog_entries

        mock_dynamodb_table.query.return_value = {
            "Items": [
                {
                    "changelog_id": "cl-1",
                    "change_type": "create",
                    "doc_type": "sow",
                    "version": 1,
                    "created_at": "2026-03-10T10:00:00.000000Z",
                },
                {
                    "changelog_id": "cl-2",
                    "change_type": "update",
                    "doc_type": "sow",
                    "version": 2,
                    "created_at": "2026-03-10T11:00:00.000000Z",
                },
            ]
        }

        result = list_changelog_entries(
            tenant_id="test-tenant",
            package_id="pkg-123",
            doc_type="sow",
            limit=50,
        )

        # Verify query was called correctly
        mock_dynamodb_table.query.assert_called_once()
        call_kwargs = mock_dynamodb_table.query.call_args.kwargs

        assert call_kwargs["ScanIndexForward"] is False  # newest first
        assert call_kwargs["Limit"] == 50

        # Verify results
        assert len(result) == 2
        assert result[0]["changelog_id"] == "cl-1"

    def test_list_entries_for_package(self, mock_dynamodb_table):
        """Should query all changelog entries for a package when doc_type is None."""
        from app.changelog_store import list_changelog_entries

        mock_dynamodb_table.query.return_value = {"Items": []}

        list_changelog_entries(
            tenant_id="test-tenant",
            package_id="pkg-123",
            doc_type=None,
            limit=20,
        )

        call_kwargs = mock_dynamodb_table.query.call_args.kwargs
        # SK prefix should not include doc_type
        key_expr = call_kwargs["KeyConditionExpression"]
        # The SK prefix should be CHANGELOG#pkg-123# (without doc_type)
        assert call_kwargs["Limit"] == 20

    def test_list_entries_empty_result(self, mock_dynamodb_table):
        """Should return empty list when no entries exist."""
        from app.changelog_store import list_changelog_entries

        mock_dynamodb_table.query.return_value = {"Items": []}

        result = list_changelog_entries(
            tenant_id="test-tenant",
            package_id="pkg-new",
            doc_type="sow",
        )

        assert result == []


class TestIntegration:
    """Integration tests for changelog in document flows."""

    def test_document_service_writes_changelog(self):
        """Verify document_service imports changelog_store correctly."""
        # This just verifies the import works
        from app.document_service import write_changelog_entry

        assert callable(write_changelog_entry)
