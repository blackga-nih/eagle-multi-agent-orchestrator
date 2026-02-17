"""
Session Store with DynamoDB Persistence
Handles conversation history, session resume, and cross-device sync.
"""
import os
import json
import time
import logging
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError, BotoCoreError

logger = logging.getLogger("eagle.sessions")

# ── Configuration ────────────────────────────────────────────────────
TABLE_NAME = os.getenv("EAGLE_SESSIONS_TABLE", "eagle")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
SESSION_TTL_DAYS = int(os.getenv("SESSION_TTL_DAYS", "30"))

# ── DynamoDB Client ──────────────────────────────────────────────────
_dynamodb = None


def _get_dynamodb():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
    return _dynamodb


def _get_table():
    return _get_dynamodb().Table(TABLE_NAME)


# ── In-Memory Cache ──────────────────────────────────────────────────
# Local cache for fast reads, with write-through to DynamoDB
_session_cache: Dict[str, Dict] = {}
_cache_ttl: Dict[str, float] = {}
CACHE_DURATION_SECONDS = 300  # 5 minutes


def _is_cache_valid(session_id: str) -> bool:
    if session_id not in _cache_ttl:
        return False
    return time.time() < _cache_ttl[session_id]


def _update_cache(session_id: str, data: Dict):
    _session_cache[session_id] = data
    _cache_ttl[session_id] = time.time() + CACHE_DURATION_SECONDS


def _invalidate_cache(session_id: str):
    _session_cache.pop(session_id, None)
    _cache_ttl.pop(session_id, None)


# ── Session Key Helpers ──────────────────────────────────────────────

def build_session_key(tenant_id: str, user_id: str, session_id: str) -> str:
    """Build a composite session key for multi-tenant isolation."""
    return f"SESSION#{tenant_id}#{user_id}#{session_id}"


def parse_session_key(key: str) -> Dict[str, str]:
    """Parse a composite session key into components."""
    parts = key.split("#")
    if len(parts) >= 4 and parts[0] == "SESSION":
        return {
            "tenant_id": parts[1],
            "user_id": parts[2],
            "session_id": parts[3],
        }
    return {"session_id": key}


def generate_session_id(user_id: str = "anonymous") -> str:
    """Generate a unique session ID."""
    import uuid
    timestamp = int(time.time() * 1000)
    unique = uuid.uuid4().hex[:8]
    return f"s-{timestamp}-{unique}"


# ── Session CRUD Operations ──────────────────────────────────────────

