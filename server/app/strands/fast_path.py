"""
EAGLE Strands Fast-Path Document Generation

Direct document creation for explicit generate/draft requests,
bypassing the full agent loop for faster response times.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .prompt_utils import (
    build_scoped_session_id,
    extract_context_data_from_prompt,
    extract_document_context_from_prompt,
    fast_path_title,
    is_document_generation_request,
    should_use_fast_document_path,
)

logger = logging.getLogger("eagle.strands_agent")


async def maybe_fast_path_document_generation(
    prompt: str,
    tenant_id: str,
    user_id: str,
    session_id: str | None,
    package_context: Any = None,
) -> dict | None:
    """Attempt fast-path document generation for explicit requests.

    Returns a dict with 'doc_type' and 'result' if fast-path was taken,
    or None if the request should go through the normal agent loop.
    """
    should_fast_path, doc_type = should_use_fast_document_path(prompt)
    if not should_fast_path or not doc_type:
        return None

    from ..tools.strands_tools import exec_create_document

    doc_ctx = extract_document_context_from_prompt(prompt)
    params: dict[str, Any] = {
        "doc_type": doc_type,
        "title": doc_ctx.get("title") or fast_path_title(prompt, doc_type),
    }
    contextual_data = extract_context_data_from_prompt(prompt, doc_type)
    if contextual_data:
        params["data"] = contextual_data
    if (
        package_context is not None
        and getattr(package_context, "is_package_mode", False)
        and getattr(package_context, "package_id", None)
    ):
        params["package_id"] = package_context.package_id

    scoped_session_id = build_scoped_session_id(tenant_id, user_id, session_id)
    result = await asyncio.to_thread(
        exec_create_document,
        params,
        tenant_id,
        scoped_session_id,
    )
    return {
        "doc_type": doc_type,
        "result": result,
    }


async def ensure_create_document_for_direct_request(
    prompt: str,
    tenant_id: str,
    user_id: str,
    session_id: str | None,
    package_context: Any,
    tools_called: list[str],
) -> dict | None:
    """Force a create_document call for direct doc requests that missed the tool.

    This reconciles cases where the model produced inline draft content without
    invoking create_document, which breaks document-card/editing UX.
    """
    should_generate, doc_type = is_document_generation_request(prompt)
    if not should_generate or not doc_type or "create_document" in tools_called:
        return None

    from ..tools.strands_tools import exec_create_document

    doc_ctx = extract_document_context_from_prompt(prompt)
    params: dict[str, Any] = {
        "doc_type": doc_type,
        "title": doc_ctx.get("title") or fast_path_title(prompt, doc_type),
    }
    contextual_data = extract_context_data_from_prompt(prompt, doc_type)
    if contextual_data:
        params["data"] = contextual_data
    if (
        package_context is not None
        and getattr(package_context, "is_package_mode", False)
        and getattr(package_context, "package_id", None)
    ):
        params["package_id"] = package_context.package_id

    scoped_session_id = build_scoped_session_id(tenant_id, user_id, session_id)
    result = await asyncio.to_thread(
        exec_create_document,
        params,
        tenant_id,
        scoped_session_id,
    )
    if isinstance(result, dict) and result.get("error"):
        logger.warning(
            "Forced create_document failed for prompt='%s': %s",
            prompt[:160],
            result.get("error"),
        )
        return None

    return {
        "doc_type": doc_type,
        "result": result,
    }
