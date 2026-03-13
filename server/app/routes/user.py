"""User endpoints — profile, usage, preferences, feedback."""

import os
import json
import time
import logging
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from ..cognito_auth import UserContext
from ..stores.session_store import get_usage_summary
from ..stores.pref_store import get_prefs, update_prefs, reset_prefs
from ..stores import feedback_store
from ..stores.feedback_store import list_feedback
from ._deps import get_user_from_header

logger = logging.getLogger("eagle")
router = APIRouter(tags=["user"])


# ── User Profile & Usage ─────────────────────────────────────────────

@router.get("/api/user/me")
async def api_user_me(user: UserContext = Depends(get_user_from_header)):
    """Get current user info."""
    return user.to_dict()


@router.get("/api/user/usage")
async def api_user_usage(
    days: int = 30,
    user: UserContext = Depends(get_user_from_header)
):
    """Get usage summary for current user."""
    tenant_id = user.tenant_id
    return get_usage_summary(tenant_id, days)


# ── Feedback ──────────────────────────────────────────────────────────

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


@router.post("/api/feedback")
async def api_submit_feedback(
    request: Request,
    user: UserContext = Depends(get_user_from_header),
):
    """Record user feedback with conversation snapshot and recent CloudWatch logs."""
    body = await request.json()
    session_id = body.get("session_id", "")
    # Accept "comment" (frontend field) or "feedback_text" (legacy/rich client)
    feedback_text = (body.get("comment") or body.get("feedback_text") or "").strip()
    feedback_type = body.get("feedback_type")
    rating = body.get("rating", 0)
    conversation_snapshot = body.get("conversation_snapshot", [])
    page = body.get("page", "")
    last_message_id = body.get("last_message_id", "")

    if rating and not (0 <= int(rating) <= 5):
        raise HTTPException(status_code=400, detail="rating must be between 0 and 5")

    cloudwatch_logs = _fetch_cloudwatch_logs_for_session(session_id)

    item = feedback_store.write_feedback(
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        tier=user.tier,
        session_id=session_id,
        feedback_text=feedback_text,
        feedback_type=feedback_type,
        conversation_snapshot=json.dumps(conversation_snapshot, default=str),
        cloudwatch_logs=json.dumps(cloudwatch_logs, default=str),
        page=page,
        last_message_id=last_message_id,
    )

    # CloudWatch: emit feedback.submitted (fire-and-forget)
    try:
        from ..telemetry.cloudwatch_emitter import emit_feedback_submitted
        emit_feedback_submitted(
            tenant_id=user.tenant_id,
            user_id=user.user_id,
            session_id=session_id or "",
            feedback_type=item.get("feedback_type", "general"),
            feedback_id=item.get("feedback_id", ""),
        )
    except Exception:
        logger.debug("feedback.submitted emission failed (non-fatal)")

    return {
        "status": "ok",
        "message": "Feedback recorded. Thank you!",
        "feedback_id": item.get("feedback_id"),
        "feedback_type": item.get("feedback_type"),
        "created_at": item.get("created_at"),
    }


@router.get("/api/feedback")
async def get_feedback(limit: int = 50, user: UserContext = Depends(get_user_from_header)):
    """List feedback for the current tenant (admin use)."""
    items = list_feedback(user.tenant_id, limit=limit)
    return {"feedback": items, "count": len(items)}


# ── User Preferences ─────────────────────────────────────────────────

@router.get("/api/user/preferences")
async def get_user_preferences(user: UserContext = Depends(get_user_from_header)):
    """Return the current user's preferences (merges with defaults)."""
    return get_prefs(user.tenant_id, user.user_id)


@router.put("/api/user/preferences")
async def update_user_preferences(
    body: Dict[str, Any],
    user: UserContext = Depends(get_user_from_header),
):
    """Update user preferences (partial update — only provided keys are changed)."""
    return update_prefs(user.tenant_id, user.user_id, body)


@router.delete("/api/user/preferences")
async def reset_user_preferences(user: UserContext = Depends(get_user_from_header)):
    """Reset all user preferences to system defaults."""
    return reset_prefs(user.tenant_id, user.user_id)
