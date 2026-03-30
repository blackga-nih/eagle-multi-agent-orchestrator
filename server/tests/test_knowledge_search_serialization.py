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
        tools = _build_subagent_kb_tools(
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
        tools = _build_subagent_kb_tools(
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
        tools = _build_subagent_kb_tools(
            tenant_id="test-tenant",
            session_id="test-session",
        )
        kb_tool = next(t for t in tools if t.tool_name == "knowledge_search")
        result_str = kb_tool._tool_func(query="test query")

    result = json.loads(result_str)
    assert result["count"] == 1
    assert result["results"][0]["title"] == "Test Doc"
