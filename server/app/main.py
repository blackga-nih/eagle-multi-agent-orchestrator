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

from fastapi import (
    FastAPI,
    HTTPException,
    Request,
    Header,
    Depends,
    WebSocket,
    UploadFile,
    File,
)
from fastapi.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketDisconnect
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
import base64
import io
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone
import json
import time
import logging
import os
from contextlib import asynccontextmanager

# Existing multi-tenant modules (preserved)
from .subscription_service import SubscriptionService
from .admin_cost_service import AdminCostService
from .document_classification_service import classify_document, extract_text_preview
from .document_export import ExportDependencyError, export_document
from .document_service import (
    create_package_document_version,
    get_document_markdown_s3_key,
)
from .document_store import get_document
from .document_key_utils import is_allowed_document_key, extract_package_document_ref
from .doc_type_registry import normalize_doc_type
from .spreadsheet_edit_service import extract_xlsx_preview_payload
from .spreadsheet_edit_service import save_xlsx_preview_edits
from .document_ai_edit_service import (
    extract_docx_preview_payload,
    save_docx_preview_edits,
)
from .routers.admin import router as admin_router
from .routers.admin import (
    GENERIC_ANALYTICS_ERROR,
    _get_result_error,
    _sanitize_result_error,
    cost_service,
    get_dashboard_stats,
    get_top_users,
    get_user_stats,
)
from .routers.analytics import router as analytics_router
from .routers.chat import (
    router as chat_router,
    set_sessions_ref as set_chat_sessions_ref,
    set_telemetry_ref as set_chat_telemetry_ref,
)
from .routers.documents import (
    router as documents_router,
    set_sessions_ref as set_documents_sessions_ref,
)
from .routers.documents import GENERIC_EDIT_ERROR
from .routers.feedback import router as feedback_router
from .routers.health import router as health_router
from .routers.commands import router as commands_router
from .routers.mcp import router as mcp_router
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
from .cognito_auth import UserContext, DEV_MODE, extract_user_context
from .config import auth as auth_config

REQUIRE_AUTH = auth_config.require_auth
from . import feedback_store
from .auth import get_current_user
from .admin_auth import get_admin_user, verify_tenant_admin
from .admin_service import calculate_cost, check_rate_limit, record_request_cost
from .models import SubscriptionTier
from .package_context_service import resolve_context, set_active_package
from .session_store import (
    add_message,
    create_session as eagle_create_session,
    delete_session as eagle_delete_session,
    get_messages,
    get_messages_for_anthropic,
    get_session as eagle_get_session,
    get_tenant_usage_overview,
    get_usage_summary,
    list_sessions as eagle_list_sessions,
    list_tenant_sessions,
    update_session as eagle_update_session,
)
from .streaming_routes import create_streaming_router
from .strands_agentic_service import EAGLE_TOOLS, MODEL, sdk_query
from .package_store import get_package

