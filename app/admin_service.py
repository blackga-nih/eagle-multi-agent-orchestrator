"""
Admin Service
Dashboard analytics, cost tracking, and user management.
"""
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError, BotoCoreError

logger = logging.getLogger("eagle.admin")

# ── Configuration ────────────────────────────────────────────────────
TABLE_NAME = os.getenv("EAGLE_SESSIONS_TABLE", "eagle")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# Cost per 1K tokens (Claude 3.5 Sonnet via Bedrock, approximate)
COST_INPUT_PER_1K = float(os.getenv("COST_INPUT_PER_1K", "0.003"))
COST_OUTPUT_PER_1K = float(os.getenv("COST_OUTPUT_PER_1K", "0.015"))

# ── DynamoDB Client ──────────────────────────────────────────────────
_dynamodb = None


def _get_dynamodb():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
    return _dynamodb


def _get_table():
    return _get_dynamodb().Table(TABLE_NAME)


def _serialize_item(item: Dict) -> Dict:
    """Convert DynamoDB item to JSON-serializable dict."""
    result = {}
    for k, v in item.items():
        if isinstance(v, Decimal):
            result[k] = float(v) if v % 1 else int(v)
        else:
            result[k] = v
    return result


# ── Cost Calculation ─────────────────────────────────────────────────

def calculate_cost(input_tokens: int, output_tokens: int) -> float:
    """Calculate cost in USD for given token counts."""
    input_cost = (input_tokens / 1000) * COST_INPUT_PER_1K
    output_cost = (output_tokens / 1000) * COST_OUTPUT_PER_1K
    return round(input_cost + output_cost, 6)


def record_request_cost(
    tenant_id: str,
    user_id: str,
    session_id: str,
    input_tokens: int,
    output_tokens: int,
    model: str = "claude-sonnet-4-20250514",
    tools_used: Optional[List[str]] = None,
    response_time_ms: int = 0
):
    """
    Record cost and usage for a single request.
    """
    now = datetime.utcnow()
    cost = calculate_cost(input_tokens, output_tokens)
    
    # Cost record
    cost_record = {
        "PK": f"COST#{tenant_id}",
        "SK": f"COST#{now.strftime('%Y-%m-%d')}#{int(now.timestamp() * 1000)}",
        "tenant_id": tenant_id,
        "user_id": user_id,
        "session_id": session_id,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "cost_usd": Decimal(str(cost)),
        "model": model,
        "tools_used": tools_used or [],
        "response_time_ms": response_time_ms,
        "created_at": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "hour": now.hour,
    }
    
    try:
        table = _get_table()
        table.put_item(Item=cost_record)
        
        # Update daily aggregate
        _update_daily_aggregate(tenant_id, now.strftime("%Y-%m-%d"), input_tokens, output_tokens, cost)
        
    except (ClientError, BotoCoreError) as e:
        logger.error("Failed to record cost: %s", e)


def _update_daily_aggregate(tenant_id: str, date: str, input_tokens: int, output_tokens: int, cost: float):
    """Update daily aggregate counters."""
    try:
        table = _get_table()
        table.update_item(
            Key={
                "PK": f"AGG#{tenant_id}",
                "SK": f"DAILY#{date}",
            },
            UpdateExpression="""
                SET input_tokens = if_not_exists(input_tokens, :zero) + :inp,
                    output_tokens = if_not_exists(output_tokens, :zero) + :out,
                    total_cost = if_not_exists(total_cost, :zero_dec) + :cost,
                    request_count = if_not_exists(request_count, :zero) + :one,
                    updated_at = :now
            """,
            ExpressionAttributeValues={
                ":zero": 0,
                ":zero_dec": Decimal("0"),
                ":inp": input_tokens,
                ":out": output_tokens,
                ":cost": Decimal(str(cost)),
                ":one": 1,
                ":now": datetime.utcnow().isoformat(),
            }
        )
    except Exception as e:
        logger.warning("Failed to update daily aggregate: %s", e)


# ── Dashboard Analytics ──────────────────────────────────────────────

