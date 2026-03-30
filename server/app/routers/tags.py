"""
EAGLE Tags Router

Owns document/package tag management and cross-entity tag search.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, Request

from ..cognito_auth import UserContext
from ..tag_store import (
    add_tags,
    find_entities_by_tag,
    get_entity_tags,
    remove_tags,
    update_entity_tags,
)
from .dependencies import get_user_from_header

router = APIRouter(tags=["tags"])


def _normalize_tag_payload(tags: Any) -> list[dict[str, str]]:
    if isinstance(tags, list) and all(isinstance(tag, str) for tag in tags):
        return [{"type": "user", "value": tag} for tag in tags]
    return tags if isinstance(tags, list) else []


def _merge_user_tags(current: dict[str, Any], tags: list[dict[str, str]]) -> list[str]:
    new_values = [tag.get("value", "") for tag in tags if tag.get("value")]
    return list(set(current.get("user_tags", []) + new_values))


@router.get("/api/documents/{doc_id}/tags")
async def get_document_tags(
    doc_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Get all tags for a document."""
    return get_entity_tags(user.tenant_id, "document", doc_id)


@router.post("/api/documents/{doc_id}/tags")
async def add_document_tags(
    doc_id: str,
    request: Request,
    user: UserContext = Depends(get_user_from_header),
):
    """Add user tags to a document."""
    body = await request.json()
    tags = _normalize_tag_payload(body.get("tags", []))
    written = add_tags(user.tenant_id, "document", doc_id, tags)
    current = get_entity_tags(user.tenant_id, "document", doc_id)
    update_entity_tags(
        user.tenant_id, "document", doc_id, user_tags=_merge_user_tags(current, tags)
    )
    return {"added": written}


@router.delete("/api/documents/{doc_id}/tags")
async def remove_document_tags(
    doc_id: str,
    request: Request,
    user: UserContext = Depends(get_user_from_header),
):
    """Remove tags from a document."""
    body = await request.json()
    tag_values = body.get("tags", [])
    deleted = remove_tags(user.tenant_id, "document", doc_id, tag_values)
    current = get_entity_tags(user.tenant_id, "document", doc_id)
    remaining = [tag for tag in current.get("user_tags", []) if tag not in tag_values]
    update_entity_tags(user.tenant_id, "document", doc_id, user_tags=remaining)
    return {"removed": deleted}


@router.get("/api/packages/{package_id}/tags")
async def get_package_tags(
    package_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Get all tags for a package."""
    return get_entity_tags(user.tenant_id, "package", package_id)


@router.post("/api/packages/{package_id}/tags")
async def add_package_tags(
    package_id: str,
    request: Request,
    user: UserContext = Depends(get_user_from_header),
):
    """Add user tags to a package."""
    body = await request.json()
    tags = _normalize_tag_payload(body.get("tags", []))
    written = add_tags(user.tenant_id, "package", package_id, tags)
    current = get_entity_tags(user.tenant_id, "package", package_id)
    update_entity_tags(
        user.tenant_id, "package", package_id, user_tags=_merge_user_tags(current, tags)
    )
    return {"added": written}


@router.delete("/api/packages/{package_id}/tags")
async def remove_package_tags(
    package_id: str,
    request: Request,
    user: UserContext = Depends(get_user_from_header),
):
    """Remove tags from a package."""
    body = await request.json()
    tag_values = body.get("tags", [])
    deleted = remove_tags(user.tenant_id, "package", package_id, tag_values)
    current = get_entity_tags(user.tenant_id, "package", package_id)
    remaining = [tag for tag in current.get("user_tags", []) if tag not in tag_values]
    update_entity_tags(user.tenant_id, "package", package_id, user_tags=remaining)
    return {"removed": deleted}


@router.get("/api/tags/search")
async def search_by_tag(
    q: str,
    type: Optional[str] = None,
    user: UserContext = Depends(get_user_from_header),
):
    """Find documents and packages by tag value."""
    results = find_entities_by_tag(user.tenant_id, q, entity_type=type)
    return {"tag": q, "results": results, "total": len(results)}
