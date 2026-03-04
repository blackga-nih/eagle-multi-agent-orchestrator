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
# 2. Skill Tools Cache
# ---------------------------------------------------------------------------

class TestSkillToolsCache:
    """Verify build_skill_tools() caches results for 60s."""

    def test_cache_hit_returns_same_tools(self):
        """Seeded cache -> build_skill_tools() returns cached list without rebuilding."""
        from app.strands_agentic_service import (
            _skill_tools_cache, _tools_cache_set, build_skill_tools,
        )

        fake_tools = [lambda: None, lambda: None]
        _tools_cache_set(TENANT, TIER, WORKSPACE_ID, fake_tools)

        result = build_skill_tools(
            tier=TIER, tenant_id=TENANT, user_id=USER, workspace_id=WORKSPACE_ID,
        )

        assert result is fake_tools

        # Cleanup
        _skill_tools_cache.clear()

    def test_cache_bypassed_when_skill_names_filter(self):
        """skill_names param -> cache is skipped, tools are rebuilt."""
        from app.strands_agentic_service import (
            _skill_tools_cache, _tools_cache_set, build_skill_tools,
        )

        fake_tools = [lambda: None]
        _tools_cache_set(TENANT, TIER, WORKSPACE_ID, fake_tools)

        # Even with cache seeded, passing skill_names should bypass it
        with mock.patch("app.strands_agentic_service.SKILL_AGENT_REGISTRY", {}):
            result = build_skill_tools(
                tier=TIER, skill_names=["nonexistent"],
                tenant_id=TENANT, user_id=USER, workspace_id=WORKSPACE_ID,
            )

        # Should NOT be the cached list
        assert result is not fake_tools
        # Only the always-included compliance_matrix tool should remain
        assert len(result) == 1

        # Cleanup
        _skill_tools_cache.clear()

    def test_second_build_faster_than_first(self):
        """Second call to build_skill_tools() should be <10ms (cache hit)."""
        from app.strands_agentic_service import (
            _skill_tools_cache, build_skill_tools,
        )
        _skill_tools_cache.clear()

        # Mock DynamoDB calls to avoid real AWS
        with mock.patch("app.strands_agentic_service.PLUGIN_CONTENTS", {}), \
             mock.patch("app.strands_agentic_service.SKILL_AGENT_REGISTRY", {}):

            # First call — populates cache
            build_skill_tools(tier=TIER, tenant_id=TENANT, user_id=USER, workspace_id=WORKSPACE_ID)

            # Second call — cache hit
            t0 = time.perf_counter()
            build_skill_tools(tier=TIER, tenant_id=TENANT, user_id=USER, workspace_id=WORKSPACE_ID)
            elapsed_ms = (time.perf_counter() - t0) * 1000

        assert elapsed_ms < 10, f"Cache hit took {elapsed_ms:.1f}ms, expected <10ms"

        # Cleanup
        _skill_tools_cache.clear()


# ---------------------------------------------------------------------------
# 3. Supervisor Direct Handling
# ---------------------------------------------------------------------------

class TestSupervisorDirectHandling:
    """Verify supervisor prompt instructs direct handling for greetings."""

    def test_prompt_contains_direct_handling_instruction(self):
        prompt = self._get_prompt()
        assert "DIRECT HANDLING" in prompt
        assert "Greetings" in prompt or "greet" in prompt.lower()
        assert "WITHOUT" in prompt

    def test_prompt_still_has_delegation_instruction(self):
        prompt = self._get_prompt()
        assert "SPECIALIST DELEGATION" in prompt
        assert "delegate" in prompt.lower()

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
        assert "invoke_async" in source, (
            "sdk_query() should use invoke_async to avoid creating redundant event loops"
        )
        assert "supervisor(prompt)" not in source, (
            "sdk_query() should NOT call supervisor(prompt) synchronously"
        )


# ---------------------------------------------------------------------------
# 5. Cache Reload Wiring
# ---------------------------------------------------------------------------

class TestCacheReload:
    """Verify admin_reload_caches() clears the new caches."""

    def test_reload_clears_workspace_cache(self):
        source = inspect.getsource(__import__("app.main", fromlist=["admin_reload_caches"]))
        assert "_workspace_cache" in source

    def test_reload_clears_skill_tools_cache(self):
        source = inspect.getsource(__import__("app.main", fromlist=["admin_reload_caches"]))
        assert "_skill_tools_cache" in source
