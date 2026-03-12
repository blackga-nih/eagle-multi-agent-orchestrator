"""REST chat endpoint — EAGLE Anthropic/Strands SDK."""

import time
import logging
from typing import Optional, Dict, List, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..cognito_auth import UserContext
from ..strands_agentic_service import sdk_query, MODEL
from ..stores.session_store import (
    create_session as eagle_create_session, get_session as eagle_get_session,
    add_message, get_messages_for_anthropic,
)
from ..admin_service import check_rate_limit, record_request_cost, calculate_cost
from ..package_context_service import resolve_context, set_active_package
from ._deps import (
    get_user_from_header, get_session_context,
    USE_PERSISTENT_SESSIONS, log_telemetry,
)

logger = logging.getLogger("eagle")
router = APIRouter(tags=["chat"])

# In-memory fallback (shared with sessions route)
SESSIONS: Dict[str, List[dict]] = {}


class EagleChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    package_id: Optional[str] = None


class EagleChatResponse(BaseModel):
    response: str
    session_id: str
    usage: Dict[str, Any]
    model: str
    tools_called: List[str]
    response_time_ms: int
    cost_usd: Optional[float] = None


@router.post("/api/chat", response_model=EagleChatResponse)
async def api_chat(req: EagleChatRequest, user: UserContext = Depends(get_user_from_header)):
    """REST chat endpoint using EAGLE Anthropic SDK with cost tracking."""
    start = time.time()
    tenant_id, user_id, session_id = get_session_context(user, req.session_id)

    # Check rate limits
    rate_check = check_rate_limit(tenant_id, user_id, user.tier)
    if not rate_check["allowed"]:
        raise HTTPException(status_code=429, detail=rate_check["reason"])

    # Get or create session
    if USE_PERSISTENT_SESSIONS:
        session = eagle_get_session(session_id, tenant_id, user_id)
        if not session:
            session = eagle_create_session(tenant_id, user_id, session_id)
        messages = get_messages_for_anthropic(session_id, tenant_id, user_id)
    else:
        if session_id not in SESSIONS:
            SESSIONS[session_id] = []
        messages = SESSIONS[session_id]

    # Add user message
    user_msg = {"role": "user", "content": req.message}
    messages.append(user_msg)

    if USE_PERSISTENT_SESSIONS:
        add_message(session_id, "user", req.message, tenant_id, user_id)

    resolved_package_context = None
    try:
        resolved_package_context = resolve_context(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            explicit_package_id=req.package_id,
        )
        if req.package_id and resolved_package_context.is_package_mode:
            set_active_package(
                tenant_id=tenant_id,
                user_id=user_id,
                session_id=session_id,
                package_id=resolved_package_context.package_id,
            )
    except Exception:
        logger.warning("Package context resolution failed for REST chat", exc_info=True)
        resolved_package_context = None

    try:
        _text_parts: list[str] = []
        _usage: dict = {}
        _tools_called: list[str] = []
        _final_text: str = ""
        async for _sdk_msg in sdk_query(
            prompt=req.message,
            tenant_id=tenant_id,
            user_id=user_id,
            tier=user.tier or "advanced",
            session_id=session_id,
            messages=messages[:-1],  # History excluding current user message
            package_context=resolved_package_context,
        ):
            _msg_type = type(_sdk_msg).__name__
            if _msg_type == "AssistantMessage":
                for _block in _sdk_msg.content:
                    if getattr(_block, "type", None) == "text":
                        _text_parts.append(_block.text)
                    elif getattr(_block, "type", None) == "tool_use":
                        _tools_called.append(getattr(_block, "name", ""))
            elif _msg_type == "ResultMessage":
                _raw = getattr(_sdk_msg, "usage", {})
                _usage = _raw if isinstance(_raw, dict) else {
                    "input_tokens": getattr(_raw, "input_tokens", 0),
                    "output_tokens": getattr(_raw, "output_tokens", 0),
                }
                _final_text = str(getattr(_sdk_msg, "result", "") or "")
        _response_text = "".join(_text_parts) or _final_text
        result = {"text": _response_text, "usage": _usage, "model": MODEL, "tools_called": _tools_called}

        # Store response
        if USE_PERSISTENT_SESSIONS:
            add_message(session_id, "assistant", result["text"], tenant_id, user_id)
        else:
            messages.append({"role": "assistant", "content": result["text"]})

        elapsed_ms = int((time.time() - start) * 1000)
        usage = result.get("usage", {})

        # Calculate and record cost
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        cost = calculate_cost(input_tokens, output_tokens)

        record_request_cost(
            tenant_id, user_id, session_id,
            input_tokens, output_tokens,
            model=result.get("model", MODEL),
            tools_used=result.get("tools_called", []),
            response_time_ms=elapsed_ms
        )

        log_telemetry({
            "event": "chat_request",
            "tenant_id": tenant_id,
            "user_id": user_id,
            "session_id": session_id,
            "endpoint": "rest",
            "tokens_in": input_tokens,
            "tokens_out": output_tokens,
            "cost_usd": cost,
            "tools_called": result.get("tools_called", []),
            "response_time_ms": elapsed_ms,
            "model": result.get("model", ""),
        })

        return EagleChatResponse(
            response=result["text"],
            session_id=session_id,
            usage=usage,
            model=result.get("model", ""),
            tools_called=result.get("tools_called", []),
            response_time_ms=elapsed_ms,
            cost_usd=cost,
        )
    except Exception as e:
        logger.error("REST chat error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error processing chat request")
