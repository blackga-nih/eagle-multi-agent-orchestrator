"""Unit tests for knowledge base tool handlers."""

from __future__ import annotations

from unittest.mock import MagicMock

from botocore.exceptions import ClientError

from app.tools import knowledge_tools as kt


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
        "complexity_level": "medium",
        "key_requirements": [],
        "keywords": keywords or ["far", "sole source"],
        "s3_key": f"kb/{doc_id}.md",
        "confidence_score": 0.9,
    }


def test_exec_knowledge_search_returns_filtered_results(monkeypatch):
    table = MagicMock()
    table.scan.return_value = {
        "Items": [
            _ddb_item(doc_id="a", title="Sole Source Guide", keywords=["sole source", "justification"]),
            _ddb_item(doc_id="b", title="Unrelated", keywords=["travel"]),
        ]
    }
    ddb = MagicMock()
    ddb.Table.return_value = table
    monkeypatch.setattr(kt, "get_dynamodb", lambda: ddb)

    result = kt.exec_knowledge_search(
        {"document_type": "guidance", "keywords": ["sole source"], "limit": 5},
        tenant_id="dev-tenant",
    )

    assert result["count"] == 1
    assert result["results"][0]["document_id"] == "a"
    assert result["results"][0]["s3_key"] == "kb/a.md"


def test_exec_knowledge_search_handles_dynamodb_error(monkeypatch):
    table = MagicMock()
    table.scan.side_effect = ClientError(
        error_response={"Error": {"Code": "ProvisionedThroughputExceededException", "Message": "boom"}},
        operation_name="Scan",
    )
    ddb = MagicMock()
    ddb.Table.return_value = table
    monkeypatch.setattr(kt, "get_dynamodb", lambda: ddb)

    result = kt.exec_knowledge_search({"limit": 2}, tenant_id="dev-tenant")

    assert result["count"] == 0
    assert result["results"] == []
    assert "error" in result


def test_exec_knowledge_fetch_returns_content(monkeypatch):
    body = MagicMock()
    body.read.return_value = b"Document body"

    s3 = MagicMock()
    s3.get_object.return_value = {"Body": body}
    monkeypatch.setattr(kt, "get_s3", lambda: s3)

    result = kt.exec_knowledge_fetch({"s3_key": "kb/doc-a.md"}, tenant_id="dev-tenant")

    assert result["document_id"] == "kb/doc-a.md"
    assert result["content"] == "Document body"
    assert result["truncated"] is False


def test_exec_knowledge_fetch_handles_missing_key(monkeypatch):
    class NoSuchKeyError(Exception):
        pass

    s3 = MagicMock()
    s3.exceptions.NoSuchKey = NoSuchKeyError
    s3.get_object.side_effect = NoSuchKeyError("missing")
    monkeypatch.setattr(kt, "get_s3", lambda: s3)

    result = kt.exec_knowledge_fetch({"s3_key": "kb/missing.md"}, tenant_id="dev-tenant")

    assert "error" in result
    assert "Document not found" in result["error"]


def test_exec_knowledge_fetch_truncates_large_content(monkeypatch):
    large_text = "A" * 51000
    body = MagicMock()
    body.read.return_value = large_text.encode("utf-8")

    s3 = MagicMock()
    s3.get_object.return_value = {"Body": body}
    monkeypatch.setattr(kt, "get_s3", lambda: s3)

    result = kt.exec_knowledge_fetch({"s3_key": "kb/large.md"}, tenant_id="dev-tenant")

    assert result["truncated"] is True
    assert result["content_length"] == 51000
    assert len(result["content"]) == 50000


# ══════════════════════════════════════════════════════════════════════════════
# Query Parameter Tests
# ══════════════════════════════════════════════════════════════════════════════


def test_exec_knowledge_search_query_matches_document_id(monkeypatch):
    """Query parameter should find documents by case number in document_id."""
    table = MagicMock()
    table.scan.return_value = {
        "Items": [
            _ddb_item(
                doc_id="eagle-knowledge-base/approved/legal-counselor/appropriations-law/GAO_B-302358_IDIQ_Min_Fund.txt",
                title="GAO Decision B-302358: IDIQ Minimum Obligation Requirements",
                topic="funding",
                keywords=["IDIQ", "obligation", "GAO"],
            ),
            _ddb_item(
                doc_id="eagle-knowledge-base/approved/legal-counselor/appropriations-law/GAO_B-321640_ADA_Bonafide.txt",
                title="GAO Decision B-321640: ADA Bona Fide Needs",
                topic="funding",
                keywords=["ADA", "bona fide", "GAO"],
            ),
        ]
    }
    ddb = MagicMock()
    ddb.Table.return_value = table
    monkeypatch.setattr(kt, "get_dynamodb", lambda: ddb)

    result = kt.exec_knowledge_search(
        {"query": "B-302358"},
        tenant_id="dev-tenant",
    )

    assert result["count"] == 1
    assert "B-302358" in result["results"][0]["document_id"]


