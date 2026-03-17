"""Acquisition packages, package documents, and approval chain endpoints."""

import logging
from typing import Optional, Dict, Any

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from ..cognito_auth import UserContext
from ..stores.package_store import (
    create_package, get_package, update_package, list_packages,
    get_package_checklist, submit_package, approve_package,
)
from ..stores.document_store import (
    get_document,
    list_package_documents,
    get_document_history,
)
from ..document_service import (
    create_package_document_version,
    get_document_download_url,
    finalize_document as finalize_document_version,
)
from ..package_context_service import (
    clear_active_package,
    resolve_context,
    set_active_package,
)
from ..stores.approval_store import (
    create_approval_chain, record_decision, get_chain_status,
)
from ..stores.audit_store import write_audit
from ._deps import get_user_from_header

logger = logging.getLogger("eagle")
router = APIRouter(tags=["packages"])


# ── Models ────────────────────────────────────────────────────────────

class ResolvePackageContextRequest(BaseModel):
    session_id: str
    package_id: Optional[str] = None
    action: Optional[str] = None  # "set" | "clear" | None


# ── Package CRUD ──────────────────────────────────────────────────────

@router.get("/api/packages")
async def list_packages_endpoint(
    status: Optional[str] = None,
    user: UserContext = Depends(get_user_from_header),
):
    """List acquisition packages for the current user's tenant."""
    return list_packages(user.tenant_id, status=status, owner_user_id=user.user_id)


@router.post("/api/packages")
async def create_package_endpoint(
    body: Dict[str, Any],
    user: UserContext = Depends(get_user_from_header),
):
    """Create a new acquisition package (auto-determines FAR pathway)."""
    from decimal import Decimal as _Decimal
    return create_package(
        tenant_id=user.tenant_id,
        owner_user_id=user.user_id,
        title=body["title"],
        requirement_type=body.get("requirement_type", "services"),
        estimated_value=_Decimal(str(body.get("estimated_value", "0"))),
        session_id=body.get("session_id"),
        notes=body.get("notes", ""),
        contract_vehicle=body.get("contract_vehicle"),
    )


