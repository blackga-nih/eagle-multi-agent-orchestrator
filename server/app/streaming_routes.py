"""
Streaming Routes for EAGLE NCI Acquisition Assistant

Provides SSE (Server-Sent Events) streaming chat and health check endpoints.
Updated to use strands_agentic_service.sdk_query() with Strands Agents SDK
subagent delegation instead of the legacy stream_chat() prompt-injection path.

# NOTE: main.py should include this router:
#   from app.streaming_routes import create_streaming_router
#   streaming_router = create_streaming_router(store, subscription_service)
#   app.include_router(streaming_router)
"""

from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi.responses import StreamingResponse
from datetime import datetime, timezone
import asyncio
import json
import logging
from contextlib import suppress
from contextlib import suppress
from typing import AsyncGenerator, Optional

from .cognito_auth import extract_user_context, UserContext
from .stream_protocol import StreamEvent, StreamEventType, MultiAgentStreamWriter
from .models import ChatMessage
from .subscription_service import SubscriptionService
from .strands_agentic_service import sdk_query, sdk_query_streaming, MODEL, EAGLE_TOOLS
from .session_store import add_message, record_usage
from .admin_service import record_request_cost, calculate_cost
from .telemetry.log_context import set_log_context

import os
REQUIRE_AUTH = os.getenv("REQUIRE_AUTH", "false").lower() == "true"

logger = logging.getLogger(__name__)


