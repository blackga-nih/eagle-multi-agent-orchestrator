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
import uuid
from typing import Any

from boto3.dynamodb.conditions import Key
from botocore.exceptions import BotoCoreError, ClientError

from .db_client import get_table, now_iso, ttl_timestamp

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seven_year_ttl() -> int:
    """Return Unix epoch seconds 7 years from now."""
    return ttl_timestamp(days=365 * 7)


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
    page: str = "",
    last_message_id: str = "",
) -> dict:
    """Write a feedback record and return the stored item."""
    feedback_id = str(uuid.uuid4())
    created_at = now_iso()
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
        "page": page,
        "last_message_id": last_message_id,
        "created_at": created_at,
        "ttl": _seven_year_ttl(),
    }

    try:
        get_table().put_item(Item=item)
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
        response = get_table().query(
            KeyConditionExpression=Key("PK").eq(pk) & Key("SK").begins_with("FEEDBACK#"),
            ScanIndexForward=False,
            Limit=limit,
        )
        return response.get("Items", [])
    except (ClientError, BotoCoreError) as exc:
        logger.error("feedback_store: failed to list feedback: %s", exc)
        raise


def write_message_feedback(
    tenant_id: str,
    user_id: str,
    session_id: str,
    message_id: str,
    feedback_type: str,  # "thumbs_up" | "thumbs_down"
    comment: str = "",
) -> dict:
    """Write per-message feedback (thumbs up/down) and return the stored item."""
    feedback_id = str(uuid.uuid4())
    created_at = now_iso()
    pk = f"FEEDBACK#{tenant_id}"
    sk = f"MSG_FEEDBACK#{session_id}#{message_id}"

    item: dict[str, Any] = {
        "PK": pk,
        "SK": sk,
        "GSI1PK": f"TENANT#{tenant_id}",
        "GSI1SK": f"MSG_FEEDBACK#{created_at}",
        "feedback_id": feedback_id,
        "user_id": user_id,
        "tenant_id": tenant_id,
        "session_id": session_id,
        "message_id": message_id,
        "feedback_type": feedback_type,
        "comment": comment,
        "created_at": created_at,
        "ttl": _seven_year_ttl(),
    }

    try:
        get_table().put_item(Item=item)
        logger.info(
            "feedback_store: wrote message feedback %s (type=%s tenant=%s msg=%s)",
            feedback_id, feedback_type, tenant_id, message_id,
        )
    except (ClientError, BotoCoreError) as exc:
        logger.error("feedback_store: failed to write message feedback: %s", exc)
        raise

    return item


def list_message_feedback(tenant_id: str, limit: int = 100) -> list[dict]:
    """Query message-level feedback for a tenant, newest first."""
    pk = f"FEEDBACK#{tenant_id}"
    try:
        response = get_table().query(
            KeyConditionExpression=Key("PK").eq(pk) & Key("SK").begins_with("MSG_FEEDBACK#"),
            ScanIndexForward=False,
            Limit=limit,
        )
        return response.get("Items", [])
    except (ClientError, BotoCoreError) as exc:
        logger.error("feedback_store: failed to list message feedback: %s", exc)
        raise


def get_message_feedback_summary(tenant_id: str) -> dict:
    """Get aggregate message feedback stats for a tenant."""
    items = list_message_feedback(tenant_id, limit=500)
    total = len(items)
    thumbs_up = sum(1 for i in items if i.get("feedback_type") == "thumbs_up")
    thumbs_down = total - thumbs_up
    return {
        "total": total,
        "thumbs_up": thumbs_up,
        "thumbs_down": thumbs_down,
        "thumbs_up_pct": round(thumbs_up / total * 100, 1) if total else 0,
    }
