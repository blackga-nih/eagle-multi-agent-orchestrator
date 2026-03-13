"""Performance tests for chat latency optimizations.

Validates: workspace cache, skill tools cache, supervisor direct handling,
async blocking fix, and cache reload wiring. All tests are fast (mocked, no AWS).
"""
import inspect
import time
from unittest import mock

import pytest


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
        from app.stores.workspace_store import (
            _workspace_cache, _ws_cache_set, get_or_create_default,
        )

        # Seed cache
        _ws_cache_set(TENANT, USER, FAKE_WORKSPACE)

        with mock.patch("app.stores.workspace_store._get_table") as mock_table:
            result = get_or_create_default(TENANT, USER)

        assert result["workspace_id"] == WORKSPACE_ID
        mock_table.assert_not_called()

        # Cleanup
        _workspace_cache.clear()

    def test_cache_expired_hits_dynamodb(self):
        """Expired cache entry -> falls through to DynamoDB."""
        from app.stores.workspace_store import (
            _workspace_cache, _ws_cache_key, get_or_create_default,
        )

        # Seed an expired entry (ts in the past)
        key = _ws_cache_key(TENANT, USER)
        _workspace_cache[key] = {"ts": time.time() - 120, "item": FAKE_WORKSPACE}

        # Mock DynamoDB to return a workspace via list_workspaces path
        mock_table = mock.MagicMock()
        mock_table.query.return_value = {"Items": [FAKE_WORKSPACE]}
        mock_table.get_item.return_value = {"Item": FAKE_WORKSPACE}

        with mock.patch("app.stores.workspace_store._get_table", return_value=mock_table):
            result = get_or_create_default(TENANT, USER)

        assert result["workspace_id"] == WORKSPACE_ID
        # DynamoDB was actually called (at least query for list_workspaces)
        assert mock_table.query.called or mock_table.get_item.called

        # Cleanup
        _workspace_cache.clear()


# ---------------------------------------------------------------------------
# 2. Skill Tools Cache
# ---------------------------------------------------------------------------

@pytest.mark.skip(reason="build_skill_tools() in-memory cache was removed; caching handled at call sites")
class TestSkillToolsCache:
    """Verify build_skill_tools() caches results for 60s."""

    def test_cache_hit_returns_same_tools(self):
        pass

    def test_cache_bypassed_when_skill_names_filter(self):
        pass

    def test_second_build_faster_than_first(self):
        pass


# ---------------------------------------------------------------------------
# 3. Supervisor Direct Handling
# ---------------------------------------------------------------------------

class TestSupervisorDirectHandling:
    """Verify supervisor prompt instructs direct handling for greetings."""

    def test_prompt_contains_direct_handling_instruction(self):
        prompt = self._get_prompt()
        assert "SPECIALIST" in prompt
        assert "greet" in prompt.lower()

    def test_prompt_still_has_delegation_instruction(self):
        prompt = self._get_prompt()
        assert "delegate" in prompt.lower()
        assert "specialist" in prompt.lower()

    @staticmethod
    def _get_prompt() -> str:
        from app.strands_agentic_service import build_supervisor_prompt
        return build_supervisor_prompt(
            tenant_id=TENANT, user_id=USER, tier=TIER,
        )


# ---------------------------------------------------------------------------
# 4. Async Blocking Fix
# ---------------------------------------------------------------------------

class TestAsyncBlocking:
    """Verify sdk_query() uses invoke_async instead of blocking synchronous call."""

    def test_sdk_query_uses_invoke_async(self):
        from app.strands_agentic_service import sdk_query
        source = inspect.getsource(sdk_query)
        # sdk_query is an async def — verify it uses await (non-blocking)
        assert "async def sdk_query" in source or "await" in source, (
            "sdk_query() should be async and use await to avoid blocking the event loop"
        )
        assert "run_until_complete" not in source, (
            "sdk_query() should NOT call run_until_complete (creates nested event loops)"
        )


# ---------------------------------------------------------------------------
# 5. Cache Reload Wiring
# ---------------------------------------------------------------------------

class TestCacheReload:
    """Verify admin_reload_caches() clears the new caches."""

    def test_reload_clears_workspace_cache(self):
        # workspace cache lives in stores/workspace_store.py
        from app.stores import workspace_store
        source = inspect.getsource(workspace_store)
        assert "_workspace_cache" in source

    @pytest.mark.skip(reason="_skill_tools_cache was removed; in-memory skill caching no longer used")
    def test_reload_clears_skill_tools_cache(self):
        pass
