"""
Feedback API Router

Handles user feedback submission and retrieval:
- General feedback (with conversation snapshots)
- Per-message feedback (thumbs up/down)
- Feedback listing and summaries
"""

import base64
import json
import logging
import os
import threading
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

# ── JIRA helpers ────────────────────────────────────────────────────


def _create_jira_for_feedback(
    feedback_id: str,
    feedback_text: str,
    feedback_type: str,
    user_id: str,
    tenant_id: str,
    tier: str,
    session_id: str,
    page: str,
    created_at: str,
    feedback_area: str = "",
) -> Optional[str]:
    """Create a JIRA issue for feedback. Returns ticket key or None."""
    from ..config import jira as jira_config

    if not jira_config.feedback_enabled:
        return None

    from ..jira_client import create_feedback_issue

    summary_text = feedback_text[:80].replace("\n", " ")
    area_tag = f"[{feedback_area}]" if feedback_area else ""
    summary = f"[Feedback][{feedback_type}]{area_tag} {summary_text}"

    description = (
        f"h3. User Feedback\n"
        f"*User:* {user_id}\n"
        f"*Tenant:* {tenant_id}\n"
        f"*Page:* {page or '(none)'}\n"
        f"*Session:* {session_id[:36] if session_id else '(none)'}\n"
        f"*Feedback Type:* {feedback_type}\n"
        f"*Feedback Area:* {feedback_area or '(none)'}\n"
        f"*Timestamp:* {created_at}\n"
        f"*Feedback ID:* {feedback_id}\n\n"
        f"----\n\n"
        f"{feedback_text}\n\n"
        f"----\n\n"
        f"_Auto-created by EAGLE feedback pipeline_"
    )

    from ..config import app as app_config

    labels = ["feedback", "auto-created", app_config.environment]
    if feedback_type and feedback_type != "general":
        labels.append(feedback_type)
    if feedback_area:
        labels.append(feedback_area)

    try:
        return create_feedback_issue(
            summary=summary,
            description=description,
            labels=labels,
        )
    except Exception:
        logger.warning(
            "Failed to create JIRA issue for feedback %s", feedback_id, exc_info=True
        )
        return None

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


# ── Models ───────────────────────────────────────────────────────────


class MessageFeedbackRequest(BaseModel):
    session_id: str
    message_id: str
    feedback_type: str  # "thumbs_up" | "thumbs_down"
    comment: Optional[str] = ""


# ── Helpers ──────────────────────────────────────────────────────────


def _upload_screenshot_to_s3(feedback_id: str, data_url: str) -> Optional[str]:
    """Decode a data-URL PNG and upload to S3. Returns S3 key or None."""
    try:
        # Strip "data:image/png;base64," prefix
        header, encoded = data_url.split(",", 1)
        image_bytes = base64.b64decode(encoded)
        if len(image_bytes) > 5 * 1024 * 1024:  # 5 MB cap
            logger.warning("feedback screenshot too large (%d bytes), skipping", len(image_bytes))
            return None
        from ..db_client import get_s3
        from ..config import aws as aws_config

        s3_key = f"feedback/screenshots/{feedback_id}.png"
        get_s3().put_object(
            Bucket=aws_config.s3_bucket,
            Key=s3_key,
            Body=image_bytes,
            ContentType="image/png",
        )
        return s3_key
    except Exception:
        logger.warning("feedback: screenshot upload failed (non-fatal)", exc_info=True)
        return None


def _fetch_cloudwatch_logs_for_session(session_id: str) -> list:
    """Return up to 50 recent CloudWatch log events matching session_id (non-fatal)."""
    if not session_id:
        return []
    try:
        log_group = os.environ.get("EAGLE_TELEMETRY_LOG_GROUP", "/eagle/telemetry")
        region = os.environ.get("AWS_REGION", "us-east-1")
        import boto3
        from botocore.config import Config

        client = boto3.client(
            "logs",
            region_name=region,
            config=Config(connect_timeout=3, read_timeout=5, retries={"max_attempts": 1}),
        )
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