async def stream_generator(
    message: str,
    tenant_id: str,
    user_id: str,
    tier,
    subscription_service: SubscriptionService,
    session_id: str | None = None,
    messages: list[dict] | None = None,
) -> AsyncGenerator[str, None]:
    """Generate SSE events from sdk_query_streaming() with real-time token streaming.

    The flow is:
      1. Yield a metadata event (initial connection handshake).
      2. Consume sdk_query_streaming() async generator for real-time text deltas.
      3. text chunks → TEXT SSE events (streamed as they arrive from Bedrock).
      4. tool_use events → TOOL_USE SSE events.
      5. complete/error → COMPLETE/ERROR SSE event.
    """
    import time as _time
    request_start = _time.time()

    writer = MultiAgentStreamWriter("eagle", "EAGLE Acquisition Assistant")
    sse_queue: asyncio.Queue[str] = asyncio.Queue()
    full_response_parts: list[str] = []
    tools_called: list[str] = []

    # Persist user message to DynamoDB so conversation history works on next turn
    if session_id:
        try:
            await asyncio.to_thread(add_message, session_id, "user", message, tenant_id, user_id)
        except Exception:
            logger.warning("Failed to persist user message for session=%s user=%s", session_id, user_id)

    # Send initial metadata event (connection acknowledgement)
    await writer.write_text(sse_queue, "")
    yield await sse_queue.get()

    # Wrap the SDK generator so we inject ": keepalive\n\n" SSE comments every
    # KEEPALIVE_INTERVAL seconds while waiting for the next chunk.  ALB idle
    # timeout is 300 s (raised from 60 s); keepalive every 20 s keeps it alive.
    KEEPALIVE_INTERVAL = 20.0

    async def _sdk_with_keepalive():
        gen = sdk_query_streaming(
            prompt=message,
            tenant_id=tenant_id,
            user_id=user_id,
            tier=tier or "advanced",
            session_id=session_id,
            messages=messages,
        )

        # Fetch the next chunk as a cancellation-safe Task.
        # asyncio.wait_for cancels the coroutine on timeout, which would close
        # the async generator and discard all post-tool text.  By wrapping each
        # __anext__ in a Task and shielding it, the timeout only cancels the
        # shield wrapper — the underlying task keeps running.  On the next loop
        # iteration we re-shield the same task, so we never lose a chunk.
        async def _safe_next() -> tuple[dict, bool]:
            """Return (chunk, done=False) or ({}, done=True) on exhaustion."""
            try:
                return await gen.__anext__(), False
            except StopAsyncIteration:
                return {}, True

        next_task: asyncio.Task = asyncio.ensure_future(_safe_next())
        try:
            while True:
                try:
                    chunk, done = await asyncio.wait_for(
                        asyncio.shield(next_task), timeout=KEEPALIVE_INTERVAL
                    )
                    if done:
                        break
                    yield chunk
                    next_task = asyncio.ensure_future(_safe_next())
                except asyncio.TimeoutError:
                    # Generator is still running (e.g. waiting for a subagent tool).
                    # Send a keepalive comment and loop back to await the same task.
                    yield {"type": "_keepalive"}
        finally:
            if not next_task.done():
                next_task.cancel()

    try:
        async for chunk in _sdk_with_keepalive():
            chunk_type = chunk.get("type", "")

            if chunk_type == "_keepalive":
                yield ": keepalive\n\n"

            elif chunk_type == "text":
                full_response_parts.append(chunk["data"])
                await writer.write_text(sse_queue, chunk["data"])
                yield await sse_queue.get()

            elif chunk_type == "tool_use":
                tool_name = chunk.get("name", "")
                if tool_name:
                    tools_called.append(tool_name)
                await writer.write_tool_use(sse_queue, tool_name, {})
                yield await sse_queue.get()

            elif chunk_type == "tool_result":
                await writer.write_tool_result(
                    sse_queue,
                    chunk.get("name", ""),
                    chunk.get("result", {}),
                )
                yield await sse_queue.get()

            elif chunk_type == "complete":
                # Persist assistant response to DynamoDB
                if session_id and full_response_parts:
                    try:
                        full_text = "".join(full_response_parts)
                        await asyncio.to_thread(add_message, session_id, "assistant", full_text, tenant_id, user_id)
                    except Exception:
                        logger.warning("Failed to persist assistant message for session=%s user=%s", session_id, user_id)

                # ── Telemetry: record usage + cost ──
                elapsed_ms = int((_time.time() - request_start) * 1000)
                usage = chunk.get("usage", {})
                chunk_tools = chunk.get("tools_called", tools_called)
                input_tokens = usage.get("input_tokens", 0)
                output_tokens = usage.get("output_tokens", 0)
                try:
                    cost = calculate_cost(input_tokens, output_tokens)
                    await asyncio.to_thread(
                        record_usage, session_id or "", tenant_id, user_id,
                        input_tokens, output_tokens, MODEL, cost,
                    )
                    await asyncio.to_thread(
                        record_request_cost, tenant_id, user_id, session_id or "",
                        input_tokens, output_tokens,
                        model=MODEL, tools_used=chunk_tools, response_time_ms=elapsed_ms,
                    )
                    logger.info(json.dumps({
                        "event": "chat_request",
                        "tenant_id": tenant_id,
                        "user_id": user_id,
                        "session_id": session_id,
                        "endpoint": "sse",
                        "tokens_in": input_tokens,
                        "tokens_out": output_tokens,
                        "cost_usd": cost,
                        "tools_called": chunk_tools,
                        "response_time_ms": elapsed_ms,
                        "model": MODEL,
                        "cycle_count": usage.get("cycle_count", 0),
                    }, default=str))
                except Exception:
                    logger.warning("Telemetry emit failed for session=%s: %s", session_id, "see traceback", exc_info=True)

                await writer.write_complete(sse_queue)
                yield await sse_queue.get()
                return

            elif chunk_type == "error":
                await writer.write_error(sse_queue, chunk.get("error", "Unknown error"))
                yield await sse_queue.get()
                return

        # Fallback COMPLETE if generator exhausts without a complete event
        if session_id and full_response_parts:
            try:
                full_text = "".join(full_response_parts)
                await asyncio.to_thread(add_message, session_id, "assistant", full_text, tenant_id, user_id)
            except Exception:
                logger.warning("Failed to persist assistant message for session=%s user=%s", session_id, user_id)

        # ── Telemetry: fallback path ──
        elapsed_ms = int((_time.time() - request_start) * 1000)
        try:
            await asyncio.to_thread(
                record_usage, session_id or "", tenant_id, user_id, 0, 0, MODEL, 0.0,
            )
            logger.info(json.dumps({
                "event": "chat_request",
                "tenant_id": tenant_id,
                "user_id": user_id,
                "session_id": session_id,
                "endpoint": "sse",
                "tokens_in": 0,
                "tokens_out": 0,
                "cost_usd": 0.0,
                "tools_called": tools_called,
                "response_time_ms": elapsed_ms,
                "model": MODEL,
            }, default=str))
        except Exception:
            logger.warning("Telemetry emit failed (fallback) for session=%s", session_id, exc_info=True)

        await writer.write_complete(sse_queue)
        yield await sse_queue.get()

    except asyncio.CancelledError:
        logger.info("Streaming client disconnected user=%s session=%s", user_id, session_id)
        return
    except Exception as e:
        logger.error("Streaming chat error user=%s session=%s: %s", user_id, session_id, str(e), exc_info=True)
        await writer.write_error(sse_queue, str(e))
        yield await sse_queue.get()


