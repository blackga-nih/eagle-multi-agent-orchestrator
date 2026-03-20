"""
Templates API Router

Provides endpoints for document template management:
- List templates (tenant + bundled)
- S3 template library listing and copying
- Template CRUD operations
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException

from ..cognito_auth import UserContext
from ..template_store import (
    put_template, delete_template,
    list_tenant_templates, resolve_template,
)
from .dependencies import get_user_from_header

router = APIRouter(prefix="/api/templates", tags=["templates"])


@router.get("")
async def list_templates_endpoint(
    doc_type: Optional[str] = None,
    user: UserContext = Depends(get_user_from_header),
):
    """List available templates for the current tenant."""
    return list_tenant_templates(user.tenant_id, doc_type)


# ── S3 Template Library ────────────────────────────────────────────
# NOTE: These must be declared before /{doc_type} to avoid
# FastAPI matching "s3" as a doc_type path parameter.


@router.get("/s3")
async def list_s3_templates_endpoint(
    phase: Optional[str] = None,
    refresh: bool = False,
    user: UserContext = Depends(get_user_from_header),
):
    """List all templates from S3 bucket with metadata.

    Query params:
        phase: Filter by acquisition phase (intake, planning, solicitation, etc.)
        refresh: Force cache refresh (default: false)
    """
    from ..template_registry import list_s3_templates, ACQUISITION_PHASES

    templates = list_s3_templates(refresh=refresh, phase_filter=phase)

    # Build phase counts for filter UI
    phase_counts: Dict[str, int] = {p: 0 for p in ACQUISITION_PHASES}
    all_templates = list_s3_templates(refresh=False) if phase else templates
    for t in all_templates:
        cat = t.get("category")
        if cat and cat.get("phase") in phase_counts:
            phase_counts[cat["phase"]] += 1

    return {
        "templates": templates,
        "count": len(templates),
        "phase_counts": phase_counts,
    }


@router.post("/s3/copy")
async def copy_s3_template_to_package(
    body: Dict[str, Any],
    user: UserContext = Depends(get_user_from_header),
):
    """Copy an S3 template into an acquisition package.

    Body:
        s3_key: Full S3 key of the template
        package_id: Target package ID

    Returns:
        Created document entry with document_id
    """
    from ..template_registry import get_s3_template_by_key, _infer_doc_type_from_filename
    from ..document_store import create_document_from_s3

    s3_key = body.get("s3_key")
    package_id = body.get("package_id")

    if not s3_key or not package_id:
        raise HTTPException(status_code=400, detail="s3_key and package_id are required")

    # Fetch template content from S3
    content = get_s3_template_by_key(s3_key)
    if content is None:
        raise HTTPException(status_code=404, detail="Template not found in S3")

    # Extract filename and doc_type
    filename = s3_key.rsplit("/", 1)[-1] if "/" in s3_key else s3_key
    file_type = filename.rsplit(".", 1)[-1].lower() if "." in filename else "unknown"

    # Infer doc_type from filename
    doc_type = _infer_doc_type_from_filename(filename) or "custom"

    # Create document entry in package
    document = create_document_from_s3(
        tenant_id=user.tenant_id,
        package_id=package_id,
        doc_type=doc_type,
        filename=filename,
        file_type=file_type,
        content=content,
        source_s3_key=s3_key,
        created_by=user.user_id,
    )

    return {
        "document_id": document.get("document_id"),
        "doc_type": doc_type,
        "filename": filename,
        "package_id": package_id,
        "source": "s3_template",
    }


# ── Template CRUD (Dynamic Routes) ─────────────────────────────────


@router.get("/{doc_type}")
async def get_active_template(
    doc_type: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Return the resolved template for this user (4-layer fallback)."""
    body, source = resolve_template(user.tenant_id, user.user_id, doc_type)
    return {"doc_type": doc_type, "template_body": body, "source": source}


@router.post("/{doc_type}")
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


@router.delete("/{doc_type}")
async def delete_template_endpoint(
    doc_type: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Delete the current user's template override for a doc type."""
    ok = delete_template(user.tenant_id, doc_type, user.user_id)
    return {"deleted": ok}