def create_session(
    tenant_id: str = "default",
    user_id: str = "anonymous",
    session_id: Optional[str] = None,
    title: Optional[str] = None,
    metadata: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Create a new session in DynamoDB.
    
    Returns the session record.
    """
    if not session_id:
        session_id = generate_session_id(user_id)
    
    now = datetime.utcnow()
    ttl = int((now + timedelta(days=SESSION_TTL_DAYS)).timestamp())
    
    session = {
        "PK": f"SESSION#{tenant_id}#{user_id}",
        "SK": f"SESSION#{session_id}",
        "session_id": session_id,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "title": title or "New Conversation",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "message_count": 0,
        "total_tokens": 0,
        "status": "active",
        "metadata": metadata or {},
        "ttl": ttl,
        # GSI for listing sessions by tenant
        "GSI1PK": f"TENANT#{tenant_id}",
        "GSI1SK": f"SESSION#{now.isoformat()}",
    }
    
    try:
        table = _get_table()
        table.put_item(Item=session)
        _update_cache(session_id, session)
        logger.info("Created session: %s for user %s", session_id, user_id)
        return _serialize_item(session)
    except (ClientError, BotoCoreError) as e:
        logger.error("Failed to create session: %s", e)
        # Fall back to in-memory only
        _update_cache(session_id, session)
        return _serialize_item(session)


def get_session(
    session_id: str,
    tenant_id: str = "default",
    user_id: str = "anonymous"
) -> Optional[Dict[str, Any]]:
    """
    Get a session by ID.
    
    Checks cache first, then DynamoDB.
    """
    # Check cache
    if _is_cache_valid(session_id):
        return _serialize_item(_session_cache[session_id])
    
    try:
        table = _get_table()
        response = table.get_item(
            Key={
                "PK": f"SESSION#{tenant_id}#{user_id}",
                "SK": f"SESSION#{session_id}",
            }
        )
        item = response.get("Item")
        if item:
            _update_cache(session_id, item)
            return _serialize_item(item)
        return None
    except (ClientError, BotoCoreError) as e:
        logger.error("Failed to get session: %s", e)
        # Return cached if available
        if session_id in _session_cache:
            return _serialize_item(_session_cache[session_id])
        return None


def update_session(
    session_id: str,
    tenant_id: str = "default",
    user_id: str = "anonymous",
    updates: Optional[Dict] = None
) -> Optional[Dict[str, Any]]:
    """
    Update session metadata.
    """
    if not updates:
        return get_session(session_id, tenant_id, user_id)
    
    now = datetime.utcnow().isoformat()
    
    # Build update expression
    update_parts = ["#upd = :updval"]
    expr_names = {"#upd": "updated_at"}
    expr_values = {":updval": now}
    
    for i, (k, v) in enumerate(updates.items()):
        if k in ("PK", "SK", "session_id", "tenant_id", "user_id"):
            continue
        alias = f"#attr{i}"
        val_alias = f":val{i}"
        update_parts.append(f"{alias} = {val_alias}")
        expr_names[alias] = k
        expr_values[val_alias] = v
    
    try:
        table = _get_table()
        response = table.update_item(
            Key={
                "PK": f"SESSION#{tenant_id}#{user_id}",
                "SK": f"SESSION#{session_id}",
            },
            UpdateExpression="SET " + ", ".join(update_parts),
            ExpressionAttributeNames=expr_names,
            ExpressionAttributeValues=expr_values,
            ReturnValues="ALL_NEW"
        )
        item = response.get("Attributes", {})
        _update_cache(session_id, item)
        return _serialize_item(item)
    except (ClientError, BotoCoreError) as e:
        logger.error("Failed to update session: %s", e)
        return None


def delete_session(
    session_id: str,
    tenant_id: str = "default",
    user_id: str = "anonymous"
) -> bool:
    """
    Delete a session and its messages.
    """
    try:
        table = _get_table()
        
        # Delete session record
        table.delete_item(
            Key={
                "PK": f"SESSION#{tenant_id}#{user_id}",
                "SK": f"SESSION#{session_id}",
            }
        )
        
        # Delete all messages (batch delete)
        response = table.query(
            KeyConditionExpression="PK = :pk AND begins_with(SK, :sk_prefix)",
            ExpressionAttributeValues={
                ":pk": f"SESSION#{tenant_id}#{user_id}",
                ":sk_prefix": f"MSG#{session_id}#",
            },
            ProjectionExpression="PK, SK"
        )
        
        with table.batch_writer() as batch:
            for item in response.get("Items", []):
                batch.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})
        
        _invalidate_cache(session_id)
        logger.info("Deleted session: %s", session_id)
        return True
    except (ClientError, BotoCoreError) as e:
        logger.error("Failed to delete session: %s", e)
        return False


def list_sessions(
    tenant_id: str = "default",
    user_id: str = "anonymous",
    limit: int = 50,
    status: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    List sessions for a user.
    
    Returns most recent sessions first.
    """
    try:
        table = _get_table()
        
        key_condition = "PK = :pk AND begins_with(SK, :sk_prefix)"
        expr_values = {
            ":pk": f"SESSION#{tenant_id}#{user_id}",
            ":sk_prefix": "SESSION#",
        }
        
        filter_expr = None
        if status:
            filter_expr = "#status = :status"
            expr_values[":status"] = status
        
        response = table.query(
            KeyConditionExpression=key_condition,
            ExpressionAttributeValues=expr_values,
            FilterExpression=filter_expr if filter_expr else None,
            ExpressionAttributeNames={"#status": "status"} if status else None,
            ScanIndexForward=False,  # Descending order
            Limit=limit
        )
        
        sessions = [_serialize_item(item) for item in response.get("Items", [])]
        return sessions
    except (ClientError, BotoCoreError) as e:
        logger.error("Failed to list sessions: %s", e)
        return []


# ── Message Operations ───────────────────────────────────────────────

def add_message(
    session_id: str,
    role: str,
    content: Any,
    tenant_id: str = "default",
    user_id: str = "anonymous",
    metadata: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Add a message to a session.
    
    Content can be a string or a list of content blocks (for tool use).
    """
    now = datetime.utcnow()
    message_id = f"{int(now.timestamp() * 1000)}-{hashlib.md5(str(content).encode()).hexdigest()[:8]}"
    
    # Serialize content if it's a list
    if isinstance(content, list):
        content_str = json.dumps(content, default=str)
    else:
        content_str = str(content)
    
    message = {
        "PK": f"SESSION#{tenant_id}#{user_id}",
        "SK": f"MSG#{session_id}#{message_id}",
        "message_id": message_id,
        "session_id": session_id,
        "role": role,
        "content": content_str,
        "content_type": "list" if isinstance(content, list) else "text",
        "created_at": now.isoformat(),
        "metadata": metadata or {},
    }
    
    try:
        table = _get_table()
        table.put_item(Item=message)
        
        # Update session message count and updated_at
        table.update_item(
            Key={
                "PK": f"SESSION#{tenant_id}#{user_id}",
                "SK": f"SESSION#{session_id}",
            },
            UpdateExpression="SET #upd = :upd, message_count = if_not_exists(message_count, :zero) + :one",
            ExpressionAttributeNames={"#upd": "updated_at"},
            ExpressionAttributeValues={
                ":upd": now.isoformat(),
                ":zero": 0,
                ":one": 1,
            }
        )
        
        return _serialize_item(message)
    except (ClientError, BotoCoreError) as e:
        logger.error("Failed to add message: %s", e)
        return _serialize_item(message)


def get_messages(
    session_id: str,
    tenant_id: str = "default",
    user_id: str = "anonymous",
    limit: int = 100,
    before: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Get messages for a session.
    
    Returns messages in chronological order.
    """
    try:
        table = _get_table()
        
        key_condition = "PK = :pk AND begins_with(SK, :sk_prefix)"
        expr_values = {
            ":pk": f"SESSION#{tenant_id}#{user_id}",
            ":sk_prefix": f"MSG#{session_id}#",
        }
        
        if before:
            key_condition = "PK = :pk AND SK < :before"
            expr_values[":before"] = f"MSG#{session_id}#{before}"
        
        response = table.query(
            KeyConditionExpression=key_condition,
            ExpressionAttributeValues=expr_values,
            ScanIndexForward=True,  # Ascending order
            Limit=limit
        )
        
        messages = []
        for item in response.get("Items", []):
            msg = _serialize_item(item)
            # Parse content back to list if needed
            if msg.get("content_type") == "list":
                try:
                    msg["content"] = json.loads(msg["content"])
                except json.JSONDecodeError:
                    pass
            messages.append(msg)
        
        return messages
    except (ClientError, BotoCoreError) as e:
        logger.error("Failed to get messages: %s", e)
        return []


def get_messages_for_anthropic(
    session_id: str,
    tenant_id: str = "default",
    user_id: str = "anonymous",
    limit: int = 100
) -> List[Dict[str, Any]]:
    """
    Get messages in Anthropic API format.
    
    Returns: [{"role": "user", "content": "..."}, ...]
    """
    messages = get_messages(session_id, tenant_id, user_id, limit)
    
    anthropic_messages = []
    for msg in messages:
        content = msg.get("content", "")
        role = msg.get("role", "user")
        
        # Handle list content (tool use)
        if isinstance(content, list):
            anthropic_messages.append({"role": role, "content": content})
        else:
            anthropic_messages.append({"role": role, "content": str(content)})
    
    return anthropic_messages


# ── Usage Tracking ───────────────────────────────────────────────────

def record_usage(
    session_id: str,
    tenant_id: str = "default",
    user_id: str = "anonymous",
    input_tokens: int = 0,
    output_tokens: int = 0,
    model: str = "",
    cost_usd: float = 0.0
):
    """
    Record token usage for a session.
    """
    now = datetime.utcnow()
    
    usage = {
        "PK": f"USAGE#{tenant_id}",
        "SK": f"USAGE#{now.strftime('%Y-%m-%d')}#{session_id}#{int(now.timestamp() * 1000)}",
        "tenant_id": tenant_id,
        "user_id": user_id,
        "session_id": session_id,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "model": model,
        "cost_usd": Decimal(str(cost_usd)),
        "created_at": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
    }
    
    try:
        table = _get_table()
        table.put_item(Item=usage)
        
        # Also update session total_tokens
        table.update_item(
            Key={
                "PK": f"SESSION#{tenant_id}#{user_id}",
                "SK": f"SESSION#{session_id}",
            },
            UpdateExpression="SET total_tokens = if_not_exists(total_tokens, :zero) + :tokens",
            ExpressionAttributeValues={
                ":zero": 0,
                ":tokens": input_tokens + output_tokens,
            }
        )
    except (ClientError, BotoCoreError) as e:
        logger.error("Failed to record usage: %s", e)


def get_usage_summary(
    tenant_id: str = "default",
    days: int = 30
) -> Dict[str, Any]:
    """
    Get usage summary for a tenant.
    """
    try:
        table = _get_table()
        
        # Query usage records for the past N days
        start_date = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        response = table.query(
            KeyConditionExpression="PK = :pk AND SK >= :start",
            ExpressionAttributeValues={
                ":pk": f"USAGE#{tenant_id}",
                ":start": f"USAGE#{start_date}",
            }
        )
        
        items = response.get("Items", [])
        
        total_input = sum(int(i.get("input_tokens", 0)) for i in items)
        total_output = sum(int(i.get("output_tokens", 0)) for i in items)
        total_cost = sum(float(i.get("cost_usd", 0)) for i in items)
        
        # Group by date
        by_date = {}
        for item in items:
            date = item.get("date", "unknown")
            if date not in by_date:
                by_date[date] = {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0, "requests": 0}
            by_date[date]["input_tokens"] += int(item.get("input_tokens", 0))
            by_date[date]["output_tokens"] += int(item.get("output_tokens", 0))
            by_date[date]["cost_usd"] += float(item.get("cost_usd", 0))
            by_date[date]["requests"] += 1
        
        return {
            "tenant_id": tenant_id,
            "period_days": days,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_tokens": total_input + total_output,
            "total_cost_usd": round(total_cost, 4),
            "total_requests": len(items),
            "by_date": dict(sorted(by_date.items(), reverse=True)),
        }
    except (ClientError, BotoCoreError) as e:
        logger.error("Failed to get usage summary: %s", e)
        return {
            "tenant_id": tenant_id,
            "period_days": days,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_tokens": 0,
            "total_cost_usd": 0,
            "total_requests": 0,
            "by_date": {},
            "error": str(e),
        }


# ── Tenant-Level Queries (Admin/Cost Services) ──────────────────────

def get_usage_metrics(
    tenant_id: str,
    start_date: datetime,
    end_date: datetime
) -> List[Dict[str, Any]]:
    """Query USAGE# records for a tenant within a date range."""
    try:
        table = _get_table()
        response = table.query(
            KeyConditionExpression="PK = :pk AND SK BETWEEN :start AND :end",
            ExpressionAttributeValues={
                ":pk": f"USAGE#{tenant_id}",
                ":start": f"USAGE#{start_date.strftime('%Y-%m-%d')}",
                ":end": f"USAGE#{end_date.strftime('%Y-%m-%d')}~",
            }
        )
        return [_serialize_item(i) for i in response.get("Items", [])]
    except (ClientError, BotoCoreError) as e:
        logger.error("Failed to get usage metrics: %s", e)
        return []


def get_all_tenants() -> List[Dict[str, str]]:
    """Scan for unique tenant IDs across all SESSION# records."""
    try:
        table = _get_table()
        response = table.scan(
            FilterExpression="begins_with(PK, :prefix) AND begins_with(SK, :sk_prefix)",
            ExpressionAttributeValues={
                ":prefix": "SESSION#",
                ":sk_prefix": "SESSION#",
            },
            ProjectionExpression="PK, tenant_id"
        )
        tenant_ids = set()
        for item in response.get("Items", []):
            tid = item.get("tenant_id")
            if tid:
                tenant_ids.add(tid)
            else:
                parts = item.get("PK", "").split("#")
                if len(parts) >= 2:
                    tenant_ids.add(parts[1])
        return [{"tenant_id": tid} for tid in tenant_ids]
    except (ClientError, BotoCoreError) as e:
        logger.error("Failed to get all tenants: %s", e)
        return []


def get_tenants_by_tier(tier: str) -> List[Dict[str, str]]:
    """Scan sessions filtered by subscription tier metadata."""
    try:
        table = _get_table()
        response = table.scan(
            FilterExpression="begins_with(SK, :sk_prefix) AND metadata.subscription_tier = :tier",
            ExpressionAttributeValues={
                ":sk_prefix": "SESSION#",
                ":tier": tier,
            },
            ProjectionExpression="PK, tenant_id"
        )
        tenant_ids = set()
        for item in response.get("Items", []):
            tid = item.get("tenant_id")
            if tid:
                tenant_ids.add(tid)
            else:
                parts = item.get("PK", "").split("#")
                if len(parts) >= 2:
                    tenant_ids.add(parts[1])
        return [{"tenant_id": tid} for tid in tenant_ids]
    except (ClientError, BotoCoreError) as e:
        logger.error("Failed to get tenants by tier: %s", e)
        return []


def store_cost_metric(
    tenant_id: str,
    user_id: str,
    session_id: str,
    metric_type: str,
    value: float,
    **metadata
) -> None:
    """Store a cost/usage metric in the eagle table."""
    now = datetime.utcnow()
    item = {
        "PK": f"COST#{tenant_id}",
        "SK": f"COST#{now.strftime('%Y-%m-%d')}#{int(now.timestamp() * 1000)}",
        "tenant_id": tenant_id,
        "user_id": user_id,
        "session_id": session_id,
        "metric_type": metric_type,
        "value": Decimal(str(value)),
        "timestamp": now.isoformat(),
        "created_at": now.isoformat(),
        **{k: v for k, v in metadata.items()},
    }
    try:
        table = _get_table()
        table.put_item(Item=item)
    except (ClientError, BotoCoreError) as e:
        logger.error("Failed to store cost metric: %s", e)


def get_tenant_usage_overview(tenant_id: str) -> Dict[str, Any]:
    """Get tenant usage overview (replaces DynamoDBStore.get_tenant_usage).

    Returns a dict with total_messages, sessions count, and recent metrics.
    """
    try:
        table = _get_table()

        # Count usage records (recent metrics)
        usage_resp = table.query(
            KeyConditionExpression="PK = :pk",
            ExpressionAttributeValues={":pk": f"USAGE#{tenant_id}"},
            ScanIndexForward=False,
            Limit=50
        )
        metrics = [_serialize_item(i) for i in usage_resp.get("Items", [])]

        # Count sessions for this tenant (scan for PK prefix)
        sessions_resp = table.scan(
            FilterExpression="begins_with(PK, :prefix) AND begins_with(SK, :sk_prefix)",
            ExpressionAttributeValues={
                ":prefix": f"SESSION#{tenant_id}#",
                ":sk_prefix": "SESSION#",
            },
            ProjectionExpression="PK",
            Select="COUNT"
        )
        session_count = sessions_resp.get("Count", 0)

        return {
            "tenant_id": tenant_id,
            "total_messages": len(metrics),
            "sessions": session_count,
            "metrics": metrics[:10],
        }
    except (ClientError, BotoCoreError) as e:
        logger.error("Failed to get tenant usage overview: %s", e)
        return {
            "tenant_id": tenant_id,
            "total_messages": 0,
            "sessions": 0,
            "metrics": [],
            "error": str(e),
        }


def list_tenant_sessions(tenant_id: str) -> List[Dict[str, Any]]:
    """List all sessions for a tenant (replaces DynamoDBStore.get_tenant_sessions)."""
    try:
        table = _get_table()
        response = table.scan(
            FilterExpression="begins_with(PK, :prefix) AND begins_with(SK, :sk_prefix)",
            ExpressionAttributeValues={
                ":prefix": f"SESSION#{tenant_id}#",
                ":sk_prefix": "SESSION#",
            }
        )
        return [_serialize_item(i) for i in response.get("Items", [])]
    except (ClientError, BotoCoreError) as e:
        logger.error("Failed to list tenant sessions: %s", e)
        return []


def get_subscription_usage(tenant_id: str, tier: str) -> Optional[Dict[str, Any]]:
    """Get current subscription usage counters for a tenant/tier."""
    try:
        table = _get_table()
        response = table.get_item(
            Key={
                "PK": f"SUB#{tenant_id}",
                "SK": f"SUB#{tier}#current",
            }
        )
        item = response.get("Item")
        return _serialize_item(item) if item else None
    except (ClientError, BotoCoreError) as e:
        logger.error("Failed to get subscription usage: %s", e)
        return None


def put_subscription_usage(
    tenant_id: str,
    tier: str,
    daily_usage: int,
    monthly_usage: int,
    active_sessions: int,
    last_reset_date: str
) -> None:
    """Store subscription usage counters for a tenant/tier."""
    try:
        table = _get_table()
        table.put_item(Item={
            "PK": f"SUB#{tenant_id}",
            "SK": f"SUB#{tier}#current",
            "tenant_id": tenant_id,
            "tier": tier,
            "daily_usage": daily_usage,
            "monthly_usage": monthly_usage,
            "active_sessions": active_sessions,
            "last_reset_date": last_reset_date,
        })
    except (ClientError, BotoCoreError) as e:
        logger.error("Failed to put subscription usage: %s", e)


# ── Helpers ──────────────────────────────────────────────────────────

def _serialize_item(item: Dict) -> Dict:
    """Convert DynamoDB item to JSON-serializable dict."""
    result = {}
    for k, v in item.items():
        if isinstance(v, Decimal):
            result[k] = float(v) if v % 1 else int(v)
        else:
            result[k] = v
    return result
