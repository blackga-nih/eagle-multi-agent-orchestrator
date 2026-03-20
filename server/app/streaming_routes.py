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
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Header
from fastapi.responses import StreamingResponse
from datetime import datetime, timezone
import asyncio
import json
import logging
import time
from typing import Any, AsyncGenerator, Optional
from pydantic import BaseModel

from .cognito_auth import extract_user_context
from .stream_protocol import MultiAgentStreamWriter
from .models import ChatMessage
from .subscription_service import SubscriptionService
from .session_store import add_message
from .package_context_service import resolve_context, set_active_package
from .telemetry.log_context import set_log_context
from .health_checks import check_knowledge_base_health
from .config import auth as auth_config

REQUIRE_AUTH = auth_config.require_auth

logger = logging.getLogger(__name__)


def _get_strands_runtime():
    from . import strands_agentic_service

    return strands_agentic_service


class GenerateTitleRequest(BaseModel):
    """Request body for generating a session title."""
    message: str
    response_snippet: Optional[str] = None


def _emit_tool_timings(
    tool_timings: list[dict],
    tenant_id: str,
    user_id: str,
    session_id: str | None,
    stream_duration_ms: int | None = None,
):
    """Emit tool.timing events to CloudWatch (fire-and-forget, never raises)."""
    try:
        from .telemetry.cloudwatch_emitter import emit_telemetry_event
        for timing in tool_timings:
            emit_telemetry_event(
                event_type="tool.timing",
                tenant_id=tenant_id,
                data={
                    "tool_name": timing["tool_name"],
                    "duration_ms": timing["duration_ms"],
                    "session_id": session_id or "",
                },
                session_id=session_id,
                user_id=user_id,
            )
        if stream_duration_ms is not None:
            emit_telemetry_event(
                event_type="stream.timing",
                tenant_id=tenant_id,
                data={
                    "duration_ms": stream_duration_ms,
                    "tools_count": len(tool_timings),
                    "session_id": session_id or "",
                },
                session_id=session_id,
                user_id=user_id,
            )
    except Exception:
        logger.debug("Failed to emit tool timing telemetry", exc_info=True)


def _emit_tool_failures(
    tool_failures: list[dict],
    tenant_id: str,
    user_id: str,
    session_id: str | None,
):
    """Emit tool.error events to CloudWatch (fire-and-forget, never raises)."""
    try:
        from .telemetry.cloudwatch_emitter import emit_telemetry_event
        for failure in tool_failures:
            emit_telemetry_event(
                event_type="tool.error",
                tenant_id=tenant_id,
                data={
                    "tool_name": failure["tool_name"],
                    "error_message": failure.get("error_message", ""),
                    "duration_ms": failure.get("duration_ms", 0),
                    "session_id": session_id or "",
                },
                session_id=session_id,
                user_id=user_id,
            )
    except Exception:
        logger.debug("Failed to emit tool failure telemetry", exc_info=True)


