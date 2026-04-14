"""Tests for package attachment endpoints."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.cognito_auth import UserContext
from app.routers.dependencies import get_user_from_header
from app.routers.packages import router as packages_router


def _make_user(tenant_id: str = "test-tenant", user_id: str = "test-user") -> UserContext:
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
    app = FastAPI()
    app.include_router(packages_router)
    app.dependency_overrides[get_user_from_header] = lambda: mock_user
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


class TestPackageAttachmentEndpoints:
    def test_upload_package_attachment_accepts_png(self, client: TestClient):
        mock_s3 = MagicMock()
        mock_attachment = {
            "attachment_id": "att-123",
            "package_id": "PKG-0001",
            "attachment_type": "image",
            "category": "technical_evidence",
            "usage": "reference",
            "include_in_zip": True,
            "title": "Screenshot",
            "filename": "screenshot.png",
            "original_filename": "screenshot.png",
            "content_type": "image/png",
            "file_type": "png",
            "size_bytes": 10,
            "s3_key": "eagle/test-tenant/packages/PKG-0001/attachments/att-123/v1/screenshot.png",
        }

        with (
            patch("app.routers.packages.get_package", return_value={"package_id": "PKG-0001"}),
            patch("app.db_client.get_s3", return_value=mock_s3),
            patch("app.routers.packages.create_attachment", return_value=mock_attachment),
        ):
            response = client.post(
                "/api/packages/PKG-0001/attachments",
                files={"file": ("screenshot.png", b"\x89PNG fake", "image/png")},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["attachment_id"] == "att-123"
        assert data["content_type"] == "image/png"
        assert data["extracted_text_available"] is False

    def test_list_update_delete_package_attachment(self, client: TestClient):
        attachment = {
            "attachment_id": "att-123",
            "package_id": "PKG-0001",
            "owner_user_id": "test-user",
            "title": "Requirements Doc",
            "category": "requirements_evidence",
            "usage": "reference",
            "linked_doc_type": None,
            "include_in_zip": True,
        }

        with patch("app.routers.packages.get_package", return_value={"package_id": "PKG-0001"}), patch(
            "app.routers.packages.list_package_attachments",
            return_value=[attachment],
        ):
            list_response = client.get("/api/packages/PKG-0001/attachments")

        assert list_response.status_code == 200
        assert list_response.json()["count"] == 1

        updated_attachment = {
            **attachment,
            "category": "prior_artifact",
            "title": "Prior SOW",
            "usage": "checklist_support",
            "linked_doc_type": "sow",
        }
        with (
            patch("app.routers.packages.get_attachment", return_value=attachment),
            patch("app.routers.packages.update_attachment", return_value=updated_attachment),
        ):
            patch_response = client.patch(
                "/api/packages/PKG-0001/attachments/att-123",
                json={
                    "category": "prior_artifact",
                    "title": "Prior SOW",
                    "usage": "checklist_support",
                    "linked_doc_type": "sow",
                },
            )

        assert patch_response.status_code == 200
        assert patch_response.json()["category"] == "prior_artifact"
        assert patch_response.json()["linked_doc_type"] == "sow"

        with (
            patch("app.routers.packages.get_attachment", return_value=attachment),
            patch("app.routers.packages.delete_attachment", return_value=True),
        ):
            delete_response = client.delete("/api/packages/PKG-0001/attachments/att-123")

        assert delete_response.status_code == 200
        assert delete_response.json() == {"deleted": True, "attachment_id": "att-123"}

    def test_attachment_only_export_returns_zip(self, client: TestClient):
        mock_s3 = MagicMock()
        mock_body = MagicMock()
        mock_body.read.return_value = b"fake-image-bytes"
        mock_s3.get_object.return_value = {"Body": mock_body}

        with (
            patch("app.routers.packages.get_package", return_value={"title": "Test Package"}),
            patch("app.routers.packages.list_package_documents", return_value=[]),
            patch(
                "app.routers.packages.list_package_attachments",
                return_value=[
                    {
                        "attachment_id": "att-1",
                        "category": "technical_evidence",
                        "title": "Screenshot",
                        "file_type": "png",
                        "s3_bucket": "bucket",
                        "s3_key": "key",
                    }
                ],
            ),
            patch("app.db_client.get_s3", return_value=mock_s3),
        ):
            response = client.get("/api/packages/PKG-0001/export/zip")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/zip"

    def test_promote_attachment_creates_canonical_package_document(self, client: TestClient):
        attachment = {
            "attachment_id": "att-123",
            "package_id": "PKG-0001",
            "owner_user_id": "test-user",
            "title": "Prior SOW",
            "filename": "prior-sow.docx",
            "original_filename": "prior-sow.docx",
            "file_type": "docx",
            "category": "prior_artifact",
            "usage": "official_candidate",
            "s3_bucket": "bucket",
            "s3_key": "attachment/key",
            "markdown_s3_key": "attachment/key.content.md",
            "session_id": "sess-1",
        }
        mock_s3 = MagicMock()
        mock_binary = MagicMock()
        mock_binary.read.return_value = b"fake-docx-bytes"
        mock_markdown = MagicMock()
        mock_markdown.read.return_value = b"# Prior SOW\n\nContent"
        mock_s3.get_object.side_effect = [
            {"Body": mock_binary},
            {"Body": mock_markdown},
        ]
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.version = 2
        mock_result.to_dict.return_value = {
            "success": True,
            "package_id": "PKG-0001",
            "doc_type": "sow",
            "version": 2,
        }
        promoted_doc = {
            "document_id": "doc-789",
            "package_id": "PKG-0001",
            "doc_type": "sow",
            "title": "Prior SOW",
            "version": 2,
            "status": "draft",
        }

        with (
            patch("app.routers.packages.get_attachment", return_value=attachment),
            patch("app.db_client.get_s3", return_value=mock_s3),
            patch("app.routers.packages.create_package_document_version", return_value=mock_result) as mock_create,
            patch("app.routers.packages.update_attachment", return_value={**attachment, "usage": "official_document"}) as mock_update,
            patch("app.routers.packages.get_document", return_value=promoted_doc),
        ):
            response = client.post(
                "/api/packages/PKG-0001/attachments/att-123/promote",
                json={"doc_type": "sow", "title": "Prior SOW", "set_as_official": True},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["doc_type"] == "sow"
        assert data["promoted_from_attachment_id"] == "att-123"
        mock_create.assert_called_once()
        create_kwargs = mock_create.call_args.kwargs
        assert create_kwargs["package_id"] == "PKG-0001"
        assert create_kwargs["doc_type"] == "sow"
        assert create_kwargs["markdown_content"] == "# Prior SOW\n\nContent"
        mock_update.assert_called_once()
