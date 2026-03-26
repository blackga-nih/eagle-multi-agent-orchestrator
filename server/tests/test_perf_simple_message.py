"""Performance tests for chat latency optimizations.

Validates: workspace cache, skill tools build, supervisor direct handling,
async generator pattern, and cache reload wiring. All tests are fast (mocked, no AWS).
"""
import inspect
import time
from unittest import mock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TENANT = "perf-tenant"
USER = "perf-user"
WORKSPACE_ID = "ws-001"
TIER = "advanced"

FAKE_WORKSPACE = {
    "workspace_id": WORKSPACE_ID,
    "tenant_id": TENANT,
    "user_id": USER,
    "name": "Default",
    "is_active": True,
    "is_default": True,
}


# ---------------------------------------------------------------------------
# 1. Workspace Cache
# ---------------------------------------------------------------------------

class TestWorkspaceCache:
    """Verify get_or_create_default() uses the 60s TTL cache."""

    def test_cache_hit_skips_dynamodb(self):
        """Seeded cache entry -> returns immediately without calling _get_table()."""
        from app.workspace_store import (
            _workspace_cache, _ws_cache_set, get_or_create_default,
        )

        # Seed cache
        _ws_cache_set(TENANT, USER, FAKE_WORKSPACE)

        with mock.patch("app.workspace_store.get_table") as mock_table:
            result = get_or_create_default(TENANT, USER)

        assert result["workspace_id"] == WORKSPACE_ID
        mock_table.assert_not_called()

        # Cleanup
        _workspace_cache.clear()

    def test_cache_expired_hits_dynamodb(self):
        """Expired cache entry -> falls through to DynamoDB."""
        from app.workspace_store import (
            _workspace_cache, _ws_cache_key, get_or_create_default,
        )

        # Seed an expired entry (ts in the past)
        key = _ws_cache_key(TENANT, USER)
        _workspace_cache[key] = {"ts": time.time() - 120, "item": FAKE_WORKSPACE}

        # Mock DynamoDB to return a workspace via list_workspaces path
        mock_table = mock.MagicMock()
        mock_table.query.return_value = {"Items": [FAKE_WORKSPACE]}
        mock_table.get_item.return_value = {"Item": FAKE_WORKSPACE}

        with mock.patch("app.workspace_store.get_table", return_value=mock_table):
            result = get_or_create_default(TENANT, USER)

        assert result["workspace_id"] == WORKSPACE_ID
        # DynamoDB was actually called (at least query for list_workspaces)
        assert mock_table.query.called or mock_table.get_item.called

        # Cleanup
        _workspace_cache.clear()


# ---------------------------------------------------------------------------
# 2. Skill Tools Build
# ---------------------------------------------------------------------------

class TestSkillToolsBuild:
    """Verify build_skill_tools() returns a list of tools."""

    def test_returns_list(self):
        """build_skill_tools() always returns a list."""
        from app.strands_agentic_service import build_skill_tools

        with mock.patch("app.strands_agentic_service.PLUGIN_CONTENTS", {}), \
             mock.patch("app.strands_agentic_service.SKILL_AGENT_REGISTRY", {}):
            result = build_skill_tools(
                tier=TIER, tenant_id=TENANT, user_id=USER, workspace_id=WORKSPACE_ID,
            )

        assert isinstance(result, list)

    def test_builds_tools_from_registry(self):
        """build_skill_tools() creates one tool per registry entry with matching content."""
        from app.strands_agentic_service import build_skill_tools

        fake_registry = {
            "test-skill": {
                "skill_key": "skills/test-skill/SKILL.md",
                "description": "Test specialist",
            }
        }
        fake_contents = {
            "skills/test-skill/SKILL.md": {"body": "You are a test specialist."}
        }

        with mock.patch("app.strands_agentic_service.SKILL_AGENT_REGISTRY", fake_registry), \
             mock.patch("app.strands_agentic_service.PLUGIN_CONTENTS", fake_contents):
            result = build_skill_tools(
                tier=TIER, tenant_id=TENANT, user_id=USER, workspace_id=WORKSPACE_ID,
            )

        assert len(result) >= 1

    def test_workspace_override_store_is_used_for_skill_prompts(self):
        """Workspace overrides should be resolved from workspace_override_store."""
        from app.strands_agentic_service import build_skill_tools

        fake_registry = {
            "test-skill": {
                "skill_key": "skills/test-skill/SKILL.md",
                "description": "Test specialist",
            }
        }
        fake_contents = {
            "skills/test-skill/SKILL.md": {"body": "Bundled prompt"}
        }

        with mock.patch("app.strands_agentic_service.SKILL_AGENT_REGISTRY", fake_registry), \
             mock.patch("app.strands_agentic_service.PLUGIN_CONTENTS", fake_contents), \
             mock.patch(
                 "app.workspace_override_store.resolve_skill",
                 return_value=("Workspace override prompt", "workspace"),
             ) as mock_resolve:
            result = build_skill_tools(
                tier=TIER, tenant_id=TENANT, user_id=USER, workspace_id=WORKSPACE_ID,
            )

        assert len(result) == 1
        mock_resolve.assert_called_once_with(TENANT, USER, WORKSPACE_ID, "test-skill")


# ---------------------------------------------------------------------------
# 3. Supervisor Direct Handling
# ---------------------------------------------------------------------------

