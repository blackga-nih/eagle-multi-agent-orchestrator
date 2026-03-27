"""
Documents API Router

Provides endpoints for document management:
- Export (content to DOCX/PDF/MD)
- S3 document browser (list, get, update)
- Document upload and classification
- DOCX/XLSX preview editing
- Presigned URL generation
"""

import io
import base64
import json
import logging
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..cognito_auth import UserContext
from ..db_client import get_s3, get_table
from ..document_export import export_document, ExportDependencyError
from ..document_store import get_document
from ..document_service import create_package_document_version, get_document_markdown_s3_key
from ..doc_type_registry import normalize_doc_type
from ..document_classification_service import classify_document, extract_text_preview
from ..package_store import get_package
from ..session_store import get_messages
from .dependencies import get_user_from_header, get_session_context

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["documents"])

GENERIC_EDIT_ERROR = "Unable to save document changes."

# ── Constants ────────────────────────────────────────────────────────

_S3_BUCKET = os.getenv("S3_BUCKET", "eagle-documents-dev")
_BINARY_FILE_EXTENSIONS = {"doc", "docx", "pdf", "xls", "xlsx"}
_TEXT_FILE_EXTENSIONS = {"md", "txt", "json", "csv", "html"}
ALLOWED_UPLOAD_MIME_TYPES = {
    "application/pdf", "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "text/plain", "text/markdown",
}
_MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB

# Feature flag and shared state (set via set_sessions_ref)
USE_PERSISTENT_SESSIONS = os.getenv("USE_PERSISTENT_SESSIONS", "true").lower() == "true"
_SESSIONS: Dict[str, List[dict]] = {}


def set_sessions_ref(sessions_dict: Dict[str, List[dict]]):
    """Set reference to sessions dict from main.py for session export."""
    global _SESSIONS
    _SESSIONS = sessions_dict


def _resolve_main_override(name: str, default: Any) -> Any:
    """Use app.main compatibility aliases when older tests patch them."""
    main_module = sys.modules.get("app.main")
    if main_module is None:
        try:
            from .. import main as main_module
        except Exception:
            return default
    return getattr(main_module, name, default)


def _get_document_metadata(
    tenant_id: str,
    package_id: str,
    doc_type: str,
    version: int,
) -> Optional[Dict[str, Any]]:
    """Read package-document metadata through the compatibility alias when patched."""
    main_module = sys.modules.get("app.main")
    override = getattr(main_module, "get_document", None) if main_module is not None else None
    if callable(override) and override is not get_document:
        return override(tenant_id, package_id, doc_type, version)
    return get_document(tenant_id, package_id, doc_type, version)


# ── Helper Functions ─────────────────────────────────────────────────


def _get_file_extension(name: str) -> str:
    base = name.rsplit("/", 1)[-1]
    if "." not in base:
        return ""
    return base.rsplit(".", 1)[-1].lower()


def _get_doc_type(name: str) -> str:
    """Infer document type from filename."""
    ext = _get_file_extension(name)
    return ext or "unknown"


def _guess_content_type(name: str) -> str:
    ext = _get_file_extension(name)
    if ext == "md":
        return "text/markdown; charset=utf-8"
    if ext == "txt":
        return "text/plain; charset=utf-8"
    if ext == "docx":
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if ext == "xlsx":
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if ext == "pdf":
        return "application/pdf"
    return "application/octet-stream"


def _is_binary_document(name: str, content_type: Optional[str]) -> bool:
    ext = _get_file_extension(name)
    if ext in _BINARY_FILE_EXTENSIONS:
        return True
    lowered = (content_type or "").lower()
    if lowered.startswith("text/"):
        return False
    if "json" in lowered or "markdown" in lowered or "csv" in lowered:
        return False
    if ("officedocument" in lowered or lowered == "application/pdf"
            or lowered == "application/msword" or lowered == "application/vnd.ms-excel"):
        return True
    return ext not in _TEXT_FILE_EXTENSIONS and bool(ext)


def _supports_binary_preview(name: str) -> bool:
    return _get_file_extension(name) in {"docx", "xlsx"}


