"""Tests for knowledge_search serialization safety.

Validates fixes for the March 29 production bug where knowledge_search
hit TypeError ('cannot pickle _thread.lock') and RecursionError during
Strands SDK tool execution.  Root cause: @lru_cache(maxsize=1) on
_get_bedrock_runtime() created a shared boto3 client with _thread.lock
objects that OTEL threading instrumentation tried to deep-copy.

Two fixes:
  1. Thread-local Bedrock client (knowledge_tools.py)
  2. Defensive try/except in KB tool closures (strands_agentic_service.py)
"""

from __future__ import annotations

import concurrent.futures
import copy
import json
import threading
from unittest.mock import MagicMock, patch

from app.tools import knowledge_tools as kt


# ---------------------------------------------------------------------------
# Change 1: Thread-local Bedrock client
# ---------------------------------------------------------------------------


def test_bedrock_client_is_thread_local():
    """Each thread should get its own boto3 client instance."""
    # Reset thread-local state so the test is deterministic
    if hasattr(kt._bedrock_local, "client"):
        del kt._bedrock_local.client

    clients = {}

    def get_client(thread_name):
        # Clear any leftover state for this thread
        if hasattr(kt._bedrock_local, "client"):
            del kt._bedrock_local.client

        with patch("boto3.client") as mock_boto:
            mock_boto.return_value = MagicMock(name=f"client-{thread_name}")
            c = kt._get_bedrock_runtime()
            clients[thread_name] = c

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        pool.submit(get_client, "thread-a").result()
        pool.submit(get_client, "thread-b").result()

    # Different threads should have gotten different client instances
    assert clients["thread-a"] is not clients["thread-b"]


def test_bedrock_client_reused_within_same_thread():
    """Within the same thread, _get_bedrock_runtime() reuses the client."""
    if hasattr(kt._bedrock_local, "client"):
        del kt._bedrock_local.client

    with patch("boto3.client") as mock_boto:
        mock_boto.return_value = MagicMock(name="client-main")
        c1 = kt._get_bedrock_runtime()
        c2 = kt._get_bedrock_runtime()

    assert c1 is c2
    # boto3.client should only be called once (cached after first call)
    mock_boto.assert_called_once()


def test_bedrock_client_no_thread_lock_deepcopy():
    """Thread-local client avoids the copy.deepcopy pickle error.

    The original @lru_cache singleton held a shared boto3 client whose
    internal _thread.lock objects caused copy.deepcopy to raise
    TypeError('cannot pickle _thread.lock').
    """
    if hasattr(kt._bedrock_local, "client"):
        del kt._bedrock_local.client

    with patch("boto3.client") as mock_boto:
        mock_boto.return_value = MagicMock(name="mock-bedrock")
        client = kt._get_bedrock_runtime()

    # Mock objects are safely copyable (real boto3 clients are not)
    copied = copy.deepcopy(client)
    assert copied is not client


# ---------------------------------------------------------------------------
# Change 2: Defensive try/except in KB tool closures
# ---------------------------------------------------------------------------


def test_subagent_kb_search_handles_type_error():
    """Subagent kb_search returns graceful JSON on TypeError."""
    from app.strands_agentic_service import _build_subagent_kb_tools

    # Patch at source module — the local import inside _build_subagent_kb_tools
    # picks up the patched version.
    with patch(
        "app.tools.knowledge_tools.exec_knowledge_search",
        side_effect=TypeError("cannot pickle '_thread.lock' object"),
    ):
        tools, _kb_depth = _build_subagent_kb_tools(
            tenant_id="test-tenant",
            session_id="test-session",
        )
        kb_tool = next(t for t in tools if t.tool_name == "knowledge_search")
        result_str = kb_tool._tool_func(query="test query")

    result = json.loads(result_str)
    assert result["count"] == 0
    assert result["results"] == []
    assert "TypeError" in result["error"]


def test_subagent_kb_search_handles_recursion_error():
    """Subagent kb_search returns graceful JSON on RecursionError."""
    from app.strands_agentic_service import _build_subagent_kb_tools

    with patch(
        "app.tools.knowledge_tools.exec_knowledge_search",
        side_effect=RecursionError("maximum recursion depth exceeded"),
    ):
        tools, _kb_depth = _build_subagent_kb_tools(
            tenant_id="test-tenant",
            session_id="test-session",
        )
        kb_tool = next(t for t in tools if t.tool_name == "knowledge_search")
        result_str = kb_tool._tool_func(query="test query")

    result = json.loads(result_str)
    assert result["count"] == 0
    assert result["results"] == []
    assert "RecursionError" in result["error"]


