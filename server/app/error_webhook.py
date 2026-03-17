"""
Error webhook for EAGLE API endpoints.

Fires a structured JSON payload to a configurable webhook URL on every
5xx error. Supports both standard exception-handler errors and in-stream
SSE errors. Fire-and-forget — telemetry never breaks the main flow.

Config via environment variables:
    ERROR_WEBHOOK_URL          — target URL (Azure Logic App, Slack, etc.)
    ERROR_WEBHOOK_ENABLED      — master on/off (default: "true")
    ERROR_WEBHOOK_TIMEOUT      — POST timeout in seconds (default: "5.0")
    ERROR_WEBHOOK_RATE_LIMIT   — max calls per minute (default: "10")
    ERROR_WEBHOOK_INCLUDE_TRACEBACK — include traceback (default: "true")
    ERROR_WEBHOOK_MIN_STATUS   — minimum status code to trigger (default: "500")
    ERROR_WEBHOOK_EXCLUDE_PATHS — comma-separated paths to skip (default: "/api/health")
"""

import asyncio
import logging
import os
import time
import traceback as tb_module
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import Request

from .telemetry.log_context import _tenant_id, _user_id, _session_id

logger = logging.getLogger("eagle.error_webhook")

# ── Configuration ────────────────────────────────────────────────────

WEBHOOK_URL: str = os.getenv(
    "ERROR_WEBHOOK_URL",
    "https://prod-52.usgovtexas.logic.azure.us:443/workflows/8705df58d766420d8847222b1b12d7a0/triggers/manual/paths/invoke?api-version=2016-06-01&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=Xo4vpYNBYWWdyreboIYnBJtGlO3cNRLSEakEcNGWBoM",
)
WEBHOOK_ENABLED: bool = os.getenv("ERROR_WEBHOOK_ENABLED", "true").lower() == "true"
WEBHOOK_TIMEOUT: float = float(os.getenv("ERROR_WEBHOOK_TIMEOUT", "5.0"))
RATE_LIMIT: int = int(os.getenv("ERROR_WEBHOOK_RATE_LIMIT", "10"))
INCLUDE_TRACEBACK: bool = os.getenv("ERROR_WEBHOOK_INCLUDE_TRACEBACK", "true").lower() == "true"
MIN_STATUS: int = int(os.getenv("ERROR_WEBHOOK_MIN_STATUS", "500"))
EXCLUDE_PATHS: list[str] = [
    p.strip() for p in os.getenv("ERROR_WEBHOOK_EXCLUDE_PATHS", "/api/health").split(",") if p.strip()
]
ENVIRONMENT: str = os.getenv("EAGLE_ENVIRONMENT", os.getenv("ENVIRONMENT", "dev"))


# ── Token-bucket rate limiter ────────────────────────────────────────

class _TokenBucket:
    """Simple token-bucket rate limiter (not thread-safe — fine for asyncio)."""

    def __init__(self, capacity: int):
        self.capacity = max(capacity, 1)
        self.tokens = float(self.capacity)
        self.refill_interval = 60.0 / self.capacity  # seconds per token
        self._last_refill = time.monotonic()

    def consume(self) -> bool:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._last_refill = now
        self.tokens = min(self.capacity, self.tokens + elapsed / self.refill_interval)
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False


_rate_limiter = _TokenBucket(RATE_LIMIT)

# ── httpx.AsyncClient (lazy-init) ───────────────────────────────────

_client: Optional[httpx.AsyncClient] = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            limits=httpx.Limits(max_connections=5),
            timeout=httpx.Timeout(WEBHOOK_TIMEOUT),
        )
    return _client


async def close_webhook_client() -> None:
    """Close the httpx client. Call from app shutdown."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


# ── Filtering ────────────────────────────────────────────────────────

def _should_report(status_code: int, path: str) -> bool:
    if status_code < MIN_STATUS:
        return False
    if path in EXCLUDE_PATHS:
        return False
    return True


# ── Core send ────────────────────────────────────────────────────────

async def send_error_webhook(payload: dict) -> None:
    """POST payload to webhook URL. Fire-and-forget — never raises."""
    if not WEBHOOK_ENABLED or not WEBHOOK_URL:
        return

    if not _rate_limiter.consume():
        logger.warning("Error webhook rate-limited, skipping notification")
        return

    try:
        client = _get_client()
        resp = await client.post(WEBHOOK_URL, json=payload)
        logger.debug("Error webhook sent: status=%d", resp.status_code)
    except httpx.TimeoutException:
        logger.warning("Error webhook timed out")
    except Exception:
        logger.warning("Error webhook failed", exc_info=True)


# ── Public API ───────────────────────────────────────────────────────

def _build_payload(
    path: str,
    method: str,
    status_code: int,
    exc: Exception,
    tenant_id: str = "",
    user_id: str = "",
    session_id: str = "",
    traceback_str: str = "",
    request_id: str = "",
) -> dict:
    error_msg = str(exc) or type(exc).__name__
    text = f"[EAGLE {ENVIRONMENT}] {status_code} {method} {path} — {error_msg}"
    if tenant_id:
        text += f" | tenant={tenant_id}"

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "eagle-backend",
        "environment": ENVIRONMENT,
        "request_id": request_id or str(uuid.uuid4()),
        "endpoint_path": path,
        "http_method": method,
        "status_code": status_code,
        "error_type": type(exc).__name__,
        "error_message": error_msg,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "session_id": session_id,
        "text": text,
    }
    if INCLUDE_TRACEBACK and traceback_str:
        payload["traceback"] = traceback_str
    return payload


def notify_error(
    request: Request,
    status_code: int,
    exception: Exception,
    traceback_str: str = "",
) -> None:
    """Build payload from a FastAPI Request and fire webhook.

    Extracts tenant/user/session from contextvars set by log_context.
    Spawns as a fire-and-forget asyncio task.
    """
    path = request.url.path
    method = request.method

    if not _should_report(status_code, path):
        return

    tenant = _tenant_id.get("")
    user = _user_id.get("")
    session = _session_id.get("")

    payload = _build_payload(
        path=path,
        method=method,
        status_code=status_code,
        exc=exception,
        tenant_id=tenant,
        user_id=user,
        session_id=session,
        traceback_str=traceback_str,
    )
    asyncio.create_task(send_error_webhook(payload))


def notify_streaming_error(
    path: str,
    method: str,
    exc: Exception,
    tenant_id: str = "",
    user_id: str = "",
    session_id: str = "",
) -> None:
    """Build payload for streaming errors where Request isn't available.

    Spawns as a fire-and-forget asyncio task.
    """
    if not _should_report(500, path):
        return

    tb_str = ""
    if INCLUDE_TRACEBACK and exc.__traceback__:
        tb_str = "".join(tb_module.format_exception(type(exc), exc, exc.__traceback__))

    payload = _build_payload(
        path=path,
        method=method,
        status_code=500,
        exc=exc,
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        traceback_str=tb_str,
    )
    asyncio.create_task(send_error_webhook(payload))
