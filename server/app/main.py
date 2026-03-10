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

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException, Depends, Header, Response, UploadFile, File
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, List, Any
from collections import deque
from datetime import datetime, timedelta
from decimal import Decimal
import asyncio
import json
import time
import logging
import os
import uuid
import io

# EAGLE modules (new)
from .strands_agentic_service import sdk_query, MODEL, EAGLE_TOOLS
from .document_export import export_document, ExportDependencyError
from .session_store import (
    create_session as eagle_create_session, get_session as eagle_get_session,
    update_session as eagle_update_session, delete_session as eagle_delete_session,
    list_sessions as eagle_list_sessions,
    add_message, get_messages, get_messages_for_anthropic, record_usage, get_usage_summary,
    get_tenant_usage_overview, list_tenant_sessions,
)
from .cognito_auth import (
    UserContext, extract_user_context,
    DEV_MODE, DEV_USER_ID, DEV_TENANT_ID
)
from .admin_service import (
    get_dashboard_stats, get_user_stats, get_top_users, get_tool_usage,
    record_request_cost, check_rate_limit, calculate_cost
)
from . import feedback_store

# Existing multi-tenant modules (preserved)
from .models import ChatMessage, ChatResponse, TenantContext, UsageMetric, SubscriptionTier
from .auth import get_current_user
from .subscription_service import SubscriptionService
from .cost_attribution import CostAttributionService
from .admin_cost_service import AdminCostService
from .admin_auth import get_admin_user, verify_tenant_admin, AdminAuthService
from .streaming_routes import create_streaming_router

# Phase 4 — hot-reload stores
from .plugin_store import (
    get_plugin_item, put_plugin_item, list_plugin_entities,
    get_plugin_manifest, ensure_plugin_seeded,
    _entity_cache as _plugin_cache,
)
from .workspace_store import (
    get_or_create_default, create_workspace, get_workspace,
    list_workspaces, activate_workspace, delete_workspace,
)
from .wspc_store import (
    put_override, get_override, list_overrides,
    delete_override, delete_all_overrides,
)
from .prompt_store import (
    put_prompt, get_prompt, delete_prompt, list_tenant_prompts,
    _prompt_cache,
)
from .config_store import (
    get_config, put_config, delete_config, list_config,
    _config_cache,
)
from .template_store import (
    put_template, get_template, delete_template,
    list_tenant_templates, resolve_template,
    _template_cache,
)
from .skill_store import (
    create_skill, get_skill, update_skill, list_skills, list_active_skills,
    submit_for_review, publish_skill, disable_skill, delete_skill,
)
from .package_store import (
    create_package, get_package, update_package, list_packages,
    get_package_checklist, submit_package, approve_package, close_package,
)
from .document_store import (
    get_document,
    list_package_documents,
    get_document_history,
)
from .document_service import (
    create_package_document_version,
    get_document_download_url,
    finalize_document as finalize_document_version,
)
from .package_context_service import (
    clear_active_package,
    resolve_context,
    set_active_package,
)
from .approval_store import (
    create_approval_chain, list_approval_chain,
    record_decision, get_chain_status,
)
from .pref_store import get_prefs, update_prefs, reset_prefs
from .audit_store import write_audit
from .feedback_store import write_feedback, list_feedback
from .health_checks import check_knowledge_base_health

# ── Logging ──────────────────────────────────────────────────────────
from .telemetry.log_context import configure_logging
configure_logging(level=logging.INFO)
logger = logging.getLogger("eagle")

# ── S3 bucket (single source of truth) ───────────────────────────────
_S3_BUCKET = os.getenv("S3_BUCKET", "eagle-documents-dev")

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

# ── Feature Flags ────────────────────────────────────────────────────
USE_PERSISTENT_SESSIONS = os.getenv("USE_PERSISTENT_SESSIONS", "true").lower() == "true"
REQUIRE_AUTH = os.getenv("REQUIRE_AUTH", "false").lower() == "true"

# ── Initialize existing services ─────────────────────────────────────
subscription_service = SubscriptionService()
cost_service = CostAttributionService()
admin_cost_service = AdminCostService()

# ── In-memory session store (fallback when persistent sessions disabled)
SESSIONS: Dict[str, List[dict]] = {}

# ── Telemetry ring buffer ────────────────────────────────────────────
TELEMETRY_LOG: deque = deque(maxlen=500)


def _log_telemetry(entry: dict):
    entry.setdefault("timestamp", datetime.utcnow().isoformat())
    TELEMETRY_LOG.append(entry)
    logger.info(json.dumps(entry, default=str))


# ── Auth Helpers ─────────────────────────────────────────────────────

async def get_user_from_header(authorization: Optional[str] = Header(None)) -> UserContext:
    """Extract user from Authorization header (EAGLE Cognito auth)."""
    user, error = extract_user_context(authorization)
    if REQUIRE_AUTH and user.user_id == "anonymous":
        raise HTTPException(status_code=401, detail=error or "Authentication required")
    return user


def get_session_context(user: UserContext, session_id: Optional[str] = None) -> tuple:
    """Get tenant_id, user_id, and session_id from user context."""
    tenant_id = user.tenant_id
    user_id = user.user_id
    sid = session_id or str(uuid.uuid4())
    return tenant_id, user_id, sid


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
async def api_chat(req: EagleChatRequest, user: UserContext = Depends(get_user_from_header)):
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
                _usage = _raw if isinstance(_raw, dict) else {
                    "input_tokens": getattr(_raw, "input_tokens", 0),
                    "output_tokens": getattr(_raw, "output_tokens", 0),
                }
                _final_text = str(getattr(_sdk_msg, "result", "") or "")
        _response_text = "".join(_text_parts) or _final_text
        result = {"text": _response_text, "usage": _usage, "model": MODEL, "tools_called": _tools_called}

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
            tenant_id, user_id, session_id,
            input_tokens, output_tokens,
            model=result.get("model", MODEL),
            tools_used=result.get("tools_called", []),
            response_time_ms=elapsed_ms
        )

        _log_telemetry({
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
        })

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
        raise HTTPException(status_code=500, detail="Internal server error processing chat request")


# ── Session management endpoints (EAGLE enhanced) ────────────────────