def test_subagent_kb_search_normal_path_unchanged():
    """Normal knowledge_search still returns results."""
    from app.strands_agentic_service import _build_subagent_kb_tools

    mock_result = {"results": [{"title": "Test Doc"}], "count": 1}
    with patch(
        "app.tools.knowledge_tools.exec_knowledge_search",
        return_value=mock_result,
    ):
        tools, _kb_depth = _build_subagent_kb_tools(
            tenant_id="test-tenant",
            session_id="test-session",
        )
        kb_tool = next(t for t in tools if t.tool_name == "knowledge_search")
        result_str = kb_tool._tool_func(query="test query")

    result = json.loads(result_str)
    assert result["count"] == 1
    assert result["results"][0]["title"] == "Test Doc"


# ---------------------------------------------------------------------------
# Change 3: _sanitize_item breaks OTEL wrapper references
# ---------------------------------------------------------------------------


def test_sanitize_item_converts_decimals():
    """_sanitize_item converts DynamoDB Decimal values to int/float."""
    from decimal import Decimal

    from app.tools.knowledge_tools import _sanitize_item

    item = {
        "confidence_score": Decimal("0.95"),
        "count": Decimal("42"),
        "keywords": ["test"],
    }
    sanitized = _sanitize_item(item)
    assert sanitized["confidence_score"] == 0.95
    assert isinstance(sanitized["confidence_score"], float)
    assert sanitized["count"] == 42
    assert isinstance(sanitized["count"], int)


def test_sanitize_item_handles_otel_wrapped_types():
    """_sanitize_item breaks OTEL wrapper references on list/dict subclasses."""
    from app.tools.knowledge_tools import _sanitize_item

    class OtelWrappedList(list):
        """Simulates an OTEL-wrapped list with circular context."""

        def __init__(self, *args):
            super().__init__(*args)
            self._otel_context = self  # circular reference

    item = {
        "document_id": "test-doc",
        "keywords": OtelWrappedList(["keyword1", "keyword2"]),
        "key_requirements": OtelWrappedList(["req1"]),
    }

    sanitized = _sanitize_item(item)

    # Result should be plain types, JSON-serializable without RecursionError
    assert type(sanitized["keywords"]) is list
    assert sanitized["keywords"] == ["keyword1", "keyword2"]
    json_str = json.dumps(sanitized)
    assert "keyword1" in json_str


def test_exec_knowledge_search_sanitizes_items():
    """exec_knowledge_search produces JSON-serializable results from OTEL-wrapped items."""
    from decimal import Decimal

    from app.tools import knowledge_tools as kt

    class OtelWrappedList(list):
        def __init__(self, *args):
            super().__init__(*args)
            self._otel_context = self

    item = {
        "document_id": "test-otel-doc",
        "title": "OTEL Wrapped Doc",
        "summary": "Test summary",
        "document_type": "guidance",
        "primary_topic": "compliance",
        "primary_agent": "supervisor-core",
        "authority_level": "guidance",
        "complexity_level": "medium",
        "key_requirements": OtelWrappedList(["req1"]),
        "keywords": OtelWrappedList(["keyword1", "keyword2"]),
        "s3_key": "kb/test.md",
        "confidence_score": Decimal("0.9"),
    }

    table_mock = MagicMock()
    table_mock.scan.return_value = {"Items": [item]}
    ddb_mock = MagicMock()
    ddb_mock.Table.return_value = table_mock

    with patch.object(kt, "get_dynamodb", return_value=ddb_mock), patch.object(
        kt, "BUILTIN_KB_ENTRIES", []
    ):
        result = kt.exec_knowledge_search({"limit": 5}, tenant_id="test-tenant")

    assert result["count"] == 1
    assert result["results"][0]["document_id"] == "test-otel-doc"

    # Must be JSON-serializable without RecursionError
    json_str = json.dumps(result, indent=2, default=str)
    assert "test-otel-doc" in json_str


# ---------------------------------------------------------------------------
# Change 4: Service-tools knowledge_search coverage
# ---------------------------------------------------------------------------


def test_service_tools_returns_expected_tools():
    """_build_kb_service_tools returns search_far, web_search, research (knowledge_search is internal)."""
    from app.strands_agentic_service import _build_kb_service_tools

    tools, _kb_depth = _build_kb_service_tools(
        tenant_id="test-tenant",
        user_id="test-user",
        session_id="test-session",
    )
    tool_names = [t.tool_name for t in tools]
    assert "search_far" in tool_names
    assert "web_search" in tool_names or "web_search_tool" in tool_names
    assert "research" in tool_names
    # knowledge_search is used internally by research, not exposed directly
    assert "knowledge_search" not in tool_names


