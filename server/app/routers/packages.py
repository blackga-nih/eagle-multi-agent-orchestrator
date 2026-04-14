"""
EAGLE Packages Router

Handles acquisition package CRUD, documents, and approval chains.
Extracted from main.py for better organization.
"""

from __future__ import annotations

from decimal import Decimal
import logging
import os
import re
import sys
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
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
from ..package_attachment_store import (
    create_attachment,
    delete_attachment,
    get_attachment,
    list_package_attachments,
    update_attachment,
)
from ..package_document_store import get_document, get_document_history, list_package_documents
from ..package_context_service import (
    clear_active_package,
    detect_package_from_session,
    resolve_context,
    set_active_package,
)
from ..package_store import (
    PatchRequiredDocsError,
    approve_package,
    clone_package,
    create_package,
    delete_package,
    doc_type_manifest,
    get_package,
    get_package_checklist,
    list_packages,
    patch_required_docs,
    submit_package,
    update_package,
)

from .dependencies import get_user_from_header

logger = logging.getLogger("eagle.packages")

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


_S3_BUCKET = os.getenv("S3_BUCKET", "eagle-documents-dev")
_MAX_UPLOAD_BYTES = 25 * 1024 * 1024
_PACKAGE_ATTACHMENT_CATEGORIES = {
    "requirements_evidence",
    "prior_artifact",
    "pricing_evidence",
    "approval_evidence",
    "technical_evidence",
    "market_research_evidence",
    "other",
}
_PACKAGE_ATTACHMENT_USAGES = {
    "reference",
    "checklist_support",
    "official_candidate",
    "official_document",
}
_PACKAGE_ATTACHMENT_MIME_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "text/plain",
    "text/markdown",
    "image/png",
    "image/jpeg",
}


def _parse_form_bool(value: Optional[str], default: bool = True) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _detect_attachment_type(filename: str, content_type: str) -> str:
    if content_type.startswith("image/"):
        lowered = filename.lower()
        if "screenshot" in lowered or "screen_shot" in lowered or "screen-shot" in lowered:
            return "screenshot"
        return "image"
    return "document"


def _suggest_attachment_category(
    doc_type: Optional[str],
    content_type: str,
    attachment_type: str,
) -> str:
    if attachment_type in {"image", "screenshot"}:
        return "technical_evidence"
    if doc_type in {"sow", "igce", "market_research", "justification", "acquisition_plan"}:
        return "prior_artifact"
    if doc_type in {"son_products", "son_services", "technical_questionnaire"}:
        return "requirements_evidence"
    if doc_type == "market_research":
        return "market_research_evidence"
    if content_type in {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
    }:
        return "pricing_evidence"
    return "other"


def _build_attachment_export_name(
    package_id: str,
    category: str,
    attachment_id: str,
    file_type: str,
) -> str:
    suffix = re.sub(r"[^\w\-]", "_", attachment_id)[-8:] or "file"
    return f"{package_id}_{category}_{suffix}.{file_type}"


class ResolvePackageContextRequest(BaseModel):
    session_id: str
    package_id: Optional[str] = None
    action: Optional[str] = None  # "set" | "clear" | None


class PackageAttachmentUpdateRequest(BaseModel):
    title: Optional[str] = None
    doc_type: Optional[str] = None
    linked_doc_type: Optional[str] = None
    category: Optional[str] = None
    usage: Optional[str] = None
    include_in_zip: Optional[bool] = None


class PromotePackageAttachmentRequest(BaseModel):
    doc_type: str
    title: Optional[str] = None
    set_as_official: bool = True


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


@router.get("/doc-types")
async def get_doc_types_manifest_endpoint(
    user: UserContext = Depends(get_user_from_header),  # noqa: ARG001
):
    """Return [{slug, label}] for every recognised package doc-type.

    Frontend uses this to populate the "+ Add Required" picker in the
    checklist customization UI (Phase C'). The manifest is the union of
    pathway baselines + compliance matrix slugs — anything that
    create_package_document_version will accept.
    """
    return {"doc_types": doc_type_manifest()}


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


