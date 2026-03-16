"""Session management endpoints."""

import uuid
import logging
from typing import Optional, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..cognito_auth import UserContext
from ..stores.session_store import (
    create_session as eagle_create_session, get_session as eagle_get_session,
    update_session as eagle_update_session, delete_session as eagle_delete_session,
    list_sessions as eagle_list_sessions,
    get_messages,
)
from ._deps import get_user_from_header, get_session_context, USE_PERSISTENT_SESSIONS
from .chat import SESSIONS  # shared in-memory fallback

logger = logging.getLogger("eagle")
router = APIRouter(tags=["sessions"])


class UpdateSessionRequest(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None
    metadata: Optional[Dict] = None


@router.get("/api/sessions")
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


@router.post("/api/sessions")
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


@router.get("/api/sessions/{session_id}")
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


@router.patch("/api/sessions/{session_id}")
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
        return {"session_id": session_id, **updates}


@router.delete("/api/sessions/{session_id}")
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


@router.get("/api/sessions/{session_id}/messages")
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


@router.get("/api/sessions/{session_id}/summary")
async def api_get_session_summary(
    session_id: str,
    user: UserContext = Depends(get_user_from_header)
):
    """Lightweight session overview — title, count, last_active, tools used."""
    tenant_id, user_id, _ = get_session_context(user)

    if USE_PERSISTENT_SESSIONS:
        session = eagle_get_session(session_id, tenant_id, user_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        messages = get_messages(session_id, tenant_id, user_id, limit=200)
    else:
        if session_id not in SESSIONS:
            raise HTTPException(status_code=404, detail="Session not found")
        msgs = SESSIONS[session_id]
        session = {"title": None, "message_count": len(msgs), "updated_at": None}
        messages = []

    tools_used: set = set()
    for msg in messages:
        for ev in (msg.get("metadata") or {}).get("audit_logs", []):
            if ev.get("type") == "tool_use" and ev.get("tool_use", {}).get("name"):
                tools_used.add(ev["tool_use"]["name"])
    return {
        "session_id": session_id,
        "title": session.get("title"),
        "message_count": session.get("message_count", len(messages)),
        "last_active": session.get("updated_at"),
        "tools_used": sorted(tools_used),
    }


@router.delete("/api/sessions/{session_id}/messages")
async def api_clear_messages(
    session_id: str,
    user: UserContext = Depends(get_user_from_header)
):
    """Delete all messages for a session without deleting the session itself."""
    tenant_id, user_id, _ = get_session_context(user)

    if not USE_PERSISTENT_SESSIONS:
        if session_id not in SESSIONS:
            raise HTTPException(status_code=404, detail="Session not found")
        count = len(SESSIONS[session_id])
        SESSIONS[session_id] = []
        return {"status": "cleared", "session_id": session_id, "deleted_count": count}

    from ..stores.session_store import _get_table
    table = _get_table()
    response = table.query(
        KeyConditionExpression="PK = :pk AND begins_with(SK, :sk_prefix)",
        ExpressionAttributeValues={
            ":pk": f"SESSION#{tenant_id}#{user_id}",
            ":sk_prefix": f"MSG#{session_id}#",
        },
        ProjectionExpression="PK, SK",
    )
    items = response.get("Items", [])
    with table.batch_writer() as batch:
        for item in items:
            batch.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})
    return {"status": "cleared", "session_id": session_id, "deleted_count": len(items)}


@router.get("/api/sessions/{session_id}/documents")
async def api_get_session_documents(
    session_id: str,
    user: UserContext = Depends(get_user_from_header)
):
    """Extract document tool_results from persisted audit_logs for a session."""
    tenant_id, user_id, _ = get_session_context(user)

    if USE_PERSISTENT_SESSIONS:
        messages = get_messages(session_id, tenant_id, user_id, limit=200)
    else:
        if session_id not in SESSIONS:
            raise HTTPException(status_code=404, detail="Session not found")
        messages = []  # in-memory sessions have no audit_log metadata

    docs = []
    for msg in messages:
        for ev in (msg.get("metadata") or {}).get("audit_logs", []):
            if ev.get("type") == "tool_result":
                r = ev.get("tool_result", {})
                if r.get("name") in ("create_document", "generate_document"):
                    docs.append({"timestamp": ev.get("timestamp"), **r.get("result", {})})
    return {"session_id": session_id, "documents": docs}


@router.get("/api/sessions/{session_id}/audit-logs")
async def api_get_audit_logs(
    session_id: str,
    user: UserContext = Depends(get_user_from_header)
):
    """Return persisted SSE audit events for a session (all turns combined)."""
    tenant_id, user_id, _ = get_session_context(user)
    messages = get_messages(session_id, tenant_id, user_id, limit=200)
    events: list = []
    for msg in messages:
        logs = (msg.get("metadata") or {}).get("audit_logs", [])
        if isinstance(logs, list):
            events.extend(logs)
    return {"session_id": session_id, "events": events}
