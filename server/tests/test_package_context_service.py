"""Tests for package_context_service.py -- Package context resolution.

Validates:
  - resolve_context(): priority order (explicit > session > workspace)
  - set_active_package(): session metadata update
  - clear_active_package(): removes package from session
  - get_active_package_id(): quick lookup without full resolution

All tests are fast (mocked stores, no AWS).
"""
import copy
from unittest import mock


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
             mock.patch("app.package_context_service.get_session", return_value=copy.deepcopy(MOCK_SESSION)):
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
             mock.patch("app.package_context_service.get_session", return_value=copy.deepcopy(MOCK_SESSION_WITH_PACKAGE)):
            ctx = resolve_context(TENANT, USER, SESSION)

        assert ctx.mode == "package"
        assert ctx.package_id == PACKAGE_ID

    def test_workspace_mode_when_no_package_context(self):
        """Returns workspace mode when no package context found."""
        from app.package_context_service import resolve_context

        with mock.patch("app.package_context_service.get_session", return_value=copy.deepcopy(MOCK_SESSION)):
            ctx = resolve_context(TENANT, USER, SESSION)

        assert ctx.mode == "workspace"
        assert ctx.package_id is None
        assert ctx.is_package_mode is False

    def test_clears_stale_package_reference(self):
        """Clears session package_id when package no longer exists."""
        from app.package_context_service import resolve_context

        # Session has package_id but package doesn't exist
        with mock.patch("app.package_context_service.get_package", return_value=None), \
             mock.patch("app.package_context_service.get_session", return_value=copy.deepcopy(MOCK_SESSION_WITH_PACKAGE)), \
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
             mock.patch("app.package_context_service.get_session", return_value=copy.deepcopy(MOCK_SESSION_WITH_PACKAGE)):
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
             mock.patch("app.package_context_service.get_session", return_value=copy.deepcopy(MOCK_SESSION)), \
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

        with mock.patch("app.package_context_service.get_session", return_value=copy.deepcopy(MOCK_SESSION_WITH_PACKAGE)), \
             mock.patch("app.package_context_service.update_session") as mock_update:
            result = clear_active_package(TENANT, USER, SESSION)

        assert result is True
        mock_update.assert_called_once()
        call_kwargs = mock_update.call_args[1]
        assert "active_package_id" not in call_kwargs["updates"]["metadata"]

    def test_returns_true_when_no_package_to_clear(self):
        """Returns True even when no active package."""
        from app.package_context_service import clear_active_package

        with mock.patch("app.package_context_service.get_session", return_value=copy.deepcopy(MOCK_SESSION)), \
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

        with mock.patch("app.package_context_service.get_session", return_value=copy.deepcopy(MOCK_SESSION_WITH_PACKAGE)):
            result = get_active_package_id(TENANT, USER, SESSION)

        assert result == PACKAGE_ID

    def test_returns_none_when_no_active_package(self):
        """Returns None when no active package."""
        from app.package_context_service import get_active_package_id

        with mock.patch("app.package_context_service.get_session", return_value=copy.deepcopy(MOCK_SESSION)):
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


# ---------------------------------------------------------------------------
# TestDetectPackageFromSession
# ---------------------------------------------------------------------------

import json

# Messages containing tool_result with package_id (Anthropic format)
MESSAGES_WITH_TOOL_RESULT = [
    {
        "role": "user",
        "content": "Generate an SOW for my package",
    },
    {
        "role": "assistant",
        "content": json.dumps([
            {"type": "tool_use", "id": "tu_1", "name": "generate_document",
             "input": {"doc_type": "sow", "package_id": PACKAGE_ID}},
        ]),
        "content_type": "list",
    },
    {
        "role": "user",
        "content": json.dumps([
            {"type": "tool_result", "tool_use_id": "tu_1",
             "content": json.dumps({"package_id": PACKAGE_ID, "doc_type": "sow", "title": "SOW v1"})},
        ]),
        "content_type": "list",
    },
]

MESSAGES_WITHOUT_PACKAGE = [
    {"role": "user", "content": "Hello"},
    {"role": "assistant", "content": "Hi there"},
]


