"""
EAGLE Admin Router

Handles admin dashboard, KB reviews, Langfuse traces, cost reports,
plugin management, prompts, and config endpoints.
Extracted from main.py for better organization.
"""

import copy
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException

from ..admin_auth import get_admin_user, verify_tenant_admin
from ..admin_cost_service import AdminCostService
from ..admin_service import get_dashboard_stats, get_top_users, get_user_stats, check_rate_limit
from ..audit_store import write_audit
from ..cognito_auth import UserContext
from ..config_store import delete_config, list_config, put_config, _config_cache
from ..cost_attribution import CostAttributionService
from ..db_client import get_dynamodb, get_s3
from ..models import SubscriptionTier
from ..plugin_store import (
    _entity_cache as _plugin_cache,
    ensure_plugin_seeded,
    get_plugin_item,
    get_plugin_manifest,
    list_plugin_entities,
    put_plugin_item,
)
from ..prompt_store import _prompt_cache, delete_prompt, get_prompt, list_tenant_prompts, put_prompt
from ..template_store import _template_cache

from .dependencies import get_user_from_header, get_session_context

logger = logging.getLogger("eagle")

router = APIRouter(prefix="/api/admin", tags=["admin"])

GENERIC_ANALYTICS_ERROR = "Analytics data is temporarily unavailable."

# Service instances
cost_service = CostAttributionService()
admin_cost_service = AdminCostService()

# S3 bucket (single source of truth)
_S3_BUCKET = os.getenv("S3_BUCKET", "eagle-documents-dev")


# ══════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ══════════════════════════════════════════════════════════════════════


def _get_dynamo():
    return get_dynamodb()


def _apply_json_patch(obj: dict, patch: list) -> dict:
    """Apply a simplified JSON Patch (RFC 6902) to a dict. Supports replace, add, remove."""
    result = copy.deepcopy(obj)
    for op in patch:
        operation = op.get("op")
        path = op.get("path", "")
        parts = [p for p in path.split("/") if p]
        try:
            if operation == "replace":
                target = result
                for part in parts[:-1]:
                    target = target[int(part)] if isinstance(target, list) else target[part]
                last = parts[-1]
                if isinstance(target, list):
                    target[int(last)] = op["value"]
                else:
                    target[last] = op["value"]
            elif operation == "add":
                target = result
                for part in parts[:-1]:
                    target = target[int(part)] if isinstance(target, list) else target[part]
                last = parts[-1]
                if isinstance(target, list):
                    target.append(op["value"])
                else:
                    target[last] = op["value"]
            elif operation == "remove":
                target = result
                for part in parts[:-1]:
                    target = target[int(part)] if isinstance(target, list) else target[part]
                last = parts[-1]
                if isinstance(target, list):
                    del target[int(last)]
                else:
                    del target[last]
        except (KeyError, IndexError, TypeError) as e:
            logger.warning("JSON patch op failed (%s %s): %s", operation, path, e)
    return result


def _regenerate_html_arrays(matrix: dict) -> None:
    """Replace THRESHOLDS and TYPES JS arrays in contract-requirements-matrix.html."""
    import json as _json
    import re as _re

    html_path = Path(__file__).resolve().parent.parent.parent.parent / "contract-requirements-matrix.html"
    if not html_path.exists():
        logger.warning("contract-requirements-matrix.html not found, skipping HTML regeneration")
        return

    html = html_path.read_text(encoding="utf-8")

    # Build new THRESHOLDS array from matrix
    thresholds_js = "const THRESHOLDS = [\n"
    for t in matrix.get("thresholds", []):
        thresholds_js += (
            f'  {{ id: "{t["id"]}", label: "{t["label"]}", '
            f'maxValue: {t.get("maxValue", "null")}, '
            f'description: "{t.get("description", "")}" }},\n'
        )
    thresholds_js += "];"

    # Build new TYPES array
    types_js = "const TYPES = [\n"
    for ct in matrix.get("types", []):
        types_js += f'  {{ id: "{ct["id"]}", label: "{ct["label"]}" }},\n'
    types_js += "];"

    # Replace in HTML
    html = _re.sub(r"const THRESHOLDS = \[[\s\S]*?\];", thresholds_js, html)
    html = _re.sub(r"const TYPES = \[[\s\S]*?\];", types_js, html)

    html_path.write_text(html, encoding="utf-8")
    logger.info("contract-requirements-matrix.html arrays regenerated")


