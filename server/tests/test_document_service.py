"""Tests for document_service.py -- Canonical document creation.

Validates:
  - create_package_document_version(): version increment, S3 upload, DynamoDB write
  - Atomicity pattern: pending -> draft status transition
  - Idempotency: duplicate content detection
  - get_document_download_url(): presigned URL generation
  - finalize_document(): status transition

All tests are fast (mocked AWS, no real calls).
"""
from datetime import datetime
from unittest import mock

import pytest
from botocore.exceptions import ClientError


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

TENANT = "test-tenant"
USER = "test-user"
SESSION = "sess-123"
PACKAGE_ID = "PKG-2026-0001"
DOC_TYPE = "sow"
TITLE = "Statement of Work"
CONTENT = "# SOW\n\nThis is the content."
FAKE_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
FAKE_NOW = datetime(2026, 3, 4, 12, 0, 0)
FAKE_ISO = FAKE_NOW.isoformat()

MOCK_PACKAGE = {
    "package_id": PACKAGE_ID,
    "title": "Test Acquisition",
    "required_documents": ["sow", "igce"],
    "completed_documents": [],
}


def _make_client_error(code="InternalServerError", msg="boom"):
    return ClientError(
        {"Error": {"Code": code, "Message": msg}},
        "PutObject",
    )


# ---------------------------------------------------------------------------
# TestCreatePackageDocumentVersion
# ---------------------------------------------------------------------------

