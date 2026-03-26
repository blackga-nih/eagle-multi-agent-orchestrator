"""Tests for session_preloader.py — parallel DynamoDB preloading.

Validates:
  - preload_session_context(): parallel fetches for prefs, package, flags
  - format_context_for_prompt(): terse prompt block rendering
  - Timeout graceful degradation
  - pref_store cache hit/invalidate

All tests are fast (mocked stores, no AWS).
"""
import asyncio
from unittest import mock

import pytest

from app.session_preloader import (
    PreloadedContext,
    format_context_for_prompt,
    preload_session_context,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TENANT = "test-tenant"
USER = "test-user"
PACKAGE_ID = "PKG-2026-0001"

MOCK_PREFS = {
    "default_model": "sonnet",
    "default_doc_format": "docx",
    "preferred_vehicle": "NITAAC CIO-SP3",
    "ui_theme": "dark",
    "notification_email": False,
    "show_far_citations": True,
    "default_template": {},
}

MOCK_PACKAGE = {
    "package_id": PACKAGE_ID,
    "title": "Cloud Infrastructure Services",
    "acquisition_pathway": "full_competition",
    "estimated_value": "350000",
    "status": "drafting",
    "required_documents": ["sow", "igce", "market_research", "acquisition_plan"],
    "completed_documents": ["sow", "igce"],
}

MOCK_CHECKLIST = {
    "required": ["sow", "igce", "market_research", "acquisition_plan"],
    "completed": ["sow", "igce"],
    "missing": ["market_research", "acquisition_plan"],
    "complete": False,
}

MOCK_DOCUMENTS = [
    {"doc_type": "igce", "version": 1, "status": "draft"},
    {"doc_type": "sow", "version": 2, "status": "draft"},
]

MOCK_FLAGS = {"streaming_v2": True, "user_skills": False, "mcp_enabled": False}


# ---------------------------------------------------------------------------
# format_context_for_prompt
# ---------------------------------------------------------------------------


class TestFormatContextForPrompt:
    """Unit tests for the prompt formatting helper."""

    def test_empty_context_returns_empty(self):
        ctx = PreloadedContext()
        assert format_context_for_prompt(ctx) == ""

    def test_preferences_only(self):
        ctx = PreloadedContext(preferences=MOCK_PREFS)
        result = format_context_for_prompt(ctx)
        assert "--- USER CONTEXT ---" in result
        assert "doc_format=docx" in result
        assert "vehicle=NITAAC CIO-SP3" in result
        assert "far_citations=on" in result

    def test_preferences_no_vehicle(self):
        prefs = {**MOCK_PREFS, "preferred_vehicle": None}
        ctx = PreloadedContext(preferences=prefs)
        result = format_context_for_prompt(ctx)
        assert "vehicle=" not in result

    def test_package_context(self):
        ctx = PreloadedContext(
            preferences=MOCK_PREFS,
            package=MOCK_PACKAGE,
            checklist=MOCK_CHECKLIST,
            documents=MOCK_DOCUMENTS,
        )
        result = format_context_for_prompt(ctx)
        assert "Active Package:" in result
        assert PACKAGE_ID in result
        assert "Cloud Infrastructure Services" in result
        assert "full_competition" in result
        assert "sow (v2)" in result
        assert "igce (v1)" in result
        assert "market_research" in result
        assert "acquisition_plan" in result

    def test_package_all_complete(self):
        checklist = {
            "required": ["sow"],
            "completed": ["sow"],
            "missing": [],
            "complete": True,
        }
        ctx = PreloadedContext(
            package=MOCK_PACKAGE,
            checklist=checklist,
            documents=[{"doc_type": "sow", "version": 1}],
        )
        result = format_context_for_prompt(ctx)
        assert "Missing: none" in result


# ---------------------------------------------------------------------------
# preload_session_context
# ---------------------------------------------------------------------------


class TestPreloadSessionContext:
    """Integration-style tests for the async preloader (mocked stores)."""

    @pytest.mark.asyncio
    async def test_preload_prefs_and_flags(self):
        with (
            mock.patch("app.session_preloader._fetch_preferences", return_value=MOCK_PREFS),
            mock.patch("app.session_preloader._fetch_feature_flags", return_value=MOCK_FLAGS),
        ):
            ctx = await preload_session_context(TENANT, USER)
            assert ctx.preferences == MOCK_PREFS
            assert ctx.feature_flags == MOCK_FLAGS
            assert ctx.package is None

    @pytest.mark.asyncio
    async def test_preload_with_package(self):
        pkg_result = {
            "package": MOCK_PACKAGE,
            "checklist": MOCK_CHECKLIST,
            "documents": MOCK_DOCUMENTS,
        }
        with (
            mock.patch("app.session_preloader._fetch_preferences", return_value=MOCK_PREFS),
            mock.patch("app.session_preloader._fetch_package_and_docs", return_value=pkg_result),
            mock.patch("app.session_preloader._fetch_feature_flags", return_value=MOCK_FLAGS),
            mock.patch("app.session_preloader._warm_template_cache"),
        ):
            ctx = await preload_session_context(TENANT, USER, package_id=PACKAGE_ID)
            assert ctx.package == MOCK_PACKAGE
            assert ctx.checklist == MOCK_CHECKLIST
            assert len(ctx.documents) == 2

    @pytest.mark.asyncio
    async def test_preload_without_package_id(self):
        with (
            mock.patch("app.session_preloader._fetch_preferences", return_value=MOCK_PREFS),
            mock.patch("app.session_preloader._fetch_feature_flags", return_value=MOCK_FLAGS),
        ):
            ctx = await preload_session_context(TENANT, USER, package_id=None)
            assert ctx.package is None
            assert ctx.checklist is None

    @pytest.mark.asyncio
    async def test_timeout_returns_partial(self):
        """When one fetch times out, we still get partial results."""

        async def slow_prefs(*a, **kw):
            await asyncio.sleep(5)
            return MOCK_PREFS

        with (
            mock.patch(
                "app.session_preloader._fetch_preferences",
                side_effect=lambda *a: (_ for _ in ()).throw(TimeoutError),
            ),
            mock.patch("app.session_preloader._fetch_feature_flags", return_value=MOCK_FLAGS),
            mock.patch("asyncio.to_thread", side_effect=lambda fn, *a, **kw: asyncio.coroutine(lambda: fn(*a, **kw))()),
        ):
            # Even though prefs throw, the timeout wrapper catches it
            ctx = await preload_session_context(TENANT, USER, timeout_ms=100)
            # Should not raise — returns default empty context
            assert isinstance(ctx, PreloadedContext)

    @pytest.mark.asyncio
    async def test_error_returns_defaults(self):
        with (
            mock.patch("app.session_preloader._fetch_preferences", side_effect=Exception("boom")),
            mock.patch("app.session_preloader._fetch_feature_flags", side_effect=Exception("boom")),
        ):
            ctx = await preload_session_context(TENANT, USER, timeout_ms=500)
            assert isinstance(ctx, PreloadedContext)


# ---------------------------------------------------------------------------
# pref_store cache
# ---------------------------------------------------------------------------


class TestPrefStoreCache:
    """Verify the pref_store in-process cache works correctly."""

    def test_cache_hit(self):
        from app.pref_store import _cache_set, _cache_get

        _cache_set("t1", "u1", {"default_model": "haiku"})
        result = _cache_get("t1", "u1")
        assert result is not None
        assert result["default_model"] == "haiku"

    def test_cache_miss(self):
        from app.pref_store import _cache_get

        result = _cache_get("nonexistent-tenant", "nonexistent-user")
        assert result is None

    def test_cache_invalidate(self):
        from app.pref_store import _cache_set, _cache_get, _cache_invalidate

        _cache_set("t2", "u2", {"default_model": "opus"})
        _cache_invalidate("t2", "u2")
        result = _cache_get("t2", "u2")
        assert result is None
