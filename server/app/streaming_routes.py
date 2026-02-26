"""
Streaming Routes for EAGLE NCI Acquisition Assistant

Provides SSE (Server-Sent Events) streaming chat and health check endpoints.
Updated to use sdk_agentic_service.sdk_query() with Claude Agent SDK
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
from typing import AsyncGenerator, Optional

from .cognito_auth import extract_user_context, UserContext
from .stream_protocol import StreamEvent, StreamEventType, MultiAgentStreamWriter
from .models import ChatMessage
from .subscription_service import SubscriptionService
from .agentic_service import MODEL, EAGLE_TOOLS
from .sdk_agentic_service import sdk_query

import os
REQUIRE_AUTH = os.getenv("REQUIRE_AUTH", "false").lower() == "true"

logger = logging.getLogger(__name__)


async def stream_generator(
    message: str,
    tenant_context,
    tier,
    subscription_service: SubscriptionService,
    session_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """Generate SSE events from sdk_query() subagent orchestration.

    The flow is:
      1. Yield a metadata event (initial connection handshake).
      2. Consume sdk_query() async generator.
      3. AssistantMessage text blocks → TEXT SSE events.
      4. AssistantMessage tool_use blocks → TOOL_USE SSE events.
      5. ResultMessage → drain queue, emit COMPLETE.
      6. On exception → emit ERROR event.
    """
    writer = MultiAgentStreamWriter("eagle", "EAGLE Acquisition Assistant")
    queue: asyncio.Queue[str] = asyncio.Queue()

    # Send initial metadata event (connection acknowledgement)
    await writer.write_text(queue, "")
    yield await queue.get()

    try:
        tenant_id = getattr(tenant_context, "tenant_id", "demo-tenant")
        user_id = getattr(tenant_context, "user_id", "demo-user")

        async for sdk_msg in sdk_query(
            prompt=message,
            tenant_id=tenant_id,
            user_id=user_id,
            tier=tier or "advanced",
            session_id=session_id,
        ):
            msg_type = type(sdk_msg).__name__
            if msg_type == "AssistantMessage":
                for block in sdk_msg.content:
                    block_type = getattr(block, "type", None)
                    if block_type == "text":
                        await writer.write_text(queue, block.text)
                    elif block_type == "tool_use":
                        await writer.write_tool_use(queue, block.name, getattr(block, "input", {}))
                    while not queue.empty():
                        yield await queue.get()
            elif msg_type == "ResultMessage":
                while not queue.empty():
                    yield await queue.get()
                await writer.write_complete(queue)
                yield await queue.get()
                return

        # Fallback COMPLETE if generator exhausts without a ResultMessage
        while not queue.empty():
            yield await queue.get()
        await writer.write_complete(queue)
        yield await queue.get()

    except Exception as e:
        logger.error("Streaming chat error: %s", str(e), exc_info=True)
        await writer.write_error(queue, str(e))
        yield await queue.get()


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

        # Return streaming response
        return StreamingResponse(
            stream_generator(
                message=message.message,
                tenant_context=message.tenant_context,
                tier=user.tier,
                subscription_service=subscription_service,
                session_id=message.session_id,
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
                "anthropic": True,
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
