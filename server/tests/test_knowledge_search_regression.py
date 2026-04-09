"""Regression tests for knowledge_search zero-results bug (2026-04-01).

Root cause: SEARCH_MODEL_ID used 'anthropic.claude-haiku-4-5-20251001-v1:0'
(no cross-region inference profile prefix).  Bedrock raised ValidationException,
the broad except caught it silently, AI ranking returned [], and the old
deterministic fallback required ALL query terms to match — producing zero
results from 676 candidate documents.

Two fixes validated here:
  1. SEARCH_MODEL_ID must use 'us.' prefix for cross-region inference
  2. _deterministic_match uses scored partial matching, not ALL-terms AND
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

from app.tools import knowledge_tools as kt


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════


def _doc(
    doc_id: str,
    title: str,
    summary: str = "",
    topic: str = "acquisition_packages",
    keywords: list[str] | None = None,
) -> dict:
    """Build a minimal KB document for testing."""
    return {
        "document_id": doc_id,
        "title": title,
        "summary": summary or f"{title} summary",
        "document_type": "guidance",
        "primary_topic": topic,
        "primary_agent": "supervisor-core",
        "authority_level": "guidance",
        "complexity_level": "medium",
        "key_requirements": [],
        "keywords": keywords or [],
        "s3_key": f"eagle-knowledge-base/approved/{doc_id}.txt",
        "confidence_score": 0.9,
    }


# The exact query + items that triggered the production zero-results bug
MICROSCOPE_QUERY = "GSA Schedule microscope scientific equipment purchase simplified acquisition"

ACQUISITION_DOCS = [
    _doc(
        "gsa-schedule-guide",
        "GSA Federal Supply Schedule Ordering Guide",
        summary="Procedures for ordering supplies and services through GSA Schedule contracts.",
        keywords=["GSA", "schedule", "ordering", "FSS", "purchase"],
    ),
    _doc(
        "simplified-acq-procedures",
        "Simplified Acquisition Procedures Under SAT",
        summary="Guide to simplified acquisition procedures for purchases under the SAT threshold.",
        keywords=["simplified", "acquisition", "SAT", "purchase", "micro-purchase"],
    ),
    _doc(
        "nih-equipment-checklist",
        "NIH Scientific Equipment Acquisition Checklist",
        summary="Checklist for acquiring scientific equipment including microscopes and lab instruments.",
        keywords=["equipment", "scientific", "checklist", "NIH", "laboratory"],
    ),
    _doc(
        "far-part-8",
        "FAR Part 8 - Required Sources of Supply",
        summary="Federal Acquisition Regulation Part 8 covering required sources including GSA.",
        keywords=["FAR", "required sources", "GSA", "AbilityOne"],
    ),
    _doc(
        "unrelated-closeout",
        "Contract Closeout Procedures Manual",
        summary="Standard procedures for contract closeout and final payment processing.",
        topic="closeout",
        keywords=["closeout", "final payment", "deobligation"],
    ),
]


# ══════════════════════════════════════════════════════════════════════════════
# Fix 1: Model ID must have cross-region inference prefix
# ══════════════════════════════════════════════════════════════════════════════


def test_search_model_id_has_cross_region_prefix():
    """SEARCH_MODEL_ID must start with 'us.' for Bedrock cross-region inference.

    Without this prefix, Bedrock raises ValidationException and AI ranking
    fails silently, causing zero results.
    """
    assert kt.SEARCH_MODEL_ID.startswith("us."), (
        f"SEARCH_MODEL_ID '{kt.SEARCH_MODEL_ID}' is missing the 'us.' "
        f"cross-region inference prefix — this will cause ValidationException "
        f"in Bedrock and silently break knowledge search AI ranking"
    )


def test_config_knowledge_search_model_has_cross_region_prefix():
    """Config default for knowledge_search_model must also use 'us.' prefix."""
    from app.config import ModelConfig

    # Temporarily clear env var to test the default
    import os
    saved = os.environ.pop("KNOWLEDGE_SEARCH_MODEL", None)
    try:
        cfg = ModelConfig()
        assert cfg.knowledge_search_model.startswith("us."), (
            f"ModelConfig.knowledge_search_model default "
            f"'{cfg.knowledge_search_model}' is missing 'us.' prefix"
        )
    finally:
        if saved is not None:
            os.environ["KNOWLEDGE_SEARCH_MODEL"] = saved


# ══════════════════════════════════════════════════════════════════════════════
# Fix 2: Deterministic fallback — scored partial matching
# ══════════════════════════════════════════════════════════════════════════════


def test_deterministic_match_partial_query_returns_results():
    """Multi-word query must return docs matching SOME terms, not require ALL.

    This is the exact regression: the old code used
        all(t in searchable for t in query_terms)
    which returned zero results for 8-term queries.
    """
    results = kt._deterministic_match(
        MICROSCOPE_QUERY,
        [],
        ACQUISITION_DOCS,
    )

    # At least the GSA and simplified acquisition docs should match
    assert len(results) >= 2, (
        f"Deterministic fallback returned {len(results)} results for "
        f"'{MICROSCOPE_QUERY}' — should return partial matches"
    )

    # The unrelated closeout doc should NOT be in the results
    result_ids = [r["document_id"] for r in results]
    assert "unrelated-closeout" not in result_ids


def test_deterministic_match_exact_production_scenario():
    """Reproduce the exact production bug: 8-term query against 676 candidates.

    Before the fix, this returned 0 results. After the fix, it must return
    documents that partially match the query terms.
    """
    # Build a larger candidate set mimicking production (676 docs)
    items = list(ACQUISITION_DOCS)
    for i in range(670):
        items.append(
            _doc(
                f"filler-{i}",
                f"Acquisition Document {i}",
                summary=f"Generic acquisition regulation document number {i}.",
                keywords=["acquisition", "regulation"],
            )
        )

    results = kt._deterministic_match(MICROSCOPE_QUERY, [], items)

    # Must return results — the exact bug was returning zero
    assert len(results) > 0, (
        "REGRESSION: deterministic fallback returned zero results for "
        "multi-word query against large candidate set"
    )

    # The most relevant docs should rank near the top
    top_ids = [r["document_id"] for r in results[:10]]
    assert any(
        doc_id in top_ids
        for doc_id in ["gsa-schedule-guide", "simplified-acq-procedures", "nih-equipment-checklist"]
    ), f"Expected relevant docs in top 10, got: {top_ids}"


def test_deterministic_match_scores_title_higher_than_summary():
    """Title matches should rank higher than summary-only matches."""
    docs = [
        _doc("summary-only", "Unrelated Title", summary="GSA Schedule ordering guide"),
        _doc("title-match", "GSA Schedule Guide", summary="Unrelated summary text"),
    ]

    results = kt._deterministic_match("GSA Schedule", [], docs)

    assert len(results) == 2
    assert results[0]["document_id"] == "title-match", (
        "Title match should rank above summary-only match"
    )


def test_deterministic_match_keyword_boost():
    """Keyword matches should boost document ranking."""
    docs = [
        _doc("no-kw", "Equipment Guide", summary="Guide for equipment", keywords=[]),
        _doc("has-kw", "Some Document", summary="Some document text", keywords=["microscope"]),
    ]

    results = kt._deterministic_match("", ["microscope"], docs)

    assert len(results) >= 1
    assert results[0]["document_id"] == "has-kw"


def test_deterministic_match_exact_substring_bonus():
    """Exact query substring match should rank highest."""
    docs = [
        _doc("partial", "GSA Ordering", summary="Schedule procedures", keywords=["GSA"]),
        _doc("exact", "Other Doc", summary="Full GSA Schedule ordering reference", keywords=[]),
    ]

    results = kt._deterministic_match("GSA Schedule ordering", [], docs)

    assert len(results) >= 1
    assert results[0]["document_id"] == "exact", (
        "Exact substring match should rank above partial matches"
    )


def test_deterministic_match_empty_items():
    """Empty items list returns empty results."""
    assert kt._deterministic_match("any query", ["kw"], []) == []


def test_deterministic_match_no_query_no_keywords_returns_all():
    """With no query or keywords, all items are returned."""
    docs = [_doc("a", "Doc A"), _doc("b", "Doc B")]
    results = kt._deterministic_match("", [], docs)
    assert len(results) == 2


def test_deterministic_match_completely_unrelated_returns_empty():
    """Completely unrelated docs should not appear in results."""
    docs = [
        _doc("closeout", "Contract Closeout Procedures",
             summary="Final payment and deobligation steps",
             keywords=["closeout", "payment"]),
    ]

    results = kt._deterministic_match(
        "GSA Schedule microscope purchase", [], docs,
    )

    assert len(results) == 0, (
        "Completely unrelated docs should be filtered out by min_term_ratio"
    )


# ══════════════════════════════════════════════════════════════════════════════
# Integration: AI ranking failure must still produce results via fallback
# ══════════════════════════════════════════════════════════════════════════════


def _mock_scan_with_docs(monkeypatch, docs: list[dict]):
    """Patch DynamoDB to return the given docs from scan."""
    table = MagicMock()
    table.scan.return_value = {"Items": docs}
    ddb = MagicMock()
    ddb.Table.return_value = table
    monkeypatch.setattr(kt, "get_dynamodb", lambda: ddb)
    monkeypatch.setattr(kt, "BUILTIN_KB_ENTRIES", [])


def test_ai_ranking_failure_falls_back_with_results(monkeypatch):
    """When AI ranking raises an exception, fallback must still return matches.

    This is the exact production failure path: Bedrock ValidationException
    → AI returns [] → fallback must produce partial matches, not zero.
    """
    _mock_scan_with_docs(monkeypatch, ACQUISITION_DOCS)

    # Simulate AI ranking failure (the exact error from production)
    with patch.object(kt, "_ai_rank_documents", return_value=[]):
        result = kt.exec_knowledge_search(
            {"query": MICROSCOPE_QUERY, "topic": "acquisition_packages"},
            tenant_id="test-tenant",
        )

    assert result["count"] > 0, (
        "REGRESSION: knowledge_search returned zero results when AI ranking "
        "failed — deterministic fallback should have produced partial matches"
    )


def test_ai_ranking_bedrock_validation_error_falls_back(monkeypatch):
    """Bedrock ValidationException (wrong model ID) must not zero out results.

    _ai_rank_documents catches the exception internally and returns [].
    This test mocks the Bedrock client to throw the exact production error,
    letting the real _ai_rank_documents handle it and fall through to
    deterministic matching.
    """
    _mock_scan_with_docs(monkeypatch, ACQUISITION_DOCS)

    # Mock the Bedrock client to throw the exact error from production
    mock_bedrock = MagicMock()
    mock_bedrock.converse.side_effect = ClientError(
        error_response={
            "Error": {
                "Code": "ValidationException",
                "Message": (
                    "Invocation of model ID anthropic.claude-haiku-4-5-20251001-v1:0 "
                    "with on-demand throughput isn't supported."
                ),
            }
        },
        operation_name="Converse",
    )
    monkeypatch.setattr(kt, "_get_bedrock_runtime", lambda: mock_bedrock)

    result = kt.exec_knowledge_search(
        {"query": "GSA Schedule equipment purchase"},
        tenant_id="test-tenant",
    )

    # AI ranking fails → deterministic fallback should produce partial matches
    assert result["count"] > 0, (
        "REGRESSION: Bedrock model ID error caused zero results — "
        "fallback should still return partial matches"
    )


def test_ai_ranking_success_returns_ranked_results(monkeypatch):
    """When AI ranking works, its results are used directly."""
    _mock_scan_with_docs(monkeypatch, ACQUISITION_DOCS)

    # AI ranking returns the first two docs in order
    def good_ai_rank(query, keywords, items, limit, boost_hints=None):
        return [items[0], items[2]]

    with patch.object(kt, "_ai_rank_documents", side_effect=good_ai_rank):
        result = kt.exec_knowledge_search(
            {"query": "GSA equipment"},
            tenant_id="test-tenant",
        )

    assert result["count"] == 2
    assert result["results"][0]["document_id"] == "gsa-schedule-guide"
    assert result["results"][1]["document_id"] == "nih-equipment-checklist"


def test_knowledge_search_no_query_no_ai_ranking(monkeypatch):
    """Without a query, AI ranking is skipped and all items are returned."""
    # Only include docs that match the topic filter (DynamoDB filters server-side;
    # mock returns whatever we give it, so pre-filter to simulate the scan)
    acq_docs = [d for d in ACQUISITION_DOCS if d["primary_topic"] == "acquisition_packages"]
    _mock_scan_with_docs(monkeypatch, acq_docs)

    result = kt.exec_knowledge_search(
        {"topic": "acquisition_packages", "limit": 10},
        tenant_id="test-tenant",
    )

    assert result["count"] == len(acq_docs)
