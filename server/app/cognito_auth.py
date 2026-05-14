"""Compatibility shim — auth has moved to ``app.auth``.

Existing call sites (``from app.cognito_auth import UserContext`` and friends)
keep working. Real auth logic lives in :mod:`app.auth.dependencies`,
:mod:`app.auth.jwt_utils`, and :mod:`app.auth.router`.

Cognito-specific runtime helpers (``validate_token``, ``_get_jwks``) have
been removed. ``generate_test_token`` is kept as a thin Entra-equivalent
adapter so existing unit tests that mint HS256 tokens for the chat
endpoint don't have to be rewritten.
"""

from typing import List, Optional

from .auth.dependencies import (  # noqa: F401  (re-export)
    DEV_MODE,
    DEV_USER_ID,
    DEV_TENANT_ID,
    UserContext,
    extract_user_context,
    get_current_user,
    require_admin,
    require_auth,
)
from .auth.jwt_utils import create_session_token


def generate_test_token(
    *,
    user_id: str,
    tenant_id: str = "default",
    tier: str = "basic",
    roles: Optional[List[str]] = None,
) -> str:
    """Mint a session JWT decodable by the live auth stack — for tests only.

    Compat shim for tests that used the legacy Cognito ``generate_test_token``.
    Bridges to :func:`app.auth.jwt_utils.create_session_token`. The token is
    HS256-signed with the live ``JWT_SIGNING_KEY``; ``decode_session_token``
    in production code accepts it.
    """
    roles = roles or []
    return create_session_token(
        user_id=user_id,
        email=f"{user_id}@example.com",
        tenant_id=tenant_id,
        tier=tier,
        is_admin="admin" in [r.lower() for r in roles],
        extra_claims={"roles": roles} if roles else None,
    )


__all__ = [
    "DEV_MODE",
    "DEV_USER_ID",
    "DEV_TENANT_ID",
    "UserContext",
    "extract_user_context",
    "generate_test_token",
    "get_current_user",
    "require_admin",
    "require_auth",
]
