"""Tests for the Entra-based auth module.

Covers:
  * UserContext shape (anonymous, dev_user, from_claims)
  * Local HS256 session JWT round-trip via create_session_token / decode_session_token
  * extract_user_context handling of Bearer prefix, expired tokens, missing tokens
  * DynamoDB-backed user_directory.get_user_profile (mocked table)

Run: pytest server/tests/test_auth_entra.py -v
"""

from __future__ import annotations

import os
import sys
import time
from unittest.mock import patch

import pytest

_server_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)


# A long-enough HS256 key to silence PyJWT's InsecureKeyLengthWarning so
# pytest --strict-warnings doesn't choke on it.
_TEST_KEY = "a" * 64


@pytest.fixture(autouse=True)
def _signing_key(monkeypatch):
    monkeypatch.setenv("JWT_SIGNING_KEY", _TEST_KEY)
    yield


# ── UserContext ──────────────────────────────────────────────────────────────


class TestUserContext:
    def test_anonymous(self):
        from app.auth import UserContext

        ctx = UserContext.anonymous()
        assert ctx.user_id == "anonymous"
        assert ctx.tenant_id == "default"
        assert ctx.is_admin() is False

    def test_dev_user(self):
        from app.auth import UserContext

        ctx = UserContext.dev_user()
        assert ctx.user_id == "dev-user"
        assert ctx.tenant_id == "dev-tenant"
        assert ctx.tier == "premium"
        assert ctx.is_admin() is True
        assert ctx.is_premium() is True

    def test_from_claims_promotes_admin_role(self):
        from app.auth import UserContext

        claims = {
            "sub": "alice",
            "email": "alice@nih.gov",
            "tenant_id": "nci",
            "tier": "premium",
            "is_admin": True,
            "display_name": "Alice",
        }
        ctx = UserContext.from_claims(claims)
        assert ctx.user_id == "alice"
        assert ctx.email == "alice@nih.gov"
        assert ctx.tenant_id == "nci"
        assert ctx.is_admin() is True
        assert "admin" in ctx.roles


# ── Session JWT round-trip ───────────────────────────────────────────────────


class TestSessionToken:
    def test_create_and_decode_roundtrip(self):
        from app.auth.jwt_utils import create_session_token, decode_session_token

        tok = create_session_token(
            user_id="alice",
            email="alice@nih.gov",
            tenant_id="nci",
            tier="premium",
            is_admin=True,
            display_name="Alice",
        )
        claims = decode_session_token(tok)
        assert claims["sub"] == "alice"
        assert claims["email"] == "alice@nih.gov"
        assert claims["tenant_id"] == "nci"
        assert claims["tier"] == "premium"
        assert claims["is_admin"] is True
        assert "exp" in claims and claims["exp"] > time.time()

    def test_expired_token_returns_error(self):
        from app.auth.jwt_utils import create_session_token, decode_session_token_safe

        tok = create_session_token(
            user_id="alice",
            email="alice@nih.gov",
            tenant_id="nci",
            expire_minutes=-1,  # already expired
        )
        ok, claims, err = decode_session_token_safe(tok)
        assert ok is False
        assert claims == {}
        assert err and "expired" in err.lower()

    def test_invalid_token_returns_error(self):
        from app.auth.jwt_utils import decode_session_token_safe

        ok, _, err = decode_session_token_safe("not.a.token")
        assert ok is False
        assert err

    def test_extract_user_context_strips_bearer_prefix(self):
        from app.auth import extract_user_context
        from app.auth.jwt_utils import create_session_token

        tok = create_session_token(
            user_id="alice",
            email="alice@nih.gov",
            tenant_id="nci",
            tier="advanced",
            is_admin=False,
        )
        ctx, err = extract_user_context(f"Bearer {tok}")
        assert err is None
        assert ctx.user_id == "alice"
        assert ctx.tier == "advanced"
        assert ctx.is_admin() is False
        assert ctx.is_premium() is True  # advanced counts as premium tier-up

    def test_no_token_returns_anonymous(self, monkeypatch):
        # Ensure DEV_MODE is off so anonymous bubbles up.
        monkeypatch.setenv("DEV_MODE", "false")
        # Re-import dependencies so DEV_MODE is re-read at module level.
        import importlib
        import app.auth.dependencies as deps
        importlib.reload(deps)

        ctx, err = deps.extract_user_context(None)
        assert ctx.user_id == "anonymous"
        assert err == "No token provided"


# ── User directory (DynamoDB lookup) ─────────────────────────────────────────


class TestUserDirectory:
    def test_get_user_profile_present(self):
        from app.auth import user_directory

        fake_item = {
            "PK": "USER#alice@nih.gov",
            "SK": "PROFILE",
            "email": "alice@nih.gov",
            "tenant_id": "nci",
            "subscription_tier": "premium",
            "is_admin": True,
            "enabled": True,
            "display_name": "Alice Smith",
        }

        class _StubTable:
            def get_item(self, Key):  # noqa: N803  (boto3 api)
                assert Key == {"PK": "USER#alice@nih.gov", "SK": "PROFILE"}
                return {"Item": fake_item}

        with patch.object(user_directory, "get_table", lambda: _StubTable()):
            profile = user_directory.get_user_profile("Alice@NIH.gov")
        assert profile is not None
        assert profile.email == "alice@nih.gov"
        assert profile.tenant_id == "nci"
        assert profile.tier == "premium"
        assert profile.is_admin is True
        assert profile.authorized is True

    def test_get_user_profile_missing(self):
        from app.auth import user_directory

        class _StubTable:
            def get_item(self, Key):
                return {}

        with patch.object(user_directory, "get_table", lambda: _StubTable()):
            assert user_directory.get_user_profile("ghost@nih.gov") is None

    def test_get_user_profile_disabled(self):
        from app.auth import user_directory

        class _StubTable:
            def get_item(self, Key):
                return {
                    "Item": {
                        "PK": "USER#bob@nih.gov",
                        "SK": "PROFILE",
                        "email": "bob@nih.gov",
                        "tenant_id": "nci",
                        "subscription_tier": "basic",
                        "is_admin": False,
                        "enabled": False,
                    }
                }

        with patch.object(user_directory, "get_table", lambda: _StubTable()):
            profile = user_directory.get_user_profile("bob@nih.gov")
        assert profile is not None
        assert profile.authorized is False


# ── Compat shim ──────────────────────────────────────────────────────────────


class TestCompatShim:
    def test_cognito_auth_re_exports(self):
        # Compare by qualified name so the test survives an importlib.reload of
        # app.auth.dependencies in another test (which produces a fresh
        # UserContext class object that is "==" by name but not "is").
        from app import auth as auth_pkg
        from app import cognito_auth as compat

        for attr in ("UserContext", "extract_user_context", "get_current_user"):
            assert getattr(compat, attr).__qualname__ == getattr(
                auth_pkg, attr
            ).__qualname__

        # The shim must expose the DEV_MODE flag too.
        assert hasattr(compat, "DEV_MODE")