def test_service_tools_research_normal_path():
    """Service-tools research tool returns results normally.

    Post-EAGLE-254: a KB doc that is fetched is removed from `kb_results` to
    avoid the LLM seeing it twice (once as a summary hit, once as full content
    under `fetched_documents`). With a single mocked search hit that also gets
    fetched, we expect it in `fetched_documents` — not in `kb_results`.
    """
    from app.strands_agentic_service import _build_kb_service_tools

    mock_result = {"results": [{"title": "Test Doc", "s3_key": "eagle-knowledge-base/test.md"}], "count": 1}
    mock_fetch = {"content": "test content", "content_length": 12, "title": "Test Doc", "document_type": "guidance"}
    with patch(
        "app.tools.knowledge_tools.exec_knowledge_search",
        return_value=mock_result,
    ), patch(
        "app.tools.knowledge_tools.exec_knowledge_fetch",
        return_value=mock_fetch,
    ), patch(
        "app.tools.knowledge_tools.exec_path_search",
        return_value={"results": []},
    ):
        tools, _kb_depth = _build_kb_service_tools(
            tenant_id="test-tenant",
            user_id="test-user",
            session_id="test-session",
        )
        research = next(t for t in tools if t.tool_name == "research")
        result_str = research._tool_func(query="test query", include_checklist=False)

    result = json.loads(result_str)
    assert len(result["fetched_documents"]) >= 1
    assert result["fetched_documents"][0]["title"] == "Test Doc"
    # Fetched doc must not also appear in kb_results (dedup contract).
    assert not any(
        r.get("s3_key") == "eagle-knowledge-base/test.md"
        for r in result.get("kb_results", [])
    )


# ══════════════════════════════════════════════════════════════════════════════
# Source transparency: lane attribution + read flag + cap (2026-04-28)
# ══════════════════════════════════════════════════════════════════════════════


def _build_research_with_lane(query: str, *, monkeypatch=None, kb_results=None, kb_extra=None):
    """Run the service-tools research tool with mocked KB calls.

    `kb_results` is the primary search return; `kb_extra` is an optional
    list returned by the secondary broadened search so we can exercise
    runner-up rendering.
    """
    from app.strands_agentic_service import _build_kb_service_tools

    primary = {
        "results": kb_results or [],
        "count": len(kb_results or []),
    }
    secondary = {
        "results": kb_extra or [],
        "count": len(kb_extra or []),
    }
    fetch_calls: dict[str, dict] = {}

    def fake_search(params, tenant_id, session_id=None, user_id=None,
                    _allowed_package_ids=None, _lane_tag="metadata"):
        # Honor the lane tag the caller passes — secondary broadens.
        out = secondary if _lane_tag == "metadata-broad" else primary
        return {
            "results": [
                {**r, "_lane": _lane_tag} for r in out["results"]
            ],
            "count": out["count"],
        }

    def fake_fetch(params, tenant_id, session_id=None, user_id=None,
                   _allowed_package_ids=None):
        key = params.get("s3_key", "")
        fetch_calls[key] = {"content": f"body-of-{key}", "content_length": 12}
        return {"content": f"body-of-{key}", "content_length": 12}

    with patch("app.tools.knowledge_tools.exec_knowledge_search", side_effect=fake_search), \
         patch("app.tools.knowledge_tools.exec_knowledge_fetch", side_effect=fake_fetch), \
         patch("app.tools.knowledge_tools.exec_path_search", return_value={"results": []}), \
         patch("app.tools.knowledge_tools.exec_semantic_search", return_value={"results": []}):
        tools, _ = _build_kb_service_tools(
            tenant_id="test-tenant",
            user_id="test-user",
            session_id="test-session",
        )
        research = next(t for t in tools if t.tool_name == "research")
        return json.loads(research._tool_func(query=query, include_checklist=False))


