"""
Sessions API Router

Provides endpoints for session management:
- List/create/get/update/delete sessions
- Get session messages
"""

import os
import uuid
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..cognito_auth import UserContext
from ..session_store import (
    create_session as eagle_create_session,
    get_session as eagle_get_session,
    update_session as eagle_update_session,
    delete_session as eagle_delete_session,
    list_sessions as eagle_list_sessions,
    get_messages,
)
from .dependencies import get_user_from_header, get_session_context

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

# Feature flags
USE_PERSISTENT_SESSIONS = os.getenv("USE_PERSISTENT_SESSIONS", "true").lower() == "true"

# In-memory session store (fallback when persistent sessions disabled)
# Shared with main.py - will be set via set_sessions_ref()
_SESSIONS: Dict[str, List[dict]] = {}


def set_sessions_ref(sessions_dict: Dict[str, List[dict]]):
    """Set reference to sessions dict from main.py for in-memory fallback."""
    global _SESSIONS
    _SESSIONS = sessions_dict


# ── Models ───────────────────────────────────────────────────────────


class UpdateSessionRequest(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None
    metadata: Optional[Dict] = None


# ── Endpoints ────────────────────────────────────────────────────────


@router.get("")
async def api_list_sessions(
    limit: int = 50,
    user: UserContext = Depends(get_user_from_header),
):
    """List sessions for the current user."""
    tenant_id, user_id, _ = get_session_context(user)

    if USE_PERSISTENT_SESSIONS:
        sessions = eagle_list_sessions(tenant_id, user_id, limit)
    else:
        sessions = []
        for sid, msgs in _SESSIONS.items():
            user_msgs = [m for m in msgs if m.get("role") == "user"]
            first_msg = user_msgs[0]["content"][:60] if user_msgs else "Empty"
            sessions.append({
                "session_id": sid,
                "message_count": len(msgs),
                "preview": first_msg,
            })

    return {"sessions": sessions, "count": len(sessions)}


@router.post("")
async def api_create_session(
    title: Optional[str] = None,
    user: UserContext = Depends(get_user_from_header),
):
    """Create a new session."""
    tenant_id, user_id, _ = get_session_context(user)

    if USE_PERSISTENT_SESSIONS:
        session = eagle_create_session(tenant_id, user_id, title=title)
    else:
        session_id = str(uuid.uuid4())
        _SESSIONS[session_id] = []
        session = {"session_id": session_id, "title": title or "New Conversation"}

    return session


@router.get("/{session_id}")
async def api_get_session(
    session_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Get session details."""
    tenant_id, user_id, _ = get_session_context(user)

    if USE_PERSISTENT_SESSIONS:
        session = eagle_get_session(session_id, tenant_id, user_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return session
    else:
        if session_id not in _SESSIONS:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"session_id": session_id, "message_count": len(_SESSIONS[session_id])}


@router.patch("/{session_id}")
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
        if session_id not in _SESSIONS:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"session_id": session_id, "updated": True, **updates}


@router.delete("/{session_id}")
async def api_delete_session(
    session_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Delete a session."""
    tenant_id, user_id, _ = get_session_context(user)

    if USE_PERSISTENT_SESSIONS:
        success = eagle_delete_session(session_id, tenant_id, user_id)
        if not success:
            raise HTTPException(status_code=404, detail="Session not found")
    else:
        if session_id in _SESSIONS:
            del _SESSIONS[session_id]
        else:
            raise HTTPException(status_code=404, detail="Session not found")

    return {"status": "deleted", "session_id": session_id}


@router.get("/{session_id}/messages")
async def api_get_messages(
    session_id: str,
    limit: int = 100,
    user: UserContext = Depends(get_user_from_header),
):
    """Get messages for a session."""
    tenant_id, user_id, _ = get_session_context(user)

    if USE_PERSISTENT_SESSIONS:
        messages = get_messages(session_id, tenant_id, user_id, limit)
    else:
        if session_id not in _SESSIONS:
            raise HTTPException(status_code=404, detail="Session not found")
        messages = _SESSIONS[session_id][-limit:]

    return {"session_id": session_id, "messages": messages}


@router.get("/{session_id}/context")
async def api_get_session_context(
    session_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Return preloaded context for a session."""
    tenant_id, user_id, _ = get_session_context(user)

    package_id = None
    if USE_PERSISTENT_SESSIONS:
        session = eagle_get_session(session_id, tenant_id, user_id)
        if session:
            meta = session.get("metadata") or {}
            package_id = meta.get("active_package_id")

    from ..session_preloader import preload_session_context

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
