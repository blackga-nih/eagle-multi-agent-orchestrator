"""
Tests for cognito_auth module — verifies DEV_MODE toggle, UserContext,
extract_user_context, and token validation behavior.

Run: pytest server/tests/test_cognito_auth.py -v
"""

import os
import sys
import importlib
from unittest.mock import patch

import pytest

_server_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)


def _reload_cognito_auth(**env_overrides):
    """Reload cognito_auth with the given env vars so module-level globals reset."""
    env = {
        "DEV_MODE": "false",
        "DEV_USER_ID": "dev-user",
        "DEV_TENANT_ID": "dev-tenant",
        "COGNITO_USER_POOL_ID": "us-east-1_TestPool",
        "COGNITO_CLIENT_ID": "test-client-id",
        "AWS_REGION": "us-east-1",
    }
    env.update(env_overrides)
    with patch.dict(os.environ, env, clear=False):
        import app.cognito_auth as mod
        importlib.reload(mod)
        return mod


def _patch_cognito_auth(monkeypatch, **overrides):
    """
    Return a reference to app.cognito_auth with module-level variables patched
    via monkeypatch.setattr() instead of importlib.reload().

    This avoids state leakage caused by app.config being a frozen singleton
    that is not re-evaluated on reload — meaning DEV_MODE and other flags read
    from auth_config stay stale across tests when reload() is used.

    Supported overrides (all optional, defaults match a non-dev configuration):
        DEV_MODE            bool or str  (default False)
        DEV_USER_ID         str          (default "dev-user")
        DEV_TENANT_ID       str          (default "dev-tenant")
        COGNITO_USER_POOL_ID str         (default "us-east-1_TestPool")
        COGNITO_CLIENT_ID   str          (default "test-client-id")
    """
    import app.cognito_auth as mod

    defaults = {
        "DEV_MODE": False,
        "DEV_USER_ID": "dev-user",
        "DEV_TENANT_ID": "dev-tenant",
        "COGNITO_USER_POOL_ID": "us-east-1_TestPool",
        "COGNITO_CLIENT_ID": "test-client-id",
    }
    # Allow string "true"/"false" for DEV_MODE, mirroring the env-var style
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


# ── UserContext unit tests ────────────────────────────────────────────


class TestUserContext:
    """Tests for UserContext class (no module reload needed)."""

    def setup_method(self):
        self.mod = _reload_cognito_auth()

    def test_dev_user_returns_dev_defaults(self):
        ctx = self.mod.UserContext.dev_user()
        assert ctx.user_id == "dev-user"
        assert ctx.tenant_id == "dev-tenant"
        assert ctx.email == "dev-user@example.com"
        assert ctx.roles == ["admin"]
        assert ctx.tier == "premium"
        assert ctx.is_admin() is True
        assert ctx.is_premium() is True

    def test_anonymous_user(self):
        ctx = self.mod.UserContext.anonymous()
        assert ctx.user_id == "anonymous"
        assert ctx.tenant_id == "default"
        assert ctx.tier == "free"
        assert ctx.is_admin() is False

    def test_from_claims_maps_cognito_fields(self):
        claims = {
            "sub": "abc-123",
            "custom:tenant_id": "nci-tenant",
            "email": "blackga@nih.gov",
            "cognito:username": "blackga",
            "cognito:groups": ["admin", "co"],
            "custom:tier": "premium",
        }
        ctx = self.mod.UserContext.from_claims(claims)
        assert ctx.user_id == "abc-123"
        assert ctx.tenant_id == "nci-tenant"
        assert ctx.email == "blackga@nih.gov"
        assert ctx.username == "blackga"
        assert ctx.roles == ["admin", "co"]
        assert ctx.tier == "premium"
        assert ctx.is_admin() is True

    def test_from_claims_defaults_for_missing_fields(self):
        ctx = self.mod.UserContext.from_claims({})
        assert ctx.user_id == "anonymous"
        assert ctx.tenant_id == "default"
        assert ctx.tier == "free"
        assert ctx.email is None

    def test_to_dict_roundtrip(self):
        ctx = self.mod.UserContext(
            user_id="u1", tenant_id="t1", email="a@b.com",
            username="a", roles=["r1"], tier="premium",
        )
        d = ctx.to_dict()
        assert d == {
            "user_id": "u1",
            "tenant_id": "t1",
            "email": "a@b.com",
            "username": "a",
            "roles": ["r1"],
            "tier": "premium",
        }


# ── DEV_MODE toggle tests ────────────────────────────────────────────


class TestDevModeToggle:
    """Verify that DEV_MODE=true vs false changes auth behavior."""

    def test_dev_mode_true_bypasses_validation(self, monkeypatch):
        mod = _patch_cognito_auth(monkeypatch, DEV_MODE="true")
        assert mod.DEV_MODE is True
        is_valid, claims, err = mod.validate_token("any-garbage-token")
        assert is_valid is True
        assert claims["sub"] == "dev-user"
        assert err is None

    def test_dev_mode_false_rejects_garbage_token(self, monkeypatch):
        mod = _patch_cognito_auth(monkeypatch, DEV_MODE="false")
        assert mod.DEV_MODE is False
        is_valid, claims, err = mod.validate_token("not-a-real-jwt")
        assert is_valid is False
        assert claims is None
        assert err is not None

    def test_dev_mode_simple_validation_bypass(self, monkeypatch):
        mod = _patch_cognito_auth(monkeypatch, DEV_MODE="true")
        is_valid, claims, err = mod.validate_token_simple("garbage")
        assert is_valid is True
        assert claims["sub"] == "dev-user"


