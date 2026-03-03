"""
Streaming Routes for EAGLE NCI Acquisition Assistant

Provides SSE (Server-Sent Events) streaming chat and health check endpoints.
Updated to use strands_agentic_service.sdk_query_streaming() with Strands
Agents SDK for real-time token streaming via QueueCallbackHandler.

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
from typing import AsyncGenerator, Optional

from .cognito_auth import extract_user_context, UserContext
from .stream_protocol import StreamEvent, StreamEventType, MultiAgentStreamWriter
from .models import ChatMessage
from .subscription_service import SubscriptionService
from .strands_agentic_service import sdk_query, sdk_query_streaming, MODEL, EAGLE_TOOLS

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
    writer = MultiAgentStreamWriter("eagle", "EAGLE Acquisition Assistant")
    sse_queue: asyncio.Queue[str] = asyncio.Queue()

    # Send initial metadata event (connection acknowledgement)
    await writer.write_text(sse_queue, "")
    yield await sse_queue.get()

    try:
        async for chunk in sdk_query_streaming(
            prompt=message,
            tenant_id=tenant_id,
            user_id=user_id,
            tier=tier or "advanced",
            session_id=session_id,
            messages=messages,
        ):
            chunk_type = chunk.get("type", "")

            if chunk_type == "text":
                await writer.write_text(sse_queue, chunk["data"])
                yield await sse_queue.get()

            elif chunk_type == "tool_use":
                await writer.write_tool_use(sse_queue, chunk.get("name", ""), {})
                yield await sse_queue.get()

            elif chunk_type == "complete":
                await writer.write_complete(sse_queue)
                yield await sse_queue.get()
                return

            elif chunk_type == "error":
                await writer.write_error(sse_queue, chunk.get("error", "Unknown error"))
                yield await sse_queue.get()
                return

        # Fallback COMPLETE if generator exhausts without a complete event
        await writer.write_complete(sse_queue)
        yield await sse_queue.get()

    except asyncio.CancelledError:
        logger.info("Streaming client disconnected")
        return
    except Exception as e:
        logger.error("Streaming chat error: %s", str(e), exc_info=True)
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
