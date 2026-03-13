"""Feedback Store -- DynamoDB-backed FEEDBACK# entity for user feedback.

Entity format:
    PK:  FEEDBACK#{tenant_id}
    SK:  FEEDBACK#{iso_timestamp}#{feedback_id}

90-day TTL auto-expiry.
"""
import os
import uuid
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from boto3.dynamodb.conditions import Key

logger = logging.getLogger("eagle.feedback_store")

TABLE_NAME = os.getenv("EAGLE_SESSIONS_TABLE", "eagle")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

_dynamodb = None


def _get_dynamodb():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
    return _dynamodb


def _get_table():
    return _get_dynamodb().Table(TABLE_NAME)


def create_feedback(
    tenant_id: str,
    user_id: str,
    rating: int = 0,
    page: str = "",
    feedback_type: Optional[str] = None,
    comment: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a feedback record with 90-day TTL."""
    feedback_id = str(uuid.uuid4())
    now = datetime.utcnow()
    iso_ts = now.isoformat()
    ttl = int((now + timedelta(days=90)).timestamp())

    item: Dict[str, Any] = {
        "PK": f"FEEDBACK#{tenant_id}",
        "SK": f"FEEDBACK#{iso_ts}#{feedback_id}",
        "feedback_id": feedback_id,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "page": page,
        "created_at": iso_ts,
        "ttl": ttl,
    }
    if rating:
        item["rating"] = rating
    if feedback_type:
        item["feedback_type"] = feedback_type
    if comment:
        item["comment"] = comment
    if session_id:
        item["session_id"] = session_id

    try:
        _get_table().put_item(Item=item)
        logger.info("feedback_store.create: [%s] rating=%s page=%s", tenant_id, rating, page)
    except (ClientError, BotoCoreError) as exc:
        logger.error("feedback_store.create failed [%s]: %s", tenant_id, exc)
        raise

    return item


def write_feedback(
    tenant_id: str,
    user_id: str,
    tier: str = "",
    session_id: str = "",
    feedback_text: str = "",
    feedback_type: Optional[str] = None,
    conversation_snapshot: str = "",
    cloudwatch_logs: str = "",
    page: str = "",
    last_message_id: str = "",
) -> Dict[str, Any]:
    """Rich feedback record — maps to create_feedback() with extended fields."""
    item = create_feedback(
        tenant_id=tenant_id,
        user_id=user_id,
        page=page,
        comment=feedback_text or None,
        feedback_type=feedback_type,
        session_id=session_id or None,
    )
    # Store extended fields if provided
    if tier or conversation_snapshot or cloudwatch_logs or last_message_id:
        updates: Dict[str, Any] = {}
        if tier:
            updates["tier"] = tier
        if conversation_snapshot:
            updates["conversation_snapshot"] = conversation_snapshot
        if cloudwatch_logs:
            updates["cloudwatch_logs"] = cloudwatch_logs
        if last_message_id:
            updates["last_message_id"] = last_message_id
        if updates:
            try:
                expr = "SET " + ", ".join(f"#{k} = :{k}" for k in updates)
                _get_table().update_item(
                    Key={"PK": item["PK"], "SK": item["SK"]},
                    UpdateExpression=expr,
                    ExpressionAttributeNames={f"#{k}": k for k in updates},
                    ExpressionAttributeValues={f":{k}": v for k, v in updates.items()},
                )
                item.update(updates)
            except (ClientError, BotoCoreError) as exc:
                logger.warning("feedback_store.write_feedback: extended update failed (non-fatal): %s", exc)
    return item


def list_feedback(tenant_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """List feedback for a tenant, newest first."""
    try:
        response = _get_table().query(
            KeyConditionExpression=(
                Key("PK").eq(f"FEEDBACK#{tenant_id}")
                & Key("SK").begins_with("FEEDBACK#")
            ),
            ScanIndexForward=False,
            Limit=limit,
        )
        return [dict(item) for item in response.get("Items", [])]
    except (ClientError, BotoCoreError) as exc:
        logger.error("feedback_store.list failed [%s]: %s", tenant_id, exc)
        return []