# ── extract_user_context tests ───────────────────────────────────────


class TestExtractUserContext:
    """Tests for the main extract_user_context() entry point."""

    def test_dev_mode_returns_dev_user_regardless_of_token(self, monkeypatch):
        mod = _patch_cognito_auth(monkeypatch, DEV_MODE="true")
        ctx, err = mod.extract_user_context(token=None)
        assert err is None
        assert ctx.user_id == "dev-user"
        assert ctx.tenant_id == "dev-tenant"

        # Even with a fake token, dev mode still returns dev user
        ctx2, err2 = mod.extract_user_context(token="Bearer fake.jwt.here")
        assert err2 is None
        assert ctx2.user_id == "dev-user"

    def test_non_dev_no_token_returns_anonymous(self, monkeypatch):
        mod = _patch_cognito_auth(monkeypatch, DEV_MODE="false")
        ctx, err = mod.extract_user_context(token=None)
        assert ctx.user_id == "anonymous"
        assert err == "No token provided"

    def test_non_dev_invalid_token_returns_anonymous(self, monkeypatch):
        mod = _patch_cognito_auth(monkeypatch, DEV_MODE="false")
        ctx, err = mod.extract_user_context(token="Bearer bad-token", validate=True)
        assert ctx.user_id == "anonymous"
        assert err is not None

    def test_bearer_prefix_stripped(self, monkeypatch):
        """extract_user_context strips 'Bearer ' before passing to validator."""
        # Use simple validation path (no Cognito configured)
        mod = _patch_cognito_auth(
            monkeypatch, DEV_MODE="false",
            COGNITO_USER_POOL_ID="", COGNITO_CLIENT_ID="",
        )
        # With empty pool, validate path goes to validate_token_simple
        # which will try to decode the JWT — will fail for garbage, but
        # the important thing is the Bearer prefix is stripped
        ctx, err = mod.extract_user_context(
            token="Bearer not.valid.jwt", validate=True
        )
        # Should be anonymous since token is invalid
        assert ctx.user_id == "anonymous"

    def test_non_dev_with_valid_simple_jwt(self, monkeypatch):
        """A properly structured JWT decoded with simple validation succeeds."""
        mod = _patch_cognito_auth(
            monkeypatch,
            DEV_MODE="false",
            COGNITO_USER_POOL_ID="",
            COGNITO_CLIENT_ID="",
        )
        # generate_test_token produces an HS256 JWT
        token = mod.generate_test_token(
            user_id="blackga", tenant_id="nci", tier="premium", roles=["co"]
        )
        assert token, "PyJWT must be installed for this test"

        # validate=False path or simple validation (no cognito configured)
        ctx, err = mod.extract_user_context(token=f"Bearer {token}", validate=True)
        assert err is None
        assert ctx.user_id == "blackga"
        assert ctx.tenant_id == "nci"
        assert ctx.tier == "premium"


# ── generate_test_token tests ────────────────────────────────────────


class TestGenerateTestToken:

    def test_generates_decodable_jwt(self):
        mod = _reload_cognito_auth()
        token = mod.generate_test_token(
            user_id="test-u", tenant_id="test-t", roles=["admin"], tier="premium"
        )
        assert token
        import jwt
        claims = jwt.decode(token, options={"verify_signature": False})
        assert claims["sub"] == "test-u"
        assert claims["custom:tenant_id"] == "test-t"
        assert claims["cognito:groups"] == ["admin"]
        assert claims["custom:tier"] == "premium"
        assert claims["email"] == "test-u@example.com"

    def test_token_has_expiry(self):
        mod = _reload_cognito_auth()
        token = mod.generate_test_token(expiry_hours=1)
        import jwt
        claims = jwt.decode(token, options={"verify_signature": False})
        assert "exp" in claims
        assert claims["exp"] > claims["iat"]


# ── require_auth / require_admin tests ───────────────────────────────


class TestAuthGuards:

    def setup_method(self):
        self.mod = _reload_cognito_auth()

    def test_require_auth_passes_for_real_user(self):
        ctx = self.mod.UserContext(user_id="real-user")
        result = self.mod.require_auth(ctx)
        assert result.user_id == "real-user"

    def test_require_auth_rejects_anonymous(self):
        ctx = self.mod.UserContext.anonymous()
        with pytest.raises(Exception) as exc_info:
            self.mod.require_auth(ctx)
        assert "401" in str(exc_info.value.status_code)

    def test_require_admin_passes_for_admin(self):
        ctx = self.mod.UserContext(user_id="admin-u", roles=["admin"])
        result = self.mod.require_admin(ctx)
        assert result.user_id == "admin-u"

    def test_require_admin_rejects_non_admin(self):
        ctx = self.mod.UserContext(user_id="regular-u", roles=["co"])
        with pytest.raises(Exception) as exc_info:
            self.mod.require_admin(ctx)
        assert "403" in str(exc_info.value.status_code)
