"""
EAGLE Packages Router

Handles acquisition package CRUD, documents, and approval chains.
Extracted from main.py for better organization.
"""

from decimal import Decimal
import sys
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from starlette.responses import Response

from ..approval_store import create_approval_chain, get_chain_status, record_decision
from ..audit_store import write_audit
from ..changelog_store import list_changelog_entries, list_document_changelog_entries
from ..cognito_auth import UserContext
from ..document_service import (
    create_package_document_version,
    finalize_document as finalize_document_version,
    get_document_download_url,
)
from ..document_store import get_document, get_document_history, list_package_documents
from ..package_context_service import clear_active_package, detect_package_from_session, resolve_context, set_active_package
from ..package_store import (
    approve_package,
    create_package,
    get_package,
    get_package_checklist,
    list_packages,
    submit_package,
    update_package,
)

from .dependencies import get_user_from_header

router = APIRouter(prefix="/api/packages", tags=["packages"])
compat_router = APIRouter(tags=["packages"])


def _resolve_main_override(name: str, default: Any) -> Any:
    """Use app.main compatibility aliases when older tests patch them."""
    main_module = sys.modules.get("app.main")
    if main_module is None:
        try:
            from .. import main as main_module
        except Exception:
            return default
    return getattr(main_module, name, default)


class ResolvePackageContextRequest(BaseModel):
    session_id: str
    package_id: Optional[str] = None
    action: Optional[str] = None  # "set" | "clear" | None


@router.get("")
async def list_packages_endpoint(
    status: Optional[str] = None,
    user: UserContext = Depends(get_user_from_header),
):
    """List acquisition packages for the current user's tenant."""
    return list_packages(user.tenant_id, status=status, owner_user_id=user.user_id)


@router.post("")
async def create_package_endpoint(
    body: Dict[str, Any],
    user: UserContext = Depends(get_user_from_header),
):
    """Create a new acquisition package (auto-determines FAR pathway)."""
    return create_package(
        tenant_id=user.tenant_id,
        owner_user_id=user.user_id,
        title=body["title"],
        requirement_type=body.get("requirement_type", "services"),
        estimated_value=Decimal(str(body.get("estimated_value", "0"))),
        session_id=body.get("session_id"),
        notes=body.get("notes", ""),
        contract_vehicle=body.get("contract_vehicle"),
        acquisition_method=body.get("acquisition_method"),
        contract_type=body.get("contract_type"),
        flags=body.get("flags"),
    )


