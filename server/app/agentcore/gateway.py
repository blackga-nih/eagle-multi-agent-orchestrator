"""
AgentCore Gateway Service — auto-discovers tools from MCP Gateway
instead of manual tool registration.

When AGENTCORE_GATEWAY_ID is set, tools are fetched from the Gateway's
MCP endpoint with semantic search. Falls back to manual TOOL_DISPATCH
when Gateway is unavailable.
"""

import json
import logging
import os
from typing import Any

logger = logging.getLogger("eagle.agentcore_gateway")

_REGION = os.getenv("AWS_REGION", "us-east-1")
_GATEWAY_ID = os.getenv("AGENTCORE_GATEWAY_ID", "")

# Lazy singleton
_gateway_client = None


def _get_gateway_client():
    """Lazy-init AgentCore Gateway MCP client."""
    global _gateway_client
    if _gateway_client is not None:
        return _gateway_client

    if not _GATEWAY_ID:
        logger.info("AGENTCORE_GATEWAY_ID not set — using manual tool registration")
        return None

    try:
        import boto3
        _gateway_client = boto3.client("bedrock-agentcore-control", region_name=_REGION)
        logger.info("AgentCore Gateway client initialized (gateway_id=%s)", _GATEWAY_ID)
        return _gateway_client
    except Exception as exc:
        logger.warning("AgentCore Gateway unavailable: %s — using manual tool registration", exc)
        return None


def is_gateway_available() -> bool:
    """Check if Gateway is configured and reachable."""
    return _get_gateway_client() is not None and bool(_GATEWAY_ID)


def list_gateway_tools() -> list[dict[str, Any]]:
    """List all tools available through the Gateway MCP endpoint.

    Returns tools in Anthropic tool_use format for compatibility with
    existing EAGLE_TOOLS schema.
    """
    client = _get_gateway_client()
    if not client:
        return []

    try:
        response = client.get_gateway(gatewayIdentifier=_GATEWAY_ID)
        targets = response.get("targets", [])

        tools = []
        for target in targets:
            tool_name = target.get("name", "")
            tool_desc = target.get("description", "")
            tool_schema = target.get("inputSchema", {})

            tools.append({
                "name": tool_name,
                "description": tool_desc,
                "input_schema": tool_schema,
                "source": "gateway",
            })

        logger.info("Gateway returned %d tools", len(tools))
        return tools

    except Exception as exc:
        logger.warning("Failed to list Gateway tools: %s", exc)
        return []


def invoke_gateway_tool(
    tool_name: str,
    tool_input: dict,
    tenant_id: str,
    user_id: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Invoke a tool through the AgentCore Gateway.

    The Gateway handles OAuth credential exchange and routes the
    request to the appropriate target (Lambda, API, etc.).
    """
    try:
        import boto3
        data_client = boto3.client("bedrock-agentcore", region_name=_REGION)

        response = data_client.invoke_gateway(
            gatewayIdentifier=_GATEWAY_ID,
            toolName=tool_name,
            input=json.dumps(tool_input),
            context={
                "tenantId": tenant_id,
                "userId": user_id,
                "sessionId": session_id or "",
            },
        )

        result_str = response.get("output", "{}")
        return json.loads(result_str) if isinstance(result_str, str) else result_str

    except Exception as exc:
        logger.error("Gateway invocation failed for %s: %s", tool_name, exc)
        return {"error": f"Gateway invocation failed: {str(exc)}", "tool": tool_name}


def create_gateway_tool_handler(tool_name: str, tenant_id: str, user_id: str, session_id: str | None = None):
    """Create a Strands @tool function that routes through the Gateway.

    Used by _build_service_tools() when Gateway is available to replace
    manual TOOL_DISPATCH handlers.
    """
    try:
        from strands import tool as strands_tool
    except ImportError:
        return None

    @strands_tool(name=tool_name)
    def gateway_tool(params: str) -> str:
        """Gateway-routed tool (docstring replaced below)."""
        parsed = json.loads(params) if isinstance(params, str) else params
        result = invoke_gateway_tool(tool_name, parsed, tenant_id, user_id, session_id)
        return json.dumps(result, indent=2, default=str)

    return gateway_tool