@router.patch("/{package_id}/required-docs")
async def patch_required_docs_endpoint(
    package_id: str,
    body: Dict[str, Any],
    user: UserContext = Depends(get_user_from_header),
):
    """Mutate a package's required_documents list (Option D, Phase B').

    Body shape:
        {"add": ["qasp"], "remove": ["sb_review"], "reset": false}

    On success returns the updated rich checklist (items[], extra[],
    custom flag, warnings[]). The frontend hook should call mutate() on
    this response to apply the change without a refetch.
    """
    add = body.get("add") or []
    remove = body.get("remove") or []
    reset = bool(body.get("reset", False))

    if not isinstance(add, list) or not isinstance(remove, list):
        raise HTTPException(
            status_code=400, detail="'add' and 'remove' must be lists of slugs"
        )

    try:
        result = patch_required_docs(
            tenant_id=user.tenant_id,
            package_id=package_id,
            add=add,
            remove=remove,
            reset=reset,
        )
    except PatchRequiredDocsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if result is None:
        raise HTTPException(status_code=404, detail="Package not found")

    write_audit(
        tenant_id=user.tenant_id,
        entity_type="package",
        entity_name=package_id,
        event_type="required_docs.patched",
        actor_user_id=user.user_id,
        metadata={"add": add, "remove": remove, "reset": reset},
    )
    return result


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


