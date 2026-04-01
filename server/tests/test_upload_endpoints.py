"""
Tests for the upload and assign-to-package endpoints in app.main.

Covers:
- POST /api/documents/upload
- POST /api/documents/{upload_id}/assign-to-package
- GET  /api/templates/s3
- POST /api/templates/s3/copy
"""
import importlib

import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch, ANY
from fastapi.testclient import TestClient

from app.cognito_auth import UserContext


# ---------------------------------------------------------------------------
# Helpers / shared fixtures
# ---------------------------------------------------------------------------
# NOTE: conftest.py evicts app.main from sys.modules between test modules,
# so we must re-import it lazily inside the fixture to get the live module.

def _make_user(tenant_id: str = "test-tenant", user_id: str = "test-user") -> UserContext:
    """Return a real UserContext for a test user."""
    return UserContext(
        user_id=user_id,
        tenant_id=tenant_id,
        email=f"{user_id}@example.com",
    )


@pytest.fixture()
def mock_user() -> UserContext:
    return _make_user()


@pytest.fixture()
def client(mock_user: UserContext):
    """TestClient with auth dependency overridden to return mock_user."""
    import app.main as _main
    _main.app.dependency_overrides[_main.get_user_from_header] = lambda: mock_user
    with TestClient(_main.app, raise_server_exceptions=False) as c:
        yield c
    _main.app.dependency_overrides.clear()


# Convenience: valid multipart PDF payload
_PDF_FILE = ("test.pdf", b"%PDF-1.4 fake pdf content", "application/pdf")
_PDF_LARGE = ("big.pdf", b"x" * (26 * 1024 * 1024), "application/pdf")
_PNG_FILE = ("photo.png", b"\x89PNG fake", "image/png")


# ---------------------------------------------------------------------------
# Group 1: TestUploadEndpoint
# ---------------------------------------------------------------------------


class TestUploadEndpoint:
    """Tests for POST /api/documents/upload."""

    def test_upload_returns_classification(self, client):
        """A successful upload response must include a classification dict."""
        mock_classification = MagicMock()
        mock_classification.doc_type = "sow"
        mock_classification.to_dict.return_value = {
            "doc_type": "sow",
            "confidence": 0.9,
            "method": "filename",
            "suggested_title": "Statement of Work",
        }

        mock_doc = {"document_id": "doc-123", "doc_type": "sow"}

        with (
            patch("app.routers.documents.get_s3", return_value=MagicMock()),
            patch("app.routers.documents.classify_document", return_value=mock_classification),
            patch("app.routers.documents.extract_text_preview", return_value="preview text"),
            patch("app.unified_document_store.create_document", return_value=mock_doc),
            patch("app.document_markdown_service.convert_to_markdown", return_value=None),
        ):
            response = client.post(
                "/api/documents/upload",
                files={"file": _PDF_FILE},
            )

        assert response.status_code == 200
        data = response.json()
        assert "classification" in data
        assert isinstance(data["classification"], dict)
        assert data["classification"]["doc_type"] == "sow"

    def test_upload_returns_upload_id(self, client):
        """A successful upload response must include a non-empty upload_id."""
        mock_classification = MagicMock()
        mock_classification.doc_type = "igce"
        mock_classification.to_dict.return_value = {"doc_type": "igce", "confidence": 0.8, "method": "filename"}

        mock_doc = {"document_id": "doc-456", "doc_type": "igce"}

        with (
            patch("app.routers.documents.get_s3", return_value=MagicMock()),
            patch("app.routers.documents.classify_document", return_value=mock_classification),
            patch("app.routers.documents.extract_text_preview", return_value=""),
            patch("app.unified_document_store.create_document", return_value=mock_doc),
            patch("app.document_markdown_service.convert_to_markdown", return_value=None),
        ):
            response = client.post(
                "/api/documents/upload",
                files={"file": _PDF_FILE},
            )

        assert response.status_code == 200
        data = response.json()
        assert "upload_id" in data
        assert len(data["upload_id"]) > 0

    def test_upload_rejects_oversized_file(self, client):
        """Files larger than 25 MB must be rejected with HTTP 413."""
        response = client.post(
            "/api/documents/upload",
            files={"file": _PDF_LARGE},
        )
        assert response.status_code == 413
        assert "25 MB" in response.json()["detail"]

    def test_upload_rejects_invalid_mime_type(self, client):
        """Files with unsupported MIME types must be rejected with HTTP 415."""
        response = client.post(
            "/api/documents/upload",
            files={"file": _PNG_FILE},
        )
        assert response.status_code == 415
        assert "Unsupported file type" in response.json()["detail"]

    def test_upload_stores_metadata_in_dynamodb(self, client):
        """create_document must be called with the correct tenant_id and user_id."""
        mock_classification = MagicMock()
        mock_classification.doc_type = "acquisition_plan"
        mock_classification.to_dict.return_value = {
            "doc_type": "acquisition_plan",
            "confidence": 0.85,
            "method": "filename",
        }

        mock_doc = {"document_id": "doc-789", "tenant_id": "test-tenant", "owner_user_id": "test-user"}

        with (
            patch("app.routers.documents.get_s3", return_value=MagicMock()),
            patch("app.routers.documents.classify_document", return_value=mock_classification),
            patch("app.routers.documents.extract_text_preview", return_value="preview"),
            patch("app.unified_document_store.create_document", return_value=mock_doc) as mock_create,
            patch("app.document_markdown_service.convert_to_markdown", return_value=None),
        ):
            response = client.post(
                "/api/documents/upload",
                files={"file": _PDF_FILE},
            )

        assert response.status_code == 200
        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args
        assert call_kwargs.kwargs["tenant_id"] == "test-tenant"
        assert call_kwargs.kwargs["user_id"] == "test-user"

    def test_put_upload_converts_float_metadata_to_decimal(self):
        """Upload metadata written to DynamoDB must not contain raw floats."""
        from app.routers.documents import _put_upload

        mock_table = MagicMock()

        with patch("app.routers.documents.get_table", return_value=mock_table):
            _put_upload(
                "test-tenant",
                "upload-123",
                {
                    "classification": {
                        "doc_type": "sow",
                        "confidence": 0.85,
                    },
                    "size_bytes": 123,
                },
            )

        mock_table.put_item.assert_called_once()
        item = mock_table.put_item.call_args.kwargs["Item"]
        assert item["classification"]["confidence"] == Decimal("0.85")


