"""EAGLE authentication package — Microsoft Entra OIDC + local session JWT.

Replaces the legacy ``app.cognito_auth`` and ``app.auth`` modules.

Existing call sites import:

    from app.auth import get_current_user
    from app.cognito_auth import UserContext, extract_user_context, DEV_MODE

Both forms continue to work — ``cognito_auth`` is now a thin re-export shim.
"""

from .dependencies import (
    DEV_MODE,
    UserContext,
    extract_user_context,
    get_current_user,
    require_auth,
    require_admin,
)
from .jwt_utils import create_session_token, decode_session_token
from .router import router as auth_router

__all__ = [
    "DEV_MODE",
    "UserContext",
    "auth_router",
    "create_session_token",
    "decode_session_token",
    "extract_user_context",
    "get_current_user",
    "require_admin",
    "require_auth",
]
