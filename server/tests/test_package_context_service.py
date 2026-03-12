"""Tests for package_context_service.py -- Package context resolution.

Validates:
  - resolve_context(): priority order (explicit > session > workspace)
  - set_active_package(): session metadata update
  - clear_active_package(): removes package from session
  - get_active_package_id(): quick lookup without full resolution

All tests are fast (mocked stores, no AWS).
"""
from unittest import mock

import pytest


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

TENANT = "test-tenant"
USER = "test-user"
SESSION = "sess-123"
PACKAGE_ID = "PKG-2026-0001"

MOCK_PACKAGE = {
    "package_id": PACKAGE_ID,
    "title": "Test Acquisition",
    "acquisition_pathway": "simplified",
    "required_documents": ["sow", "igce"],
    "completed_documents": ["sow"],
    "status": "drafting",
}

MOCK_SESSION = {
    "session_id": SESSION,
    "tenant_id": TENANT,
    "user_id": USER,
    "metadata": {},
}

MOCK_SESSION_WITH_PACKAGE = {
    "session_id": SESSION,
    "tenant_id": TENANT,
    "user_id": USER,
    "metadata": {"active_package_id": PACKAGE_ID},
}


# ---------------------------------------------------------------------------
# TestResolveContext
# ---------------------------------------------------------------------------

class TestResolveContext:
    """Verify resolve_context priority order and behavior."""

    def test_explicit_package_id_takes_priority(self):
        """Explicit package_id in request overrides session metadata."""
        from app.package_context_service import resolve_context

        with mock.patch("app.package_context_service.get_package", return_value=MOCK_PACKAGE), \
             mock.patch("app.package_context_service.get_session", return_value=MOCK_SESSION):
            ctx = resolve_context(TENANT, USER, SESSION, explicit_package_id=PACKAGE_ID)

        assert ctx.mode == "package"
        assert ctx.package_id == PACKAGE_ID
        assert ctx.is_package_mode is True
        assert ctx.package_title == "Test Acquisition"
        assert ctx.acquisition_pathway == "simplified"

    def test_session_metadata_used_when_no_explicit(self):
        """Session active_package_id used when no explicit package_id."""
        from app.package_context_service import resolve_context

        with mock.patch("app.package_context_service.get_package", return_value=MOCK_PACKAGE), \
             mock.patch("app.package_context_service.get_session", return_value=MOCK_SESSION_WITH_PACKAGE):
            ctx = resolve_context(TENANT, USER, SESSION)

        assert ctx.mode == "package"
        assert ctx.package_id == PACKAGE_ID

    def test_workspace_mode_when_no_package_context(self):
        """Returns workspace mode when no package context found."""
        from app.package_context_service import resolve_context

        with mock.patch("app.package_context_service.get_session", return_value=MOCK_SESSION):
            ctx = resolve_context(TENANT, USER, SESSION)

        assert ctx.mode == "workspace"
        assert ctx.package_id is None
        assert ctx.is_package_mode is False

    def test_clears_stale_package_reference(self):
        """Clears session package_id when package no longer exists."""
        from app.package_context_service import resolve_context

        # Session has package_id but package doesn't exist
        with mock.patch("app.package_context_service.get_package", return_value=None), \
             mock.patch("app.package_context_service.get_session", return_value=MOCK_SESSION_WITH_PACKAGE), \
             mock.patch("app.package_context_service.clear_active_package") as mock_clear:
            ctx = resolve_context(TENANT, USER, SESSION)

        mock_clear.assert_called_once_with(TENANT, USER, SESSION)
        assert ctx.mode == "workspace"

    def test_explicit_invalid_package_falls_through(self):
        """Falls through to session when explicit package_id is invalid."""
        from app.package_context_service import resolve_context

        def get_package_side_effect(tenant, pkg_id):
            if pkg_id == PACKAGE_ID:
                return MOCK_PACKAGE
            return None

        with mock.patch("app.package_context_service.get_package", side_effect=get_package_side_effect), \
             mock.patch("app.package_context_service.get_session", return_value=MOCK_SESSION_WITH_PACKAGE):
            ctx = resolve_context(TENANT, USER, SESSION, explicit_package_id="invalid-pkg")

        # Falls back to session's active_package_id
        assert ctx.mode == "package"
        assert ctx.package_id == PACKAGE_ID


# ---------------------------------------------------------------------------
# TestSetActivePackage
# ---------------------------------------------------------------------------