def _langfuse_latency_ms(t: dict) -> int:
    """Calculate latency from Langfuse trace latency field or timestamps."""
    if t.get("latency"):
        return int(t["latency"] * 1000)
    return 0


def _obs_duration_ms(o: dict) -> int:
    """Calculate observation duration from start/end times."""
    start = o.get("startTime")
    end = o.get("endTime")
    if start and end:
        try:
            from datetime import datetime as _dt

            for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%f+00:00"):
                try:
                    s = _dt.strptime(start.replace("+00:00", "Z").rstrip("Z") + "Z", fmt)
                    e = _dt.strptime(end.replace("+00:00", "Z").rstrip("Z") + "Z", fmt)
                    return int((e - s).total_seconds() * 1000)
                except ValueError:
                    continue
        except Exception:
            pass
    return 0


def _extract_env_from_trace(tags: list, metadata: dict = None) -> str:
    """Extract environment from tags (['env:local']) or OTEL metadata."""
    for tag in tags or []:
        if isinstance(tag, str) and tag.startswith("env:"):
            return tag[4:]
    if metadata:
        if metadata.get("eagle.environment"):
            return metadata["eagle.environment"]
        ta = metadata.get("trace_attributes", {})
        if isinstance(ta, dict) and ta.get("eagle.environment"):
            return ta["eagle.environment"]
    return "unknown"


def _truncate(value: Any, max_len: int = 200) -> Any:
    """Truncate string values for list views."""
    if isinstance(value, str) and len(value) > max_len:
        return value[:max_len] + "..."
    return value


def _langfuse_url(trace_id: str) -> str:
    """Build Langfuse UI link."""
    from ..telemetry.langfuse_client import langfuse_trace_url

    return langfuse_trace_url(trace_id)


def _get_result_error(result: Any) -> Optional[str]:
    if isinstance(result, dict):
        error = result.get("error")
        if isinstance(error, str) and error:
            return error
    return None


def _sanitize_result_error(result: Dict[str, Any], fallback_error: str) -> Dict[str, Any]:
    sanitized = dict(result)
    sanitized["error"] = fallback_error
    return sanitized


# ══════════════════════════════════════════════════════════════════════
# KB REVIEW ENDPOINTS
# ══════════════════════════════════════════════════════════════════════


@router.get("/kb-reviews")
async def api_list_kb_reviews(
    status: Optional[str] = "pending",
    user: UserContext = Depends(get_user_from_header),
):
    """List KB review records from DynamoDB (admin only)."""
    from boto3.dynamodb.conditions import Attr

    table_name = os.getenv("METADATA_TABLE", "eagle-document-metadata-dev")
    try:
        ddb = _get_dynamo()
        table = ddb.Table(table_name)
        resp = table.scan(
            FilterExpression=Attr("PK").begins_with("KB_REVIEW#") & Attr("status").eq(status),
        )
        reviews = resp.get("Items", [])
        reviews.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return {"reviews": reviews, "count": len(reviews)}
    except Exception as e:
        logger.error("KB review list error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to list KB reviews")


