"""Package attachment persistence for uploaded source material.

Attachments are package-scoped uploads such as technical requirements,
screenshots, prior SOWs, quotes, and other supporting files. They are distinct
from canonical package documents, which remain versioned in
``package_document_store.py``.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError

from .db_client import get_table, item_to_dict, now_iso

logger = logging.getLogger("eagle.package_attachment_store")


def _pk(tenant_id: str) -> str:
    return f"ATTACHMENT#{tenant_id}"


def _sk(package_id: str, attachment_id: str) -> str:
    return f"PACKAGE#{package_id}#{attachment_id}"


def _sk_prefix(package_id: str) -> str:
    return f"PACKAGE#{package_id}#"


def _to_dynamodb_value(value: Any) -> Any:
    """Normalize values for DynamoDB writes."""
    from decimal import Decimal

    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, list):
        return [_to_dynamodb_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _to_dynamodb_value(v) for k, v in value.items()}
    return value


def _infer_file_type(content_type: str, filename: str) -> str:
    type_map = {
        "application/pdf": "pdf",
        "application/msword": "doc",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
        "application/vnd.ms-excel": "xls",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
        "text/plain": "txt",
        "text/markdown": "md",
        "image/png": "png",
        "image/jpeg": "jpg",
    }
    if content_type in type_map:
        return type_map[content_type]
    if "." in filename:
        return filename.rsplit(".", 1)[-1].lower()
    return "unknown"


def create_attachment(
    tenant_id: str,
    package_id: str,
    user_id: str,
    s3_bucket: str,
    s3_key: str,
    filename: str,
    original_filename: str,
    content_type: str,
    size_bytes: int,
    title: Optional[str] = None,
    attachment_type: str = "document",
    doc_type: Optional[str] = None,
    linked_doc_type: Optional[str] = None,
    category: str = "other",
    usage: str = "reference",
    include_in_zip: bool = True,
    classification: Optional[dict] = None,
    classification_source: Optional[str] = None,
    markdown_s3_key: Optional[str] = None,
    extracted_text: Optional[str] = None,
    session_id: Optional[str] = None,
    attachment_id: Optional[str] = None,
) -> dict:
    table = get_table()
    now = now_iso().replace("+00:00", "Z")
    attachment_id = attachment_id or str(uuid.uuid4())

    item: dict[str, Any] = {
        "PK": _pk(tenant_id),
        "SK": _sk(package_id, attachment_id),
        "entity_type": "package_attachment",
        "attachment_id": attachment_id,
        "package_id": package_id,
        "tenant_id": tenant_id,
        "owner_user_id": user_id,
        "attachment_type": attachment_type,
        "doc_type": doc_type,
        "linked_doc_type": linked_doc_type,
        "category": category,
        "usage": usage,
        "include_in_zip": include_in_zip,
        "title": title or filename,
        "display_name": title or filename,
        "filename": filename,
        "original_filename": original_filename,
        "file_type": _infer_file_type(content_type, filename),
        "content_type": content_type,
        "size_bytes": size_bytes,
        "s3_bucket": s3_bucket,
        "s3_key": s3_key,
        "created_at": now,
        "updated_at": now,
    }
    if classification:
        item["classification"] = classification
        item["classification_confidence"] = classification.get("confidence")
    if classification_source:
        item["classification_source"] = classification_source
    if markdown_s3_key:
        item["markdown_s3_key"] = markdown_s3_key
    if extracted_text:
        item["extracted_text"] = extracted_text
    if session_id:
        item["session_id"] = session_id

    table.put_item(Item=_to_dynamodb_value(item))
    return item_to_dict(item)


def get_attachment(tenant_id: str, package_id: str, attachment_id: str) -> Optional[dict]:
    table = get_table()
    try:
        response = table.get_item(
            Key={"PK": _pk(tenant_id), "SK": _sk(package_id, attachment_id)}
        )
        item = response.get("Item")
        return item_to_dict(item) if item else None
    except ClientError as exc:
        logger.error("Failed to get package attachment %s: %s", attachment_id, exc)
        raise


def list_package_attachments(
    tenant_id: str,
    package_id: str,
    include_zip_only: Optional[bool] = None,
    limit: int = 100,
) -> list[dict]:
    table = get_table()
    try:
        response = table.query(
            KeyConditionExpression=(
                Key("PK").eq(_pk(tenant_id))
                & Key("SK").begins_with(_sk_prefix(package_id))
            ),
            Limit=limit,
            ScanIndexForward=False,
        )
        items = [item_to_dict(item) for item in response.get("Items", [])]
        if include_zip_only is True:
            items = [item for item in items if item.get("include_in_zip") is True]
        return items
    except ClientError as exc:
        logger.error("Failed to list package attachments for %s: %s", package_id, exc)
        raise


def list_user_package_attachments(
    tenant_id: str,
    user_id: str,
    package_id: Optional[str] = None,
    limit: int = 100,
) -> list[dict]:
    """List package attachments owned by a user, optionally filtered by package."""
    table = get_table()
    try:
        response = table.query(
            KeyConditionExpression=Key("PK").eq(_pk(tenant_id)),
            ScanIndexForward=False,
            Limit=max(limit * 3, limit),
        )
        items = [item_to_dict(item) for item in response.get("Items", [])]
        filtered = [
            item
            for item in items
            if item.get("owner_user_id") == user_id
            and (package_id is None or item.get("package_id") == package_id)
        ]
        return filtered[:limit]
    except ClientError as exc:
        logger.error("Failed to list user package attachments: %s", exc)
        raise


def find_attachment_by_id(
    tenant_id: str,
    attachment_id: str,
    owner_user_id: Optional[str] = None,
) -> Optional[dict]:
    """Find an attachment by ID across packages within a tenant."""
    table = get_table()
    try:
        response = table.query(
            KeyConditionExpression=Key("PK").eq(_pk(tenant_id)),
            FilterExpression=Attr("attachment_id").eq(attachment_id),
            Limit=25,
        )
        items = [item_to_dict(item) for item in response.get("Items", [])]
        if owner_user_id:
            items = [item for item in items if item.get("owner_user_id") == owner_user_id]
        return items[0] if items else None
    except ClientError as exc:
        logger.error("Failed to find package attachment %s: %s", attachment_id, exc)
        raise


def update_attachment(
    tenant_id: str,
    package_id: str,
    attachment_id: str,
    updates: dict[str, Any],
) -> Optional[dict]:
    table = get_table()
    update_parts = ["updated_at = :now"]
    expr_values: dict[str, Any] = {":now": now_iso().replace("+00:00", "Z")}
    expr_names: dict[str, str] = {}

    allowed_fields = {
        "title",
        "display_name",
        "doc_type",
        "linked_doc_type",
        "category",
        "usage",
        "include_in_zip",
        "classification_source",
    }

    for key, value in updates.items():
        if key not in allowed_fields:
            continue
        attr_name = f"#{key}" if key in {"usage"} else key
        if attr_name.startswith("#"):
            expr_names[attr_name] = key
        update_parts.append(f"{attr_name} = :{key}")
        expr_values[f":{key}"] = _to_dynamodb_value(value)

    if len(update_parts) == 1:
        return get_attachment(tenant_id, package_id, attachment_id)

    try:
        response = table.update_item(
            Key={"PK": _pk(tenant_id), "SK": _sk(package_id, attachment_id)},
            UpdateExpression="SET " + ", ".join(update_parts),
            ExpressionAttributeValues=expr_values,
            ExpressionAttributeNames=expr_names if expr_names else None,
            ConditionExpression=Attr("PK").exists(),
            ReturnValues="ALL_NEW",
        )
        return item_to_dict(response.get("Attributes", {}))
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return None
        logger.error("Failed to update attachment %s: %s", attachment_id, exc)
        raise


def delete_attachment(tenant_id: str, package_id: str, attachment_id: str) -> bool:
    table = get_table()
    try:
        response = table.delete_item(
            Key={"PK": _pk(tenant_id), "SK": _sk(package_id, attachment_id)},
            ConditionExpression=Attr("PK").exists(),
            ReturnValues="ALL_OLD",
        )
        return response.get("Attributes") is not None
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        logger.error("Failed to delete attachment %s: %s", attachment_id, exc)
        raise