def _extract_binary_preview_payload(name: str, raw_bytes: bytes) -> dict[str, Any]:
    ext = _get_file_extension(name)
    if ext == "docx":
        from ..document_ai_edit_service import extract_docx_preview_payload

        return extract_docx_preview_payload(raw_bytes)
    if ext == "xlsx":
        from ..spreadsheet_edit_service import extract_xlsx_preview_payload

        return extract_xlsx_preview_payload(raw_bytes)
    return {"content": None, "preview_blocks": [], "preview_sheets": [], "preview_mode": "none"}


def _is_allowed_document_key(doc_key: str, tenant_id: str, user_id: str) -> bool:
    return (doc_key.startswith(f"eagle/{tenant_id}/{user_id}/")
            or doc_key.startswith(f"eagle/{tenant_id}/packages/"))


def _extract_package_document_ref(doc_key: str) -> Optional[dict[str, Any]]:
    canonical = re.match(
        r"^eagle/(?P<tenant>[^/]+)/packages/(?P<package_id>[^/]+)/(?P<doc_type>[^/]+)/v(?P<version>\d+)/(?P<filename>[^/]+)$",
        doc_key,
    )
    if canonical:
        info = canonical.groupdict()
        return {
            "tenant_id": info["tenant"],
            "package_id": info["package_id"],
            "doc_type": info["doc_type"],
            "version": int(info["version"]),
            "filename": info["filename"],
        }
    legacy = re.match(
        r"^eagle/(?P<tenant>[^/]+)/(?P<user>[^/]+)/packages/(?P<package_id>[^/]+)/(?P<filename>[^/]+)$",
        doc_key,
    )
    if not legacy:
        return None
    info = legacy.groupdict()
    filename = info["filename"]
    stem = filename.rsplit(".", 1)[0]
    doc_type = stem.split("_v", 1)[0] if "_v" in stem else stem
    version = None
    version_match = re.search(r"_v(\d+)", stem)
    if version_match:
        version = int(version_match.group(1))
    return {
        "tenant_id": info["tenant"],
        "package_id": info["package_id"],
        "doc_type": doc_type,
        "version": version,
        "filename": filename,
    }


def _build_document_response(
    *,
    doc_key: str,
    response: dict,
    content: Optional[str],
    download_url: Optional[str],
    preview_blocks: Optional[List[dict[str, Any]]] = None,
    preview_sheets: Optional[List[dict[str, Any]]] = None,
    preview_mode: Optional[str] = None,
) -> dict[str, Any]:
    content_type = response.get("ContentType") or _guess_content_type(doc_key)
    package_ref = _extract_package_document_ref(doc_key)
    package_id = package_ref["package_id"] if package_ref else None
    doc_type = package_ref["doc_type"] if package_ref else None
    version = package_ref["version"] if package_ref else None
    filename = (package_ref or {}).get("filename") or doc_key.rsplit("/", 1)[-1]
    file_type = _get_file_extension(filename)
    is_binary = _is_binary_document(filename, content_type)
    title = None
    document_id = doc_key
    if package_ref and version is not None:
        metadata = _get_document_metadata(
            package_ref["tenant_id"],
            package_ref["package_id"],
            package_ref["doc_type"],
            version,
        )
        if metadata:
            title = metadata.get("title")
            document_id = metadata.get("document_id", document_id)
            file_type = metadata.get("file_type", file_type)
            version = metadata.get("version", version)
    elif package_ref:
        title = package_ref["doc_type"].replace("_", " ").title()
    return {
        "key": doc_key,
        "s3_key": doc_key,
        "document_id": document_id,
        "content": content,
        "preview_blocks": preview_blocks or [],
        "preview_sheets": preview_sheets or [],
        "preview_mode": preview_mode,
        "content_type": content_type,
        "file_type": file_type,
        "is_binary": is_binary,
        "download_url": download_url,
        "size_bytes": response.get("ContentLength", 0),
        "last_modified": response.get("LastModified").isoformat() if response.get("LastModified") else None,
        "package_id": package_id,
        "document_type": doc_type,
        "version": version,
        "title": title,
    }


def _get_markdown_sidecar_candidates(doc_key: str) -> list[str]:
    candidates = [get_document_markdown_s3_key(doc_key)]
    if "." in doc_key:
        candidates.append(doc_key.rsplit(".", 1)[0] + ".parsed.md")
    return candidates