@app.get("/api/sessions")
async def api_list_sessions(
    limit: int = 50,
    user: UserContext = Depends(get_user_from_header)
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
            sessions.append({
                "session_id": sid,
                "message_count": len(msgs),
                "preview": first_msg,
            })

    return {"sessions": sessions, "count": len(sessions)}


@app.post("/api/sessions")
async def api_create_session(
    title: Optional[str] = None,
    user: UserContext = Depends(get_user_from_header)
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
    session_id: str,
    user: UserContext = Depends(get_user_from_header)
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
    user: UserContext = Depends(get_user_from_header)
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
    session_id: str,
    user: UserContext = Depends(get_user_from_header)
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
    session_id: str,
    limit: int = 100,
    user: UserContext = Depends(get_user_from_header)
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


# ── Document export endpoints ────────────────────────────────────────

class ExportRequest(BaseModel):
    content: str
    title: str = "Document"
    format: str = "docx"


@app.post("/api/documents/export")
async def api_export_document(req: ExportRequest, user: UserContext = Depends(get_user_from_header)):
    """Export content to DOCX, PDF, or Markdown."""
    try:
        result = export_document(req.content, req.format, req.title)

        return StreamingResponse(
            io.BytesIO(result["data"]),
            media_type=result["content_type"],
            headers={
                "Content-Disposition": f'attachment; filename="{result["filename"]}"',
                "X-File-Size": str(result["size_bytes"]),
            }
        )
    except ExportDependencyError as e:
        logger.error("Export dependency error: %s", e)
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        logger.warning("Export validation error: %s", e)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Export error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error during export")


@app.get("/api/documents/export/{session_id}")
async def api_export_session(
    session_id: str,
    format: str = "docx",
    user: UserContext = Depends(get_user_from_header)
):
    """Export an entire session conversation."""
    tenant_id, user_id, _ = get_session_context(user)

    if USE_PERSISTENT_SESSIONS:
        messages = get_messages(session_id, tenant_id, user_id)
    else:
        if session_id not in SESSIONS:
            raise HTTPException(status_code=404, detail="Session not found")
        messages = SESSIONS[session_id]

    content = f"# EAGLE Session Export\n\n**Session ID:** {session_id}\n**Exported:** {datetime.utcnow().isoformat()}\n\n---\n\n"

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
            }
        )
    except ExportDependencyError as e:
        logger.error("Session export dependency error: %s", e)
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("Session export error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error during session export")


# ── S3 Document Browser ──────────────────────────────────────────────

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
            documents.append({
                "key": key,
                "name": name,
                "size_bytes": obj["Size"],
                "last_modified": obj["LastModified"].isoformat(),
                "type": _get_doc_type(name),
            })

        return {"documents": documents, "bucket": bucket, "prefix": prefix}
    except ClientError as e:
        logger.error("S3 list error: %s", e, exc_info=True)
        return {"documents": [], "error": "Failed to list documents"}


@app.get("/api/documents/{doc_key:path}")
async def api_get_document(doc_key: str, user: UserContext = Depends(get_user_from_header)):
    """Get document content from S3."""
    import boto3
    from botocore.exceptions import ClientError

    tenant_id = user.tenant_id
    user_id = user.user_id
    bucket = _S3_BUCKET

    # Security: ensure key is within user's prefix
    if not doc_key.startswith(f"eagle/{tenant_id}/{user_id}/"):
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-east-1"))
        response = s3.get_object(Bucket=bucket, Key=doc_key)
        content = response["Body"].read().decode("utf-8", errors="replace")

        return {
            "key": doc_key,
            "content": content,
            "content_type": response.get("ContentType", "text/plain"),
            "size_bytes": response.get("ContentLength", 0),
            "last_modified": response.get("LastModified").isoformat() if response.get("LastModified") else None,
        }
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

    # Security: ensure key is within user's prefix
    if not doc_key.startswith(f"eagle/{tenant_id}/{user_id}/"):
        raise HTTPException(status_code=403, detail="Access denied")

    # Detect if this is a package document by checking the key pattern
    # Package docs: eagle/{tenant}/{user}/packages/{package_id}/...
    is_package_doc = "/packages/" in doc_key

    if is_package_doc:
        # Route through document_service for versioning
        from app.document_service import create_package_document_version

        # Extract package_id and doc_type from the key
        # Pattern: eagle/{tenant}/{user}/packages/{package_id}/{doc_type}_v{N}.{ext}
        parts = doc_key.split("/")
        try:
            pkg_idx = parts.index("packages")
            package_id = parts[pkg_idx + 1]
            filename = parts[-1]
            # Extract doc_type from filename (e.g., "sow_v1.md" → "sow")
            doc_type = filename.split("_v")[0] if "_v" in filename else filename.rsplit(".", 1)[0]
            title = doc_type.replace("_", " ").title()
        except (ValueError, IndexError):
            raise HTTPException(status_code=400, detail="Invalid package document key format")

        result = create_package_document_version(
            tenant_id=tenant_id,
            package_id=package_id,
            doc_type=doc_type,
            content=request.content,
            title=title,
            file_type="md",
            created_by_user_id=user_id,
            change_source=request.change_source,
        )

        if not result.success:
            raise HTTPException(status_code=500, detail=result.error or "Failed to create document version")

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
                ContentType="text/markdown; charset=utf-8",
            )
            return {
                "success": True,
                "key": doc_key,
                "message": "Document saved",
            }
        except ClientError as e:
            logger.error("S3 put document error: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to save document")


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

_ALLOWED_UPLOAD_MIME = {
    "application/pdf", "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain", "text/markdown",
}
_MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB


