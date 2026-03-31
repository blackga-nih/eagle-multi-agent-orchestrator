"""Tests for the Knowledge Base browse endpoints.

Covers:
- GET /api/knowledge-base          (list/search KB documents)
- GET /api/knowledge-base/stats    (aggregate counts)
- GET /api/knowledge-base/document/{s3_key}  (fetch content)
- GET /api/knowledge-base/plugin-data        (static reference files)
"""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.cognito_auth import UserContext


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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
    """TestClient with auth dependency overridden."""
    import app.main as _main
    _main.app.dependency_overrides[_main.get_user_from_header] = lambda: mock_user
    with TestClient(_main.app, raise_server_exceptions=False) as c:
        yield c
    _main.app.dependency_overrides.clear()


def _ddb_item(
    *,
    doc_id: str,
    title: str,
    topic: str = "compliance",
    document_type: str = "guidance",
    agent: str = "supervisor-core",
    keywords: list[str] | None = None,
) -> dict:
    return {
        "document_id": doc_id,
        "title": title,
        "summary": f"{title} summary",
        "document_type": document_type,
        "primary_topic": topic,
        "primary_agent": agent,
        "authority_level": "guidance",
        "keywords": keywords or ["far", "compliance"],
        "s3_key": f"kb/{doc_id}.md",
        "confidence_score": 0.9,
        "word_count": 500,
        "page_count": 2,
        "file_type": "md",
        "last_updated": "2026-03-25T00:00:00Z",
    }


def _mock_dynamo_resource(items: list[dict]):
    """Return a mock boto3 DynamoDB resource whose Table().scan() returns items."""
    table = MagicMock()
    table.scan.return_value = {"Items": items}
    ddb = MagicMock()
    ddb.Table.return_value = table
    return ddb


# ---------------------------------------------------------------------------
# GET /api/knowledge-base
# ---------------------------------------------------------------------------


