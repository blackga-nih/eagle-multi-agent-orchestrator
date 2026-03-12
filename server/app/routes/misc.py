"""Miscellaneous endpoints — telemetry, tools, WebSocket, health."""

import time
import logging
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..cognito_auth import UserContext, extract_user_context, DEV_MODE
from ..strands_agentic_service import sdk_query, MODEL, EAGLE_TOOLS
from ..stores.session_store import (
    create_session as eagle_create_session, get_session as eagle_get_session,
    add_message, get_messages_for_anthropic,
)
from ..admin_service import check_rate_limit, record_request_cost, calculate_cost
from ..health_checks import check_knowledge_base_health
from ._deps import (
    USE_PERSISTENT_SESSIONS, TELEMETRY_LOG, log_telemetry,
)
from .chat import SESSIONS  # shared in-memory fallback

logger = logging.getLogger("eagle")
router = APIRouter()


# ── Telemetry endpoint ────────────────────────────────────────────────

@router.get("/api/telemetry", tags=["telemetry"])
async def api_telemetry(limit: int = 50):
    """Return recent telemetry entries."""
    entries = list(TELEMETRY_LOG)[-limit:]
    entries.reverse()

    chat_entries = [e for e in TELEMETRY_LOG if e.get("event") == "chat_request"]
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
            "active_sessions": len(SESSIONS),
        },
    }


# ── Tools info endpoint ──────────────────────────────────────────────

@router.get("/api/tools", tags=["tools"])
async def api_tools():
    """List available EAGLE tools."""
    tools = []
    for tool in EAGLE_TOOLS:
        tools.append({
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool.get("input_schema", {}),
        })
    return {"tools": tools, "count": len(tools)}


# ── WebSocket chat endpoint ──────────────────────────────────────────
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
                if session_id not in SESSIONS:
                    SESSIONS[session_id] = []
                messages = SESSIONS[session_id]

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
                async for _sdk_msg in sdk_query(
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
                result = {"text": _response_text, "usage": _usage, "model": MODEL, "tools_called": tools_called}

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
                    model=result.get("model", MODEL),
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

                log_telemetry({
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


# ── Health Check ──────────────────────────────────────────────────────

@router.get("/api/health", tags=["health"])
async def health_check():
    """Backend health check endpoint."""
    knowledge_base = check_knowledge_base_health()
    return {
        "status": "healthy",
        "service": "eagle-backend",
        "version": "4.0.0",
        "services": {
            "bedrock": True,
            "dynamodb": True,
            "cognito": True,
            "s3": True,
            "knowledge_metadata_table": knowledge_base["metadata_table"]["ok"],
            "knowledge_document_bucket": knowledge_base["document_bucket"]["ok"],
        },
        "knowledge_base": knowledge_base,
        "timestamp": datetime.utcnow().isoformat(),
    }
