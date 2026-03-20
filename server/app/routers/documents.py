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
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..cognito_auth import UserContext
from ..document_export import export_document, ExportDependencyError
from ..document_store import get_document
from ..document_service import create_package_document_version
from ..document_ai_edit_service import extract_docx_preview_payload, save_docx_preview_edits
from ..spreadsheet_edit_service import extract_xlsx_preview_payload, save_xlsx_preview_edits
from ..document_classification_service import classify_document, extract_text_preview
from ..package_store import get_package
from ..session_store import get_messages
from .dependencies import get_user_from_header, get_session_context

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["documents"])

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
        return extract_docx_preview_payload(raw_bytes)
    if ext == "xlsx":
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


# ── Upload tracking (DynamoDB) ───────────────────────────────────────


def _put_upload(tenant_id: str, upload_id: str, metadata: Dict[str, Any]) -> None:
    import boto3
    table = boto3.resource("dynamodb", region_name=os.getenv("AWS_REGION", "us-east-1")).Table(
        os.getenv("EAGLE_SESSIONS_TABLE", "eagle")
    )
    item = {"PK": f"UPLOAD#{tenant_id}", "SK": f"UPLOAD#{upload_id}", "ttl": int(time.time()) + 3600, **metadata}
    table.put_item(Item=item)


def _get_upload(tenant_id: str, upload_id: str) -> Optional[Dict[str, Any]]:
    import boto3
    table = boto3.resource("dynamodb", region_name=os.getenv("AWS_REGION", "us-east-1")).Table(
        os.getenv("EAGLE_SESSIONS_TABLE", "eagle")
    )
    resp = table.get_item(Key={"PK": f"UPLOAD#{tenant_id}", "SK": f"UPLOAD#{upload_id}"})
    return resp.get("Item")


def _delete_upload(tenant_id: str, upload_id: str) -> None:
    import boto3
    table = boto3.resource("dynamodb", region_name=os.getenv("AWS_REGION", "us-east-1")).Table(
        os.getenv("EAGLE_SESSIONS_TABLE", "eagle")
    )
    table.delete_item(Key={"PK": f"UPLOAD#{tenant_id}", "SK": f"UPLOAD#{upload_id}"})


# ── Models ───────────────────────────────────────────────────────────


class ExportRequest(BaseModel):
    content: str
    title: str = "Document"
    format: str = "docx"


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


@router.post("/export")
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
            },
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
    import boto3
    from botocore.exceptions import ClientError

    tenant_id = user.tenant_id
    user_id = user.user_id
    bucket = _S3_BUCKET
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


@router.get("/presign")
async def api_presign_document(key: str, user: UserContext = Depends(get_user_from_header)):
    """Generate a time-limited presigned URL for an S3 document."""
    import boto3
    from botocore.exceptions import ClientError

    tenant_id = user.tenant_id
    user_id = user.user_id
    if not key.startswith(f"eagle/{tenant_id}/{user_id}/"):
        raise HTTPException(status_code=403, detail="Access denied")

    bucket = _S3_BUCKET
    try:
        s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-east-1"))
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
    import boto3
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
        s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-east-1"))
        s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType=content_type)
    except ClientError as e:
        logger.error("S3 upload error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to upload document")

    content_preview = extract_text_preview(body, content_type)
    classification = classify_document(file.filename or safe_name, content_preview)

    package_context = {"mode": "workspace", "package_id": None}
    if package_id:
        pkg = get_package(tenant_id, package_id)
        if pkg:
            package_context = {"mode": "package", "package_id": package_id}

    _put_upload(tenant_id, upload_id, {
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
        "created_at": datetime.utcnow().isoformat(),
    })

    logger.info("Uploaded %s -> s3://%s/%s (upload_id=%s, classified=%s)", safe_name, bucket, key, upload_id, classification.doc_type)

    return {
        "key": key,
        "upload_id": upload_id,
        "filename": safe_name,
        "size_bytes": len(body),
        "content_type": content_type,
        "classification": classification.to_dict(),
        "package_context": package_context,
    }