def _load_document_markdown_sidecar(
    *,
    s3,
    bucket: str,
    doc_key: str,
    tenant_id: str,
    user_id: str,
) -> Optional[str]:
    from botocore.exceptions import ClientError

    package_ref = _extract_package_document_ref(doc_key)
    metadata = None
    if package_ref and package_ref.get("version") is not None:
        metadata = _get_document_metadata(
            package_ref["tenant_id"],
            package_ref["package_id"],
            package_ref["doc_type"],
            package_ref["version"],
        )

    candidates: list[str] = []
    markdown_s3_key = (metadata or {}).get("markdown_s3_key")
    if markdown_s3_key:
        candidates.append(markdown_s3_key)
    candidates.extend(_get_markdown_sidecar_candidates(doc_key))

    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        if not _is_allowed_document_key(candidate, tenant_id, user_id):
            continue
        try:
            sidecar_resp = s3.get_object(Bucket=bucket, Key=candidate)
            return sidecar_resp["Body"].read().decode("utf-8", errors="replace")
        except ClientError:
            continue
    return None


# ── Upload tracking (DynamoDB) ───────────────────────────────────────


def _coerce_dynamodb_value(value: Any) -> Any:
    """Convert floats in nested upload metadata to Decimal for DynamoDB."""
    from decimal import Decimal

    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, list):
        return [_coerce_dynamodb_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _coerce_dynamodb_value(item) for key, item in value.items()}
    return value


def _put_upload(tenant_id: str, upload_id: str, metadata: Dict[str, Any]) -> None:
    table = get_table()
    item = {
        "PK": f"UPLOAD#{tenant_id}",
        "SK": f"UPLOAD#{upload_id}",
        "ttl": int(time.time()) + 86400,
        **_coerce_dynamodb_value(metadata),
    }
    table.put_item(Item=item)


def _get_upload(tenant_id: str, upload_id: str) -> Optional[Dict[str, Any]]:
    table = get_table()
    resp = table.get_item(Key={"PK": f"UPLOAD#{tenant_id}", "SK": f"UPLOAD#{upload_id}"})
    return resp.get("Item")


def _delete_upload(tenant_id: str, upload_id: str) -> None:
    table = get_table()
    table.delete_item(Key={"PK": f"UPLOAD#{tenant_id}", "SK": f"UPLOAD#{upload_id}"})


# ── Models ───────────────────────────────────────────────────────────


class ExportRequest(BaseModel):
    doc_key: Optional[str] = None
    content: Optional[str] = None
    content_b64: Optional[str] = None
    title: str = "Document"
    format: str = "docx"
    save_to_workspace: bool = False