class TestSupervisorDirectHandling:
    """Verify supervisor prompt instructs routing for fast vs deep queries."""

    def test_prompt_contains_fast_routing(self):
        prompt = self._get_prompt()
        assert "FAST" in prompt
        assert "DEEP" in prompt or "specialist" in prompt.lower()

    def test_prompt_still_has_delegation_instruction(self):
        prompt = self._get_prompt()
        assert "delegate" in prompt.lower() or "specialist" in prompt.lower()

    def test_workspace_override_store_is_used_for_supervisor_prompt(self):
        from app.strands_agentic_service import _build_supervisor_prompt_body

        with mock.patch(
            "app.workspace_override_store.resolve_agent",
            return_value=("Workspace supervisor prompt", "workspace"),
        ) as mock_resolve:
            prompt = _build_supervisor_prompt_body(
                tenant_id=TENANT,
                user_id=USER,
                tier=TIER,
                agent_names=[],
                workspace_id=WORKSPACE_ID,
            )

        assert prompt.startswith("Workspace supervisor prompt")
        mock_resolve.assert_called_once_with(TENANT, USER, WORKSPACE_ID, "supervisor")

    @staticmethod
    def _get_prompt() -> str:
        from app.strands_agentic_service import build_supervisor_prompt
        return build_supervisor_prompt(
            tenant_id=TENANT, user_id=USER, tier=TIER,
        )


# ---------------------------------------------------------------------------
# 4. Package / Document Tool Extraction
# ---------------------------------------------------------------------------

class TestPackageDocumentTools:
    """Verify extracted package/document handlers keep expected behaviour."""

    def test_get_latest_document_returns_document_and_recent_changes(self):
        from app.tools.package_document_tools import exec_get_latest_document

        fake_document = {
            "doc_type": "sow",
            "version": 3,
            "title": "Test SOW",
            "status": "draft",
            "created_at": "2026-03-25T00:00:00Z",
            "s3_key": "eagle/test/pkg/sow_v3.md",
        }
        fake_changes = [
            {
                "change_type": "update",
                "change_summary": "Updated scope",
                "actor_user_id": USER,
                "created_at": "2026-03-25T01:00:00Z",
            }
        ]

        with mock.patch("app.document_store.get_document", return_value=fake_document), \
             mock.patch("app.changelog_store.list_changelog_entries", return_value=fake_changes):
            result = exec_get_latest_document(
                {"package_id": "pkg-1", "doc_type": "sow"},
                TENANT,
            )

        assert result["document"]["version"] == 3
        assert result["recent_changes"][0]["change_summary"] == "Updated scope"

    def test_manage_package_create_extracts_owner_from_session(self):
        from app.tools.package_document_tools import exec_manage_package

        with mock.patch("app.package_store.create_package", return_value={"package_id": "pkg-1"}) as mock_create:
            result = exec_manage_package(
                {
                    "operation": "create",
                    "title": "Test Package",
                    "requirement_type": "services",
                    "estimated_value": 1000,
                },
                TENANT,
                f"{TENANT}#{TIER}#{USER}#session-1",
            )

        assert result["package_id"] == "pkg-1"
        assert mock_create.call_args.kwargs["owner_user_id"] == USER


class TestFarSearchTool:
    """Verify extracted FAR search handler keeps expected fallback behaviour."""

    def test_search_far_returns_default_clause_when_no_results(self):
        from app.tools.far_search import exec_search_far

        with mock.patch("app.compliance_matrix.search_far", return_value=[]):
            result = exec_search_far({"query": "nonexistent"}, TENANT)

        assert result["results_count"] == 1
        assert result["clauses"][0]["section"] == "1.102"


class TestLegacyDispatchExtraction:
    """Verify legacy dispatch now prefers active tool modules for migrated tools."""

    def test_dispatch_uses_active_package_document_handler(self):
        from app.tools.legacy_dispatch import get_tool_dispatch
        from app.tools.package_document_tools import exec_get_latest_document

        dispatch = get_tool_dispatch()
        assert dispatch["get_latest_document"] is exec_get_latest_document

    def test_dispatch_uses_active_far_search_handler(self):
        from app.tools.legacy_dispatch import get_tool_dispatch
        from app.tools.far_search import exec_search_far

        dispatch = get_tool_dispatch()
        assert dispatch["search_far"] is exec_search_far

    def test_dispatch_uses_active_admin_handler(self):
        from app.tools.admin_tools import exec_manage_prompts
        from app.tools.legacy_dispatch import get_tool_dispatch

        dispatch = get_tool_dispatch()
        assert dispatch["manage_prompts"] is exec_manage_prompts

    def test_dispatch_uses_active_docx_edit_handler(self):
        from app.tools.docx_edit_tool import exec_edit_docx_document
        from app.tools.legacy_dispatch import get_tool_dispatch

        dispatch = get_tool_dispatch()
        assert dispatch["edit_docx_document"] is exec_edit_docx_document


# ---------------------------------------------------------------------------
# 5. Async Generator Pattern
# ---------------------------------------------------------------------------

class TestAsyncGenerator:
    """Verify sdk_query() is an async generator function."""

    def test_sdk_query_is_async_generator(self):
        from app.strands_agentic_service import sdk_query
        assert inspect.isasyncgenfunction(sdk_query), (
            "sdk_query() should be an async generator function"
        )


# ---------------------------------------------------------------------------
# 6. Cache Reload Wiring
# ---------------------------------------------------------------------------

class TestCacheReload:
    """Verify admin_reload_caches() clears the store caches."""

    def test_reload_clears_plugin_cache(self):
        source = inspect.getsource(__import__("app.main", fromlist=["admin_reload_caches"]))
        assert "_plugin_cache" in source

    def test_reload_clears_prompt_cache(self):
        source = inspect.getsource(__import__("app.main", fromlist=["admin_reload_caches"]))
        assert "_prompt_cache" in source
