"""FastAPI auth dependencies and the ``UserContext`` shape.

Compatibility contract — every existing call site keeps working:

    from app.cognito_auth import UserContext, extract_user_context, DEV_MODE
    from app.auth import get_current_user

The ``UserContext`` constructor signature, ``from_claims`` classmethod, and
helpers (``is_admin``, ``is_premium``, ``to_dict``, ``anonymous``,
``dev_user``) are preserved so direct constructor use in tests and helper
scripts continues to compile.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .jwt_utils import decode_session_token_safe

DEV_MODE = os.getenv("DEV_MODE", "false").lower() == "true"
DEV_USER_ID = os.getenv("DEV_USER_ID", "dev-user")
DEV_TENANT_ID = os.getenv("DEV_TENANT_ID", "dev-tenant")

_security = HTTPBearer(auto_error=not DEV_MODE)


# ── UserContext ──────────────────────────────────────────────────────────────


class UserContext:
    """Resolved user/tenant/role for the current request.

    Built from local session JWT claims minted at ``/api/auth/callback`` after
    Entra login, or from ``DEV_MODE`` defaults. The shape matches the legacy
    ``app.cognito_auth.UserContext`` so existing imports keep compiling.
    """

    def __init__(
        self,
        user_id: str,
        tenant_id: str = "default",
        email: Optional[str] = None,
        username: Optional[str] = None,
        roles: Optional[List[str]] = None,
        tier: str = "basic",
        claims: Optional[Dict[str, Any]] = None,
        display_name: Optional[str] = None,
        is_admin: bool = False,
    ) -> None:
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.email = email
        self.username = username or user_id
        self.roles = list(roles or [])
        self.tier = tier
        self.claims = claims or {}
        self.display_name = display_name or self.username
        self._is_admin = bool(is_admin) or "admin" in [r.lower() for r in self.roles]

    # — factories —

    @classmethod
    def from_claims(cls, claims: Dict[str, Any]) -> "UserContext":
        is_admin = bool(claims.get("is_admin", False))
        roles: List[str] = list(claims.get("roles", []))
        if is_admin and "admin" not in [r.lower() for r in roles]:
            roles.append("admin")
        return cls(
            user_id=str(claims.get("sub") or claims.get("email") or "anonymous"),
            tenant_id=str(claims.get("tenant_id", claims.get("custom:tenant_id", "default"))),
            email=claims.get("email"),
            username=claims.get("email") or claims.get("sub"),
            roles=roles,
            tier=str(claims.get("tier", claims.get("custom:tier", "basic"))),
            display_name=claims.get("display_name"),
            is_admin=is_admin,
            claims=claims,
        )

    @classmethod
    def anonymous(cls) -> "UserContext":
        return cls(user_id="anonymous", tenant_id="default", tier="basic")

    @classmethod
    def dev_user(cls) -> "UserContext":
        return cls(
            user_id=DEV_USER_ID,
            tenant_id=DEV_TENANT_ID,
            email=f"{DEV_USER_ID}@example.com",
            username=DEV_USER_ID,
            roles=["admin"],
            tier="premium",
            display_name="Dev User",
            is_admin=True,
        )

    # — predicates / serialization —

    def is_admin(self) -> bool:
        return self._is_admin

    def is_premium(self) -> bool:
        return self.tier.lower() in ("premium", "enterprise", "pro", "advanced")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "email": self.email,
            "username": self.username,
            "roles": self.roles,
            "tier": self.tier,
            "is_admin": self._is_admin,
            "display_name": self.display_name,
        }


# ── Token → UserContext ──────────────────────────────────────────────────────


def extract_user_context(
    token: Optional[str] = None,
    validate: bool = True,  # kept for signature compat; always validated now
) -> Tuple[UserContext, Optional[str]]:
    """Decode the session JWT into a ``UserContext``.

    Returns ``(UserContext, error)``. Anonymous user is returned when the
    token is missing/invalid; callers gate behind ``REQUIRE_AUTH`` to convert
    that into a 401.
    """
    if DEV_MODE and not token:
        return UserContext.dev_user(), None

    if not token:
        return UserContext.anonymous(), "No token provided"

    if token.startswith("Bearer "):
        token = token[7:]

    ok, claims, error = decode_session_token_safe(token)
    if not ok:
        if DEV_MODE:
            return UserContext.dev_user(), None
        return UserContext.anonymous(), error

    return UserContext.from_claims(claims), None


# ── FastAPI dependencies ─────────────────────────────────────────────────────


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_security),
) -> Dict[str, Any]:
    """Dependency that returns the current user as a dict.

    Mirrors the legacy ``app.auth.get_current_user`` shape (a dict with
    ``user_id``/``tenant_id``/``subscription_tier``/``email``/``role``) so
    existing callers in ``admin_auth`` and ``routers/tenants.py`` keep working.
    """
    if DEV_MODE and (credentials is None or credentials.credentials in {"", "dev-mode-token"}):
        return UserContext.dev_user().to_dict() | {
            "subscription_tier": "premium",
            "role": "admin",
        }

    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user, error = extract_user_context(credentials.credentials)
    if user.user_id == "anonymous":
        raise HTTPException(status_code=401, detail=error or "Not authenticated")

    payload = user.to_dict()
    # Aliases for backwards compat with code that read the legacy dict shape.
    payload["subscription_tier"] = user.tier
    payload["role"] = "admin" if user.is_admin() else "user"
    return payload


def require_auth(user: UserContext) -> UserContext:
    if user.user_id == "anonymous":
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def require_admin(user: UserContext) -> UserContext:
    if not user.is_admin():
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