def _resolve_export_content(req: ExportRequest, tenant_id: str, user_id: str) -> str:
    """Resolve export content from a stored document or inline body payload."""
    from botocore.exceptions import ClientError

    if req.doc_key:
        if not _is_allowed_document_key(req.doc_key, tenant_id, user_id):
            raise HTTPException(status_code=403, detail="Access denied")

        s3 = get_s3()
        try:
            response = s3.get_object(Bucket=_S3_BUCKET, Key=req.doc_key)
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "NoSuchKey":
                raise HTTPException(status_code=404, detail="Document not found") from exc
            logger.error("S3 export fetch error for %s: %s", req.doc_key, exc, exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to retrieve export source") from exc

        content_type = response.get("ContentType") or _guess_content_type(req.doc_key)
        if not _is_binary_document(req.doc_key, content_type):
            return response["Body"].read().decode("utf-8", errors="replace")

        raw_bytes = response["Body"].read()
        if _supports_binary_preview(req.doc_key):
            sidecar_content = _load_document_markdown_sidecar(
                s3=s3,
                bucket=_S3_BUCKET,
                doc_key=req.doc_key,
                tenant_id=tenant_id,
                user_id=user_id,
            )
            if sidecar_content is not None:
                return sidecar_content
            preview_payload = _extract_binary_preview_payload(req.doc_key, raw_bytes)
            if preview_payload.get("content"):
                return preview_payload["content"]

        raise HTTPException(
            status_code=400,
            detail="Document content is not available for export. Open a document with previewable text or provide content directly.",
        )

    if req.content is not None:
        return req.content
    if not req.content_b64:
        raise HTTPException(status_code=400, detail="doc_key or content is required")
    try:
        return base64.b64decode(req.content_b64).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid content_b64 payload") from exc


class DocumentUpdateRequest(BaseModel):
    content: str
    change_source: str = "user_edit"


class DocxPreviewEditRequest(BaseModel):
    preview_blocks: List[Dict[str, Any]]
    preview_mode: str
    change_source: str = "user_edit"


class XlsxPreviewEditRequest(BaseModel):
    cell_edits: List[Dict[str, Any]]
    change_source: str = "user_edit"


class AssignToPackageRequest(BaseModel):
    package_id: str
    doc_type: Optional[str] = None
    title: Optional[str] = None


# ── Endpoints ────────────────────────────────────────────────────────


def _save_export_to_workspace(
    tenant_id: str, user_id: str, filename: str,
    data: bytes, content_type: str, title: str, fmt: str,
) -> str:
    """Save exported file to user's workspace in S3. Returns the S3 key."""
    from ..changelog_store import write_document_changelog_entry

    s3_key = f"eagle/{tenant_id}/{user_id}/exports/{filename}"
    get_s3().put_object(Bucket=_S3_BUCKET, Key=s3_key, Body=data, ContentType=content_type)
    write_document_changelog_entry(
        tenant_id=tenant_id,
        document_key=s3_key,
        change_type="create",
        change_source="user_export",
        change_summary=f"Exported {title} as {fmt}",
        actor_user_id=user_id,
    )
    logger.info("Export saved to workspace: %s (%d bytes)", s3_key, len(data))
    return s3_key


@router.post("/export")
async def api_export_document(req: ExportRequest, user: UserContext = Depends(get_user_from_header)):
    """Export content to DOCX, PDF, or Markdown."""
    try:
        result = export_document(_resolve_export_content(req, user.tenant_id, user.user_id), req.format, req.title)
        headers = {
            "Content-Disposition": f'attachment; filename="{result["filename"]}"',
            "X-File-Size": str(result["size_bytes"]),
        }
        if req.save_to_workspace:
            try:
                s3_key = _save_export_to_workspace(
                    user.tenant_id, user.user_id, result["filename"],
                    result["data"], result["content_type"], req.title, req.format,
                )
                headers["X-S3-Key"] = s3_key
            except Exception as e:
                logger.warning("Failed to save export to workspace: %s", e)
                headers["X-S3-Save-Error"] = str(e)[:200]
        return StreamingResponse(
            io.BytesIO(result["data"]),
            media_type=result["content_type"],
            headers=headers,
        )
    except ExportDependencyError as e:
        logger.error("Export dependency error: %s", e)
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        logger.warning("Export validation error: %s", e)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Export error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error during export")


@router.get("/export/{session_id}")
async def api_export_session(
    session_id: str,
    format: str = "docx",
    user: UserContext = Depends(get_user_from_header),
):
    """Export an entire session conversation."""
    tenant_id, user_id, _ = get_session_context(user)
    if USE_PERSISTENT_SESSIONS:
        messages = get_messages(session_id, tenant_id, user_id)
    else:
        if session_id not in _SESSIONS:
            raise HTTPException(status_code=404, detail="Session not found")
        messages = _SESSIONS[session_id]

    export_ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    content = f"# EAGLE Session Export\n\n**Session ID:** {session_id}\n**Exported:** {export_ts}\n\n---\n\n"
    for msg in messages:
        role = msg.get("role", "unknown").upper()
        text = msg.get("content", "")
        if isinstance(text, list):
            text = json.dumps(text, indent=2)
        content += f"## {role}\n\n{text}\n\n---\n\n"

    try:
        result = export_document(content, format, f"Session_{session_id}")
        return StreamingResponse(
            io.BytesIO(result["data"]),
            media_type=result["content_type"],
            headers={"Content-Disposition": f'attachment; filename="{result["filename"]}"'},
        )
    except ExportDependencyError as e:
        logger.error("Session export dependency error: %s", e)
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("Session export error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error during session export")


@router.get("")
async def api_list_documents(user: UserContext = Depends(get_user_from_header)):
    """List documents in S3 for the current user."""
    from botocore.exceptions import ClientError

    tenant_id = user.tenant_id
    user_id = user.user_id
    bucket = _S3_BUCKET
    prefix = f"eagle/{tenant_id}/{user_id}/"

    try:
        s3 = get_s3()
        response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=100)
        documents = []
        for obj in response.get("Contents", []):
            key = obj["Key"]
            name = key.split("/")[-1]
            if not name:
                continue
            documents.append({
                "key": key,
                "name": name,
                "size_bytes": obj["Size"],
                "last_modified": obj["LastModified"].isoformat(),
                "type": _get_doc_type(name),
            })
        return {"documents": documents, "bucket": bucket, "prefix": prefix}
    except ClientError as e:
        logger.error("S3 list error: %s", e, exc_info=True)
        return {"documents": [], "error": "Failed to list documents"}


