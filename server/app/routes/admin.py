"""Admin endpoints — dashboard, KB reviews, cost reports, plugin CRUD, prompts, config, test runs."""

import os
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException

from ..cognito_auth import UserContext
from ..admin_service import (
    get_dashboard_stats, get_top_users, get_user_stats, get_tool_usage,
    check_rate_limit,
)
from ..admin_auth import get_admin_user, verify_tenant_admin
from ..cost_attribution import CostAttributionService
from ..admin_cost_service import AdminCostService
from ..stores.plugin_store import (
    get_plugin_item, put_plugin_item, list_plugin_entities,
    get_plugin_manifest, ensure_plugin_seeded,
    _entity_cache as _plugin_cache,
)
from ..stores.prompt_store import (
    put_prompt, get_prompt, delete_prompt, list_tenant_prompts,
    _prompt_cache,
)
from ..stores.config_store import (
    put_config, delete_config, list_config,
    _config_cache,
)
from ..stores.template_store import _template_cache
from ..stores.audit_store import write_audit
from ._deps import get_user_from_header, get_session_context, S3_BUCKET

logger = logging.getLogger("eagle")
router = APIRouter(tags=["admin"])

# ── Service instances ─────────────────────────────────────────────────
cost_service = CostAttributionService()
admin_cost_service = AdminCostService()


# ── Dashboard & Analytics ─────────────────────────────────────────────

@router.get("/api/admin/dashboard")
async def api_admin_dashboard(
    days: int = 30,
    user: UserContext = Depends(get_user_from_header)
):
    """Get admin dashboard statistics."""
    tenant_id = user.tenant_id
    return get_dashboard_stats(tenant_id, days)


@router.get("/api/admin/users")
async def api_admin_users(
    days: int = 30,
    limit: int = 10,
    user: UserContext = Depends(get_user_from_header)
):
    """Get top users by usage."""
    tenant_id = user.tenant_id
    return {"users": get_top_users(tenant_id, days, limit)}


@router.get("/api/admin/users/{target_user_id}")
async def api_admin_user_stats(
    target_user_id: str,
    days: int = 30,
    user: UserContext = Depends(get_user_from_header)
):
    """Get stats for a specific user."""
    tenant_id = user.tenant_id
    return get_user_stats(tenant_id, target_user_id, days)


@router.get("/api/admin/tools")
async def api_admin_tools(
    days: int = 30,
    user: UserContext = Depends(get_user_from_header)
):
    """Get tool usage analytics."""
    tenant_id = user.tenant_id
    return get_tool_usage(tenant_id, days)


@router.get("/api/admin/rate-limit")
async def api_check_rate_limit(user: UserContext = Depends(get_user_from_header)):
    """Check current rate limit status."""
    tenant_id, user_id, _ = get_session_context(user)
    return check_rate_limit(tenant_id, user_id, user.tier)


# ── KB Review endpoints ───────────────────────────────────────────────

def _get_dynamo():
    import boto3
    return boto3.resource("dynamodb", region_name=os.getenv("AWS_REGION", "us-east-1"))


@router.get("/api/admin/kb-reviews")
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


