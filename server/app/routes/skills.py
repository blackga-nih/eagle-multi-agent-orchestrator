"""User-created skills (SKILL#) CRUD endpoints."""

import logging
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException

from ..cognito_auth import UserContext
from ..stores.skill_store import (
    create_skill, get_skill, update_skill, list_skills,
    submit_for_review, publish_skill, delete_skill,
)
from ..stores.audit_store import write_audit
from ._deps import get_user_from_header

logger = logging.getLogger("eagle")
router = APIRouter(tags=["skills"])


@router.get("/api/skills")
async def list_skills_endpoint(
    status: Optional[str] = None,
    user: UserContext = Depends(get_user_from_header),
):
    """List user-created skills. Returns active bundled + tenant SKILL# items."""
    return list_skills(user.tenant_id, status)


@router.post("/api/skills")
async def create_skill_endpoint(
    body: Dict[str, Any],
    user: UserContext = Depends(get_user_from_header),
):
    """Create a new user skill (status=draft)."""
    return create_skill(
        tenant_id=user.tenant_id,
        owner_user_id=user.user_id,
        name=body["name"],
        display_name=body.get("display_name", body["name"]),
        description=body.get("description", ""),
        prompt_body=body.get("prompt_body", ""),
        triggers=body.get("triggers"),
        tools=body.get("tools"),
        model=body.get("model"),
        visibility=body.get("visibility", "private"),
    )


@router.get("/api/skills/{skill_id}")
async def get_skill_endpoint(
    skill_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Get a skill by ID."""
    skill = get_skill(user.tenant_id, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return skill


@router.put("/api/skills/{skill_id}")
async def update_skill_endpoint(
    skill_id: str,
    body: Dict[str, Any],
    user: UserContext = Depends(get_user_from_header),
):
    """Update a draft skill."""
    updated = update_skill(user.tenant_id, skill_id, body)
    if not updated:
        raise HTTPException(status_code=404, detail="Skill not found")
    return updated


@router.post("/api/skills/{skill_id}/submit")
async def submit_skill_endpoint(
    skill_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Submit a skill for review (draft → review)."""
    skill = submit_for_review(user.tenant_id, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found or not in draft status")
    return skill


@router.post("/api/skills/{skill_id}/publish")
async def publish_skill_endpoint(
    skill_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Approve and activate a skill (review → active). Admin action."""
    skill = publish_skill(user.tenant_id, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found or not in review status")
    write_audit(
        tenant_id=user.tenant_id,
        entity_type="skill",
        entity_name=skill_id,
        event_type="publish",
        actor_user_id=user.user_id,
    )
    return skill


@router.delete("/api/skills/{skill_id}")
async def delete_skill_endpoint(
    skill_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Delete a skill (only draft or disabled)."""
    ok = delete_skill(user.tenant_id, skill_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Skill not found or cannot be deleted (must be draft or disabled)")
    return {"deleted": skill_id}
