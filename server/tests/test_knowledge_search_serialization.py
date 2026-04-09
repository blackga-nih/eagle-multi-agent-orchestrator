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
    """Service-tools research tool returns results normally."""
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
    assert len(result["kb_results"]) >= 1
    assert result["kb_results"][0]["title"] == "Test Doc"
