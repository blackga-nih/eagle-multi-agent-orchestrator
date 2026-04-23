"""
Unique-user identity tests.

Purpose
-------
On dev, every caller is currently flattened to the static DEV_USER_ID/
DEV_TENANT_ID (see app.cognito_auth.extract_user_context — DEV_MODE short-
circuits before the token is even inspected). That collapses every
signed-in user into one shared workspace.

These tests pin down the correct behavior:

  * A real Cognito JWT — when one is supplied — MUST take precedence over
    the DEV_MODE fallback.
  * Two different users with two different tokens MUST get two different
    UserContext objects (so their sessions, workspaces, cost rows, and
    package contexts stay isolated).
  * The DEV_MODE fallback is only acceptable when the caller sends NO
    token at all (e.g. a local curl without Authorization).
  * When the request reaches /api/chat, the telemetry row and the
    session/tenant scoping MUST use the JWT's `sub` and
    `custom:tenant_id` — not the dev defaults.

Several of these tests are EXPECTED TO FAIL against today's
app.cognito_auth: that failure is the signal for the fix (don't bypass
token parsing when a token is actually present).

Run: pytest server/tests/test_unique_user_identity.py -v
"""

from __future__ import annotations

import os
import sys
from typing import AsyncGenerator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Ensure server/ is on sys.path so `app.*` imports resolve when pytest is
# invoked from the repo root.
_server_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)


# ── Shared helpers ────────────────────────────────────────────────────


def _patch_cognito_auth(monkeypatch, **overrides):
    """
    Patch the module-level flags in app.cognito_auth without reloading.

    The app.config singletons are frozen dataclasses, so importlib.reload
    leaves them stale. monkeypatch.setattr hits the names that
    extract_user_context / validate_token actually read.
    """
    import app.cognito_auth as mod

    defaults = {
        "DEV_MODE": False,
        "DEV_USER_ID": "dev-user",
        "DEV_TENANT_ID": "dev-tenant",
        # Empty pool IDs force validate_token_simple (no JWKS network call)
        "COGNITO_USER_POOL_ID": "",
        "COGNITO_CLIENT_ID": "",
    }
    merged = {**defaults, **overrides}

    dev_mode_raw = merged["DEV_MODE"]
    if isinstance(dev_mode_raw, str):
        dev_mode_val = dev_mode_raw.lower() in ("true", "1", "yes")
    else:
        dev_mode_val = bool(dev_mode_raw)

    monkeypatch.setattr(mod, "DEV_MODE", dev_mode_val)
    monkeypatch.setattr(mod, "DEV_USER_ID", merged["DEV_USER_ID"])
    monkeypatch.setattr(mod, "DEV_TENANT_ID", merged["DEV_TENANT_ID"])
    monkeypatch.setattr(mod, "COGNITO_USER_POOL_ID", merged["COGNITO_USER_POOL_ID"])
    monkeypatch.setattr(mod, "COGNITO_CLIENT_ID", merged["COGNITO_CLIENT_ID"])
    return mod


def _issue_token(mod, user_id: str, tenant_id: str, tier: str = "premium", roles=None):
    """Issue a decodable HS256 JWT for tests (validate_token_simple accepts it)."""
    token = mod.generate_test_token(
        user_id=user_id,
        tenant_id=tenant_id,
        tier=tier,
        roles=roles or [],
    )
    assert token, "PyJWT must be installed for these tests"
    return token


# ══════════════════════════════════════════════════════════════════════
# 1. extract_user_context — real JWT must beat DEV_MODE fallback
# ══════════════════════════════════════════════════════════════════════