@router.post("/{upload_id}/assign-to-package")
async def assign_upload_to_package(
    upload_id: str,
    body: AssignToPackageRequest,
    user: UserContext = Depends(get_user_from_header),
):
    """Assign an uploaded document to an acquisition package."""
    import boto3
    from botocore.exceptions import ClientError

    upload_meta = _get_upload(user.tenant_id, upload_id)
    if not upload_meta:
        raise HTTPException(status_code=404, detail="Upload not found or expired")

    if upload_meta["tenant_id"] != user.tenant_id or upload_meta["user_id"] != user.user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    pkg = get_package(user.tenant_id, body.package_id)
    if not pkg:
        raise HTTPException(status_code=404, detail=f"Package {body.package_id} not found")

    doc_type = body.doc_type or upload_meta["classification"].get("doc_type", "unknown")
    if doc_type == "unknown":
        raise HTTPException(status_code=400, detail="Document type could not be determined. Please specify doc_type.")

    title = body.title or upload_meta["classification"].get("suggested_title") or upload_meta["filename"]

    try:
        s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-east-1"))
        response = s3.get_object(Bucket=upload_meta["s3_bucket"], Key=upload_meta["s3_key"])
        content = response["Body"].read()
    except ClientError as e:
        logger.error("S3 fetch error for upload %s: %s", upload_id, e)
        raise HTTPException(status_code=500, detail="Failed to retrieve uploaded file")

    content_type = upload_meta["content_type"]
    file_type = "md"
    if "pdf" in content_type:
        file_type = "pdf"
    elif "wordprocessingml" in content_type or "msword" in content_type:
        file_type = "docx"
    elif "spreadsheet" in content_type or "excel" in content_type:
        file_type = "xlsx"

    result = create_package_document_version(
        tenant_id=user.tenant_id,
        package_id=body.package_id,
        doc_type=doc_type,
        content=content,
        title=title,
        file_type=file_type,
        created_by_user_id=user.user_id,
        session_id=upload_meta.get("session_id"),
        change_source="user_upload",
    )

    if not result.success:
        raise HTTPException(status_code=500, detail=result.error or "Failed to create document")

    _delete_upload(user.tenant_id, upload_id)
    logger.info("Assigned upload %s to package %s as %s v%s", upload_id, body.package_id, doc_type, result.version)
    return result.to_dict()


@router.post("/docx-edit/{doc_key:path}")
async def api_update_docx_preview_document(
    doc_key: str,
    request: DocxPreviewEditRequest,
    user: UserContext = Depends(get_user_from_header),
):
    """Update a DOCX document through structured preview blocks."""
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


@router.post("/xlsx-edit/{doc_key:path}")
async def api_update_xlsx_preview_document(
    doc_key: str,
    request: XlsxPreviewEditRequest,
    user: UserContext = Depends(get_user_from_header),
):
    """Update an XLSX document through structured cell edits."""
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


# ── Get/Update Single Document ────────────────────────────────────────


@router.get("/{doc_key:path}")
async def api_get_document(
    doc_key: str,
    request: Request,
    user: UserContext = Depends(get_user_from_header),
):
    """Get document content from S3."""
    import boto3
    from botocore.exceptions import ClientError

    tenant_id = user.tenant_id
    user_id = user.user_id
    bucket = _S3_BUCKET

    include_content = request.query_params.get("content") != "false"
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
                sidecar_key = f"{doc_key}.content.md"
                try:
                    sidecar_resp = s3.get_object(Bucket=bucket, Key=sidecar_key)
                    content = sidecar_resp["Body"].read().decode("utf-8", errors="replace")
                    preview_mode = "markdown_sidecar"
                except ClientError:
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
    import boto3
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
            s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-east-1"))
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
