"""
audit_store.py — Write-only AUDIT# entity for the EAGLE single-table.

Entity layout:
    PK:  AUDIT#{tenant_id}
    SK:  AUDIT#{ISO_timestamp}#{entity_type}#{entity_name}

TTL: 7 years from write time (epoch seconds stored in `ttl` attribute).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any

import boto3
from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy DynamoDB singletons (same pattern as plugin_store.py)
# ---------------------------------------------------------------------------

_dynamodb = None
_table = None


def _get_dynamodb():
    global _dynamodb
    if _dynamodb is None:
        region = os.environ.get("AWS_REGION", "us-east-1")
        _dynamodb = boto3.resource("dynamodb", region_name=region)
    return _dynamodb


def _get_table():
    global _table
    if _table is None:
        table_name = os.environ.get("TABLE_NAME", "eagle")
        _table = _get_dynamodb().Table(table_name)
    return _table


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seven_year_ttl() -> int:
    """Return Unix epoch seconds 7 years from now."""
    return int((datetime.utcnow() + timedelta(days=365 * 7)).timestamp())


def _now_iso() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def _to_json_str(value: Any) -> str | None:
    """Coerce a value to a JSON string, or return None if value is None."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, default=str)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def write_audit(
    tenant_id: str,
    entity_type: str,
    entity_name: str,
    event_type: str,
    actor_user_id: str,
    before: Any = None,
    after: Any = None,
    metadata: dict | None = None,
) -> dict:
    """Write an immutable audit record and return the stored item.

    Parameters
    ----------
    tenant_id:     Tenant owning this event.
    entity_type:   Kind of thing that changed, e.g. "agent", "skill", "config".
    entity_name:   Specific name/id of the entity, e.g. "supervisor".
    event_type:    What happened, e.g. "RELOAD", "CREATE", "DELETE", "UPDATE".
    actor_user_id: User or system process that triggered the event.
    before:        Optional snapshot before the change (str or JSON-serialisable).
    after:         Optional snapshot after the change (str or JSON-serialisable).
    metadata:      Arbitrary key/value dict for extra context.
    """
    occurred_at = _now_iso()
    pk = f"AUDIT#{tenant_id}"
    sk = f"AUDIT#{occurred_at}#{entity_type}#{entity_name}"

    item: dict[str, Any] = {
        "PK": pk,
        "SK": sk,
        "event_type": event_type,
        "entity_type": entity_type,
        "entity_name": entity_name,
        "actor_user_id": actor_user_id,
        "tenant_id": tenant_id,
        "occurred_at": occurred_at,
        "metadata": metadata or {},
        "ttl": _seven_year_ttl(),
    }

    before_str = _to_json_str(before)
    after_str = _to_json_str(after)
    if before_str is not None:
        item["before"] = before_str
    if after_str is not None:
        item["after"] = after_str

    try:
        _get_table().put_item(Item=item)
        logger.info(
            "audit_store: wrote %s event for %s/%s (tenant=%s actor=%s)",
            event_type,
            entity_type,
            entity_name,
            tenant_id,
            actor_user_id,
        )
    except (ClientError, BotoCoreError) as exc:
        logger.error("audit_store: failed to write audit event: %s", exc)
        raise

    return item


def list_audit_events(
    tenant_id: str,
    entity_type: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Query audit events for a tenant, newest first.

    Parameters
    ----------
    tenant_id:   Tenant whose audit log to read.
    entity_type: If provided, filter to events where entity_type matches.
    limit:       Maximum number of items to return (default 50).
    """
    pk = f"AUDIT#{tenant_id}"

    query_kwargs: dict[str, Any] = {
        "KeyConditionExpression": Key("PK").eq(pk) & Key("SK").begins_with("AUDIT#"),
        "ScanIndexForward": False,  # newest first
        "Limit": limit,
    }

    if entity_type is not None:
        query_kwargs["FilterExpression"] = Attr("entity_type").eq(entity_type)

    try:
        response = _get_table().query(**query_kwargs)
        items: list[dict] = response.get("Items", [])
        logger.debug(
            "audit_store: retrieved %d events for tenant=%s entity_type=%s",
            len(items),
            tenant_id,
            entity_type,
        )
        return items
    except (ClientError, BotoCoreError) as exc:
        logger.error("audit_store: failed to list audit events: %s", exc)
        raise
