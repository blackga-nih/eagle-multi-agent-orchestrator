"""
Langfuse REST API client for the EAGLE admin traces dashboard.

Queries traces and observations from Langfuse Cloud so the admin UI
can display the same data visible at us.cloud.langfuse.com.

Also provides error classification and trace tagging so errors can be
filtered by category in the Langfuse dashboard (e.g. Tag: severity:infra,
Tag: error:sso-expired).

Requires LANGFUSE_PUBLIC_KEY + LANGFUSE_SECRET_KEY env vars.
"""
import asyncio
import base64
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger("eagle.telemetry.langfuse_client")

_LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "https://us.cloud.langfuse.com")


def _auth_header() -> Optional[str]:
    """Build Basic auth header from env vars. Returns None if not configured."""
    pub = os.getenv("LANGFUSE_PUBLIC_KEY")
    sec = os.getenv("LANGFUSE_SECRET_KEY")
    if not pub or not sec:
        return None
    return "Basic " + base64.b64encode(f"{pub}:{sec}".encode()).decode()


async def list_traces(
    *,
    limit: int = 50,
    page: int = 1,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    tags: Optional[List[str]] = None,
    from_timestamp: Optional[str] = None,
    to_timestamp: Optional[str] = None,
    order_by: str = "timestamp",
    order: str = "DESC",
    name: Optional[str] = None,
) -> Dict[str, Any]:
    """Fetch paginated trace list from Langfuse public API.

    Returns {"data": [...], "meta": {"page": N, "limit": N, "totalItems": N, "totalPages": N}}
    """
    auth = _auth_header()
    if not auth:
        return {"data": [], "meta": {"page": 1, "limit": limit, "totalItems": 0, "totalPages": 0},
                "error": "Langfuse credentials not configured"}

    params: Dict[str, Any] = {"limit": limit, "page": page, "orderBy": order_by, "order": order}
    if user_id:
        params["userId"] = user_id
    if session_id:
        params["sessionId"] = session_id
    if name:
        params["name"] = name
    if from_timestamp:
        params["fromTimestamp"] = from_timestamp
    if to_timestamp:
        params["toTimestamp"] = to_timestamp
    if tags:
        params["tags"] = tags

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{_LANGFUSE_HOST}/api/public/traces",
                params=params,
                headers={"Authorization": auth},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.error("Langfuse list_traces failed: %s", exc)
        return {"data": [], "meta": {"page": 1, "limit": limit, "totalItems": 0, "totalPages": 0},
                "error": str(exc)}


async def get_trace(trace_id: str) -> Optional[Dict[str, Any]]:
    """Fetch a single trace by ID from Langfuse."""
    auth = _auth_header()
    if not auth:
        return None

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{_LANGFUSE_HOST}/api/public/traces/{trace_id}",
                headers={"Authorization": auth},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.error("Langfuse get_trace(%s) failed: %s", trace_id, exc)
        return None


async def list_observations(
    *,
    trace_id: Optional[str] = None,
    limit: int = 100,
    page: int = 1,
    type: Optional[str] = None,
) -> Dict[str, Any]:
    """Fetch observations (spans/generations) from Langfuse.

    type can be: "GENERATION", "SPAN", "EVENT"
    """
    auth = _auth_header()
    if not auth:
        return {"data": [], "meta": {"page": 1, "limit": limit, "totalItems": 0, "totalPages": 0}}

    params: Dict[str, Any] = {"limit": limit, "page": page}
    if trace_id:
        params["traceId"] = trace_id
    if type:
        params["type"] = type

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{_LANGFUSE_HOST}/api/public/observations",
                params=params,
                headers={"Authorization": auth},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.error("Langfuse list_observations failed: %s", exc)
        return {"data": [], "meta": {"page": 1, "limit": limit, "totalItems": 0, "totalPages": 0},
                "error": str(exc)}


def langfuse_trace_url(trace_id: str) -> str:
    """Build the Langfuse UI URL for a trace."""
    project_id = os.getenv("LANGFUSE_PROJECT_ID", "")
    if project_id:
        return f"{_LANGFUSE_HOST}/project/{project_id}/traces/{trace_id}"
    return f"{_LANGFUSE_HOST}/traces/{trace_id}"


# ---------------------------------------------------------------------------
# Error classification + trace tagging
# Ported from nci-webtools-ctri-arti/gateway/langfuse.js classifyError()
# ---------------------------------------------------------------------------