class TestRealTokenBeatsDevFallback:
    """
    Anchor test for the bug: if a real Cognito JWT is present on the
    request, DEV_MODE must NOT silently discard it.
    """

    def test_valid_jwt_returns_real_user_even_under_dev_mode(self, monkeypatch):
        mod = _patch_cognito_auth(monkeypatch, DEV_MODE="true")
        token = _issue_token(mod, user_id="alice-sub-uuid", tenant_id="nci-tenant-a")

        ctx, err = mod.extract_user_context(token=f"Bearer {token}", validate=True)

        assert err is None, f"unexpected auth error: {err}"
        assert ctx.user_id == "alice-sub-uuid", (
            "extract_user_context returned the dev fallback instead of the "
            "JWT's `sub` — every user will share the same workspace."
        )
        assert ctx.tenant_id == "nci-tenant-a", (
            "extract_user_context returned DEV_TENANT_ID instead of the "
            "JWT's `custom:tenant_id` — tenant scoping is broken."
        )

    def test_valid_jwt_tier_overrides_dev_default(self, monkeypatch):
        mod = _patch_cognito_auth(monkeypatch, DEV_MODE="true")
        token = _issue_token(
            mod, user_id="bob", tenant_id="nci-tenant-b", tier="basic"
        )

        ctx, _err = mod.extract_user_context(token=f"Bearer {token}")

        assert ctx.tier == "basic", (
            "Tier from JWT should override DEV_MODE's premium default — "
            "otherwise every dev user is silently upgraded."
        )

    def test_dev_fallback_allowed_when_no_token_present(self, monkeypatch):
        """No token at all → dev fallback is acceptable (legacy curl/dev)."""
        mod = _patch_cognito_auth(monkeypatch, DEV_MODE="true")

        ctx, err = mod.extract_user_context(token=None)

        # This is the intentionally permissive path — there is literally
        # no caller identity to preserve.
        assert err is None
        assert ctx.user_id == "dev-user"
        assert ctx.tenant_id == "dev-tenant"

    def test_dev_fallback_allowed_when_empty_token(self, monkeypatch):
        mod = _patch_cognito_auth(monkeypatch, DEV_MODE="true")

        ctx, _err = mod.extract_user_context(token="")

        assert ctx.user_id == "dev-user"


# ══════════════════════════════════════════════════════════════════════
# 2. Two users, two tokens → two distinct contexts
# ══════════════════════════════════════════════════════════════════════


class TestUsersAreDistinct:
    """
    Two concurrent users on the same dev box must NOT collide into a
    shared identity. This is the multi-tenant invariant that DynamoDB
    session keys (SESSION#<tenant>#<user>) rely on.
    """

    def test_two_jwts_yield_distinct_user_ids(self, monkeypatch):
        mod = _patch_cognito_auth(monkeypatch, DEV_MODE="true")
        alice = _issue_token(mod, user_id="alice-uuid", tenant_id="tenant-a")
        bob = _issue_token(mod, user_id="bob-uuid", tenant_id="tenant-b")

        ctx_a, _ = mod.extract_user_context(token=f"Bearer {alice}")
        ctx_b, _ = mod.extract_user_context(token=f"Bearer {bob}")

        assert ctx_a.user_id != ctx_b.user_id, (
            "Two different JWTs collapsed to the same user_id — "
            "workspace isolation is broken."
        )
        assert ctx_a.tenant_id != ctx_b.tenant_id, (
            "Two different JWTs collapsed to the same tenant_id — "
            "cross-tenant data leakage risk."
        )

    def test_same_user_same_context_across_calls(self, monkeypatch):
        """Idempotent: the same JWT always resolves to the same identity."""
        mod = _patch_cognito_auth(monkeypatch, DEV_MODE="true")
        token = _issue_token(mod, user_id="carol-uuid", tenant_id="tenant-c")

        ctx1, _ = mod.extract_user_context(token=f"Bearer {token}")
        ctx2, _ = mod.extract_user_context(token=f"Bearer {token}")

        assert ctx1.user_id == ctx2.user_id == "carol-uuid"
        assert ctx1.tenant_id == ctx2.tenant_id == "tenant-c"

    def test_jwt_preserves_email_and_roles(self, monkeypatch):
        mod = _patch_cognito_auth(monkeypatch, DEV_MODE="true")
        token = _issue_token(
            mod,
            user_id="dana-uuid",
            tenant_id="tenant-d",
            roles=["co", "admin"],
        )

        ctx, _ = mod.extract_user_context(token=f"Bearer {token}")

        # generate_test_token sets email to f"{user_id}@example.com"
        assert ctx.email == "dana-uuid@example.com", (
            "JWT email claim must reach UserContext so auditing and "
            "feedback attribution work."
        )
        assert "admin" in ctx.roles
        assert "co" in ctx.roles


# ══════════════════════════════════════════════════════════════════════
# 3. get_session_context propagates identity from JWT → session keys
# ══════════════════════════════════════════════════════════════════════


