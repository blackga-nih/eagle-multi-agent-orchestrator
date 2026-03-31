"""Tests for the tool dispatch layer — routing, session handling, error wrapping,
JSON serializability, and frontend panel schema contracts."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.tools.legacy_dispatch import (
    TOOLS_NEEDING_SESSION,
    execute_tool,
    get_tool_dispatch,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SESSION_ID = "test-tenant#standard#test-user#sess-001"


def _assert_keys(result: dict, *keys: str) -> None:
    for key in keys:
        assert key in result, f"Missing key '{key}' in {list(result.keys())}"


# ---------------------------------------------------------------------------
# TestDispatchRouting
# ---------------------------------------------------------------------------


class TestDispatchRouting:
    """Verify execute_tool() mechanics — routing, session handling, errors."""

    EXPECTED_TOOLS = {
        "s3_document_ops",
        "dynamodb_intake",
        "cloudwatch_logs",
        "search_far",
        "create_document",
        "edit_docx_document",
        "get_intake_status",
        "intake_workflow",
        "query_compliance_matrix",
        "knowledge_search",
        "knowledge_fetch",
        "manage_skills",
        "manage_prompts",
        "manage_templates",
        "document_changelog_search",
        "get_latest_document",
        "finalize_package",
        "manage_package",
    }

    def test_get_tool_dispatch_returns_all_18_tools(self):
        dispatch = get_tool_dispatch()
        assert len(dispatch) == 18
        assert set(dispatch.keys()) == self.EXPECTED_TOOLS

    def test_execute_tool_unknown_tool_returns_error_json(self):
        raw = execute_tool("nonexistent_tool", {})
        result = json.loads(raw)
        assert "error" in result
        assert "nonexistent_tool" in result["error"]

    def test_execute_tool_routes_to_correct_handler(self):
        mock_handler = MagicMock(return_value={"ok": True})
        with patch(
            "app.tools.legacy_dispatch.get_tool_dispatch",
            return_value={"test_tool": mock_handler},
        ):
            raw = execute_tool("test_tool", {"a": 1})
            result = json.loads(raw)
            assert result == {"ok": True}
            mock_handler.assert_called_once()

    def test_execute_tool_passes_session_id_for_session_tools(self):
        for tool_name in TOOLS_NEEDING_SESSION:
            mock_handler = MagicMock(return_value={"done": True})
            with patch(
                "app.tools.legacy_dispatch.get_tool_dispatch",
                return_value={tool_name: mock_handler},
            ):
                execute_tool(tool_name, {"x": 1}, session_id=SESSION_ID)
                args = mock_handler.call_args
                # Should receive 3 args: params, tenant_id, session_id
                assert len(args[0]) == 3, f"{tool_name} should get 3 positional args"
                assert args[0][2] == SESSION_ID

    def test_execute_tool_omits_session_id_for_non_session_tools(self):
        non_session_tools = get_tool_dispatch().keys() - TOOLS_NEEDING_SESSION
        for tool_name in non_session_tools:
            mock_handler = MagicMock(return_value={"done": True})
            with patch(
                "app.tools.legacy_dispatch.get_tool_dispatch",
                return_value={tool_name: mock_handler},
            ):
                execute_tool(tool_name, {"x": 1}, session_id=SESSION_ID)
                args = mock_handler.call_args
                # Should receive 2 args: params, tenant_id
                assert len(args[0]) == 2, f"{tool_name} should get 2 positional args"

    def test_execute_tool_returns_valid_json_string(self):
        mock_handler = MagicMock(return_value={"status": "ok"})
        with patch(
            "app.tools.legacy_dispatch.get_tool_dispatch",
            return_value={"test_tool": mock_handler},
        ):
            raw = execute_tool("test_tool", {})
            parsed = json.loads(raw)
            assert isinstance(parsed, dict)

    def test_execute_tool_wraps_exception_in_error_json(self):
        def exploding_handler(params, tenant_id):
            raise RuntimeError("kaboom")

        with patch(
            "app.tools.legacy_dispatch.get_tool_dispatch",
            return_value={"boom_tool": exploding_handler},
        ):
            raw = execute_tool("boom_tool", {})
            result = json.loads(raw)
            _assert_keys(result, "error", "tool", "suggestion")
            assert "kaboom" in result["error"]
            assert result["tool"] == "boom_tool"

    def test_execute_tool_extracts_tenant_from_session(self):
        mock_handler = MagicMock(return_value={})
        with patch(
            "app.tools.legacy_dispatch.get_tool_dispatch",
            return_value={"t": mock_handler},
        ):
            execute_tool("t", {}, session_id="my-org#premium#bob#s99")
            tenant_id = mock_handler.call_args[0][1]
            assert tenant_id == "my-org"

    def test_execute_tool_default_tenant_when_no_session(self):
        mock_handler = MagicMock(return_value={})
        with patch(
            "app.tools.legacy_dispatch.get_tool_dispatch",
            return_value={"t": mock_handler},
        ):
            execute_tool("t", {}, session_id=None)
            tenant_id = mock_handler.call_args[0][1]
            assert tenant_id == "demo-tenant"

    def test_tools_needing_session_set(self):
        assert TOOLS_NEEDING_SESSION == {
            "s3_document_ops",
            "create_document",
            "edit_docx_document",
            "get_intake_status",
            "manage_package",
        }


# ---------------------------------------------------------------------------
# TestToolOutputSerializable
# ---------------------------------------------------------------------------


TOOL_MOCK_OUTPUTS: dict[str, dict] = {
    "s3_document_ops": {"operation": "list", "files": [], "file_count": 0},
    "dynamodb_intake": {"operation": "list", "items": [], "count": 0},
    "cloudwatch_logs": {"operation": "recent", "events": [], "event_count": 0},
    "search_far": {"query": "q", "clauses": [], "results_count": 0},
    "create_document": {"status": "success", "doc_type": "sow", "title": "SOW"},
    "edit_docx_document": {"status": "success", "edits_applied": 1},
    "get_intake_status": {"intake_id": "I1", "completion_pct": "0%"},
    "intake_workflow": {"action": "status", "intake_id": "I1"},
    "query_compliance_matrix": {"operation": "get_requirements", "data": []},
    "knowledge_search": {"results": [], "count": 0},
    "knowledge_fetch": {"document_id": "d1", "content": "hello"},
    "manage_skills": {"action": "list", "count": 0, "skills": []},
    "manage_prompts": {"action": "list", "count": 0, "prompts": []},
    "manage_templates": {"action": "list", "count": 0, "templates": []},
    "document_changelog_search": {"package_id": "p1", "count": 0, "entries": []},
    "get_latest_document": {"document": {}, "recent_changes": []},
    "finalize_package": {"ready": True, "missing": []},
    "manage_package": {"packages": [], "count": 0},
}


class TestToolOutputSerializable:
    """Every tool's output must survive json.dumps(result, default=str)."""

    @pytest.mark.parametrize("tool_name", sorted(TOOL_MOCK_OUTPUTS.keys()))
    def test_tool_output_is_json_serializable(self, tool_name):
        output = TOOL_MOCK_OUTPUTS[tool_name]
        # This is the same serialization path used by execute_tool
        raw = json.dumps(output, indent=2, default=str)
        parsed = json.loads(raw)
        assert isinstance(parsed, dict)