@router.post("/kb-review/{review_id}/approve")
async def api_approve_kb_review(
    review_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Approve a KB review: apply diff to matrix.json, update HTML, move doc to approved/."""
    import json as _json

    from botocore.exceptions import ClientError

    table_name = os.getenv("METADATA_TABLE", "eagle-document-metadata-dev")
    bucket = _S3_BUCKET
    ddb = _get_dynamo()
    table = ddb.Table(table_name)
    s3 = get_s3()

    pk = f"KB_REVIEW#{review_id}"
    try:
        item = table.get_item(Key={"PK": pk, "SK": "META"}).get("Item")
    except Exception as e:
        logger.error("KB review fetch error (approve): %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch KB review")

    if not item:
        raise HTTPException(status_code=404, detail="KB review not found")
    if item.get("status") != "pending":
        raise HTTPException(status_code=409, detail="Review already processed")

    proposed_diff = item.get("proposed_diff", [])

    # Apply diff to matrix.json (file on disk relative to this server)
    matrix_path = Path(__file__).resolve().parent.parent.parent.parent / "eagle-plugin" / "data" / "matrix.json"
    if matrix_path.exists():
        try:
            matrix = _json.loads(matrix_path.read_text(encoding="utf-8"))
            matrix = _apply_json_patch(matrix, proposed_diff)
            matrix["version"] = datetime.utcnow().strftime("%Y-%m-%d")
            matrix_path.write_text(_json.dumps(matrix, indent=2, ensure_ascii=False), encoding="utf-8")
            logger.info("matrix.json updated after KB review %s", review_id)

            _regenerate_html_arrays(matrix)
        except Exception as e:
            logger.warning("matrix.json patch failed (non-fatal): %s", e)
    else:
        logger.warning("matrix.json not found at %s — skipping patch", matrix_path)

    # Move S3 doc from pending/ to approved/
    old_key = item.get("s3_key", "")
    if old_key and old_key.startswith("eagle-knowledge-base/pending/"):
        new_key = old_key.replace("eagle-knowledge-base/pending/", "eagle-knowledge-base/approved/")
        try:
            s3.copy_object(Bucket=bucket, CopySource={"Bucket": bucket, "Key": old_key}, Key=new_key)
            s3.delete_object(Bucket=bucket, Key=old_key)
        except ClientError as e:
            logger.warning("S3 move failed: %s", e)

    now = datetime.utcnow().isoformat()
    table.update_item(
        Key={"PK": pk, "SK": "META"},
        UpdateExpression="SET #st = :s, reviewed_by = :u, reviewed_at = :t",
        ExpressionAttributeNames={"#st": "status"},
        ExpressionAttributeValues={":s": "approved", ":u": user.user_id, ":t": now},
    )
    return {"status": "approved", "review_id": review_id, "reviewed_at": now}


@router.post("/kb-review/{review_id}/reject")
async def api_reject_kb_review(
    review_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Reject a KB review: mark rejected, move doc to rejected/."""
    from botocore.exceptions import ClientError

    table_name = os.getenv("METADATA_TABLE", "eagle-document-metadata-dev")
    bucket = _S3_BUCKET
    ddb = _get_dynamo()
    table = ddb.Table(table_name)
    s3 = get_s3()

    pk = f"KB_REVIEW#{review_id}"
    try:
        item = table.get_item(Key={"PK": pk, "SK": "META"}).get("Item")
    except Exception as e:
        logger.error("KB review fetch error (reject): %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch KB review")

    if not item:
        raise HTTPException(status_code=404, detail="KB review not found")
    if item.get("status") != "pending":
        raise HTTPException(status_code=409, detail="Review already processed")

    old_key = item.get("s3_key", "")
    if old_key and old_key.startswith("eagle-knowledge-base/pending/"):
        new_key = old_key.replace("eagle-knowledge-base/pending/", "eagle-knowledge-base/rejected/")
        try:
            s3.copy_object(Bucket=bucket, CopySource={"Bucket": bucket, "Key": old_key}, Key=new_key)
            s3.delete_object(Bucket=bucket, Key=old_key)
        except ClientError as e:
            logger.warning("S3 move failed: %s", e)

    now = datetime.utcnow().isoformat()
    table.update_item(
        Key={"PK": pk, "SK": "META"},
        UpdateExpression="SET #st = :s, reviewed_by = :u, reviewed_at = :t",
        ExpressionAttributeNames={"#st": "status"},
        ExpressionAttributeValues={":s": "rejected", ":u": user.user_id, ":t": now},
    )
    return {"status": "rejected", "review_id": review_id, "reviewed_at": now}


# ══════════════════════════════════════════════════════════════════════
# DASHBOARD & USER STATS
# ══════════════════════════════════════════════════════════════════════


@router.get("/dashboard")
async def api_admin_dashboard(
    days: int = 30,
    user: UserContext = Depends(get_user_from_header),
):
    """Get admin dashboard statistics."""
    return get_dashboard_stats(user.tenant_id, days)


@router.get("/users")
async def api_admin_users(
    days: int = 30,
    limit: int = 10,
    user: UserContext = Depends(get_user_from_header),
):
    """Get top users by usage."""
    return {"users": get_top_users(user.tenant_id, days, limit)}


@router.get("/users/{target_user_id}")
async def api_admin_user_stats(
    target_user_id: str,
    days: int = 30,
    user: UserContext = Depends(get_user_from_header),
):
    """Get stats for a specific user."""
    return get_user_stats(user.tenant_id, target_user_id, days)


@router.get("/tools")
async def api_admin_tools(
    period: str = "24h",
    admin_user: dict = Depends(get_admin_user),
):
    """Per-tool health metrics aggregated from recent Langfuse traces."""
    from ..telemetry.langfuse_client import list_observations, list_traces

    now = datetime.now(timezone.utc)
    from_ts = (now - timedelta(days=7 if period == "7d" else 1)).isoformat()

    result = await list_traces(limit=100, from_timestamp=from_ts)
    traces = result.get("data", [])

    tool_stats: dict[str, dict] = {}
    for t in traces:
        trace_id = t.get("id", "")
        if not trace_id:
            continue
        obs_result = await list_observations(trace_id=trace_id, limit=50, type="SPAN")
        for obs in obs_result.get("data", []):
            name = obs.get("name", "")
            if not name or name in ("agent", "supervisor"):
                continue
            if name not in tool_stats:
                tool_stats[name] = {
                    "call_count": 0,
                    "success_count": 0,
                    "error_count": 0,
                    "total_ms": 0,
                    "recent_errors": [],
                }
            s = tool_stats[name]
            s["call_count"] += 1
            level = obs.get("level", "DEFAULT")
            if level == "ERROR":
                s["error_count"] += 1
                msg = obs.get("statusMessage", "")
                if msg and len(s["recent_errors"]) < 5:
                    s["recent_errors"].append(msg[:200])
            else:
                s["success_count"] += 1
            start = obs.get("startTime")
            end = obs.get("endTime")
            if start and end:
                try:
                    from datetime import datetime as dt

                    s_dt = dt.fromisoformat(start.replace("Z", "+00:00"))
                    e_dt = dt.fromisoformat(end.replace("Z", "+00:00"))
                    s["total_ms"] += int((e_dt - s_dt).total_seconds() * 1000)
                except Exception:
                    pass

    tools = []
    for name, s in sorted(tool_stats.items(), key=lambda x: x[1]["call_count"], reverse=True):
        total = s["call_count"]
        tools.append({
            "name": name,
            "call_count": total,
            "success_count": s["success_count"],
            "error_count": s["error_count"],
            "success_rate": round(s["success_count"] / total * 100, 1) if total else 100,
            "avg_duration_ms": round(s["total_ms"] / total) if total else 0,
            "recent_errors": s["recent_errors"],
        })

    return {"tools": tools, "period": period}


@router.get("/rate-limit")
async def api_check_rate_limit(user: UserContext = Depends(get_user_from_header)):
    """Check current rate limit status."""
    tenant_id, user_id, _ = get_session_context(user)
    result = check_rate_limit(tenant_id, user_id, user.tier)
    error = _get_result_error(result)
    return _sanitize_result_error(result, GENERIC_ANALYTICS_ERROR) if error else result


# ══════════════════════════════════════════════════════════════════════
# LANGFUSE TRACE ENDPOINTS
# ══════════════════════════════════════════════════════════════════════


@router.get("/traces")
async def get_admin_traces(
    limit: int = 50,
    page: int = 1,
    user_id: str = None,
    session_id: str = None,
    tag: str = None,
    from_date: str = None,
    to_date: str = None,
    name: str = None,
    admin_user: dict = Depends(get_admin_user),
):
    """List traces from Langfuse (admin only)."""
    from ..telemetry.langfuse_client import list_traces

    tags = [tag] if tag else None
    result = await list_traces(
        limit=limit,
        page=page,
        user_id=user_id,
        session_id=session_id,
        tags=tags,
        from_timestamp=from_date,
        to_timestamp=to_date,
        name=name,
    )
    data = result.get("data", [])
    traces = []
    for t in data:
        traces.append({
            "trace_id": t.get("id", ""),
            "name": t.get("name", ""),
            "session_id": t.get("sessionId", ""),
            "user_id": t.get("userId", ""),
            "created_at": t.get("timestamp", ""),
            "updated_at": t.get("updatedAt", ""),
            "duration_ms": _langfuse_latency_ms(t),
            "total_input_tokens": t.get("usage", {}).get("input", 0) if t.get("usage") else 0,
            "total_output_tokens": t.get("usage", {}).get("output", 0) if t.get("usage") else 0,
            "total_tokens": t.get("usage", {}).get("total", 0) if t.get("usage") else 0,
            "total_cost_usd": float(t.get("usage", {}).get("totalCost", 0) or 0) if t.get("usage") else 0,
            "tags": t.get("tags", []),
            "metadata": t.get("metadata", {}),
            "status": "error" if t.get("level") == "ERROR" else "success",
            "environment": _extract_env_from_trace(t.get("tags", []), t.get("metadata")),
            "input": _truncate(t.get("input"), 200),
            "output": _truncate(t.get("output"), 200),
            "observation_count": t.get("observationCount", 0),
            "langfuse_url": _langfuse_url(t.get("id", "")),
        })
    return {
        "traces": traces,
        "meta": result.get("meta", {}),
        "error": result.get("error"),
    }


@router.get("/traces/{trace_id}")
async def get_admin_trace_detail(
    trace_id: str,
    admin_user: dict = Depends(get_admin_user),
):
    """Get single trace detail + observations from Langfuse (admin only)."""
    from ..telemetry.langfuse_client import get_trace, langfuse_trace_url, list_observations

    trace = await get_trace(trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found in Langfuse")

    raw_obs = trace.get("observations") or []
    if not raw_obs:
        obs_result = await list_observations(trace_id=trace_id, limit=100)
        raw_obs = obs_result.get("data", [])

    observations = []
    for o in raw_obs:
        observations.append({
            "id": o.get("id", ""),
            "name": o.get("name", ""),
            "type": o.get("type", ""),
            "start_time": o.get("startTime", ""),
            "end_time": o.get("endTime", ""),
            "duration_ms": _obs_duration_ms(o),
            "model": o.get("model", ""),
            "input_tokens": o.get("usage", {}).get("input", 0) if o.get("usage") else 0,
            "output_tokens": o.get("usage", {}).get("output", 0) if o.get("usage") else 0,
            "total_cost": float(o.get("usage", {}).get("totalCost", 0) or 0) if o.get("usage") else 0,
            "input": _truncate(o.get("input"), 500),
            "output": _truncate(o.get("output"), 500),
            "metadata": o.get("metadata", {}),
            "level": o.get("level", "DEFAULT"),
            "status_message": o.get("statusMessage", ""),
        })

    return {
        "trace_id": trace.get("id", ""),
        "name": trace.get("name", ""),
        "session_id": trace.get("sessionId", ""),
        "user_id": trace.get("userId", ""),
        "created_at": trace.get("timestamp", ""),
        "duration_ms": _langfuse_latency_ms(trace),
        "total_input_tokens": trace.get("usage", {}).get("input", 0) if trace.get("usage") else 0,
        "total_output_tokens": trace.get("usage", {}).get("output", 0) if trace.get("usage") else 0,
        "total_cost_usd": float(trace.get("usage", {}).get("totalCost", 0) or 0) if trace.get("usage") else 0,
        "tags": trace.get("tags", []),
        "metadata": trace.get("metadata", {}),
        "status": "error" if trace.get("level") == "ERROR" else "success",
        "environment": _extract_env_from_trace(trace.get("tags", []), trace.get("metadata")),
        "input": trace.get("input"),
        "output": trace.get("output"),
        "observations": observations,
        "langfuse_url": langfuse_trace_url(trace_id),
    }


@router.get("/traces/summary")
async def get_admin_traces_summary(
    period: str = "24h",
    admin_user: dict = Depends(get_admin_user),
):
    """Aggregated trace statistics for the admin dashboard."""
    from ..telemetry.langfuse_client import list_traces

    now = datetime.now(timezone.utc)
    if period == "7d":
        from_ts = (now - timedelta(days=7)).isoformat()
    else:
        from_ts = (now - timedelta(hours=24)).isoformat()

    result = await list_traces(limit=200, from_timestamp=from_ts)
    data = result.get("data", [])

    total = len(data)
    errors = sum(1 for t in data if t.get("level") == "ERROR")
    error_rate = (errors / total * 100) if total else 0

    latencies = [_langfuse_latency_ms(t) for t in data]
    avg_latency = sum(latencies) / len(latencies) if latencies else 0

    total_cost = sum(
        float(t.get("usage", {}).get("totalCost", 0) or 0) for t in data if t.get("usage")
    )
    total_tokens = sum(t.get("usage", {}).get("total", 0) for t in data if t.get("usage"))

    by_user: dict[str, int] = {}
    by_session: dict[str, int] = {}
    for t in data:
        u = t.get("userId") or "unknown"
        s = t.get("sessionId") or "unknown"
        by_user[u] = by_user.get(u, 0) + 1
        by_session[s] = by_session.get(s, 0) + 1

    return {
        "period": period,
        "total_traces": total,
        "error_count": errors,
        "error_rate_pct": round(error_rate, 1),
        "avg_latency_ms": round(avg_latency),
        "total_cost_usd": round(total_cost, 4),
        "total_tokens": total_tokens,
        "unique_users": len(by_user),
        "unique_sessions": len(by_session),
        "top_users": sorted(by_user.items(), key=lambda x: x[1], reverse=True)[:5],
    }


# ══════════════════════════════════════════════════════════════════════
# COST REPORT ENDPOINTS
# ══════════════════════════════════════════════════════════════════════


@router.get("/cost-report")
async def get_cost_report(
    tenant_id: str = None,
    days: int = 30,
    admin_user: dict = Depends(get_admin_user),
):
    """Generate comprehensive cost report (admin only)."""
    report = await cost_service.generate_cost_report(tenant_id, days)
    return report


@router.get("/tier-costs/{tier}")
async def get_tier_costs(
    tier: str,
    days: int = 30,
    admin_user: dict = Depends(get_admin_user),
):
    """Get cost breakdown by subscription tier (admin only)."""
    subscription_tier = SubscriptionTier(tier)
    costs = await cost_service.get_subscription_tier_costs(subscription_tier, days)
    return costs


@router.get("/tenants/{tenant_id}/overall-cost")
async def get_admin_tenant_overall_cost(
    tenant_id: str,
    days: int = 30,
    admin_user: dict = Depends(verify_tenant_admin),
):
    """1. Overall Tenant Cost - Admin Only."""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    costs = await admin_cost_service.get_tenant_overall_cost(tenant_id, start_date, end_date)
    return costs


@router.get("/tenants/{tenant_id}/per-user-cost")
async def get_admin_per_user_cost(
    tenant_id: str,
    days: int = 30,
    admin_user: dict = Depends(verify_tenant_admin),
):
    """2. Per User Cost - Admin Only."""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    costs = await admin_cost_service.get_tenant_per_user_cost(tenant_id, start_date, end_date)
    return costs


@router.get("/tenants/{tenant_id}/service-wise-cost")
async def get_admin_service_wise_cost(
    tenant_id: str,
    days: int = 30,
    admin_user: dict = Depends(verify_tenant_admin),
):
    """3. Overall Tenant Service-wise Consumption Cost - Admin Only."""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    costs = await admin_cost_service.get_tenant_service_wise_cost(tenant_id, start_date, end_date)
    return costs


@router.get("/tenants/{tenant_id}/users/{user_id}/service-cost")
async def get_admin_user_service_cost(
    tenant_id: str,
    user_id: str,
    days: int = 30,
    admin_user: dict = Depends(verify_tenant_admin),
):
    """4. User Service-wise Consumption Cost - Admin Only."""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    costs = await admin_cost_service.get_user_service_wise_cost(tenant_id, user_id, start_date, end_date)
    return costs


@router.get("/tenants/{tenant_id}/comprehensive-report")
async def get_comprehensive_admin_report(
    tenant_id: str,
    days: int = 30,
    admin_user: dict = Depends(verify_tenant_admin),
):
    """Comprehensive Admin Cost Report - All 4 breakdowns."""
    report = await admin_cost_service.generate_comprehensive_admin_report(tenant_id, days)
    return report


@router.get("/my-tenants")
async def get_admin_tenants(admin_user: dict = Depends(get_admin_user)):
    """Get tenants where current user has admin access."""
    return {"admin_email": admin_user["email"], "admin_tenants": admin_user["admin_tenants"]}


@router.post("/add-to-group")
async def add_user_to_admin_group(request: dict):
    """Add user to admin group during registration."""
    from ..admin_auth import AdminAuthService

    email = request.get("email")
    tenant_id = request.get("tenant_id")

    if not email or not tenant_id:
        raise HTTPException(status_code=400, detail="Email and tenant_id required")

    admin_service_instance = AdminAuthService()

    try:
        group_name = f"{tenant_id}-admins"
        admin_service_instance.cognito_client.create_group(
            GroupName=group_name,
            UserPoolId=admin_service_instance.user_pool_id,
            Description=f"{tenant_id.title()} Administrators",
        )
    except Exception:
        pass

    try:
        admin_service_instance.cognito_client.admin_add_user_to_group(
            UserPoolId=admin_service_instance.user_pool_id,
            Username=email,
            GroupName=f"{tenant_id}-admins",
        )
        return {"success": True, "message": f"Added {email} to {tenant_id}-admins group"}
    except Exception as e:
        logger.error("Failed to add user to admin group: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to add user to admin group")


# ══════════════════════════════════════════════════════════════════════
# CACHE & PLUGIN MANAGEMENT
# ══════════════════════════════════════════════════════════════════════


@router.post("/reload")
async def admin_reload_caches(user: UserContext = Depends(get_user_from_header)):
    """Force-flush all in-process caches across plugin, prompt, config, template stores."""
    _plugin_cache.clear()
    _prompt_cache.clear()
    _config_cache.clear()
    _template_cache.clear()
    write_audit(
        tenant_id=user.tenant_id,
        entity_type="cache",
        entity_name="all",
        event_type="reload",
        actor_user_id=user.user_id,
    )
    return {"status": "flushed", "caches": ["plugin", "prompt", "config", "template"]}


@router.post("/plugin/sync")
async def admin_plugin_sync(user: UserContext = Depends(get_user_from_header)):
    """Force reseed all PLUGIN# entities from bundled eagle-plugin/ files (factory reset)."""
    from ..plugin_store import BUNDLED_PLUGIN_VERSION, _get_table

    try:
        _get_table().delete_item(Key={"PK": "PLUGIN#manifest", "SK": "PLUGIN#manifest"})
    except Exception:
        pass
    _plugin_cache.clear()
    ensure_plugin_seeded()
    write_audit(
        tenant_id=user.tenant_id,
        entity_type="plugin",
        entity_name="manifest",
        event_type="sync",
        actor_user_id=user.user_id,
        after=f"reseeded from bundled v{BUNDLED_PLUGIN_VERSION}",
    )
    return {"status": "reseeded", "version": BUNDLED_PLUGIN_VERSION}


@router.get("/plugin/status")
async def admin_plugin_status(user: UserContext = Depends(get_user_from_header)):
    """Return PLUGIN# manifest version, seed date, and entity counts."""
    manifest = get_plugin_manifest()
    agents = list_plugin_entities("agents")
    skills = list_plugin_entities("skills")
    templates = list_plugin_entities("templates")
    return {
        "manifest": manifest,
        "counts": {"agents": len(agents), "skills": len(skills), "templates": len(templates)},
    }


@router.get("/plugin/{entity_type}")
async def admin_list_plugin_entities(
    entity_type: str,
    user: UserContext = Depends(get_user_from_header),
):
    """List all PLUGIN# items for the given entity type."""
    return list_plugin_entities(entity_type)


@router.get("/plugin/{entity_type}/{name}")
async def admin_get_plugin_entity(
    entity_type: str,
    name: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Get a single PLUGIN# entity by type and name."""
    item = get_plugin_item(entity_type, name)
    if not item:
        raise HTTPException(status_code=404, detail=f"Plugin entity not found: {entity_type}/{name}")
    return item


@router.put("/plugin/{entity_type}/{name}")
async def admin_put_plugin_entity(
    entity_type: str,
    name: str,
    body: Dict[str, Any],
    user: UserContext = Depends(get_user_from_header),
):
    """Update a PLUGIN# entity content. Writes an AUDIT# entry."""
    existing = get_plugin_item(entity_type, name)
    item = put_plugin_item(
        entity_type=entity_type,
        name=name,
        content=body.get("content", ""),
        metadata=body.get("metadata"),
        content_type=body.get("content_type", "markdown"),
    )
    write_audit(
        tenant_id=user.tenant_id,
        entity_type=f"plugin_{entity_type}",
        entity_name=name,
        event_type="update",
        actor_user_id=user.user_id,
        before=existing.get("content") if existing else None,
        after=item.get("content"),
    )
    _plugin_cache.pop(entity_type, None)
    return item


# ══════════════════════════════════════════════════════════════════════
# PROMPT OVERRIDES
# ══════════════════════════════════════════════════════════════════════


@router.get("/prompts")
async def list_admin_prompts(user: UserContext = Depends(get_user_from_header)):
    """List all tenant-level prompt overrides."""
    return list_tenant_prompts(user.tenant_id)


@router.put("/prompts/{agent_name}")
async def set_admin_prompt(
    agent_name: str,
    body: Dict[str, Any],
    user: UserContext = Depends(get_user_from_header),
):
    """Set a tenant-level prompt override for an agent."""
    existing = get_prompt(user.tenant_id, agent_name)
    item = put_prompt(
        tenant_id=user.tenant_id,
        agent_name=agent_name,
        prompt_body=body.get("prompt_body", ""),
        is_append=body.get("is_append", False),
        updated_by=user.user_id,
    )
    write_audit(
        tenant_id=user.tenant_id,
        entity_type="prompt",
        entity_name=agent_name,
        event_type="update",
        actor_user_id=user.user_id,
        before=existing.get("prompt_body") if existing else None,
        after=item.get("prompt_body"),
    )
    _prompt_cache.pop(f"{user.tenant_id}#{agent_name}", None)
    return item


@router.delete("/prompts/{agent_name}")
async def delete_admin_prompt(
    agent_name: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Delete a tenant prompt override (reverts to PLUGIN# canonical)."""
    ok = delete_prompt(user.tenant_id, agent_name)
    _prompt_cache.pop(f"{user.tenant_id}#{agent_name}", None)
    return {"deleted": ok}


# ══════════════════════════════════════════════════════════════════════
# RUNTIME CONFIG
# ══════════════════════════════════════════════════════════════════════


@router.get("/config")
async def get_all_config(user: UserContext = Depends(get_user_from_header)):
    """Return all CONFIG# runtime feature flags."""
    return list_config()


@router.put("/config/{key}")
async def set_config_key(
    key: str,
    body: Dict[str, Any],
    user: UserContext = Depends(get_user_from_header),
):
    """Set a CONFIG# runtime value."""
    item = put_config(key=key, value=body.get("value"), updated_by=user.user_id)
    write_audit(
        tenant_id=user.tenant_id,
        entity_type="config",
        entity_name=key,
        event_type="update",
        actor_user_id=user.user_id,
        after=str(body.get("value")),
    )
    return item


@router.delete("/config/{key}")
async def delete_config_key(
    key: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Delete a CONFIG# key (reverts to hardcoded default)."""
    ok = delete_config(key)
    return {"deleted": ok}


# ══════════════════════════════════════════════════════════════════════
# TEST RUNS (from eval suite)
# ══════════════════════════════════════════════════════════════════════


@router.get("/test-runs")
async def list_test_runs_endpoint(limit: int = 20):
    """List recent test runs from DynamoDB."""
    from ..test_result_store import list_test_runs

    runs = list_test_runs(limit=limit)
    return {"runs": runs, "count": len(runs)}


@router.get("/test-runs/{run_id}")
async def get_test_run_detail(run_id: str):
    """Get individual test results for a specific run."""
    from ..test_result_store import get_test_run_results

    results = get_test_run_results(run_id)
    return {"run_id": run_id, "results": results, "count": len(results)}
