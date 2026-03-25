"""Compatibility boundary for active tool handlers.

Active runtime code should import this module rather than importing the
deprecated orchestration modules directly.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from .knowledge_tools import exec_knowledge_fetch, exec_knowledge_search
from ..session_scope import extract_tenant_id
from .admin_tools import (
    exec_manage_prompts,
    exec_manage_skills,
    exec_manage_templates,
    exec_query_compliance_matrix,
)
from .aws_ops_tools import exec_cloudwatch_logs, exec_dynamodb_intake, exec_s3_document_ops
from .docx_edit_tool import exec_edit_docx_document
from .far_search import exec_search_far
from .intake_tools import exec_get_intake_status, exec_intake_workflow
from .package_document_tools import (
    exec_document_changelog_search,
    exec_finalize_package,
    exec_get_latest_document,
    exec_manage_package,
)

logger = logging.getLogger("eagle.tools.legacy_dispatch")

ToolHandler = Callable[..., dict[str, Any]]

TOOLS_NEEDING_SESSION = {
    "s3_document_ops",
    "create_document",
    "edit_docx_document",
    "get_intake_status",
    "manage_package",
}


def exec_create_document(params: dict, tenant_id: str, session_id: str | None = None) -> dict:
    from .document_generation import exec_create_document as _exec_create_document

    return _exec_create_document(params, tenant_id, session_id)


def get_tool_dispatch() -> dict[str, ToolHandler]:
    return {
        "s3_document_ops": exec_s3_document_ops,
        "dynamodb_intake": exec_dynamodb_intake,
        "cloudwatch_logs": exec_cloudwatch_logs,
        "search_far": exec_search_far,
        "create_document": exec_create_document,
        "edit_docx_document": exec_edit_docx_document,
        "get_intake_status": exec_get_intake_status,
        "intake_workflow": exec_intake_workflow,
        "query_compliance_matrix": exec_query_compliance_matrix,
        "knowledge_search": exec_knowledge_search,
        "knowledge_fetch": exec_knowledge_fetch,
        "manage_skills": exec_manage_skills,
        "manage_prompts": exec_manage_prompts,
        "manage_templates": exec_manage_templates,
        "document_changelog_search": exec_document_changelog_search,
        "get_latest_document": exec_get_latest_document,
        "finalize_package": exec_finalize_package,
        "manage_package": exec_manage_package,
    }


def execute_tool(tool_name: str, tool_input: dict, session_id: str | None = None) -> str:
    tenant_id = extract_tenant_id(session_id)
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