def test_exec_knowledge_search_query_matches_title(monkeypatch):
    """Query parameter should find documents by text in title."""
    table = MagicMock()
    table.scan.return_value = {
        "Items": [
            _ddb_item(doc_id="doc1", title="IDIQ Minimum Obligation Requirements"),
            _ddb_item(doc_id="doc2", title="Contract Closeout Procedures"),
        ]
    }
    ddb = MagicMock()
    ddb.Table.return_value = table
    monkeypatch.setattr(kt, "get_dynamodb", lambda: ddb)
    # Suppress built-in KB entries so only DynamoDB mock results participate
    monkeypatch.setattr(kt, "BUILTIN_KB_ENTRIES", [])

    result = kt.exec_knowledge_search(
        {"query": "IDIQ Minimum"},
        tenant_id="dev-tenant",
    )

    assert result["count"] == 1
    assert result["results"][0]["document_id"] == "doc1"


def test_exec_knowledge_search_query_case_insensitive(monkeypatch):
    """Query matching should be case-insensitive."""
    table = MagicMock()
    table.scan.return_value = {
        "Items": [
            _ddb_item(doc_id="GAO_B-302358.txt", title="GAO Decision"),
        ]
    }
    ddb = MagicMock()
    ddb.Table.return_value = table
    monkeypatch.setattr(kt, "get_dynamodb", lambda: ddb)

    # Lowercase query should match uppercase document_id
    result = kt.exec_knowledge_search(
        {"query": "b-302358"},
        tenant_id="dev-tenant",
    )

    assert result["count"] == 1


def test_exec_knowledge_search_query_combined_with_topic_filter(monkeypatch):
    """Query and topic filters should work together (AND logic)."""
    table = MagicMock()
    # Simulate DynamoDB returning only items matching topic filter
    table.scan.return_value = {
        "Items": [
            _ddb_item(doc_id="GAO_B-302358.txt", title="GAO Decision", topic="funding"),
        ]
    }
    ddb = MagicMock()
    ddb.Table.return_value = table
    monkeypatch.setattr(kt, "get_dynamodb", lambda: ddb)

    # Search with both query and topic
    result = kt.exec_knowledge_search(
        {"query": "B-302358", "topic": "funding"},
        tenant_id="dev-tenant",
    )

    assert result["count"] == 1
    assert result["results"][0]["primary_topic"] == "funding"


def test_exec_knowledge_search_query_no_match_returns_empty(monkeypatch):
    """Query with no matches should return empty results."""
    table = MagicMock()
    table.scan.return_value = {
        "Items": [
            _ddb_item(doc_id="unrelated.txt", title="Unrelated Document"),
        ]
    }
    ddb = MagicMock()
    ddb.Table.return_value = table
    monkeypatch.setattr(kt, "get_dynamodb", lambda: ddb)
    # Suppress built-in KB entries so only DynamoDB mock results participate
    monkeypatch.setattr(kt, "BUILTIN_KB_ENTRIES", [])

    result = kt.exec_knowledge_search(
        {"query": "B-999999"},
        tenant_id="dev-tenant",
    )

    assert result["count"] == 0
    assert result["results"] == []


def test_exec_knowledge_search_query_matches_summary(monkeypatch):
    """Query parameter should find documents by text in summary."""
    table = MagicMock()
    table.scan.return_value = {
        "Items": [
            _ddb_item(doc_id="doc1", title="Generic Title"),
            _ddb_item(doc_id="doc2", title="Another Title"),
        ]
    }
    # Override the summary for first item
    table.scan.return_value["Items"][0]["summary"] = "This document covers B-302358 case law"

    ddb = MagicMock()
    ddb.Table.return_value = table
    monkeypatch.setattr(kt, "get_dynamodb", lambda: ddb)
    # Suppress built-in KB entries so only DynamoDB mock results participate
    monkeypatch.setattr(kt, "BUILTIN_KB_ENTRIES", [])

    result = kt.exec_knowledge_search(
        {"query": "B-302358"},
        tenant_id="dev-tenant",
    )

    assert result["count"] == 1
    assert result["results"][0]["document_id"] == "doc1"