class TestCreatePackageDocumentVersion:
    """Verify create_package_document_version orchestration."""

    def test_creates_first_version(self):
        """Creates v1 when no prior versions exist."""
        from app.document_service import create_package_document_version

        mock_table = mock.MagicMock()
        mock_s3 = mock.MagicMock()

        with mock.patch("app.document_service.get_package", return_value=MOCK_PACKAGE), \
             mock.patch("app.document_service.get_document_history", return_value=[]), \
             mock.patch("app.document_service._get_table", return_value=mock_table), \
             mock.patch("app.document_service._get_s3", return_value=mock_s3), \
             mock.patch("app.document_service.update_package"), \
             mock.patch("uuid.uuid4", return_value=FAKE_UUID), \
             mock.patch("app.document_service.datetime", wraps=datetime,
                       **{"utcnow.return_value": FAKE_NOW}):
            result = create_package_document_version(
                tenant_id=TENANT,
                package_id=PACKAGE_ID,
                doc_type=DOC_TYPE,
                content=CONTENT,
                title=TITLE,
            )

        assert result.success is True
        assert result.version == 1
        assert result.doc_type == DOC_TYPE
        assert result.package_id == PACKAGE_ID
        assert f"v1" in result.s3_key
        mock_s3.put_object.assert_called_once()

    def test_increments_version(self):
        """Creates v2 when v1 exists."""
        from app.document_service import create_package_document_version

        existing = [{"version": 1, "status": "draft", "content_hash": "different"}]

        mock_table = mock.MagicMock()
        mock_s3 = mock.MagicMock()

        with mock.patch("app.document_service.get_package", return_value=MOCK_PACKAGE), \
             mock.patch("app.document_service.get_document_history", return_value=existing), \
             mock.patch("app.document_service._get_table", return_value=mock_table), \
             mock.patch("app.document_service._get_s3", return_value=mock_s3), \
             mock.patch("app.document_service.update_package"), \
             mock.patch("uuid.uuid4", return_value=FAKE_UUID), \
             mock.patch("app.document_service.datetime", wraps=datetime,
                       **{"utcnow.return_value": FAKE_NOW}):
            result = create_package_document_version(
                tenant_id=TENANT,
                package_id=PACKAGE_ID,
                doc_type=DOC_TYPE,
                content=CONTENT,
                title=TITLE,
            )

        assert result.success is True
        assert result.version == 2
        assert f"v2" in result.s3_key

    def test_returns_error_when_package_not_found(self):
        """Returns error when package doesn't exist."""
        from app.document_service import create_package_document_version

        with mock.patch("app.document_service.get_package", return_value=None):
            result = create_package_document_version(
                tenant_id=TENANT,
                package_id="invalid-pkg",
                doc_type=DOC_TYPE,
                content=CONTENT,
                title=TITLE,
            )

        assert result.success is False
        assert "not found" in result.error

    def test_idempotency_returns_existing_on_duplicate_content(self):
        """Returns existing document when content hash matches."""
        from app.document_service import create_package_document_version
        import hashlib

        content_hash = hashlib.sha256(CONTENT.encode()).hexdigest()
        existing = [{
            "version": 1,
            "status": "draft",
            "content_hash": content_hash,
            "document_id": "existing-doc-id",
            "s3_key": "existing/key",
            "s3_bucket": "bucket",
            "title": TITLE,
            "created_at": FAKE_ISO,
        }]

        with mock.patch("app.document_service.get_package", return_value=MOCK_PACKAGE), \
             mock.patch("app.document_service.get_document_history", return_value=existing):
            result = create_package_document_version(
                tenant_id=TENANT,
                package_id=PACKAGE_ID,
                doc_type=DOC_TYPE,
                content=CONTENT,
                title=TITLE,
            )

        assert result.success is True
        assert result.version == 1
        assert result.document_id == "existing-doc-id"

    def test_s3_failure_marks_document_as_failed(self):
        """Sets status to failed when S3 upload fails."""
        from app.document_service import create_package_document_version

        mock_table = mock.MagicMock()
        mock_s3 = mock.MagicMock()
        mock_s3.put_object.side_effect = _make_client_error()

        with mock.patch("app.document_service.get_package", return_value=MOCK_PACKAGE), \
             mock.patch("app.document_service.get_document_history", return_value=[]), \
             mock.patch("app.document_service._get_table", return_value=mock_table), \
             mock.patch("app.document_service._get_s3", return_value=mock_s3), \
             mock.patch("uuid.uuid4", return_value=FAKE_UUID), \
             mock.patch("app.document_service.datetime", wraps=datetime,
                       **{"utcnow.return_value": FAKE_NOW}):
            result = create_package_document_version(
                tenant_id=TENANT,
                package_id=PACKAGE_ID,
                doc_type=DOC_TYPE,
                content=CONTENT,
                title=TITLE,
            )

        assert result.success is False
        assert "S3 upload failed" in result.error

        # Verify status was updated to failed
        update_calls = [c for c in mock_table.update_item.call_args_list]
        assert len(update_calls) >= 1

    def test_supersedes_prior_versions(self):
        """Marks prior versions as superseded."""
        from app.document_service import create_package_document_version

        existing = [
            {"version": 1, "status": "draft", "content_hash": "hash1"},
            {"version": 2, "status": "draft", "content_hash": "hash2"},
        ]

        mock_table = mock.MagicMock()
        mock_s3 = mock.MagicMock()

        with mock.patch("app.document_service.get_package", return_value=MOCK_PACKAGE), \
             mock.patch("app.document_service.get_document_history", return_value=existing), \
             mock.patch("app.document_service._get_table", return_value=mock_table), \
             mock.patch("app.document_service._get_s3", return_value=mock_s3), \
             mock.patch("app.document_service.update_package"), \
             mock.patch("uuid.uuid4", return_value=FAKE_UUID), \
             mock.patch("app.document_service.datetime", wraps=datetime,
                       **{"utcnow.return_value": FAKE_NOW}):
            result = create_package_document_version(
                tenant_id=TENANT,
                package_id=PACKAGE_ID,
                doc_type=DOC_TYPE,
                content=CONTENT,
                title=TITLE,
            )

        assert result.success is True
        assert result.version == 3

        # Verify supersession updates were called
        update_calls = mock_table.update_item.call_args_list
        # Should have: pending->draft update + 2 supersession updates
        assert len(update_calls) >= 2

    def test_updates_package_checklist(self):
        """Updates package completed_documents when doc is required."""
        from app.document_service import create_package_document_version

        mock_table = mock.MagicMock()
        mock_s3 = mock.MagicMock()

        with mock.patch("app.document_service.get_package", return_value=MOCK_PACKAGE), \
             mock.patch("app.document_service.get_document_history", return_value=[]), \
             mock.patch("app.document_service._get_table", return_value=mock_table), \
             mock.patch("app.document_service._get_s3", return_value=mock_s3), \
             mock.patch("app.document_service.update_package") as mock_update, \
             mock.patch("uuid.uuid4", return_value=FAKE_UUID), \
             mock.patch("app.document_service.datetime", wraps=datetime,
                       **{"utcnow.return_value": FAKE_NOW}):
            result = create_package_document_version(
                tenant_id=TENANT,
                package_id=PACKAGE_ID,
                doc_type=DOC_TYPE,  # sow is in required_documents
                content=CONTENT,
                title=TITLE,
            )

        assert result.success is True
        mock_update.assert_called_once()
        call_args = mock_update.call_args[0]
        assert call_args[0] == TENANT
        assert call_args[1] == PACKAGE_ID
        assert "sow" in call_args[2]["completed_documents"]

    def test_s3_key_format(self):
        """Verifies S3 key follows canonical format."""
        from app.document_service import create_package_document_version

        mock_table = mock.MagicMock()
        mock_s3 = mock.MagicMock()

        with mock.patch("app.document_service.get_package", return_value=MOCK_PACKAGE), \
             mock.patch("app.document_service.get_document_history", return_value=[]), \
             mock.patch("app.document_service._get_table", return_value=mock_table), \
             mock.patch("app.document_service._get_s3", return_value=mock_s3), \
             mock.patch("app.document_service.update_package"), \
             mock.patch("uuid.uuid4", return_value=FAKE_UUID), \
             mock.patch("app.document_service.datetime", wraps=datetime,
                       **{"utcnow.return_value": FAKE_NOW}):
            result = create_package_document_version(
                tenant_id=TENANT,
                package_id=PACKAGE_ID,
                doc_type=DOC_TYPE,
                content=CONTENT,
                title=TITLE,
                file_type="docx",
            )

        # Format: eagle/{tenant}/packages/{package}/{doc_type}/v{version}/{artifact}.{ext}
        expected_prefix = f"eagle/{TENANT}/packages/{PACKAGE_ID}/{DOC_TYPE}/v1/"
        assert result.s3_key.startswith(expected_prefix)
        assert result.s3_key.endswith(".docx")


