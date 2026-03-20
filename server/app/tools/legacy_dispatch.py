"""Compatibility boundary for handlers still hosted in agentic_service.

Active runtime code should import this module rather than importing the
deprecated ``agentic_service`` module path directly.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from .knowledge_tools import exec_knowledge_fetch, exec_knowledge_search

logger = logging.getLogger("eagle.tools.legacy_dispatch")

ToolHandler = Callable[..., dict[str, Any]]

TOOLS_NEEDING_SESSION = {
    "s3_document_ops",
    "create_document",
    "edit_docx_document",
    "get_intake_status",
}


def _legacy_module():
    from .. import agentic_service

    return agentic_service


def exec_search_far(params: dict, tenant_id: str) -> dict:
    return _legacy_module()._exec_search_far(params, tenant_id)


def exec_create_document(params: dict, tenant_id: str, session_id: str | None = None) -> dict:
    return _legacy_module()._exec_create_document(params, tenant_id, session_id)


def get_tool_dispatch() -> dict[str, ToolHandler]:
    legacy = _legacy_module()
    return {
        "s3_document_ops": legacy._exec_s3_document_ops,
        "dynamodb_intake": legacy._exec_dynamodb_intake,
        "cloudwatch_logs": legacy._exec_cloudwatch_logs,
        "search_far": exec_search_far,
        "create_document": exec_create_document,
        "edit_docx_document": legacy._exec_edit_docx_document,
        "get_intake_status": legacy._exec_get_intake_status,
        "intake_workflow": legacy._exec_intake_workflow,
        "query_compliance_matrix": legacy._exec_query_compliance_matrix,
        "knowledge_search": exec_knowledge_search,
        "knowledge_fetch": exec_knowledge_fetch,
        "manage_skills": legacy._exec_manage_skills,
        "manage_prompts": legacy._exec_manage_prompts,
        "manage_templates": legacy._exec_manage_templates,
        "document_changelog_search": legacy._exec_document_changelog_search,
        "get_latest_document": legacy._exec_get_latest_document,
        "finalize_package": legacy._exec_finalize_package,
    }


def execute_tool(tool_name: str, tool_input: dict, session_id: str | None = None) -> str:
    legacy = _legacy_module()
    tenant_id = legacy._extract_tenant_id(session_id)
    handler = get_tool_dispatch().get(tool_name)
    if handler is None:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    try:
        if tool_name in TOOLS_NEEDING_SESSION:
            result = handler(tool_input, tenant_id, session_id)
        else:
            result = handler(tool_input, tenant_id)
        return json.dumps(result, indent=2, default=str)
    except Exception as exc:  # noqa: BLE001
        logger.error("Tool execution error (%s): %s", tool_name, exc, exc_info=True)
        return json.dumps(
            {
                "error": f"Tool execution failed: {exc}",
                "tool": tool_name,
                "suggestion": "Try again or use a different approach.",
            }
        )