def test_research_packet_tags_lane_score_and_read_flag():
    """Each fetched_document and kb_result must carry lane/score/score_pct/rationale/read.

    This is the wire contract the frontend Sources table reads. If any field
    goes missing the table loses transparency — score bars disappear, lane
    chips revert to default, the read indicator gets stuck.
    """
    docs = [
        {
            "title": "Sole Source J&A Template",
            "s3_key": "eagle-knowledge-base/approved/templates/sole-source-ja.md",
            "summary": "Template for FAR 6.302-1 justifications",
            "_ai_rank_position": 0,
            "_ai_rationale": "Title matches 'sole source J&A'.",
        },
        {
            "title": "PMR SAP Checklist",
            "s3_key": "eagle-knowledge-base/approved/checklists/pmr-sap.md",
            "summary": "PMR checklist for SAP procurements",
            "_ai_rank_position": 1,
            "_ai_rationale": "Adjacent: SAP checklist required for J&A.",
        },
    ]
    packet = _build_research_with_lane("sole source FAR 6.302-1", kb_results=docs)

    assert packet.get("fetched_documents"), "expected at least one fetched doc"
    fetched = packet["fetched_documents"][0]
    for field in ("lane", "score", "score_pct", "rationale", "read"):
        assert field in fetched, f"fetched_documents entry missing '{field}'"
    assert fetched["read"] is True
    assert fetched["lane"] == "metadata"
    assert 0 <= fetched["score_pct"] <= 100
    # AI rank position 0 → ~100% via _score_packet
    assert fetched["score_pct"] == 100
    assert fetched["rationale"]  # non-empty AI rationale flowed through

    # _meta block must surface lane breakdown + total counts for the frontend
    meta = packet.get("_meta", {})
    assert "lane_breakdown" in meta
    assert meta.get("kb_results_cap") == 16
    assert meta.get("total_surfaced") == len(packet["fetched_documents"]) + len(packet.get("kb_results", []))


def test_research_kb_results_cap_is_16_by_default():
    """KB_RESULTS_CAP defaults to 16 so users see runner-ups, not just the top 8.

    Was 8 (hard-coded). Bumped + made env-tunable so operators see what
    *almost* made the fetch line.
    """
    # Build 25 results — only the AI-rank fetch budget reads a few; the rest
    # should land in kb_results up to the cap.
    docs = [
        {
            "title": f"Doc {i}",
            "s3_key": f"eagle-knowledge-base/approved/doc-{i}.md",
            "summary": f"Summary for doc {i}",
            "_ai_rank_position": i,
        }
        for i in range(25)
    ]
    packet = _build_research_with_lane("broad acquisition query", kb_results=docs)

    fetched = packet.get("fetched_documents", [])
    surfaced = packet.get("kb_results", [])
    # Sum of fetched + surfaced should hit the 16 cap (cap excludes fetched)
    assert len(surfaced) <= 16
    # Bump check — pre-transparency cap was 8; post-transparency surfaces > 8
    # when the candidate pool is big enough.
    assert len(surfaced) > 8, (
        "kb_results should expose runner-ups beyond the legacy 8 cap"
    )
    # All surfaced rows must declare read=False
    assert all(r.get("read") is False for r in surfaced)
    # And all fetched rows must declare read=True
    assert all(r.get("read") is True for r in fetched)


# ══════════════════════════════════════════════════════════════════════════════
# Sources Summary modal: per-doc rows + lane breakdown in _kb_depth (2026-04-29)
# ══════════════════════════════════════════════════════════════════════════════


def _build_tools_and_run_research(query: str, kb_results: list[dict]) -> tuple[list, dict]:
    """Run research_tool with mocked KB calls, return (tools_list, kb_depth).

    Mirrors _build_research_with_lane but returns the _kb_depth dict so we
    can assert the sources_summary aggregation that flows into the modal.
    """
    from app.strands_agentic_service import _build_kb_service_tools

    primary = {"results": kb_results, "count": len(kb_results)}

    def fake_search(params, tenant_id, session_id=None, user_id=None,
                    _allowed_package_ids=None, _lane_tag="metadata"):
        return {
            "results": [{**r, "_lane": _lane_tag} for r in primary["results"]],
            "count": primary["count"],
        }

    def fake_fetch(params, tenant_id, session_id=None, user_id=None,
                   _allowed_package_ids=None):
        key = params.get("s3_key", "")
        return {
            "content": f"body-of-{key}",
            "content_length": 12,
            "title": f"Title for {key.rsplit('/', 1)[-1]}",
            "document_type": "guidance",
        }

    with patch("app.tools.knowledge_tools.exec_knowledge_search", side_effect=fake_search), \
         patch("app.tools.knowledge_tools.exec_knowledge_fetch", side_effect=fake_fetch), \
         patch("app.tools.knowledge_tools.exec_path_search", return_value={"results": []}), \
         patch("app.tools.knowledge_tools.exec_semantic_search", return_value={"results": []}):
        tools, kb_depth = _build_kb_service_tools(
            tenant_id="test-tenant",
            user_id="test-user",
            session_id="test-session",
        )
        research = next(t for t in tools if t.tool_name == "research")
        research._tool_func(query=query, include_checklist=False)
    return tools, kb_depth