@router.post("/api/admin/kb-review/{review_id}/approve")
async def api_approve_kb_review(
    review_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Approve a KB review: apply diff to matrix.json, update HTML, move doc to approved/."""
    import boto3
    from botocore.exceptions import ClientError

    table_name = os.getenv("METADATA_TABLE", "eagle-document-metadata-dev")
    bucket = S3_BUCKET
    ddb = _get_dynamo()
    table = ddb.Table(table_name)
    s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-east-1"))

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

    matrix_path = Path(__file__).resolve().parent.parent.parent.parent.parent / "eagle-plugin" / "data" / "matrix.json"
    if matrix_path.exists():
        try:
            matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
            matrix = _apply_json_patch(matrix, proposed_diff)
            matrix["version"] = datetime.utcnow().strftime("%Y-%m-%d")
            matrix_path.write_text(json.dumps(matrix, indent=2, ensure_ascii=False), encoding="utf-8")
            logger.info("matrix.json updated after KB review %s", review_id)
            _regenerate_html_arrays(matrix)
        except Exception as e:
            logger.warning("matrix.json patch failed (non-fatal): %s", e)
    else:
        logger.warning("matrix.json not found at %s — skipping patch", matrix_path)

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


@router.post("/api/admin/kb-review/{review_id}/reject")
async def api_reject_kb_review(
    review_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Reject a KB review: mark rejected, move doc to rejected/."""
    import boto3
    from botocore.exceptions import ClientError

    table_name = os.getenv("METADATA_TABLE", "eagle-document-metadata-dev")
    bucket = S3_BUCKET
    ddb = _get_dynamo()
    table = ddb.Table(table_name)
    s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-east-1"))

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


# ── Admin Cost Reports ────────────────────────────────────────────────

@router.get("/api/admin/cost-report")
async def get_cost_report(tenant_id: str = None, days: int = 30, admin_user: dict = Depends(get_admin_user)):
    """Generate comprehensive cost report (admin only)"""
    report = await cost_service.generate_cost_report(tenant_id, days)
    return report


@router.get("/api/admin/tier-costs/{tier}")
async def get_tier_costs(tier: str, days: int = 30, admin_user: dict = Depends(get_admin_user)):
    """Get cost breakdown by subscription tier (admin only)"""
    from ..models import SubscriptionTier
    subscription_tier = SubscriptionTier(tier)
    costs = await cost_service.get_subscription_tier_costs(subscription_tier, days)
    return costs


@router.get("/api/admin/tenants/{tenant_id}/overall-cost")
async def get_admin_tenant_overall_cost(tenant_id: str, days: int = 30, admin_user: dict = Depends(verify_tenant_admin)):
    """1. Overall Tenant Cost - Admin Only"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    costs = await admin_cost_service.get_tenant_overall_cost(tenant_id, start_date, end_date)
    return costs


@router.get("/api/admin/tenants/{tenant_id}/per-user-cost")
async def get_admin_per_user_cost(tenant_id: str, days: int = 30, admin_user: dict = Depends(verify_tenant_admin)):
    """2. Per User Cost - Admin Only"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    costs = await admin_cost_service.get_tenant_per_user_cost(tenant_id, start_date, end_date)
    return costs


@router.get("/api/admin/tenants/{tenant_id}/service-wise-cost")
async def get_admin_service_wise_cost(tenant_id: str, days: int = 30, admin_user: dict = Depends(verify_tenant_admin)):
    """3. Overall Tenant Service-wise Consumption Cost - Admin Only"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    costs = await admin_cost_service.get_tenant_service_wise_cost(tenant_id, start_date, end_date)
    return costs


@router.get("/api/admin/tenants/{tenant_id}/users/{user_id}/service-cost")
async def get_admin_user_service_cost(tenant_id: str, user_id: str, days: int = 30, admin_user: dict = Depends(verify_tenant_admin)):
    """4. User Service-wise Consumption Cost - Admin Only"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    costs = await admin_cost_service.get_user_service_wise_cost(tenant_id, user_id, start_date, end_date)
    return costs


@router.get("/api/admin/tenants/{tenant_id}/comprehensive-report")
async def get_comprehensive_admin_report(tenant_id: str, days: int = 30, admin_user: dict = Depends(verify_tenant_admin)):
    """Comprehensive Admin Cost Report - All 4 breakdowns"""
    report = await admin_cost_service.generate_comprehensive_admin_report(tenant_id, days)
    return report


@router.get("/api/admin/my-tenants")
async def get_admin_tenants(admin_user: dict = Depends(get_admin_user)):
    """Get tenants where current user has admin access"""
    return {
        "admin_email": admin_user["email"],
        "admin_tenants": admin_user["admin_tenants"]
    }


@router.post("/api/admin/add-to-group")
async def add_user_to_admin_group(request: dict):
    """Add user to admin group during registration"""
    from app.admin_auth import AdminAuthService

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
            Description=f"{tenant_id.title()} Administrators"
        )
    except Exception:
        pass

    try:
        admin_service_instance.cognito_client.admin_add_user_to_group(
            UserPoolId=admin_service_instance.user_pool_id,
            Username=email,
            GroupName=f"{tenant_id}-admins"
        )
        return {"success": True, "message": f"Added {email} to {tenant_id}-admins group"}
    except Exception as e:
        logger.error("Failed to add user to admin group: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to add user to admin group")


# ── Cache Flush ───────────────────────────────────────────────────────

@router.post("/api/admin/reload")
async def admin_reload_caches(user: UserContext = Depends(get_user_from_header)):
    """Force-flush all in-process caches."""
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


@router.post("/api/admin/plugin/sync")
async def admin_plugin_sync(user: UserContext = Depends(get_user_from_header)):
    """Force reseed all PLUGIN# entities from bundled eagle-plugin/ files (factory reset)."""
    from ..stores.plugin_store import BUNDLED_PLUGIN_VERSION
    try:
        from ..stores.plugin_store import _get_table
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


