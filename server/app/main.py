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
    print(f"[EAGLE STARTUP] Loaded .env, ANTHROPIC_API_KEY set={bool(_os.getenv('ANTHROPIC_API_KEY'))}, DEV_MODE={_os.getenv('DEV_MODE')}")
else:
    load_dotenv(override=True)
    print(f"[EAGLE STARTUP] No .env found at {_env_path}, using defaults")

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, List, Optional
from collections import deque
from datetime import datetime, timezone
import json
import time
import logging
import os
from contextlib import asynccontextmanager

# Existing multi-tenant modules (preserved)
from .subscription_service import SubscriptionService
from .admin_cost_service import AdminCostService
from .document_classification_service import classify_document, extract_text_preview
from .document_export import export_document
from .document_service import create_package_document_version
from .document_store import get_document, list_package_documents
from .routers.admin import router as admin_router
from .routers.analytics import router as analytics_router
from .routers.chat import EagleChatRequest, router as chat_router, set_sessions_ref as set_chat_sessions_ref, set_telemetry_ref as set_chat_telemetry_ref
from .routers.documents import router as documents_router, set_sessions_ref as set_documents_sessions_ref
from .routers.feedback import router as feedback_router
from .routers.health import router as health_router
from .routers.mcp import router as mcp_router
from .routers.packages import router as packages_router
from .routers.packages import compat_router as packages_compat_router
from .routers.sessions import router as sessions_router, set_sessions_ref as set_sessions_router_ref
from .routers.skills import router as skills_router
from .routers.tags import router as tags_router
from .routers.tenants import router as tenants_router
from .routers.templates import router as templates_router, compat_router as templates_compat_router
from .routers.user import router as user_router
from .routers.workspaces import router as workspaces_router
from .routers.dependencies import get_user_from_header
from .routers.documents import _delete_upload, _get_upload, _put_upload
from .streaming_routes import create_streaming_router
from .package_store import get_package

from .error_webhook import notify_error, close_webhook_client
from .teams_notifier import notify_startup, notify_suspicious, close_notifier_client
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
    """Handle HTTPExceptions — send webhook on 5xx, notify suspicious 404s."""
    if exc.status_code >= 500:
        notify_error(request=request, status_code=exc.status_code, exception=exc)
    elif exc.status_code == 404 and request.url.path not in ("/api/health", "/favicon.ico"):
        notify_suspicious("404", f"{request.method} {request.url.path}")
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
admin_cost_service = AdminCostService()

# ── In-memory session store (fallback when persistent sessions disabled)
SESSIONS: Dict[str, List[dict]] = {}
set_chat_sessions_ref(SESSIONS)
set_sessions_router_ref(SESSIONS)
set_documents_sessions_ref(SESSIONS)

# ── Telemetry ring buffer ────────────────────────────────────────────
TELEMETRY_LOG: deque = deque(maxlen=500)
set_chat_telemetry_ref(TELEMETRY_LOG)


def _log_telemetry(entry: dict):
    entry.setdefault("timestamp", datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    TELEMETRY_LOG.append(entry)
    logger.info(json.dumps(entry, default=str))


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
app.include_router(documents_router)
app.include_router(feedback_router)
app.include_router(health_router)
app.include_router(mcp_router)
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


# ══════════════════════════════════════════════════════════════════════
# HEALTH CHECK (frontend now served by Next.js on port 3000)
# ══════════════════════════════════════════════════════════════════════

@app.get("/api/ping")
async def ping():
    """Lightweight liveness probe — no I/O, no dependencies."""
    return {"status": "healthy"}


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
