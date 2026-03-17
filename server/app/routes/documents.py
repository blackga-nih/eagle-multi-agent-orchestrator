"""Document export, S3 browser, and upload endpoints."""

import io
import os
import re
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..cognito_auth import UserContext
from ..document_export import export_document, ExportDependencyError
from ..stores.session_store import get_messages
from ..stores.document_store import get_document
from ._deps import get_user_from_header, get_session_context, USE_PERSISTENT_SESSIONS, S3_BUCKET
from .chat import SESSIONS  # shared in-memory fallback

logger = logging.getLogger("eagle")
router = APIRouter(tags=["documents"])


# ── Constants ────────────────────────────────────────────────────────

_BINARY_FILE_EXTENSIONS = {"doc", "docx", "pdf", "xls", "xlsx"}
_TEXT_FILE_EXTENSIONS = {"md", "txt", "json", "csv", "html"}


# ── Models ────────────────────────────────────────────────────────────

class ExportRequest(BaseModel):
    content: str
    title: str = "Document"
    format: str = "docx"


class DocumentUpdateRequest(BaseModel):
    """Request body for updating document content."""
    content: str
    change_source: str = "user_edit"  # "user_edit" | "ai_edit"


class DocxPreviewEditRequest(BaseModel):
    """Request body for structured DOCX preview editing."""
    preview_blocks: List[Dict[str, Any]]
    preview_mode: str
    change_source: str = "user_edit"


class XlsxPreviewEditRequest(BaseModel):
    """Request body for structured XLSX cell editing."""
    cell_edits: List[Dict[str, Any]]
    change_source: str = "user_edit"


# ── Helpers ───────────────────────────────────────────────────────────

def _get_file_extension(name: str) -> str:
    base = name.rsplit("/", 1)[-1]
    if "." not in base:
        return ""
    return base.rsplit(".", 1)[-1].lower()


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
    if (
        "officedocument" in lowered
        or lowered == "application/pdf"
        or lowered == "application/msword"
        or lowered == "application/vnd.ms-excel"
    ):
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
    return (
        doc_key.startswith(f"eagle/{tenant_id}/{user_id}/")
        or doc_key.startswith(f"eagle/{tenant_id}/packages/")
    )


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
        metadata = get_document(package_ref["tenant_id"], package_ref["package_id"], package_ref["doc_type"], version)
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


def _get_doc_type(name: str) -> str:
    """Infer document type from filename."""
    name_lower = name.lower()
    if "sow" in name_lower:
        return "sow"
    elif "igce" in name_lower:
        return "igce"
    elif "market" in name_lower:
        return "market_research"
    elif "justification" in name_lower or "j&a" in name_lower:
        return "justification"
    elif name_lower.endswith(".md"):
        return "markdown"
    elif name_lower.endswith(".pdf"):
        return "pdf"
    elif name_lower.endswith(".docx"):
        return "docx"
    else:
        return "document"


# ── Export endpoints ──────────────────────────────────────────────────

@router.post("/api/documents/export")
async def api_export_document(req: ExportRequest, user: UserContext = Depends(get_user_from_header)):
    """Export content to DOCX, PDF, or Markdown."""
    try:
        result = export_document(req.content, req.format, req.title)

        return StreamingResponse(
            io.BytesIO(result["data"]),
            media_type=result["content_type"],
            headers={
                "Content-Disposition": f'attachment; filename="{result["filename"]}"',
                "X-File-Size": str(result["size_bytes"]),
            }
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


@router.get("/api/documents/export/{session_id}")
async def api_export_session(
    session_id: str,
    format: str = "docx",
    user: UserContext = Depends(get_user_from_header)
):
    """Export an entire session conversation."""
    import json
    tenant_id, user_id, _ = get_session_context(user)

    if USE_PERSISTENT_SESSIONS:
        messages = get_messages(session_id, tenant_id, user_id)
    else:
        if session_id not in SESSIONS:
            raise HTTPException(status_code=404, detail="Session not found")
        messages = SESSIONS[session_id]

    content = f"# EAGLE Session Export\n\n**Session ID:** {session_id}\n**Exported:** {datetime.utcnow().isoformat()}\n\n---\n\n"

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
            headers={
                "Content-Disposition": f'attachment; filename="{result["filename"]}"',
            }
        )
    except ExportDependencyError as e:
        logger.error("Session export dependency error: %s", e)
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("Session export error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error during session export")


# ── S3 Document Browser ──────────────────────────────────────────────

@router.get("/api/documents")
async def api_list_documents(user: UserContext = Depends(get_user_from_header)):
    """List documents in S3 for the current user."""
    tenant_id = user.tenant_id
    user_id = user.user_id
    bucket = S3_BUCKET
    prefix = f"eagle/{tenant_id}/{user_id}/"

    try:
        s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-east-1"))
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


