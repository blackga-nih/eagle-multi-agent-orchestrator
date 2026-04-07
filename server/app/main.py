"""
EAGLE – NCI Acquisition Assistant
Full-featured FastAPI application merging:
- Original multi-tenant architecture (SSE streaming, admin HTML pages, tenant costs)
- EAGLE option1-simple (Anthropic SDK, document export, S3 browser, admin dashboard, WebSocket)
"""

import os as _os
from pathlib import Path as _Path
from dotenv import load_dotenv

# Load .env from project root (parent of app/) — must happen before any other imports
_env_path = _Path(__file__).resolve().parent.parent / ".env"
print(f"[EAGLE STARTUP] .env path: {_env_path} exists={_env_path.exists()}")
if _env_path.exists():
    load_dotenv(str(_env_path), override=True)
    print(
        f"[EAGLE STARTUP] Loaded .env, ANTHROPIC_API_KEY set={bool(_os.getenv('ANTHROPIC_API_KEY'))}, DEV_MODE={_os.getenv('DEV_MODE')}"
    )
else:
    load_dotenv(override=True)
    print(f"[EAGLE STARTUP] No .env found at {_env_path}, using defaults")

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
from collections import deque
from datetime import datetime, timezone
import json
import time
import logging
import os
from contextlib import asynccontextmanager

# Services
from .subscription_service import SubscriptionService
from .admin_service import calculate_cost, check_rate_limit, record_request_cost
from .package_context_service import resolve_context, set_active_package
from .session_store import (
    add_message,
    create_session as eagle_create_session,
    get_messages_for_anthropic,
    get_session as eagle_get_session,
)
from .streaming_routes import create_streaming_router
from .strands_agentic_service import MODEL, sdk_query

# Routers
from .routers.admin import router as admin_router
from .routers.analytics import router as analytics_router
from .routers.chat import (
    router as chat_router,
    set_sessions_ref as set_chat_sessions_ref,
    set_telemetry_ref as set_chat_telemetry_ref,
)
from .routers.commands import router as commands_router
from .routers.documents import (
    router as documents_router,
    set_sessions_ref as set_documents_sessions_ref,
)
from .routers.feedback import router as feedback_router
from .routers.feedback_actions import router as feedback_actions_router
from .routers.triage_actions import router as triage_actions_router
from .routers.health import router as health_router
from .routers.knowledge import router as knowledge_router
from .routers.packages import router as packages_router
from .routers.packages import compat_router as packages_compat_router
from .routers.sessions import (
    router as sessions_router,
    set_sessions_ref as set_sessions_router_ref,
)
from .routers.skills import router as skills_router
from .routers.tags import router as tags_router
from .routers.tenants import router as tenants_router
from .routers.templates import (
    router as templates_router,
    compat_router as templates_compat_router,
)
from .routers.user import router as user_router
from .routers.workspaces import router as workspaces_router
from .routers.dependencies import get_user_from_header, get_session_context
from .cognito_auth import UserContext

from .error_webhook import notify_error, close_webhook_client
from .teams_notifier import (
    close_notifier_client,
    notify_startup,
    notify_suspicious,
)
from .daily_scheduler import start_scheduler, stop_scheduler

# ── Logging ──────────────────────────────────────────────────────────
from .telemetry.log_context import configure_logging

configure_logging(level=logging.INFO)
logger = logging.getLogger("eagle")
# Compatibility note: REQUIRE_AUTH is still the controlling auth flag, even
# though the guarded endpoint implementations now live in router modules.


@asynccontextmanager
async def _lifespan(app):
    """FastAPI lifespan handler (replaces deprecated @app.on_event)."""
    # Startup
    notify_startup()
    start_scheduler()
    # Warm config cache so first request avoids cold-start DynamoDB read
    try:
        from .config_store import list_config

        list_config()
    except Exception:
        pass
    yield
    # Shutdown
    await close_webhook_client()
    stop_scheduler()
    await close_notifier_client()
    from .jira_client import close_jira_client

    close_jira_client()


app = FastAPI(
    title="EAGLE – NCI Acquisition Assistant",
    version="4.0.0",
    description="Multi-tenant acquisition intake system with Anthropic SDK, auth, persistence, and analytics",
    lifespan=_lifespan,
)

