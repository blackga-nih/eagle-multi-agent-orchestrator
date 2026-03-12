"""Template CRUD endpoints."""

import logging
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends

from ..cognito_auth import UserContext
from ..stores.template_store import (
    put_template, delete_template,
    list_tenant_templates, resolve_template,
)
from ._deps import get_user_from_header

logger = logging.getLogger("eagle")
router = APIRouter(tags=["templates"])


@router.get("/api/templates")
async def list_templates_endpoint(
    doc_type: Optional[str] = None,
    user: UserContext = Depends(get_user_from_header),
):
    """List available templates for the current tenant."""
    return list_tenant_templates(user.tenant_id, doc_type)


@router.get("/api/templates/{doc_type}")
async def get_active_template(
    doc_type: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Return the resolved template for this user (4-layer fallback)."""
    body, source = resolve_template(user.tenant_id, user.user_id, doc_type)
    return {"doc_type": doc_type, "template_body": body, "source": source}


@router.post("/api/templates/{doc_type}")
async def create_template_endpoint(
    doc_type: str,
    body: Dict[str, Any],
    user: UserContext = Depends(get_user_from_header),
):
    """Create or update a user/tenant template override."""
    return put_template(
        tenant_id=user.tenant_id,
        doc_type=doc_type,
        user_id=body.get("user_id", user.user_id),
        template_body=body.get("template_body", ""),
        display_name=body.get("display_name", ""),
        is_default=body.get("is_default", False),
    )


@router.delete("/api/templates/{doc_type}")
async def delete_template_endpoint(
    doc_type: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Delete the current user's template override for a doc type."""
    ok = delete_template(user.tenant_id, doc_type, user.user_id)
    return {"deleted": ok}