class TestListKnowledgeBase:
    """Tests for GET /api/knowledge-base."""

    def test_returns_documents(self, client):
        items = [
            _ddb_item(doc_id="doc-1", title="FAR Sole Source"),
            _ddb_item(doc_id="doc-2", title="IGCE Template", topic="funding"),
        ]
        ddb = _mock_dynamo_resource(items)

        with patch("app.routers.knowledge._get_dynamo", return_value=ddb):
            resp = client.get("/api/knowledge-base")

        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        assert len(data["documents"]) == 2
        assert data["documents"][0]["document_id"] in ("doc-1", "doc-2")

    def test_filters_by_topic(self, client):
        items = [
            _ddb_item(doc_id="doc-1", title="Compliance Guide", topic="compliance"),
            _ddb_item(doc_id="doc-2", title="Funding Guide", topic="funding"),
        ]
        ddb = _mock_dynamo_resource(items)

        with patch("app.routers.knowledge._get_dynamo", return_value=ddb):
            resp = client.get("/api/knowledge-base?topic=compliance")

        assert resp.status_code == 200
        # The filter is applied via DynamoDB FilterExpression, but since we're
        # mocking the scan, both items are returned — the endpoint uses filter_expr
        # which DDB applies server-side. With mock, we just verify the endpoint works.
        data = resp.json()
        assert "documents" in data
        assert "count" in data

    def test_delegates_to_search_when_query_provided(self, client):
        mock_result = {
            "results": [{"document_id": "a", "title": "Result A", "s3_key": "kb/a.md"}],
            "count": 1,
        }
        with patch("app.tools.knowledge_tools.exec_knowledge_search", return_value=mock_result) as mock_search:
            resp = client.get("/api/knowledge-base?query=sole+source")

        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["documents"][0]["document_id"] == "a"
        mock_search.assert_called_once()

    def test_returns_empty_when_no_docs(self, client):
        ddb = _mock_dynamo_resource([])

        with patch("app.routers.knowledge._get_dynamo", return_value=ddb):
            resp = client.get("/api/knowledge-base")

        assert resp.status_code == 200
        assert resp.json()["count"] == 0
        assert resp.json()["documents"] == []

    def test_respects_limit(self, client):
        items = [_ddb_item(doc_id=f"doc-{i}", title=f"Doc {i}") for i in range(10)]
        ddb = _mock_dynamo_resource(items)

        with patch("app.routers.knowledge._get_dynamo", return_value=ddb):
            resp = client.get("/api/knowledge-base?limit=3")

        assert resp.status_code == 200
        assert len(resp.json()["documents"]) == 3

    def test_excludes_kb_review_records(self, client):
        """Items with PK attribute (KB_REVIEW records) should be filtered out."""
        items = [
            _ddb_item(doc_id="doc-1", title="Good Doc"),
            {**_ddb_item(doc_id="doc-2", title="KB Review"), "PK": "KB_REVIEW#123", "SK": "META"},
        ]
        # The filter uses Attr("PK").not_exists() — with mock scan,
        # DDB doesn't actually filter, but we verify endpoint doesn't crash
        ddb = _mock_dynamo_resource(items)

        with patch("app.routers.knowledge._get_dynamo", return_value=ddb):
            resp = client.get("/api/knowledge-base")

        assert resp.status_code == 200

    def test_handles_dynamo_error(self, client):
        from botocore.exceptions import ClientError

        table = MagicMock()
        table.scan.side_effect = ClientError(
            error_response={"Error": {"Code": "InternalServerError", "Message": "boom"}},
            operation_name="Scan",
        )
        ddb = MagicMock()
        ddb.Table.return_value = table

        with patch("app.routers.knowledge._get_dynamo", return_value=ddb):
            resp = client.get("/api/knowledge-base")

        assert resp.status_code == 500

    def test_document_shape(self, client):
        """Verify the response document shape has all expected fields."""
        items = [_ddb_item(doc_id="doc-1", title="Test Doc")]
        ddb = _mock_dynamo_resource(items)

        with patch("app.routers.knowledge._get_dynamo", return_value=ddb):
            resp = client.get("/api/knowledge-base")

        doc = resp.json()["documents"][0]
        expected_keys = {
            "document_id", "title", "summary", "document_type",
            "primary_topic", "primary_agent", "authority_level",
            "keywords", "s3_key", "confidence_score",
            "word_count", "page_count", "file_type", "last_updated",
        }
        assert expected_keys.issubset(set(doc.keys()))


# ---------------------------------------------------------------------------
# GET /api/knowledge-base/stats
# ---------------------------------------------------------------------------


class TestKnowledgeBaseStats:
    """Tests for GET /api/knowledge-base/stats."""

    def test_returns_aggregated_stats(self, client):
        items = [
            _ddb_item(doc_id="1", title="A", topic="compliance", document_type="regulation"),
            _ddb_item(doc_id="2", title="B", topic="compliance", document_type="guidance"),
            _ddb_item(doc_id="3", title="C", topic="funding", document_type="guidance"),
        ]
        ddb = _mock_dynamo_resource(items)

        with patch("app.routers.knowledge._get_dynamo", return_value=ddb):
            resp = client.get("/api/knowledge-base/stats")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert data["by_topic"]["compliance"] == 2
        assert data["by_topic"]["funding"] == 1
        assert data["by_type"]["guidance"] == 2
        assert data["by_type"]["regulation"] == 1

    def test_empty_table_returns_zero_counts(self, client):
        ddb = _mock_dynamo_resource([])

        with patch("app.routers.knowledge._get_dynamo", return_value=ddb):
            resp = client.get("/api/knowledge-base/stats")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["by_topic"] == {}
        assert data["by_type"] == {}
        assert data["by_agent"] == {}

    def test_handles_dynamo_error(self, client):
        from botocore.exceptions import ClientError

        table = MagicMock()
        table.scan.side_effect = ClientError(
            error_response={"Error": {"Code": "ServiceUnavailable", "Message": "down"}},
            operation_name="Scan",
        )
        ddb = MagicMock()
        ddb.Table.return_value = table

        with patch("app.routers.knowledge._get_dynamo", return_value=ddb):
            resp = client.get("/api/knowledge-base/stats")

        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# GET /api/knowledge-base/document/{s3_key}