@router.get("/{package_id}")
async def get_package_endpoint(
    package_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Get an acquisition package by ID."""
    pkg = get_package(user.tenant_id, package_id)
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
    return pkg


@router.put("/{package_id}")
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


@router.get("/{package_id}/checklist")
async def get_package_checklist_endpoint(
    package_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Return the document checklist for a package (required, completed, missing)."""
    return get_package_checklist(user.tenant_id, package_id)


@router.post("/{package_id}/submit")
async def submit_package_endpoint(
    package_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Submit package for review (drafting -> review)."""
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


@router.post("/{package_id}/approve")
async def approve_package_endpoint(
    package_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Approve a package (review -> approved)."""
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


@router.get("/{package_id}/export/zip")
async def export_package_zip_endpoint(
    package_id: str,
    format: str = "docx",
    save_to_workspace: bool = False,
    user: UserContext = Depends(get_user_from_header),
):
    """Download all package documents as a ZIP archive."""
    import logging
    from ..db_client import get_s3
    from ..document_export import export_package_zip

    logger = logging.getLogger("eagle.packages")

    lookup_package = _resolve_main_override("get_package", get_package)
    list_docs = _resolve_main_override("list_package_documents", list_package_documents)

    pkg = lookup_package(user.tenant_id, package_id)
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")

    docs = list_docs(user.tenant_id, package_id)
    if not docs:
        raise HTTPException(status_code=404, detail="No documents found for this package")

    # Fetch content from S3 for each document (content is stored in S3, not DynamoDB)
    s3 = get_s3()
    docs_with_content = []
    for doc in docs:
        # If content already present (e.g. from test mocks), use it directly
        if doc.get("content"):
            docs_with_content.append(doc)
            continue

        s3_key = doc.get("s3_key")
        s3_bucket = doc.get("s3_bucket")
        if not s3_key or not s3_bucket:
            logger.warning("Document %s/%s missing s3_key or s3_bucket, skipping",
                           doc.get("doc_type"), doc.get("version"))
            continue

        try:
            obj = s3.get_object(Bucket=s3_bucket, Key=s3_key)
            raw_content = obj["Body"].read()
            file_type = doc.get("file_type", "md")
            if file_type in ("md", "txt", "json", "html"):
                doc["content"] = raw_content.decode("utf-8")
            else:
                doc["_binary"] = raw_content
                doc["filename"] = f"{doc.get('doc_type', 'doc')}_{doc.get('title', 'document')}.{file_type}"
            docs_with_content.append(doc)
        except Exception as e:
            logger.warning("Failed to fetch S3 content for %s: %s", s3_key, e)

    if not docs_with_content:
        raise HTTPException(status_code=404, detail="No documents with content found")

    result = export_package_zip(docs_with_content, pkg.get("title", "Package"), format)

    headers = {
        "Content-Disposition": f'attachment; filename="{result["filename"]}"',
    }
    if save_to_workspace:
        try:
            from .documents import _save_export_to_workspace
            s3_key = _save_export_to_workspace(
                user.tenant_id, user.user_id, result["filename"],
                result["data"], result["content_type"],
                pkg.get("title", "Package"), "zip",
            )
            headers["X-S3-Key"] = s3_key
        except Exception as e:
            logger.warning("Failed to save ZIP export to workspace: %s", e)
            headers["X-S3-Save-Error"] = str(e)[:200]

    return Response(
        content=result["data"],
        media_type=result["content_type"],
        headers=headers,
    )


@router.get("/{package_id}/documents")
async def list_documents_endpoint(
    package_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """List all generated documents for a package (latest version per doc type)."""
    list_docs = _resolve_main_override("list_package_documents", list_package_documents)
    return list_docs(user.tenant_id, package_id)


@router.post("/resolve-context")
async def resolve_package_context_endpoint(
    body: ResolvePackageContextRequest,
    user: UserContext = Depends(get_user_from_header),
):
    """Resolve and optionally persist active package context for a session."""
    if body.action == "clear":
        clear_active_package(user.tenant_id, user.user_id, body.session_id)
        return {"mode": "workspace", "package_id": None}

    if body.action == "detect":
        detected = detect_package_from_session(
            tenant_id=user.tenant_id,
            user_id=user.user_id,
            session_id=body.session_id,
        )
        if detected:
            return {
                "mode": detected.mode,
                "package_id": detected.package_id,
                "package_title": detected.package_title,
                "acquisition_pathway": detected.acquisition_pathway,
                "required_documents": detected.required_documents or [],
                "completed_documents": detected.completed_documents or [],
            }
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


@router.post("/{package_id}/documents")
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


@router.get("/{package_id}/documents/{doc_type}/history")
async def get_document_history_endpoint(
    package_id: str,
    doc_type: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Return version history for a package document type."""
    return get_document_history(user.tenant_id, package_id, doc_type)


@router.get("/{package_id}/documents/{doc_type}/versions/{version}/download-url")
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


@router.get("/{package_id}/documents/{doc_type}")
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


@router.post("/{package_id}/documents/{doc_type}/finalize")
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


@router.post("/{package_id}/documents/{doc_type}/versions/{version}/promote-final")
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


@router.get("/{package_id}/documents/{doc_type}/changelog")
async def get_document_changelog_endpoint(
    package_id: str,
    doc_type: str,
    limit: int = 50,
    user: UserContext = Depends(get_user_from_header),
):
    """Get changelog entries for a document."""
    entries = list_changelog_entries(user.tenant_id, package_id, doc_type, limit)
    return {"entries": entries, "count": len(entries)}


@router.get("/{package_id}/changelog")
async def get_package_changelog_endpoint(
    package_id: str,
    limit: int = 50,
    user: UserContext = Depends(get_user_from_header),
):
    """Get all changelog entries for a package (all document types)."""
    entries = list_changelog_entries(user.tenant_id, package_id, None, limit)
    return {"entries": entries, "count": len(entries)}


@router.get("/document-changelog/by-key")
async def get_document_key_changelog_endpoint(
    key: str,
    limit: int = 50,
    user: UserContext = Depends(get_user_from_header),
):
    """Get changelog entries for a document by S3 key."""
    tenant_id = user.tenant_id
    if not key.startswith(f"eagle/{tenant_id}/"):
        raise HTTPException(status_code=403, detail="Access denied")

    entries = list_document_changelog_entries(tenant_id, key, limit)
    return {"entries": entries, "count": len(entries)}


@compat_router.get("/api/document-changelog", include_in_schema=False)
async def get_document_key_changelog_compat_endpoint(
    key: str,
    limit: int = 50,
    user: UserContext = Depends(get_user_from_header),
):
    """Compatibility alias for legacy document changelog lookups."""
    return await get_document_key_changelog_endpoint(key=key, limit=limit, user=user)


# ── Approval Chains ────────────────────────────────────────────────


@router.get("/{package_id}/approvals")
async def get_approval_chain_endpoint(
    package_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Return the approval chain status for a package."""
    return get_chain_status(user.tenant_id, package_id)


@router.post("/{package_id}/approvals")
async def create_approval_chain_endpoint(
    package_id: str,
    body: Dict[str, Any],
    user: UserContext = Depends(get_user_from_header),
):
    """Create the FAR-driven approval chain for a package."""
    estimated_value = Decimal(str(body.get("estimated_value", "0")))
    return create_approval_chain(user.tenant_id, package_id, estimated_value)


@router.post("/{package_id}/approvals/{step}/decision")
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