@app.post("/api/documents/upload")
async def api_upload_document(
    file: UploadFile = File(...),
    user: UserContext = Depends(get_user_from_header),
):
    """Upload a document to the user's S3 workspace and trigger metadata extraction."""
    import boto3
    from botocore.exceptions import ClientError
    import re

    # Validate content type
    content_type = file.content_type or "application/octet-stream"
    if content_type not in _ALLOWED_UPLOAD_MIME:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {content_type}. Accepted: PDF, Word, plain text, Markdown."
        )

    body = await file.read()
    if len(body) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 25 MB limit.")

    tenant_id = user.tenant_id
    user_id = user.user_id
    bucket = _S3_BUCKET

    # Sanitize filename
    safe_name = re.sub(r"[^A-Za-z0-9._\-]", "_", file.filename or "upload")
    key = f"eagle/{tenant_id}/{user_id}/uploads/{safe_name}"

    try:
        s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-east-1"))
        s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType=content_type)
    except ClientError as e:
        logger.error("S3 upload error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to upload document")

    logger.info("Uploaded %s → s3://%s/%s", safe_name, bucket, key)
    return {"key": key, "filename": safe_name, "size_bytes": len(body), "content_type": content_type}


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
    from boto3.dynamodb.conditions import Key, Attr
    table_name = os.getenv("METADATA_TABLE", "eagle-document-metadata-dev")
    try:
        ddb = _get_dynamo()
        table = ddb.Table(table_name)
        resp = table.scan(
            FilterExpression=Attr("PK").begins_with("KB_REVIEW#") & Attr("status").eq(status),
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
    matrix_path = _Path(__file__).resolve().parent.parent.parent.parent / "eagle-plugin" / "data" / "matrix.json"
    if matrix_path.exists():
        try:
            matrix = _json.loads(matrix_path.read_text(encoding="utf-8"))
            matrix = _apply_json_patch(matrix, proposed_diff)
            matrix["version"] = datetime.utcnow().strftime("%Y-%m-%d")
            matrix_path.write_text(_json.dumps(matrix, indent=2, ensure_ascii=False), encoding="utf-8")
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
        new_key = old_key.replace("eagle-knowledge-base/pending/", "eagle-knowledge-base/approved/")
        try:
            s3.copy_object(Bucket=bucket, CopySource={"Bucket": bucket, "Key": old_key}, Key=new_key)
            s3.delete_object(Bucket=bucket, Key=old_key)
        except ClientError as e:
            logger.warning("S3 move failed: %s", e)

    # Update DynamoDB record
    now = datetime.utcnow().isoformat()
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
        new_key = old_key.replace("eagle-knowledge-base/pending/", "eagle-knowledge-base/rejected/")
        try:
            s3.copy_object(Bucket=bucket, CopySource={"Bucket": bucket, "Key": old_key}, Key=new_key)
            s3.delete_object(Bucket=bucket, Key=old_key)
        except ClientError as e:
            logger.warning("S3 move failed: %s", e)

    now = datetime.utcnow().isoformat()
    table.update_item(
        Key={"PK": pk, "SK": "META"},
        UpdateExpression="SET #st = :s, reviewed_by = :u, reviewed_at = :t",
        ExpressionAttributeNames={"#st": "status"},
        ExpressionAttributeValues={":s": "rejected", ":u": user.user_id, ":t": now},
    )
    return {"status": "rejected", "review_id": review_id, "reviewed_at": now}


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
                    target = target[int(part)] if isinstance(target, list) else target[part]
                last = parts[-1]
                if isinstance(target, list):
                    target[int(last)] = op["value"]
                else:
                    target[last] = op["value"]
            elif operation == "add":
                target = result
                for part in parts[:-1]:
                    target = target[int(part)] if isinstance(target, list) else target[part]
                last = parts[-1]
                if isinstance(target, list):
                    target.append(op["value"])
                else:
                    target[last] = op["value"]
            elif operation == "remove":
                target = result
                for part in parts[:-1]:
                    target = target[int(part)] if isinstance(target, list) else target[part]
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

    html_path = _Path(__file__).resolve().parent.parent.parent.parent / "contract-requirements-matrix.html"
    if not html_path.exists():
        logger.warning("contract-requirements-matrix.html not found, skipping HTML regeneration")
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
        parts = [f"id: {_json.dumps(ct['id'])}", f"label: {_json.dumps(ct['label'])}",
                 f"risk: {ct['risk']}", f"category: {_json.dumps(ct['category'])}"]
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
    if "sow" in name_lower:
        return "sow"
    elif "igce" in name_lower:
        return "igce"
    elif "market" in name_lower:
        return "market_research"
    elif "justification" in name_lower or "j&a" in name_lower:
        return "justification"
    elif name_lower.endswith(".md"):
        return "markdown"
    elif name_lower.endswith(".pdf"):
        return "pdf"
    elif name_lower.endswith(".docx"):
        return "docx"
    else:
        return "document"


# ── EAGLE Admin & Analytics endpoints ────────────────────────────────

@app.get("/api/admin/dashboard")
async def api_admin_dashboard(
    days: int = 30,
    user: UserContext = Depends(get_user_from_header)
):
    """Get admin dashboard statistics."""
    tenant_id = user.tenant_id
    return get_dashboard_stats(tenant_id, days)


@app.get("/api/admin/users")
async def api_admin_users(
    days: int = 30,
    limit: int = 10,
    user: UserContext = Depends(get_user_from_header)
):
    """Get top users by usage."""
    tenant_id = user.tenant_id
    return {"users": get_top_users(tenant_id, days, limit)}


@app.get("/api/admin/users/{target_user_id}")
async def api_admin_user_stats(
    target_user_id: str,
    days: int = 30,
    user: UserContext = Depends(get_user_from_header)
):
    """Get stats for a specific user."""
    tenant_id = user.tenant_id
    return get_user_stats(tenant_id, target_user_id, days)


@app.get("/api/admin/tools")
async def api_admin_tools(
    days: int = 30,
    user: UserContext = Depends(get_user_from_header)
):
    """Get tool usage analytics."""
    tenant_id = user.tenant_id
    return get_tool_usage(tenant_id, days)


@app.get("/api/admin/rate-limit")
async def api_check_rate_limit(user: UserContext = Depends(get_user_from_header)):
    """Check current rate limit status."""
    tenant_id, user_id, _ = get_session_context(user)
    return check_rate_limit(tenant_id, user_id, user.tier)


# ── User endpoints ───────────────────────────────────────────────────

@app.get("/api/user/me")
async def api_user_me(user: UserContext = Depends(get_user_from_header)):
    """Get current user info."""
    return user.to_dict()


@app.get("/api/user/usage")
async def api_user_usage(
    days: int = 30,
    user: UserContext = Depends(get_user_from_header)
):
    """Get usage summary for current user."""
    tenant_id = user.tenant_id
    return get_usage_summary(tenant_id, days)


# ── Feedback endpoint ────────────────────────────────────────────────

def _fetch_cloudwatch_logs_for_session(session_id: str) -> list:
    """Return up to 50 recent CloudWatch log events matching session_id (non-fatal)."""
    if not session_id:
        return []
    try:
        log_group = os.environ.get("EAGLE_TELEMETRY_LOG_GROUP", "/eagle/telemetry")
        region = os.environ.get("AWS_REGION", "us-east-1")
        client = _boto3.client("logs", region_name=region)
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
    user: UserContext = Depends(get_user_from_header),
):
    """Record user feedback with conversation snapshot and recent CloudWatch logs."""
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
    return {"status": "ok", "message": "Feedback recorded. Thank you!"}


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
        if chat_entries else 0
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
        tools.append({
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool.get("input_schema", {}),
        })
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
    await ws.send_json({"type": "connected", "chatId": default_session_id, "user": user.to_dict()})

    try:
        while True:
            data = await ws.receive_json()
            msg_type = data.get("type", "")

            if msg_type == "auth":
                token = data.get("token", "")
                user, error = extract_user_context(token)
                tenant_id = user.tenant_id
                user_id = user.user_id
                await ws.send_json({
                    "type": "authenticated",
                    "user": user.to_dict(),
                    "error": error,
                })
                continue

            if msg_type != "chat.send":
                await ws.send_json({"type": "error", "message": f"Unknown type: {msg_type}"})
                continue

            user_message = data.get("message", "").strip()
            if not user_message:
                await ws.send_json({"type": "error", "message": "Empty message"})
                continue

            session_id = data.get("session_id") or default_session_id

            rate_check = check_rate_limit(tenant_id, user_id, user.tier)
            if not rate_check["allowed"]:
                await ws.send_json({"type": "error", "message": rate_check["reason"], "rate_limited": True})
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
                    await ws.send_json({
                        "type": "tool_use",
                        "tool": tool_name,
                        "input": tool_input,
                    })

                async def on_tool_result(tool_name: str, output: str):
                    display_output = output[:2000] + "..." if len(output) > 2000 else output
                    await ws.send_json({
                        "type": "tool_result",
                        "tool": tool_name,
                        "output": display_output,
                    })

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
                                await on_tool_use(getattr(_block, "name", ""), getattr(_block, "input", {}))
                    elif _msg_type == "ResultMessage":
                        _raw = getattr(_sdk_msg, "usage", {})
                        _usage = _raw if isinstance(_raw, dict) else {
                            "input_tokens": getattr(_raw, "input_tokens", 0),
                            "output_tokens": getattr(_raw, "output_tokens", 0),
                        }
                        _final_text = str(getattr(_sdk_msg, "result", "") or "")
                _response_text = "".join(_text_parts) or _final_text
                if _response_text and not _text_parts:
                    await on_text(_response_text)
                result = {"text": _response_text, "usage": _usage, "model": MODEL, "tools_called": tools_called}

                if USE_PERSISTENT_SESSIONS:
                    add_message(session_id, "assistant", result["text"], tenant_id, user_id)
                else:
                    messages.append({"role": "assistant", "content": result["text"]})

                usage = result.get("usage", {})
                elapsed_ms = int((time.time() - start_time) * 1000)

                input_tokens = usage.get("input_tokens", 0)
                output_tokens = usage.get("output_tokens", 0)
                cost = calculate_cost(input_tokens, output_tokens)

                record_request_cost(
                    tenant_id, user_id, session_id,
                    input_tokens, output_tokens,
                    model=result.get("model", MODEL),
                    tools_used=result.get("tools_called", []),
                    response_time_ms=elapsed_ms
                )

                await ws.send_json({
                    "type": "final",
                    "text": result["text"],
                    "session_id": session_id,
                    "usage": usage,
                    "model": result.get("model", ""),
                    "tools_called": result.get("tools_called", []),
                    "response_time_ms": elapsed_ms,
                    "cost_usd": cost,
                })

                _log_telemetry({
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
                })

            except Exception as e:
                logger.error("Stream error: %s", e, exc_info=True)
                await ws.send_json({"type": "error", "message": "Internal error processing stream"})

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: %s", default_session_id)
    except Exception as e:
        logger.error("WebSocket error: %s", e, exc_info=True)
        try:
            await ws.send_json({"type": "error", "message": "WebSocket connection error"})
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════
# PRESERVED MULTI-TENANT ENDPOINTS (from original main.py)
# ══════════════════════════════════════════════════════════════════════

