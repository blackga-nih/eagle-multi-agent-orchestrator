"""
Tenants API Router

Provides endpoints for tenant-level operations:
- Usage metrics
- Cost attribution
- Subscription info
- Sessions list
- Analytics
"""

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException

from ..auth import get_current_user
from ..session_store import get_tenant_usage_overview, list_tenant_sessions
from ..subscription_service import SubscriptionService
from ..cost_attribution import CostAttributionService

router = APIRouter(prefix="/api/tenants", tags=["tenants"])

# Service instances (initialized once per process)
_subscription_service = SubscriptionService()
_cost_service = CostAttributionService()

GENERIC_ANALYTICS_ERROR = "Analytics data is temporarily unavailable."


def _get_result_error(result: Any) -> Optional[str]:
    if isinstance(result, dict):
        error = result.get("error")
        if isinstance(error, str) and error:
            return error
    return None


def _sanitize_result_error(
    result: Dict[str, Any], fallback_error: str
) -> Dict[str, Any]:
    sanitized = dict(result)
    sanitized["error"] = fallback_error
    return sanitized


@router.get("/{tenant_id}/usage")
async def get_tenant_usage(
    tenant_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get usage metrics for authenticated tenant."""
    if tenant_id != current_user["tenant_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    result = get_tenant_usage_overview(tenant_id)
    error = _get_result_error(result)
    return _sanitize_result_error(result, GENERIC_ANALYTICS_ERROR) if error else result


@router.get("/{tenant_id}/costs")
async def get_tenant_costs(
    tenant_id: str,
    days: int = 30,
    current_user: dict = Depends(get_current_user),
):
    """Get cost attribution for tenant."""
    if tenant_id != current_user["tenant_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    costs = await _cost_service.calculate_tenant_costs(tenant_id, start_date, end_date)
    return costs


@router.get("/{tenant_id}/users/{user_id}/costs")
async def get_user_costs(
    tenant_id: str,
    user_id: str,
    days: int = 30,
    current_user: dict = Depends(get_current_user),
):
    """Get cost attribution for specific user."""
    if tenant_id != current_user["tenant_id"] or user_id != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    costs = await _cost_service.calculate_user_costs(
        tenant_id, user_id, start_date, end_date
    )
    return costs


@router.get("/{tenant_id}/subscription")
async def get_subscription_info(
    tenant_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get subscription tier information and usage limits."""
    if tenant_id != current_user["tenant_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    tier = current_user["subscription_tier"]
    limits = _subscription_service.get_tier_limits(tier)
    usage = await _subscription_service.get_usage(tenant_id, tier)
    usage_limits = await _subscription_service.check_usage_limits(tenant_id, tier)
    return {
        "tenant_id": tenant_id,
        "subscription_tier": tier.value,
        "limits": limits.dict(),
        "current_usage": usage.dict(),
        "limit_status": usage_limits,
    }


@router.get("/{tenant_id}/sessions")
async def get_tenant_sessions(
    tenant_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get all sessions for authenticated tenant."""
    if tenant_id != current_user["tenant_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    return {
        "tenant_id": tenant_id,
        "sessions": list_tenant_sessions(tenant_id),
    }


@router.get("/{tenant_id}/analytics")
async def get_tenant_analytics(
    tenant_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get enhanced analytics with trace data for authenticated tenant."""
    if tenant_id != current_user["tenant_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    usage_data = get_tenant_usage_overview(tenant_id)
    if _get_result_error(usage_data):
        usage_data = _sanitize_result_error(usage_data, GENERIC_ANALYTICS_ERROR)
    tier = current_user["subscription_tier"]
    analytics = {
        "tenant_id": tenant_id,
        "subscription_tier": tier.value,
        "total_interactions": usage_data.get("total_messages", 0),
        "active_sessions": usage_data.get("sessions", 0),
        "processing_patterns": {
            "agent_invocations": len(
                [
                    m
                    for m in usage_data.get("metrics", [])
                    if m.get("metric_type") == "agent_invocation"
                ]
            ),
            "trace_analyses": len(
                [
                    m
                    for m in usage_data.get("metrics", [])
                    if m.get("metric_type") == "trace_analysis"
                ]
            ),
        },
        "resource_breakdown": {
            "model_invocations": usage_data.get("total_messages", 0),
            "knowledge_base_queries": 0,
            "action_group_calls": 0,
        },
        "tier_specific_metrics": {
            "mcp_tools_available": _subscription_service.get_tier_limits(
                tier
            ).mcp_server_access,
            "usage_limits": _subscription_service.get_tier_limits(tier).dict(),
        },
    }
    if usage_data.get("error"):
        analytics["error"] = GENERIC_ANALYTICS_ERROR
    return analytics