@router.get("/presign")
async def api_presign_document(key: str, user: UserContext = Depends(get_user_from_header)):
    """Generate a time-limited presigned URL for an S3 document."""
    from botocore.exceptions import ClientError

    tenant_id = user.tenant_id
    user_id = user.user_id
    if not key.startswith(f"eagle/{tenant_id}/{user_id}/"):
        raise HTTPException(status_code=403, detail="Access denied")

    bucket = _S3_BUCKET
    try:
        s3 = get_s3()
        url = s3.generate_presigned_url("get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=3600)
        return {"url": url, "key": key, "expires_in": 3600}
    except ClientError as e:
        logger.error("Presign error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload")
async def api_upload_document(
    file: UploadFile = File(...),
    session_id: Optional[str] = None,
    package_id: Optional[str] = None,
    user: UserContext = Depends(get_user_from_header),
):
    """Upload a document to the user's S3 workspace with automatic classification."""
    from botocore.exceptions import ClientError

    content_type = file.content_type or "application/octet-stream"
    if content_type not in ALLOWED_UPLOAD_MIME_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {content_type}. Accepted: PDF, Word, plain text, Markdown.",
        )

    body = await file.read()
    if len(body) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 25 MB limit.")

    tenant_id = user.tenant_id
    user_id = user.user_id
    bucket = _S3_BUCKET
    upload_id = str(uuid.uuid4())
    safe_name = re.sub(r"[^A-Za-z0-9._\-]", "_", file.filename or "upload")
    key = f"eagle/{tenant_id}/{user_id}/uploads/{upload_id}/{safe_name}"

    try:
        s3 = get_s3()
        s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType=content_type)
    except ClientError as e:
        logger.error("S3 upload error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to upload document")

    extract_preview = _resolve_main_override("extract_text_preview", extract_text_preview)
    classify = _resolve_main_override("classify_document", classify_document)
    persist_upload = _resolve_main_override("_put_upload", _put_upload)

    content_preview = extract_preview(body, content_type)
    classification = classify(file.filename or safe_name, content_preview)

    from ..document_markdown_service import convert_to_markdown

    markdown_content = convert_to_markdown(body, content_type, file.filename or safe_name)

    quality_score = None
    if markdown_content and classification.doc_type not in ("unknown", None):
        try:
            from ..template_standardizer import standardize_template as _standardize

            std_result = _standardize(
                body, file.filename or safe_name, content_type, classification.doc_type,
            )
            if std_result.success and std_result.quality_score > 50:
                markdown_content = std_result.markdown
            quality_score = std_result.quality_score
        except Exception as e:  # noqa: BLE001
            logger.warning("Auto-standardize failed for %s: %s", safe_name, e)

    markdown_s3_key = None
    if markdown_content:
        md_key = f"{key}.parsed.md"
        try:
            s3 = get_s3()
            s3.put_object(
                Bucket=bucket,
                Key=md_key,
                Body=markdown_content.encode("utf-8"),
                ContentType="text/markdown",
            )
            markdown_s3_key = md_key
        except ClientError as e:
            logger.warning("Failed to upload markdown sibling: %s", e)

    package_context = {"mode": "workspace", "package_id": None}
    if package_id:
        pkg = get_package(tenant_id, package_id)
        if pkg:
            package_context = {"mode": "package", "package_id": package_id}

    persist_upload(tenant_id, upload_id, {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "s3_bucket": bucket,
        "s3_key": key,
        "filename": safe_name,
        "original_filename": file.filename,
        "content_type": content_type,
        "size_bytes": len(body),
        "classification": classification.to_dict(),
        "session_id": session_id,
        "markdown_s3_key": markdown_s3_key,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    })

    logger.info(
        "Uploaded %s -> s3://%s/%s (upload_id=%s, classified=%s)",
        safe_name, bucket, key, upload_id, classification.doc_type,
    )

    return {
        "key": key,
        "upload_id": upload_id,
        "filename": safe_name,
        "size_bytes": len(body),
        "content_type": content_type,
        "classification": classification.to_dict(),
        "package_context": package_context,
        "quality_score": quality_score,
    }


