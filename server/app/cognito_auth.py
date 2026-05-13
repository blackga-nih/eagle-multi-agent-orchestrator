"""Compatibility shim — auth has moved to ``app.auth``.

Existing call sites (``from app.cognito_auth import UserContext`` and friends)
keep working. Real auth logic lives in :mod:`app.auth.dependencies`,
:mod:`app.auth.jwt_utils`, and :mod:`app.auth.router`.

The Cognito-specific helpers (``validate_token``, ``generate_test_token``,
``_get_jwks``, etc.) have been removed; if anything still imports them the
import error will surface at start-up rather than silently dispatching to
dead code.
"""

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

__all__ = [
    "DEV_MODE",
    "DEV_USER_ID",
    "DEV_TENANT_ID",
    "UserContext",
    "extract_user_context",
    "get_current_user",
    "require_admin",
    "require_auth",
]