def get_dashboard_stats(tenant_id: str = "default", days: int = 30) -> Dict[str, Any]:
    """
    Get dashboard statistics for a tenant.
    
    Returns summary stats and daily breakdowns.
    """
    try:
        table = _get_table()
        
        # Get daily aggregates
        start_date = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        response = table.query(
            KeyConditionExpression="PK = :pk AND SK >= :start",
            ExpressionAttributeValues={
                ":pk": f"AGG#{tenant_id}",
                ":start": f"DAILY#{start_date}",
            }
        )
        
        daily_data = [_serialize_item(i) for i in response.get("Items", [])]
        
        # Calculate totals
        total_input = sum(d.get("input_tokens", 0) for d in daily_data)
        total_output = sum(d.get("output_tokens", 0) for d in daily_data)
        total_cost = sum(d.get("total_cost", 0) for d in daily_data)
        total_requests = sum(d.get("request_count", 0) for d in daily_data)
        
        # Get active sessions count
        sessions_response = table.query(
            KeyConditionExpression="PK = :pk AND begins_with(SK, :prefix)",
            ExpressionAttributeValues={
                ":pk": f"SESSION#{tenant_id}#",
                ":prefix": "SESSION#",
            },
            Select="COUNT"
        )
        active_sessions = sessions_response.get("Count", 0)
        
        # Format daily data for charts
        chart_data = []
        for d in sorted(daily_data, key=lambda x: x.get("SK", "")):
            date = d.get("SK", "").replace("DAILY#", "")
            chart_data.append({
                "date": date,
                "input_tokens": d.get("input_tokens", 0),
                "output_tokens": d.get("output_tokens", 0),
                "cost": round(d.get("total_cost", 0), 4),
                "requests": d.get("request_count", 0),
            })
        
        return {
            "tenant_id": tenant_id,
            "period_days": days,
            "summary": {
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "total_tokens": total_input + total_output,
                "total_cost_usd": round(total_cost, 4),
                "total_requests": total_requests,
                "active_sessions": active_sessions,
                "avg_tokens_per_request": round((total_input + total_output) / max(total_requests, 1)),
                "avg_cost_per_request": round(total_cost / max(total_requests, 1), 4),
            },
            "daily": chart_data,
            "generated_at": datetime.utcnow().isoformat(),
        }
        
    except (ClientError, BotoCoreError) as e:
        logger.error("Failed to get dashboard stats: %s", e)
        return {
            "tenant_id": tenant_id,
            "period_days": days,
            "summary": {
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "total_tokens": 0,
                "total_cost_usd": 0,
                "total_requests": 0,
                "active_sessions": 0,
            },
            "daily": [],
            "error": str(e),
        }


def get_user_stats(tenant_id: str, user_id: str, days: int = 30) -> Dict[str, Any]:
    """
    Get usage statistics for a specific user.
    """
    try:
        table = _get_table()
        
        start_date = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        # Query cost records for this user
        response = table.query(
            KeyConditionExpression="PK = :pk AND SK >= :start",
            FilterExpression="user_id = :user",
            ExpressionAttributeValues={
                ":pk": f"COST#{tenant_id}",
                ":start": f"COST#{start_date}",
                ":user": user_id,
            }
        )
        
        records = [_serialize_item(i) for i in response.get("Items", [])]
        
        total_input = sum(r.get("input_tokens", 0) for r in records)
        total_output = sum(r.get("output_tokens", 0) for r in records)
        total_cost = sum(r.get("cost_usd", 0) for r in records)
        
        # Group by session
        by_session = {}
        for r in records:
            sid = r.get("session_id", "unknown")
            if sid not in by_session:
                by_session[sid] = {"tokens": 0, "cost": 0, "requests": 0}
            by_session[sid]["tokens"] += r.get("total_tokens", 0)
            by_session[sid]["cost"] += r.get("cost_usd", 0)
            by_session[sid]["requests"] += 1
        
        return {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "period_days": days,
            "summary": {
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "total_tokens": total_input + total_output,
                "total_cost_usd": round(total_cost, 4),
                "total_requests": len(records),
                "total_sessions": len(by_session),
            },
            "by_session": by_session,
        }
        
    except (ClientError, BotoCoreError) as e:
        logger.error("Failed to get user stats: %s", e)
        return {"error": str(e)}