@router.get("/api/documents/{doc_key:path}")
async def api_get_document(
    doc_key: str,
    request: Request,
    user: UserContext = Depends(get_user_from_header),
):
    """Get document content from S3 with binary preview support."""
    tenant_id = user.tenant_id
    user_id = user.user_id
    bucket = S3_BUCKET
    include_content = request.query_params.get("content") != "false"

    # Security: allow workspace documents and canonical tenant package docs
    if not _is_allowed_document_key(doc_key, tenant_id, user_id):
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-east-1"))
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

        return _build_document_response(
            doc_key=doc_key,
            response=response,
            content=content,
            download_url=download_url,
            preview_blocks=preview_blocks,
            preview_sheets=preview_sheets,
            preview_mode=preview_mode,
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchKey":
            raise HTTPException(status_code=404, detail="Document not found")
        logger.error("S3 get document error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve document")


# ── Document Update (PUT) ────────────────────────────────────────────

@router.put("/api/documents/{doc_key:path}")
async def api_update_document(
    doc_key: str,
    request: DocumentUpdateRequest,
    user: UserContext = Depends(get_user_from_header),
):
    """Update document content in S3.

    For package documents (eagle/{tenant}/packages/...), creates a new version.
    For workspace documents, performs a direct overwrite.
    """
    tenant_id = user.tenant_id
    user_id = user.user_id
    bucket = S3_BUCKET

    # Security: ensure key is within user's prefix or package path
    if not _is_allowed_document_key(doc_key, tenant_id, user_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Detect if this is a package document by checking the key pattern
    is_package_doc = "/packages/" in doc_key

    if is_package_doc:
        from app.document_service import create_package_document_version

        parts = doc_key.split("/")
        try:
            pkg_idx = parts.index("packages")
            package_id = parts[pkg_idx + 1]
            filename = parts[-1]
            doc_type = filename.split("_v")[0] if "_v" in filename else filename.rsplit(".", 1)[0]
            title = doc_type.replace("_", " ").title()
        except (ValueError, IndexError):
            raise HTTPException(status_code=400, detail="Invalid package document key format")

        result = create_package_document_version(
            tenant_id=tenant_id,
            package_id=package_id,
            doc_type=doc_type,
            content=request.content,
            title=title,
            file_type="md",
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
            s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-east-1"))
            s3.put_object(
                Bucket=bucket,
                Key=doc_key,
                Body=request.content.encode("utf-8"),
                ContentType="text/markdown; charset=utf-8",
            )
            return {
                "success": True,
                "key": doc_key,
                "message": "Document saved",
            }
        except ClientError as e:
            logger.error("S3 put document error: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to save document")


# ── DOCX Preview Edit (POST) ────────────────────────────────────────

@router.post("/api/documents/docx-edit/{doc_key:path}")
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
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ── XLSX Preview Edit (POST) ────────────────────────────────────────

@router.post("/api/documents/xlsx-edit/{doc_key:path}")
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
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ── S3 Presigned URL ─────────────────────────────────────────────────

@router.get("/api/documents/presign")
async def api_presign_document(
    key: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Generate a time-limited presigned URL for an S3 document."""
    tenant_id = user.tenant_id
    user_id = user.user_id

    if not _is_allowed_document_key(key, tenant_id, user_id):
        raise HTTPException(status_code=403, detail="Access denied")

    bucket = S3_BUCKET
    try:
        s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-east-1"))
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=3600,
        )
        return {"url": url, "key": key, "expires_in": 3600}
    except ClientError as e:
        logger.error("Presign error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ── User document upload ─────────────────────────────────────────────

_ALLOWED_UPLOAD_MIME = {
    "application/pdf", "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain", "text/markdown",
}
_MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB


@router.post("/api/documents/upload")
async def api_upload_document(
    file: UploadFile = File(...),
    user: UserContext = Depends(get_user_from_header),
):
    """Upload a document to the user's S3 workspace and trigger metadata extraction."""
    content_type = file.content_type or "application/octet-stream"
    if content_type not in _ALLOWED_UPLOAD_MIME:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {content_type}. Accepted: PDF, Word, plain text, Markdown."
        )

    body = await file.read()
    if len(body) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 25 MB limit.")

    tenant_id = user.tenant_id
    user_id = user.user_id
    bucket = S3_BUCKET

    safe_name = re.sub(r"[^A-Za-z0-9._\-]", "_", file.filename or "upload")
    key = f"eagle/{tenant_id}/{user_id}/uploads/{safe_name}"

    try:
        s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-east-1"))
        s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType=content_type)
    except ClientError as e:
        logger.error("S3 upload error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to upload document")

    logger.info("Uploaded %s → s3://%s/%s", safe_name, bucket, key)
    return {"key": key, "filename": safe_name, "size_bytes": len(body), "content_type": content_type}