def create_streaming_router(
    subscription_service: SubscriptionService,
) -> APIRouter:
    """Factory to create router with service dependencies.

    This pattern allows main.py to wire up concrete service instances::

        streaming_router = create_streaming_router(subscription_service)
        app.include_router(streaming_router)

    Parameters
    ----------
    subscription_service : SubscriptionService
        The initialised subscription/usage service.

    Returns
    -------
    APIRouter
        A FastAPI router containing the /api/chat/stream and
        /api/health endpoints.
    """
    router = APIRouter()

    # ------------------------------------------------------------------
    # POST /api/chat/stream - Streaming chat via SSE (EAGLE backend)
    # ------------------------------------------------------------------
    @router.post("/api/chat/stream")
    async def chat_stream(
        message: ChatMessage,
        authorization: Optional[str] = Header(None),
    ):
        """Send message to EAGLE agent and receive a streaming SSE response.

        Uses EAGLE cognito_auth (DEV_MODE-aware). Accepts the same request
        body as POST /api/chat. The response is delivered as a stream of
        text/event-stream SSE events following the StreamEvent protocol.
        """
        # Authenticate using EAGLE cognito_auth (supports DEV_MODE bypass)
        user, error = extract_user_context(authorization)
        if REQUIRE_AUTH and user.user_id == "anonymous":
            raise HTTPException(status_code=401, detail=error or "Authentication required")

        tenant_id = user.tenant_id
        user_id = user.user_id

        # Use tenant_context from message body if provided, else from auth
        if message.tenant_context:
            tenant_id = message.tenant_context.tenant_id or tenant_id
            user_id = message.tenant_context.user_id or user_id

        # Set structured logging context so all downstream logs include user/tenant
        set_log_context(tenant_id=tenant_id, user_id=user_id, session_id=message.session_id or "")

        # Load conversation history for multi-turn context
        history = []
        if message.session_id:
            try:
                from .session_store import get_messages_for_anthropic
                history = get_messages_for_anthropic(message.session_id, tenant_id, user_id)
            except Exception:
                pass

        # Return streaming response
        return StreamingResponse(
            stream_generator(
                message=message.message,
                tenant_id=tenant_id,
                user_id=user_id,
                tier=user.tier,
                subscription_service=subscription_service,
                session_id=message.session_id,
                messages=history,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # ------------------------------------------------------------------
    # GET /api/health - Health check (no auth required)
    # ------------------------------------------------------------------
    @router.get("/api/health")
    async def health_check():
        """Return service health status, available agents, and EAGLE tools.

        This endpoint does not require authentication and is intended
        for load-balancer health probes and operational dashboards.
        """
        return {
            "status": "healthy",
            "service": "EAGLE – NCI Acquisition Assistant",
            "version": "4.0.0",
            "model": MODEL,
            "services": {
                "bedrock": True,
                "dynamodb": True,
                "cognito": True,
                "s3": True,
            },
            "agents": [
                {
                    "id": "eagle",
                    "name": "EAGLE Acquisition Assistant",
                    "status": "online",
                },
                {
                    "id": "supervisor",
                    "name": "Supervisor",
                    "status": "online",
                },
                {
                    "id": "oa-intake",
                    "name": "OA Intake Agent",
                    "status": "online",
                },
            ],
            "tools": [tool["name"] for tool in EAGLE_TOOLS],
            "features": {
                "persistent_sessions": os.getenv("USE_PERSISTENT_SESSIONS", "true").lower() == "true",
                "auth_required": os.getenv("REQUIRE_AUTH", "false").lower() == "true",
                "dev_mode": os.getenv("DEV_MODE", "false").lower() == "true",
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    return router
