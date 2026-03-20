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
from __future__ import annotations

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

from .error_webhook import notify_error, close_webhook_client
from .teams_notifier import notify_startup, notify_suspicious, close_notifier_client
from .daily_scheduler import start_scheduler, stop_scheduler

# ── Logging ──────────────────────────────────────────────────────────
from .telemetry.log_context import configure_logging
configure_logging(level=logging.INFO)
logger = logging.getLogger("eagle")


def _default_router_names() -> list[str] | None:
    raw = os.getenv("EAGLE_APP_ROUTERS", "").strip()
    if not raw:
        return None
    return [part.strip() for part in raw.split(",") if part.strip()]


def _include_selected_routers(app: FastAPI, router_names: list[str] | None) -> None:
    selected = set(router_names or [
        "streaming",
        "chat",
        "feedback",
        "health",
        "mcp",
        "analytics",
        "user",
        "skills",
        "workspaces",
        "templates",
        "tenants",
        "sessions",
        "documents",
        "packages",
        "admin",
    ])

    if "streaming" in selected:
        from .streaming_routes import create_streaming_router

        app.include_router(create_streaming_router(subscription_service))

    if "chat" in selected:
        from .routers.chat import router as chat_router
        from .routers.chat import set_sessions_ref as set_chat_sessions_ref, set_telemetry_ref

        app.include_router(chat_router)
        set_chat_sessions_ref(SESSIONS)
        set_telemetry_ref(TELEMETRY_LOG)

    if "feedback" in selected:
        from .routers.feedback import router as feedback_router

        app.include_router(feedback_router)

    if "health" in selected:
        from .routers.health import router as health_router

        app.include_router(health_router)

    if "mcp" in selected:
        from .routers.mcp import router as mcp_router

        app.include_router(mcp_router)

    if "analytics" in selected:
        from .routers.analytics import router as analytics_router

        app.include_router(analytics_router)

    if "user" in selected:
        from .routers.user import router as user_router

        app.include_router(user_router)

    if "skills" in selected:
        from .routers.skills import router as skills_router

        app.include_router(skills_router)

    if "workspaces" in selected:
        from .routers.workspaces import router as workspaces_router

        app.include_router(workspaces_router)

    if "templates" in selected:
        from .routers.templates import router as templates_router

        app.include_router(templates_router)

    if "tenants" in selected:
        from .routers.tenants import router as tenants_router

        app.include_router(tenants_router)

    if "sessions" in selected:
        from .routers.sessions import router as sessions_router, set_sessions_ref

        app.include_router(sessions_router)
        set_sessions_ref(SESSIONS)

    if "documents" in selected:
        from .routers.documents import router as documents_router
        from .routers.documents import set_sessions_ref as set_documents_sessions_ref

        app.include_router(documents_router)
        set_documents_sessions_ref(SESSIONS)

    if "packages" in selected:
        from .routers.packages import router as packages_router

        app.include_router(packages_router)

    if "admin" in selected:
        from .routers.admin import router as admin_router

        app.include_router(admin_router)

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


def create_app(router_names: list[str] | None = None) -> FastAPI:
    app = FastAPI(
        title="EAGLE – NCI Acquisition Assistant",
        version="4.0.0",
        description="Multi-tenant acquisition intake system with Anthropic SDK, auth, persistence, and analytics",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

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

    _include_selected_routers(app, router_names)

    @app.get("/api/document-changelog")
    async def get_document_key_changelog_endpoint(
        key: str,
        limit: int = 50,
        user: UserContext = Depends(get_user_from_header),
    ):
        """Get changelog entries for a document by S3 key."""
        from .changelog_store import list_document_changelog_entries

        tenant_id = user.tenant_id
        if not key.startswith(f"eagle/{tenant_id}/"):
            raise HTTPException(status_code=403, detail="Access denied")

        entries = list_document_changelog_entries(tenant_id, key, limit)
        return {"entries": entries, "count": len(entries)}

    return app


app = create_app(_default_router_names())

# Backwards-compatible re-exports for tests and legacy imports.
try:
    from .routers.chat import EagleChatRequest, EagleChatResponse
except Exception:  # pragma: no cover - optional when chat router is intentionally excluded
    pass


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("APP_PORT", "8000"))
    uvicorn.run(app, host="127.0.0.1", port=port)
