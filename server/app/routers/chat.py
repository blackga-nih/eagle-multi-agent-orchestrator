"""
Chat API Router

Provides REST and WebSocket chat endpoints using the Strands SDK.
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from ..cognito_auth import UserContext, extract_user_context, DEV_MODE
from ..session_store import (
    create_session as eagle_create_session,
    get_session as eagle_get_session,
    add_message,
    get_messages_for_anthropic,
)
from ..admin_service import record_request_cost, check_rate_limit, calculate_cost
from ..package_context_service import resolve_context, set_active_package
from .dependencies import get_user_from_header, get_session_context

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

# ── Feature Flags ────────────────────────────────────────────────────
USE_PERSISTENT_SESSIONS = os.getenv("USE_PERSISTENT_SESSIONS", "true").lower() == "true"

# ── In-memory session store (fallback when persistent sessions disabled)
_SESSIONS: Dict[str, List[dict]] = {}

# ── Telemetry ring buffer ────────────────────────────────────────────
_TELEMETRY_LOG: deque = deque(maxlen=500)


def _get_strands_runtime():
    from .. import strands_agentic_service

    return strands_agentic_service


def set_sessions_ref(sessions_dict: Dict[str, List[dict]]):
    """Set reference to sessions dict from main.py."""
    global _SESSIONS
    _SESSIONS = sessions_dict


def set_telemetry_ref(telemetry_log: deque):
    """Set reference to telemetry log from main.py."""
    global _TELEMETRY_LOG
    _TELEMETRY_LOG = telemetry_log


def get_telemetry_log() -> deque:
    """Get the telemetry log for external access."""
    return _TELEMETRY_LOG


def _log_telemetry(entry: dict):
    entry.setdefault("timestamp", datetime.utcnow().isoformat())
    _TELEMETRY_LOG.append(entry)
    logger.info("telemetry_event", extra=entry)


# ── Models ───────────────────────────────────────────────────────────


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


# ── REST Chat Endpoint ───────────────────────────────────────────────


@router.post("/api/chat", response_model=EagleChatResponse)
async def api_chat(req: EagleChatRequest, user: UserContext = Depends(get_user_from_header)):
    """REST chat endpoint using EAGLE Strands SDK with cost tracking."""
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
        if session_id not in _SESSIONS:
            _SESSIONS[session_id] = []
        messages = _SESSIONS[session_id]

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

        strands_runtime = _get_strands_runtime()
        async for _sdk_msg in strands_runtime.sdk_query(
            prompt=req.message,
            tenant_id=tenant_id,
            user_id=user_id,
            tier=user.tier or "advanced",
            session_id=session_id,
            messages=messages[:-1],
            package_context=resolved_package_context,
            username=user.username or user_id,
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
        result = {
            "text": _response_text,
            "usage": _usage,
            "model": strands_runtime.MODEL,
            "tools_called": _tools_called,
        }

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
            model=result.get("model", strands_runtime.MODEL),
            tools_used=result.get("tools_called", []),
            response_time_ms=elapsed_ms
        )

        _log_telemetry({
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


# ── Telemetry Endpoint ───────────────────────────────────────────────


@router.get("/api/telemetry")
async def api_telemetry(limit: int = 50):
    """Return recent telemetry entries."""
    entries = list(_TELEMETRY_LOG)[-limit:]
    entries.reverse()

    chat_entries = [e for e in _TELEMETRY_LOG if e.get("event") == "chat_request"]
    total_tokens_in = sum(e.get("tokens_in", 0) for e in chat_entries)
    total_tokens_out = sum(e.get("tokens_out", 0) for e in chat_entries)
    total_cost = sum(e.get("cost_usd", 0) for e in chat_entries)
    avg_response = (
        sum(e.get("response_time_ms", 0) for e in chat_entries) / len(chat_entries)
        if chat_entries else 0
    )
    all_tools = []
    for e in chat_entries:
        all_tools.extend(e.get("tools_called", []))

    return {
        "entries": entries,
        "summary": {
            "total_requests": len(chat_entries),
            "total_tokens_in": total_tokens_in,
            "total_tokens_out": total_tokens_out,
            "total_cost_usd": round(total_cost, 4),
            "avg_response_time_ms": round(avg_response),
            "tools_usage": {tool: all_tools.count(tool) for tool in set(all_tools)},
            "active_sessions": len(_SESSIONS),
        },
    }


# ── Tools Info Endpoint ──────────────────────────────────────────────


@router.get("/api/tools")
async def api_tools():
    """List available EAGLE tools."""
    tools = []
    for tool in _get_strands_runtime().EAGLE_TOOLS:
        tools.append({
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool.get("input_schema", {}),
        })
    return {"tools": tools, "count": len(tools)}


# ── WebSocket Chat Endpoint ──────────────────────────────────────────

_ws_counter = 0


@router.websocket("/ws/chat")
async def websocket_chat(ws: WebSocket):
    """Real-time streaming chat via WebSocket with EAGLE tools."""
    global _ws_counter
    await ws.accept()
    _ws_counter += 1
    default_session_id = f"ws-{_ws_counter}-{int(time.time()) % 100000}"

    user = UserContext.dev_user() if DEV_MODE else UserContext.anonymous()
    tenant_id = user.tenant_id
    user_id = user.user_id

    logger.info("WebSocket connected: %s", default_session_id)
    await ws.send_json({"type": "connected", "chatId": default_session_id, "user": user.to_dict()})

    try:
        while True:
            data = await ws.receive_json()
            msg_type = data.get("type", "")

            if msg_type == "auth":
                token = data.get("token", "")
                user, error = extract_user_context(token)
                tenant_id = user.tenant_id
                user_id = user.user_id
                await ws.send_json({
                    "type": "authenticated",
                    "user": user.to_dict(),
                    "error": error,
                })
                continue

            if msg_type != "chat.send":
                await ws.send_json({"type": "error", "message": f"Unknown type: {msg_type}"})
                continue

            user_message = data.get("message", "").strip()
            if not user_message:
                await ws.send_json({"type": "error", "message": "Empty message"})
                continue

            session_id = data.get("session_id") or default_session_id

            rate_check = check_rate_limit(tenant_id, user_id, user.tier)
            if not rate_check["allowed"]:
                await ws.send_json({"type": "error", "message": rate_check["reason"], "rate_limited": True})
                continue

            if USE_PERSISTENT_SESSIONS:
                session = eagle_get_session(session_id, tenant_id, user_id)
                if not session:
                    session = eagle_create_session(tenant_id, user_id, session_id)
                messages = get_messages_for_anthropic(session_id, tenant_id, user_id)
            else:
                if session_id not in _SESSIONS:
                    _SESSIONS[session_id] = []
                messages = _SESSIONS[session_id]

            messages.append({"role": "user", "content": user_message})
            if USE_PERSISTENT_SESSIONS:
                add_message(session_id, "user", user_message, tenant_id, user_id)

            start_time = time.time()
            tools_called = []

            try:
                async def on_text(delta: str):
                    await ws.send_json({"type": "delta", "text": delta})

                async def on_tool_use(tool_name: str, tool_input: dict):
                    tools_called.append(tool_name)
                    await ws.send_json({
                        "type": "tool_use",
                        "tool": tool_name,
                        "input": tool_input,
                    })

                async def on_tool_result(tool_name: str, output: str):
                    display_output = output[:2000] + "..." if len(output) > 2000 else output
                    await ws.send_json({
                        "type": "tool_result",
                        "tool": tool_name,
                        "output": display_output,
                    })

                _text_parts: list[str] = []
                _usage: dict = {}
                _final_text: str = ""

                strands_runtime = _get_strands_runtime()
                async for _sdk_msg in strands_runtime.sdk_query(
                    prompt=user_message,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    tier=user.tier or "advanced",
                    session_id=session_id,
                    messages=messages[:-1],
                ):
                    _msg_type = type(_sdk_msg).__name__
                    if _msg_type == "AssistantMessage":
                        for _block in _sdk_msg.content:
                            _bt = getattr(_block, "type", None)
                            if _bt == "text":
                                _text_parts.append(_block.text)
                                await on_text(_block.text)
                            elif _bt == "tool_use":
                                tools_called.append(getattr(_block, "name", ""))
                                await on_tool_use(getattr(_block, "name", ""), getattr(_block, "input", {}))
                    elif _msg_type == "ResultMessage":
                        _raw = getattr(_sdk_msg, "usage", {})
                        _usage = _raw if isinstance(_raw, dict) else {
                            "input_tokens": getattr(_raw, "input_tokens", 0),
                            "output_tokens": getattr(_raw, "output_tokens", 0),
                        }
                        _final_text = str(getattr(_sdk_msg, "result", "") or "")

                _response_text = "".join(_text_parts) or _final_text
                if _response_text and not _text_parts:
                    await on_text(_response_text)
                result = {
                    "text": _response_text,
                    "usage": _usage,
                    "model": strands_runtime.MODEL,
                    "tools_called": tools_called,
                }

                if USE_PERSISTENT_SESSIONS:
                    add_message(session_id, "assistant", result["text"], tenant_id, user_id)
                else:
                    messages.append({"role": "assistant", "content": result["text"]})

                usage = result.get("usage", {})
                elapsed_ms = int((time.time() - start_time) * 1000)

                input_tokens = usage.get("input_tokens", 0)
                output_tokens = usage.get("output_tokens", 0)
                cost = calculate_cost(input_tokens, output_tokens)

                record_request_cost(
                    tenant_id, user_id, session_id,
                    input_tokens, output_tokens,
                    model=result.get("model", strands_runtime.MODEL),
                    tools_used=result.get("tools_called", []),
                    response_time_ms=elapsed_ms
                )

                await ws.send_json({
                    "type": "final",
                    "text": result["text"],
                    "session_id": session_id,
                    "usage": usage,
                    "model": result.get("model", ""),
                    "tools_called": result.get("tools_called", []),
                    "response_time_ms": elapsed_ms,
                    "cost_usd": cost,
                })

                _log_telemetry({
                    "event": "chat_request",
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                    "session_id": session_id,
                    "endpoint": "websocket",
                    "tokens_in": input_tokens,
                    "tokens_out": output_tokens,
                    "cost_usd": cost,
                    "tools_called": result.get("tools_called", []),
                    "response_time_ms": elapsed_ms,
                    "model": result.get("model", ""),
                })

            except Exception as e:
                logger.error("Stream error: %s", e, exc_info=True)
                await ws.send_json({"type": "error", "message": "Internal error processing stream"})

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: %s", default_session_id)
    except Exception as e:
        logger.error("WebSocket error: %s", e, exc_info=True)
        try:
            await ws.send_json({"type": "error", "message": "WebSocket connection error"})
        except Exception:
            pass
