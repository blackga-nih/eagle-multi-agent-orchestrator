"""
MCP (Model Context Protocol) API Router

Provides endpoints for MCP tool integration, currently supporting weather tools.
"""

from fastapi import APIRouter, Depends, HTTPException

from ..auth import get_current_user

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


@router.get("/weather/tools")
async def get_available_weather_tools(current_user: dict = Depends(get_current_user)):
    """Get available weather MCP tools for current subscription tier."""
    try:
        from ..weather_mcp_service import WeatherMCPClient

        weather_client = WeatherMCPClient()
        tier = current_user["subscription_tier"]
        weather_tools = await weather_client.get_available_weather_tools(tier)
        return {"subscription_tier": tier.value, "weather_tools": weather_tools}
    except ImportError:
        return {
            "subscription_tier": "unknown",
            "weather_tools": [],
            "note": "Weather MCP not available",
        }


@router.post("/weather/{tool_name}")
async def execute_weather_mcp_tool(
    tool_name: str,
    arguments: dict,
    current_user: dict = Depends(get_current_user),
):
    """Execute weather MCP tool if subscription tier allows it."""
    try:
        from ..weather_mcp_service import WeatherMCPClient

        weather_client = WeatherMCPClient()
        tier = current_user["subscription_tier"]
        result = await weather_client.execute_weather_tool(tool_name, arguments, tier)
        return {
            "tool_name": tool_name,
            "subscription_tier": tier.value,
            "result": result,
        }
    except ImportError:
        raise HTTPException(status_code=503, detail="Weather MCP service not available")