from .error_webhook import notify_error, close_webhook_client
from .teams_notifier import (
    close_notifier_client,
    notify_feedback,
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
from fastapi.responses import JSONResponse, StreamingResponse


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
admin_cost_service = AdminCostService()
GENERIC_TRACE_ERROR = "Trace data is temporarily unavailable."

# ── S3 Configuration ─────────────────────────────────────────────────
_S3_BUCKET = os.getenv("S3_BUCKET", "eagle-documents-dev")
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
                _usage = (
                    _raw
                    if isinstance(_raw, dict)
                    else {
                        "input_tokens": getattr(_raw, "input_tokens", 0),
                        "output_tokens": getattr(_raw, "output_tokens", 0),
                    }
                )
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


# ── Session management endpoints (EAGLE enhanced) ────────────────────


@app.get("/api/sessions")
async def api_list_sessions(
    limit: int = 50, user: UserContext = Depends(get_user_from_header)
):
    """List sessions for the current user."""
    tenant_id, user_id, _ = get_session_context(user)

    if USE_PERSISTENT_SESSIONS:
        sessions = eagle_list_sessions(tenant_id, user_id, limit)
    else:
        sessions = []
        for sid, msgs in SESSIONS.items():
            user_msgs = [m for m in msgs if m.get("role") == "user"]
            first_msg = user_msgs[0]["content"][:60] if user_msgs else "Empty"
            sessions.append(
                {
                    "session_id": sid,
                    "message_count": len(msgs),
                    "preview": first_msg,
                }
            )

    return {"sessions": sessions, "count": len(sessions)}


@app.post("/api/sessions")
async def api_create_session(
    title: Optional[str] = None, user: UserContext = Depends(get_user_from_header)
):
    """Create a new session."""
    tenant_id, user_id, _ = get_session_context(user)

    if USE_PERSISTENT_SESSIONS:
        session = eagle_create_session(tenant_id, user_id, title=title)
    else:
        session_id = str(uuid.uuid4())
        SESSIONS[session_id] = []
        session = {"session_id": session_id, "title": title or "New Conversation"}

    return session


@app.get("/api/sessions/{session_id}")
async def api_get_session(
    session_id: str, user: UserContext = Depends(get_user_from_header)
):
    """Get session details."""
    tenant_id, user_id, _ = get_session_context(user)

    if USE_PERSISTENT_SESSIONS:
        session = eagle_get_session(session_id, tenant_id, user_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return session
    else:
        if session_id not in SESSIONS:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"session_id": session_id, "message_count": len(SESSIONS[session_id])}


class UpdateSessionRequest(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None
    metadata: Optional[Dict] = None


@app.patch("/api/sessions/{session_id}")
async def api_update_session(
    session_id: str,
    req: UpdateSessionRequest,
    user: UserContext = Depends(get_user_from_header),
):
    """Update session title or metadata."""
    tenant_id, user_id, _ = get_session_context(user)

    updates = {}
    if req.title is not None:
        updates["title"] = req.title
    if req.status is not None:
        updates["status"] = req.status
    if req.metadata is not None:
        updates["metadata"] = req.metadata

    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")

    if USE_PERSISTENT_SESSIONS:
        session = eagle_update_session(session_id, tenant_id, user_id, updates)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return session
    else:
        if session_id not in SESSIONS:
            raise HTTPException(status_code=404, detail="Session not found")
        # In-memory sessions don't have metadata, just acknowledge
        return {"session_id": session_id, **updates}


@app.delete("/api/sessions/{session_id}")
async def api_delete_session(
    session_id: str, user: UserContext = Depends(get_user_from_header)
):
    """Delete a session."""
    tenant_id, user_id, _ = get_session_context(user)

    if USE_PERSISTENT_SESSIONS:
        success = eagle_delete_session(session_id, tenant_id, user_id)
        if not success:
            raise HTTPException(status_code=404, detail="Session not found")
    else:
        if session_id in SESSIONS:
            del SESSIONS[session_id]
        else:
            raise HTTPException(status_code=404, detail="Session not found")

    return {"status": "deleted", "session_id": session_id}


@app.get("/api/sessions/{session_id}/messages")
async def api_get_messages(
    session_id: str, limit: int = 100, user: UserContext = Depends(get_user_from_header)
):
    """Get messages for a session."""
    tenant_id, user_id, _ = get_session_context(user)

    if USE_PERSISTENT_SESSIONS:
        messages = get_messages(session_id, tenant_id, user_id, limit)
    else:
        if session_id not in SESSIONS:
            raise HTTPException(status_code=404, detail="Session not found")
        messages = SESSIONS[session_id][-limit:]

    return {"session_id": session_id, "messages": messages}


@app.get("/api/sessions/{session_id}/context")
async def api_get_session_context(
    session_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Return preloaded context for a session — preferences, package state, feature flags."""
    tenant_id, user_id, _ = get_session_context(user)

    # Resolve active package_id from session metadata
    package_id = None
    if USE_PERSISTENT_SESSIONS:
        session = eagle_get_session(session_id, tenant_id, user_id)
        if session:
            meta = session.get("metadata") or {}
            package_id = meta.get("active_package_id")

    from .session_preloader import preload_session_context

    ctx = await preload_session_context(tenant_id, user_id, package_id=package_id)

    result: dict = {"preferences": ctx.preferences, "feature_flags": ctx.feature_flags}
    if ctx.package:
        result["package"] = {
            "package_id": ctx.package.get("package_id"),
            "title": ctx.package.get("title"),
            "status": ctx.package.get("status"),
            "acquisition_pathway": ctx.package.get("acquisition_pathway"),
            "estimated_value": str(ctx.package.get("estimated_value", "")),
            "checklist": ctx.checklist,
        }
    return result


# ── Document export endpoints ────────────────────────────────────────


class ExportRequest(BaseModel):
    doc_key: Optional[str] = None
    content: Optional[str] = None
    content_b64: Optional[str] = None
    title: str = "Document"
    format: str = "docx"


def _resolve_export_content(req: ExportRequest, tenant_id: str, user_id: str) -> str:
    """Resolve export content from a stored document or inline body payload."""
    from botocore.exceptions import ClientError
    import boto3

    if req.doc_key:
        if not _is_allowed_document_key(req.doc_key, tenant_id, user_id):
            raise HTTPException(status_code=403, detail="Access denied")

        s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-east-1"))
        try:
            response = s3.get_object(Bucket=_S3_BUCKET, Key=req.doc_key)
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "NoSuchKey":
                raise HTTPException(
                    status_code=404, detail="Document not found"
                ) from exc
            logger.error(
                "S3 export fetch error for %s: %s", req.doc_key, exc, exc_info=True
            )
            raise HTTPException(
                status_code=500, detail="Failed to retrieve export source"
            ) from exc

        content_type = response.get("ContentType") or _guess_content_type(req.doc_key)
        if not _is_binary_document(req.doc_key, content_type):
            return response["Body"].read().decode("utf-8", errors="replace")

        raw_bytes = response["Body"].read()
        if _supports_binary_preview(req.doc_key):
            sidecar_content = _load_document_markdown_sidecar(
                s3=s3,
                bucket=_S3_BUCKET,
                doc_key=req.doc_key,
                tenant_id=tenant_id,
                user_id=user_id,
            )
            if sidecar_content is not None:
                return sidecar_content
            preview_payload = _extract_binary_preview_payload(req.doc_key, raw_bytes)
            if preview_payload.get("content"):
                return preview_payload["content"]

        raise HTTPException(
            status_code=400,
            detail="Document content is not available for export. Open a document with previewable text or provide content directly.",
        )

    if req.content is not None:
        return req.content
    if not req.content_b64:
        raise HTTPException(status_code=400, detail="doc_key or content is required")
    try:
        return base64.b64decode(req.content_b64).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=400, detail="Invalid content_b64 payload"
        ) from exc


@app.post("/api/documents/export")
async def api_export_document(
    req: ExportRequest, user: UserContext = Depends(get_user_from_header)
):
    """Export content to DOCX, PDF, or Markdown."""
    try:
        result = export_document(
            _resolve_export_content(req, user.tenant_id, user.user_id),
            req.format,
            req.title,
        )

        return StreamingResponse(
            io.BytesIO(result["data"]),
            media_type=result["content_type"],
            headers={
                "Content-Disposition": f'attachment; filename="{result["filename"]}"',
                "X-File-Size": str(result["size_bytes"]),
            },
        )
    except ExportDependencyError as e:
        logger.error("Export dependency error: %s", e)
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        logger.warning("Export validation error: %s", e)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Export error: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500, detail="Internal server error during export"
        )


@app.get("/api/documents/export/{session_id}")
async def api_export_session(
    session_id: str,
    format: str = "docx",
    user: UserContext = Depends(get_user_from_header),
):
    """Export an entire session conversation."""
    tenant_id, user_id, _ = get_session_context(user)

    if USE_PERSISTENT_SESSIONS:
        messages = get_messages(session_id, tenant_id, user_id)
    else:
        if session_id not in SESSIONS:
            raise HTTPException(status_code=404, detail="Session not found")
        messages = SESSIONS[session_id]

    export_ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    content = f"# EAGLE Session Export\n\n**Session ID:** {session_id}\n**Exported:** {export_ts}\n\n---\n\n"

    for msg in messages:
        role = msg.get("role", "unknown").upper()
        text = msg.get("content", "")
        if isinstance(text, list):
            text = json.dumps(text, indent=2)
        content += f"## {role}\n\n{text}\n\n---\n\n"

    try:
        result = export_document(content, format, f"Session_{session_id}")

        return StreamingResponse(
            io.BytesIO(result["data"]),
            media_type=result["content_type"],
            headers={
                "Content-Disposition": f'attachment; filename="{result["filename"]}"',
            },
        )
    except ExportDependencyError as e:
        logger.error("Session export dependency error: %s", e)
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("Session export error: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500, detail="Internal server error during session export"
        )


# ── S3 Document Browser ──────────────────────────────────────────────

_BINARY_FILE_EXTENSIONS = {"doc", "docx", "pdf", "xls", "xlsx"}
_TEXT_FILE_EXTENSIONS = {"md", "txt", "json", "csv", "html"}


def _get_file_extension(name: str) -> str:
    base = name.rsplit("/", 1)[-1]
    if "." not in base:
        return ""
    return base.rsplit(".", 1)[-1].lower()


def _guess_content_type(name: str) -> str:
    ext = _get_file_extension(name)
    if ext == "md":
        return "text/markdown; charset=utf-8"
    if ext == "txt":
        return "text/plain; charset=utf-8"
    if ext == "docx":
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if ext == "xlsx":
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if ext == "pdf":
        return "application/pdf"
    return "application/octet-stream"


def _is_binary_document(name: str, content_type: Optional[str]) -> bool:
    ext = _get_file_extension(name)
    if ext in _BINARY_FILE_EXTENSIONS:
        return True

    lowered = (content_type or "").lower()
    if lowered.startswith("text/"):
        return False
    if "json" in lowered or "markdown" in lowered or "csv" in lowered:
        return False
    if (
        "officedocument" in lowered
        or lowered == "application/pdf"
        or lowered == "application/msword"
        or lowered == "application/vnd.ms-excel"
    ):
        return True

    return ext not in _TEXT_FILE_EXTENSIONS and bool(ext)


def _supports_binary_preview(name: str) -> bool:
    return _get_file_extension(name) in {"docx", "xlsx"}


def _extract_binary_preview_payload(name: str, raw_bytes: bytes) -> dict[str, Any]:
    ext = _get_file_extension(name)
    if ext == "docx":
        return extract_docx_preview_payload(raw_bytes)
    if ext == "xlsx":
        return extract_xlsx_preview_payload(raw_bytes)
    return {
        "content": None,
        "preview_blocks": [],
        "preview_sheets": [],
        "preview_mode": "none",
    }


_is_allowed_document_key = is_allowed_document_key
_extract_package_document_ref = extract_package_document_ref


def _build_document_response(
    *,
    doc_key: str,
    response: dict,
    content: Optional[str],
    download_url: Optional[str],
    preview_blocks: Optional[List[dict[str, Any]]] = None,
    preview_sheets: Optional[List[dict[str, Any]]] = None,
    preview_mode: Optional[str] = None,
) -> dict[str, Any]:
    content_type = response.get("ContentType") or _guess_content_type(doc_key)
    package_ref = _extract_package_document_ref(doc_key)

    package_id = package_ref["package_id"] if package_ref else None
    doc_type = package_ref["doc_type"] if package_ref else None
    version = package_ref["version"] if package_ref else None
    filename = (package_ref or {}).get("filename") or doc_key.rsplit("/", 1)[-1]
    file_type = _get_file_extension(filename)
    is_binary = _is_binary_document(filename, content_type)

    title = None
    document_id = doc_key
    template_provenance = None
    if package_ref and version is not None:
        metadata = get_document(
            package_ref["tenant_id"],
            package_ref["package_id"],
            package_ref["doc_type"],
            version,
        )
        if metadata:
            title = metadata.get("title")
            document_id = metadata.get("document_id", document_id)
            file_type = metadata.get("file_type", file_type)
            version = metadata.get("version", version)
            template_provenance = metadata.get("template_provenance")
    elif package_ref:
        title = package_ref["doc_type"].replace("_", " ").title()

    return {
        "key": doc_key,
        "s3_key": doc_key,
        "document_id": document_id,
        "content": content,
        "preview_blocks": preview_blocks or [],
        "preview_sheets": preview_sheets or [],
        "preview_mode": preview_mode,
        "content_type": content_type,
        "file_type": file_type,
        "is_binary": is_binary,
        "download_url": download_url,
        "size_bytes": response.get("ContentLength", 0),
        "last_modified": response.get("LastModified").isoformat()
        if response.get("LastModified")
        else None,
        "package_id": package_id,
        "document_type": doc_type,
        "version": version,
        "title": title,
        "template_provenance": template_provenance,
    }


def _get_markdown_sidecar_candidates(doc_key: str) -> list[str]:
    candidates = [get_document_markdown_s3_key(doc_key)]
    if "." in doc_key:
        candidates.append(doc_key.rsplit(".", 1)[0] + ".parsed.md")
    return candidates


def _load_document_markdown_sidecar(
    *,
    s3,
    bucket: str,
    doc_key: str,
    tenant_id: str,
    user_id: str,
) -> Optional[str]:
    from botocore.exceptions import ClientError

    package_ref = _extract_package_document_ref(doc_key)
    metadata = None
    if package_ref and package_ref.get("version") is not None:
        metadata = get_document(
            package_ref["tenant_id"],
            package_ref["package_id"],
            package_ref["doc_type"],
            package_ref["version"],
        )

    candidates: list[str] = []
    markdown_s3_key = (metadata or {}).get("markdown_s3_key")
    if markdown_s3_key:
        candidates.append(markdown_s3_key)
    candidates.extend(_get_markdown_sidecar_candidates(doc_key))

    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        if not _is_allowed_document_key(candidate, tenant_id, user_id):
            continue
        try:
            sidecar_resp = s3.get_object(Bucket=bucket, Key=candidate)
            return sidecar_resp["Body"].read().decode("utf-8", errors="replace")
        except ClientError:
            continue
    return None


@app.get("/api/documents")
async def api_list_documents(user: UserContext = Depends(get_user_from_header)):
    """List documents in S3 for the current user."""
    import boto3
    from botocore.exceptions import ClientError

    tenant_id = user.tenant_id
    user_id = user.user_id
    bucket = _S3_BUCKET
    prefix = f"eagle/{tenant_id}/{user_id}/"

    try:
        s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-east-1"))
        response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=100)

        documents = []
        for obj in response.get("Contents", []):
            key = obj["Key"]
            name = key.split("/")[-1]
            if not name:
                continue
            documents.append(
                {
                    "key": key,
                    "name": name,
                    "size_bytes": obj["Size"],
                    "last_modified": obj["LastModified"].isoformat(),
                    "type": _get_doc_type(name),
                }
            )

        return {"documents": documents, "bucket": bucket, "prefix": prefix}
    except ClientError as e:
        logger.error("S3 list error: %s", e, exc_info=True)
        return {"documents": [], "error": "Failed to list documents"}


@app.get("/api/documents/{doc_key:path}")
async def api_get_document(
    doc_key: str,
    request: Request,
    user: UserContext = Depends(get_user_from_header),
):
    """Get document content from S3."""
    import boto3
    from botocore.exceptions import ClientError

    tenant_id = user.tenant_id
    user_id = user.user_id
    bucket = _S3_BUCKET

    include_content = request.query_params.get("content") != "false"
    # Security: allow either workspace documents or canonical tenant package docs.
    if not _is_allowed_document_key(doc_key, tenant_id, user_id):
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-east-1"))
        response = s3.get_object(Bucket=bucket, Key=doc_key)
        content_type = response.get("ContentType") or _guess_content_type(doc_key)
        is_binary = _is_binary_document(doc_key, content_type)
        content = None
        download_url = None
        preview_blocks = None
        preview_sheets = None
        preview_mode = None

        if not is_binary and include_content:
            content = response["Body"].read().decode("utf-8", errors="replace")
        else:
            if include_content and _supports_binary_preview(doc_key):
                raw_bytes = response["Body"].read()
                # Prefer the saved markdown sidecar over binary extraction so
                # preview and exports reflect the same stored document content.
                sidecar_content = _load_document_markdown_sidecar(
                    s3=s3,
                    bucket=bucket,
                    doc_key=doc_key,
                    tenant_id=tenant_id,
                    user_id=user_id,
                )
                if sidecar_content is not None:
                    content = sidecar_content
                    preview_mode = "markdown_sidecar"
                else:
                    preview_payload = _extract_binary_preview_payload(
                        doc_key, raw_bytes
                    )
                    content = preview_payload.get("content")
                    preview_blocks = preview_payload.get("preview_blocks", [])
                    preview_sheets = preview_payload.get("preview_sheets", [])
                    preview_mode = preview_payload.get("preview_mode")
            download_url = s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": doc_key},
                ExpiresIn=3600,
            )

        return _build_document_response(
            doc_key=doc_key,
            response=response,
            content=content,
            download_url=download_url,
            preview_blocks=preview_blocks,
            preview_sheets=preview_sheets,
            preview_mode=preview_mode,
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchKey":
            raise HTTPException(status_code=404, detail="Document not found")
        logger.error("S3 get document error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve document")


# ── Document Update (PUT) ────────────────────────────────────────────


class DocumentUpdateRequest(BaseModel):
    """Request body for updating document content."""

    content: str
    change_source: str = "user_edit"  # "user_edit" | "ai_edit"


class DocxPreviewEditRequest(BaseModel):
    """Request body for structured DOCX preview edits."""

    preview_blocks: List[Dict[str, Any]]
    preview_mode: str
    change_source: str = "user_edit"


class XlsxPreviewEditRequest(BaseModel):
    """Request body for structured XLSX preview edits."""

    cell_edits: List[Dict[str, Any]]
    change_source: str = "user_edit"


@app.put("/api/documents/{doc_key:path}")
async def api_update_document(
    doc_key: str,
    request: DocumentUpdateRequest,
    user: UserContext = Depends(get_user_from_header),
):
    """Update document content in S3.

    For package documents (eagle/{tenant}/packages/...), creates a new version.
    For workspace documents, performs a direct overwrite.
    """
    import boto3
    from botocore.exceptions import ClientError

    tenant_id = user.tenant_id
    user_id = user.user_id
    bucket = _S3_BUCKET

    # Security: allow either workspace documents or canonical tenant package docs.
    if not _is_allowed_document_key(doc_key, tenant_id, user_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Detect if this is a package document by checking the key pattern
    # Package docs: eagle/{tenant}/{user}/packages/{package_id}/...
    is_package_doc = "/packages/" in doc_key
    file_type = _get_file_extension(doc_key)

    if _is_binary_document(doc_key, _guess_content_type(doc_key)):
        raise HTTPException(
            status_code=415,
            detail="Binary Office documents cannot be saved through the plain text editor. Use the DOCX AI edit flow or download the original file.",
        )

    if is_package_doc:
        # Route through document_service for versioning
        from app.document_service import create_package_document_version

        package_ref = _extract_package_document_ref(doc_key)
        if not package_ref:
            raise HTTPException(
                status_code=400, detail="Invalid package document key format"
            )

        package_id = package_ref["package_id"]
        doc_type = package_ref["doc_type"]
        title = doc_type.replace("_", " ").title()
        version = package_ref.get("version")
        if version is not None:
            current = get_document(tenant_id, package_id, doc_type, version)
            if current and current.get("title"):
                title = current["title"]

        result = create_package_document_version(
            tenant_id=tenant_id,
            package_id=package_id,
            doc_type=doc_type,
            content=request.content,
            title=title,
            file_type=file_type or "md",
            created_by_user_id=user_id,
            change_source=request.change_source,
        )

        if not result.success:
            raise HTTPException(
                status_code=500,
                detail=result.error or "Failed to create document version",
            )

        return {
            "success": True,
            "key": result.s3_key,
            "version": result.version,
            "document_id": result.document_id,
            "message": f"Document updated (version {result.version})",
        }
    else:
        # Workspace document: direct S3 overwrite
        try:
            s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-east-1"))
            s3.put_object(
                Bucket=bucket,
                Key=doc_key,
                Body=request.content.encode("utf-8"),
                ContentType=_guess_content_type(doc_key),
            )

            # Write changelog entry for workspace document
            from app.changelog_store import write_document_changelog_entry

            try:
                write_document_changelog_entry(
                    tenant_id=tenant_id,
                    document_key=doc_key,
                    change_type="update",
                    change_source=request.change_source,
                    change_summary="Updated document via editor",
                    actor_user_id=user_id,
                )
            except Exception as cl_err:
                logger.warning(
                    "Failed to write changelog for workspace doc: %s", cl_err
                )

            return {
                "success": True,
                "key": doc_key,
                "message": "Document saved",
            }
        except ClientError as e:
            logger.error("S3 put document error: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to save document")


@app.post("/api/documents/docx-edit/{doc_key:path}")
async def api_update_docx_preview_document(
    doc_key: str,
    request: DocxPreviewEditRequest,
    user: UserContext = Depends(get_user_from_header),
):
    """Update a DOCX document through structured preview blocks."""
    result = save_docx_preview_edits(
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        doc_key=doc_key,
        preview_blocks=request.preview_blocks,
        preview_mode=request.preview_mode,
        change_source=request.change_source,
    )
    error = _get_result_error(result)
    if error:
        logger.warning("DOCX preview edit failed: %s", error)
        raise HTTPException(status_code=400, detail=GENERIC_EDIT_ERROR)
    return {
        "success": True,
        "mode": result.get("mode"),
        "document_id": result.get("document_id"),
        "key": result.get("key"),
        "version": result.get("version"),
        "file_type": result.get("file_type"),
        "content": result.get("content"),
        "preview_blocks": result.get("preview_blocks", []),
        "preview_mode": result.get("preview_mode"),
        "message": result.get("message"),
    }


@app.post("/api/documents/xlsx-edit/{doc_key:path}")
async def api_update_xlsx_preview_document(
    doc_key: str,
    request: XlsxPreviewEditRequest,
    user: UserContext = Depends(get_user_from_header),
):
    """Update an XLSX document through structured cell edits."""
    result = save_xlsx_preview_edits(
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        doc_key=doc_key,
        cell_edits=request.cell_edits,
        change_source=request.change_source,
    )
    error = _get_result_error(result)
    if error:
        logger.warning("XLSX preview edit failed: %s", error)
        raise HTTPException(status_code=400, detail=GENERIC_EDIT_ERROR)
    return {
        "success": True,
        "mode": result.get("mode"),
        "document_id": result.get("document_id"),
        "key": result.get("key"),
        "version": result.get("version"),
        "file_type": result.get("file_type"),
        "content": result.get("content"),
        "preview_mode": result.get("preview_mode"),
        "preview_sheets": result.get("preview_sheets", []),
        "missing": result.get("missing", []),
        "message": result.get("message"),
    }


# ── S3 Presigned URL ─────────────────────────────────────────────────


@app.get("/api/documents/presign")
async def api_presign_document(
    key: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Generate a time-limited presigned URL for an S3 document."""
    import boto3
    from botocore.exceptions import ClientError

    tenant_id = user.tenant_id
    user_id = user.user_id

    # Security: ensure key is within user's prefix
    if not key.startswith(f"eagle/{tenant_id}/{user_id}/"):
        raise HTTPException(status_code=403, detail="Access denied")

    bucket = _S3_BUCKET
    try:
        s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-east-1"))
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=3600,  # 1 hour
        )
        return {"url": url, "key": key, "expires_in": 3600}
    except ClientError as e:
        logger.error("Presign error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ── User document upload ─────────────────────────────────────────────

ALLOWED_UPLOAD_MIME_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # .xlsx
    "application/vnd.ms-excel",  # .xls
    "text/plain",
    "text/markdown",
}
_MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB


# DynamoDB-backed upload tracking (1-hour TTL auto-deletes stale entries)
def _coerce_dynamodb_value(value: Any) -> Any:
    """Convert floats in nested upload metadata to Decimal for DynamoDB."""
    from decimal import Decimal

    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, list):
        return [_coerce_dynamodb_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _coerce_dynamodb_value(item) for key, item in value.items()}
    return value


def _put_upload(tenant_id: str, upload_id: str, metadata: Dict[str, Any]) -> None:
    """Store upload metadata in DynamoDB with 24-hour TTL."""
    import boto3

    table = boto3.resource(
        "dynamodb", region_name=os.getenv("AWS_REGION", "us-east-1")
    ).Table(os.getenv("EAGLE_SESSIONS_TABLE", "eagle"))
    item = {
        "PK": f"UPLOAD#{tenant_id}",
        "SK": f"UPLOAD#{upload_id}",
        "ttl": int(time.time()) + 86400,
        **_coerce_dynamodb_value(metadata),
    }
    table.put_item(Item=item)


def _get_upload(tenant_id: str, upload_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve upload metadata from DynamoDB. Returns None if expired/missing."""
    import boto3

    table = boto3.resource(
        "dynamodb", region_name=os.getenv("AWS_REGION", "us-east-1")
    ).Table(os.getenv("EAGLE_SESSIONS_TABLE", "eagle"))
    resp = table.get_item(
        Key={"PK": f"UPLOAD#{tenant_id}", "SK": f"UPLOAD#{upload_id}"}
    )
    return resp.get("Item")


def _delete_upload(tenant_id: str, upload_id: str) -> None:
    """Remove upload metadata from DynamoDB."""
    import boto3

    table = boto3.resource(
        "dynamodb", region_name=os.getenv("AWS_REGION", "us-east-1")
    ).Table(os.getenv("EAGLE_SESSIONS_TABLE", "eagle"))
    table.delete_item(Key={"PK": f"UPLOAD#{tenant_id}", "SK": f"UPLOAD#{upload_id}"})


@app.post("/api/documents/upload")
async def api_upload_document(
    file: UploadFile = File(...),
    session_id: Optional[str] = None,
    package_id: Optional[str] = None,
    user: UserContext = Depends(get_user_from_header),
):
    """Upload a document to the user's S3 workspace with automatic classification.

    Returns upload metadata including classification result for package assignment flow.
    """
    import boto3
    from botocore.exceptions import ClientError
    import re

    # Validate content type
    content_type = file.content_type or "application/octet-stream"
    if content_type not in ALLOWED_UPLOAD_MIME_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {content_type}. Accepted: PDF, Word, plain text, Markdown.",
        )

    body = await file.read()
    if len(body) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 25 MB limit.")

    tenant_id = user.tenant_id
    user_id = user.user_id
    bucket = _S3_BUCKET

    # Generate upload_id for tracking
    upload_id = str(uuid.uuid4())

    # Sanitize filename
    safe_name = re.sub(r"[^A-Za-z0-9._\-]", "_", file.filename or "upload")
    key = f"eagle/{tenant_id}/{user_id}/uploads/{upload_id}/{safe_name}"

    try:
        s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-east-1"))
        s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType=content_type)
    except ClientError as e:
        logger.error("S3 upload error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to upload document")

    # Extract text preview for classification
    content_preview = extract_text_preview(body, content_type)

    # Classify document
    classification = classify_document(file.filename or safe_name, content_preview)

    # Convert to markdown for persistence
    from .document_markdown_service import convert_to_markdown

    markdown_content = convert_to_markdown(
        body, content_type, file.filename or safe_name
    )

    # Auto-standardize markdown via Bedrock AI
    quality_score = None
    if markdown_content and classification.doc_type not in ("unknown", None):
        try:
            from .template_standardizer import standardize_template as _standardize

            std_result = _standardize(
                body,
                file.filename or safe_name,
                content_type,
                classification.doc_type,
            )
            if std_result.success and std_result.quality_score > 50:
                markdown_content = std_result.markdown
            quality_score = std_result.quality_score
        except Exception as e:
            logger.warning("Auto-standardize failed for %s: %s", safe_name, e)

    # Upload markdown sibling to S3 if conversion succeeded
    markdown_s3_key = None
    if markdown_content:
        md_key = f"{key}.parsed.md"
        try:
            s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-east-1"))
            s3.put_object(
                Bucket=bucket,
                Key=md_key,
                Body=markdown_content.encode("utf-8"),
                ContentType="text/markdown",
            )
            markdown_s3_key = md_key
        except ClientError as e:
            logger.warning("Failed to upload markdown sibling: %s", e)

    # Determine package context
    package_context = {"mode": "workspace", "package_id": None}
    if package_id:
        pkg = get_package(tenant_id, package_id)
        if pkg:
            package_context = {"mode": "package", "package_id": package_id}

    # Store upload metadata for later assignment
    _put_upload(
        tenant_id,
        upload_id,
        {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "s3_bucket": bucket,
            "s3_key": key,
            "filename": safe_name,
            "original_filename": file.filename,
            "content_type": content_type,
            "size_bytes": len(body),
            "classification": classification.to_dict(),
            "session_id": session_id,
            "markdown_s3_key": markdown_s3_key,
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        },
    )

    logger.info(
        "Uploaded %s → s3://%s/%s (upload_id=%s, classified=%s)",
        safe_name,
        bucket,
        key,
        upload_id,
        classification.doc_type,
    )

    return {
        "key": key,
        "upload_id": upload_id,
        "filename": safe_name,
        "size_bytes": len(body),
        "content_type": content_type,
        "classification": classification.to_dict(),
        "package_context": package_context,
        "quality_score": quality_score,
    }


class AssignToPackageRequest(BaseModel):
    """Request body for assigning an uploaded document to a package."""

    package_id: str
    doc_type: Optional[str] = None
    title: Optional[str] = None


@app.post("/api/documents/{upload_id}/assign-to-package")
async def assign_upload_to_package(
    upload_id: str,
    body: AssignToPackageRequest,
    user: UserContext = Depends(get_user_from_header),
):
    """Assign an uploaded document to an acquisition package.

    Creates a versioned package document from the uploaded file.
    """
    import boto3
    from botocore.exceptions import ClientError

    # Retrieve upload metadata
    upload_meta = _get_upload(user.tenant_id, upload_id)
    if not upload_meta:
        raise HTTPException(status_code=404, detail="Upload not found or expired")

    # Verify ownership
    if (
        upload_meta["tenant_id"] != user.tenant_id
        or upload_meta["user_id"] != user.user_id
    ):
        raise HTTPException(status_code=403, detail="Access denied")

    # Verify package exists
    pkg = get_package(user.tenant_id, body.package_id)
    if not pkg:
        raise HTTPException(
            status_code=404, detail=f"Package {body.package_id} not found"
        )

    # Determine doc_type (from request or classification) and normalize
    raw_doc_type = body.doc_type or upload_meta["classification"].get(
        "doc_type", "unknown"
    )
    doc_type = (
        normalize_doc_type(raw_doc_type) if raw_doc_type != "unknown" else "unknown"
    )
    if doc_type == "unknown" or doc_type == "":
        raise HTTPException(
            status_code=400,
            detail="Document type could not be determined. Please specify doc_type.",
        )

    # Determine title
    title = (
        body.title
        or upload_meta["classification"].get("suggested_title")
        or upload_meta["filename"]
    )

    # Fetch file content from S3
    try:
        s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-east-1"))
        response = s3.get_object(
            Bucket=upload_meta["s3_bucket"], Key=upload_meta["s3_key"]
        )
        content = response["Body"].read()
    except ClientError as e:
        logger.error("S3 fetch error for upload %s: %s", upload_id, e)
        raise HTTPException(status_code=500, detail="Failed to retrieve uploaded file")

    # Fetch markdown content if available
    markdown_content = None
    markdown_s3_key = upload_meta.get("markdown_s3_key")
    if markdown_s3_key:
        try:
            md_response = s3.get_object(
                Bucket=upload_meta["s3_bucket"], Key=markdown_s3_key
            )
            markdown_content = (
                md_response["Body"].read().decode("utf-8", errors="replace")
            )
        except ClientError:
            logger.debug("Could not fetch markdown sibling for upload %s", upload_id)

    # Compute auto-tags from template metadata
    from .tag_computation import (
        compute_document_tags,
        compute_far_tags_from_template,
        compute_completeness_pct,
    )

    doc_stub = {"doc_type": doc_type, "title": title}
    system_tags = compute_document_tags(doc_stub, pkg)
    far_tags = compute_far_tags_from_template(doc_type)
    completeness_pct = None
    if markdown_content:
        completeness_pct = compute_completeness_pct(doc_type, markdown_content)

    # Determine file type from content_type
    content_type = upload_meta["content_type"]
    file_type = "md"  # default
    if "pdf" in content_type:
        file_type = "pdf"
    elif "wordprocessingml" in content_type or "msword" in content_type:
        file_type = "docx"
    elif "spreadsheet" in content_type or "excel" in content_type:
        file_type = "xlsx"

    # Create versioned package document
    result = create_package_document_version(
        tenant_id=user.tenant_id,
        package_id=body.package_id,
        doc_type=doc_type,
        content=content,
        title=title,
        file_type=file_type,
        created_by_user_id=user.user_id,
        session_id=upload_meta.get("session_id"),
        change_source="user_upload",
        markdown_content=markdown_content,
        system_tags=system_tags,
        far_tags=far_tags,
        completeness_pct=completeness_pct,
        original_filename=upload_meta.get("original_filename"),
    )

    if not result.success:
        raise HTTPException(
            status_code=500, detail=result.error or "Failed to create document"
        )

    # Clean up upload registry
    _delete_upload(user.tenant_id, upload_id)

    logger.info(
        "Assigned upload %s to package %s as %s v%s",
        upload_id,
        body.package_id,
        doc_type,
        result.version,
    )

    return result.to_dict()


# ── Admin KB review endpoints ─────────────────────────────────────────


def _get_dynamo():
    import boto3

    return boto3.resource("dynamodb", region_name=os.getenv("AWS_REGION", "us-east-1"))


@app.get("/api/admin/kb-reviews")
async def api_list_kb_reviews(
    status: Optional[str] = "pending",
    user: UserContext = Depends(get_user_from_header),
):
    """List KB review records from DynamoDB (admin only)."""
    from boto3.dynamodb.conditions import Attr

    table_name = os.getenv("METADATA_TABLE", "eagle-document-metadata-dev")
    try:
        ddb = _get_dynamo()
        table = ddb.Table(table_name)
        resp = table.scan(
            FilterExpression=Attr("PK").begins_with("KB_REVIEW#")
            & Attr("status").eq(status),
        )
        reviews = resp.get("Items", [])
        reviews.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return {"reviews": reviews, "count": len(reviews)}
    except Exception as e:
        logger.error("KB review list error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to list KB reviews")


@app.post("/api/admin/kb-review/{review_id}/approve")
async def api_approve_kb_review(
    review_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Approve a KB review: apply diff to matrix.json, update HTML, move doc to approved/."""
    import boto3
    import json as _json
    from botocore.exceptions import ClientError

    table_name = os.getenv("METADATA_TABLE", "eagle-document-metadata-dev")
    bucket = _S3_BUCKET
    ddb = _get_dynamo()
    table = ddb.Table(table_name)
    s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-east-1"))

    # Fetch the review record
    pk = f"KB_REVIEW#{review_id}"
    try:
        item = table.get_item(Key={"PK": pk, "SK": "META"}).get("Item")
    except Exception as e:
        logger.error("KB review fetch error (approve): %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch KB review")

    if not item:
        raise HTTPException(status_code=404, detail="KB review not found")
    if item.get("status") != "pending":
        raise HTTPException(status_code=409, detail="Review already processed")

    proposed_diff = item.get("proposed_diff", [])

    # Apply diff to matrix.json (file on disk relative to this server)
    matrix_path = (
        _Path(__file__).resolve().parent.parent.parent.parent
        / "eagle-plugin"
        / "data"
        / "matrix.json"
    )
    if matrix_path.exists():
        try:
            matrix = _json.loads(matrix_path.read_text(encoding="utf-8"))
            matrix = _apply_json_patch(matrix, proposed_diff)
            matrix["version"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            matrix_path.write_text(
                _json.dumps(matrix, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            logger.info("matrix.json updated after KB review %s", review_id)

            # Regenerate HTML THRESHOLDS/TYPES arrays
            _regenerate_html_arrays(matrix)
        except Exception as e:
            logger.warning("matrix.json patch failed (non-fatal): %s", e)
    else:
        logger.warning("matrix.json not found at %s — skipping patch", matrix_path)

    # Move S3 doc from pending/ to approved/
    old_key = item.get("s3_key", "")
    if old_key and old_key.startswith("eagle-knowledge-base/pending/"):
        new_key = old_key.replace(
            "eagle-knowledge-base/pending/", "eagle-knowledge-base/approved/"
        )
        try:
            s3.copy_object(
                Bucket=bucket,
                CopySource={"Bucket": bucket, "Key": old_key},
                Key=new_key,
            )
            s3.delete_object(Bucket=bucket, Key=old_key)
        except ClientError as e:
            logger.warning("S3 move failed: %s", e)

    # Update DynamoDB record
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    table.update_item(
        Key={"PK": pk, "SK": "META"},
        UpdateExpression="SET #st = :s, reviewed_by = :u, reviewed_at = :t",
        ExpressionAttributeNames={"#st": "status"},
        ExpressionAttributeValues={":s": "approved", ":u": user.user_id, ":t": now},
    )
    return {"status": "approved", "review_id": review_id, "reviewed_at": now}


@app.post("/api/admin/kb-review/{review_id}/reject")
async def api_reject_kb_review(
    review_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Reject a KB review: mark rejected, move doc to rejected/."""
    import boto3
    from botocore.exceptions import ClientError

    table_name = os.getenv("METADATA_TABLE", "eagle-document-metadata-dev")
    bucket = _S3_BUCKET
    ddb = _get_dynamo()
    table = ddb.Table(table_name)
    s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-east-1"))

    pk = f"KB_REVIEW#{review_id}"
    try:
        item = table.get_item(Key={"PK": pk, "SK": "META"}).get("Item")
    except Exception as e:
        logger.error("KB review fetch error (reject): %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch KB review")

    if not item:
        raise HTTPException(status_code=404, detail="KB review not found")
    if item.get("status") != "pending":
        raise HTTPException(status_code=409, detail="Review already processed")

    # Move S3 doc from pending/ to rejected/
    old_key = item.get("s3_key", "")
    if old_key and old_key.startswith("eagle-knowledge-base/pending/"):
        new_key = old_key.replace(
            "eagle-knowledge-base/pending/", "eagle-knowledge-base/rejected/"
        )
        try:
            s3.copy_object(
                Bucket=bucket,
                CopySource={"Bucket": bucket, "Key": old_key},
                Key=new_key,
            )
            s3.delete_object(Bucket=bucket, Key=old_key)
        except ClientError as e:
            logger.warning("S3 move failed: %s", e)

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    table.update_item(
        Key={"PK": pk, "SK": "META"},
        UpdateExpression="SET #st = :s, reviewed_by = :u, reviewed_at = :t",
        ExpressionAttributeNames={"#st": "status"},
        ExpressionAttributeValues={":s": "rejected", ":u": user.user_id, ":t": now},
    )
    return {"status": "rejected", "review_id": review_id, "reviewed_at": now}


# ── Knowledge Base browse endpoints ──────────────────────────────────


@app.get("/api/knowledge-base")
async def api_list_knowledge_base(
    topic: Optional[str] = None,
    document_type: Optional[str] = None,
    agent: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = 50,
    user: UserContext = Depends(get_user_from_header),
):
    """List/search knowledge base documents from the metadata table."""
    from boto3.dynamodb.conditions import Attr

    # If free-text query provided, delegate to the existing search tool
    if query:
        from .tools.knowledge_tools import exec_knowledge_search

        result = exec_knowledge_search(
            {
                "query": query,
                "topic": topic,
                "document_type": document_type,
                "agent": agent,
                "limit": limit,
            },
            tenant_id=user.tenant_id,
        )
        return {"documents": result.get("results", []), "count": result.get("count", 0)}

    table_name = os.getenv("METADATA_TABLE", "eagle-document-metadata-dev")
    try:
        ddb = _get_dynamo()
        table = ddb.Table(table_name)

        # Use GSI when a single filter is provided, otherwise scan
        scan_kwargs: dict = {}
        filter_expr = Attr("PK").not_exists()  # Exclude KB_REVIEW# records

        if topic:
            filter_expr = filter_expr & Attr("primary_topic").eq(topic)
        if document_type:
            filter_expr = filter_expr & Attr("document_type").eq(document_type)
        if agent:
            filter_expr = filter_expr & Attr("primary_agent").eq(agent)

        scan_kwargs["FilterExpression"] = filter_expr

        items: list = []
        resp = table.scan(**scan_kwargs)
        items.extend(resp.get("Items", []))
        while "LastEvaluatedKey" in resp:
            scan_kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
            resp = table.scan(**scan_kwargs)
            items.extend(resp.get("Items", []))

        # Sort by last_updated descending
        items.sort(key=lambda x: x.get("last_updated", ""), reverse=True)
        items = items[:limit]

        documents = []
        for item in items:
            documents.append(
                {
                    "document_id": item.get("document_id", ""),
                    "title": item.get("title", ""),
                    "summary": item.get("summary", ""),
                    "document_type": item.get("document_type", ""),
                    "primary_topic": item.get("primary_topic", ""),
                    "primary_agent": item.get("primary_agent", ""),
                    "authority_level": item.get("authority_level", ""),
                    "keywords": item.get("keywords", [])[:10],
                    "s3_key": item.get("s3_key", ""),
                    "confidence_score": float(item.get("confidence_score", 0)),
                    "word_count": int(item.get("word_count", 0)),
                    "page_count": int(item.get("page_count", 0)),
                    "file_type": item.get("file_type", ""),
                    "last_updated": item.get("last_updated", ""),
                }
            )

        return {"documents": documents, "count": len(documents)}
    except Exception as e:
        logger.error("Knowledge base list error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to list knowledge base")


@app.get("/api/knowledge-base/stats")
async def api_knowledge_base_stats(
    user: UserContext = Depends(get_user_from_header),
):
    """Aggregate knowledge base stats by topic, type, and agent."""
    from boto3.dynamodb.conditions import Attr

    table_name = os.getenv("METADATA_TABLE", "eagle-document-metadata-dev")
    try:
        ddb = _get_dynamo()
        table = ddb.Table(table_name)

        items: list = []
        resp = table.scan(FilterExpression=Attr("PK").not_exists())
        items.extend(resp.get("Items", []))
        while "LastEvaluatedKey" in resp:
            resp = table.scan(
                FilterExpression=Attr("PK").not_exists(),
                ExclusiveStartKey=resp["LastEvaluatedKey"],
            )
            items.extend(resp.get("Items", []))

        by_topic: dict[str, int] = {}
        by_type: dict[str, int] = {}
        by_agent: dict[str, int] = {}
        for item in items:
            t = item.get("primary_topic", "unknown")
            by_topic[t] = by_topic.get(t, 0) + 1
            dt = item.get("document_type", "unknown")
            by_type[dt] = by_type.get(dt, 0) + 1
            a = item.get("primary_agent", "unknown")
            by_agent[a] = by_agent.get(a, 0) + 1

        return {
            "total": len(items),
            "by_topic": dict(
                sorted(by_topic.items(), key=lambda x: x[1], reverse=True)
            ),
            "by_type": dict(sorted(by_type.items(), key=lambda x: x[1], reverse=True)),
            "by_agent": dict(
                sorted(by_agent.items(), key=lambda x: x[1], reverse=True)
            ),
        }
    except Exception as e:
        logger.error("Knowledge base stats error: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500, detail="Failed to get knowledge base stats"
        )


@app.get("/api/knowledge-base/document/{s3_key:path}")
async def api_kb_document(
    s3_key: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Fetch full document content from S3."""
    from .tools.knowledge_tools import exec_knowledge_fetch

    result = exec_knowledge_fetch({"s3_key": s3_key}, tenant_id=user.tenant_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


_PLUGIN_DATA_FILES = {
    "far-database.json": "FAR/DFARS/HHSAR clause database (~900+ clauses)",
    "matrix.json": "Acquisition decision matrix — thresholds and contract types",
    "thresholds.json": "Fiscal year regulatory thresholds (SAT, MPT, JOFOC)",
    "contract-vehicles.json": "Pre-approved contract vehicles (GSA, NITAAC, etc.)",
}


@app.get("/api/knowledge-base/plugin-data")
async def api_kb_plugin_data(
    file: Optional[str] = None,
    user: UserContext = Depends(get_user_from_header),
):
    """List or fetch static plugin reference data files."""
    import json as _json

    data_dir = _Path(__file__).resolve().parent.parent.parent / "eagle-plugin" / "data"

    if file is None:
        # List all files with metadata
        files = []
        for name, description in _PLUGIN_DATA_FILES.items():
            fpath = data_dir / name
            if fpath.exists():
                content = _json.loads(fpath.read_text(encoding="utf-8"))
                item_count = (
                    len(content) if isinstance(content, list) else len(content.keys())
                )
                files.append(
                    {
                        "name": name,
                        "description": description,
                        "size_bytes": fpath.stat().st_size,
                        "item_count": item_count,
                    }
                )
        return {"files": files}

    # Validate filename to prevent path traversal
    if file not in _PLUGIN_DATA_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file. Allowed: {list(_PLUGIN_DATA_FILES.keys())}",
        )

    fpath = data_dir / file
    if not fpath.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {file}")

    content = _json.loads(fpath.read_text(encoding="utf-8"))
    item_count = len(content) if isinstance(content, list) else len(content.keys())
    return {"name": file, "content": content, "item_count": item_count}


def _apply_json_patch(obj: dict, patch: list) -> dict:
    """Apply a simplified JSON Patch (RFC 6902) to a dict. Supports replace, add, remove."""
    import copy

    result = copy.deepcopy(obj)
    for op in patch:
        operation = op.get("op")
        path = op.get("path", "")
        parts = [p for p in path.split("/") if p]
        try:
            if operation == "replace":
                target = result
                for part in parts[:-1]:
                    target = (
                        target[int(part)] if isinstance(target, list) else target[part]
                    )
                last = parts[-1]
                if isinstance(target, list):
                    target[int(last)] = op["value"]
                else:
                    target[last] = op["value"]
            elif operation == "add":
                target = result
                for part in parts[:-1]:
                    target = (
                        target[int(part)] if isinstance(target, list) else target[part]
                    )
                last = parts[-1]
                if isinstance(target, list):
                    target.append(op["value"])
                else:
                    target[last] = op["value"]
            elif operation == "remove":
                target = result
                for part in parts[:-1]:
                    target = (
                        target[int(part)] if isinstance(target, list) else target[part]
                    )
                last = parts[-1]
                if isinstance(target, list):
                    del target[int(last)]
                else:
                    del target[last]
        except (KeyError, IndexError, TypeError) as e:
            logger.warning("JSON patch op failed (%s %s): %s", operation, path, e)
    return result


def _regenerate_html_arrays(matrix: dict) -> None:
    """Replace THRESHOLDS and TYPES JS arrays in contract-requirements-matrix.html."""
    import json as _json
    import re as _re

    html_path = (
        _Path(__file__).resolve().parent.parent.parent.parent
        / "contract-requirements-matrix.html"
    )
    if not html_path.exists():
        logger.warning(
            "contract-requirements-matrix.html not found, skipping HTML regeneration"
        )
        return

    html = html_path.read_text(encoding="utf-8")

    # Build new THRESHOLDS array from matrix
    thresholds_js = "const THRESHOLDS = [\n"
    for t in matrix.get("thresholds", []):
        thresholds_js += (
            f"  {{ value: {t['value']:<12} label: {_json.dumps(t['label'])}, "
            f"short: {_json.dumps(t['short'])} }},\n"
        )
    thresholds_js += "];"

    # Build new TYPES array from contract_types
    types_js = "const TYPES = [\n"
    for ct in matrix.get("contract_types", []):
        parts = [
            f"id: {_json.dumps(ct['id'])}",
            f"label: {_json.dumps(ct['label'])}",
            f"risk: {ct['risk']}",
            f"category: {_json.dumps(ct['category'])}",
        ]
        if ct.get("fee_cap"):
            parts.append(f"feeCap: {_json.dumps(ct['fee_cap'])}")
        if ct.get("prereqs"):
            parts.append(f"prereqs: {_json.dumps(ct['prereqs'])}")
        types_js += "  { " + ", ".join(parts) + " },\n"
    types_js += "];"

    # Replace blocks using regex
    html = _re.sub(
        r"const THRESHOLDS\s*=\s*\[[\s\S]*?\];",
        thresholds_js,
        html,
    )
    html = _re.sub(
        r"const TYPES\s*=\s*\[[\s\S]*?\];",
        types_js,
        html,
    )
    html_path.write_text(html, encoding="utf-8")
    logger.info("Regenerated THRESHOLDS/TYPES in contract-requirements-matrix.html")


def _get_doc_type(name: str) -> str:
    """Infer document type from filename."""
    name_lower = name.lower()
    # Content-based matching first (order: specific before general)
    if "igce" in name_lower or "ige" in name_lower:
        return "igce"
    elif (
        "sow" in name_lower
        or "statement-of-work" in name_lower
        or "statement_of_work" in name_lower
    ):
        return "sow"
    elif "son" in name_lower and (
        "product" in name_lower or "service" in name_lower or "need" in name_lower
    ):
        return "son_products" if "product" in name_lower else "son_services"
    elif "market" in name_lower and "research" in name_lower:
        return "market_research"
    elif (
        "justification" in name_lower or "j&a" in name_lower or "j_and_a" in name_lower
    ):
        return "justification"
    elif "acquisition" in name_lower and "plan" in name_lower:
        return "acquisition_plan"
    elif "cor" in name_lower and (
        "appointment" in name_lower
        or "designation" in name_lower
        or "certification" in name_lower
    ):
        return "cor_certification"
    elif "buy" in name_lower and "american" in name_lower:
        return "buy_american"
    elif "subk" in name_lower or "subcontract" in name_lower:
        return "subk_plan"
    elif "conference" in name_lower:
        return "conference_request"
    # Extension-based fallback
    elif name_lower.endswith(".md"):
        return "markdown"
    elif name_lower.endswith(".pdf"):
        return "pdf"
    elif name_lower.endswith(".docx"):
        return "docx"
    elif name_lower.endswith(".xlsx"):
        return "xlsx"
    elif name_lower.endswith(".txt"):
        return "txt"
    else:
        return "document"


# ── EAGLE Admin & Analytics endpoints ────────────────────────────────


@app.get("/api/admin/dashboard")
async def api_admin_dashboard(
    days: int = 30, user: UserContext = Depends(get_user_from_header)
):
    """Get admin dashboard statistics."""
    tenant_id = user.tenant_id
    result = get_dashboard_stats(tenant_id, days)
    error = _get_result_error(result)
    return _sanitize_result_error(result, GENERIC_ANALYTICS_ERROR) if error else result


@app.get("/api/admin/users")
async def api_admin_users(
    days: int = 30, limit: int = 10, user: UserContext = Depends(get_user_from_header)
):
    """Get top users by usage."""
    tenant_id = user.tenant_id
    return {"users": get_top_users(tenant_id, days, limit)}


@app.get("/api/admin/users/{target_user_id}")
async def api_admin_user_stats(
    target_user_id: str,
    days: int = 30,
    user: UserContext = Depends(get_user_from_header),
):
    """Get stats for a specific user."""
    tenant_id = user.tenant_id
    result = get_user_stats(tenant_id, target_user_id, days)
    error = _get_result_error(result)
    return _sanitize_result_error(result, GENERIC_ANALYTICS_ERROR) if error else result


@app.get("/api/admin/tools")
async def api_admin_tools(
    period: str = "24h",
    admin_user: dict = Depends(get_admin_user),
):
    """Per-tool health metrics aggregated from recent Langfuse traces."""
    from .telemetry.langfuse_client import list_traces, list_observations
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    from_ts = (now - timedelta(days=7 if period == "7d" else 1)).isoformat()

    result = await list_traces(limit=100, from_timestamp=from_ts)
    traces = result.get("data", [])

    tool_stats: dict[str, dict] = {}
    for t in traces:
        # Get observations for each trace to find tool calls
        trace_id = t.get("id", "")
        if not trace_id:
            continue
        obs_result = await list_observations(trace_id=trace_id, limit=50, type="SPAN")
        for obs in obs_result.get("data", []):
            name = obs.get("name", "")
            if not name or name in ("agent", "supervisor"):
                continue
            if name not in tool_stats:
                tool_stats[name] = {
                    "call_count": 0,
                    "success_count": 0,
                    "error_count": 0,
                    "total_ms": 0,
                    "recent_errors": [],
                }
            s = tool_stats[name]
            s["call_count"] += 1
            level = obs.get("level", "DEFAULT")
            if level == "ERROR":
                s["error_count"] += 1
                msg = obs.get("statusMessage", "")
                if msg and len(s["recent_errors"]) < 5:
                    s["recent_errors"].append(msg[:200])
            else:
                s["success_count"] += 1
            # Duration
            start = obs.get("startTime")
            end = obs.get("endTime")
            if start and end:
                try:
                    from datetime import datetime as dt

                    s_dt = dt.fromisoformat(start.replace("Z", "+00:00"))
                    e_dt = dt.fromisoformat(end.replace("Z", "+00:00"))
                    s["total_ms"] += int((e_dt - s_dt).total_seconds() * 1000)
                except Exception:
                    pass

    tools = []
    for name, s in sorted(
        tool_stats.items(), key=lambda x: x[1]["call_count"], reverse=True
    ):
        total = s["call_count"]
        tools.append(
            {
                "name": name,
                "call_count": total,
                "success_count": s["success_count"],
                "error_count": s["error_count"],
                "success_rate": round(s["success_count"] / total * 100, 1)
                if total
                else 100,
                "avg_duration_ms": round(s["total_ms"] / total) if total else 0,
                "recent_errors": s["recent_errors"],
            }
        )

    return {"tools": tools, "period": period}


@app.get("/api/admin/rate-limit")
async def api_check_rate_limit(user: UserContext = Depends(get_user_from_header)):
    """Check current rate limit status."""
    tenant_id, user_id, _ = get_session_context(user)
    result = check_rate_limit(tenant_id, user_id, user.tier)
    error = _get_result_error(result)
    return _sanitize_result_error(result, GENERIC_ANALYTICS_ERROR) if error else result


# ── User endpoints ───────────────────────────────────────────────────


@app.get("/api/user/me")
async def api_user_me(user: UserContext = Depends(get_user_from_header)):
    """Get current user info."""
    return user.to_dict()


@app.get("/api/user/usage")
async def api_user_usage(
    days: int = 30, user: UserContext = Depends(get_user_from_header)
):
    """Get usage summary for current user."""
    tenant_id = user.tenant_id
    result = get_usage_summary(tenant_id, days)
    error = _get_result_error(result)
    return _sanitize_result_error(result, GENERIC_ANALYTICS_ERROR) if error else result


# ── Feedback endpoint ────────────────────────────────────────────────


def _fetch_cloudwatch_logs_for_session(session_id: str) -> list:
    """Return up to 50 recent CloudWatch log events matching session_id (non-fatal)."""
    if not session_id:
        return []
    try:
        log_group = os.environ.get("EAGLE_TELEMETRY_LOG_GROUP", "/eagle/telemetry")
        region = os.environ.get("AWS_REGION", "us-east-1")
        import boto3

        client = boto3.client("logs", region_name=region)
        now_ms = int(time.time() * 1000)
        day_ms = 24 * 60 * 60 * 1000
        response = client.filter_log_events(
            logGroupName=log_group,
            startTime=now_ms - day_ms,
            endTime=now_ms,
            filterPattern=session_id,
            limit=50,
        )
        return response.get("events", [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("feedback: cloudwatch fetch failed (non-fatal): %s", exc)
        return []


@app.post("/api/feedback")
async def api_submit_feedback(
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """Record user feedback with conversation snapshot and recent CloudWatch logs."""
    user, auth_error = extract_user_context(authorization)
    if REQUIRE_AUTH and user.user_id == "anonymous":
        logger.warning(
            "feedback: auth failed — %s (token present: %s)",
            auth_error,
            bool(authorization),
        )
        raise HTTPException(
            status_code=401, detail=auth_error or "Authentication required"
        )

    body = await request.json()
    session_id = body.get("session_id", "")
    feedback_text = body.get("feedback_text", "").strip()
    conversation_snapshot = body.get("conversation_snapshot", [])
    page = body.get("page", "")
    last_message_id = body.get("last_message_id", "")

    if not feedback_text:
        raise HTTPException(status_code=400, detail="feedback_text is required")

    cloudwatch_logs = _fetch_cloudwatch_logs_for_session(session_id)

    feedback_store.write_feedback(
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        tier=user.tier,
        session_id=session_id,
        feedback_text=feedback_text,
        conversation_snapshot=json.dumps(conversation_snapshot, default=str),
        cloudwatch_logs=json.dumps(cloudwatch_logs, default=str),
        page=page,
        last_message_id=last_message_id,
    )
    notify_feedback(
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        tier=user.tier,
        session_id=session_id,
        feedback_text=feedback_text,
        feedback_type=body.get("feedback_type", "general"),
        page=page,
    )
    return {"status": "ok", "message": "Feedback recorded. Thank you!"}


class MessageFeedbackRequest(BaseModel):
    session_id: str
    message_id: str
    feedback_type: str  # "thumbs_up" | "thumbs_down"
    comment: Optional[str] = ""


@app.post("/api/feedback/message")
async def api_submit_message_feedback(
    req: MessageFeedbackRequest,
    user: UserContext = Depends(get_user_from_header),
):
    """Record thumbs up/down feedback for a specific message."""
    if req.feedback_type not in ("thumbs_up", "thumbs_down"):
        raise HTTPException(
            status_code=400, detail="feedback_type must be 'thumbs_up' or 'thumbs_down'"
        )

    feedback_store.write_message_feedback(
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        session_id=req.session_id,
        message_id=req.message_id,
        feedback_type=req.feedback_type,
        comment=req.comment or "",
    )
    return {"status": "ok", "message": "Feedback recorded"}


# ── Analytics ingestion endpoint ─────────────────────────────────────


@app.post("/api/analytics/events")
async def api_analytics_events(request: Request):
    """Ingest batched analytics events — writes to CloudWatch."""
    try:
        body = await request.json()
        events = body.get("events", [])
        if not events:
            return {"status": "ok", "ingested": 0}

        from .telemetry.cloudwatch_emitter import emit_telemetry_event

        for event in events[:100]:  # Cap at 100 per batch
            emit_telemetry_event(
                event_type=f"analytics.{event.get('event', 'unknown')}",
                tenant_id="frontend",
                data={
                    "page": event.get("page", ""),
                    "metadata": event.get("metadata", {}),
                    "client_timestamp": event.get("timestamp", 0),
                },
            )
        return {"status": "ok", "ingested": len(events)}
    except Exception as e:
        logger.warning("Analytics ingestion error: %s", e)
        return {"status": "ok", "ingested": 0}


# ── Telemetry endpoint ───────────────────────────────────────────────


@app.get("/api/telemetry")
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
        if chat_entries
        else 0
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


@app.get("/api/tools")
async def api_tools():
    """List available EAGLE tools."""
    tools = []
    for tool in EAGLE_TOOLS:
        tools.append(
            {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool.get("input_schema", {}),
            }
        )
    return {"tools": tools, "count": len(tools)}


# ── WebSocket chat endpoint ──────────────────────────────────────────
_ws_counter = 0


@app.websocket("/ws/chat")
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
    await ws.send_json(
        {"type": "connected", "chatId": default_session_id, "user": user.to_dict()}
    )

    try:
        while True:
            data = await ws.receive_json()
            msg_type = data.get("type", "")

            if msg_type == "auth":
                token = data.get("token", "")
                user, error = extract_user_context(token)
                tenant_id = user.tenant_id
                user_id = user.user_id
                await ws.send_json(
                    {
                        "type": "authenticated",
                        "user": user.to_dict(),
                        "error": error,
                    }
                )
                continue

            if msg_type != "chat.send":
                await ws.send_json(
                    {"type": "error", "message": f"Unknown type: {msg_type}"}
                )
                continue

            user_message = data.get("message", "").strip()
            if not user_message:
                await ws.send_json({"type": "error", "message": "Empty message"})
                continue

            session_id = data.get("session_id") or default_session_id

            rate_check = check_rate_limit(tenant_id, user_id, user.tier)
            if not rate_check["allowed"]:
                await ws.send_json(
                    {
                        "type": "error",
                        "message": rate_check["reason"],
                        "rate_limited": True,
                    }
                )
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
                    await ws.send_json(
                        {
                            "type": "tool_use",
                            "tool": tool_name,
                            "input": tool_input,
                        }
                    )

                async def on_tool_result(tool_name: str, output: str):
                    display_output = (
                        output[:2000] + "..." if len(output) > 2000 else output
                    )
                    await ws.send_json(
                        {
                            "type": "tool_result",
                            "tool": tool_name,
                            "output": display_output,
                        }
                    )

                _text_parts: list[str] = []
                _usage: dict = {}
                _final_text: str = ""
                _final_text: str = ""
                async for _sdk_msg in sdk_query(
                    prompt=user_message,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    tier=user.tier or "advanced",
                    session_id=session_id,
                    messages=messages[:-1],  # History excluding current user message
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
                                await on_tool_use(
                                    getattr(_block, "name", ""),
                                    getattr(_block, "input", {}),
                                )
                    elif _msg_type == "ResultMessage":
                        _raw = getattr(_sdk_msg, "usage", {})
                        _usage = (
                            _raw
                            if isinstance(_raw, dict)
                            else {
                                "input_tokens": getattr(_raw, "input_tokens", 0),
                                "output_tokens": getattr(_raw, "output_tokens", 0),
                            }
                        )
                        _final_text = str(getattr(_sdk_msg, "result", "") or "")
                _response_text = "".join(_text_parts) or _final_text
                if _response_text and not _text_parts:
                    await on_text(_response_text)
                result = {
                    "text": _response_text,
                    "usage": _usage,
                    "model": MODEL,
                    "tools_called": tools_called,
                }

                if USE_PERSISTENT_SESSIONS:
                    add_message(
                        session_id, "assistant", result["text"], tenant_id, user_id
                    )
                else:
                    messages.append({"role": "assistant", "content": result["text"]})

                usage = result.get("usage", {})
                elapsed_ms = int((time.time() - start_time) * 1000)

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

                await ws.send_json(
                    {
                        "type": "final",
                        "text": result["text"],
                        "session_id": session_id,
                        "usage": usage,
                        "model": result.get("model", ""),
                        "tools_called": result.get("tools_called", []),
                        "response_time_ms": elapsed_ms,
                        "cost_usd": cost,
                    }
                )

                _log_telemetry(
                    {
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
                    }
                )

            except Exception as e:
                logger.error("Stream error: %s", e, exc_info=True)
                await ws.send_json(
                    {"type": "error", "message": "Internal error processing stream"}
                )

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: %s", default_session_id)
    except Exception as e:
        logger.error("WebSocket error: %s", e, exc_info=True)
        try:
            await ws.send_json(
                {"type": "error", "message": "WebSocket connection error"}
            )
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════
# PRESERVED MULTI-TENANT ENDPOINTS (from original main.py)
# ══════════════════════════════════════════════════════════════════════

# ── Tenant usage & cost endpoints ────────────────────────────────────


@app.get("/api/tenants/{tenant_id}/usage")
async def get_tenant_usage(
    tenant_id: str, current_user: dict = Depends(get_current_user)
):
    """Get usage metrics for authenticated tenant"""
    if tenant_id != current_user["tenant_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    result = get_tenant_usage_overview(tenant_id)
    error = _get_result_error(result)
    return _sanitize_result_error(result, GENERIC_ANALYTICS_ERROR) if error else result


@app.get("/api/tenants/{tenant_id}/costs")
async def get_tenant_costs(
    tenant_id: str, days: int = 30, current_user: dict = Depends(get_current_user)
):
    """Get cost attribution for tenant"""
    if tenant_id != current_user["tenant_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    costs = await cost_service.calculate_tenant_costs(tenant_id, start_date, end_date)
    return costs


@app.get("/api/tenants/{tenant_id}/users/{user_id}/costs")
async def get_user_costs(
    tenant_id: str,
    user_id: str,
    days: int = 30,
    current_user: dict = Depends(get_current_user),
):
    """Get cost attribution for specific user"""
    if tenant_id != current_user["tenant_id"] or user_id != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    costs = await cost_service.calculate_user_costs(
        tenant_id, user_id, start_date, end_date
    )
    return costs


@app.get("/api/tenants/{tenant_id}/subscription")
async def get_subscription_info(
    tenant_id: str, current_user: dict = Depends(get_current_user)
):
    """Get subscription tier information and usage limits"""
    if tenant_id != current_user["tenant_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    tier = current_user["subscription_tier"]
    limits = subscription_service.get_tier_limits(tier)
    usage = await subscription_service.get_usage(tenant_id, tier)
    usage_limits = await subscription_service.check_usage_limits(tenant_id, tier)
    return {
        "tenant_id": tenant_id,
        "subscription_tier": tier.value,
        "limits": limits.dict(),
        "current_usage": usage.dict(),
        "limit_status": usage_limits,
    }


@app.get("/api/tenants/{tenant_id}/sessions")
async def get_tenant_sessions(
    tenant_id: str, current_user: dict = Depends(get_current_user)
):
    """Get all sessions for authenticated tenant"""
    if tenant_id != current_user["tenant_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    return {"tenant_id": tenant_id, "sessions": list_tenant_sessions(tenant_id)}


@app.get("/api/tenants/{tenant_id}/analytics")
async def get_tenant_analytics(
    tenant_id: str, current_user: dict = Depends(get_current_user)
):
    """Get enhanced analytics with trace data for authenticated tenant"""
    if tenant_id != current_user["tenant_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    usage_data = get_tenant_usage_overview(tenant_id)
    if _get_result_error(usage_data):
        usage_data = _sanitize_result_error(usage_data, GENERIC_ANALYTICS_ERROR)
    tier = current_user["subscription_tier"]
    analytics = {
        "tenant_id": tenant_id,
        "subscription_tier": tier.value,
        "total_interactions": usage_data.get("total_messages", 0),
        "active_sessions": usage_data.get("sessions", 0),
        "processing_patterns": {
            "agent_invocations": len(
                [
                    m
                    for m in usage_data.get("metrics", [])
                    if m.get("metric_type") == "agent_invocation"
                ]
            ),
            "trace_analyses": len(
                [
                    m
                    for m in usage_data.get("metrics", [])
                    if m.get("metric_type") == "trace_analysis"
                ]
            ),
        },
        "resource_breakdown": {
            "model_invocations": usage_data.get("total_messages", 0),
            "knowledge_base_queries": 0,
            "action_group_calls": 0,
        },
        "tier_specific_metrics": {
            "mcp_tools_available": subscription_service.get_tier_limits(
                tier
            ).mcp_server_access,
            "usage_limits": subscription_service.get_tier_limits(tier).dict(),
        },
    }
    if usage_data.get("error"):
        analytics["error"] = GENERIC_ANALYTICS_ERROR
    return analytics


# ── Weather MCP endpoints (compatibility) ────────────────────────────


@app.get("/api/mcp/weather/tools")
async def get_available_weather_tools(current_user: dict = Depends(get_current_user)):
    """Get available weather MCP tools for current subscription tier"""
    try:
        from .weather_mcp_service import WeatherMCPClient

        weather_client = WeatherMCPClient()
        tier = current_user["subscription_tier"]
        weather_tools = await weather_client.get_available_weather_tools(tier)
        return {"subscription_tier": tier.value, "weather_tools": weather_tools}
    except ImportError:
        return {
            "subscription_tier": "unknown",
            "weather_tools": [],
            "note": "Weather MCP not available",
        }


@app.post("/api/mcp/weather/{tool_name}")
async def execute_weather_mcp_tool(
    tool_name: str, arguments: dict, current_user: dict = Depends(get_current_user)
):
    """Execute weather MCP tool if subscription tier allows it"""
    try:
        from .weather_mcp_service import WeatherMCPClient

        weather_client = WeatherMCPClient()
        tier = current_user["subscription_tier"]
        result = await weather_client.execute_weather_tool(tool_name, arguments, tier)
        return {
            "tool_name": tool_name,
            "subscription_tier": tier.value,
            "result": result,
        }
    except ImportError:
        raise HTTPException(status_code=503, detail="Weather MCP service not available")


# ── Admin Langfuse trace endpoints ────────────────────────────────────


@app.get("/api/admin/traces")
async def get_admin_traces(
    limit: int = 50,
    page: int = 1,
    user_id: str = None,
    session_id: str = None,
    tag: str = None,
    from_date: str = None,
    to_date: str = None,
    name: str = None,
    admin_user: dict = Depends(get_admin_user),
):
    """List traces from Langfuse (admin only)."""
    from .telemetry.langfuse_client import list_traces

    tags = [tag] if tag else None
    result = await list_traces(
        limit=limit,
        page=page,
        user_id=user_id,
        session_id=session_id,
        tags=tags,
        from_timestamp=from_date,
        to_timestamp=to_date,
        name=name,
    )
    # Normalize for frontend: wrap in {"traces": [...], "meta": {...}}
    data = result.get("data", [])
    traces = []
    for t in data:
        traces.append(
            {
                "trace_id": t.get("id", ""),
                "name": t.get("name", ""),
                "session_id": t.get("sessionId", ""),
                "user_id": t.get("userId", ""),
                "created_at": t.get("timestamp", ""),
                "updated_at": t.get("updatedAt", ""),
                "duration_ms": _langfuse_latency_ms(t),
                "total_input_tokens": t.get("usage", {}).get("input", 0)
                if t.get("usage")
                else 0,
                "total_output_tokens": t.get("usage", {}).get("output", 0)
                if t.get("usage")
                else 0,
                "total_tokens": t.get("usage", {}).get("total", 0)
                if t.get("usage")
                else 0,
                "total_cost_usd": float(t.get("usage", {}).get("totalCost", 0) or 0)
                if t.get("usage")
                else 0,
                "tags": t.get("tags", []),
                "metadata": t.get("metadata", {}),
                "status": "error" if t.get("level") == "ERROR" else "success",
                "environment": _extract_env_from_trace(
                    t.get("tags", []), t.get("metadata")
                ),
                "input": _truncate(t.get("input"), 200),
                "output": _truncate(t.get("output"), 200),
                "observation_count": t.get("observationCount", 0),
                "langfuse_url": _langfuse_url(t.get("id", "")),
            }
        )
    response = {
        "traces": traces,
        "meta": result.get("meta", {}),
        "error": result.get("error"),
    }
    if _get_result_error(response):
        response["error"] = GENERIC_TRACE_ERROR
    return response


@app.get("/api/admin/traces/{trace_id}")
async def get_admin_trace_detail(
    trace_id: str,
    admin_user: dict = Depends(get_admin_user),
):
    """Get single trace detail + observations from Langfuse (admin only)."""
    from .telemetry.langfuse_client import (
        get_trace,
        list_observations,
        langfuse_trace_url,
    )

    trace = await get_trace(trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found in Langfuse")

    # Prefer inline observations from trace detail; fallback to observations API
    raw_obs = trace.get("observations") or []
    if not raw_obs:
        obs_result = await list_observations(trace_id=trace_id, limit=100)
        raw_obs = obs_result.get("data", [])

    observations = []
    for o in raw_obs:
        observations.append(
            {
                "id": o.get("id", ""),
                "name": o.get("name", ""),
                "type": o.get("type", ""),
                "start_time": o.get("startTime", ""),
                "end_time": o.get("endTime", ""),
                "duration_ms": _obs_duration_ms(o),
                "model": o.get("model", ""),
                "input_tokens": o.get("usage", {}).get("input", 0)
                if o.get("usage")
                else 0,
                "output_tokens": o.get("usage", {}).get("output", 0)
                if o.get("usage")
                else 0,
                "total_cost": float(o.get("usage", {}).get("totalCost", 0) or 0)
                if o.get("usage")
                else 0,
                "input": _truncate(o.get("input"), 500),
                "output": _truncate(o.get("output"), 500),
                "metadata": o.get("metadata", {}),
                "level": o.get("level", "DEFAULT"),
                "status_message": o.get("statusMessage", ""),
            }
        )

    return {
        "trace_id": trace.get("id", ""),
        "name": trace.get("name", ""),
        "session_id": trace.get("sessionId", ""),
        "user_id": trace.get("userId", ""),
        "created_at": trace.get("timestamp", ""),
        "duration_ms": _langfuse_latency_ms(trace),
        "total_input_tokens": trace.get("usage", {}).get("input", 0)
        if trace.get("usage")
        else 0,
        "total_output_tokens": trace.get("usage", {}).get("output", 0)
        if trace.get("usage")
        else 0,
        "total_cost_usd": float(trace.get("usage", {}).get("totalCost", 0) or 0)
        if trace.get("usage")
        else 0,
        "tags": trace.get("tags", []),
        "metadata": trace.get("metadata", {}),
        "status": "error" if trace.get("level") == "ERROR" else "success",
        "environment": _extract_env_from_trace(
            trace.get("tags", []), trace.get("metadata")
        ),
        "input": trace.get("input"),
        "output": trace.get("output"),
        "observations": observations,
        "langfuse_url": langfuse_trace_url(trace_id),
    }


@app.get("/api/admin/traces/summary")
async def get_admin_traces_summary(
    period: str = "24h",
    admin_user: dict = Depends(get_admin_user),
):
    """Aggregated trace statistics for the admin dashboard."""
    from .telemetry.langfuse_client import list_traces
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    if period == "7d":
        from_ts = (now - timedelta(days=7)).isoformat()
    else:
        from_ts = (now - timedelta(hours=24)).isoformat()

    result = await list_traces(limit=200, from_timestamp=from_ts)
    data = result.get("data", [])

    total = len(data)
    errors = sum(1 for t in data if t.get("level") == "ERROR")
    error_rate = (errors / total * 100) if total else 0

    latencies = [_langfuse_latency_ms(t) for t in data]
    avg_latency = sum(latencies) / len(latencies) if latencies else 0

    total_cost = sum(
        float(t.get("usage", {}).get("totalCost", 0) or 0)
        for t in data
        if t.get("usage")
    )

    # Tool failure breakdown from tags
    tool_failures: dict[str, int] = {}
    for t in data:
        tags = t.get("tags", [])
        for tag in tags:
            if tag.startswith("error:"):
                category = tag.replace("error:", "")
                tool_failures[category] = tool_failures.get(category, 0) + 1

    return {
        "period": period,
        "total_traces": total,
        "error_count": errors,
        "error_rate_pct": round(error_rate, 1),
        "avg_latency_ms": round(avg_latency),
        "total_cost_usd": round(total_cost, 4),
        "error_breakdown": tool_failures,
    }


def _langfuse_latency_ms(t: dict) -> int:
    """Calculate latency from Langfuse trace latency field or timestamps."""
    if t.get("latency"):
        return int(t["latency"] * 1000)
    return 0


def _obs_duration_ms(o: dict) -> int:
    """Calculate observation duration from start/end times."""
    start = o.get("startTime")
    end = o.get("endTime")
    if start and end:
        try:
            from datetime import datetime as _dt

            # Handle ISO timestamps with Z or +00:00
            for fmt in (
                "%Y-%m-%dT%H:%M:%S.%fZ",
                "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S.%f+00:00",
            ):
                try:
                    s = _dt.strptime(
                        start.replace("+00:00", "Z").rstrip("Z") + "Z", fmt
                    )
                    e = _dt.strptime(end.replace("+00:00", "Z").rstrip("Z") + "Z", fmt)
                    return int((e - s).total_seconds() * 1000)
                except ValueError:
                    continue
        except Exception:
            pass
    return 0


def _extract_env_from_trace(tags: list, metadata: dict = None) -> str:
    """Extract environment from tags (['env:local']) or OTEL metadata ({'eagle.environment': 'local'})."""
    for tag in tags or []:
        if isinstance(tag, str) and tag.startswith("env:"):
            return tag[4:]
    if metadata:
        if metadata.get("eagle.environment"):
            return metadata["eagle.environment"]
        # Strands OTEL puts attributes under trace_attributes
        ta = metadata.get("trace_attributes", {})
        if isinstance(ta, dict) and ta.get("eagle.environment"):
            return ta["eagle.environment"]
    return "unknown"


def _truncate(value: Any, max_len: int = 200) -> Any:
    """Truncate string values for list views."""
    if isinstance(value, str) and len(value) > max_len:
        return value[:max_len] + "..."
    return value


def _langfuse_url(trace_id: str) -> str:
    """Build Langfuse UI link."""
    from .telemetry.langfuse_client import langfuse_trace_url

    return langfuse_trace_url(trace_id)


# ── Admin cost report endpoints (original) ───────────────────────────


@app.get("/api/admin/cost-report")
async def get_cost_report(
    tenant_id: str = None, days: int = 30, admin_user: dict = Depends(get_admin_user)
):
    """Generate comprehensive cost report (admin only)"""
    report = await cost_service.generate_cost_report(tenant_id, days)
    return report


@app.get("/api/admin/tier-costs/{tier}")
async def get_tier_costs(
    tier: str, days: int = 30, admin_user: dict = Depends(get_admin_user)
):
    """Get cost breakdown by subscription tier (admin only)"""
    subscription_tier = SubscriptionTier(tier)
    costs = await cost_service.get_subscription_tier_costs(subscription_tier, days)
    return costs


# ── Admin-Only Granular Cost Endpoints (preserved) ───────────────────


@app.get("/api/admin/tenants/{tenant_id}/overall-cost")
async def get_admin_tenant_overall_cost(
    tenant_id: str, days: int = 30, admin_user: dict = Depends(verify_tenant_admin)
):
    """1. Overall Tenant Cost - Admin Only"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    costs = await admin_cost_service.get_tenant_overall_cost(
        tenant_id, start_date, end_date
    )
    return costs


@app.get("/api/admin/tenants/{tenant_id}/per-user-cost")
async def get_admin_per_user_cost(
    tenant_id: str, days: int = 30, admin_user: dict = Depends(verify_tenant_admin)
):
    """2. Per User Cost - Admin Only"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    costs = await admin_cost_service.get_tenant_per_user_cost(
        tenant_id, start_date, end_date
    )
    return costs


@app.get("/api/admin/tenants/{tenant_id}/service-wise-cost")
async def get_admin_service_wise_cost(
    tenant_id: str, days: int = 30, admin_user: dict = Depends(verify_tenant_admin)
):
    """3. Overall Tenant Service-wise Consumption Cost - Admin Only"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    costs = await admin_cost_service.get_tenant_service_wise_cost(
        tenant_id, start_date, end_date
    )
    return costs


@app.get("/api/admin/tenants/{tenant_id}/users/{user_id}/service-cost")
async def get_admin_user_service_cost(
    tenant_id: str,
    user_id: str,
    days: int = 30,
    admin_user: dict = Depends(verify_tenant_admin),
):
    """4. User Service-wise Consumption Cost - Admin Only"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    costs = await admin_cost_service.get_user_service_wise_cost(
        tenant_id, user_id, start_date, end_date
    )
    return costs


@app.get("/api/admin/tenants/{tenant_id}/comprehensive-report")
async def get_comprehensive_admin_report(
    tenant_id: str, days: int = 30, admin_user: dict = Depends(verify_tenant_admin)
):
    """Comprehensive Admin Cost Report - All 4 breakdowns"""
    report = await admin_cost_service.generate_comprehensive_admin_report(
        tenant_id, days
    )
    return report


@app.get("/api/admin/my-tenants")
async def get_admin_tenants(admin_user: dict = Depends(get_admin_user)):
    """Get tenants where current user has admin access"""
    return {
        "admin_email": admin_user["email"],
        "admin_tenants": admin_user["admin_tenants"],
    }


@app.post("/api/admin/add-to-group")
async def add_user_to_admin_group(request: dict):
    """Add user to admin group during registration"""
    from app.admin_auth import AdminAuthService

    email = request.get("email")
    tenant_id = request.get("tenant_id")

    if not email or not tenant_id:
        raise HTTPException(status_code=400, detail="Email and tenant_id required")

    admin_service_instance = AdminAuthService()

    try:
        group_name = f"{tenant_id}-admins"
        admin_service_instance.cognito_client.create_group(
            GroupName=group_name,
            UserPoolId=admin_service_instance.user_pool_id,
            Description=f"{tenant_id.title()} Administrators",
        )
    except Exception:
        pass

    try:
        admin_service_instance.cognito_client.admin_add_user_to_group(
            UserPoolId=admin_service_instance.user_pool_id,
            Username=email,
            GroupName=f"{tenant_id}-admins",
        )
        return {
            "success": True,
            "message": f"Added {email} to {tenant_id}-admins group",
        }
    except Exception as e:
        logger.error("Failed to add user to admin group: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to add user to admin group")


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
