"""
User API Router

Provides endpoints for user profile and preferences:
- User info (/api/user/me)
- Usage summary (/api/user/usage)
- User preferences (get/update/reset)
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends

from ..cognito_auth import UserContext
from ..session_store import get_usage_summary
from ..pref_store import get_prefs, update_prefs, reset_prefs
from .dependencies import get_user_from_header

router = APIRouter(prefix="/api/user", tags=["user"])

GENERIC_ANALYTICS_ERROR = "Analytics data is temporarily unavailable."


def _get_result_error(result: Any) -> Optional[str]:
    if isinstance(result, dict):
        error = result.get("error")
        if isinstance(error, str) and error:
            return error
    return None


def _sanitize_result_error(result: Dict[str, Any], fallback_error: str) -> Dict[str, Any]:
    sanitized = dict(result)
    sanitized["error"] = fallback_error
    return sanitized


@router.get("/me")
async def api_user_me(user: UserContext = Depends(get_user_from_header)):
    """Get current user info."""
    return user.to_dict()


@router.get("/usage")
async def api_user_usage(
    days: int = 30,
    user: UserContext = Depends(get_user_from_header),
):
    """Get usage summary for current user."""
    tenant_id = user.tenant_id
    result = get_usage_summary(tenant_id, days)
    error = _get_result_error(result)
    return _sanitize_result_error(result, GENERIC_ANALYTICS_ERROR) if error else result


@router.get("/preferences")
async def get_user_preferences(user: UserContext = Depends(get_user_from_header)):
    """Return the current user's preferences (merges with defaults)."""
    return get_prefs(user.tenant_id, user.user_id)


@router.put("/preferences")
async def update_user_preferences(
    body: Dict[str, Any],
    user: UserContext = Depends(get_user_from_header),
):
    """Update user preferences (partial update — only provided keys are changed)."""
    return update_prefs(user.tenant_id, user.user_id, body)


@router.delete("/preferences")
async def reset_user_preferences(user: UserContext = Depends(get_user_from_header)):
    """Reset all user preferences to system defaults."""
    return reset_prefs(user.tenant_id, user.user_id)