# ── Plugin Entity CRUD ────────────────────────────────────────────────

@router.get("/api/admin/plugin/status")
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


@router.get("/api/admin/plugin/{entity_type}")
async def admin_list_plugin_entities(
    entity_type: str,
    user: UserContext = Depends(get_user_from_header),
):
    """List all PLUGIN# items for the given entity type."""
    return list_plugin_entities(entity_type)


@router.get("/api/admin/plugin/{entity_type}/{name}")
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


@router.put("/api/admin/plugin/{entity_type}/{name}")
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


# ── Admin Prompt Overrides ────────────────────────────────────────────

@router.get("/api/admin/prompts")
async def list_admin_prompts(user: UserContext = Depends(get_user_from_header)):
    """List all tenant-level prompt overrides."""
    return list_tenant_prompts(user.tenant_id)


@router.put("/api/admin/prompts/{agent_name}")
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


@router.delete("/api/admin/prompts/{agent_name}")
async def delete_admin_prompt(
    agent_name: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Delete a tenant prompt override (reverts to PLUGIN# canonical)."""
    ok = delete_prompt(user.tenant_id, agent_name)
    _prompt_cache.pop(f"{user.tenant_id}#{agent_name}", None)
    return {"deleted": ok}


# ── Runtime Config ────────────────────────────────────────────────────

@router.get("/api/admin/config")
async def get_all_config(user: UserContext = Depends(get_user_from_header)):
    """Return all CONFIG# runtime feature flags."""
    return list_config()


@router.put("/api/admin/config/{key}")
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


@router.delete("/api/admin/config/{key}")
async def delete_config_key(
    key: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Delete a CONFIG# key (reverts to hardcoded default)."""
    ok = delete_config(key)
    return {"deleted": ok}


# ── Test Run Viewer ───────────────────────────────────────────────────

@router.get("/api/admin/test-runs")
async def list_test_runs_endpoint(limit: int = 20):
    """List recent test runs from DynamoDB."""
    from ..stores.test_result_store import list_test_runs
    runs = list_test_runs(limit=limit)
    return {"runs": runs, "count": len(runs)}


@router.get("/api/admin/test-runs/{run_id}")
async def get_test_run_detail(run_id: str):
    """Get individual test results for a specific run."""
    from ..stores.test_result_store import get_test_run_results
    results = get_test_run_results(run_id)
    return {"run_id": run_id, "results": results, "count": len(results)}


# ── Helper functions ──────────────────────────────────────────────────

def _apply_json_patch(obj: dict, patch: list) -> dict:
    """Apply a simplified JSON Patch (RFC 6902) to a dict. Supports replace, add, remove."""
    import copy
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
    import re as _re

    html_path = Path(__file__).resolve().parent.parent.parent.parent.parent / "contract-requirements-matrix.html"
    if not html_path.exists():
        logger.warning("contract-requirements-matrix.html not found, skipping HTML regeneration")
        return

    html = html_path.read_text(encoding="utf-8")

    thresholds_js = "const THRESHOLDS = [\n"
    for t in matrix.get("thresholds", []):
        thresholds_js += (
            f"  {{ value: {t['value']:<12} label: {json.dumps(t['label'])}, "
            f"short: {json.dumps(t['short'])} }},\n"
        )
    thresholds_js += "];"

    types_js = "const TYPES = [\n"
    for ct in matrix.get("contract_types", []):
        parts = [f"id: {json.dumps(ct['id'])}", f"label: {json.dumps(ct['label'])}",
                 f"risk: {ct['risk']}", f"category: {json.dumps(ct['category'])}"]
        if ct.get("fee_cap"):
            parts.append(f"feeCap: {json.dumps(ct['fee_cap'])}")
        if ct.get("prereqs"):
            parts.append(f"prereqs: {json.dumps(ct['prereqs'])}")
        types_js += "  { " + ", ".join(parts) + " },\n"
    types_js += "];"

    html = _re.sub(
        r"const THRESHOLDS\s*=\s*\[[\s\S]*?\];",
        thresholds_js,
        html,
    )
    html = _re.sub(
        r"const TYPES\s*=\s*\[[\s\S]*?\];",
        types_js,
        html,
    )
    html_path.write_text(html, encoding="utf-8")
    logger.info("Regenerated THRESHOLDS/TYPES in contract-requirements-matrix.html")
