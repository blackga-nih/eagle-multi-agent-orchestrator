"""User Document Store -- user uploads and workspace documents.

Manages durable document records for user-uploaded files and workspace
documents. Documents can optionally be assigned to acquisition packages.
Separate from package_document_store.py which handles agent-generated
versioned acquisition documents (DOCUMENT# prefix).

Entity format:
    PK:  USER_DOC#{tenant_id}
    SK:  USER_DOC#{document_id}

GSI1 (user's documents):
    GSI1PK:  OWNER#{tenant_id}#{user_id}
    GSI1SK:  USER_DOC#{created_at}

GSI2 (package's documents):
    GSI2PK:  PKG#{tenant_id}#{package_id}
    GSI2SK:  USER_DOC#{doc_type}#{version:04d}
"""

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError

from .db_client import get_table, item_to_dict

logger = logging.getLogger("eagle.user_document_store")


# -- Key Helpers --------------------------------------------------------------


def _pk(tenant_id: str) -> str:
    return f"USER_DOC#{tenant_id}"


def _sk(document_id: str) -> str:
    return f"USER_DOC#{document_id}"


def _gsi1_pk(tenant_id: str, user_id: str) -> str:
    return f"OWNER#{tenant_id}#{user_id}"


def _gsi1_sk(created_at: str) -> str:
    return f"USER_DOC#{created_at}"


def _gsi2_pk(tenant_id: str, package_id: Optional[str]) -> str:
    if package_id is None:
        return f"PKG#{tenant_id}#__NONE__"
    return f"PKG#{tenant_id}#{package_id}"


def _gsi2_sk(doc_type: str, version: int) -> str:
    return f"USER_DOC#{doc_type}#{version:04d}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _to_dynamodb_value(value: Any) -> Any:
    """Recursively normalize Python values for DynamoDB writes.

    boto3 rejects raw float values. Convert them to Decimal while preserving
    nested structures such as classification metadata.
    """
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, list):
        return [_to_dynamodb_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _to_dynamodb_value(v) for k, v in value.items()}
    return value


# -- Core CRUD ----------------------------------------------------------------


