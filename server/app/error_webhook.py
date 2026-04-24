"""
Error webhook for EAGLE API endpoints.

Two parallel channels — both use the same Adaptive Card format but post
to different Teams webhook URLs:

  1. PRIMARY (ERROR_WEBHOOK_URL)
     Fires on 5xx HTTP errors only. High-severity, 10/min by default.
     Existing behaviour; unchanged by the debug-channel rollout.

  2. DEBUG (DEBUG_WEBHOOK_URL)
     Fires on anything that smells like an error the primary misses:
     4xx HTTP, tool-dispatch error-dict returns, frontend ErrorBoundary
     / window.onerror / unhandledrejection. Broader catch-all, 30/min
     by default. Sends ADDITIVELY — when a 5xx fires the primary, the
     debug channel also receives it (so the debug feed is a superset).
     Safe to leave DEBUG_WEBHOOK_URL unset; every code path silently
     no-ops in that case.

Fire-and-forget — telemetry never breaks the main flow.

Config via environment variables (primary):
    ERROR_WEBHOOK_URL          — target URL (Azure Logic App, Slack, etc.)
    ERROR_WEBHOOK_ENABLED      — master on/off (default: "true")
    ERROR_WEBHOOK_TIMEOUT      — POST timeout in seconds (default: "5.0")
    ERROR_WEBHOOK_RATE_LIMIT   — max calls per minute (default: "10")
    ERROR_WEBHOOK_INCLUDE_TRACEBACK — include traceback (default: "true")
    ERROR_WEBHOOK_MIN_STATUS   — minimum status code to trigger (default: "500")
    ERROR_WEBHOOK_EXCLUDE_PATHS — comma-separated paths to skip (default: "/api/health")

Config via environment variables (debug):
    DEBUG_WEBHOOK_URL          — target URL for the debug channel (no-op if unset)
    DEBUG_WEBHOOK_ENABLED      — master on/off (default: "true")
    DEBUG_WEBHOOK_TIMEOUT      — POST timeout in seconds (default: "5.0")
    DEBUG_WEBHOOK_RATE_LIMIT   — max calls per minute (default: "30")
    DEBUG_WEBHOOK_MIN_STATUS   — minimum status code to trigger (default: "400")
    DEBUG_WEBHOOK_INCLUDE_TRACEBACK — include traceback (default: "true")
    DEBUG_WEBHOOK_MAX_PAYLOAD_BYTES — cap serialized JSON size (default: "50000")
"""

import asyncio
import logging
import time
import traceback as tb_module
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import Request

from .telemetry.log_context import _tenant_id, _user_id, _session_id
from .config import webhooks as webhook_config, app as app_config

logger = logging.getLogger("eagle.error_webhook")

# ── Configuration (from centralized config) ──────────────────────────

WEBHOOK_URL: str = webhook_config.error_url
WEBHOOK_ENABLED: bool = webhook_config.error_enabled
WEBHOOK_TIMEOUT: float = webhook_config.error_timeout
RATE_LIMIT: int = webhook_config.error_rate_limit
INCLUDE_TRACEBACK: bool = webhook_config.error_include_traceback
MIN_STATUS: int = webhook_config.error_min_status
EXCLUDE_PATHS: list[str] = webhook_config.error_exclude_paths
ENVIRONMENT: str = app_config.environment

# ── Debug-channel config (broader catch-all, separate URL + bucket) ──
DEBUG_WEBHOOK_URL: str = webhook_config.debug_url
DEBUG_WEBHOOK_ENABLED: bool = webhook_config.debug_enabled
DEBUG_WEBHOOK_TIMEOUT: float = webhook_config.debug_timeout
DEBUG_RATE_LIMIT: int = webhook_config.debug_rate_limit
DEBUG_INCLUDE_TRACEBACK: bool = webhook_config.debug_include_traceback
DEBUG_MIN_STATUS: int = webhook_config.debug_min_status
DEBUG_MAX_PAYLOAD_BYTES: int = webhook_config.debug_max_payload_bytes


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
_debug_rate_limiter = _TokenBucket(DEBUG_RATE_LIMIT)