@router.post("/{upload_id}/assign-to-package")
async def assign_upload_to_package(
    upload_id: str,
    body: AssignToPackageRequest,
    user: UserContext = Depends(get_user_from_header),
):
    """Assign an uploaded document to an acquisition package."""
    from botocore.exceptions import ClientError

    get_upload = _resolve_main_override("_get_upload", _get_upload)
    lookup_package = _resolve_main_override("get_package", get_package)
    create_document_version = _resolve_main_override(
        "create_package_document_version",
        create_package_document_version,
    )
    delete_upload = _resolve_main_override("_delete_upload", _delete_upload)

    upload_meta = get_upload(user.tenant_id, upload_id)
    if not upload_meta:
        raise HTTPException(status_code=404, detail="Upload not found or expired")

    if upload_meta["tenant_id"] != user.tenant_id or upload_meta["user_id"] != user.user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    pkg = lookup_package(user.tenant_id, body.package_id)
    if not pkg:
        raise HTTPException(status_code=404, detail=f"Package {body.package_id} not found")

    raw_doc_type = body.doc_type or upload_meta["classification"].get("doc_type", "unknown")
    doc_type = normalize_doc_type(raw_doc_type) if raw_doc_type != "unknown" else "unknown"
    if doc_type == "unknown" or doc_type == "":
        raise HTTPException(
            status_code=400,
            detail="Document type could not be determined. Please specify doc_type.",
        )

    title = body.title or upload_meta["classification"].get("suggested_title") or upload_meta["filename"]

    try:
        s3 = get_s3()
        response = s3.get_object(Bucket=upload_meta["s3_bucket"], Key=upload_meta["s3_key"])
        content = response["Body"].read()
    except ClientError as e:
        logger.error("S3 fetch error for upload %s: %s", upload_id, e)
        raise HTTPException(status_code=500, detail="Failed to retrieve uploaded file")

    markdown_content = None
    markdown_s3_key = upload_meta.get("markdown_s3_key")
    if markdown_s3_key:
        try:
            md_response = s3.get_object(Bucket=upload_meta["s3_bucket"], Key=markdown_s3_key)
            markdown_content = md_response["Body"].read().decode("utf-8", errors="replace")
        except ClientError:
            logger.debug("Could not fetch markdown sibling for upload %s", upload_id)

    from ..tag_computation import (
        compute_completeness_pct,
        compute_document_tags,
        compute_far_tags_from_template,
    )

    doc_stub = {"doc_type": doc_type, "title": title}
    system_tags = compute_document_tags(doc_stub, pkg)
    far_tags = compute_far_tags_from_template(doc_type)
    completeness_pct = None
    if markdown_content:
        completeness_pct = compute_completeness_pct(doc_type, markdown_content)

    content_type = upload_meta["content_type"]
    file_type = "md"
    if "pdf" in content_type:
        file_type = "pdf"
    elif "wordprocessingml" in content_type or "msword" in content_type:
        file_type = "docx"
    elif "spreadsheet" in content_type or "excel" in content_type:
        file_type = "xlsx"

    result = create_document_version(
        tenant_id=user.tenant_id,
        package_id=body.package_id,
        doc_type=doc_type,
        content=content,
        title=title,
        file_type=file_type,
        created_by_user_id=user.user_id,
        session_id=upload_meta.get("session_id"),
        change_source="user_upload",
        markdown_content=markdown_content,
        system_tags=system_tags,
        far_tags=far_tags,
        completeness_pct=completeness_pct,
        original_filename=upload_meta.get("original_filename"),
    )

    if not result.success:
        raise HTTPException(status_code=500, detail=result.error or "Failed to create document")

    delete_upload(user.tenant_id, upload_id)
    logger.info("Assigned upload %s to package %s as %s v%s", upload_id, body.package_id, doc_type, result.version)
    return result.to_dict()