# ══════════════════════════════════════════════════════════════════════════════
# Semantic Search — KB-only filter tests
# ══════════════════════════════════════════════════════════════════════════════


def _make_vector(s3_key: str, distance: float = 0.3) -> dict:
    """Build a fake S3 Vectors query_vectors response vector."""
    return {
        "metadata": {
            "s3_key": s3_key,
            "document_id": s3_key,
            "title": s3_key.rsplit("/", 1)[-1],
            "summary": "",
            "document_type": "",
            "primary_topic": "",
            "primary_agent": "",
        },
        "distance": distance,
    }


def test_semantic_search_filters_non_kb_docs(monkeypatch):
    """exec_semantic_search must drop docs outside eagle-knowledge-base/."""
    monkeypatch.setattr(kt, "embed_text", lambda *a, **kw: [0.1] * 1024)

    sv_mock = MagicMock()
    sv_mock.query_vectors.return_value = {
        "vectors": [
            _make_vector("eagle-knowledge-base/approved/template.md", distance=0.4),
            _make_vector("eagle/dev-tenant/dev-user/documents/sow_20260403.docx", distance=0.1),
            _make_vector("eagle-knowledge-base/approved/guide.md", distance=0.5),
        ],
    }
    monkeypatch.setattr(kt, "_get_s3vectors_client", lambda: sv_mock)

    result = kt.exec_semantic_search("statement of work", tenant_id="dev-tenant")

    keys = [r["s3_key"] for r in result["results"]]
    assert "eagle/dev-tenant/dev-user/documents/sow_20260403.docx" not in keys
    assert "eagle-knowledge-base/approved/template.md" in keys
    assert "eagle-knowledge-base/approved/guide.md" in keys
    assert result["count"] == 2


def test_semantic_search_non_kb_docs_dont_displace_kb_docs(monkeypatch):
    """Non-KB docs must not consume ranking slots that KB docs need."""
    monkeypatch.setattr(kt, "embed_text", lambda *a, **kw: [0.1] * 1024)

    # 5 non-KB user docs with HIGH similarity (low distance = high confidence)
    user_docs = [
        _make_vector(f"eagle/dev-tenant/dev-user/documents/sow_{i}.docx", distance=0.05)
        for i in range(5)
    ]
    # 12 KB docs with LOWER similarity
    kb_docs = [
        _make_vector(f"eagle-knowledge-base/approved/doc_{i}.md", distance=0.3 + i * 0.02)
        for i in range(12)
    ]

    sv_mock = MagicMock()
    sv_mock.query_vectors.return_value = {"vectors": user_docs + kb_docs}
    monkeypatch.setattr(kt, "_get_s3vectors_client", lambda: sv_mock)

    result = kt.exec_semantic_search("SOW template", tenant_id="dev-tenant", limit=10)

    # All 10 slots should be KB docs — user docs must not steal any slots
    assert result["count"] == 10
    for r in result["results"]:
        assert r["s3_key"].startswith("eagle-knowledge-base/"), (
            f"Non-KB doc leaked into results: {r['s3_key']}"
        )


def test_semantic_search_returns_empty_when_only_non_kb_docs(monkeypatch):
    """If the index only contains non-KB docs, return empty results."""
    monkeypatch.setattr(kt, "embed_text", lambda *a, **kw: [0.1] * 1024)

    sv_mock = MagicMock()
    sv_mock.query_vectors.return_value = {
        "vectors": [
            _make_vector("eagle/dev-tenant/dev-user/documents/sow.docx", distance=0.1),
            _make_vector("eagle/dev-tenant/packages/pkg1/doc.md", distance=0.2),
        ],
    }
    monkeypatch.setattr(kt, "_get_s3vectors_client", lambda: sv_mock)

    result = kt.exec_semantic_search("SOW", tenant_id="dev-tenant")

    assert result["count"] == 0
    assert result["results"] == []


def test_semantic_search_disabled_returns_empty(monkeypatch):
    """When SEMANTIC_LANE_ENABLED=false, return empty without querying."""
    monkeypatch.setenv("SEMANTIC_LANE_ENABLED", "false")

    result = kt.exec_semantic_search("anything", tenant_id="dev-tenant")

    assert result["count"] == 0
    assert result["results"] == []