@router.get("/api/packages/{package_id}")
async def get_package_endpoint(
    package_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Get an acquisition package by ID."""
    pkg = get_package(user.tenant_id, package_id)
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
    return pkg


@router.put("/api/packages/{package_id}")
async def update_package_endpoint(
    package_id: str,
    body: Dict[str, Any],
    user: UserContext = Depends(get_user_from_header),
):
    """Update an acquisition package."""
    updated = update_package(user.tenant_id, package_id, body)
    if not updated:
        raise HTTPException(status_code=404, detail="Package not found")
    return updated


@router.get("/api/packages/{package_id}/checklist")
async def get_package_checklist_endpoint(
    package_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Return the document checklist for a package (required, completed, missing)."""
    return get_package_checklist(user.tenant_id, package_id)


@router.post("/api/packages/{package_id}/submit")
async def submit_package_endpoint(
    package_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Submit package for review (drafting → review)."""
    pkg = submit_package(user.tenant_id, package_id)
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
    write_audit(
        tenant_id=user.tenant_id,
        entity_type="package",
        entity_name=package_id,
        event_type="submit",
        actor_user_id=user.user_id,
    )
    return pkg


@router.post("/api/packages/{package_id}/approve")
async def approve_package_endpoint(
    package_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Approve a package (review → approved)."""
    pkg = approve_package(user.tenant_id, package_id)
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
    write_audit(
        tenant_id=user.tenant_id,
        entity_type="package",
        entity_name=package_id,
        event_type="approve",
        actor_user_id=user.user_id,
    )
    return pkg


# ── Package Documents ─────────────────────────────────────────────────

@router.get("/api/packages/{package_id}/documents")
async def list_documents_endpoint(
    package_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """List all generated documents for a package (latest version per doc type)."""
    return list_package_documents(user.tenant_id, package_id)


@router.post("/api/packages/resolve-context")
async def resolve_package_context_endpoint(
    body: ResolvePackageContextRequest,
    user: UserContext = Depends(get_user_from_header),
):
    """Resolve and optionally persist active package context for a session."""
    if body.action == "clear":
        clear_active_package(user.tenant_id, user.user_id, body.session_id)
        return {"mode": "workspace", "package_id": None}

    if body.package_id and body.action in (None, "set"):
        set_active_package(
            tenant_id=user.tenant_id,
            user_id=user.user_id,
            session_id=body.session_id,
            package_id=body.package_id,
        )

    ctx = resolve_context(
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        session_id=body.session_id,
        explicit_package_id=body.package_id,
    )
    return {
        "mode": ctx.mode,
        "package_id": ctx.package_id,
        "package_title": ctx.package_title,
        "acquisition_pathway": ctx.acquisition_pathway,
        "required_documents": ctx.required_documents or [],
        "completed_documents": ctx.completed_documents or [],
    }


@router.post("/api/packages/{package_id}/documents")
async def create_document_endpoint(
    package_id: str,
    body: Dict[str, Any],
    user: UserContext = Depends(get_user_from_header),
):
    """Save a generated document for a package using canonical document service."""
    result = create_package_document_version(
        tenant_id=user.tenant_id,
        package_id=package_id,
        doc_type=body["doc_type"],
        content=body["content"],
        title=body.get("title") or body["doc_type"].replace("_", " ").title(),
        file_type=body.get("file_type", "md"),
        created_by_user_id=user.user_id,
        session_id=body.get("session_id"),
        change_source=body.get("change_source", "user_edit"),
        template_id=body.get("template_id"),
    )
    if not result.success:
        status = 404 if result.error and "not found" in result.error.lower() else 500
        raise HTTPException(status_code=status, detail=result.error or "Document creation failed")

    doc = get_document(user.tenant_id, package_id, body["doc_type"], result.version)
    if doc:
        return doc
    return result.to_dict()


@router.get("/api/packages/{package_id}/documents/{doc_type}/history")
async def get_document_history_endpoint(
    package_id: str,
    doc_type: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Return version history for a package document type."""
    return get_document_history(user.tenant_id, package_id, doc_type)


@router.get("/api/packages/{package_id}/documents/{doc_type}/versions/{version}/download-url")
async def get_document_download_url_endpoint(
    package_id: str,
    doc_type: str,
    version: int,
    expires_in: int = 3600,
    user: UserContext = Depends(get_user_from_header),
):
    """Return a presigned download URL for a specific document version."""
    url = get_document_download_url(
        tenant_id=user.tenant_id,
        package_id=package_id,
        doc_type=doc_type,
        version=version,
        expires_in=expires_in,
    )
    if not url:
        raise HTTPException(status_code=404, detail="Document download URL unavailable")
    return {"download_url": url, "expires_in": expires_in}


@router.get("/api/packages/{package_id}/documents/{doc_type}")
async def get_document_endpoint(
    package_id: str,
    doc_type: str,
    version: Optional[int] = None,
    user: UserContext = Depends(get_user_from_header),
):
    """Get a specific document (latest version by default)."""
    doc = get_document(user.tenant_id, package_id, doc_type, version)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.post("/api/packages/{package_id}/documents/{doc_type}/finalize")
async def finalize_document_endpoint(
    package_id: str,
    doc_type: str,
    body: Dict[str, Any],
    user: UserContext = Depends(get_user_from_header),
):
    """Mark a document version as final."""
    doc = finalize_document_version(
        user.tenant_id,
        package_id,
        doc_type,
        body.get("version", 1),
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.post("/api/packages/{package_id}/documents/{doc_type}/versions/{version}/promote-final")
async def promote_document_final_endpoint(
    package_id: str,
    doc_type: str,
    version: int,
    user: UserContext = Depends(get_user_from_header),
):
    """Promote a specific document version to final status."""
    doc = finalize_document_version(user.tenant_id, package_id, doc_type, version)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


# ── Document Download (DOCX / PDF) ───────────────────────────────────

@router.get("/api/packages/{package_id}/documents/{doc_type}/download")
async def download_package_document(
    package_id: str,
    doc_type: str,
    format: str = "docx",
    version: Optional[int] = None,
    user: UserContext = Depends(get_user_from_header),
):
    """Download a package document as DOCX or PDF (rendered from stored markdown)."""
    from ..document_export import export_document, ExportDependencyError

    doc = get_document(user.tenant_id, package_id, doc_type, version)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    content = doc.get("content") or doc.get("s3_content") or ""
    if not content:
        raise HTTPException(status_code=422, detail="Document has no content to export")

    title = doc.get("title") or doc_type.replace("_", " ").title()

    try:
        result = export_document(content, format, title)
    except ExportDependencyError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return Response(
        content=result["data"],
        media_type=result["content_type"],
        headers={"Content-Disposition": f'attachment; filename="{result["filename"]}"'},
    )


# ── Workspace Document Export (no package required) ──────────────────

@router.post("/api/documents/export")
async def export_document_content(
    format: str = "docx",
    body: Dict[str, Any] = Body(...),
    user: UserContext = Depends(get_user_from_header),
):
    """Export arbitrary markdown content as DOCX or PDF — no package_id required.

    Accepts: { content: str, title: str, doc_type: str }
    Returns: binary DOCX or PDF with Content-Disposition: attachment.
    """
    from ..document_export import export_document, ExportDependencyError

    content = body.get("content", "")
    title = body.get("title", "Document")
    doc_type = body.get("doc_type", "document")

    if not content:
        raise HTTPException(status_code=422, detail="content is required")

    try:
        result = export_document(content, format, title)
    except ExportDependencyError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return Response(
        content=result["data"],
        media_type=result["content_type"],
        headers={"Content-Disposition": f'attachment; filename="{result["filename"]}"'},
    )


# ── Approval Chains ──────────────────────────────────────────────────

@router.get("/api/packages/{package_id}/approvals")
async def get_approval_chain_endpoint(
    package_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Return the approval chain status for a package."""
    return get_chain_status(user.tenant_id, package_id)


@router.post("/api/packages/{package_id}/approvals")
async def create_approval_chain_endpoint(
    package_id: str,
    body: Dict[str, Any],
    user: UserContext = Depends(get_user_from_header),
):
    """Create the FAR-driven approval chain for a package."""
    from decimal import Decimal as _Decimal
    estimated_value = _Decimal(str(body.get("estimated_value", "0")))
    return create_approval_chain(user.tenant_id, package_id, estimated_value)


@router.post("/api/packages/{package_id}/approvals/{step}/decision")
async def record_approval_decision(
    package_id: str,
    step: int,
    body: Dict[str, Any],
    user: UserContext = Depends(get_user_from_header),
):
    """Record an approval decision (approved/rejected/returned) for a step."""
    result = record_decision(
        tenant_id=user.tenant_id,
        package_id=package_id,
        step=step,
        status=body["status"],
        comments=body.get("comments", ""),
        decided_by=user.user_id,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Approval step not found")
    write_audit(
        tenant_id=user.tenant_id,
        entity_type="approval",
        entity_name=f"{package_id}#{step}",
        event_type=body["status"],
        actor_user_id=user.user_id,
        after=body.get("comments"),
    )
    return result


# ── Document Changelog ───────────────────────────────────────────────

@router.get("/api/packages/{package_id}/documents/{doc_type}/changelog")
async def get_document_changelog_endpoint(
    package_id: str,
    doc_type: str,
    limit: int = 50,
    user: UserContext = Depends(get_user_from_header),
):
    """Get changelog entries for a document."""
    from ..changelog_store import list_changelog_entries
    entries = list_changelog_entries(user.tenant_id, package_id, doc_type, limit)
    return {"entries": entries, "count": len(entries)}


@router.get("/api/packages/{package_id}/changelog")
async def get_package_changelog_endpoint(
    package_id: str,
    limit: int = 50,
    user: UserContext = Depends(get_user_from_header),
):
    """Get all changelog entries for a package (all document types)."""
    from ..changelog_store import list_changelog_entries
    entries = list_changelog_entries(user.tenant_id, package_id, None, limit)
    return {"entries": entries, "count": len(entries)}


@router.get("/api/document-changelog")
async def get_document_key_changelog_endpoint(
    key: str,
    limit: int = 50,
    user: UserContext = Depends(get_user_from_header),
):
    """Get changelog entries for a document by S3 key."""
    from ..changelog_store import list_document_changelog_entries

    tenant_id = user.tenant_id

    # Security: ensure key is within user's tenant prefix
    if not key.startswith(f"eagle/{tenant_id}/"):
        raise HTTPException(status_code=403, detail="Access denied")

    entries = list_document_changelog_entries(tenant_id, key, limit)
    return {"entries": entries, "count": len(entries)}