# ---------------------------------------------------------------------------
# Group 2: TestAssignToPackage
# ---------------------------------------------------------------------------


class TestAssignToPackage:
    """Tests for POST /api/documents/{upload_id}/assign-to-package."""

    def _mock_upload_meta(
        self,
        tenant_id: str = "test-tenant",
        user_id: str = "test-user",
        doc_type: str = "sow",
        suggested_title: str = "Statement of Work",
        content_type: str = "application/pdf",
    ) -> dict:
        return {
            "PK": f"UPLOAD#{tenant_id}",
            "SK": f"UPLOAD#fake-upload-id",
            "tenant_id": tenant_id,
            "user_id": user_id,
            "s3_bucket": "eagle-documents-dev",
            "s3_key": f"eagle/{tenant_id}/{user_id}/uploads/fake-id/test.pdf",
            "filename": "test.pdf",
            "original_filename": "test.pdf",
            "content_type": content_type,
            "size_bytes": 1024,
            "classification": {
                "doc_type": doc_type,
                "confidence": 0.9,
                "suggested_title": suggested_title,
            },
            "session_id": None,
            "created_at": "2026-03-19T00:00:00",
        }

    def _mock_result(self) -> MagicMock:
        result = MagicMock()
        result.success = True
        result.version = 1
        result.error = None
        result.to_dict.return_value = {
            "document_id": "doc-abc-123",
            "version": 1,
            "doc_type": "sow",
        }
        return result

    def test_assign_creates_package_document(self, client):
        """A valid assign request must return a 200 with document info."""
        upload_meta = self._mock_upload_meta()
        mock_pkg = {"package_id": "pkg-1", "tenant_id": "test-tenant", "title": "Test Package"}

        with (
            patch("app.routers.documents._get_upload", return_value=upload_meta),
            patch("app.routers.documents.get_package", return_value=mock_pkg),
            patch("app.routers.documents.create_package_document_version", return_value=self._mock_result()),
            patch("app.routers.documents._delete_upload"),
            patch("boto3.client") as mock_boto3_client,
        ):
            mock_s3 = MagicMock()
            mock_s3.get_object.return_value = {"Body": MagicMock(read=lambda: b"pdf content")}
            mock_boto3_client.return_value = mock_s3

            response = client.post(
                "/api/documents/fake-upload-id/assign-to-package",
                json={"package_id": "pkg-1"},
            )

        assert response.status_code == 200
        data = response.json()
        assert "document_id" in data

    def test_assign_returns_404_for_missing_upload(self, client):
        """When _get_upload returns None, the endpoint must raise HTTP 404."""
        with patch("app.routers.documents._get_upload", return_value=None):
            response = client.post(
                "/api/documents/nonexistent-id/assign-to-package",
                json={"package_id": "pkg-1"},
            )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_assign_returns_403_for_wrong_tenant(self, client):
        """Upload belonging to a different tenant must raise HTTP 403."""
        # upload_meta has a different tenant_id than the authed user's tenant
        upload_meta = self._mock_upload_meta(tenant_id="other-tenant", user_id="other-user")

        with patch("app.routers.documents._get_upload", return_value=upload_meta):
            response = client.post(
                "/api/documents/some-upload-id/assign-to-package",
                json={"package_id": "pkg-1"},
            )

        assert response.status_code == 403
        assert "denied" in response.json()["detail"].lower()

    def test_assign_returns_404_for_missing_package(self, client):
        """When the target package does not exist, the endpoint must raise HTTP 404."""
        upload_meta = self._mock_upload_meta()

        with (
            patch("app.routers.documents._get_upload", return_value=upload_meta),
            patch("app.routers.documents.get_package", return_value=None),
        ):
            response = client.post(
                "/api/documents/fake-id/assign-to-package",
                json={"package_id": "pkg-does-not-exist"},
            )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_assign_requires_doc_type_for_unknown_classification(self, client):
        """If classification doc_type is 'unknown' and request body has no doc_type, expect 400."""
        upload_meta = self._mock_upload_meta(doc_type="unknown")
        mock_pkg = {"package_id": "pkg-1", "tenant_id": "test-tenant"}

        with (
            patch("app.routers.documents._get_upload", return_value=upload_meta),
            patch("app.routers.documents.get_package", return_value=mock_pkg),
        ):
            response = client.post(
                "/api/documents/fake-id/assign-to-package",
                # No doc_type in body — classification says "unknown"
                json={"package_id": "pkg-1"},
            )

        assert response.status_code == 400
        assert "doc_type" in response.json()["detail"].lower()

    def test_assign_uses_classification_doc_type_as_default(self, client):
        """When request body omits doc_type, classification doc_type (igce) is used."""
        upload_meta = self._mock_upload_meta(doc_type="igce", suggested_title="IGCE")
        mock_pkg = {"package_id": "pkg-1", "tenant_id": "test-tenant"}

        captured_call = {}

        def fake_create(**kwargs):
            captured_call.update(kwargs)
            return self._mock_result()

        with (
            patch("app.routers.documents._get_upload", return_value=upload_meta),
            patch("app.routers.documents.get_package", return_value=mock_pkg),
            patch("app.routers.documents.create_package_document_version", side_effect=fake_create),
            patch("app.routers.documents._delete_upload"),
            patch("boto3.client") as mock_boto3_client,
        ):
            mock_s3 = MagicMock()
            mock_s3.get_object.return_value = {"Body": MagicMock(read=lambda: b"content")}
            mock_boto3_client.return_value = mock_s3

            response = client.post(
                "/api/documents/fake-id/assign-to-package",
                # No doc_type in body — should fall back to "igce" from classification
                json={"package_id": "pkg-1"},
            )

        assert response.status_code == 200
        assert captured_call.get("doc_type") == "igce"