class TestSessionContextScoping:
    """
    get_session_context is what turns a UserContext into the
    (tenant_id, user_id, session_id) tuple that every downstream
    DynamoDB/S3 key uses. If it loses the JWT identity, every workspace
    write lands under the dev user.
    """

    def test_session_context_uses_jwt_user_and_tenant(self, monkeypatch):
        mod = _patch_cognito_auth(monkeypatch, DEV_MODE="true")
        token = _issue_token(mod, user_id="erin-uuid", tenant_id="tenant-e")
        ctx, _ = mod.extract_user_context(token=f"Bearer {token}")

        from app.routers.dependencies import get_session_context

        tenant_id, user_id, session_id = get_session_context(ctx, session_id="ses-1")

        assert tenant_id == "tenant-e"
        assert user_id == "erin-uuid"
        assert session_id == "ses-1"

    def test_session_context_generates_unique_sid_when_missing(self, monkeypatch):
        from app.routers.dependencies import get_session_context

        mod = _patch_cognito_auth(monkeypatch, DEV_MODE="true")
        token = _issue_token(mod, user_id="frank-uuid", tenant_id="tenant-f")
        ctx, _ = mod.extract_user_context(token=f"Bearer {token}")

        _, _, sid1 = get_session_context(ctx, session_id=None)
        _, _, sid2 = get_session_context(ctx, session_id=None)

        assert sid1 != sid2, "Missing session_id should produce unique UUIDs"
        assert len(sid1) >= 32


# ══════════════════════════════════════════════════════════════════════
# 4. /api/chat end-to-end — telemetry and session scoping track the JWT
# ══════════════════════════════════════════════════════════════════════


async def _mock_sdk_query(*args, **kwargs) -> AsyncGenerator:
    """Minimal stand-in so /api/chat returns 200 without hitting Bedrock."""
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "ok"

    assistant_msg = MagicMock()
    assistant_msg.__class__.__name__ = "AssistantMessage"
    assistant_msg.content = [text_block]

    result_msg = MagicMock()
    result_msg.__class__.__name__ = "ResultMessage"
    result_msg.usage = {"input_tokens": 1, "output_tokens": 1}
    result_msg.result = "ok"

    yield assistant_msg
    yield result_msg


async def _mock_sdk_query_streaming(*args, **kwargs) -> AsyncGenerator:
    yield {
        "type": "complete",
        "data": {
            "usage": {"input_tokens": 1, "output_tokens": 1},
            "response": "ok",
            "tools_called": [],
        },
    }


@pytest.fixture
def chat_app(monkeypatch):
    """
    Build a FastAPI app in DEV_MODE=true with the chat router mounted and
    the Strands runtime mocked. DEV_MODE is ON intentionally — that is the
    exact condition under which the bug occurs.
    """
    env_patch = {
        "DEV_MODE": "true",
        "REQUIRE_AUTH": "false",
        "USE_BEDROCK": "false",
        "COGNITO_USER_POOL_ID": "",
        "COGNITO_CLIENT_ID": "",
        "USE_PERSISTENT_SESSIONS": "false",
        "EAGLE_APP_ROUTERS": "chat,streaming",
    }
    with patch.dict(os.environ, env_patch, clear=False):
        # Force fresh imports in dependency order so every module picks up
        # DEV_MODE=true from the patched env AND gets a fresh
        # extract_user_context function reference. We use sys.modules.pop()
        # + plain import rather than importlib.reload() because in CI the
        # full suite runs 1500+ other tests first, and any of them may
        # leave these modules in a state where reload()'s identity check
        # (sys.modules[name] is module) fails. Pop + fresh import is
        # bulletproof against that.
        #
        # IMPORTANT: we must also pop EVERY app.routers.* module, not just
        # the ones this fixture re-imports. Each router module does
        # ``from .dependencies import get_user_from_header`` at load time
        # and caches that function object. If app.routers.dependencies is
        # re-imported here (new function object) but a downstream router
        # (e.g. app.routers.documents) is left cached, the router's routes
        # still reference the OLD function. Later tests that set
        # dependency_overrides via the NEW function as key then see their
        # overrides ignored, and real auth runs (returning the DEV_MODE
        # default tenant instead of the mock). Popping them here lets the
        # next test re-import them cleanly against the current dependencies
        # module.
        _base_pops = [
            "app.main",
            "app.streaming_routes",
            "app.routers.dependencies",
            "app.cognito_auth",
            "app.config",
        ]
        _router_pops = [m for m in list(sys.modules) if m.startswith("app.routers.")]
        for mod_name in _base_pops + _router_pops:
            sys.modules.pop(mod_name, None)

        import app.config as config_module  # noqa: F401
        import app.cognito_auth as cognito_auth
        import app.routers.dependencies as deps_module  # noqa: F401
        import app.routers.chat as chat_module  # noqa: F401
        import app.streaming_routes as streaming_module  # noqa: F401
        import app.main as main_module

        app = main_module.create_app(["chat", "streaming"])

        fake_runtime = MagicMock()
        fake_runtime.sdk_query = _mock_sdk_query
        fake_runtime.sdk_query_streaming = _mock_sdk_query_streaming
        fake_runtime.MODEL = "test-model"
        fake_runtime.EAGLE_TOOLS = []

        with patch(
            "app.routers.chat._get_strands_runtime", return_value=fake_runtime
        ), patch(
            "app.streaming_routes._get_strands_runtime", return_value=fake_runtime
        ):
            yield app, cognito_auth