def _process_feedback_side_effects(
    item: dict,
    session_id: str,
    feedback_text: str,
    feedback_area: str,
    display_name: str,
    tenant_id: str,
    tier: str,
    page: str,
    feedback_type_from_body: str,
    screenshot_data: str | None,
) -> None:
    """Run all non-critical feedback side effects (CloudWatch, JIRA, S3, Teams).

    Spawned in a daemon thread — fully fire-and-forget.
    """
    feedback_id = item.get("feedback_id", "")

    # CloudWatch logs
    try:
        cloudwatch_logs = _fetch_cloudwatch_logs_for_session(session_id)
        if cloudwatch_logs:
            feedback_store.patch_cloudwatch_logs(
                feedback_id,
                tenant_id,
                json.dumps(cloudwatch_logs, default=str),
            )
    except Exception:
        logger.debug("feedback: cloudwatch patch failed (non-fatal)", exc_info=True)

    # JIRA issue
    jira_key = _create_jira_for_feedback(
        feedback_id=feedback_id,
        feedback_text=feedback_text,
        feedback_type=item.get("feedback_type", "general"),
        user_id=display_name,
        tenant_id=tenant_id,
        tier=tier,
        session_id=session_id,
        page=page,
        created_at=item.get("created_at", ""),
        feedback_area=feedback_area,
    )

    # Screenshot → S3 + JIRA attachment
    screenshot_url: Optional[str] = None
    if screenshot_data and isinstance(screenshot_data, str):
        s3_key = _upload_screenshot_to_s3(feedback_id, screenshot_data)
        if s3_key:
            try:
                from ..db_client import get_s3
                from ..config import aws as aws_config

                screenshot_url = get_s3().generate_presigned_url(
                    "get_object",
                    Params={"Bucket": aws_config.s3_bucket, "Key": s3_key},
                    ExpiresIn=7 * 24 * 3600,
                )
            except Exception:
                logger.debug("feedback: presigned URL failed (non-fatal)", exc_info=True)
            if jira_key:
                try:
                    image_bytes = base64.b64decode(screenshot_data.split(",", 1)[1])
                    from ..jira_client import add_attachment

                    add_attachment(jira_key, f"feedback-{feedback_id[:8]}.png", image_bytes)
                except Exception:
                    logger.debug("feedback: jira attachment failed (non-fatal)", exc_info=True)

    # Teams notification
    notify_feedback(
        tenant_id=tenant_id,
        user_id=display_name,
        tier=tier,
        session_id=session_id,
        feedback_text=feedback_text,
        feedback_type=feedback_type_from_body,
        feedback_area=feedback_area,
        page=page,
        jira_key=jira_key,
        feedback_id=feedback_id,
        screenshot_url=screenshot_url,
    )


@router.post("")
async def api_submit_feedback(
    request: Request,
    user: UserContext = Depends(get_user_from_header),
):
    """Record user feedback with conversation snapshot and recent CloudWatch logs."""
    body = await request.json()
    session_id = body.get("session_id", "")
    feedback_text = body.get("feedback_text", "").strip()
    feedback_area = body.get("feedback_area", "") or ""
    conversation_snapshot = body.get("conversation_snapshot", [])
    page = body.get("page", "")
    last_message_id = body.get("last_message_id", "")

    if not feedback_text:
        raise HTTPException(status_code=400, detail="feedback_text is required")

    display_name = user.email or user.username or user.user_id

    # Critical path: DynamoDB write only — returns fast.
    item = feedback_store.write_feedback(
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        tier=user.tier,
        session_id=session_id,
        feedback_text=feedback_text,
        conversation_snapshot=json.dumps(conversation_snapshot, default=str),
        cloudwatch_logs="[]",
        page=page,
        last_message_id=last_message_id,
        feedback_area=feedback_area,
    )

    # Fire-and-forget: daemon thread for all slow side effects.
    threading.Thread(
        target=_process_feedback_side_effects,
        kwargs=dict(
            item=item,
            session_id=session_id,
            feedback_text=feedback_text,
            feedback_area=feedback_area,
            display_name=display_name,
            tenant_id=user.tenant_id,
            tier=user.tier,
            page=page,
            feedback_type_from_body=body.get("feedback_type", "general"),
            screenshot_data=body.get("screenshot"),
        ),
        daemon=True,
    ).start()

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
