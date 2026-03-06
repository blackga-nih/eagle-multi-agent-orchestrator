"""
Document Service -- Canonical document creation for packages.

Orchestrates the creation of versioned package documents with:
1. DynamoDB metadata records (DOCUMENT#)
2. S3 content storage at deterministic keys
3. Automatic version increment and supersession
4. Atomicity via pending/draft status pattern

This is the single source of truth for package document creation,
used by both the chat tool path and the package API path.
"""
import os
import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Tuple

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from .document_store import (
    get_document_history,
    get_document,
    finalize_document as store_finalize_document,
)
from .package_store import get_package, update_package

logger = logging.getLogger("eagle.document_service")

# Configuration
S3_BUCKET = os.getenv("S3_BUCKET", "eagle-documents-695681773636-dev")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
TABLE_NAME = os.getenv("EAGLE_SESSIONS_TABLE", "eagle")

# Lazy singletons
_s3 = None
_dynamodb = None


def _get_s3():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3", region_name=AWS_REGION)
    return _s3


def _get_dynamodb():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
    return _dynamodb


def _get_table():
    return _get_dynamodb().Table(TABLE_NAME)


@dataclass
class DocumentResult:
    """Result of a document creation operation."""

    success: bool
    document_id: Optional[str] = None
    package_id: Optional[str] = None
    doc_type: Optional[str] = None
    version: Optional[int] = None
    status: Optional[str] = None
    s3_bucket: Optional[str] = None
    s3_key: Optional[str] = None
    content_hash: Optional[str] = None
    title: Optional[str] = None
    word_count: Optional[int] = None
    created_at: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            k: v for k, v in {
                "success": self.success,
                "document_id": self.document_id,
                "package_id": self.package_id,
                "doc_type": self.doc_type,
                "version": self.version,
                "status": self.status,
                "s3_bucket": self.s3_bucket,
                "s3_key": self.s3_key,
                "content_hash": self.content_hash,
                "title": self.title,
                "word_count": self.word_count,
                "created_at": self.created_at,
                "error": self.error,
            }.items() if v is not None
        }


def create_package_document_version(
    tenant_id: str,
    package_id: str,
    doc_type: str,
    content: bytes | str,
    title: str,
    file_type: str = "md",
    created_by_user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    change_source: str = "agent_tool",
    template_id: Optional[str] = None,
) -> DocumentResult:
    """Create a new versioned document for a package.

    This is the canonical entry point for package document creation.
    Handles version calculation, S3 storage, and DynamoDB metadata.

    Args:
        tenant_id: Tenant identifier
        package_id: Package identifier
        doc_type: Document type (sow, igce, market_research, etc.)
        content: Document content (bytes for binary, str for text)
        title: Document title
        file_type: File extension (md, docx, xlsx)
        created_by_user_id: User who created the document
        session_id: Chat session that triggered creation
        change_source: How the document was created (agent_tool, user_edit, import, migration)
        template_id: Template used for generation (if any)

    Returns:
        DocumentResult with success status and document details
    """
    # Validate package exists
    pkg = get_package(tenant_id, package_id)
    if not pkg:
        return DocumentResult(
            success=False,
            error=f"Package {package_id} not found for tenant {tenant_id}"
        )

    # Calculate content hash for idempotency
    if isinstance(content, str):
        content_bytes = content.encode("utf-8")
    else:
        content_bytes = content
    content_hash = hashlib.sha256(content_bytes).hexdigest()

    # Check for duplicate (same content already exists for this package+doc_type)
    existing = _find_by_content_hash(tenant_id, package_id, doc_type, content_hash)
    if existing:
        logger.info(
            "Document with same content already exists: %s v%s",
            doc_type, existing.get("version")
        )
        return DocumentResult(
            success=True,
            document_id=existing.get("document_id"),
            package_id=package_id,
            doc_type=doc_type,
            version=existing.get("version"),
            status=existing.get("status"),
            s3_bucket=existing.get("s3_bucket"),
            s3_key=existing.get("s3_key"),
            content_hash=content_hash,
            title=existing.get("title", title),
            created_at=existing.get("created_at"),
        )

    # Calculate next version
    history = get_document_history(tenant_id, package_id, doc_type)
    next_version = (max(d["version"] for d in history) + 1) if history else 1

    # Generate S3 key
    artifact_name = _sanitize_filename(title) or doc_type
    s3_key = f"eagle/{tenant_id}/packages/{package_id}/{doc_type}/v{next_version}/{artifact_name}.{file_type}"

    now = datetime.utcnow().isoformat()

    # Step 1: Create DynamoDB record with status=pending
    document_id, db_error = _create_document_record(
        tenant_id=tenant_id,
        package_id=package_id,
        doc_type=doc_type,
        version=next_version,
        title=title,
        content_hash=content_hash,
        s3_bucket=S3_BUCKET,
        s3_key=s3_key,
        file_type=file_type,
        created_by_user_id=created_by_user_id,
        session_id=session_id,
        change_source=change_source,
        template_id=template_id,
        status="pending",
        created_at=now,
    )

    if db_error:
        return DocumentResult(success=False, error=f"DynamoDB write failed: {db_error}")

    # Step 2: Upload to S3
    s3_error = _upload_to_s3(s3_key, content_bytes, file_type)

    if s3_error:
        # Mark DynamoDB record as failed
        _update_document_status(tenant_id, package_id, doc_type, next_version, "failed", s3_error)
        return DocumentResult(
            success=False,
            document_id=document_id,
            error=f"S3 upload failed: {s3_error}"
        )

    # Step 3: Update status to draft
    _update_document_status(tenant_id, package_id, doc_type, next_version, "draft")

    # Step 4: Supersede prior versions
    _supersede_prior_versions(tenant_id, package_id, doc_type, next_version)

    # Step 5: Update package completed_documents if needed
    _update_package_checklist(tenant_id, package_id, doc_type)

    word_count = len(content.split()) if isinstance(content, str) else None

    logger.info(
        "Created document %s v%s for package %s",
        doc_type, next_version, package_id
    )

    return DocumentResult(
        success=True,
        document_id=document_id,
        package_id=package_id,
        doc_type=doc_type,
        version=next_version,
        status="draft",
        s3_bucket=S3_BUCKET,
        s3_key=s3_key,
        content_hash=content_hash,
        title=title,
        word_count=word_count,
        created_at=now,
    )


