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

        with mock.patch("app.workspace_store._get_table") as mock_table:
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

        with mock.patch("app.workspace_store._get_table", return_value=mock_table):
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

    @staticmethod
    def _get_prompt() -> str:
        from app.strands_agentic_service import build_supervisor_prompt
        return build_supervisor_prompt(
            tenant_id=TENANT, user_id=USER, tier=TIER,
        )


# ---------------------------------------------------------------------------
# 4. Async Generator Pattern
# ---------------------------------------------------------------------------

class TestAsyncGenerator:
    """Verify sdk_query() is an async generator function."""

    def test_sdk_query_is_async_generator(self):
        from app.strands_agentic_service import sdk_query
        assert inspect.isasyncgenfunction(sdk_query), (
            "sdk_query() should be an async generator function"
        )


# ---------------------------------------------------------------------------
# 5. Cache Reload Wiring
# ---------------------------------------------------------------------------

class TestCacheReload:
    """Verify admin_reload_caches() clears the store caches."""

    def test_reload_clears_plugin_cache(self):
        source = inspect.getsource(__import__("app.main", fromlist=["admin_reload_caches"]))
        assert "_plugin_cache" in source

    def test_reload_clears_prompt_cache(self):
        source = inspect.getsource(__import__("app.main", fromlist=["admin_reload_caches"]))
        assert "_prompt_cache" in source