def get_top_users(tenant_id: str, days: int = 30, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Get top users by usage for a tenant.
    """
    try:
        table = _get_table()
        
        start_date = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        response = table.query(
            KeyConditionExpression="PK = :pk AND SK >= :start",
            ExpressionAttributeValues={
                ":pk": f"COST#{tenant_id}",
                ":start": f"COST#{start_date}",
            }
        )
        
        # Aggregate by user
        by_user = {}
        for item in response.get("Items", []):
            user_id = item.get("user_id", "unknown")
            if user_id not in by_user:
                by_user[user_id] = {
                    "user_id": user_id,
                    "total_tokens": 0,
                    "total_cost": 0,
                    "request_count": 0,
                }
            by_user[user_id]["total_tokens"] += int(item.get("total_tokens", 0))
            by_user[user_id]["total_cost"] += float(item.get("cost_usd", 0))
            by_user[user_id]["request_count"] += 1
        
        # Sort by cost and return top N
        sorted_users = sorted(by_user.values(), key=lambda x: x["total_cost"], reverse=True)
        return sorted_users[:limit]
        
    except (ClientError, BotoCoreError) as e:
        logger.error("Failed to get top users: %s", e)
        return []


# ── Tool Usage Analytics ─────────────────────────────────────────────

def get_tool_usage(tenant_id: str, days: int = 30) -> Dict[str, Any]:
    """
    Get tool usage breakdown.
    """
    try:
        table = _get_table()
        
        start_date = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        response = table.query(
            KeyConditionExpression="PK = :pk AND SK >= :start",
            ExpressionAttributeValues={
                ":pk": f"COST#{tenant_id}",
                ":start": f"COST#{start_date}",
            }
        )
        
        # Count tool usage
        tool_counts = {}
        for item in response.get("Items", []):
            tools = item.get("tools_used", [])
            for tool in tools:
                tool_counts[tool] = tool_counts.get(tool, 0) + 1
        
        # Sort by usage
        sorted_tools = sorted(tool_counts.items(), key=lambda x: x[1], reverse=True)
        
        return {
            "tenant_id": tenant_id,
            "period_days": days,
            "tools": [{"name": t[0], "count": t[1]} for t in sorted_tools],
            "total_tool_calls": sum(tool_counts.values()),
        }
        
    except (ClientError, BotoCoreError) as e:
        logger.error("Failed to get tool usage: %s", e)
        return {"error": str(e)}


# ── Rate Limiting ────────────────────────────────────────────────────

# Rate limits by tier (requests per hour, tokens per day)
RATE_LIMITS = {
    "free": {"requests_per_hour": 20, "tokens_per_day": 50000},
    "basic": {"requests_per_hour": 100, "tokens_per_day": 500000},
    "premium": {"requests_per_hour": 500, "tokens_per_day": 2000000},
    "enterprise": {"requests_per_hour": 2000, "tokens_per_day": 10000000},
}


def check_rate_limit(tenant_id: str, user_id: str, tier: str = "free") -> Dict[str, Any]:
    """
    Check if user is within rate limits.
    
    Returns:
        Dict with: allowed, reason, usage, limits
    """
    limits = RATE_LIMITS.get(tier.lower(), RATE_LIMITS["free"])
    
    try:
        table = _get_table()
        
        now = datetime.utcnow()
        hour_start = now.replace(minute=0, second=0, microsecond=0)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Count requests in current hour
        hour_response = table.query(
            KeyConditionExpression="PK = :pk AND SK >= :start",
            FilterExpression="user_id = :user",
            ExpressionAttributeValues={
                ":pk": f"COST#{tenant_id}",
                ":start": f"COST#{hour_start.strftime('%Y-%m-%d')}#{int(hour_start.timestamp() * 1000)}",
                ":user": user_id,
            },
            Select="COUNT"
        )
        requests_this_hour = hour_response.get("Count", 0)
        
        # Count tokens today
        day_response = table.query(
            KeyConditionExpression="PK = :pk AND SK >= :start",
            FilterExpression="user_id = :user",
            ExpressionAttributeValues={
                ":pk": f"COST#{tenant_id}",
                ":start": f"COST#{day_start.strftime('%Y-%m-%d')}",
                ":user": user_id,
            }
        )
        
        tokens_today = sum(int(i.get("total_tokens", 0)) for i in day_response.get("Items", []))
        
        # Check limits
        if requests_this_hour >= limits["requests_per_hour"]:
            return {
                "allowed": False,
                "reason": f"Rate limit exceeded: {requests_this_hour}/{limits['requests_per_hour']} requests/hour",
                "usage": {"requests_this_hour": requests_this_hour, "tokens_today": tokens_today},
                "limits": limits,
                "retry_after_seconds": 3600 - (now.minute * 60 + now.second),
            }
        
        if tokens_today >= limits["tokens_per_day"]:
            return {
                "allowed": False,
                "reason": f"Token limit exceeded: {tokens_today}/{limits['tokens_per_day']} tokens/day",
                "usage": {"requests_this_hour": requests_this_hour, "tokens_today": tokens_today},
                "limits": limits,
                "retry_after_seconds": 86400 - (now.hour * 3600 + now.minute * 60 + now.second),
            }
        
        return {
            "allowed": True,
            "reason": None,
            "usage": {"requests_this_hour": requests_this_hour, "tokens_today": tokens_today},
            "limits": limits,
            "remaining": {
                "requests_this_hour": limits["requests_per_hour"] - requests_this_hour,
                "tokens_today": limits["tokens_per_day"] - tokens_today,
            },
        }
        
    except (ClientError, BotoCoreError) as e:
        logger.error("Failed to check rate limit: %s", e)
        # Allow on error (fail open)
        return {
            "allowed": True,
            "reason": "Rate limit check failed, allowing request",
            "error": str(e),
        }