def get_document_download_url(
    tenant_id: str,
    package_id: str,
    doc_type: str,
    version: Optional[int] = None,
    expires_in: int = 3600,
) -> Optional[str]:
    """Generate a presigned URL for downloading a document.

    Args:
        tenant_id: Tenant identifier
        package_id: Package identifier
        doc_type: Document type
        version: Specific version (None for latest)
        expires_in: URL expiration in seconds (default 1 hour)

    Returns:
        Presigned URL string, or None if document not found
    """
    doc = get_document(tenant_id, package_id, doc_type, version)
    if not doc:
        return None

    s3_key = doc.get("s3_key")
    s3_bucket = doc.get("s3_bucket", S3_BUCKET)

    if not s3_key:
        # Legacy document without S3 key
        return None

    try:
        s3 = _get_s3()
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": s3_bucket, "Key": s3_key},
            ExpiresIn=expires_in,
        )
        return url
    except (ClientError, BotoCoreError) as e:
        logger.error("Failed to generate presigned URL: %s", e)
        return None


def finalize_document(
    tenant_id: str,
    package_id: str,
    doc_type: str,
    version: int,
) -> Optional[dict]:
    """Finalize a document version (transition from draft to final).

    Args:
        tenant_id: Tenant identifier
        package_id: Package identifier
        doc_type: Document type
        version: Version to finalize

    Returns:
        Updated document dict, or None if not found
    """
    return store_finalize_document(tenant_id, package_id, doc_type, version)


# --- Internal helpers ---

def _create_document_record(
    tenant_id: str,
    package_id: str,
    doc_type: str,
    version: int,
    title: str,
    content_hash: str,
    s3_bucket: str,
    s3_key: str,
    file_type: str,
    created_by_user_id: Optional[str],
    session_id: Optional[str],
    change_source: str,
    template_id: Optional[str],
    status: str,
    created_at: str,
) -> Tuple[Optional[str], Optional[str]]:
    """Create a DOCUMENT# record in DynamoDB.

    Returns:
        Tuple of (document_id, error_message)
    """
    import uuid

    document_id = str(uuid.uuid4())

    item = {
        "PK": f"DOCUMENT#{tenant_id}",
        "SK": f"DOCUMENT#{package_id}#{doc_type}#{version}",
        "GSI1PK": f"TENANT#{tenant_id}",
        "GSI1SK": f"DOCUMENT#{package_id}#{doc_type}#{version:04d}",
        "document_id": document_id,
        "package_id": package_id,
        "doc_type": doc_type,
        "version": version,
        "title": title,
        "status": status,
        "content_hash": content_hash,
        "s3_bucket": s3_bucket,
        "s3_key": s3_key,
        "file_type": file_type,
        "change_source": change_source,
        "created_at": created_at,
    }

    if created_by_user_id:
        item["created_by_user_id"] = created_by_user_id
    if session_id:
        item["session_id"] = session_id
    if template_id:
        item["template_id"] = template_id

    try:
        table = _get_table()
        table.put_item(Item=item)
        return document_id, None
    except (ClientError, BotoCoreError) as e:
        logger.error("Failed to create document record: %s", e)
        return None, str(e)