@router.delete("/{package_id}")
async def delete_package_endpoint(
    package_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Delete a package (only intake/drafting status)."""
    pkg = delete_package(user.tenant_id, package_id)
    if not pkg:
        raise HTTPException(
            status_code=404,
            detail="Package not found or cannot be deleted",
        )
    write_audit(
        tenant_id=user.tenant_id,
        entity_type="package",
        entity_name=package_id,
        event_type="delete",
        actor_user_id=user.user_id,
    )
    return {"deleted": True, "package_id": package_id}


@router.post("/{package_id}/clone")
async def clone_package_endpoint(
    package_id: str,
    body: dict = {},
    user: UserContext = Depends(get_user_from_header),
):
    """Clone a package with new ID, copying metadata but not documents."""
    new_title = body.get("title")
    pkg = clone_package(
        user.tenant_id, package_id, new_title,
        owner_user_id=user.user_id,
    )
    if not pkg:
        raise HTTPException(status_code=404, detail="Source package not found")
    write_audit(
        tenant_id=user.tenant_id,
        entity_type="package",
        entity_name=pkg["package_id"],
        event_type="clone",
        actor_user_id=user.user_id,
    )
    return pkg


@router.post("/{package_id}/attachments")
async def upload_package_attachment_endpoint(
    package_id: str,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    doc_type: Optional[str] = Form(None),
    linked_doc_type: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    usage: Optional[str] = Form(None),
    include_in_zip: Optional[str] = Form(None),
    session_id: Optional[str] = Form(None),
    user: UserContext = Depends(get_user_from_header),
):
    """Upload a source attachment directly into a package."""
    import hashlib
    import uuid

    from botocore.exceptions import ClientError

    from ..db_client import get_s3
    from ..document_classification_service import (
        ClassificationResult,
        classify_document,
        extract_text_preview,
    )
    from ..document_markdown_service import convert_to_markdown
    from ..doc_type_registry import normalize_doc_type

    pkg = get_package(user.tenant_id, package_id)
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")

    content_type = file.content_type or "application/octet-stream"
    if content_type not in _PACKAGE_ATTACHMENT_MIME_TYPES:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Unsupported file type: {content_type}. Accepted: PDF, Word, Excel, "
                "plain text, Markdown, PNG, JPEG."
            ),
        )

    body = await file.read()
    if len(body) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 25 MB limit.")

    attachment_id = str(uuid.uuid4())
    safe_name = re.sub(r"[^A-Za-z0-9._\\-]", "_", file.filename or "attachment")
    s3_key = (
        f"eagle/{user.tenant_id}/packages/{package_id}/attachments/"
        f"{attachment_id}/v1/{safe_name}"
    )

    try:
        get_s3().put_object(
            Bucket=_S3_BUCKET,
            Key=s3_key,
            Body=body,
            ContentType=content_type,
        )
    except ClientError as exc:
        logger.error("Failed to upload package attachment: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to upload attachment")

    normalized_doc_type = normalize_doc_type(doc_type) if doc_type else None
    normalized_linked_doc_type = normalize_doc_type(linked_doc_type) if linked_doc_type else None
    preview = extract_text_preview(body, content_type)
    if normalized_doc_type:
        classification = ClassificationResult(
            doc_type=normalized_doc_type,
            confidence=1.0,
            method="filename",
            suggested_title=title or safe_name,
        )
        classification_source = "user"
    elif content_type.startswith("image/"):
        classification = ClassificationResult(
            doc_type="unknown",
            confidence=0.2,
            method="unknown",
            suggested_title=title or safe_name,
        )
        classification_source = "unknown"
    else:
        classification = classify_document(file.filename or safe_name, preview)
        classification_source = classification.method

    attachment_type = _detect_attachment_type(file.filename or safe_name, content_type)
    normalized_category = category or _suggest_attachment_category(
        classification.doc_type,
        content_type,
        attachment_type,
    )
    if normalized_category not in _PACKAGE_ATTACHMENT_CATEGORIES:
        raise HTTPException(status_code=400, detail="Invalid attachment category")

    normalized_usage = usage or ("checklist_support" if normalized_linked_doc_type else "reference")
    if normalized_usage not in _PACKAGE_ATTACHMENT_USAGES:
        raise HTTPException(status_code=400, detail="Invalid attachment usage")
    if normalized_usage == "checklist_support" and not normalized_linked_doc_type:
        raise HTTPException(status_code=400, detail="linked_doc_type is required for checklist support")

    include_in_zip_bool = _parse_form_bool(include_in_zip, default=True)

    markdown_content = None
    if not content_type.startswith("image/"):
        markdown_content = convert_to_markdown(body, content_type, file.filename or safe_name)

    markdown_s3_key = None
    if markdown_content:
        markdown_s3_key = f"{s3_key}.content.md"
        try:
            get_s3().put_object(
                Bucket=_S3_BUCKET,
                Key=markdown_s3_key,
                Body=markdown_content.encode("utf-8"),
                ContentType="text/markdown",
            )
        except ClientError as exc:
            logger.warning("Failed to upload attachment markdown sibling: %s", exc)
            markdown_s3_key = None

    attachment = create_attachment(
        tenant_id=user.tenant_id,
        package_id=package_id,
        user_id=user.user_id,
        s3_bucket=_S3_BUCKET,
        s3_key=s3_key,
        filename=safe_name,
        original_filename=file.filename or safe_name,
        content_type=content_type,
        size_bytes=len(body),
        title=title or classification.suggested_title or safe_name,
        attachment_type=attachment_type,
        doc_type=classification.doc_type if classification.doc_type != "unknown" else None,
        linked_doc_type=normalized_linked_doc_type,
        category=normalized_category,
        usage=normalized_usage,
        include_in_zip=include_in_zip_bool,
        classification=classification.to_dict(),
        classification_source=classification_source,
        markdown_s3_key=markdown_s3_key,
        extracted_text=markdown_content or preview,
        session_id=session_id,
        attachment_id=attachment_id,
    )
    attachment["content_hash"] = hashlib.sha256(body).hexdigest()
    attachment["extracted_text_available"] = bool(markdown_content or preview)
    return attachment


@router.get("/{package_id}/attachments")
async def list_package_attachments_endpoint(
    package_id: str,
    include_zip_only: Optional[bool] = None,
    limit: int = 100,
    user: UserContext = Depends(get_user_from_header),
):
    pkg = get_package(user.tenant_id, package_id)
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
    attachments = list_package_attachments(
        user.tenant_id,
        package_id,
        include_zip_only=include_zip_only,
        limit=limit,
    )
    return {"attachments": attachments, "count": len(attachments)}


@router.patch("/{package_id}/attachments/{attachment_id}")
async def update_package_attachment_endpoint(
    package_id: str,
    attachment_id: str,
    body: PackageAttachmentUpdateRequest,
    user: UserContext = Depends(get_user_from_header),
):
    attachment = get_attachment(user.tenant_id, package_id, attachment_id)
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")
    if attachment.get("owner_user_id") != user.user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    updates = body.model_dump(exclude_unset=True)
    if "doc_type" in updates and updates["doc_type"]:
        from ..doc_type_registry import normalize_doc_type

        updates["doc_type"] = normalize_doc_type(updates["doc_type"])
    if "linked_doc_type" in updates:
        from ..doc_type_registry import normalize_doc_type

        updates["linked_doc_type"] = (
            normalize_doc_type(updates["linked_doc_type"])
            if updates["linked_doc_type"]
            else None
        )
    if "category" in updates and updates["category"] not in _PACKAGE_ATTACHMENT_CATEGORIES:
        raise HTTPException(status_code=400, detail="Invalid attachment category")
    if "usage" in updates and updates["usage"] not in _PACKAGE_ATTACHMENT_USAGES:
        raise HTTPException(status_code=400, detail="Invalid attachment usage")
    if (
        updates.get("usage") == "checklist_support"
        and not updates.get("linked_doc_type")
        and not attachment.get("linked_doc_type")
    ):
        raise HTTPException(status_code=400, detail="linked_doc_type is required for checklist support")
    if updates.get("usage") == "reference" and "linked_doc_type" not in updates:
        updates["linked_doc_type"] = None
    if "title" in updates:
        updates["display_name"] = updates["title"]

    updated = update_attachment(user.tenant_id, package_id, attachment_id, updates)
    if not updated:
        raise HTTPException(status_code=404, detail="Attachment not found")
    return updated


@router.delete("/{package_id}/attachments/{attachment_id}")
async def delete_package_attachment_endpoint(
    package_id: str,
    attachment_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    attachment = get_attachment(user.tenant_id, package_id, attachment_id)
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")
    if attachment.get("owner_user_id") != user.user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    deleted = delete_attachment(user.tenant_id, package_id, attachment_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Attachment not found")
    return {"deleted": True, "attachment_id": attachment_id}


@router.get("/{package_id}/attachments/{attachment_id}/download-url")
async def get_package_attachment_download_url_endpoint(
    package_id: str,
    attachment_id: str,
    expires_in: int = 3600,
    user: UserContext = Depends(get_user_from_header),
):
    from ..db_client import get_s3

    attachment = get_attachment(user.tenant_id, package_id, attachment_id)
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")
    if attachment.get("owner_user_id") != user.user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    try:
        url = get_s3().generate_presigned_url(
            "get_object",
            Params={"Bucket": attachment["s3_bucket"], "Key": attachment["s3_key"]},
            ExpiresIn=expires_in,
        )
    except Exception as exc:
        logger.error("Failed to generate attachment download URL: %s", exc)
        raise HTTPException(status_code=500, detail="Attachment download URL unavailable")
    return {"download_url": url, "expires_in": expires_in}


@router.post("/{package_id}/attachments/{attachment_id}/promote")
async def promote_package_attachment_endpoint(
    package_id: str,
    attachment_id: str,
    body: PromotePackageAttachmentRequest,
    user: UserContext = Depends(get_user_from_header),
):
    from ..db_client import get_s3
    from ..doc_type_registry import normalize_doc_type

    attachment = get_attachment(user.tenant_id, package_id, attachment_id)
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")
    if attachment.get("owner_user_id") != user.user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    normalized_doc_type = normalize_doc_type(body.doc_type)
    if not normalized_doc_type or normalized_doc_type == "unknown":
        raise HTTPException(status_code=400, detail="Valid doc_type is required")

    try:
        s3 = get_s3()
        source_obj = s3.get_object(
            Bucket=attachment["s3_bucket"],
            Key=attachment["s3_key"],
        )
        content = source_obj["Body"].read()
    except Exception as exc:
        logger.error("Failed to load attachment %s for promotion: %s", attachment_id, exc)
        raise HTTPException(status_code=500, detail="Failed to load attachment content")

    markdown_content = attachment.get("extracted_text")
    markdown_s3_key = attachment.get("markdown_s3_key")
    if markdown_s3_key:
        try:
            md_obj = s3.get_object(Bucket=attachment["s3_bucket"], Key=markdown_s3_key)
            markdown_content = md_obj["Body"].read().decode("utf-8", errors="replace")
        except Exception:
            logger.debug("Promotion could not fetch markdown sidecar for %s", attachment_id)

    promoted_title = (body.title or attachment.get("title") or attachment.get("filename") or normalized_doc_type).strip()
    result = create_package_document_version(
        tenant_id=user.tenant_id,
        package_id=package_id,
        doc_type=normalized_doc_type,
        content=content,
        title=promoted_title,
        file_type=attachment.get("file_type", "md"),
        created_by_user_id=user.user_id,
        session_id=attachment.get("session_id"),
        change_source="attachment_promotion",
        markdown_content=markdown_content,
        original_filename=attachment.get("original_filename") or attachment.get("filename"),
        source_context_type="package_attachment_promotion",
        source_data_summary=(
            f"Promoted attachment {attachment.get('attachment_id')} "
            f"({attachment.get('title') or attachment.get('filename')}) "
            f"to canonical {normalized_doc_type}"
        ),
        source_data={
            "attachment_id": attachment.get("attachment_id"),
            "attachment_category": attachment.get("category"),
            "attachment_usage": attachment.get("usage"),
            "attachment_s3_key": attachment.get("s3_key"),
        },
    )
    if not result.success:
        status = 404 if result.error and "not found" in result.error.lower() else 500
        raise HTTPException(status_code=status, detail=result.error or "Promotion failed")

    if body.set_as_official:
        update_attachment(
            user.tenant_id,
            package_id,
            attachment_id,
            {
                "doc_type": normalized_doc_type,
                "linked_doc_type": normalized_doc_type,
                "usage": "official_document",
                "title": promoted_title,
                "display_name": promoted_title,
            },
        )

    promoted = get_document(user.tenant_id, package_id, normalized_doc_type, result.version)
    if promoted:
        promoted["promoted_from_attachment_id"] = attachment_id
        return promoted

    response = result.to_dict()
    response["promoted_from_attachment_id"] = attachment_id
    return response


@router.get("/{package_id}/exports")
async def list_package_exports_endpoint(
    package_id: str,
    limit: int = 50,
    user: UserContext = Depends(get_user_from_header),
):
    """List export history for a package."""
    from ..export_store import list_exports

    exports = list_exports(user.tenant_id, package_id=package_id, limit=limit)
    return {"exports": exports, "count": len(exports)}


@router.get("/{package_id}/export/zip")
async def export_package_zip_endpoint(
    package_id: str,
    format: str = "docx",
    save_to_workspace: bool = False,
    doc_types: Optional[str] = None,
    format_map: Optional[str] = None,
    user: UserContext = Depends(get_user_from_header),
):
    """Download package documents as a ZIP archive.

    Query params:
        format: Default export format (docx, pdf, md). Default: docx
        doc_types: Comma-separated doc types to include (e.g. sow,igce). Default: all
        format_map: JSON per-doc format overrides (e.g. {"sow":"pdf","igce":"md"})
        save_to_workspace: Save ZIP to user workspace in S3
    """
    import json as _json

    from ..db_client import get_s3
    from ..document_export import export_package_zip as _export_zip

    parsed_format_map = None
    if format_map:
        try:
            parsed_format_map = _json.loads(format_map)
        except _json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="format_map must be valid JSON")

    lookup_package = _resolve_main_override("get_package", get_package)
    list_docs = _resolve_main_override("list_package_documents", list_package_documents)

    pkg = lookup_package(user.tenant_id, package_id)
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")

    docs = list_docs(user.tenant_id, package_id)
    attachments = list_package_attachments(user.tenant_id, package_id, include_zip_only=True)
    if not docs and not attachments:
        raise HTTPException(
            status_code=404, detail="No documents or attachments found for this package"
        )

    s3 = get_s3()
    docs_with_content = []
    for doc in docs:
        if doc.get("content"):
            docs_with_content.append(doc)
            continue

        s3_key = doc.get("s3_key")
        s3_bucket = doc.get("s3_bucket")
        if not s3_key or not s3_bucket:
            logger.warning(
                "Document %s/%s missing s3_key or s3_bucket, skipping",
                doc.get("doc_type"),
                doc.get("version"),
            )
            continue

        try:
            obj = s3.get_object(Bucket=s3_bucket, Key=s3_key)
            raw_content = obj["Body"].read()
            file_type = doc.get("file_type", "md")
            if file_type in ("md", "txt", "json", "html"):
                doc["content"] = raw_content.decode("utf-8")
            elif file_type in ("docx", "xlsx"):
                # For DOCX/XLSX, check if a markdown sibling exists (the
                # markdown source is more useful for format conversion and
                # avoids exporting unfilled templates).
                # Sidecar convention: {s3_key}.content.md  (stored by document_service)
                # Also check DynamoDB record for explicit markdown_s3_key.
                md_key = doc.get("markdown_s3_key") or f"{s3_key}.content.md"
                try:
                    md_obj = s3.get_object(Bucket=s3_bucket, Key=md_key)
                    doc["content"] = md_obj["Body"].read().decode("utf-8")
                    logger.debug("ZIP export: using markdown sibling for %s", s3_key)
                except Exception:
                    # No markdown sibling — include the binary DOCX directly
                    doc["_binary"] = raw_content
                    doc["filename"] = (
                        f"{doc.get('doc_type', 'doc')}"
                        f"_{doc.get('title', 'document')}.{file_type}"
                    )
            else:
                doc["_binary"] = raw_content
                doc["filename"] = (
                    f"{doc.get('doc_type', 'doc')}"
                    f"_{doc.get('title', 'document')}.{file_type}"
                )
            docs_with_content.append(doc)
        except Exception as e:
            logger.warning("Failed to fetch S3 content for %s: %s", s3_key, e)

    attachment_exports = []
    for attachment in attachments:
        s3_key = attachment.get("s3_key")
        s3_bucket = attachment.get("s3_bucket")
        if not s3_key or not s3_bucket:
            continue
        try:
            obj = s3.get_object(Bucket=s3_bucket, Key=s3_key)
            raw_content = obj["Body"].read()
            file_type = attachment.get("file_type", "bin")
            category = attachment.get("category", "other")
            attachment_exports.append(
                {
                    "doc_type": attachment.get("doc_type") or "attachment",
                    "title": attachment.get("title") or attachment.get("filename") or "attachment",
                    "_binary": raw_content,
                    "file_type": file_type,
                    "filename": _build_attachment_export_name(
                        package_id,
                        category,
                        attachment.get("attachment_id", "attachment"),
                        file_type,
                    ),
                    "zip_folder": f"09_Attachments/{category}/",
                }
            )
        except Exception as e:
            logger.warning("Failed to fetch attachment content for %s: %s", s3_key, e)

    if not docs_with_content and not attachment_exports:
        raise HTTPException(status_code=404, detail="No documents or attachments with content found")

    # Selective export filter
    if doc_types:
        requested = {dt.strip() for dt in doc_types.split(",")}
        docs_with_content = [
            d for d in docs_with_content
            if d.get("doc_type") in requested
        ]
        if not docs_with_content:
            raise HTTPException(
                status_code=404,
                detail="No documents matching requested doc_types",
            )

    result = _export_zip(
        docs_with_content, pkg.get("title", "Package"), format,
        package_metadata=pkg, format_map=parsed_format_map, attachments=attachment_exports,
    )

    # Record export (non-fatal)
    try:
        from ..export_store import record_export

        record_export(
            tenant_id=user.tenant_id,
            package_id=package_id,
            user_id=user.user_id,
            export_format=format,
            doc_types_included=[
                d.get("doc_type", "unknown")
                for d in docs_with_content
            ] + [a.get("doc_type", "attachment") for a in attachment_exports],
            file_size=result["size_bytes"],
        )
    except Exception as e:
        logger.warning("Failed to record export: %s", e)

    headers = {
        "Content-Disposition": f'attachment; filename="{result["filename"]}"',
    }
    if save_to_workspace:
        try:
            from .documents import _save_export_to_workspace

            s3_key = _save_export_to_workspace(
                user.tenant_id,
                user.user_id,
                result["filename"],
                result["data"],
                result["content_type"],
                pkg.get("title", "Package"),
                "zip",
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
    """Save a generated document for a package using canonical document service.

    Provenance footer injection happens inside ``create_package_document_version``
    so the bypass that used to skip the agent path is now closed — every write
    to DOCUMENT# carries the markdown footer regardless of caller.

    The response includes the fresh ``checklist`` so the calling client can
    call ``usePackageChecklist().mutate(checklist)`` and avoid a refetch round
    trip. Other tabs/sessions pick up the change on next cold load via
    ``GET /api/packages/{id}/checklist``.
    """
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
        raise HTTPException(
            status_code=status, detail=result.error or "Document creation failed"
        )

    checklist = None
    try:
        checklist = get_package_checklist(user.tenant_id, package_id)
    except Exception:
        logger.debug("checklist fetch failed after document create", exc_info=True)

    doc = get_document(user.tenant_id, package_id, body["doc_type"], result.version)
    payload: Dict[str, Any] = doc if doc else result.to_dict()
    if checklist is not None:
        payload = {**payload, "checklist": checklist}
    return payload


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
    """Get a specific document (latest version by default).

    Includes a presigned download_url and content for the document viewer.
    """
    doc = get_document(user.tenant_id, package_id, doc_type, version)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    # Always include a download URL so the frontend doesn't need a separate call
    if doc.get("s3_key") and not doc.get("download_url"):
        url = get_document_download_url(
            tenant_id=user.tenant_id,
            package_id=package_id,
            doc_type=doc_type,
            version=doc.get("version"),
        )
        if url:
            doc["download_url"] = url

    # Fetch content from S3 so the viewer modal can render a preview
    if not doc.get("content"):
        s3_key = doc.get("s3_key")
        s3_bucket = doc.get("s3_bucket")
        if s3_key and s3_bucket:
            try:
                from ..db_client import get_s3

                s3 = get_s3()
                file_type = doc.get("file_type", "md")
                if file_type in ("md", "txt", "json", "html"):
                    obj = s3.get_object(Bucket=s3_bucket, Key=s3_key)
                    doc["content"] = obj["Body"].read().decode("utf-8")
                elif file_type in ("docx", "xlsx"):
                    obj = s3.get_object(Bucket=s3_bucket, Key=s3_key)
                    raw_bytes = obj["Body"].read()

                    if file_type == "docx":
                        from ..document_ai_edit_service import (
                            extract_docx_preview_payload,
                        )

                        preview_payload = extract_docx_preview_payload(raw_bytes)
                    else:
                        from ..spreadsheet_edit_service import (
                            extract_xlsx_preview_payload,
                        )

                        preview_payload = extract_xlsx_preview_payload(raw_bytes)

                    doc["preview_blocks"] = preview_payload.get("preview_blocks", [])
                    doc["preview_sheets"] = preview_payload.get("preview_sheets", [])
                    doc["preview_mode"] = preview_payload.get("preview_mode")

                    # Prefer markdown sidecar for human-readable text content,
                    # but still return structured preview data for the viewer.
                    md_key = doc.get("markdown_s3_key") or f"{s3_key}.content.md"
                    try:
                        md_obj = s3.get_object(Bucket=s3_bucket, Key=md_key)
                        doc["content"] = md_obj["Body"].read().decode("utf-8")
                    except Exception:
                        doc["content"] = preview_payload.get("content")
            except Exception as e:
                logger.warning("Failed to fetch content for %s: %s", s3_key, e)

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