@router.post("/docx-edit/{doc_key:path}")
async def api_update_docx_preview_document(
    doc_key: str,
    request: DocxPreviewEditRequest,
    user: UserContext = Depends(get_user_from_header),
):
    """Update a DOCX document through structured preview blocks."""
    from ..document_ai_edit_service import save_docx_preview_edits

    result = save_docx_preview_edits(
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        doc_key=doc_key,
        preview_blocks=request.preview_blocks,
        preview_mode=request.preview_mode,
        change_source=request.change_source,
    )
    error = result.get("error")
    if error:
        logger.warning("DOCX preview edit failed: %s", error)
        raise HTTPException(status_code=400, detail=GENERIC_EDIT_ERROR)
    return {
        "success": True,
        "mode": result.get("mode"),
        "document_id": result.get("document_id"),
        "key": result.get("key"),
        "version": result.get("version"),
        "file_type": result.get("file_type"),
        "content": result.get("content"),
        "preview_blocks": result.get("preview_blocks", []),
        "preview_mode": result.get("preview_mode"),
        "message": result.get("message"),
    }


@router.post("/xlsx-edit/{doc_key:path}")
async def api_update_xlsx_preview_document(
    doc_key: str,
    request: XlsxPreviewEditRequest,
    user: UserContext = Depends(get_user_from_header),
):
    """Update an XLSX document through structured cell edits."""
    from ..spreadsheet_edit_service import save_xlsx_preview_edits

    result = save_xlsx_preview_edits(
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        doc_key=doc_key,
        cell_edits=request.cell_edits,
        change_source=request.change_source,
    )
    error = result.get("error")
    if error:
        logger.warning("XLSX preview edit failed: %s", error)
        raise HTTPException(status_code=400, detail=GENERIC_EDIT_ERROR)
    return {
        "success": True,
        "mode": result.get("mode"),
        "document_id": result.get("document_id"),
        "key": result.get("key"),
        "version": result.get("version"),
        "file_type": result.get("file_type"),
        "content": result.get("content"),
        "preview_mode": result.get("preview_mode"),
        "preview_sheets": result.get("preview_sheets", []),
        "missing": result.get("missing", []),
        "message": result.get("message"),
    }


# ── Get/Update Single Document ────────────────────────────────────────