class TestDetectPackageFromSession:
    """Verify detect_package_from_session scans messages for package_id."""

    def test_detects_package_from_tool_result(self):
        """Finds package_id in tool_result content blocks."""
        from app.package_context_service import detect_package_from_session

        with mock.patch("app.package_context_service.get_messages", return_value=MESSAGES_WITH_TOOL_RESULT), \
             mock.patch("app.package_context_service.get_package", return_value=MOCK_PACKAGE), \
             mock.patch("app.package_context_service.get_session", return_value=copy.deepcopy(MOCK_SESSION)), \
             mock.patch("app.package_context_service.update_session"):
            ctx = detect_package_from_session(TENANT, USER, SESSION)

        assert ctx is not None
        assert ctx.package_id == PACKAGE_ID
        assert ctx.mode == "package"

    def test_returns_none_when_no_messages(self):
        """Returns None when session has no messages."""
        from app.package_context_service import detect_package_from_session

        with mock.patch("app.package_context_service.get_messages", return_value=[]):
            ctx = detect_package_from_session(TENANT, USER, SESSION)

        assert ctx is None

    def test_returns_none_when_no_package_in_messages(self):
        """Returns None when messages have no package_id references."""
        from app.package_context_service import detect_package_from_session

        # Tier A finds nothing; Tier B/C run and also find nothing because
        # the tenant has no packages and the chat has no PKG-id mentions.
        with mock.patch("app.package_context_service.get_messages", return_value=MESSAGES_WITHOUT_PACKAGE), \
             mock.patch("app.package_context_service.list_packages", return_value=[]), \
             mock.patch("app.package_context_service.list_package_documents", return_value=[]):
            ctx = detect_package_from_session(TENANT, USER, SESSION)

        assert ctx is None

    def test_detects_package_from_tool_use_input(self):
        """Finds package_id in tool_use input blocks."""
        from app.package_context_service import detect_package_from_session

        messages = [
            {
                "role": "assistant",
                "content": json.dumps([
                    {"type": "tool_use", "id": "tu_1", "name": "generate_document",
                     "input": {"doc_type": "sow", "package_id": PACKAGE_ID}},
                ]),
                "content_type": "list",
            },
        ]

        with mock.patch("app.package_context_service.get_messages", return_value=messages), \
             mock.patch("app.package_context_service.get_package", return_value=MOCK_PACKAGE), \
             mock.patch("app.package_context_service.get_session", return_value=copy.deepcopy(MOCK_SESSION)), \
             mock.patch("app.package_context_service.update_session"):
            ctx = detect_package_from_session(TENANT, USER, SESSION)

        assert ctx is not None
        assert ctx.package_id == PACKAGE_ID


# ---------------------------------------------------------------------------
# TestDetectPackageRegexFallback — Tier B (PKG-id) and Tier C (titles)
# ---------------------------------------------------------------------------


SECOND_PACKAGE_ID = "PKG-2026-0042"
SECOND_PACKAGE = {
    "package_id": SECOND_PACKAGE_ID,
    "title": "FY26 GenAI Bench Acquisition",
    "acquisition_pathway": "competitive",
    "required_documents": ["sow", "igce", "acquisition_plan"],
    "completed_documents": [],
    "status": "drafting",
}


