"""Document export, S3 browser, and upload endpoints."""

import io
import os
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..cognito_auth import UserContext
from ..document_export import export_document, ExportDependencyError
from ..stores.session_store import get_messages
from ._deps import get_user_from_header, get_session_context, USE_PERSISTENT_SESSIONS, S3_BUCKET
from .chat import SESSIONS  # shared in-memory fallback

logger = logging.getLogger("eagle")
router = APIRouter(tags=["documents"])


# ── Models ────────────────────────────────────────────────────────────

class ExportRequest(BaseModel):
    content: str
    title: str = "Document"
    format: str = "docx"


class DocumentUpdateRequest(BaseModel):
    """Request body for updating document content."""
    content: str
    change_source: str = "user_edit"  # "user_edit" | "ai_edit"


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
    import boto3
    from botocore.exceptions import ClientError

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
async def api_get_document(doc_key: str, user: UserContext = Depends(get_user_from_header)):
    """Get document content from S3."""
    import boto3
    from botocore.exceptions import ClientError

    tenant_id = user.tenant_id
    user_id = user.user_id
    bucket = S3_BUCKET

    # Security: ensure key is within user's prefix
    if not doc_key.startswith(f"eagle/{tenant_id}/{user_id}/"):
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-east-1"))
        response = s3.get_object(Bucket=bucket, Key=doc_key)
        content = response["Body"].read().decode("utf-8", errors="replace")

        return {
            "key": doc_key,
            "content": content,
            "content_type": response.get("ContentType", "text/plain"),
            "size_bytes": response.get("ContentLength", 0),
            "last_modified": response.get("LastModified").isoformat() if response.get("LastModified") else None,
        }
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
    import boto3
    from botocore.exceptions import ClientError

    tenant_id = user.tenant_id
    user_id = user.user_id
    bucket = S3_BUCKET

    # Security: ensure key is within user's prefix
    if not doc_key.startswith(f"eagle/{tenant_id}/{user_id}/"):
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


# ── S3 Presigned URL ─────────────────────────────────────────────────

@router.get("/api/documents/presign")
async def api_presign_document(
    key: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Generate a time-limited presigned URL for an S3 document."""
    import boto3
    from botocore.exceptions import ClientError

    tenant_id = user.tenant_id
    user_id = user.user_id

    if not key.startswith(f"eagle/{tenant_id}/{user_id}/"):
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
    import boto3
    from botocore.exceptions import ClientError
    import re

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


# ── Helpers ───────────────────────────────────────────────────────────

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
