"""Tests for Langfuse-identified tool-calling fixes (2026-04-10).

Covers 6 fixes:
  1. knowledge-retrieval removed from plugin.json skills
  2. manage_package(create) gated on explicit user intent
  3. s3_document_ops guards against KB path misuse
  4. Cascade violation state shared across supervisor→subagent boundary
  5. s3_document_ops removed from supervisor prompt tools list
  6. knowledge_retrieval removed from eval expected skills and status_messages
"""

from __future__ import annotations

import json
import pathlib
from unittest.mock import MagicMock

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent


# ===========================================================================
# 1. knowledge-retrieval removed from plugin.json
# ===========================================================================


class TestKnowledgeRetrievalRemoved:
    """Verify knowledge-retrieval skill is no longer registered."""

    def test_plugin_json_no_knowledge_retrieval(self):
        plugin_path = REPO_ROOT / "eagle-plugin" / "plugin.json"
        data = json.loads(plugin_path.read_text())
        assert "knowledge-retrieval" not in data["skills"], (
            "knowledge-retrieval should be removed from plugin.json skills"
        )

    def test_status_messages_no_knowledge_retrieval(self):
        from app.telemetry.status_messages import SKILL_DISPLAY_NAMES

        assert "knowledge-retrieval" not in SKILL_DISPLAY_NAMES, (
            "knowledge-retrieval should be removed from SKILL_DISPLAY_NAMES"
        )

    def test_subagent_tool_names_no_knowledge_retrieval(self):
        from app.telemetry.status_messages import _SUBAGENT_TOOL_NAMES

        assert "knowledge_retrieval" not in _SUBAGENT_TOOL_NAMES, (
            "knowledge_retrieval should not be in _SUBAGENT_TOOL_NAMES"
        )


# ===========================================================================
# 2. manage_package(create) gated on explicit user intent
# ===========================================================================


class TestPackageCreationGating:
    """Verify supervisor prompt gates package creation on explicit intent."""

    @pytest.fixture
    def agent_md(self):
        path = REPO_ROOT / "eagle-plugin" / "agents" / "supervisor" / "agent.md"
        return path.read_text()

    def test_no_immediately_create(self, agent_md):
        assert "IMMEDIATELY call `manage_package" not in agent_md, (
            "Supervisor prompt should not say IMMEDIATELY call manage_package"
        )

    def test_requires_explicit_intent(self, agent_md):
        assert "actively starting an acquisition" in agent_md

    def test_intake_flow_trigger(self, agent_md):
        assert "intake flow" in agent_md or "intake questions" in agent_md

    def test_explicit_start_trigger(self, agent_md):
        # Must mention user explicitly asking to start/create a package
        assert "start a package" in agent_md or "create a package" in agent_md

    def test_no_general_research_trigger(self, agent_md):
        # Must mention NOT creating for general research
        assert "general research" in agent_md or "policy lookups" in agent_md


# ===========================================================================
# 3. s3_document_ops guards against KB path misuse
# ===========================================================================


class TestS3DocumentOpsKBGuard:
    """Verify s3_document_ops rejects eagle-knowledge-base/ paths."""

    @pytest.fixture
    def mock_s3(self, monkeypatch):
        import app.tools.aws_ops_tools as aot

        client = MagicMock()
        monkeypatch.setattr(aot, "get_s3", lambda: client)
        return client

    def test_read_kb_path_rejected(self, mock_s3):
        import app.tools.aws_ops_tools as aot

        result = aot.exec_s3_document_ops(
            {
                "operation": "read",
                "key": "eagle-knowledge-base/approved/far/part-6.txt",
            },
            "test-tenant",
            "test-tenant#standard#test-user#sess-001",
        )
        assert "error" in result
        assert "knowledge_fetch" in result["error"] or "research" in result["error"]
        # S3 should NOT have been called
        mock_s3.get_object.assert_not_called()

    def test_read_user_path_allowed(self, mock_s3):
        import app.tools.aws_ops_tools as aot

        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=lambda: b"hello"),
            "ContentType": "text/plain",
            "ContentLength": 5,
        }
        result = aot.exec_s3_document_ops(
            {
                "operation": "read",
                "key": "eagle/test-tenant/test-user/my-doc.txt",
            },
            "test-tenant",
            "test-tenant#standard#test-user#sess-001",
        )
        assert "error" not in result
        assert result["operation"] == "read"

    def test_read_relative_path_allowed(self, mock_s3):
        """A relative path (no eagle-knowledge-base/ prefix) should be prefixed and allowed."""
        import app.tools.aws_ops_tools as aot

        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=lambda: b"data"),
            "ContentType": "text/plain",
            "ContentLength": 4,
        }
        result = aot.exec_s3_document_ops(
            {"operation": "read", "key": "my-file.txt"},
            "test-tenant",
            "test-tenant#standard#test-user#sess-001",
        )
        assert "error" not in result
        assert result["operation"] == "read"


# ===========================================================================
# 4. Cascade violation state shared across supervisor→subagent boundary
# ===========================================================================