# Log configuration at import time so CloudWatch shows webhook is wired up
if WEBHOOK_ENABLED:
    logger.info(
        "Error webhook configured: url=%s env=%s", WEBHOOK_URL[:60], ENVIRONMENT
    )
if DEBUG_WEBHOOK_ENABLED and DEBUG_WEBHOOK_URL:
    logger.info(
        "Debug webhook configured: url=%s env=%s rate=%d/min min_status=%d",
        DEBUG_WEBHOOK_URL[:60],
        ENVIRONMENT,
        DEBUG_RATE_LIMIT,
        DEBUG_MIN_STATUS,
    )

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


async def _post_webhook(url: str, payload: dict, channel: str) -> None:
    """Single POST attempt with uniform error handling. Caller owns rate limiting."""
    try:
        client = _get_client()
        resp = await client.post(url, json=payload)
        if resp.status_code >= 300:
            logger.warning(
                "%s webhook non-2xx: status=%d body=%s",
                channel,
                resp.status_code,
                resp.text[:200],
            )
        else:
            logger.debug("%s webhook sent: status=%d", channel, resp.status_code)
    except httpx.TimeoutException:
        logger.warning("%s webhook timed out", channel)
    except Exception:
        logger.warning("%s webhook failed", channel, exc_info=True)


async def send_error_webhook(payload: dict) -> None:
    """POST payload to primary + debug webhook URLs. Fire-and-forget — never raises.

    Primary (ERROR_WEBHOOK_URL) fires only when its own config says so.
    Debug (DEBUG_WEBHOOK_URL) is ADDITIVE — if configured, it receives a
    copy of every primary event too, so the debug channel is a superset.
    Each channel has its own rate limiter.
    """
    tasks = []
    if WEBHOOK_ENABLED and WEBHOOK_URL:
        if _rate_limiter.consume():
            tasks.append(_post_webhook(WEBHOOK_URL, payload, "Error"))
        else:
            logger.warning("Error webhook rate-limited, skipping notification")
    if DEBUG_WEBHOOK_ENABLED and DEBUG_WEBHOOK_URL:
        if _debug_rate_limiter.consume():
            tasks.append(_post_webhook(DEBUG_WEBHOOK_URL, payload, "Debug"))
        else:
            logger.warning("Debug webhook rate-limited, skipping notification")
    for coro in tasks:
        await coro


async def send_debug_webhook(payload: dict) -> None:
    """POST payload to the DEBUG webhook only. Used by notify_debug_event
    for signals that never flow through the primary 5xx path (tool-dispatch
    errors, 4xx, frontend crashes).
    """
    if not DEBUG_WEBHOOK_ENABLED or not DEBUG_WEBHOOK_URL:
        return
    if not _debug_rate_limiter.consume():
        logger.warning("Debug webhook rate-limited, skipping notification")
        return
    await _post_webhook(DEBUG_WEBHOOK_URL, payload, "Debug")


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
    from .teams_cards import error_card

    error_msg = str(exc) or type(exc).__name__
    ts = datetime.now(timezone.utc).isoformat()

    return error_card(
        environment=ENVIRONMENT,
        status_code=status_code,
        method=method,
        path=path,
        error_type=type(exc).__name__,
        error_message=error_msg,
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        request_id=request_id or str(uuid.uuid4()),
        timestamp=ts,
    )


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