# ── Tenant usage & cost endpoints ────────────────────────────────────

@app.get("/api/tenants/{tenant_id}/usage")
async def get_tenant_usage(tenant_id: str, current_user: dict = Depends(get_current_user)):
    """Get usage metrics for authenticated tenant"""
    if tenant_id != current_user["tenant_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    return get_tenant_usage_overview(tenant_id)


@app.get("/api/tenants/{tenant_id}/costs")
async def get_tenant_costs(tenant_id: str, days: int = 30, current_user: dict = Depends(get_current_user)):
    """Get cost attribution for tenant"""
    if tenant_id != current_user["tenant_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    costs = await cost_service.calculate_tenant_costs(tenant_id, start_date, end_date)
    return costs


@app.get("/api/tenants/{tenant_id}/users/{user_id}/costs")
async def get_user_costs(tenant_id: str, user_id: str, days: int = 30, current_user: dict = Depends(get_current_user)):
    """Get cost attribution for specific user"""
    if tenant_id != current_user["tenant_id"] or user_id != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    costs = await cost_service.calculate_user_costs(tenant_id, user_id, start_date, end_date)
    return costs


@app.get("/api/tenants/{tenant_id}/subscription")
async def get_subscription_info(tenant_id: str, current_user: dict = Depends(get_current_user)):
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
        "limit_status": usage_limits
    }


@app.get("/api/tenants/{tenant_id}/sessions")
async def get_tenant_sessions(tenant_id: str, current_user: dict = Depends(get_current_user)):
    """Get all sessions for authenticated tenant"""
    if tenant_id != current_user["tenant_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    return {
        "tenant_id": tenant_id,
        "sessions": list_tenant_sessions(tenant_id)
    }


@app.get("/api/tenants/{tenant_id}/analytics")
async def get_tenant_analytics(tenant_id: str, current_user: dict = Depends(get_current_user)):
    """Get enhanced analytics with trace data for authenticated tenant"""
    if tenant_id != current_user["tenant_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    usage_data = get_tenant_usage_overview(tenant_id)
    tier = current_user["subscription_tier"]
    analytics = {
        "tenant_id": tenant_id,
        "subscription_tier": tier.value,
        "total_interactions": usage_data.get("total_messages", 0),
        "active_sessions": usage_data.get("sessions", 0),
        "processing_patterns": {
            "agent_invocations": len([m for m in usage_data.get("metrics", []) if m.get("metric_type") == "agent_invocation"]),
            "trace_analyses": len([m for m in usage_data.get("metrics", []) if m.get("metric_type") == "trace_analysis"])
        },
        "resource_breakdown": {
            "model_invocations": usage_data.get("total_messages", 0),
            "knowledge_base_queries": 0,
            "action_group_calls": 0
        },
        "tier_specific_metrics": {
            "mcp_tools_available": subscription_service.get_tier_limits(tier).mcp_server_access,
            "usage_limits": subscription_service.get_tier_limits(tier).dict()
        }
    }
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
        return {"subscription_tier": "unknown", "weather_tools": [], "note": "Weather MCP not available"}


@app.post("/api/mcp/weather/{tool_name}")
async def execute_weather_mcp_tool(tool_name: str, arguments: dict, current_user: dict = Depends(get_current_user)):
    """Execute weather MCP tool if subscription tier allows it"""
    try:
        from .weather_mcp_service import WeatherMCPClient
        weather_client = WeatherMCPClient()
        tier = current_user["subscription_tier"]
        result = await weather_client.execute_weather_tool(tool_name, arguments, tier)
        return {"tool_name": tool_name, "subscription_tier": tier.value, "result": result}
    except ImportError:
        raise HTTPException(status_code=503, detail="Weather MCP service not available")


# ── Admin cost report endpoints (original) ───────────────────────────

@app.get("/api/admin/cost-report")
async def get_cost_report(tenant_id: str = None, days: int = 30, admin_user: dict = Depends(get_admin_user)):
    """Generate comprehensive cost report (admin only)"""
    report = await cost_service.generate_cost_report(tenant_id, days)
    return report


@app.get("/api/admin/tier-costs/{tier}")
async def get_tier_costs(tier: str, days: int = 30, admin_user: dict = Depends(get_admin_user)):
    """Get cost breakdown by subscription tier (admin only)"""
    subscription_tier = SubscriptionTier(tier)
    costs = await cost_service.get_subscription_tier_costs(subscription_tier, days)
    return costs


# ── Admin-Only Granular Cost Endpoints (preserved) ───────────────────

@app.get("/api/admin/tenants/{tenant_id}/overall-cost")
async def get_admin_tenant_overall_cost(tenant_id: str, days: int = 30, admin_user: dict = Depends(verify_tenant_admin)):
    """1. Overall Tenant Cost - Admin Only"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    costs = await admin_cost_service.get_tenant_overall_cost(tenant_id, start_date, end_date)
    return costs


@app.get("/api/admin/tenants/{tenant_id}/per-user-cost")
async def get_admin_per_user_cost(tenant_id: str, days: int = 30, admin_user: dict = Depends(verify_tenant_admin)):
    """2. Per User Cost - Admin Only"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    costs = await admin_cost_service.get_tenant_per_user_cost(tenant_id, start_date, end_date)
    return costs


@app.get("/api/admin/tenants/{tenant_id}/service-wise-cost")
async def get_admin_service_wise_cost(tenant_id: str, days: int = 30, admin_user: dict = Depends(verify_tenant_admin)):
    """3. Overall Tenant Service-wise Consumption Cost - Admin Only"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    costs = await admin_cost_service.get_tenant_service_wise_cost(tenant_id, start_date, end_date)
    return costs


@app.get("/api/admin/tenants/{tenant_id}/users/{user_id}/service-cost")
async def get_admin_user_service_cost(tenant_id: str, user_id: str, days: int = 30, admin_user: dict = Depends(verify_tenant_admin)):
    """4. User Service-wise Consumption Cost - Admin Only"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    costs = await admin_cost_service.get_user_service_wise_cost(tenant_id, user_id, start_date, end_date)
    return costs


@app.get("/api/admin/tenants/{tenant_id}/comprehensive-report")
async def get_comprehensive_admin_report(tenant_id: str, days: int = 30, admin_user: dict = Depends(verify_tenant_admin)):
    """Comprehensive Admin Cost Report - All 4 breakdowns"""
    report = await admin_cost_service.generate_comprehensive_admin_report(tenant_id, days)
    return report


@app.get("/api/admin/my-tenants")
async def get_admin_tenants(admin_user: dict = Depends(get_admin_user)):
    """Get tenants where current user has admin access"""
    return {
        "admin_email": admin_user["email"],
        "admin_tenants": admin_user["admin_tenants"]
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
            Description=f"{tenant_id.title()} Administrators"
        )
    except Exception:
        pass

    try:
        admin_service_instance.cognito_client.admin_add_user_to_group(
            UserPoolId=admin_service_instance.user_pool_id,
            Username=email,
            GroupName=f"{tenant_id}-admins"
        )
        return {"success": True, "message": f"Added {email} to {tenant_id}-admins group"}
    except Exception as e:
        logger.error("Failed to add user to admin group: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to add user to admin group")


# ══════════════════════════════════════════════════════════════════════
# SSE STREAMING ROUTER (preserved from C3 integration)
# ══════════════════════════════════════════════════════════════════════

# Include SSE streaming router - uses EAGLE agentic_service now
streaming_router = create_streaming_router(subscription_service)
app.include_router(streaming_router)


# ══════════════════════════════════════════════════════════════════════
# HEALTH CHECK (frontend now served by Next.js on port 3000)
# ══════════════════════════════════════════════════════════════════════

@app.get("/api/health")
async def health_check():
    """Backend health check endpoint."""
    knowledge_base = check_knowledge_base_health()
    return {
        "status": "healthy",
        "service": "eagle-backend",
        "version": "4.0.0",
        "services": {
            "bedrock": True,
            "dynamodb": True,
            "cognito": True,
            "s3": True,
            "knowledge_metadata_table": knowledge_base["metadata_table"]["ok"],
            "knowledge_document_bucket": knowledge_base["document_bucket"]["ok"],
        },
        "knowledge_base": knowledge_base,
        "timestamp": datetime.utcnow().isoformat(),
    }


# ══════════════════════════════════════════════════════════════════════
# PHASE 4 — HOT-RELOAD ADMIN + USER ENDPOINTS
# ══════════════════════════════════════════════════════════════════════

# ── Admin: Cache Flush ─────────────────────────────────────────────

@app.post("/api/admin/reload")
async def admin_reload_caches(user: UserContext = Depends(get_user_from_header)):
    """Force-flush all in-process caches across plugin, prompt, config, template stores.

    All ECS tasks flush independently on next request — visible within 60s without restart.
    """
    _plugin_cache.clear()
    _prompt_cache.clear()
    _config_cache.clear()
    _template_cache.clear()
    write_audit(
        tenant_id=user.tenant_id,
        entity_type="cache",
        entity_name="all",
        event_type="reload",
        actor_user_id=user.user_id,
    )
    return {"status": "flushed", "caches": ["plugin", "prompt", "config", "template"]}


@app.post("/api/admin/plugin/sync")
async def admin_plugin_sync(user: UserContext = Depends(get_user_from_header)):
    """Force reseed all PLUGIN# entities from bundled eagle-plugin/ files (factory reset).

    Bumps the manifest version to trigger a fresh seed on next request.
    """
    from .plugin_store import BUNDLED_PLUGIN_VERSION
    # Delete manifest so ensure_plugin_seeded() treats it as stale
    try:
        from .plugin_store import _get_table
        _get_table().delete_item(Key={"PK": "PLUGIN#manifest", "SK": "PLUGIN#manifest"})
    except Exception:
        pass
    _plugin_cache.clear()
    ensure_plugin_seeded()
    write_audit(
        tenant_id=user.tenant_id,
        entity_type="plugin",
        entity_name="manifest",
        event_type="sync",
        actor_user_id=user.user_id,
        after=f"reseeded from bundled v{BUNDLED_PLUGIN_VERSION}",
    )
    return {"status": "reseeded", "version": BUNDLED_PLUGIN_VERSION}


# ── Admin: Plugin Entity CRUD ──────────────────────────────────────

@app.get("/api/admin/plugin/status")
async def admin_plugin_status(user: UserContext = Depends(get_user_from_header)):
    """Return PLUGIN# manifest version, seed date, and entity counts."""
    manifest = get_plugin_manifest()
    agents = list_plugin_entities("agents")
    skills = list_plugin_entities("skills")
    templates = list_plugin_entities("templates")
    return {
        "manifest": manifest,
        "counts": {"agents": len(agents), "skills": len(skills), "templates": len(templates)},
    }


@app.get("/api/admin/plugin/{entity_type}")
async def admin_list_plugin_entities(
    entity_type: str,
    user: UserContext = Depends(get_user_from_header),
):
    """List all PLUGIN# items for the given entity type."""
    return list_plugin_entities(entity_type)


@app.get("/api/admin/plugin/{entity_type}/{name}")
async def admin_get_plugin_entity(
    entity_type: str,
    name: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Get a single PLUGIN# entity by type and name."""
    item = get_plugin_item(entity_type, name)
    if not item:
        raise HTTPException(status_code=404, detail=f"Plugin entity not found: {entity_type}/{name}")
    return item


@app.put("/api/admin/plugin/{entity_type}/{name}")
async def admin_put_plugin_entity(
    entity_type: str,
    name: str,
    body: Dict[str, Any],
    user: UserContext = Depends(get_user_from_header),
):
    """Update a PLUGIN# entity content. Writes an AUDIT# entry."""
    existing = get_plugin_item(entity_type, name)
    item = put_plugin_item(
        entity_type=entity_type,
        name=name,
        content=body.get("content", ""),
        metadata=body.get("metadata"),
        content_type=body.get("content_type", "markdown"),
    )
    write_audit(
        tenant_id=user.tenant_id,
        entity_type=f"plugin_{entity_type}",
        entity_name=name,
        event_type="update",
        actor_user_id=user.user_id,
        before=existing.get("content") if existing else None,
        after=item.get("content"),
    )
    _plugin_cache.pop(entity_type, None)
    return item


# ── Workspaces ─────────────────────────────────────────────────────

@app.get("/api/workspace")
async def list_user_workspaces(user: UserContext = Depends(get_user_from_header)):
    """List all workspaces for the current user."""
    return list_workspaces(user.tenant_id, user.user_id)


@app.post("/api/workspace")
async def create_user_workspace(
    body: Dict[str, Any],
    user: UserContext = Depends(get_user_from_header),
):
    """Create a new workspace for the current user."""
    ws = create_workspace(
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        name=body.get("name", "New Workspace"),
        description=body.get("description", ""),
        visibility=body.get("visibility", "private"),
        is_active=body.get("is_active", False),
    )
    return ws


@app.get("/api/workspace/active")
async def get_active_workspace_endpoint(user: UserContext = Depends(get_user_from_header)):
    """Return the currently active workspace (auto-provisions Default if none exists)."""
    return get_or_create_default(user.tenant_id, user.user_id)


@app.get("/api/workspace/{workspace_id}")
async def get_workspace_endpoint(
    workspace_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Get a workspace by ID."""
    ws = get_workspace(user.tenant_id, user.user_id, workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return ws


@app.put("/api/workspace/{workspace_id}/activate")
async def activate_workspace_endpoint(
    workspace_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Switch active workspace."""
    ws = activate_workspace(user.tenant_id, user.user_id, workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return ws


@app.delete("/api/workspace/{workspace_id}")
async def delete_workspace_endpoint(
    workspace_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Delete a non-default workspace and all its overrides."""
    delete_all_overrides(user.tenant_id, user.user_id, workspace_id)
    ok = delete_workspace(user.tenant_id, user.user_id, workspace_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Cannot delete default workspace or workspace not found")
    return {"deleted": workspace_id}


# ── Workspace Overrides (WSPC#) ────────────────────────────────────

@app.get("/api/workspace/{workspace_id}/overrides")
async def list_workspace_overrides(
    workspace_id: str,
    entity_type: Optional[str] = None,
    user: UserContext = Depends(get_user_from_header),
):
    """List all overrides in a workspace."""
    return list_overrides(user.tenant_id, user.user_id, workspace_id, entity_type)


@app.put("/api/workspace/{workspace_id}/overrides/{entity_type}/{name}")
async def set_workspace_override(
    workspace_id: str,
    entity_type: str,
    name: str,
    body: Dict[str, Any],
    user: UserContext = Depends(get_user_from_header),
):
    """Set a workspace override for an agent, skill, template, or config."""
    return put_override(
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        workspace_id=workspace_id,
        entity_type=entity_type,
        name=name,
        content=body.get("content", ""),
        is_append=body.get("is_append", False),
    )


@app.delete("/api/workspace/{workspace_id}/overrides/{entity_type}/{name}")
async def delete_workspace_override(
    workspace_id: str,
    entity_type: str,
    name: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Delete a specific override (reset to default for this entity)."""
    ok = delete_override(user.tenant_id, user.user_id, workspace_id, entity_type, name)
    return {"deleted": ok}


@app.delete("/api/workspace/{workspace_id}/overrides")
async def reset_workspace_overrides(
    workspace_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Delete all overrides in a workspace (reset entire workspace to defaults)."""
    count = delete_all_overrides(user.tenant_id, user.user_id, workspace_id)
    return {"deleted_count": count}


# ── Admin Prompt Overrides (PROMPT#) ──────────────────────────────

@app.get("/api/admin/prompts")
async def list_admin_prompts(user: UserContext = Depends(get_user_from_header)):
    """List all tenant-level prompt overrides."""
    return list_tenant_prompts(user.tenant_id)


@app.put("/api/admin/prompts/{agent_name}")
async def set_admin_prompt(
    agent_name: str,
    body: Dict[str, Any],
    user: UserContext = Depends(get_user_from_header),
):
    """Set a tenant-level prompt override for an agent."""
    existing = get_prompt(user.tenant_id, agent_name)
    item = put_prompt(
        tenant_id=user.tenant_id,
        agent_name=agent_name,
        prompt_body=body.get("prompt_body", ""),
        is_append=body.get("is_append", False),
        updated_by=user.user_id,
    )
    write_audit(
        tenant_id=user.tenant_id,
        entity_type="prompt",
        entity_name=agent_name,
        event_type="update",
        actor_user_id=user.user_id,
        before=existing.get("prompt_body") if existing else None,
        after=item.get("prompt_body"),
    )
    _prompt_cache.pop(f"{user.tenant_id}#{agent_name}", None)
    return item


@app.delete("/api/admin/prompts/{agent_name}")
async def delete_admin_prompt(
    agent_name: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Delete a tenant prompt override (reverts to PLUGIN# canonical)."""
    ok = delete_prompt(user.tenant_id, agent_name)
    _prompt_cache.pop(f"{user.tenant_id}#{agent_name}", None)
    return {"deleted": ok}


# ── Runtime Config (CONFIG#) ───────────────────────────────────────

@app.get("/api/admin/config")
async def get_all_config(user: UserContext = Depends(get_user_from_header)):
    """Return all CONFIG# runtime feature flags."""
    return list_config()


@app.put("/api/admin/config/{key}")
async def set_config_key(
    key: str,
    body: Dict[str, Any],
    user: UserContext = Depends(get_user_from_header),
):
    """Set a CONFIG# runtime value."""
    item = put_config(key=key, value=body.get("value"), updated_by=user.user_id)
    write_audit(
        tenant_id=user.tenant_id,
        entity_type="config",
        entity_name=key,
        event_type="update",
        actor_user_id=user.user_id,
        after=str(body.get("value")),
    )
    return item


@app.delete("/api/admin/config/{key}")
async def delete_config_key(
    key: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Delete a CONFIG# key (reverts to hardcoded default)."""
    ok = delete_config(key)
    return {"deleted": ok}


# ── Templates ──────────────────────────────────────────────────────

@app.get("/api/templates")
async def list_templates_endpoint(
    doc_type: Optional[str] = None,
    user: UserContext = Depends(get_user_from_header),
):
    """List available templates for the current tenant."""
    return list_tenant_templates(user.tenant_id, doc_type)


@app.get("/api/templates/{doc_type}")
async def get_active_template(
    doc_type: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Return the resolved template for this user (4-layer fallback)."""
    body, source = resolve_template(user.tenant_id, user.user_id, doc_type)
    return {"doc_type": doc_type, "template_body": body, "source": source}


@app.post("/api/templates/{doc_type}")
async def create_template_endpoint(
    doc_type: str,
    body: Dict[str, Any],
    user: UserContext = Depends(get_user_from_header),
):
    """Create or update a user/tenant template override."""
    return put_template(
        tenant_id=user.tenant_id,
        doc_type=doc_type,
        user_id=body.get("user_id", user.user_id),
        template_body=body.get("template_body", ""),
        display_name=body.get("display_name", ""),
        is_default=body.get("is_default", False),
    )


@app.delete("/api/templates/{doc_type}")
async def delete_template_endpoint(
    doc_type: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Delete the current user's template override for a doc type."""
    ok = delete_template(user.tenant_id, doc_type, user.user_id)
    return {"deleted": ok}


# ── User-Created Skills (SKILL#) ───────────────────────────────────

@app.get("/api/skills")
async def list_skills_endpoint(
    status: Optional[str] = None,
    user: UserContext = Depends(get_user_from_header),
):
    """List user-created skills. Returns active bundled + tenant SKILL# items."""
    return list_skills(user.tenant_id, status)


@app.post("/api/skills")
async def create_skill_endpoint(
    body: Dict[str, Any],
    user: UserContext = Depends(get_user_from_header),
):
    """Create a new user skill (status=draft)."""
    return create_skill(
        tenant_id=user.tenant_id,
        owner_user_id=user.user_id,
        name=body["name"],
        display_name=body.get("display_name", body["name"]),
        description=body.get("description", ""),
        prompt_body=body.get("prompt_body", ""),
        triggers=body.get("triggers"),
        tools=body.get("tools"),
        model=body.get("model"),
        visibility=body.get("visibility", "private"),
    )


@app.get("/api/skills/{skill_id}")
async def get_skill_endpoint(
    skill_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Get a skill by ID."""
    skill = get_skill(user.tenant_id, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return skill


@app.put("/api/skills/{skill_id}")
async def update_skill_endpoint(
    skill_id: str,
    body: Dict[str, Any],
    user: UserContext = Depends(get_user_from_header),
):
    """Update a draft skill."""
    updated = update_skill(user.tenant_id, skill_id, body)
    if not updated:
        raise HTTPException(status_code=404, detail="Skill not found")
    return updated


@app.post("/api/skills/{skill_id}/submit")
async def submit_skill_endpoint(
    skill_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Submit a skill for review (draft → review)."""
    skill = submit_for_review(user.tenant_id, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found or not in draft status")
    return skill


@app.post("/api/skills/{skill_id}/publish")
async def publish_skill_endpoint(
    skill_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Approve and activate a skill (review → active). Admin action."""
    skill = publish_skill(user.tenant_id, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found or not in review status")
    write_audit(
        tenant_id=user.tenant_id,
        entity_type="skill",
        entity_name=skill_id,
        event_type="publish",
        actor_user_id=user.user_id,
    )
    return skill


@app.delete("/api/skills/{skill_id}")
async def delete_skill_endpoint(
    skill_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Delete a skill (only draft or disabled)."""
    ok = delete_skill(user.tenant_id, skill_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Skill not found or cannot be deleted (must be draft or disabled)")
    return {"deleted": skill_id}


# ── Acquisition Packages (PACKAGE#) ───────────────────────────────

@app.get("/api/packages")
async def list_packages_endpoint(
    status: Optional[str] = None,
    user: UserContext = Depends(get_user_from_header),
):
    """List acquisition packages for the current user's tenant."""
    return list_packages(user.tenant_id, status=status, owner_user_id=user.user_id)


@app.post("/api/packages")
async def create_package_endpoint(
    body: Dict[str, Any],
    user: UserContext = Depends(get_user_from_header),
):
    """Create a new acquisition package (auto-determines FAR pathway)."""
    from decimal import Decimal as _Decimal
    return create_package(
        tenant_id=user.tenant_id,
        owner_user_id=user.user_id,
        title=body["title"],
        requirement_type=body.get("requirement_type", "services"),
        estimated_value=_Decimal(str(body.get("estimated_value", "0"))),
        session_id=body.get("session_id"),
        notes=body.get("notes", ""),
        contract_vehicle=body.get("contract_vehicle"),
    )


@app.get("/api/packages/{package_id}")
async def get_package_endpoint(
    package_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Get an acquisition package by ID."""
    pkg = get_package(user.tenant_id, package_id)
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
    return pkg


@app.put("/api/packages/{package_id}")
async def update_package_endpoint(
    package_id: str,
    body: Dict[str, Any],
    user: UserContext = Depends(get_user_from_header),
):
    """Update an acquisition package."""
    updated = update_package(user.tenant_id, package_id, body)
    if not updated:
        raise HTTPException(status_code=404, detail="Package not found")
    return updated


@app.get("/api/packages/{package_id}/checklist")
async def get_package_checklist_endpoint(
    package_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Return the document checklist for a package (required, completed, missing)."""
    return get_package_checklist(user.tenant_id, package_id)


@app.post("/api/packages/{package_id}/submit")
async def submit_package_endpoint(
    package_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Submit package for review (drafting → review)."""
    pkg = submit_package(user.tenant_id, package_id)
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
    write_audit(
        tenant_id=user.tenant_id,
        entity_type="package",
        entity_name=package_id,
        event_type="submit",
        actor_user_id=user.user_id,
    )
    return pkg


@app.post("/api/packages/{package_id}/approve")
async def approve_package_endpoint(
    package_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Approve a package (review → approved)."""
    pkg = approve_package(user.tenant_id, package_id)
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
    write_audit(
        tenant_id=user.tenant_id,
        entity_type="package",
        entity_name=package_id,
        event_type="approve",
        actor_user_id=user.user_id,
    )
    return pkg


# ── Acquisition Documents (DOCUMENT#) ─────────────────────────────

class ResolvePackageContextRequest(BaseModel):
    session_id: str
    package_id: Optional[str] = None
    action: Optional[str] = None  # "set" | "clear" | None

@app.get("/api/packages/{package_id}/documents")
async def list_documents_endpoint(
    package_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """List all generated documents for a package (latest version per doc type)."""
    return list_package_documents(user.tenant_id, package_id)


@app.post("/api/packages/resolve-context")
async def resolve_package_context_endpoint(
    body: ResolvePackageContextRequest,
    user: UserContext = Depends(get_user_from_header),
):
    """Resolve and optionally persist active package context for a session."""
    if body.action == "clear":
        clear_active_package(user.tenant_id, user.user_id, body.session_id)
        return {"mode": "workspace", "package_id": None}

    if body.package_id and body.action in (None, "set"):
        set_active_package(
            tenant_id=user.tenant_id,
            user_id=user.user_id,
            session_id=body.session_id,
            package_id=body.package_id,
        )

    ctx = resolve_context(
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        session_id=body.session_id,
        explicit_package_id=body.package_id,
    )
    return {
        "mode": ctx.mode,
        "package_id": ctx.package_id,
        "package_title": ctx.package_title,
        "acquisition_pathway": ctx.acquisition_pathway,
        "required_documents": ctx.required_documents or [],
        "completed_documents": ctx.completed_documents or [],
    }


@app.post("/api/packages/{package_id}/documents")
async def create_document_endpoint(
    package_id: str,
    body: Dict[str, Any],
    user: UserContext = Depends(get_user_from_header),
):
    """Save a generated document for a package using canonical document service."""
    result = create_package_document_version(
        tenant_id=user.tenant_id,
        package_id=package_id,
        doc_type=body["doc_type"],
        content=body["content"],
        title=body.get("title") or body["doc_type"].replace("_", " ").title(),
        file_type=body.get("file_type", "md"),
        created_by_user_id=user.user_id,
        session_id=body.get("session_id"),
        change_source=body.get("change_source", "user_edit"),
        template_id=body.get("template_id"),
    )
    if not result.success:
        status = 404 if result.error and "not found" in result.error.lower() else 500
        raise HTTPException(status_code=status, detail=result.error or "Document creation failed")

    doc = get_document(user.tenant_id, package_id, body["doc_type"], result.version)
    if doc:
        return doc
    return result.to_dict()


@app.get("/api/packages/{package_id}/documents/{doc_type}/history")
async def get_document_history_endpoint(
    package_id: str,
    doc_type: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Return version history for a package document type."""
    return get_document_history(user.tenant_id, package_id, doc_type)


@app.get("/api/packages/{package_id}/documents/{doc_type}/versions/{version}/download-url")
async def get_document_download_url_endpoint(
    package_id: str,
    doc_type: str,
    version: int,
    expires_in: int = 3600,
    user: UserContext = Depends(get_user_from_header),
):
    """Return a presigned download URL for a specific document version."""
    url = get_document_download_url(
        tenant_id=user.tenant_id,
        package_id=package_id,
        doc_type=doc_type,
        version=version,
        expires_in=expires_in,
    )
    if not url:
        raise HTTPException(status_code=404, detail="Document download URL unavailable")
    return {"download_url": url, "expires_in": expires_in}


@app.get("/api/packages/{package_id}/documents/{doc_type}")
async def get_document_endpoint(
    package_id: str,
    doc_type: str,
    version: Optional[int] = None,
    user: UserContext = Depends(get_user_from_header),
):
    """Get a specific document (latest version by default)."""
    doc = get_document(user.tenant_id, package_id, doc_type, version)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@app.post("/api/packages/{package_id}/documents/{doc_type}/finalize")
async def finalize_document_endpoint(
    package_id: str,
    doc_type: str,
    body: Dict[str, Any],
    user: UserContext = Depends(get_user_from_header),
):
    """Mark a document version as final."""
    doc = finalize_document_version(
        user.tenant_id,
        package_id,
        doc_type,
        body.get("version", 1),
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@app.post("/api/packages/{package_id}/documents/{doc_type}/versions/{version}/promote-final")
async def promote_document_final_endpoint(
    package_id: str,
    doc_type: str,
    version: int,
    user: UserContext = Depends(get_user_from_header),
):
    """Promote a specific document version to final status."""
    doc = finalize_document_version(user.tenant_id, package_id, doc_type, version)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


# ── Approval Chains (APPROVAL#) ────────────────────────────────────

@app.get("/api/packages/{package_id}/approvals")
async def get_approval_chain_endpoint(
    package_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Return the approval chain status for a package."""
    return get_chain_status(user.tenant_id, package_id)


@app.post("/api/packages/{package_id}/approvals")
async def create_approval_chain_endpoint(
    package_id: str,
    body: Dict[str, Any],
    user: UserContext = Depends(get_user_from_header),
):
    """Create the FAR-driven approval chain for a package."""
    from decimal import Decimal as _Decimal
    estimated_value = _Decimal(str(body.get("estimated_value", "0")))
    return create_approval_chain(user.tenant_id, package_id, estimated_value)


@app.post("/api/packages/{package_id}/approvals/{step}/decision")
async def record_approval_decision(
    package_id: str,
    step: int,
    body: Dict[str, Any],
    user: UserContext = Depends(get_user_from_header),
):
    """Record an approval decision (approved/rejected/returned) for a step."""
    result = record_decision(
        tenant_id=user.tenant_id,
        package_id=package_id,
        step=step,
        status=body["status"],
        comments=body.get("comments", ""),
        decided_by=user.user_id,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Approval step not found")
    write_audit(
        tenant_id=user.tenant_id,
        entity_type="approval",
        entity_name=f"{package_id}#{step}",
        event_type=body["status"],
        actor_user_id=user.user_id,
        after=body.get("comments"),
    )
    return result


# ── User Preferences (PREF#) ───────────────────────────────────────

@app.get("/api/user/preferences")
async def get_user_preferences(user: UserContext = Depends(get_user_from_header)):
    """Return the current user's preferences (merges with defaults)."""
    return get_prefs(user.tenant_id, user.user_id)


@app.put("/api/user/preferences")
async def update_user_preferences(
    body: Dict[str, Any],
    user: UserContext = Depends(get_user_from_header),
):
    """Update user preferences (partial update — only provided keys are changed)."""
    return update_prefs(user.tenant_id, user.user_id, body)


@app.delete("/api/user/preferences")
async def reset_user_preferences(user: UserContext = Depends(get_user_from_header)):
    """Reset all user preferences to system defaults."""
    return reset_prefs(user.tenant_id, user.user_id)



# ── Test Run Viewer Endpoints ─────────────────────────────────────

@app.get("/api/admin/test-runs")
async def list_test_runs_endpoint(limit: int = 20):
    """List recent test runs from DynamoDB."""
    from .test_result_store import list_test_runs
    runs = list_test_runs(limit=limit)
    return {"runs": runs, "count": len(runs)}


@app.get("/api/admin/test-runs/{run_id}")
async def get_test_run_detail(run_id: str):
    """Get individual test results for a specific run."""
    from .test_result_store import get_test_run_results
    results = get_test_run_results(run_id)
    return {"run_id": run_id, "results": results, "count": len(results)}




@app.get("/api/feedback")
async def get_feedback(limit: int = 50, user: UserContext = Depends(get_user_from_header)):
    """List feedback for the current tenant (admin use)."""
    items = list_feedback(user.tenant_id, limit=limit)
    return {"feedback": items, "count": len(items)}



if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("APP_PORT", "8000"))
    # Bind to localhost for security - use reverse proxy for external access
    uvicorn.run(app, host="127.0.0.1", port=port)
