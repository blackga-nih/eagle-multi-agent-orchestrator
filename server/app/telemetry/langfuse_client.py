"""
Langfuse REST API client for the EAGLE admin traces dashboard.

Queries traces and observations from Langfuse Cloud so the admin UI
can display the same data visible at us.cloud.langfuse.com.

Requires LANGFUSE_PUBLIC_KEY + LANGFUSE_SECRET_KEY env vars.
"""
import base64
import logging
import os
from typing import Any, Dict, List, Optional

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
