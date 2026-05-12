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
from .aws_ops_tools import (
    exec_cloudwatch_logs,
    exec_dynamodb_intake,
    exec_kb_inventory,
    exec_s3_document_ops,
)
from .batch_doc_gen_tools import (
    exec_batch_generate_documents,
    exec_get_doc_jobs,
)
from .docx_edit_tool import exec_edit_docx_document
from .far_search import exec_search_far
from .intake_approval_tools import (
    exec_confirm_intake_approval,
    exec_submit_intake_for_approval,
)
from .intake_tools import exec_get_intake_status, exec_intake_workflow
from .langfuse_tools import exec_langfuse_traces
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
    "research",
    "submit_intake_for_approval",
    "confirm_intake_approval",
    "batch_generate_documents",
    "get_doc_jobs",
}


def exec_create_document(
    params: dict, tenant_id: str, session_id: str | None = None
) -> dict:
    from .document_generation import exec_create_document as _exec_create_document

    return _exec_create_document(params, tenant_id, session_id)


def exec_research(
    params: dict, tenant_id: str, session_id: str | None = None
) -> dict:
    """Legacy dispatch wrapper for the composite research tool."""
    from .research_tool import exec_research as _exec_research

    return _exec_research(params, tenant_id, session_id)


def get_tool_dispatch() -> dict[str, ToolHandler]:
    return {
        "s3_document_ops": exec_s3_document_ops,
        "dynamodb_intake": exec_dynamodb_intake,
        "cloudwatch_logs": exec_cloudwatch_logs,
        "kb_inventory": exec_kb_inventory,
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
        "research": exec_research,
        "langfuse_traces": exec_langfuse_traces,
        "submit_intake_for_approval": exec_submit_intake_for_approval,
        "confirm_intake_approval": exec_confirm_intake_approval,
        "batch_generate_documents": exec_batch_generate_documents,
        "get_doc_jobs": exec_get_doc_jobs,
    }


def _forward_tool_error_to_debug_channel(
    tool_name: str, tool_input: dict, result: dict, tenant_id: str
) -> None:
    """Fire a debug-channel event when a tool handler returns an error dict.

    These silent-failure results (HTTP 200 but {"error": ...} inside) never
    reach FastAPI's exception handler and therefore never reach the primary
    error webhook. The debug channel catches them so ops see the pattern.

    Narrow guard: fires only when the result is a dict with a NON-EMPTY
    `error` key. Successful results that happen to contain the substring
    "error" elsewhere are NOT triggered.
    """
    if not isinstance(result, dict):
        return
    err_val = result.get("error")
    if not err_val:
        return
    try:
        from ..error_webhook import notify_debug_event

        # Redact oversized or binary-ish input fields before attaching.
        safe_input = {}
        for k, v in (tool_input or {}).items():
            if isinstance(v, str) and len(v) > 500:
                safe_input[k] = v[:500] + "…[truncated]"
            elif isinstance(v, (str, int, float, bool)) or v is None:
                safe_input[k] = v
            else:
                safe_input[k] = f"<{type(v).__name__}>"

        notify_debug_event(
            source="tool_dispatch",
            error_type=str(result.get("status") or "ToolError"),
            message=str(err_val)[:2000],
            context={
                "tool": tool_name,
                "tenant_id": tenant_id,
                "input": safe_input,
            },
        )
    except Exception:
        # Telemetry must never break tool dispatch.
        pass


def execute_tool(
    tool_name: str, tool_input: dict, session_id: str | None = None
) -> str:
    tenant_id = extract_tenant_id(session_id)
    handler = get_tool_dispatch().get(tool_name)
    if handler is None:
        unknown_result = {"error": f"Unknown tool: {tool_name}"}
        _forward_tool_error_to_debug_channel(
            tool_name, tool_input, unknown_result, tenant_id
        )
        return json.dumps(unknown_result)

    try:
        if tool_name in TOOLS_NEEDING_SESSION:
            result = handler(tool_input, tenant_id, session_id)
        else:
            result = handler(tool_input, tenant_id)
        # Post-dispatch error detection — catches the HTTP-200-with-error-dict
        # silent-failure class that the exception handler below can't see.
        _forward_tool_error_to_debug_channel(
            tool_name, tool_input, result if isinstance(result, dict) else {}, tenant_id
        )
        return json.dumps(result, indent=2, default=str)
    except Exception as exc:  # noqa: BLE001
        logger.error("Tool execution error (%s): %s", tool_name, exc, exc_info=True)
        err_result = {
            "error": f"Tool execution failed: {exc}",
            "tool": tool_name,
            "suggestion": "Try again or use a different approach.",
        }
        _forward_tool_error_to_debug_channel(
            tool_name, tool_input, err_result, tenant_id
        )
        return json.dumps(err_result)