class TestSetActivePackage:
    """Verify set_active_package updates session metadata."""

    def test_sets_package_in_session_metadata(self):
        """Updates session metadata with active_package_id."""
        from app.package_context_service import set_active_package

        with mock.patch("app.package_context_service.get_package", return_value=MOCK_PACKAGE), \
             mock.patch("app.package_context_service.get_session", return_value=MOCK_SESSION), \
             mock.patch("app.package_context_service.update_session") as mock_update:
            ctx = set_active_package(TENANT, USER, SESSION, PACKAGE_ID)

        mock_update.assert_called_once()
        call_kwargs = mock_update.call_args[1]
        assert call_kwargs["updates"]["metadata"]["active_package_id"] == PACKAGE_ID
        assert ctx.package_id == PACKAGE_ID

    def test_returns_none_when_package_not_found(self):
        """Returns None when package doesn't exist."""
        from app.package_context_service import set_active_package

        with mock.patch("app.package_context_service.get_package", return_value=None):
            ctx = set_active_package(TENANT, USER, SESSION, "invalid-pkg")

        assert ctx is None

    def test_returns_none_when_session_not_found(self):
        """Returns None when session doesn't exist."""
        from app.package_context_service import set_active_package

        with mock.patch("app.package_context_service.get_package", return_value=MOCK_PACKAGE), \
             mock.patch("app.package_context_service.get_session", return_value=None):
            ctx = set_active_package(TENANT, USER, SESSION, PACKAGE_ID)

        assert ctx is None


# ---------------------------------------------------------------------------
# TestClearActivePackage
# ---------------------------------------------------------------------------

class TestClearActivePackage:
    """Verify clear_active_package removes package from session."""

    def test_clears_active_package_from_metadata(self):
        """Removes active_package_id from session metadata."""
        from app.package_context_service import clear_active_package

        with mock.patch("app.package_context_service.get_session", return_value=MOCK_SESSION_WITH_PACKAGE), \
             mock.patch("app.package_context_service.update_session") as mock_update:
            result = clear_active_package(TENANT, USER, SESSION)

        assert result is True
        mock_update.assert_called_once()
        call_kwargs = mock_update.call_args[1]
        assert "active_package_id" not in call_kwargs["updates"]["metadata"]

    def test_returns_true_when_no_package_to_clear(self):
        """Returns True even when no active package."""
        from app.package_context_service import clear_active_package

        with mock.patch("app.package_context_service.get_session", return_value=MOCK_SESSION), \
             mock.patch("app.package_context_service.update_session") as mock_update:
            result = clear_active_package(TENANT, USER, SESSION)

        assert result is True
        mock_update.assert_not_called()

    def test_returns_false_when_session_not_found(self):
        """Returns False when session doesn't exist."""
        from app.package_context_service import clear_active_package

        with mock.patch("app.package_context_service.get_session", return_value=None):
            result = clear_active_package(TENANT, USER, SESSION)

        assert result is False


# ---------------------------------------------------------------------------
# TestGetActivePackageId
# ---------------------------------------------------------------------------

class TestGetActivePackageId:
    """Verify get_active_package_id quick lookup."""

    def test_returns_package_id_from_session(self):
        """Returns active_package_id from session metadata."""
        from app.package_context_service import get_active_package_id

        with mock.patch("app.package_context_service.get_session", return_value=MOCK_SESSION_WITH_PACKAGE):
            result = get_active_package_id(TENANT, USER, SESSION)

        assert result == PACKAGE_ID

    def test_returns_none_when_no_active_package(self):
        """Returns None when no active package."""
        from app.package_context_service import get_active_package_id

        with mock.patch("app.package_context_service.get_session", return_value=MOCK_SESSION):
            result = get_active_package_id(TENANT, USER, SESSION)

        assert result is None

    def test_returns_none_when_session_not_found(self):
        """Returns None when session doesn't exist."""
        from app.package_context_service import get_active_package_id

        with mock.patch("app.package_context_service.get_session", return_value=None):
            result = get_active_package_id(TENANT, USER, SESSION)

        assert result is None


# ---------------------------------------------------------------------------
# TestPackageContext
# ---------------------------------------------------------------------------

class TestPackageContext:
    """Verify PackageContext dataclass behavior."""

    def test_is_package_mode_true_when_package_mode(self):
        from app.package_context_service import PackageContext

        ctx = PackageContext(mode="package", package_id=PACKAGE_ID)
        assert ctx.is_package_mode is True

    def test_is_package_mode_false_when_workspace_mode(self):
        from app.package_context_service import PackageContext

        ctx = PackageContext(mode="workspace")
        assert ctx.is_package_mode is False

    def test_is_package_mode_false_when_no_package_id(self):
        from app.package_context_service import PackageContext

        ctx = PackageContext(mode="package", package_id=None)
        assert ctx.is_package_mode is False
