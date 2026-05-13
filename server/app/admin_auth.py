"""Admin authorization helpers.

Source of truth for "is this user an admin" is the ``is_admin`` claim on the
local session JWT, which was populated at OIDC callback time from the
``USER#<email>`` DynamoDB profile. Multi-tenant admin scoping collapses to
"admin within their own tenant" — there is no per-tenant admin matrix in v1.
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import Depends, HTTPException

from app.auth import get_current_user


class AdminAuthService:
    """Lightweight helper retained for the few existing call sites.

    The legacy implementation queried Cognito groups; the new model reads
    ``is_admin`` and ``tenant_id`` straight off the resolved user dict.
    """

    @staticmethod
    def is_tenant_admin(user_context: Dict[str, Any], tenant_id: str) -> bool:
        return bool(user_context.get("is_admin")) and (
            user_context.get("tenant_id") == tenant_id
        )

    @staticmethod
    def get_admin_tenants(user_context: Dict[str, Any]) -> List[str]:
        if user_context.get("is_admin") and user_context.get("tenant_id"):
            return [str(user_context["tenant_id"])]
        return []


async def get_admin_user(
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """FastAPI dependency that fails 403 unless the caller is an admin."""
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    admin_tenants = AdminAuthService.get_admin_tenants(current_user)
    return {
        **current_user,
        "admin_tenants": admin_tenants,
        "admin_groups": [f"{t}-admins" for t in admin_tenants],
    }


async def verify_tenant_admin(
    tenant_id: str,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Dependency that asserts admin access for a specific tenant."""
    if not AdminAuthService.is_tenant_admin(current_user, tenant_id):
        raise HTTPException(
            status_code=403, detail=f"Admin access required for tenant {tenant_id}"
        )
    return current_user
