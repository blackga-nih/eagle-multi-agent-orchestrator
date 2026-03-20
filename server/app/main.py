"""
EAGLE – NCI Acquisition Assistant
Full-featured FastAPI application with modular routers.

All endpoints are now organized into routers under app/routers/:
- chat: REST/WebSocket chat, telemetry, tools info
- documents: S3 browser, export, upload, edit
- packages: Acquisition package CRUD
- sessions: Session management
- admin: Admin dashboard, user management
- feedback: User feedback
- health: Health checks
- etc.
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

from fastapi import FastAPI, Request, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Optional, Dict, List
from collections import deque
from datetime import datetime
import json
import time
import logging
import os

# EAGLE modules
from .cognito_auth import UserContext, extract_user_context
from .subscription_service import SubscriptionService
from .streaming_routes import create_streaming_router
from .routers import (
    feedback_router, health_router, mcp_router, analytics_router,
    user_router, skills_router, workspaces_router, templates_router,
    tenants_router, sessions_router, documents_router, packages_router,
    admin_router, chat_router,
)
from .routers.sessions import set_sessions_ref
from .routers.documents import set_sessions_ref as set_documents_sessions_ref
from .routers.chat import set_sessions_ref as set_chat_sessions_ref, set_telemetry_ref

from .error_webhook import notify_error, close_webhook_client
from .teams_notifier import notify_startup, notify_suspicious, close_notifier_client
from .daily_scheduler import start_scheduler, stop_scheduler

# ── Logging ──────────────────────────────────────────────────────────
from .telemetry.log_context import configure_logging
configure_logging(level=logging.INFO)
logger = logging.getLogger("eagle")

app = FastAPI(
    title="EAGLE – NCI Acquisition Assistant",
    version="4.0.0",
    description="Multi-tenant acquisition intake system with Anthropic SDK, auth, persistence, and analytics"
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


@app.on_event("startup")
async def startup_teams_notifier():
    notify_startup()
    start_scheduler()


@app.on_event("shutdown")
async def shutdown_webhook_client():
    await close_webhook_client()


@app.on_event("shutdown")
async def shutdown_teams_notifier():
    stop_scheduler()
    await close_notifier_client()


# ── Feature Flags ────────────────────────────────────────────────────
REQUIRE_AUTH = os.getenv("REQUIRE_AUTH", "false").lower() == "true"

# ── Initialize existing services ─────────────────────────────────────
subscription_service = SubscriptionService()

# ── Shared state (in-memory fallback) ────────────────────────────────
SESSIONS: Dict[str, List[dict]] = {}
TELEMETRY_LOG: deque = deque(maxlen=500)


# ── Auth Helpers ─────────────────────────────────────────────────────

async def get_user_from_header(authorization: Optional[str] = Header(None)) -> UserContext:
    """Extract user from Authorization header (EAGLE Cognito auth)."""
    user, error = extract_user_context(authorization)
    if REQUIRE_AUTH and user.user_id == "anonymous":
        raise HTTPException(status_code=401, detail=error or "Authentication required")
    return user


# ══════════════════════════════════════════════════════════════════════
# INCLUDE ROUTERS
# ══════════════════════════════════════════════════════════════════════

# SSE streaming router
streaming_router = create_streaming_router(subscription_service)
app.include_router(streaming_router)

# Modular routers
app.include_router(chat_router)
app.include_router(feedback_router)
app.include_router(health_router)
app.include_router(mcp_router)
app.include_router(analytics_router)
app.include_router(user_router)
app.include_router(skills_router)
app.include_router(workspaces_router)
app.include_router(templates_router)
app.include_router(tenants_router)
app.include_router(sessions_router)
app.include_router(documents_router)
app.include_router(packages_router)
app.include_router(admin_router)

# Wire up shared state for routers (in-memory fallback)
set_sessions_ref(SESSIONS)
set_documents_sessions_ref(SESSIONS)
set_chat_sessions_ref(SESSIONS)
set_telemetry_ref(TELEMETRY_LOG)


# ── Document Changelog Endpoint ──────────────────────────────────────


@app.get("/api/document-changelog")
async def get_document_key_changelog_endpoint(
    key: str,
    limit: int = 50,
    user: UserContext = Depends(get_user_from_header),
):
    """Get changelog entries for a document by S3 key."""
    from .changelog_store import list_document_changelog_entries

    tenant_id = user.tenant_id

    # Security: ensure key is within user's prefix
    if not key.startswith(f"eagle/{tenant_id}/"):
        raise HTTPException(status_code=403, detail="Access denied")

    entries = list_document_changelog_entries(tenant_id, key, limit)
    return {"entries": entries, "count": len(entries)}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("APP_PORT", "8000"))
    uvicorn.run(app, host="127.0.0.1", port=port)