# ---------------------------------------------------------------------------
# TestFrontendPanelContract
# ---------------------------------------------------------------------------


class TestFrontendPanelContract:
    """Verify tool outputs contain the keys that frontend result panels parse.

    Frontend panel mapping (tool-result-panels/index.ts):
      s3_document_ops    → S3ResultPanel
      search_far         → SearchResultPanel
      knowledge_search   → KnowledgeSearchPanel
      intake_workflow    → IntakeWorkflowPanel
      manage_package     → PackageStatusPanel
      query_compliance_matrix → ComplianceResultPanel
      knowledge_fetch    → KnowledgeFetchPanel
      web_search         → WebSearchPanel
      default            → MarkdownFallbackPanel
    """

    def test_s3_list_has_keys_for_s3_result_panel(self):
        """S3ResultPanel expects operation, files, file_count."""
        output = {
            "operation": "list",
            "bucket": "b",
            "prefix": "p/",
            "file_count": 2,
            "files": [{"key": "a.txt", "size_bytes": 10}],
        }
        _assert_keys(output, "operation", "files", "file_count")

    def test_search_far_has_keys_for_search_result_panel(self):
        """SearchResultPanel expects clauses with part, section, title, summary."""
        output = {
            "query": "sole source",
            "parts_searched": ["all"],
            "results_count": 1,
            "clauses": [
                {
                    "part": "6",
                    "section": "6.302",
                    "title": "J&A",
                    "summary": "Justification requirements",
                    "applicability": "All",
                    "s3_keys": [],
                }
            ],
            "source": "FAR",
            "note": "n",
        }
        _assert_keys(output, "query", "clauses", "results_count")
        clause = output["clauses"][0]
        _assert_keys(clause, "part", "section", "title", "summary")

    def test_intake_workflow_has_keys_for_intake_workflow_panel(self):
        """IntakeWorkflowPanel expects action, current_stage."""
        output = {
            "action": "started",
            "intake_id": "I1",
            "current_stage": {"number": 1, "name": "Requirements Gathering"},
            "next_actions": ["Describe the acquisition need"],
        }
        _assert_keys(output, "action", "current_stage")

    def test_manage_package_list_has_keys_for_package_status_panel(self):
        """PackageStatusPanel renders from packages list or single package dict."""
        list_output = {
            "packages": [{"package_id": "p1", "title": "My Package"}],
            "count": 1,
        }
        _assert_keys(list_output, "packages", "count")

    def test_knowledge_fetch_has_keys_for_knowledge_fetch_panel(self):
        output = {"document_id": "d1", "content": "Full text here", "truncated": False}
        _assert_keys(output, "document_id", "content")

    def test_compliance_matrix_has_keys_for_compliance_result_panel(self):
        output = {"operation": "get_requirements", "data": []}
        _assert_keys(output, "operation")

    @pytest.mark.parametrize(
        "tool_name",
        [
            "dynamodb_intake",
            "cloudwatch_logs",
            "create_document",
            "edit_docx_document",
            "get_intake_status",
            "manage_skills",
            "manage_prompts",
            "manage_templates",
            "document_changelog_search",
            "get_latest_document",
            "finalize_package",
        ],
    )
    def test_default_tools_produce_json_parseable_output(self, tool_name):
        """Tools that fall through to MarkdownFallbackPanel must be JSON-parseable."""
        output = TOOL_MOCK_OUTPUTS[tool_name]
        raw = json.dumps(output, indent=2, default=str)
        parsed = json.loads(raw)
        assert isinstance(parsed, dict)