class TestDetectPackageRegexFallback:
    """Detection should fall back to regex over chat text when there are no
    structured tool blocks. This covers the on-demand 'Detect Package from
    Chat' button path on the activity panel."""

    def _setup(self, messages, packages, docs_by_pkg, get_pkg_lookup):
        """Common patches — only get_package needs a per-id side effect."""
        return [
            mock.patch("app.package_context_service.get_messages", return_value=messages),
            mock.patch("app.package_context_service.list_packages", return_value=packages),
            mock.patch(
                "app.package_context_service.list_package_documents",
                side_effect=lambda _t, pid: docs_by_pkg.get(pid, []),
            ),
            mock.patch(
                "app.package_context_service.get_package",
                side_effect=get_pkg_lookup,
            ),
            mock.patch(
                "app.package_context_service.get_session",
                return_value=copy.deepcopy(MOCK_SESSION),
            ),
            mock.patch("app.package_context_service.update_session"),
        ]

    def test_detects_package_id_in_plain_user_text(self):
        """Tier B: assistant's plain-text reply mentions PKG-2026-0042."""
        from app.package_context_service import detect_package_from_session

        messages = [
            {"role": "user", "content": "What's the status of my package?"},
            {
                "role": "assistant",
                "content": "Looking at PKG-2026-0042 — it's still in drafting.",
            },
        ]

        def get_pkg(_tenant, pid):
            return SECOND_PACKAGE if pid == SECOND_PACKAGE_ID else None

        patches = self._setup(messages, [SECOND_PACKAGE], {}, get_pkg)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            ctx = detect_package_from_session(TENANT, USER, SESSION)

        assert ctx is not None
        assert ctx.package_id == SECOND_PACKAGE_ID

    def test_ignores_package_id_that_does_not_exist(self):
        """Tier B should not lock onto a PKG-id that isn't in the store."""
        from app.package_context_service import detect_package_from_session

        messages = [
            {"role": "assistant", "content": "Reference: PKG-2099-9999 (typo)"},
        ]

        patches = self._setup(messages, [], {}, lambda *_: None)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            ctx = detect_package_from_session(TENANT, USER, SESSION)

        assert ctx is None

    def test_detects_package_via_document_title(self):
        """Tier C: assistant references a previously-generated document
        title without ever mentioning the PKG-id explicitly."""
        from app.package_context_service import detect_package_from_session

        messages = [
            {"role": "user", "content": "Update the SOW."},
            {
                "role": "assistant",
                "content": (
                    "I just regenerated the FY26 GenAI Bench Statement of Work "
                    "with the new scope language."
                ),
            },
        ]
        docs = {
            SECOND_PACKAGE_ID: [
                {"doc_type": "sow", "title": "FY26 GenAI Bench Statement of Work", "version": 3},
            ],
        }

        def get_pkg(_tenant, pid):
            return SECOND_PACKAGE if pid == SECOND_PACKAGE_ID else None

        patches = self._setup(messages, [SECOND_PACKAGE], docs, get_pkg)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            ctx = detect_package_from_session(TENANT, USER, SESSION)

        assert ctx is not None
        assert ctx.package_id == SECOND_PACKAGE_ID

    def test_most_recent_message_wins_when_two_packages_referenced(self):
        """If the chat mentions two packages, the latest reference wins so
        the right-hand panel reflects what the user is currently working on."""
        from app.package_context_service import detect_package_from_session

        # Older message references PACKAGE_ID, newer references SECOND_PACKAGE_ID.
        messages = [
            {"role": "assistant", "content": f"Earlier we worked on {PACKAGE_ID}."},
            {"role": "user", "content": f"Now show me {SECOND_PACKAGE_ID}."},
        ]

        def get_pkg(_tenant, pid):
            return {PACKAGE_ID: MOCK_PACKAGE, SECOND_PACKAGE_ID: SECOND_PACKAGE}.get(pid)

        patches = self._setup(
            messages, [MOCK_PACKAGE, SECOND_PACKAGE], {}, get_pkg
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            ctx = detect_package_from_session(TENANT, USER, SESSION)

        assert ctx is not None
        assert ctx.package_id == SECOND_PACKAGE_ID

    def test_tier_a_still_wins_over_text_match(self):
        """When a structured tool_use block carries a package_id, it should
        be preferred over a plain-text mention of a different package."""
        from app.package_context_service import detect_package_from_session

        messages = [
            # Tool block points at PACKAGE_ID — highest confidence.
            {
                "role": "assistant",
                "content": json.dumps([
                    {"type": "tool_use", "id": "tu_1", "name": "generate_document",
                     "input": {"doc_type": "sow", "package_id": PACKAGE_ID}},
                ]),
                "content_type": "list",
            },
            # Plain-text mention of a different package — should be ignored.
            {"role": "assistant", "content": f"Also see {SECOND_PACKAGE_ID}."},
        ]

        def get_pkg(_tenant, pid):
            return {PACKAGE_ID: MOCK_PACKAGE, SECOND_PACKAGE_ID: SECOND_PACKAGE}.get(pid)

        patches = self._setup(
            messages, [MOCK_PACKAGE, SECOND_PACKAGE], {}, get_pkg
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            ctx = detect_package_from_session(TENANT, USER, SESSION)

        assert ctx is not None
        assert ctx.package_id == PACKAGE_ID
