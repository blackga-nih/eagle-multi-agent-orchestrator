"""Streaming routes for EAGLE using Strands-only orchestration."""

from fastapi import APIRouter, HTTPException, Header
from fastapi.responses import StreamingResponse
from datetime import datetime, timezone
import asyncio
import logging
from contextlib import suppress
from typing import AsyncGenerator, Optional
import time
import uuid

from .cognito_auth import extract_user_context
from .stream_protocol import MultiAgentStreamWriter
from .models import ChatMessage
from .subscription_service import SubscriptionService
from .admin_service import record_request_cost
from .strands_agentic_service import strands_query, get_active_model, get_tools_for_api

import os
REQUIRE_AUTH = os.getenv("REQUIRE_AUTH", "false").lower() == "true"

logger = logging.getLogger(__name__)


async def stream_generator(
    message: str,
    tenant_id: str,
    user_id: str,
    tier,
    session_id: str,
    subscription_service: SubscriptionService,
) -> AsyncGenerator[str, None]:
    """Generate SSE events from strands_query() orchestration."""
    writer = MultiAgentStreamWriter("eagle", "EAGLE Acquisition Assistant")
    queue: asyncio.Queue[str] = asyncio.Queue()
    start = time.time()
    usage = {"input_tokens": 0, "output_tokens": 0}
    tools_called: list[str] = []

    # Send initial metadata event (connection acknowledgement)
    await writer.write_text(queue, "")
    yield await queue.get()

    try:
        strands_messages = strands_query(
            prompt=message,
            tenant_id=tenant_id,
            user_id=user_id,
            tier=tier or "advanced",
            session_id=session_id,
        )

        async for event in strands_messages:
            event_type = event.get("type")
            if event_type == "text":
                await writer.write_text(queue, event.get("content", ""))
            elif event_type == "tool_use":
                tool_name = event.get("name", "")
                tools_called.append(tool_name)
                await writer.write_tool_use(queue, tool_name, event.get("input", {}))
            elif event_type == "complete":
                usage = event.get("usage", usage) or usage
                while not queue.empty():
                    yield await queue.get()
                await writer.write_complete(queue)
                yield await queue.get()
                elapsed_ms = int((time.time() - start) * 1000)
                record_request_cost(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    session_id=session_id,
                    input_tokens=int(usage.get("input_tokens", 0)),
                    output_tokens=int(usage.get("output_tokens", 0)),
                    model=get_active_model(),
                    tools_used=tools_called,
                    response_time_ms=elapsed_ms,
                )
                return
            elif event_type == "error":
                await writer.write_error(queue, str(event.get("message", "Unknown streaming error")))
                yield await queue.get()
                return
            while not queue.empty():
                yield await queue.get()

        # Fallback COMPLETE if generator exhausts without a complete event
        while not queue.empty():
            yield await queue.get()
        await writer.write_complete(queue)
        yield await queue.get()
        elapsed_ms = int((time.time() - start) * 1000)
        record_request_cost(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
            model=get_active_model(),
            tools_used=tools_called,
            response_time_ms=elapsed_ms,
        )

    except asyncio.CancelledError:
        # Client disconnected mid-stream; treat as expected cancellation path.
        logger.info("Streaming client disconnected")
        return
    except Exception as e:
        logger.error("Streaming chat error: %s", str(e), exc_info=True)
        await writer.write_error(queue, str(e))
        yield await queue.get()
    finally:
        if "strands_messages" in locals():
            with suppress(Exception):
                await strands_messages.aclose()


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
                tenant_id=tenant_id,
                user_id=user_id,
                tier=user.tier,
                session_id=(message.tenant_context.session_id if message.tenant_context else str(uuid.uuid4())),
                subscription_service=subscription_service,
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
            "model": get_active_model(),
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
            "tools": [tool["name"] for tool in get_tools_for_api(tier="advanced")],
            "features": {
                "persistent_sessions": os.getenv("USE_PERSISTENT_SESSIONS", "true").lower() == "true",
                "auth_required": os.getenv("REQUIRE_AUTH", "false").lower() == "true",
                "dev_mode": os.getenv("DEV_MODE", "false").lower() == "true",
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    return router