def notify_debug_event(
    source: str,
    error_type: str,
    message: str,
    context: Optional[dict] = None,
    status_code: int = 400,
    path: str = "",
    method: str = "",
) -> None:
    """Fire a debug-channel event for non-exception error signals.

    Covers silent-failure classes the primary 5xx webhook never sees:
      - Tool-dispatch handlers that return {"error": ...} with HTTP 200
        (no raised exception → no FastAPI handler → no primary webhook)
      - Client 4xx errors (below the primary's MIN_STATUS=500 default)
      - Frontend React/window/promise errors forwarded via
        POST /api/errors/report

    Posts ONLY to DEBUG_WEBHOOK_URL — never to the primary. The
    primary-fires-also-post-to-debug flow is handled separately by
    send_error_webhook (so 5xx events still reach both channels).

    Args:
        source: Short tag naming where the event originated
                (e.g. "tool_dispatch", "document_service",
                "react_error_boundary", "window_error").
        error_type: Exception-class-style short name
                (e.g. "UnknownDocType", "ValidationError").
        message: Human-readable error message.
        context: Optional dict of structured fields to carry in the card.
                Kept small; the whole payload is capped at
                DEBUG_WEBHOOK_MAX_PAYLOAD_BYTES (default 50KB).
        status_code: Synthetic status used for the card styling.
                Defaults to 400 so the debug card renders as client error
                rather than server error.
        path, method: Optional request coordinates when known.

    Fire-and-forget — spawns an asyncio task; never raises.
    """
    import json as _json

    if not DEBUG_WEBHOOK_ENABLED or not DEBUG_WEBHOOK_URL:
        return
    if status_code < DEBUG_MIN_STATUS:
        return

    from .teams_cards import error_card

    ts = datetime.now(timezone.utc).isoformat()
    ctx_blob = ""
    if context:
        try:
            ctx_blob = _json.dumps(context, default=str)[:8000]
        except Exception:
            ctx_blob = str(context)[:8000]

    tenant = _tenant_id.get("")
    user = _user_id.get("")
    session = _session_id.get("")

    # Reuse the existing Adaptive Card format — user explicitly asked for
    # "the same webhook format as the other ones" to the debug channel.
    # We fold source/error_type/context into the error_message so ops see
    # the distinguishing info inline on the card.
    composed_message = message
    if source:
        composed_message = f"[{source}] {composed_message}"
    if ctx_blob:
        composed_message = f"{composed_message}\n\ncontext: {ctx_blob}"

    payload = error_card(
        environment=ENVIRONMENT,
        status_code=status_code,
        method=method or "N/A",
        path=path or f"debug:{source}",
        error_type=error_type,
        error_message=composed_message,
        tenant_id=tenant,
        user_id=user,
        session_id=session,
        request_id=str(uuid.uuid4()),
        timestamp=ts,
    )
    # Tag as debug-category so downstream consumers can distinguish
    # primary-channel events (always 5xx) from debug (4xx/tool/fe).
    if isinstance(payload, dict):
        payload["event_category"] = "debug"

    # Size guard — the card can bloat on large context or stack traces.
    try:
        serialized_len = len(_json.dumps(payload, default=str))
        if serialized_len > DEBUG_MAX_PAYLOAD_BYTES:
            logger.warning(
                "Debug webhook payload %d bytes exceeds cap %d; truncating message",
                serialized_len,
                DEBUG_MAX_PAYLOAD_BYTES,
            )
            # Truncate composed_message in the card body. The teams_cards
            # format nests text in body[].text — a shallow search keeps
            # us loosely coupled to its internal structure.
            _truncate_card_text(payload, DEBUG_MAX_PAYLOAD_BYTES)
    except Exception:
        pass  # size accounting never blocks telemetry

    try:
        asyncio.create_task(send_debug_webhook(payload))
    except RuntimeError:
        # No running event loop (e.g. called from a sync test context).
        # Log instead; tests monkeypatch send_debug_webhook directly.
        logger.debug(
            "notify_debug_event: no event loop, dropping (source=%s type=%s)",
            source,
            error_type,
        )


def _truncate_card_text(payload: dict, cap: int) -> None:
    """Walk the card payload and shorten any long text fields in place."""
    import json as _json

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "text" and isinstance(v, str) and len(v) > 2000:
                    node[k] = v[:2000] + "…[truncated]"
                else:
                    walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    # Second pass: if still too big, drop optional fields.
    if len(_json.dumps(payload, default=str)) > cap:
        payload.pop("event_category", None)