def _update_document_status(
    tenant_id: str,
    package_id: str,
    doc_type: str,
    version: int,
    status: str,
    error_message: Optional[str] = None,
) -> None:
    """Update the status of a document record."""
    try:
        table = _get_table()

        update_expr = "SET #s = :status"
        expr_names = {"#s": "status"}
        expr_values = {":status": status}

        if error_message:
            update_expr += ", error_message = :err"
            expr_values[":err"] = error_message

        table.update_item(
            Key={
                "PK": f"DOCUMENT#{tenant_id}",
                "SK": f"DOCUMENT#{package_id}#{doc_type}#{version}",
            },
            UpdateExpression=update_expr,
            ExpressionAttributeNames=expr_names,
            ExpressionAttributeValues=expr_values,
        )
    except (ClientError, BotoCoreError) as e:
        logger.error("Failed to update document status: %s", e)


def _upload_to_s3(s3_key: str, content: bytes, file_type: str) -> Optional[str]:
    """Upload content to S3.

    Returns:
        Error message if failed, None if successful
    """
    content_types = {
        "md": "text/markdown",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "pdf": "application/pdf",
    }
    content_type = content_types.get(file_type, "application/octet-stream")

    try:
        s3 = _get_s3()
        s3.put_object(
            Bucket=S3_BUCKET,
            Key=s3_key,
            Body=content,
            ContentType=content_type,
        )
        return None
    except (ClientError, BotoCoreError) as e:
        logger.error("S3 upload failed for %s: %s", s3_key, e)
        return str(e)


def _supersede_prior_versions(
    tenant_id: str,
    package_id: str,
    doc_type: str,
    current_version: int,
) -> None:
    """Mark all prior versions as superseded."""
    history = get_document_history(tenant_id, package_id, doc_type)
    table = _get_table()

    for doc in history:
        if doc["version"] < current_version and doc.get("status") != "superseded":
            try:
                table.update_item(
                    Key={
                        "PK": f"DOCUMENT#{tenant_id}",
                        "SK": f"DOCUMENT#{package_id}#{doc_type}#{doc['version']}",
                    },
                    UpdateExpression="SET #s = :superseded",
                    ExpressionAttributeNames={"#s": "status"},
                    ExpressionAttributeValues={":superseded": "superseded"},
                )
            except (ClientError, BotoCoreError) as e:
                logger.warning(
                    "Failed to supersede version %s: %s", doc["version"], e
                )


def _update_package_checklist(
    tenant_id: str,
    package_id: str,
    doc_type: str,
) -> None:
    """Update package completed_documents if this doc_type is required."""
    pkg = get_package(tenant_id, package_id)
    if not pkg:
        return

    required = pkg.get("required_documents", [])
    completed = pkg.get("completed_documents", [])

    if doc_type in required and doc_type not in completed:
        completed = list(set(completed + [doc_type]))
        update_package(tenant_id, package_id, {"completed_documents": completed})
        logger.debug(
            "Updated package %s completed_documents: %s", package_id, completed
        )


def _find_by_content_hash(
    tenant_id: str,
    package_id: str,
    doc_type: str,
    content_hash: str,
) -> Optional[dict]:
    """Find an existing document with the same content hash."""
    history = get_document_history(tenant_id, package_id, doc_type)
    for doc in history:
        if doc.get("content_hash") == content_hash and doc.get("status") != "failed":
            return doc
    return None


def _sanitize_filename(name: str) -> str:
    """Sanitize a string for use in S3 keys."""
    import re
    # Replace spaces with hyphens, remove non-alphanumeric except hyphens/underscores
    sanitized = re.sub(r"[^\w\s-]", "", name)
    sanitized = re.sub(r"\s+", "-", sanitized)
    return sanitized[:50].strip("-")  # Limit length