_ERROR_PATTERNS: List[Tuple[re.Pattern, str, str]] = [
    (re.compile(r"token has expired|refresh failed|ExpiredToken", re.I), "sso-expired", "infra"),
    (re.compile(r"UnrecognizedClientException|InvalidIdentityToken", re.I), "credentials-invalid", "infra"),
    (re.compile(r"ThrottlingException|rate limit|too many requests", re.I), "throttled", "infra"),
    (re.compile(r"ModelNotReadyException|cold start", re.I), "model-cold-start", "infra"),
    (re.compile(r"AccessDeniedException|not authorized|forbidden", re.I), "access-denied", "infra"),
    # model-not-found must precede network-error (ResourceNotFoundException contains "eNotFound")
    (re.compile(r"ResourceNotFoundException|model.*not found", re.I), "model-not-found", "config"),
    (re.compile(r"ECONNREFUSED|ECONNRESET|ETIMEDOUT|\bENOTFOUND\b|EPIPE|ConnectionReset", re.I), "network-error", "infra"),
    (re.compile(r"socket hang up|fetch failed|abort|ConnectionError", re.I), "network-error", "infra"),
    (re.compile(r"CERT_|certificate|TLS|SSL", re.I), "tls-error", "infra"),
    (re.compile(r"ValidationException", re.I), "validation-error", "app"),
]


def classify_error(message: str) -> Dict[str, str]:
    """Categorize an error message for Langfuse tagging/filtering.

    Returns {"category": "...", "severity": "..."} where severity is
    "infra" (network/auth), "config" (misconfiguration), or "app" (logic).

    In Langfuse you can filter by:
      - Tag: severity:infra  → see (or exclude) all network/infra errors
      - Tag: error:sso-expired → see just SSO expiry errors
    """
    if not message:
        return {"category": "unknown", "severity": "app"}
    for pattern, category, severity in _ERROR_PATTERNS:
        if pattern.search(message):
            return {"category": category, "severity": severity}
    return {"category": "unknown", "severity": "app"}


async def _find_latest_trace_id(session_id: str) -> Optional[str]:
    """Find the most recent trace ID for a session."""
    result = await list_traces(limit=1, session_id=session_id)
    traces = result.get("data", [])
    if traces:
        return traces[0].get("id")
    return None


async def update_trace(trace_id: str, *, tags: Optional[List[str]] = None,
                       metadata: Optional[Dict[str, Any]] = None) -> bool:
    """Update a Langfuse trace with tags and/or metadata via REST API."""
    auth = _auth_header()
    if not auth:
        return False

    body: Dict[str, Any] = {}
    if tags is not None:
        body["tags"] = tags
    if metadata is not None:
        body["metadata"] = metadata
    if not body:
        return False

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.patch(
                f"{_LANGFUSE_HOST}/api/public/traces/{trace_id}",
                json=body,
                headers={"Authorization": auth, "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            return True
    except Exception as exc:
        logger.warning("Langfuse update_trace(%s) failed: %s", trace_id, exc)
        return False


async def tag_trace_error(
    session_id: str,
    error_message: str,
    *,
    trace_id: Optional[str] = None,
    source: str = "sm-eagle",
) -> None:
    """Classify an error and tag the Langfuse trace for filtering.

    If trace_id is not provided, looks up the latest trace for the session.
    Fire-and-forget — errors are logged but never raised.
    """
    try:
        info = classify_error(error_message)

        tid = trace_id
        if not tid and session_id:
            tid = await _find_latest_trace_id(session_id)
        if not tid:
            logger.debug("tag_trace_error: no trace found for session=%s", session_id)
            return

        tags = [
            source,
            f"error:{info['category']}",
            f"severity:{info['severity']}",
        ]
        metadata = {
            "errorCategory": info["category"],
            "errorSeverity": info["severity"],
            "errorMessage": error_message[:500] if error_message else "",
        }
        await update_trace(tid, tags=tags, metadata=metadata)
        logger.info(
            "Tagged trace %s with error:%s severity:%s",
            tid, info["category"], info["severity"],
        )
    except Exception as exc:
        logger.warning("tag_trace_error failed: %s", exc)


def notify_trace_error(
    session_id: str,
    error_message: str,
    *,
    trace_id: Optional[str] = None,
) -> None:
    """Fire-and-forget wrapper for tag_trace_error (called from sync context)."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(tag_trace_error(
            session_id, error_message, trace_id=trace_id,
        ))
    except RuntimeError:
        pass
