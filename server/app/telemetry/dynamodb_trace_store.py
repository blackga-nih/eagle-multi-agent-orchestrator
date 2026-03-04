"""
DynamoDB persistence for trace summaries.

Uses the existing 'eagle' table with TRACE# partition key prefix.
No new tables required.
"""
import json
import logging
import os
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any

import boto3
from botocore.exceptions import ClientError, BotoCoreError

logger = logging.getLogger("eagle.telemetry.store")

TABLE_NAME = os.getenv("EAGLE_SESSIONS_TABLE", "eagle")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
TRACE_TTL_DAYS = int(os.getenv("TRACE_TTL_DAYS", "30"))

_dynamodb = None


def _get_table():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
    return _dynamodb.Table(TABLE_NAME)


def store_trace(summary: dict, spans: list, trace_json: list = None) -> bool:
    """Persist a trace summary + spans to DynamoDB.

    Key schema:
        PK: TRACE#{tenant_id}
        SK: TRACE#{date}#{trace_id}
    GSI1:
        GSI1PK: SESSION#{session_id}
        GSI1SK: TRACE#{trace_id}
    """
    trace_id = summary.get("trace_id", "unknown")
    tenant_id = summary.get("tenant_id", "default")
    session_id = summary.get("session_id", "unknown")
    now = datetime.utcnow()
    ttl = int((now + timedelta(days=TRACE_TTL_DAYS)).timestamp())

    item = {
        "PK": f"TRACE#{tenant_id}",
        "SK": f"TRACE#{now.strftime('%Y-%m-%d')}#{trace_id}",
        "trace_id": trace_id,
        "tenant_id": tenant_id,
        "user_id": summary.get("user_id", "anonymous"),
        "session_id": session_id,
        "created_at": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "duration_ms": summary.get("duration_ms", 0),
        "total_input_tokens": summary.get("total_input_tokens", 0),
        "total_output_tokens": summary.get("total_output_tokens", 0),
        "total_cost_usd": Decimal(str(summary.get("total_cost_usd", 0))),
        "tools_called": summary.get("tools_called", []),
        "agents_delegated": summary.get("agents_delegated", []),
        "span_count": len(spans),
        "spans": json.dumps(spans, default=str),
        "status": "error" if summary.get("error") else "success",
        "ttl": ttl,
        # GSI for lookup by session
        "GSI1PK": f"SESSION#{session_id}",
        "GSI1SK": f"TRACE#{trace_id}",
    }

    # Optionally store full trace (truncated to stay under 400KB DynamoDB limit)
    if trace_json:
        trace_str = json.dumps(trace_json, default=str)
        if len(trace_str) < 350_000:  # Leave headroom
            item["trace_json"] = trace_str

    try:
        table = _get_table()
        table.put_item(Item=item)
        logger.info("Stored trace %s for tenant %s", trace_id, tenant_id)
        return True
    except (ClientError, BotoCoreError) as e:
        logger.error("Failed to store trace %s: %s", trace_id, e)
        return False


def get_traces(
    tenant_id: str,
    limit: int = 50,
    from_date: str = None,
) -> List[Dict[str, Any]]:
    """Fetch recent traces for a tenant."""
    try:
        table = _get_table()

        key_condition = "PK = :pk"
        expr_values: dict = {":pk": f"TRACE#{tenant_id}"}

        if from_date:
            key_condition += " AND SK >= :from_sk"
            expr_values[":from_sk"] = f"TRACE#{from_date}"

        response = table.query(
            KeyConditionExpression=key_condition,
            ExpressionAttributeValues=expr_values,
            ScanIndexForward=False,
            Limit=limit,
            ProjectionExpression=(
                "trace_id, tenant_id, user_id, session_id, created_at, "
                "duration_ms, total_input_tokens, total_output_tokens, "
                "total_cost_usd, tools_called, agents_delegated, span_count, #s"
            ),
            ExpressionAttributeNames={"#s": "status"},
        )

        return [_serialize(item) for item in response.get("Items", [])]
    except (ClientError, BotoCoreError) as e:
        logger.error("Failed to fetch traces for %s: %s", tenant_id, e)
        return []


def get_trace_detail(tenant_id: str, trace_id: str, date: str) -> Optional[Dict]:
    """Fetch a single trace with full spans and trace_json."""
    try:
        table = _get_table()
        response = table.get_item(
            Key={
                "PK": f"TRACE#{tenant_id}",
                "SK": f"TRACE#{date}#{trace_id}",
            }
        )
        item = response.get("Item")
        if not item:
            return None

        result = _serialize(item)
        # Parse spans back from JSON
        if "spans" in result and isinstance(result["spans"], str):
            result["spans"] = json.loads(result["spans"])
        if "trace_json" in result and isinstance(result["trace_json"], str):
            result["trace_json"] = json.loads(result["trace_json"])
        return result
    except (ClientError, BotoCoreError) as e:
        logger.error("Failed to fetch trace %s: %s", trace_id, e)
        return None


def get_traces_by_session(session_id: str, limit: int = 20) -> List[Dict]:
    """Fetch traces for a specific session.

    Tries GSI1 first (fast lookup). If the GSI doesn't exist, falls back
    to a table scan filtered by session_id (slower but works without GSI).
    """
    try:
        table = _get_table()
        try:
            response = table.query(
                IndexName="GSI1",
                KeyConditionExpression="GSI1PK = :pk AND begins_with(GSI1SK, :prefix)",
                ExpressionAttributeValues={
                    ":pk": f"SESSION#{session_id}",
                    ":prefix": "TRACE#",
                },
                ScanIndexForward=False,
                Limit=limit,
            )
            return [_serialize(item) for item in response.get("Items", [])]
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "ValidationException":
                # GSI1 doesn't exist — fall back to scan
                logger.info("GSI1 not found, falling back to scan for session %s", session_id)
                response = table.scan(
                    FilterExpression="session_id = :sid AND begins_with(PK, :prefix)",
                    ExpressionAttributeValues={
                        ":sid": session_id,
                        ":prefix": "TRACE#",
                    },
                    Limit=limit,
                )
                return [_serialize(item) for item in response.get("Items", [])]
            raise
    except (ClientError, BotoCoreError) as e:
        logger.error("Failed to fetch traces for session %s: %s", session_id, e)
        return []


def _serialize(item: dict) -> dict:
    """Convert DynamoDB Decimal types to Python floats/ints."""
    result = {}
    for k, v in item.items():
        if isinstance(v, Decimal):
            result[k] = float(v) if v % 1 else int(v)
        else:
            result[k] = v
    return result