def create_document(
    tenant_id: str,
    user_id: str,
    s3_bucket: str,
    s3_key: str,
    filename: str,
    original_filename: str,
    content_type: str,
    size_bytes: int,
    doc_type: str = "unknown",
    title: Optional[str] = None,
    file_type: Optional[str] = None,
    classification: Optional[dict] = None,
    markdown_s3_key: Optional[str] = None,
    content_hash: Optional[str] = None,
    package_id: Optional[str] = None,
    is_deliverable: bool = False,
    session_id: Optional[str] = None,
    document_id: Optional[str] = None,
    # Origin context for IGCE XLSX generation (Phase 4)
    template_id: Optional[str] = None,
    template_provenance: Optional[dict] = None,
    source_context_type: Optional[str] = None,
    source_data_summary: Optional[str] = None,
    source_data: Optional[dict] = None,
) -> dict:
    """Create a new document record.

    Documents are durable from creation (no TTL). They can be assigned to a
    package later via update_document().

    Args:
        tenant_id: Tenant identifier
        user_id: User who uploaded the document
        s3_bucket: S3 bucket name
        s3_key: S3 object key for the original file
        filename: Sanitized filename
        original_filename: Original filename from upload
        content_type: MIME type
        size_bytes: File size in bytes
        doc_type: Document type (requirements, sow, igce, etc.)
        title: Document title (defaults to filename)
        file_type: File extension (docx, xlsx, pdf, etc.)
        classification: Auto-classification result dict
        markdown_s3_key: S3 key for markdown sidecar
        content_hash: SHA256 hash of content
        package_id: Package to assign to (null = workspace)
        is_deliverable: True if this is a generated output
        session_id: Chat session that created this document
        document_id: Optional precomputed document UUID to preserve external IDs
        template_id: Template identifier used for generation
        template_provenance: Dict with template source info (s3_key, source, etc.)
        source_context_type: Type of generation context (e.g., "igce_xlsx_generation")
        source_data_summary: Human-readable summary of generation context
        source_data: Compact dict of generation data for follow-up edits

    Returns:
        Created document dict
    """
    table = get_table()
    now = _now_iso()
    document_id = document_id or str(uuid.uuid4())

    item: dict = {
        "PK": _pk(tenant_id),
        "SK": _sk(document_id),
        "GSI1PK": _gsi1_pk(tenant_id, user_id),
        "GSI1SK": _gsi1_sk(now),
        "GSI2PK": _gsi2_pk(tenant_id, package_id),
        "GSI2SK": _gsi2_sk(doc_type, 1),
        # Core fields
        "document_id": document_id,
        "tenant_id": tenant_id,
        "owner_user_id": user_id,
        # S3 location
        "s3_bucket": s3_bucket,
        "s3_key": s3_key,
        # Versioning
        "current_version": 1,
        "status": "draft",
        # Classification
        "title": title or filename,
        "doc_type": doc_type,
        "file_type": file_type or _infer_file_type(content_type, filename),
        "content_type": content_type,
        # Package relationship
        "package_id": package_id,
        "is_deliverable": is_deliverable,
        # Metadata
        "filename": filename,
        "original_filename": original_filename,
        "size_bytes": size_bytes,
        "created_at": now,
        "updated_at": now,
    }

    # Optional fields
    if classification:
        item["classification"] = classification
    if markdown_s3_key:
        item["markdown_s3_key"] = markdown_s3_key
    if content_hash:
        item["content_hash"] = content_hash
    if session_id:
        item["session_id"] = session_id
    # Origin context for IGCE XLSX generation
    if template_id:
        item["template_id"] = template_id
    if template_provenance:
        item["template_provenance"] = template_provenance
    if source_context_type:
        item["source_context_type"] = source_context_type
    if source_data_summary:
        item["source_data_summary"] = source_data_summary
    if source_data:
        item["source_data"] = source_data

    try:
        table.put_item(Item=_to_dynamodb_value(item))
        logger.info(
            "Created document %s for user %s (package=%s)",
            document_id,
            user_id,
            package_id,
        )
        return item_to_dict(item)
    except ClientError as e:
        logger.error("Failed to create document: %s", e)
        raise


def get_document(tenant_id: str, document_id: str) -> Optional[dict]:
    """Get a document by ID.

    Args:
        tenant_id: Tenant identifier
        document_id: Document UUID

    Returns:
        Document dict or None if not found
    """
    table = get_table()
    try:
        response = table.get_item(
            Key={"PK": _pk(tenant_id), "SK": _sk(document_id)}
        )
        item = response.get("Item")
        return item_to_dict(item) if item else None
    except ClientError as e:
        logger.error("Failed to get document %s: %s", document_id, e)
        raise