class TestChatEndpointHonorsJwt:
    """
    Hit /api/chat with DEV_MODE=true and a real Bearer JWT. The telemetry
    row must record the JWT's user/tenant — not dev-user/dev-tenant.
    """

    def test_chat_records_jwt_user_in_telemetry(self, chat_app):
        app, cognito_auth = chat_app
        token = cognito_auth.generate_test_token(
            user_id="alice-chat-uuid",
            tenant_id="tenant-alice",
            tier="premium",
        )

        with TestClient(app) as client:
            resp = client.post(
                "/api/chat",
                json={"message": "hi", "session_id": "ses-alice"},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 200, resp.text

        from app.routers.chat import get_telemetry_log

        entries = [
            e for e in get_telemetry_log() if e.get("session_id") == "ses-alice"
        ]
        assert entries, "No telemetry row recorded for the request"
        latest = entries[-1]

        assert latest["user_id"] == "alice-chat-uuid", (
            f"Telemetry recorded user_id={latest['user_id']!r} — under "
            f"DEV_MODE=true the backend is overriding the JWT identity. "
            f"Every caller on dev shows up as the same user."
        )
        assert latest["tenant_id"] == "tenant-alice", (
            f"Telemetry recorded tenant_id={latest['tenant_id']!r} — "
            f"workspace isolation is broken."
        )

    def test_two_concurrent_users_are_distinct_in_telemetry(self, chat_app):
        app, cognito_auth = chat_app

        alice = cognito_auth.generate_test_token(
            user_id="alice-iso", tenant_id="tenant-alice-iso"
        )
        bob = cognito_auth.generate_test_token(
            user_id="bob-iso", tenant_id="tenant-bob-iso"
        )

        with TestClient(app) as client:
            r1 = client.post(
                "/api/chat",
                json={"message": "hello from alice", "session_id": "ses-a-iso"},
                headers={"Authorization": f"Bearer {alice}"},
            )
            r2 = client.post(
                "/api/chat",
                json={"message": "hello from bob", "session_id": "ses-b-iso"},
                headers={"Authorization": f"Bearer {bob}"},
            )

        assert r1.status_code == 200, r1.text
        assert r2.status_code == 200, r2.text

        from app.routers.chat import get_telemetry_log

        by_session = {e.get("session_id"): e for e in get_telemetry_log()}
        a_entry = by_session.get("ses-a-iso")
        b_entry = by_session.get("ses-b-iso")
        assert a_entry and b_entry, "Missing telemetry for one or both users"

        assert a_entry["user_id"] != b_entry["user_id"], (
            "Two users sending two different Bearer tokens ended up with "
            "the same user_id in telemetry — dev-mode is collapsing them."
        )
        assert a_entry["tenant_id"] != b_entry["tenant_id"], (
            "Two users ended up in the same tenant — workspaces are "
            "leaking across accounts."
        )
        assert a_entry["user_id"] == "alice-iso"
        assert b_entry["user_id"] == "bob-iso"

    def test_chat_without_auth_header_falls_back_to_dev_user(self, chat_app):
        """Sanity check: the permissive path (no header) still works."""
        app, _ = chat_app

        with TestClient(app) as client:
            resp = client.post(
                "/api/chat",
                json={"message": "hi", "session_id": "ses-no-auth"},
            )

        assert resp.status_code == 200, resp.text

        from app.routers.chat import get_telemetry_log

        entries = [
            e for e in get_telemetry_log() if e.get("session_id") == "ses-no-auth"
        ]
        assert entries
        assert entries[-1]["user_id"] == "dev-user"
        assert entries[-1]["tenant_id"] == "dev-tenant"
