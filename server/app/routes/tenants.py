"""Tenant usage, costs, subscription, analytics, and weather MCP endpoints."""

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException

from ..auth import get_current_user
from ..subscription_service import SubscriptionService
from ..cost_attribution import CostAttributionService
from ..stores.session_store import get_tenant_usage_overview, list_tenant_sessions

logger = logging.getLogger("eagle")
router = APIRouter(tags=["tenants"])

# ── Service instances ─────────────────────────────────────────────────
subscription_service = SubscriptionService()
cost_service = CostAttributionService()


# ── Tenant usage & cost endpoints ─────────────────────────────────────

@router.get("/api/tenants/{tenant_id}/usage")
async def get_tenant_usage(tenant_id: str, current_user: dict = Depends(get_current_user)):
    """Get usage metrics for authenticated tenant"""
    if tenant_id != current_user["tenant_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    return get_tenant_usage_overview(tenant_id)


@router.get("/api/tenants/{tenant_id}/costs")
async def get_tenant_costs(tenant_id: str, days: int = 30, current_user: dict = Depends(get_current_user)):
    """Get cost attribution for tenant"""
    if tenant_id != current_user["tenant_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    costs = await cost_service.calculate_tenant_costs(tenant_id, start_date, end_date)
    return costs


@router.get("/api/tenants/{tenant_id}/users/{user_id}/costs")
async def get_user_costs(tenant_id: str, user_id: str, days: int = 30, current_user: dict = Depends(get_current_user)):
    """Get cost attribution for specific user"""
    if tenant_id != current_user["tenant_id"] or user_id != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    costs = await cost_service.calculate_user_costs(tenant_id, user_id, start_date, end_date)
    return costs


@router.get("/api/tenants/{tenant_id}/subscription")
async def get_subscription_info(tenant_id: str, current_user: dict = Depends(get_current_user)):
    """Get subscription tier information and usage limits"""
    if tenant_id != current_user["tenant_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    tier = current_user["subscription_tier"]
    limits = subscription_service.get_tier_limits(tier)
    usage = await subscription_service.get_usage(tenant_id, tier)
    usage_limits = await subscription_service.check_usage_limits(tenant_id, tier)
    return {
        "tenant_id": tenant_id,
        "subscription_tier": tier.value,
        "limits": limits.dict(),
        "current_usage": usage.dict(),
        "limit_status": usage_limits
    }


@router.get("/api/tenants/{tenant_id}/sessions")
async def get_tenant_sessions(tenant_id: str, current_user: dict = Depends(get_current_user)):
    """Get all sessions for authenticated tenant"""
    if tenant_id != current_user["tenant_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    return {
        "tenant_id": tenant_id,
        "sessions": list_tenant_sessions(tenant_id)
    }


@router.get("/api/tenants/{tenant_id}/analytics")
async def get_tenant_analytics(tenant_id: str, current_user: dict = Depends(get_current_user)):
    """Get enhanced analytics with trace data for authenticated tenant"""
    if tenant_id != current_user["tenant_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    usage_data = get_tenant_usage_overview(tenant_id)
    tier = current_user["subscription_tier"]
    analytics = {
        "tenant_id": tenant_id,
        "subscription_tier": tier.value,
        "total_interactions": usage_data.get("total_messages", 0),
        "active_sessions": usage_data.get("sessions", 0),
        "processing_patterns": {
            "agent_invocations": len([m for m in usage_data.get("metrics", []) if m.get("metric_type") == "agent_invocation"]),
            "trace_analyses": len([m for m in usage_data.get("metrics", []) if m.get("metric_type") == "trace_analysis"])
        },
        "resource_breakdown": {
            "model_invocations": usage_data.get("total_messages", 0),
            "knowledge_base_queries": 0,
            "action_group_calls": 0
        },
        "tier_specific_metrics": {
            "mcp_tools_available": subscription_service.get_tier_limits(tier).mcp_server_access,
            "usage_limits": subscription_service.get_tier_limits(tier).dict()
        }
    }
    return analytics


# ── Weather MCP endpoints (compatibility) ─────────────────────────────

@router.get("/api/mcp/weather/tools")
async def get_available_weather_tools(current_user: dict = Depends(get_current_user)):
    """Get available weather MCP tools for current subscription tier"""
    try:
        from ..weather_mcp_service import WeatherMCPClient
        weather_client = WeatherMCPClient()
        tier = current_user["subscription_tier"]
        weather_tools = await weather_client.get_available_weather_tools(tier)
        return {"subscription_tier": tier.value, "weather_tools": weather_tools}
    except ImportError:
        return {"subscription_tier": "unknown", "weather_tools": [], "note": "Weather MCP not available"}


@router.post("/api/mcp/weather/{tool_name}")
async def execute_weather_mcp_tool(tool_name: str, arguments: dict, current_user: dict = Depends(get_current_user)):
    """Execute weather MCP tool if subscription tier allows it"""
    try:
        from ..weather_mcp_service import WeatherMCPClient
        weather_client = WeatherMCPClient()
        tier = current_user["subscription_tier"]
        result = await weather_client.execute_weather_tool(tool_name, arguments, tier)
        return {"tool_name": tool_name, "subscription_tier": tier.value, "result": result}
    except ImportError:
        raise HTTPException(status_code=503, detail="Weather MCP service not available")