def update_document(
    tenant_id: str,
    document_id: str,
    updates: dict[str, Any],
) -> Optional[dict]:
    """Update document fields.

    Common use cases:
    - Assign to package: updates={"package_id": "PKG-2026-0001"}
    - Unassign: updates={"package_id": None}
    - Update title: updates={"title": "New Title"}
    - Mark as deliverable: updates={"is_deliverable": True}

    Args:
        tenant_id: Tenant identifier
        document_id: Document UUID
        updates: Dict of fields to update

    Returns:
        Updated document dict or None if not found
    """
    table = get_table()

    # Build update expression
    update_parts = ["updated_at = :now"]
    expr_values: dict[str, Any] = {":now": _now_iso()}
    expr_names: dict[str, str] = {}

    # Allowed update fields
    allowed_fields = {
        "package_id", "is_deliverable", "title", "doc_type",
        "status", "markdown_s3_key", "content_hash",
    }

    for key, value in updates.items():
        if key not in allowed_fields:
            logger.warning("Ignoring non-updatable field: %s", key)
            continue

        # Handle reserved words
        attr_name = f"#{key}" if key in {"status"} else key
        if key in {"status"}:
            expr_names[attr_name] = key

        update_parts.append(f"{attr_name} = :{key}")
        expr_values[f":{key}"] = _to_dynamodb_value(value)

    # Update GSI2PK if package_id changed
    if "package_id" in updates:
        new_package_id = updates["package_id"]
        update_parts.append("GSI2PK = :gsi2pk")
        expr_values[":gsi2pk"] = _gsi2_pk(tenant_id, new_package_id)

    update_expr = "SET " + ", ".join(update_parts)

    try:
        response = table.update_item(
            Key={"PK": _pk(tenant_id), "SK": _sk(document_id)},
            UpdateExpression=update_expr,
            ExpressionAttributeValues=expr_values,
            ExpressionAttributeNames=expr_names if expr_names else None,
            ConditionExpression=Attr("PK").exists(),
            ReturnValues="ALL_NEW",
        )
        logger.info("Updated document %s: %s", document_id, list(updates.keys()))
        return item_to_dict(response.get("Attributes", {}))
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            logger.warning("Document %s not found for update", document_id)
            return None
        logger.error("Failed to update document %s: %s", document_id, e)
        raise


def delete_document(tenant_id: str, document_id: str) -> bool:
    """Delete a document record.

    Note: This only deletes the DynamoDB record. S3 cleanup should be
    handled separately by the caller.

    Args:
        tenant_id: Tenant identifier
        document_id: Document UUID

    Returns:
        True if deleted, False if not found
    """
    table = get_table()
    try:
        response = table.delete_item(
            Key={"PK": _pk(tenant_id), "SK": _sk(document_id)},
            ConditionExpression=Attr("PK").exists(),
            ReturnValues="ALL_OLD",
        )
        deleted = response.get("Attributes") is not None
        if deleted:
            logger.info("Deleted document %s", document_id)
        return deleted
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        logger.error("Failed to delete document %s: %s", document_id, e)
        raise


# -- List Queries -------------------------------------------------------------


def list_user_documents(
    tenant_id: str,
    user_id: str,
    scope: str = "all",
    limit: int = 100,
) -> list[dict]:
    """List documents owned by a user.

    Args:
        tenant_id: Tenant identifier
        user_id: User identifier
        scope: "all", "workspace" (package_id=null), or "assigned" (has package)
        limit: Maximum number of documents to return

    Returns:
        List of document dicts, sorted by created_at descending
    """
    table = get_table()

    try:
        response = table.query(
            IndexName="GSI1",
            KeyConditionExpression=Key("GSI1PK").eq(_gsi1_pk(tenant_id, user_id)),
            ScanIndexForward=False,  # Newest first
            Limit=limit,
        )
        documents = [item_to_dict(item) for item in response.get("Items", [])]

        # Apply scope filter
        if scope == "workspace":
            documents = [d for d in documents if d.get("package_id") is None]
        elif scope == "assigned":
            documents = [d for d in documents if d.get("package_id") is not None]

        return documents
    except ClientError as e:
        logger.error("Failed to list user documents: %s", e)
        raise


def list_package_documents(
    tenant_id: str,
    package_id: str,
    deliverable_only: Optional[bool] = None,
    limit: int = 100,
) -> list[dict]:
    """List documents in a package.

    Args:
        tenant_id: Tenant identifier
        package_id: Package identifier
        deliverable_only: If True, only return deliverables; if False, only sources
        limit: Maximum number of documents to return

    Returns:
        List of document dicts
    """
    table = get_table()

    try:
        response = table.query(
            IndexName="GSI2",
            KeyConditionExpression=Key("GSI2PK").eq(_gsi2_pk(tenant_id, package_id)),
            Limit=limit,
        )
        documents = [item_to_dict(item) for item in response.get("Items", [])]

        # Apply deliverable filter
        if deliverable_only is True:
            documents = [d for d in documents if d.get("is_deliverable") is True]
        elif deliverable_only is False:
            documents = [d for d in documents if d.get("is_deliverable") is False]

        return documents
    except ClientError as e:
        logger.error("Failed to list package documents: %s", e)
        raise


