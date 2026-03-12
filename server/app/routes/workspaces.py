"""Workspace CRUD and workspace override endpoints."""

import logging
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException

from ..cognito_auth import UserContext
from ..stores.workspace_store import (
    get_or_create_default, create_workspace, get_workspace,
    list_workspaces, activate_workspace, delete_workspace,
)
from ..stores.workspace_config_store import (
    put_override, list_overrides,
    delete_override, delete_all_overrides,
)
from ._deps import get_user_from_header

logger = logging.getLogger("eagle")
router = APIRouter(tags=["workspaces"])


# ── Workspace CRUD ────────────────────────────────────────────────────

@router.get("/api/workspace")
async def list_user_workspaces(user: UserContext = Depends(get_user_from_header)):
    """List all workspaces for the current user."""
    return list_workspaces(user.tenant_id, user.user_id)


@router.post("/api/workspace")
async def create_user_workspace(
    body: Dict[str, Any],
    user: UserContext = Depends(get_user_from_header),
):
    """Create a new workspace for the current user."""
    ws = create_workspace(
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        name=body.get("name", "New Workspace"),
        description=body.get("description", ""),
        visibility=body.get("visibility", "private"),
        is_active=body.get("is_active", False),
    )
    return ws


@router.get("/api/workspace/active")
async def get_active_workspace_endpoint(user: UserContext = Depends(get_user_from_header)):
    """Return the currently active workspace (auto-provisions Default if none exists)."""
    return get_or_create_default(user.tenant_id, user.user_id)


@router.get("/api/workspace/{workspace_id}")
async def get_workspace_endpoint(
    workspace_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Get a workspace by ID."""
    ws = get_workspace(user.tenant_id, user.user_id, workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return ws


@router.put("/api/workspace/{workspace_id}/activate")
async def activate_workspace_endpoint(
    workspace_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Switch active workspace."""
    ws = activate_workspace(user.tenant_id, user.user_id, workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return ws


@router.delete("/api/workspace/{workspace_id}")
async def delete_workspace_endpoint(
    workspace_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Delete a non-default workspace and all its overrides."""
    delete_all_overrides(user.tenant_id, user.user_id, workspace_id)
    ok = delete_workspace(user.tenant_id, user.user_id, workspace_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Cannot delete default workspace or workspace not found")
    return {"deleted": workspace_id}


# ── Workspace Overrides (WSPC#) ──────────────────────────────────────

@router.get("/api/workspace/{workspace_id}/overrides")
async def list_workspace_overrides(
    workspace_id: str,
    entity_type: Optional[str] = None,
    user: UserContext = Depends(get_user_from_header),
):
    """List all overrides in a workspace."""
    return list_overrides(user.tenant_id, user.user_id, workspace_id, entity_type)


@router.put("/api/workspace/{workspace_id}/overrides/{entity_type}/{name}")
async def set_workspace_override(
    workspace_id: str,
    entity_type: str,
    name: str,
    body: Dict[str, Any],
    user: UserContext = Depends(get_user_from_header),
):
    """Set a workspace override for an agent, skill, template, or config."""
    return put_override(
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        workspace_id=workspace_id,
        entity_type=entity_type,
        name=name,
        content=body.get("content", ""),
        is_append=body.get("is_append", False),
    )


@router.delete("/api/workspace/{workspace_id}/overrides/{entity_type}/{name}")
async def delete_workspace_override(
    workspace_id: str,
    entity_type: str,
    name: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Delete a specific override (reset to default for this entity)."""
    ok = delete_override(user.tenant_id, user.user_id, workspace_id, entity_type, name)
    return {"deleted": ok}


@router.delete("/api/workspace/{workspace_id}/overrides")
async def reset_workspace_overrides(
    workspace_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Delete all overrides in a workspace (reset entire workspace to defaults)."""
    count = delete_all_overrides(user.tenant_id, user.user_id, workspace_id)
    return {"deleted_count": count}
