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

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Header, Response
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
from .agentic_service import stream_chat, get_client, MODEL, EAGLE_TOOLS
from .document_export import export_document
from .session_store import (
    create_session as eagle_create_session, get_session as eagle_get_session,
    update_session as eagle_update_session, delete_session as eagle_delete_session,
    list_sessions as eagle_list_sessions,
    add_message, get_messages, get_messages_for_anthropic, record_usage, get_usage_summary
)
from .cognito_auth import (
    UserContext, extract_user_context,
    DEV_MODE, DEV_USER_ID, DEV_TENANT_ID
)
from .admin_service import (
    get_dashboard_stats, get_user_stats, get_top_users, get_tool_usage,
    record_request_cost, check_rate_limit, calculate_cost
)

# Existing multi-tenant modules (preserved)
from .models import ChatMessage, ChatResponse, TenantContext, UsageMetric, SubscriptionTier
from .dynamodb_store import DynamoDBStore
from .auth import get_current_user
from .subscription_service import SubscriptionService
from .cost_attribution import CostAttributionService
from .admin_cost_service import AdminCostService
from .admin_auth import get_admin_user, verify_tenant_admin, AdminAuthService
from .streaming_routes import create_streaming_router

# ── Logging ──────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("eagle")

app = FastAPI(
    title="EAGLE – NCI Acquisition Assistant",
    version="4.0.0",
    description="Multi-tenant acquisition intake system with Anthropic SDK, auth, persistence, and analytics"
)

# ── CORS Middleware ──────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Feature Flags ────────────────────────────────────────────────────
USE_PERSISTENT_SESSIONS = os.getenv("USE_PERSISTENT_SESSIONS", "true").lower() == "true"
REQUIRE_AUTH = os.getenv("REQUIRE_AUTH", "false").lower() == "true"

# ── Initialize existing services ─────────────────────────────────────
store = DynamoDBStore()
subscription_service = SubscriptionService(store)
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

    try:
        result = await stream_chat(messages, session_id=session_id)

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
        logger.error("REST chat error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


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
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Export error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


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
    except Exception as e:
        logger.error("Session export error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ── S3 Document Browser ──────────────────────────────────────────────

@app.get("/api/documents")
async def api_list_documents(user: UserContext = Depends(get_user_from_header)):
    """List documents in S3 for the current user."""
    import boto3
    from botocore.exceptions import ClientError

    tenant_id = user.tenant_id
    user_id = user.user_id
    bucket = os.getenv("S3_BUCKET", "nci-documents")
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
        logger.error("S3 list error: %s", e)
        return {"documents": [], "error": str(e)}


@app.get("/api/documents/{doc_key:path}")
async def api_get_document(doc_key: str, user: UserContext = Depends(get_user_from_header)):
    """Get document content from S3."""
    import boto3
    from botocore.exceptions import ClientError

    tenant_id = user.tenant_id
    user_id = user.user_id
    bucket = os.getenv("S3_BUCKET", "nci-documents")

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
        raise HTTPException(status_code=500, detail=str(e))


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

                result = await stream_chat(
                    messages,
                    on_text=on_text,
                    on_tool_use=on_tool_use,
                    on_tool_result=on_tool_result,
                    session_id=session_id,
                )

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
                await ws.send_json({"type": "error", "message": str(e)})

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: %s", default_session_id)
    except Exception as e:
        logger.error("WebSocket error: %s", e)
        try:
            await ws.send_json({"type": "error", "message": str(e)})
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
    return store.get_tenant_usage(tenant_id)


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
        "sessions": store.get_tenant_sessions(tenant_id)
    }


@app.get("/api/tenants/{tenant_id}/analytics")
async def get_tenant_analytics(tenant_id: str, current_user: dict = Depends(get_current_user)):
    """Get enhanced analytics with trace data for authenticated tenant"""
    if tenant_id != current_user["tenant_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    usage_data = store.get_tenant_usage(tenant_id)
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
        raise HTTPException(status_code=500, detail=f"Failed to add user to admin group: {str(e)}")


# ══════════════════════════════════════════════════════════════════════
# SSE STREAMING ROUTER (preserved from C3 integration)
# ══════════════════════════════════════════════════════════════════════

# Include SSE streaming router - uses EAGLE agentic_service now
streaming_router = create_streaming_router(store, subscription_service)
app.include_router(streaming_router)


# ══════════════════════════════════════════════════════════════════════
# HEALTH CHECK (frontend now served by Next.js on port 3000)
# ══════════════════════════════════════════════════════════════════════

@app.get("/api/health")
async def health_check():
    """Backend health check endpoint."""
    return {
        "status": "healthy",
        "service": "eagle-backend",
        "version": "4.0.0",
        "timestamp": datetime.utcnow().isoformat(),
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("APP_PORT", "8000"))
    # Bind to localhost for security - use reverse proxy for external access
    uvicorn.run(app, host="127.0.0.1", port=port)