# ── CORS Middleware ──────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request Timing Middleware ─────────────────────────────────────────
@app.middleware("http")
async def request_timing_middleware(request: Request, call_next):
    """Log every request with duration_ms for CloudWatch Insights queries."""
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = int((time.perf_counter() - start) * 1000)
    logger.info(
        "request_completed",
        extra={
            "endpoint": request.url.path,
            "method": request.method,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    return response


# ── Error Webhook Exception Handlers ─────────────────────────────────
from fastapi.responses import JSONResponse


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTPExceptions — send webhook on 5xx, notify suspicious 404s on unknown routes."""
    if exc.status_code >= 500:
        notify_error(request=request, status_code=exc.status_code, exception=exc)
    elif exc.status_code == 404:
        # Only alert on truly unknown routes — Starlette uses exactly "Not Found"
        # for unmatched paths. App-level 404s use specific messages like
        # "Document not found", "Session not found", etc.
        is_unknown_route = (
            request.url.path.startswith("/api/") and exc.detail == "Not Found"
        )
        logger.info(
            "http_404",
            extra={
                "path": request.url.path,
                "method": request.method,
                "detail": exc.detail,
                "is_unknown_route": is_unknown_route,
            },
        )
        if is_unknown_route:
            from .telemetry.log_context import _tenant_id, _user_id

            notify_suspicious(
                "404",
                f"{request.method} {request.url.path}",
                tenant_id=_tenant_id.get(""),
                user_id=_user_id.get(""),
            )
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Handle unhandled exceptions — send webhook with traceback, return 500."""
    import traceback

    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    notify_error(request=request, status_code=500, exception=exc, traceback_str=tb)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# ── Initialize existing services ─────────────────────────────────────
subscription_service = SubscriptionService()
USE_PERSISTENT_SESSIONS = os.getenv("USE_PERSISTENT_SESSIONS", "true").lower() == "true"

# ── In-memory session store (fallback when persistent sessions disabled)
SESSIONS: Dict[str, List[dict]] = {}
set_chat_sessions_ref(SESSIONS)
set_sessions_router_ref(SESSIONS)
set_documents_sessions_ref(SESSIONS)

# ── Telemetry ring buffer ────────────────────────────────────────────
TELEMETRY_LOG: deque = deque(maxlen=500)
set_chat_telemetry_ref(TELEMETRY_LOG)


def _log_telemetry(entry: dict):
    entry.setdefault(
        "timestamp", datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )
    TELEMETRY_LOG.append(entry)
    logger.info(json.dumps(entry, default=str))


# ══════════════════════════════════════════════════════════════════════
# EAGLE ENDPOINTS (new from option1-simple)
# ══════════════════════════════════════════════════════════════════════

# ── REST chat endpoint (EAGLE - Anthropic SDK) ───────────────────────


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


@app.post("/api/chat", response_model=EagleChatResponse)
async def api_chat(
    req: EagleChatRequest, user: UserContext = Depends(get_user_from_header)
):
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
        _final_text: str = ""
        async for _sdk_msg in sdk_query(
            prompt=req.message,
            tenant_id=tenant_id,
            user_id=user_id,
            tier=user.tier or "advanced",
            session_id=session_id,
            messages=messages[:-1],  # History excluding current user message
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
                if not isinstance(_raw, dict):
                    _raw = {
                        "input_tokens": getattr(_raw, "input_tokens", 0),
                        "output_tokens": getattr(_raw, "output_tokens", 0),
                    }
                # Strands SDK uses camelCase (inputTokens); normalize to snake_case
                _usage = {
                    "input_tokens": _raw.get("input_tokens") or _raw.get("inputTokens", 0),
                    "output_tokens": _raw.get("output_tokens") or _raw.get("outputTokens", 0),
                    "total_tokens": _raw.get("total_tokens") or _raw.get("totalTokens", 0),
                    "cache_read_input_tokens": _raw.get("cache_read_input_tokens") or _raw.get("cacheReadInputTokens", 0),
                    "cache_creation_input_tokens": _raw.get("cache_creation_input_tokens") or _raw.get("cacheWriteInputTokens", 0),
                }
                _final_text = str(getattr(_sdk_msg, "result", "") or "")
        _response_text = "".join(_text_parts) or _final_text
        result = {
            "text": _response_text,
            "usage": _usage,
            "model": MODEL,
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
            tenant_id,
            user_id,
            session_id,
            input_tokens,
            output_tokens,
            model=result.get("model", MODEL),
            tools_used=result.get("tools_called", []),
            response_time_ms=elapsed_ms,
        )

        _log_telemetry(
            {
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
            }
        )

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
        raise HTTPException(
            status_code=500, detail="Internal server error processing chat request"
        )


# ══════════════════════════════════════════════════════════════════════
# SSE STREAMING ROUTER (preserved from C3 integration)
# ══════════════════════════════════════════════════════════════════════

# Include SSE streaming router for the active Strands runtime.
# Cache reload ownership now lives in the admin router, which clears
# _plugin_cache, _prompt_cache, _config_cache, and _template_cache.
streaming_router = create_streaming_router(subscription_service)
app.include_router(admin_router)
app.include_router(analytics_router)
app.include_router(chat_router)
app.include_router(commands_router)
app.include_router(documents_router)
app.include_router(feedback_router)
app.include_router(feedback_actions_router)
app.include_router(triage_actions_router)
app.include_router(health_router)
app.include_router(knowledge_router)
app.include_router(packages_router)
app.include_router(packages_compat_router)
app.include_router(sessions_router)
app.include_router(skills_router)
app.include_router(tags_router)
app.include_router(tenants_router)
app.include_router(templates_router)
app.include_router(templates_compat_router)
app.include_router(user_router)
app.include_router(workspaces_router)
app.include_router(streaming_router)


def create_app(enabled_routers: Optional[List[str]] = None) -> FastAPI:
    """Compatibility app factory retained for tests and older harnesses.

    The backend now composes the shared module-level ``app`` directly during
    import. The optional ``enabled_routers`` argument is accepted for backward
    compatibility with older tests, but the router selection is no longer
    performed in ``main.py``.
    """
    return app


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("APP_PORT", "8000"))
    # Bind to localhost for security - use reverse proxy for external access
    uvicorn.run(app, host="127.0.0.1", port=port)