# -- Versioning ---------------------------------------------------------------


def create_document_version(
    tenant_id: str,
    document_id: str,
    s3_key: str,
    content_hash: str,
    size_bytes: int,
    markdown_s3_key: Optional[str] = None,
) -> Optional[dict]:
    """Create a new version of an existing document.

    Increments current_version, updates S3 keys, and marks previous version
    as superseded.

    Args:
        tenant_id: Tenant identifier
        document_id: Document UUID
        s3_key: New S3 key for this version
        content_hash: SHA256 hash of new content
        size_bytes: New file size
        markdown_s3_key: New markdown sidecar key

    Returns:
        Updated document dict or None if not found
    """
    doc = get_document(tenant_id, document_id)
    if not doc:
        return None

    new_version = doc.get("current_version", 1) + 1
    now = _now_iso()

    # Update GSI2SK with new version
    new_gsi2_sk = _gsi2_sk(doc.get("doc_type", "unknown"), new_version)

    updates = {
        "current_version": new_version,
        "s3_key": s3_key,
        "content_hash": content_hash,
        "size_bytes": size_bytes,
        "GSI2SK": new_gsi2_sk,
        "updated_at": now,
    }

    if markdown_s3_key:
        updates["markdown_s3_key"] = markdown_s3_key

    table = get_table()
    try:
        # Build update expression for version fields
        update_parts = [f"{k} = :{k}" for k in updates.keys()]
        expr_values = {f":{k}": v for k, v in updates.items()}

        response = table.update_item(
            Key={"PK": _pk(tenant_id), "SK": _sk(document_id)},
            UpdateExpression="SET " + ", ".join(update_parts),
            ExpressionAttributeValues=expr_values,
            ConditionExpression=Attr("PK").exists(),
            ReturnValues="ALL_NEW",
        )
        logger.info("Created version %d for document %s", new_version, document_id)
        return item_to_dict(response.get("Attributes", {}))
    except ClientError as e:
        logger.error("Failed to create document version: %s", e)
        raise


# -- Helpers ------------------------------------------------------------------


def _infer_file_type(content_type: str, filename: str) -> str:
    """Infer file type from content type or filename."""
    # Try content type first
    type_map = {
        "application/pdf": "pdf",
        "application/msword": "doc",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
        "application/vnd.ms-excel": "xls",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
        "text/plain": "txt",
        "text/markdown": "md",
    }
    if content_type in type_map:
        return type_map[content_type]

    # Fall back to extension
    if "." in filename:
        return filename.rsplit(".", 1)[-1].lower()

    return "unknown"


def find_document_by_content_hash(
    tenant_id: str,
    user_id: str,
    content_hash: str,
) -> Optional[dict]:
    """Find a document by its content hash (for deduplication).

    Args:
        tenant_id: Tenant identifier
        user_id: User identifier
        content_hash: SHA256 hash of content

    Returns:
        Document dict if found, None otherwise
    """
    documents = list_user_documents(tenant_id, user_id, scope="all", limit=500)
    for doc in documents:
        if doc.get("content_hash") == content_hash:
            return doc
    return None


def find_document_by_s3_key(
    tenant_id: str,
    user_id: str,
    s3_key: str,
) -> Optional[dict]:
    """Find a document by its current S3 key for a given user."""
    documents = list_user_documents(tenant_id, user_id, scope="all", limit=500)
    for doc in documents:
        if doc.get("s3_key") == s3_key or doc.get("markdown_s3_key") == s3_key:
            return doc
    return None