# ---------------------------------------------------------------------------
# Group 3: TestS3TemplateEndpoints
# ---------------------------------------------------------------------------


class TestS3TemplateEndpoints:
    """Tests for GET /api/templates/s3, preview/download, and POST /api/templates/s3/copy."""

    def _sample_template(self, s3_key: str = "templates/sow_template.md", phase: str = "planning") -> dict:
        return {
            "s3_key": s3_key,
            "filename": s3_key.rsplit("/", 1)[-1],
            "title": "SOW Template",
            "size": 4096,
            "category": {"phase": phase, "doc_type": "sow"},
        }

    def test_list_s3_templates_returns_metadata(self, client):
        """GET /api/templates/s3 must return templates list with total and phases."""
        fake_templates = [
            self._sample_template("templates/sow_template.md"),
            self._sample_template("templates/igce_template.xlsx"),
        ]
        fake_phases = {
            "intake": "Intake & Requirements",
            "planning": "Acquisition Planning",
            "solicitation": "Solicitation",
            "evaluation": "Evaluation & Selection",
            "award": "Award & Contract",
            "administration": "Contract Administration",
        }

        with (
            patch("app.template_registry.list_s3_templates", return_value=fake_templates),
            patch("app.template_registry.ACQUISITION_PHASES", fake_phases),
        ):
            response = client.get("/api/templates/s3")

        assert response.status_code == 200
        data = response.json()
        assert "templates" in data
        assert "total" in data
        assert "phases" in data
        assert isinstance(data["templates"], list)

    def test_list_s3_templates_with_phase_filter(self, client):
        """The phase query param must be forwarded to list_s3_templates."""
        fake_templates = [self._sample_template()]
        fake_phases = {
            "intake": "Intake & Requirements",
            "planning": "Acquisition Planning",
        }

        with (
            patch("app.template_registry.list_s3_templates", return_value=fake_templates) as mock_list,
            patch("app.template_registry.ACQUISITION_PHASES", fake_phases),
        ):
            response = client.get("/api/templates/s3?phase=planning")

        assert response.status_code == 200
        # list_s3_templates is called at least once; check any call had phase_filter="planning"
        assert mock_list.call_count >= 1
        found_planning = False
        for call in mock_list.call_args_list:
            if call.kwargs.get("phase_filter") == "planning":
                found_planning = True
                break
        assert found_planning, (
            f"list_s3_templates was not called with phase_filter='planning'. "
            f"Calls: {mock_list.call_args_list}"
        )

    def test_copy_template_to_package(self, client):
        """POST /api/templates/s3/copy must return a 200 with document_id and source=s3_template."""
        fake_content = b"# SOW Template\n\nStatement of Work..."
        fake_document = {
            "document_id": "doc-xyz-789",
            "doc_type": "sow",
            "filename": "sow_template.md",
        }

        with (
            patch("app.template_registry.get_s3_template_by_key", return_value=fake_content),
            patch("app.template_registry._infer_doc_type_from_filename", return_value="sow"),
            patch("app.document_store.create_document_from_s3", return_value=fake_document),
        ):
            response = client.post(
                "/api/templates/s3/copy",
                json={
                    "s3_key": "templates/sow_template.md",
                    "package_id": "pkg-abc",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["document_id"] == "doc-xyz-789"
        assert data["source"] == "s3_template"
        assert data["package_id"] == "pkg-abc"

    def test_get_s3_template_download_url(self, client):
        """GET /api/templates/s3/download-url returns a presigned URL for valid template keys."""
        valid_key = "eagle-knowledge-base/approved/supervisor-core/essential-templates/1.a. AP Under SAT.docx"

        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.return_value = "https://signed.example/template"

        with patch("app.routers.templates.get_s3", return_value=mock_s3):
            response = client.get(f"/api/templates/s3/download-url?s3_key={valid_key}")

        assert response.status_code == 200
        data = response.json()
        assert data["download_url"] == "https://signed.example/template"
        assert data["filename"] == "1.a. AP Under SAT.docx"

    def test_get_s3_template_download_url_rejects_invalid_prefix(self, client):
        """GET /api/templates/s3/download-url blocks keys outside the configured template prefix."""
        response = client.get("/api/templates/s3/download-url?s3_key=templates/bad.docx")

        assert response.status_code == 403
        assert "invalid template key" in response.json()["detail"].lower()

    def test_copy_template_returns_404_for_missing_key(self, client):
        """When get_s3_template_by_key returns None, the endpoint must raise HTTP 404."""
        with (
            patch("app.template_registry.get_s3_template_by_key", return_value=None),
            patch("app.template_registry._infer_doc_type_from_filename", return_value=None),
        ):
            response = client.post(
                "/api/templates/s3/copy",
                json={
                    "s3_key": "templates/nonexistent.md",
                    "package_id": "pkg-abc",
                },
            )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