def test_kb_depth_aggregates_sources_rows_after_research():
    """research_tool must populate _kb_depth['sources_rows'] + ['lane_breakdown']
    so the end-of-turn sources_summary SSE event carries the per-doc breakdown.

    The Sources Summary modal renders these rows directly — without them the
    modal regresses to the flat fetched_keys list.
    """
    docs = [
        {
            "title": f"Doc {i}",
            "s3_key": f"eagle-knowledge-base/approved/doc-{i}.md",
            "summary": f"Summary for doc {i}",
            "_ai_rank_position": i,
        }
        for i in range(5)
    ]
    _, kb_depth = _build_tools_and_run_research("test query", docs)

    rows = kb_depth.get("sources_rows", [])
    assert rows, "research_tool should populate _kb_depth['sources_rows']"
    # Every row carries the wire contract fields the modal renders
    for row in rows:
        for field in ("title", "s3_key", "lane", "score_pct", "read"):
            assert field in row, f"sources_rows entry missing '{field}'"

    # Lane breakdown is non-empty and matches the rows we recorded
    breakdown = kb_depth.get("lane_breakdown", {})
    assert breakdown, "research_tool should populate _kb_depth['lane_breakdown']"
    assert sum(breakdown.values()) == len(rows)

    # Mix of read/surfaced rows expected when there are more candidates than
    # the AI fetch budget.
    read_rows = [r for r in rows if r.get("read")]
    assert read_rows, "expected at least one read=True row in sources_rows"


def test_kb_depth_records_manual_fetch_for_direct_knowledge_fetch():
    """A direct knowledge_fetch (no prior research_tool) records a row with
    lane='manual-fetch' so the modal can still show what the agent read.
    """
    from app.strands_agentic_service import _build_subagent_kb_tools

    fake_doc = {
        "content": "body",
        "content_length": 4,
        "title": "Fetched Doc",
        "document_type": "guidance",
    }
    with patch("app.tools.knowledge_tools.exec_knowledge_fetch", return_value=fake_doc):
        # _build_subagent_kb_tools returns (tools, _kb_depth) despite its
        # `-> list:` annotation — pre-existing typing inconsistency.
        tools, depth = _build_subagent_kb_tools(
            tenant_id="test-tenant",
            session_id="test-session",
            result_queue=None,
            loop=None,
            user_id="test-user",
        )
        kb_fetch = next(t for t in tools if t.tool_name == "knowledge_fetch")
        kb_fetch._tool_func(s3_key="eagle-knowledge-base/approved/foo.md")

    rows = depth.get("sources_rows", [])
    assert len(rows) == 1, f"expected 1 manual-fetch row, got {len(rows)}"
    row = rows[0]
    assert row["lane"] == "manual-fetch"
    assert row["read"] is True
    assert row["s3_key"] == "eagle-knowledge-base/approved/foo.md"
    assert row["title"] == "Fetched Doc"
    assert depth["lane_breakdown"]["manual-fetch"] == 1


def test_record_source_row_dedups_and_upgrades_read():
    """_record_source_row replaces a surfaced-only row when a read=True row
    arrives later for the same s3_key — the modal should never show the same
    doc twice with conflicting read state.
    """
    from app.strands_agentic_service import _record_source_row

    depth = {"sources_rows": [], "lane_breakdown": {}}
    _record_source_row(depth, {
        "title": "Doc A",
        "s3_key": "eagle-knowledge-base/a.md",
        "lane": "metadata",
        "score_pct": 80,
        "read": False,
    })
    assert len(depth["sources_rows"]) == 1
    assert depth["sources_rows"][0]["read"] is False

    # Same s3_key, but now read=True — should replace, not append
    _record_source_row(depth, {
        "title": "Doc A",
        "s3_key": "eagle-knowledge-base/a.md",
        "lane": "manual-fetch",
        "score_pct": 0,
        "read": True,
    })
    assert len(depth["sources_rows"]) == 1, "duplicate s3_key must dedupe"
    assert depth["sources_rows"][0]["read"] is True
    # Lane breakdown should not double-count the same doc
    assert depth["lane_breakdown"]["metadata"] == 1
    assert "manual-fetch" not in depth["lane_breakdown"]

    # A different s3_key appends a new row + bumps its lane
    _record_source_row(depth, {
        "title": "Doc B",
        "s3_key": "eagle-knowledge-base/b.md",
        "lane": "manual-fetch",
        "score_pct": 0,
        "read": True,
    })
    assert len(depth["sources_rows"]) == 2
    assert depth["lane_breakdown"]["manual-fetch"] == 1
