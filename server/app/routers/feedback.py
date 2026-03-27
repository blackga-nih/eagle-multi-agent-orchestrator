"""
Feedback API Router

Handles user feedback submission and retrieval:
- General feedback (with conversation snapshots)
- Per-message feedback (thumbs up/down)
- Feedback listing and summaries
"""

import json
import logging
import os
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..cognito_auth import UserContext
from .. import feedback_store
from ..feedback_store import (
    list_feedback,
    list_message_feedback,
    get_message_feedback_summary,
)
from ..teams_notifier import notify_feedback
from .dependencies import get_user_from_header

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


# ── Models ───────────────────────────────────────────────────────────


class MessageFeedbackRequest(BaseModel):
    session_id: str
    message_id: str
    feedback_type: str  # "thumbs_up" | "thumbs_down"
    comment: Optional[str] = ""


# ── Helpers ──────────────────────────────────────────────────────────


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


# ── Endpoints ────────────────────────────────────────────────────────


@router.post("")
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


@router.post("/message")
async def api_submit_message_feedback(
    req: MessageFeedbackRequest,
    user: UserContext = Depends(get_user_from_header),
):
    """Record thumbs up/down feedback for a specific message."""
    if req.feedback_type not in ("thumbs_up", "thumbs_down"):
        raise HTTPException(
            status_code=400,
            detail="feedback_type must be 'thumbs_up' or 'thumbs_down'",
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


@router.get("")
async def get_feedback_list(
    limit: int = 50,
    user: UserContext = Depends(get_user_from_header),
):
    """List feedback for the current tenant (admin use)."""
    items = list_feedback(user.tenant_id, limit=limit)
    return {"feedback": items, "count": len(items)}


@router.get("/messages")
async def get_message_feedback_list(
    limit: int = 100,
    user: UserContext = Depends(get_user_from_header),
):
    """List per-message feedback for the current tenant."""
    items = list_message_feedback(user.tenant_id, limit=limit)
    return {"feedback": items, "count": len(items)}


@router.get("/messages/summary")
async def get_message_feedback_summary_endpoint(
    user: UserContext = Depends(get_user_from_header),
):
    """Get aggregate message feedback stats."""
    summary = get_message_feedback_summary(user.tenant_id)
    return summary
