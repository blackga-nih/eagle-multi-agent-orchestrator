"""Frontend error reporting endpoint.

Accepts a structured error payload from the client (ErrorBoundary,
window.onerror, unhandledrejection) and forwards it to the debug
Teams channel via ``notify_debug_event``.

Never the source of truth for what constitutes an error — the frontend
decides to POST; the backend just relays. Same rate-limit bucket as
every other debug-channel event.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, field_validator

from ..error_webhook import notify_debug_event

logger = logging.getLogger("eagle.routers.errors")

router = APIRouter(prefix="/api/errors", tags=["errors"])


# Max accepted body size for a single report. Guards against a runaway
# React loop POSTing a multi-megabyte stack trace.
_MAX_REPORT_BYTES = 50_000


class FrontendErrorReport(BaseModel):
    """Payload shape for POST /api/errors/report.

    ``source`` identifies where the error was captured on the client:
      - ``react_error_boundary``  — ErrorBoundary.componentDidCatch
      - ``window_error``          — window.addEventListener('error', …)
      - ``unhandled_rejection``   — window.addEventListener('unhandledrejection', …)
    Any other value is accepted but gets passed through verbatim.
    """

    source: str = Field(..., max_length=64)
    error_type: str = Field(default="", max_length=200)
    message: str = Field(..., min_length=1, max_length=4000)
    stack: Optional[str] = Field(default=None, max_length=8000)
    component_stack: Optional[str] = Field(default=None, max_length=8000)
    path: Optional[str] = Field(default=None, max_length=512)
    user_agent: Optional[str] = Field(default=None, max_length=512)

    @field_validator("source")
    @classmethod
    def _trim_source(cls, v: str) -> str:
        return (v or "").strip() or "unknown"


@router.post(
    "/report",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Forward a client-side error to the debug Teams channel",
)
async def report_error(
    request: Request,
    report: FrontendErrorReport = Body(...),
) -> Response:
    # Size guard. FastAPI already parsed JSON by now, but reject anyway
    # when the body was large — pydantic's per-field caps above cover
    # the common case; this catches an explosion of small fields.
    try:
        body_len = int(request.headers.get("content-length") or 0)
    except (TypeError, ValueError):
        body_len = 0
    if body_len > _MAX_REPORT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Error report too large (>{_MAX_REPORT_BYTES} bytes)",
        )

    context: dict = {
        "path": report.path or "",
        "user_agent": report.user_agent or request.headers.get("user-agent", ""),
    }
    if report.stack:
        context["stack"] = report.stack
    if report.component_stack:
        context["component_stack"] = report.component_stack

    try:
        notify_debug_event(
            source=report.source,
            error_type=report.error_type or "FrontendError",
            message=report.message,
            context=context,
            status_code=400,
            path=report.path or "/",
            method="CLIENT",
        )
    except Exception:
        # Never break the client — swallow and log.
        logger.warning("report_error: notify_debug_event failed", exc_info=True)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
