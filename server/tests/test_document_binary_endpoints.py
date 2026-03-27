"""Tests for binary-safe document endpoint behavior."""

import io
import os
import sys
from datetime import datetime
from types import ModuleType
from unittest.mock import MagicMock, patch

from fastapi import APIRouter
from fastapi.testclient import TestClient

# Ensure server/ is on sys.path so "app.main" resolves
_server_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)


ENV_PATCH = {
    "REQUIRE_AUTH": "false",
    "DEV_MODE": "true",
    "USE_BEDROCK": "false",
    "COGNITO_USER_POOL_ID": "us-east-1_test",
    "COGNITO_CLIENT_ID": "test-client",
    "EAGLE_SESSIONS_TABLE": "eagle",
    "USE_PERSISTENT_SESSIONS": "false",
    "S3_BUCKET": "test-bucket",
}


def _build_s3_mock() -> MagicMock:
    s3 = MagicMock()

    def get_object(*, Bucket, Key):
        if Key.endswith(".content.md"):
            from botocore.exceptions import ClientError

            raise ClientError(
                {"Error": {"Code": "NoSuchKey", "Message": "Not found"}},
                "GetObject",
            )
        return {
            "Body": io.BytesIO(b"# Test markdown\n\nhello"),
            "ContentType": "text/markdown; charset=utf-8",
            "ContentLength": 24,
            "LastModified": datetime(2026, 3, 11, 12, 5, 0),
        }

    s3.get_object.side_effect = get_object
    s3.generate_presigned_url.return_value = "https://signed.example/document"
    return s3


def _load_app():
    with patch.dict(os.environ, ENV_PATCH, clear=False):
        fake_strands = ModuleType("app.strands_agentic_service")
        fake_streaming_routes = ModuleType("app.streaming_routes")

        async def _mock_sdk_query(*args, **kwargs):
            if False:
                yield None

        async def _mock_sdk_query_streaming(*args, **kwargs):
            if False:
                yield None

        fake_strands.sdk_query = _mock_sdk_query
        fake_strands.sdk_query_streaming = _mock_sdk_query_streaming
        fake_strands.MODEL = "test-model"
        fake_strands.EAGLE_TOOLS = []
        fake_streaming_routes.create_streaming_router = lambda *args, **kwargs: APIRouter()

        with patch.dict(
            sys.modules,
            {
                "app.strands_agentic_service": fake_strands,
                "app.streaming_routes": fake_streaming_routes,
            },
        ):
            import importlib

            for _mod in ("app.main", "app.changelog_store", "app.cognito_auth", "app.document_ai_edit_service", "app.spreadsheet_edit_service"):
                sys.modules.pop(_mod, None)

            import app.main as main_module

            importlib.reload(main_module)

            # Capture the get_user_from_header callable that the reloaded app
            # registered in its Depends() — needed for dependency_overrides.
            _dep_func = main_module.get_user_from_header

            return main_module, _dep_func


def _override_auth(app, dep_func):
    """Use FastAPI dependency_overrides to inject a test user."""
    from app.cognito_auth import UserContext

    async def _test_user():
        return UserContext(
            user_id="dev-user",
            tenant_id="dev-tenant",
            email="dev-user@example.com",
            username="dev-user",
            roles=["admin"],
            tier="premium",
        )

    app.dependency_overrides[dep_func] = _test_user


def test_put_document_rejects_binary_office_document():
    main_module, dep_func = _load_app()
    app = main_module.app
    _override_auth(app, dep_func)

    # The 415 rejection happens before any S3 call — no S3 mock needed.
    with TestClient(app) as client:
        resp = client.put(
            "/api/documents/eagle/dev-tenant/packages/PKG-1/sow/v2/source.docx",
            json={"content": "replacement text"},
        )

    assert resp.status_code == 415
    assert "plain text editor" in resp.json()["detail"].lower()


def test_get_document_still_returns_inline_content_for_text_documents():
    main_module, dep_func = _load_app()
    app = main_module.app
    _override_auth(app, dep_func)
    s3 = _build_s3_mock()

    import app.db_client as _db
    _db.get_s3.cache_clear()
    with patch("boto3.client", return_value=s3):
        with TestClient(app) as client:
            resp = client.get("/api/documents/eagle/dev-tenant/dev-user/documents/test.md?content=true")

    assert resp.status_code == 200
    data = resp.json()
    assert data["is_binary"] is False
    assert data["content"].startswith("# Test markdown")
    assert data["download_url"] is None
    assert data["file_type"] == "md"
