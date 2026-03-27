"""
EAGLE Business Tools MCP Server

Exposes the execute_tool() dispatcher from agentic_service.py as a local
MCP server so that SDK skill subagents can call S3, DynamoDB, CloudWatch,
and document generation tools.

Tools exposed:
  - s3_document_ops       (read/write/list S3 documents)
  - dynamodb_intake       (create/read/update/list intake records)
  - cloudwatch_logs       (search/read CloudWatch log streams)
  - create_document       (generate SOW/IGCE/AP/J&A etc. and save to S3)
  - get_intake_status     (check intake package completeness)
  - intake_workflow       (advance workflow stages)
  - search_far            (search FAR/DFARS database)

Usage:
    from app.eagle_tools_mcp import create_eagle_mcp_server

    mcp_server = create_eagle_mcp_server(tenant_id="nci-oa", session_id="nci-oa-premium-u1-s1")
    options = ClaudeAgentOptions(
        ...
        mcp_servers={"eagle-tools": mcp_server},
    )
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

# Import through a compatibility boundary so active code no longer depends on
# the deprecated agentic_service module path directly.
try:
    from .tools.legacy_dispatch import execute_tool as _execute_tool
except ImportError:
    # Allow running outside the package (e.g., in tests)
    import sys
    import os
    _app_dir = os.path.dirname(os.path.abspath(__file__))
    if _app_dir not in sys.path:
        sys.path.insert(0, _app_dir)
    from tools.legacy_dispatch import execute_tool as _execute_tool

logger = logging.getLogger("eagle.tools_mcp")


# ── Input dataclasses for each exposed tool ─────────────────────────


@dataclass
class S3DocumentOpsInput:
    action: str
    key: str = ""
    content: str = ""
    prefix: str = ""
    destination_key: str = ""
    expiry_seconds: int = 3600


@dataclass
class DynamoDBIntakeInput:
    action: str
    intake_id: str = ""
    tenant_id: str = ""
    data: dict = None
    item_ids: str = ""
    items: list = None

    def __post_init__(self):
        if self.data is None:
            self.data = {}
        if self.items is None:
            self.items = []


@dataclass
class CloudWatchLogsInput:
    action: str
    log_group: str = ""
    log_stream: str = ""
    query: str = ""
    limit: int = 20
    prefix: str = ""


@dataclass
class CreateDocumentInput:
    doc_type: str
    title: str = ""
    content: dict = None
    save_to_s3: bool = True

    def __post_init__(self):
        if self.content is None:
            self.content = {}


@dataclass
class GetIntakeStatusInput:
    intake_id: str


@dataclass
class IntakeWorkflowInput:
    action: str
    intake_id: str = ""
    stage: str = ""
    data: dict = None

    def __post_init__(self):
        if self.data is None:
            self.data = {}


@dataclass
class SearchFARInput:
    query: str
    part: str = ""
    subpart: str = ""


# ── MCP server factory ───────────────────────────────────────────────


def create_eagle_mcp_server(
    tenant_id: str = "demo-tenant",
    session_id: str | None = None,
):
    """Create a local MCP server that exposes EAGLE business tools.

    Each tool delegates to execute_tool() from agentic_service.py.
    The tenant_id and session_id are injected into every tool call for
    per-tenant scoping and audit trail consistency.

    Args:
        tenant_id: Tenant identifier used to scope all tool calls.
        session_id: Session identifier used for per-user document scoping.

    Returns:
        An MCP server instance compatible with ClaudeAgentOptions.mcp_servers.
    """
    # Capture tenant/session in closure for all tool handlers
    _tenant_id = tenant_id
    _session_id = session_id or f"{tenant_id}-sdk-session"

    @tool(
        "s3_document_ops",
        "Read, write, list, delete, copy, rename, move, check existence, or generate presigned URLs for acquisition documents in the EAGLE S3 document store.",
        S3DocumentOpsInput,
    )
    async def s3_document_ops_tool(inp: S3DocumentOpsInput) -> dict[str, Any]:
        tool_input = {
            "action": inp.action,
            "key": inp.key,
            "content": inp.content,
            "prefix": inp.prefix,
            "destination_key": inp.destination_key,
            "expiry_seconds": inp.expiry_seconds,
        }
        result_json = _execute_tool("s3_document_ops", tool_input, _session_id)
        return {"content": [{"type": "text", "text": result_json}]}

    @tool(
        "dynamodb_intake",
        "Create, read, update, delete, list, query, count, batch_get, or batch_write intake records in the EAGLE DynamoDB table.",
        DynamoDBIntakeInput,
    )
    async def dynamodb_intake_tool(inp: DynamoDBIntakeInput) -> dict[str, Any]:
        tool_input = {
            "action": inp.action,
            "intake_id": inp.intake_id,
            "tenant_id": _tenant_id,
            "data": inp.data,
            "item_ids": inp.item_ids,
            "items": inp.items,
        }
        result_json = _execute_tool("dynamodb_intake", tool_input, _session_id)
        return {"content": [{"type": "text", "text": result_json}]}

    @tool(
        "cloudwatch_logs",
        "Search, read, run Logs Insights queries, or list log groups for EAGLE audit trails and session logs.",
        CloudWatchLogsInput,
    )
    async def cloudwatch_logs_tool(inp: CloudWatchLogsInput) -> dict[str, Any]:
        tool_input = {
            "action": inp.action,
            "log_group": inp.log_group,
            "log_stream": inp.log_stream,
            "query": inp.query,
            "limit": inp.limit,
            "prefix": inp.prefix,
        }
        result_json = _execute_tool("cloudwatch_logs", tool_input, _session_id)
        return {"content": [{"type": "text", "text": result_json}]}

    @tool(
        "create_document",
        "Generate a formal acquisition document (SOW, IGCE, AP, J&A, etc.) and optionally save to S3.",
        CreateDocumentInput,
    )
    async def create_document_tool(inp: CreateDocumentInput) -> dict[str, Any]:
        tool_input = {
            "doc_type": inp.doc_type,
            "title": inp.title,
            "content": inp.content,
            "save_to_s3": inp.save_to_s3,
        }
        result_json = _execute_tool("create_document", tool_input, _session_id)
        return {"content": [{"type": "text", "text": result_json}]}

    @tool(
        "get_intake_status",
        "Check the completeness and workflow status of an EAGLE intake package.",
        GetIntakeStatusInput,
    )
    async def get_intake_status_tool(inp: GetIntakeStatusInput) -> dict[str, Any]:
        tool_input = {"intake_id": inp.intake_id}
        result_json = _execute_tool("get_intake_status", tool_input, _session_id)
        return {"content": [{"type": "text", "text": result_json}]}

    @tool(
        "intake_workflow",
        "Advance an intake package through workflow stages (submit, approve, reject, etc.).",
        IntakeWorkflowInput,
    )
    async def intake_workflow_tool(inp: IntakeWorkflowInput) -> dict[str, Any]:
        tool_input = {
            "action": inp.action,
            "intake_id": inp.intake_id,
            "stage": inp.stage,
            "data": inp.data,
        }
        result_json = _execute_tool("intake_workflow", tool_input, _session_id)
        return {"content": [{"type": "text", "text": result_json}]}

    @tool(
        "search_far",
        "Search the FAR/DFARS regulation database for clauses, parts, and subparts.",
        SearchFARInput,
    )
    async def search_far_tool(inp: SearchFARInput) -> dict[str, Any]:
        tool_input = {
            "query": inp.query,
            "part": inp.part,
            "subpart": inp.subpart,
        }
        result_json = _execute_tool("search_far", tool_input, _session_id)
        return {"content": [{"type": "text", "text": result_json}]}

    return create_sdk_mcp_server(
        "eagle-tools",
        tools=[
            s3_document_ops_tool,
            dynamodb_intake_tool,
            cloudwatch_logs_tool,
            create_document_tool,
            get_intake_status_tool,
            intake_workflow_tool,
            search_far_tool,
        ],
    )
