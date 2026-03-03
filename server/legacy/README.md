# Legacy Code Archive

These files are archived legacy code superseded by the current architecture.

They are preserved here for reference but are no longer imported or executed
by the application. Do not import from this directory in production code.

| File | Superseded by |
|------|---------------|
| `auth.py` | `app/cognito_auth.py` — EAGLE Cognito JWT auth with DEV_MODE support |
| `weather_mcp_service.py` | Removed: weather MCP endpoints deleted in codebase cleanup |
| `mcp_agent_integration.py` | `app/sdk_agentic_service.py` — Claude Agent SDK orchestration |
| `gateway_client.py` | Direct Anthropic SDK usage via `app/sdk_agentic_service.py` |
