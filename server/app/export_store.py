"""
export_store.py — EXPORT# entity for tracking package export events.

Entity layout:
    PK:  EXPORT#{tenant_id}
    SK:  EXPORT#{ISO_timestamp}#{export_id}

TTL: 1 year from write time.
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Optional

from boto3.dynamodb.conditions import Key
from botocore.exceptions import BotoCoreError, ClientError

from .db_client import get_table, now_iso, ttl_timestamp

logger = logging.getLogger("eagle.exports")


def _one_year_ttl() -> int:
    return ttl_timestamp(days=365)


def _serialize(item: dict) -> dict:
    result = {}
    for k, v in item.items():
        if isinstance(v, Decimal):
            result[k] = float(v) if v % 1 else int(v)
        else:
            result[k] = v
    return result


def record_export(
    tenant_id: str,
    package_id: str,
    user_id: str,
    export_format: str,
    doc_types_included: list[str],
    file_size: int,
) -> dict:
    """Record a package export event. Returns the stored item."""
    ts = now_iso()
    export_id = f"EXP-{uuid.uuid4().hex[:8]}"

    item = {
        "PK": f"EXPORT#{tenant_id}",
        "SK": f"EXPORT#{ts}#{export_id}",
        "export_id": export_id,
        "tenant_id": tenant_id,
        "package_id": package_id,
        "user_id": user_id,
        "export_format": export_format,
        "doc_types_included": doc_types_included,
        "file_size": file_size,
        "created_at": ts,
        "ttl": _one_year_ttl(),
    }

    try:
        get_table().put_item(Item=item)
        logger.info(
            "Recorded export %s for package %s (tenant=%s)",
            export_id, package_id, tenant_id,
        )
    except (ClientError, BotoCoreError):
        logger.exception("Failed to record export %s", export_id)
        raise

    return _serialize(item)


def list_exports(
    tenant_id: str,
    package_id: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """List export history for a tenant, newest first.

    When package_id is provided, filters results to that package.
    """
    try:
        resp = get_table().query(
            KeyConditionExpression=Key("PK").eq(f"EXPORT#{tenant_id}")
            & Key("SK").begins_with("EXPORT#"),
            ScanIndexForward=False,
            Limit=limit,
        )
    except (ClientError, BotoCoreError):
        logger.exception("list_exports failed (tenant=%s)", tenant_id)
        raise

    items = [_serialize(item) for item in resp.get("Items", [])]

    if package_id:
        items = [item for item in items if item.get("package_id") == package_id]

    return items