@router.get("/{doc_key:path}")
async def api_get_document(
    doc_key: str,
    request: Request,
    user: UserContext = Depends(get_user_from_header),
):
    """Get document content from S3."""
    from botocore.exceptions import ClientError

    tenant_id = user.tenant_id
    user_id = user.user_id
    bucket = _S3_BUCKET

    include_content = request.query_params.get("content") != "false"
    if not _is_allowed_document_key(doc_key, tenant_id, user_id):
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        s3 = get_s3()
        response = s3.get_object(Bucket=bucket, Key=doc_key)
        content_type = response.get("ContentType") or _guess_content_type(doc_key)
        is_binary = _is_binary_document(doc_key, content_type)
        content = None
        download_url = None
        preview_blocks = None
        preview_sheets = None
        preview_mode = None

        if not is_binary and include_content:
            content = response["Body"].read().decode("utf-8", errors="replace")
        else:
            if include_content and _supports_binary_preview(doc_key):
                raw_bytes = response["Body"].read()
                sidecar_content = _load_document_markdown_sidecar(
                    s3=s3,
                    bucket=bucket,
                    doc_key=doc_key,
                    tenant_id=tenant_id,
                    user_id=user_id,
                )
                if sidecar_content is not None:
                    content = sidecar_content
                    preview_mode = "markdown_sidecar"
                else:
                    preview_payload = _extract_binary_preview_payload(doc_key, raw_bytes)
                    content = preview_payload.get("content")
                    preview_blocks = preview_payload.get("preview_blocks", [])
                    preview_sheets = preview_payload.get("preview_sheets", [])
                    preview_mode = preview_payload.get("preview_mode")
            download_url = s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": doc_key},
                ExpiresIn=3600,
            )

        result = _build_document_response(
            doc_key=doc_key,
            response=response,
            content=content,
            download_url=download_url,
            preview_blocks=preview_blocks,
            preview_sheets=preview_sheets,
            preview_mode=preview_mode,
        )
        package_ref = _extract_package_document_ref(doc_key)
        if package_ref and package_ref.get("version") is not None:
            metadata = _get_document_metadata(
                package_ref["tenant_id"],
                package_ref["package_id"],
                package_ref["doc_type"],
                package_ref["version"],
            )
            if metadata:
                result["document_id"] = metadata.get("document_id", result["document_id"])
                result["title"] = metadata.get("title", result.get("title"))
                result["file_type"] = metadata.get("file_type", result["file_type"])
                result["version"] = metadata.get("version", result["version"])
        return result
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchKey":
            raise HTTPException(status_code=404, detail="Document not found")
        logger.error("S3 get document error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve document")


@router.put("/{doc_key:path}")
async def api_update_document(
    doc_key: str,
    request: DocumentUpdateRequest,
    user: UserContext = Depends(get_user_from_header),
):
    """Update document content in S3.

    For package documents (eagle/{tenant}/packages/...), creates a new version.
    For workspace documents, performs a direct overwrite.
    """
    from botocore.exceptions import ClientError

    tenant_id = user.tenant_id
    user_id = user.user_id
    bucket = _S3_BUCKET

    if not _is_allowed_document_key(doc_key, tenant_id, user_id):
        raise HTTPException(status_code=403, detail="Access denied")

    is_package_doc = "/packages/" in doc_key
    file_type = _get_file_extension(doc_key)

    if _is_binary_document(doc_key, _guess_content_type(doc_key)):
        raise HTTPException(
            status_code=415,
            detail="Binary Office documents cannot be saved through the plain text editor. Use the DOCX AI edit flow or download the original file.",
        )

    if is_package_doc:
        package_ref = _extract_package_document_ref(doc_key)
        if not package_ref:
            raise HTTPException(status_code=400, detail="Invalid package document key format")

        package_id = package_ref["package_id"]
        doc_type = package_ref["doc_type"]
        title = doc_type.replace("_", " ").title()
        version = package_ref.get("version")
        if version is not None:
            current = get_document(tenant_id, package_id, doc_type, version)
            if current and current.get("title"):
                title = current["title"]

        result = create_package_document_version(
            tenant_id=tenant_id,
            package_id=package_id,
            doc_type=doc_type,
            content=request.content,
            title=title,
            file_type=file_type or "md",
            created_by_user_id=user_id,
            change_source=request.change_source,
        )

        if not result.success:
            raise HTTPException(status_code=500, detail=result.error or "Failed to create document version")

        return {
            "success": True,
            "key": result.s3_key,
            "version": result.version,
            "document_id": result.document_id,
            "message": f"Document updated (version {result.version})",
        }
    else:
        try:
            s3 = get_s3()
            s3.put_object(
                Bucket=bucket,
                Key=doc_key,
                Body=request.content.encode("utf-8"),
                ContentType=_guess_content_type(doc_key),
            )

            from ..changelog_store import write_document_changelog_entry
            try:
                write_document_changelog_entry(
                    tenant_id=tenant_id,
                    document_key=doc_key,
                    change_type="update",
                    change_source=request.change_source,
                    change_summary="Updated document via editor",
                    actor_user_id=user_id,
                )
            except Exception as cl_err:
                logger.warning("Failed to write changelog for workspace doc: %s", cl_err)

            return {
                "success": True,
                "key": doc_key,
                "message": "Document saved",
            }
        except ClientError as e:
            logger.error("S3 put document error: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to save document")