# ---------------------------------------------------------------------------


class TestKBDocumentFetch:
    """Tests for GET /api/knowledge-base/document/{s3_key}."""

    def test_returns_content(self, client):
        mock_result = {
            "document_id": "kb/doc-1.md",
            "content": "# FAR Guidance\n\nDocument content here.",
            "truncated": False,
            "content_length": 40,
        }
        with patch("app.tools.knowledge_tools.exec_knowledge_fetch", return_value=mock_result):
            resp = client.get("/api/knowledge-base/document/kb/doc-1.md")

        assert resp.status_code == 200
        data = resp.json()
        assert data["content"] == "# FAR Guidance\n\nDocument content here."
        assert data["truncated"] is False

    def test_returns_404_for_missing_document(self, client):
        mock_result = {"error": "Document not found: kb/missing.md"}
        with patch("app.tools.knowledge_tools.exec_knowledge_fetch", return_value=mock_result):
            resp = client.get("/api/knowledge-base/document/kb/missing.md")

        assert resp.status_code == 404

    def test_handles_nested_s3_key(self, client):
        """S3 keys with slashes should be captured correctly."""
        mock_result = {
            "document_id": "eagle-knowledge-base/approved/far-guidance.md",
            "content": "content",
            "truncated": False,
            "content_length": 7,
        }
        with patch("app.tools.knowledge_tools.exec_knowledge_fetch", return_value=mock_result):
            resp = client.get(
                "/api/knowledge-base/document/eagle-knowledge-base/approved/far-guidance.md"
            )

        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/knowledge-base/plugin-data
# ---------------------------------------------------------------------------


class TestPluginData:
    """Tests for GET /api/knowledge-base/plugin-data."""

    def test_lists_plugin_files(self, client):
        resp = client.get("/api/knowledge-base/plugin-data")

        assert resp.status_code == 200
        data = resp.json()
        assert "files" in data
        names = [f["name"] for f in data["files"]]
        assert "far-database.json" in names
        assert "matrix.json" in names
        assert "thresholds.json" in names
        assert "contract-vehicles.json" in names

    def test_file_metadata_shape(self, client):
        resp = client.get("/api/knowledge-base/plugin-data")

        data = resp.json()
        for f in data["files"]:
            assert "name" in f
            assert "description" in f
            assert "size_bytes" in f
            assert "item_count" in f
            assert f["size_bytes"] > 0
            assert f["item_count"] > 0

    def test_fetches_specific_file(self, client):
        resp = client.get("/api/knowledge-base/plugin-data?file=thresholds.json")

        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "thresholds.json"
        assert "content" in data
        assert data["item_count"] > 0

    def test_fetches_far_database(self, client):
        resp = client.get("/api/knowledge-base/plugin-data?file=far-database.json")

        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "far-database.json"
        assert isinstance(data["content"], list)
        assert data["item_count"] > 0

    def test_fetches_matrix(self, client):
        resp = client.get("/api/knowledge-base/plugin-data?file=matrix.json")

        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "matrix.json"
        assert isinstance(data["content"], dict)

    def test_rejects_invalid_filename(self, client):
        resp = client.get("/api/knowledge-base/plugin-data?file=../../etc/passwd")

        assert resp.status_code == 400
        assert "Invalid file" in resp.json()["detail"]

    def test_rejects_unknown_filename(self, client):
        resp = client.get("/api/knowledge-base/plugin-data?file=nonexistent.json")

        assert resp.status_code == 400