async def stream_generator(
    message: str,
    tenant_id: str,
    user_id: str,
    tier,
    subscription_service: SubscriptionService,
    session_id: str | None = None,
    messages: list[dict] | None = None,
    package_context: Any = None,
    username: str | None = None,
) -> AsyncGenerator[str, None]:
    """Generate SSE events from sdk_query_streaming() with real-time token streaming.

    The flow is:
      1. Yield a metadata event (initial connection handshake).
      2. Consume sdk_query_streaming() async generator for real-time text deltas.
      3. text chunks → TEXT SSE events (streamed as they arrive from Bedrock).
      4. tool_use events → TOOL_USE SSE events.
      5. complete/error → COMPLETE/ERROR SSE event.
    """
    stream_start = time.perf_counter()
    writer = MultiAgentStreamWriter("eagle", "EAGLE Acquisition Assistant")
    sse_queue: asyncio.Queue[str] = asyncio.Queue()
    full_response_parts: list[str] = []
    # Tool timing: track start times when tool_use arrives, compute duration on tool_result
    _tool_start_times: dict[str, float] = {}  # tool_name → perf_counter
    _tool_timings: list[dict] = []  # collected {tool_name, duration_ms}
    _tool_failures: list[dict] = []  # collected {tool_name, error_message, duration_ms}

    # Persist user message to DynamoDB so conversation history works on next turn
    if session_id:
        try:
            await asyncio.to_thread(add_message, session_id, "user", message, tenant_id, user_id)
        except Exception:
            logger.warning("Failed to persist user message for session=%s user=%s", session_id, user_id)

    # Send initial metadata event (connection acknowledgement)
    await writer.write_text(sse_queue, "")
    yield await sse_queue.get()

    # Send initial agent status so the frontend shows progress immediately
    await writer.write_agent_status(sse_queue, "Analyzing your request...")
    yield await sse_queue.get()

    # Wrap the SDK generator so we inject ": keepalive\n\n" SSE comments every
    # KEEPALIVE_INTERVAL seconds while waiting for the next chunk.  ALB idle
    # timeout is 300 s (raised from 60 s); keepalive every 20 s keeps it alive.
    KEEPALIVE_INTERVAL = 20.0

    async def _sdk_with_keepalive():
        gen = _get_strands_runtime().sdk_query_streaming(
            prompt=message,
            tenant_id=tenant_id,
            user_id=user_id,
            tier=tier or "advanced",
            session_id=session_id,
            messages=messages,
            package_context=package_context,
            username=username,
        )
        aiter = gen.__aiter__()
        pending_task = None
        while True:
            try:
                # Reuse pending task if previous iteration timed out (don't lose chunks)
                if pending_task is None:
                    pending_task = asyncio.create_task(aiter.__anext__())

                done, _ = await asyncio.wait({pending_task}, timeout=KEEPALIVE_INTERVAL)

                if done:
                    # Task completed - get result and clear pending
                    chunk = pending_task.result()
                    pending_task = None
                    yield chunk
                else:
                    # Timeout - yield keepalive but keep the task pending
                    yield {"type": "_keepalive"}
            except StopAsyncIteration:
                break
            except Exception:
                # Handle StopAsyncIteration from the task result
                if pending_task and pending_task.done():
                    try:
                        pending_task.result()
                    except StopAsyncIteration:
                        break
                raise

    try:
        async for chunk in _sdk_with_keepalive():
            chunk_type = chunk.get("type", "")

            if chunk_type == "_keepalive":
                yield ": keepalive\n\n"

            elif chunk_type == "text":
                text_data = chunk.get("data", "")
                logger.debug("SSE text event: len=%d", len(text_data))
                full_response_parts.append(text_data)
                await writer.write_text(sse_queue, text_data)
                yield await sse_queue.get()

            elif chunk_type == "tool_use":
                tool_name = chunk.get("name", "")
                tool_input = chunk.get("input", {})
                # Parse stringified input if needed (Strands may send JSON string)
                if isinstance(tool_input, str):
                    try:
                        tool_input = json.loads(tool_input)
                    except (json.JSONDecodeError, ValueError):
                        tool_input = {"raw": tool_input} if tool_input else {}
                # Track tool start time for duration calculation
                if tool_name:
                    _tool_start_times[tool_name] = time.perf_counter()
                await writer.write_tool_use(
                    sse_queue,
                    tool_name,
                    tool_input,
                    tool_use_id=chunk.get("tool_use_id", ""),
                )
                yield await sse_queue.get()

            elif chunk_type == "tool_result":
                tr_name = chunk.get("name", "")
                if not tr_name:
                    logger.debug("Skipping empty-name tool_result: keys=%s", list(chunk.keys()))
                    continue
                # Compute tool duration from start time
                start_t = _tool_start_times.pop(tr_name, None)
                duration_ms = int((time.perf_counter() - start_t) * 1000) if start_t is not None else None
                if duration_ms is not None:
                    _tool_timings.append({
                        "tool_name": tr_name,
                        "duration_ms": duration_ms,
                    })
                # Detect tool failure from result content
                result_data = chunk.get("result", {})
                is_error = False
                if isinstance(result_data, dict):
                    is_error = result_data.get("is_error", False) or "error" in str(result_data.get("status", "")).lower()
                elif isinstance(result_data, str):
                    is_error = result_data.strip().lower().startswith("error")
                if is_error:
                    _tool_failures.append({
                        "tool_name": tr_name,
                        "error_message": str(result_data)[:500],
                        "duration_ms": duration_ms,
                    })
                await writer.write_tool_result(sse_queue, tr_name, result_data)
                yield await sse_queue.get()

            elif chunk_type == "state_update":
                await writer.write_state_update(
                    sse_queue,
                    chunk.get("state_type", ""),
                    {k: v for k, v in chunk.items() if k not in ("type", "state_type")},
                )
                yield await sse_queue.get()

            elif chunk_type == "agent_status":
                await writer.write_agent_status(
                    sse_queue,
                    chunk.get("status", ""),
                    chunk.get("detail", ""),
                )
                yield await sse_queue.get()

            elif chunk_type == "complete":
                complete_text = chunk.get("text", "")
                complete_metadata = {}
                if "tools_called" in chunk:
                    complete_metadata["tools_called"] = chunk.get("tools_called") or []
                if "usage" in chunk:
                    complete_metadata["usage"] = chunk.get("usage") or {}
                # Include total stream duration in complete event
                duration_ms = int((time.perf_counter() - stream_start) * 1000)
                complete_metadata["duration_ms"] = duration_ms
                # Include per-tool timings for frontend visibility
                if _tool_timings:
                    complete_metadata["tool_timings"] = _tool_timings
                # Include tool failures for frontend visibility
                if _tool_failures:
                    complete_metadata["tool_failures"] = _tool_failures
                logger.debug("SSE complete: complete_text_len=%d full_parts=%d duration_ms=%d", len(complete_text), len(full_response_parts), duration_ms)
                if not full_response_parts and complete_text:
                    full_response_parts.append(complete_text)
                    await writer.write_text(sse_queue, complete_text)
                    yield await sse_queue.get()

                # Guaranteed fallback: never send blank response to frontend
                if not full_response_parts:
                    fallback = "[No response generated. Please try again.]"
                    logger.warning("No text generated for session=%s user=%s — emitting fallback", session_id, user_id)
                    full_response_parts.append(fallback)
                    await writer.write_text(sse_queue, fallback)
                    yield await sse_queue.get()

                # Persist assistant response to DynamoDB
                if session_id and full_response_parts:
                    try:
                        full_text = "".join(full_response_parts)
                        await asyncio.to_thread(add_message, session_id, "assistant", full_text, tenant_id, user_id)
                    except Exception:
                        logger.warning("Failed to persist assistant message for session=%s user=%s", session_id, user_id)
                await writer.write_complete(
                    sse_queue,
                    metadata=complete_metadata if complete_metadata else None,
                )
                yield await sse_queue.get()
                # Emit tool timing telemetry to CloudWatch
                _emit_tool_timings(_tool_timings, tenant_id, user_id, session_id, duration_ms)
                _emit_tool_failures(_tool_failures, tenant_id, user_id, session_id)
                # Score conversation quality
                try:
                    from .telemetry.conversation_scorer import score_conversation
                    from .telemetry.cloudwatch_emitter import emit_telemetry_event
                    quality = score_conversation(
                        completed=True,
                        error_count=0,
                        tool_timings=_tool_timings,
                        tool_failures=_tool_failures,
                        response_text="".join(full_response_parts),
                        tools_called=complete_metadata.get("tools_called", []),
                        user_message=message,
                        duration_ms=duration_ms,
                    )
                    emit_telemetry_event(
                        event_type="conversation.quality",
                        tenant_id=tenant_id,
                        data={
                            "score": quality["score"],
                            "breakdown": quality["breakdown"],
                            "flags": quality["flags"],
                            "session_id": session_id or "",
                        },
                        session_id=session_id,
                        user_id=user_id,
                    )
                except Exception:
                    logger.debug("Failed to score conversation quality", exc_info=True)
                return

            elif chunk_type == "error":
                error_msg = chunk.get("error", "Unknown error")
                await writer.write_error(sse_queue, error_msg)
                from .error_webhook import notify_streaming_error
                notify_streaming_error(
                    "/api/chat/stream", "POST",
                    Exception(error_msg),
                    tenant_id=tenant_id, user_id=user_id, session_id=session_id or "",
                )
                # Classify and tag the Langfuse trace for filtering
                from .telemetry.langfuse_client import notify_trace_error
                notify_trace_error(session_id or "", error_msg)
                yield await sse_queue.get()
                return

        # Fallback COMPLETE if generator exhausts without a complete event
        if session_id and full_response_parts:
            try:
                full_text = "".join(full_response_parts)
                await asyncio.to_thread(add_message, session_id, "assistant", full_text, tenant_id, user_id)
            except Exception:
                logger.warning("Failed to persist assistant message for session=%s user=%s", session_id, user_id)
        fallback_duration_ms = int((time.perf_counter() - stream_start) * 1000)
        await writer.write_complete(sse_queue, metadata={"duration_ms": fallback_duration_ms})
        yield await sse_queue.get()
        _emit_tool_timings(_tool_timings, tenant_id, user_id, session_id, fallback_duration_ms)
        _emit_tool_failures(_tool_failures, tenant_id, user_id, session_id)

    except asyncio.CancelledError:
        logger.debug("Streaming client disconnected user=%s session=%s", user_id, session_id)
        return
    except Exception as e:
        logger.error("Streaming chat error user=%s session=%s: %s", user_id, session_id, str(e), exc_info=True)
        await writer.write_error(sse_queue, str(e))
        from .error_webhook import notify_streaming_error
        notify_streaming_error(
            "/api/chat/stream", "POST", e,
            tenant_id=tenant_id, user_id=user_id, session_id=session_id or "",
        )
        # Classify and tag the Langfuse trace for filtering
        from .telemetry.langfuse_client import notify_trace_error
        notify_trace_error(session_id or "", str(e))
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
        username = user.username or user.user_id

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

        resolved_package_context = None
        try:
            resolved_package_context = resolve_context(
                tenant_id=tenant_id,
                user_id=user_id,
                session_id=message.session_id or "",
                explicit_package_id=message.package_id,
            )
            if (
                message.package_id
                and message.session_id
                and resolved_package_context.is_package_mode
            ):
                set_active_package(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    session_id=message.session_id,
                    package_id=resolved_package_context.package_id,
                )
        except Exception:
            logger.warning(
                "Package context resolution failed for session=%s",
                message.session_id,
                exc_info=True,
            )
            resolved_package_context = None

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
                package_context=resolved_package_context,
                username=username,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # ------------------------------------------------------------------
    # POST /api/generate-title - Generate smart session title
    # ------------------------------------------------------------------
    @router.post("/api/generate-title")
    async def generate_title(
        req: GenerateTitleRequest,
        authorization: Optional[str] = Header(None),
    ):
        """Generate a smart session title from the user's first message.

        Uses Claude to extract key concepts (project name, document type, action)
        and returns a concise, meaningful title.
        """
        try:
            from anthropic import Anthropic

            client = Anthropic()
            prompt = f"""Given the user's first message in a conversation, generate a short, concise session title (3-6 words max).
Extract key information like:
- Project/initiative name
- Document type (SOW, IGCE, etc.)
- Main action or focus

User message: "{req.message}"
"""
            if req.response_snippet:
                prompt += f"\nInitial response preview: {req.response_snippet[:100]}"

            prompt += "\n\nRespond with ONLY the title, no explanations."

            response = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=50,
                messages=[{"role": "user", "content": prompt}],
            )

            title = response.content[0].text.strip()
            # Ensure title is not empty and reasonable length
            if title and len(title) < 100:
                return {"title": title}
        except Exception as e:
            logger.warning(f"Failed to generate title: {e}")

        return {"title": "New Session"}

    # ------------------------------------------------------------------
    # GET /api/health - Health check (no auth required)
    # ------------------------------------------------------------------
    @router.get("/api/health")
    async def health_check():
        """Return service health status, available agents, and EAGLE tools.

        This endpoint does not require authentication and is intended
        for load-balancer health probes and operational dashboards.
        """
        knowledge_base = check_knowledge_base_health()
        return {
            "status": "healthy",
            "service": "EAGLE – NCI Acquisition Assistant",
            "version": "4.0.0",
            "model": _get_strands_runtime().MODEL,
            "services": {
                "bedrock": True,
                "dynamodb": True,
                "cognito": True,
                "s3": True,
                "knowledge_metadata_table": knowledge_base["metadata_table"]["ok"],
                "knowledge_document_bucket": knowledge_base["document_bucket"]["ok"],
            },
            "knowledge_base": knowledge_base,
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
            "tools": [tool["name"] for tool in _get_strands_runtime().EAGLE_TOOLS],
            "features": {
                "persistent_sessions": auth_config.require_auth,  # sessions require auth
                "auth_required": auth_config.require_auth,
                "dev_mode": auth_config.dev_mode,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    return router