# ---------------------------------------------------------------------------
# TestGetDocumentDownloadUrl
# ---------------------------------------------------------------------------

class TestGetDocumentDownloadUrl:
    """Verify get_document_download_url presigned URL generation."""

    def test_generates_presigned_url(self):
        """Generates presigned URL for document."""
        from app.document_service import get_document_download_url

        mock_doc = {
            "s3_key": "eagle/tenant/packages/pkg/sow/v1/doc.md",
            "s3_bucket": "test-bucket",
        }
        mock_s3 = mock.MagicMock()
        mock_s3.generate_presigned_url.return_value = "https://presigned-url"

        with mock.patch("app.document_service.get_document", return_value=mock_doc), \
             mock.patch("app.document_service._get_s3", return_value=mock_s3):
            url = get_document_download_url(TENANT, PACKAGE_ID, DOC_TYPE)

        assert url == "https://presigned-url"
        mock_s3.generate_presigned_url.assert_called_once()

    def test_returns_none_when_document_not_found(self):
        """Returns None when document doesn't exist."""
        from app.document_service import get_document_download_url

        with mock.patch("app.document_service.get_document", return_value=None):
            url = get_document_download_url(TENANT, PACKAGE_ID, DOC_TYPE)

        assert url is None

    def test_returns_none_for_legacy_document_without_s3_key(self):
        """Returns None for legacy docs without s3_key."""
        from app.document_service import get_document_download_url

        mock_doc = {"content": "inline content", "version": 1}

        with mock.patch("app.document_service.get_document", return_value=mock_doc):
            url = get_document_download_url(TENANT, PACKAGE_ID, DOC_TYPE)

        assert url is None


# ---------------------------------------------------------------------------
# TestFinalizeDocument
# ---------------------------------------------------------------------------

class TestFinalizeDocument:
    """Verify finalize_document delegates to store."""

    def test_delegates_to_store(self):
        """Calls store finalize_document."""
        from app.document_service import finalize_document

        with mock.patch("app.document_service.store_finalize_document") as mock_finalize:
            mock_finalize.return_value = {"status": "final"}
            result = finalize_document(TENANT, PACKAGE_ID, DOC_TYPE, 1)

        mock_finalize.assert_called_once_with(TENANT, PACKAGE_ID, DOC_TYPE, 1)
        assert result["status"] == "final"


# ---------------------------------------------------------------------------
# TestDocumentResult
# ---------------------------------------------------------------------------

class TestDocumentResult:
    """Verify DocumentResult dataclass."""

    def test_to_dict_excludes_none_values(self):
        from app.document_service import DocumentResult

        result = DocumentResult(
            success=True,
            document_id="doc-123",
            version=1,
            error=None,  # Should be excluded
        )
        d = result.to_dict()

        assert d["success"] is True
        assert d["document_id"] == "doc-123"
        assert d["version"] == 1
        assert "error" not in d

    def test_to_dict_includes_error_when_present(self):
        from app.document_service import DocumentResult

        result = DocumentResult(
            success=False,
            error="Something went wrong",
        )
        d = result.to_dict()

        assert d["success"] is False
        assert d["error"] == "Something went wrong"


# ---------------------------------------------------------------------------
# TestSanitizeFilename
# ---------------------------------------------------------------------------

class TestSanitizeFilename:
    """Verify _sanitize_filename helper."""

    def test_replaces_spaces_with_hyphens(self):
        from app.document_service import _sanitize_filename

        result = _sanitize_filename("Statement of Work")
        assert result == "Statement-of-Work"

    def test_removes_special_characters(self):
        from app.document_service import _sanitize_filename

        result = _sanitize_filename("SOW (v2) - Final!")
        assert "(" not in result
        assert ")" not in result
        assert "!" not in result

    def test_limits_length(self):
        from app.document_service import _sanitize_filename

        long_name = "A" * 100
        result = _sanitize_filename(long_name)
        assert len(result) <= 50
