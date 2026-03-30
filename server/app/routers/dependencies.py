"""
Shared dependencies for EAGLE API routers.

Provides authentication helpers and common utilities used across multiple routers.
"""

import uuid
from typing import Optional

from fastapi import Header, HTTPException

from ..cognito_auth import UserContext, extract_user_context
from ..config import auth as auth_config

REQUIRE_AUTH = auth_config.require_auth


async def get_user_from_header(
    authorization: Optional[str] = Header(None),
) -> UserContext:
    """Extract user from Authorization header (EAGLE Cognito auth)."""
    user, error = extract_user_context(authorization)
    if REQUIRE_AUTH and user.user_id == "anonymous":
        raise HTTPException(status_code=401, detail=error or "Authentication required")
    return user


def get_session_context(user: UserContext, session_id: Optional[str] = None) -> tuple:
    """Get tenant_id, user_id, and session_id from user context."""
    tenant_id = user.tenant_id
    user_id = user.user_id
    sid = session_id or str(uuid.uuid4())
    return tenant_id, user_id, sid
