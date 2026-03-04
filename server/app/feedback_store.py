"""
feedback_store.py — Write feedback submissions to the EAGLE single-table.

Entity layout:
    PK:     FEEDBACK#{tenant_id}
    SK:     FEEDBACK#{ISO_timestamp}#{feedback_id}
    GSI1PK: TENANT#{tenant_id}
    GSI1SK: FEEDBACK#{created_at}

TTL: 7 years from write time (epoch seconds stored in `ttl` attribute).
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy DynamoDB singletons (same pattern as audit_store.py)
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


_TYPE_KEYWORDS: dict[str, list[str]] = {
    "bug":            ["bug", "error", "broken", "doesn't work", "not working", "crash", "fail", "issue"],
    "suggestion":     ["suggest", "feature", "improve", "wish", "could", "should", "would be better"],
    "praise":         ["great", "love", "excellent", "perfect", "helpful", "amazing", "good", "thank"],
    "incorrect_info": ["incorrect", "false", "inaccurate", "wrong", "misinformation", "misleading"],
}


def _detect_feedback_type(text: str) -> str:
    lower = text.lower()
    for ftype, keywords in _TYPE_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return ftype
    return "general"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def write_feedback(
    tenant_id: str,
    user_id: str,
    tier: str,
    session_id: str,
    feedback_text: str,
    conversation_snapshot: str,
    cloudwatch_logs: str,
) -> dict:
    """Write a feedback record and return the stored item."""
    feedback_id = str(uuid.uuid4())
    created_at = _now_iso()
    pk = f"FEEDBACK#{tenant_id}"
    sk = f"FEEDBACK#{created_at}#{feedback_id}"

    item: dict[str, Any] = {
        "PK": pk,
        "SK": sk,
        "GSI1PK": f"TENANT#{tenant_id}",
        "GSI1SK": f"FEEDBACK#{created_at}",
        "feedback_id": feedback_id,
        "user_id": user_id,
        "tenant_id": tenant_id,
        "tier": tier,
        "session_id": session_id,
        "feedback_text": feedback_text,
        "feedback_type": _detect_feedback_type(feedback_text),
        "conversation_snapshot": conversation_snapshot,
        "cloudwatch_logs": cloudwatch_logs,
        "created_at": created_at,
        "ttl": _seven_year_ttl(),
    }

    try:
        _get_table().put_item(Item=item)
        logger.info(
            "feedback_store: wrote feedback %s (type=%s tenant=%s user=%s session=%s)",
            feedback_id,
            item["feedback_type"],
            tenant_id,
            user_id,
            session_id,
        )
    except (ClientError, BotoCoreError) as exc:
        logger.error("feedback_store: failed to write feedback: %s", exc)
        raise

    return item


def list_feedback(tenant_id: str, limit: int = 50) -> list[dict]:
    """Query feedback for a tenant, newest first."""
    pk = f"FEEDBACK#{tenant_id}"
    try:
        response = _get_table().query(
            KeyConditionExpression=Key("PK").eq(pk) & Key("SK").begins_with("FEEDBACK#"),
            ScanIndexForward=False,
            Limit=limit,
        )
        return response.get("Items", [])
    except (ClientError, BotoCoreError) as exc:
        logger.error("feedback_store: failed to list feedback: %s", exc)
        raise