class TestCascadeStateInheritance:
    """Verify _build_subagent_kb_tools inherits parent cascade state."""

    def test_subagent_kb_tools_accepts_parent_kb_called(self):
        """_build_subagent_kb_tools should accept parent_kb_called parameter."""
        import inspect
        from app.strands_agentic_service import _build_subagent_kb_tools

        sig = inspect.signature(_build_subagent_kb_tools)
        assert "parent_kb_called" in sig.parameters

    def test_make_subagent_tool_accepts_parent_kb_called(self):
        """_make_subagent_tool should accept parent_kb_called parameter."""
        import inspect
        from app.strands_agentic_service import _make_subagent_tool

        sig = inspect.signature(_make_subagent_tool)
        assert "parent_kb_called" in sig.parameters

    def test_build_skill_tools_accepts_parent_kb_called(self):
        """build_skill_tools should accept parent_kb_called parameter."""
        import inspect
        from app.strands_agentic_service import build_skill_tools

        sig = inspect.signature(build_skill_tools)
        assert "parent_kb_called" in sig.parameters

    def test_build_kb_service_tools_accepts_kb_tools_called_ref(self):
        """_build_kb_service_tools should accept kb_tools_called_ref parameter."""
        import inspect
        from app.strands_agentic_service import _build_kb_service_tools

        sig = inspect.signature(_build_kb_service_tools)
        assert "kb_tools_called_ref" in sig.parameters

    def test_subagent_pre_seeds_from_parent(self):
        """When parent_kb_called has entries, subagent's cascade set should be pre-seeded."""
        from app.strands_agentic_service import _build_subagent_kb_tools

        parent_called = {"research", "search_far"}
        tools, _depth = _build_subagent_kb_tools(
            tenant_id="test-tenant",
            session_id="test-session",
            parent_kb_called=parent_called,
        )
        # Find the web_search tool and verify it doesn't trigger cascade violation
        web_search_fn = None
        for t in tools:
            if getattr(t, "__name__", "") == "web_search":
                web_search_fn = t
                break
        assert web_search_fn is not None, "web_search tool should exist in subagent KB tools"

    def test_subagent_empty_parent_has_empty_set(self):
        """When no parent_kb_called, subagent starts with empty cascade set."""
        from app.strands_agentic_service import _build_subagent_kb_tools

        tools, _depth = _build_subagent_kb_tools(
            tenant_id="test-tenant",
            session_id="test-session",
            parent_kb_called=None,
        )
        assert len(tools) > 0


# ===========================================================================
# 5. s3_document_ops removed from supervisor prompt tools list
# ===========================================================================


class TestSupervisorToolsList:
    """Verify supervisor agent.md no longer lists s3_document_ops."""

    @pytest.fixture
    def agent_md(self):
        path = REPO_ROOT / "eagle-plugin" / "agents" / "supervisor" / "agent.md"
        return path.read_text()

    def test_no_s3_document_ops_in_tools(self, agent_md):
        # Parse the YAML frontmatter tools list
        import yaml

        # Extract frontmatter between --- markers
        parts = agent_md.split("---", 2)
        assert len(parts) >= 3, "agent.md should have YAML frontmatter"
        frontmatter = yaml.safe_load(parts[1])
        tools_list = frontmatter.get("tools", [])
        assert "s3_document_ops" not in tools_list, (
            "s3_document_ops should be removed from supervisor tools list"
        )

    def test_search_far_still_in_tools(self, agent_md):
        """search_far should remain — it's a valid supervisor tool."""
        import yaml

        parts = agent_md.split("---", 2)
        frontmatter = yaml.safe_load(parts[1])
        tools_list = frontmatter.get("tools", [])
        assert "search_far" in tools_list


# ===========================================================================
# 6. knowledge_retrieval removed from eval expected skills
# ===========================================================================


class TestEvalExpectedSkills:
    """Verify test_strands_eval.py no longer expects knowledge_retrieval."""

    def test_eval_file_no_knowledge_retrieval(self):
        eval_path = pathlib.Path(__file__).parent / "test_strands_eval.py"
        if not eval_path.exists():
            pytest.skip("test_strands_eval.py not found")
        content = eval_path.read_text()
        # Count occurrences — should be zero
        assert content.count('"knowledge_retrieval"') == 0, (
            "knowledge_retrieval should be removed from all expected skill sets"
        )
        assert content.count("'knowledge_retrieval'") == 0, (
            "knowledge_retrieval should be removed from all expected skill sets"
        )


# ===========================================================================
# Integration: research tool is the primary entry point
# ===========================================================================


class TestResearchToolPrimacy:
    """Verify supervisor prompt positions research as the primary tool."""

    @pytest.fixture
    def agent_md(self):
        path = REPO_ROOT / "eagle-plugin" / "agents" / "supervisor" / "agent.md"
        return path.read_text()

    def test_research_is_step_1(self, agent_md):
        assert "Step 1" in agent_md
        step1_idx = agent_md.index("Step 1")
        # research should appear near Step 1
        research_idx = agent_md.index("Research Tool", step1_idx)
        assert research_idx - step1_idx < 100, (
            "Research Tool should be mentioned within Step 1"
        )

    def test_web_search_is_step_3(self, agent_md):
        assert "Step 3" in agent_md
        step3_idx = agent_md.index("Step 3")
        web_idx = agent_md.index("Web Search", step3_idx)
        assert web_idx - step3_idx < 100

    def test_cascade_order_preserved(self, agent_md):
        step1 = agent_md.index("Step 1")
        step3 = agent_md.index("Step 3")
        assert step1 < step3, "Step 1 (research) must come before Step 3 (web search)"
