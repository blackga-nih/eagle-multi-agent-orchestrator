"""
Teams QA channel notifier for EAGLE.

Sends structured notifications to a Microsoft Teams channel via webhook
(Azure Logic App). Covers: user feedback, daily summaries, deployment
events, and suspicious request patterns.

Fire-and-forget — telemetry never breaks the main flow.

Config via environment variables:
    TEAMS_WEBHOOK_URL           — target URL (defaults to ERROR_WEBHOOK_URL)
    TEAMS_WEBHOOK_ENABLED       — master on/off (default: "true")
    TEAMS_WEBHOOK_TIMEOUT       — POST timeout in seconds (default: "5.0")
"""

import asyncio
import logging
import os
import platform
import time
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger("eagle.teams_notifier")

# ── Configuration ────────────────────────────────────────────────────

WEBHOOK_URL: str = os.getenv(
    "TEAMS_WEBHOOK_URL",
    os.getenv(
        "ERROR_WEBHOOK_URL",
        "https://prod-52.usgovtexas.logic.azure.us:443/workflows/8705df58d766420d8847222b1b12d7a0/triggers/manual/paths/invoke?api-version=2016-06-01&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=Xo4vpYNBYWWdyreboIYnBJtGlO3cNRLSEakEcNGWBoM",
    ),
)
_IS_ECS: bool = os.getenv("ECS_CONTAINER_METADATA_URI") is not None
WEBHOOK_ENABLED: bool = os.getenv("TEAMS_WEBHOOK_ENABLED", "true").lower() == "true"
WEBHOOK_TIMEOUT: float = float(os.getenv("TEAMS_WEBHOOK_TIMEOUT", "5.0"))
ENVIRONMENT: str = os.getenv(
    "EAGLE_ENVIRONMENT",
    os.getenv(
        "ENVIRONMENT",
        "dev" if os.getenv("ECS_CONTAINER_METADATA_URI") else "localhost",
    ),
)


# ── Token-bucket rate limiter (per category) ─────────────────────────


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


_rate_limiters: dict[str, _TokenBucket] = {
    "feedback": _TokenBucket(30),
    "daily_summary": _TokenBucket(2),
    "deployment": _TokenBucket(5),
    "suspicious": _TokenBucket(5),
}


# ── httpx.AsyncClient (lazy-init) ───────────────────────────────────

_client: Optional[httpx.AsyncClient] = None

# Dedup guard: track the date string of the last sent daily summary
# so we never send two for the same calendar day from the same process.
_last_summary_date: Optional[str] = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            limits=httpx.Limits(max_connections=5),
            timeout=httpx.Timeout(WEBHOOK_TIMEOUT),
        )
    return _client


async def close_notifier_client() -> None:
    """Close the httpx client. Call from app shutdown."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


# ── Core send ────────────────────────────────────────────────────────


async def _send(payload: dict, category: str) -> None:
    """POST payload to webhook URL. Fire-and-forget — never raises."""
    if not WEBHOOK_ENABLED or not WEBHOOK_URL:
        return

    limiter = _rate_limiters.get(category)
    if limiter and not limiter.consume():
        logger.warning("Teams notifier rate-limited (category=%s), skipping", category)
        return

    try:
        client = _get_client()
        resp = await client.post(WEBHOOK_URL, json=payload)
        if resp.status_code >= 300:
            logger.warning(
                "Teams notifier non-2xx: category=%s status=%d body=%s",
                category,
                resp.status_code,
                resp.text[:200],
            )
        else:
            logger.debug(
                "Teams notifier sent: category=%s status=%d", category, resp.status_code
            )
    except httpx.TimeoutException:
        logger.warning("Teams notifier timed out (category=%s)", category)
    except Exception:
        logger.warning("Teams notifier failed (category=%s)", category, exc_info=True)


def _fire(payload: dict, category: str) -> None:
    """Schedule _send as a fire-and-forget asyncio task."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_send(payload, category))
    except RuntimeError:
        # No running event loop — skip silently
        logger.debug(
            "Teams notifier: no event loop, skipping %s notification", category
        )


# ── Public API ───────────────────────────────────────────────────────


def notify_feedback(
    tenant_id: str,
    user_id: str,
    tier: str,
    session_id: str,
    feedback_text: str,
    feedback_type: str = "general",
    page: str = "",
    jira_key: str | None = None,
    feedback_id: str = "",
) -> None:
    """Notify Teams when a user submits Ctrl+J feedback."""
    from .teams_cards import feedback_card

    payload = feedback_card(
        environment=ENVIRONMENT,
        tenant_id=tenant_id,
        user_id=user_id,
        tier=tier,
        session_id=session_id,
        feedback_text=feedback_text,
        feedback_type=feedback_type,
        page=page,
        jira_key=jira_key,
        feedback_id=feedback_id,
    )
    _fire(payload, "feedback")


async def send_daily_summary() -> None:
    """Query stores and send a daily usage/feedback digest to Teams."""
    global _last_summary_date

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if _last_summary_date == today:
        logger.info("Daily summary already sent for %s, skipping duplicate", today)
        return
    _last_summary_date = today

    from . import session_store, feedback_store

    try:
        tenants = session_store.get_all_tenants()
        tenant_ids = [t["tenant_id"] for t in tenants] or ["default"]

        total_requests = 0
        total_tokens = 0
        total_cost = 0.0
        active_users: set[str] = set()

        for tid in tenant_ids:
            summary = session_store.get_usage_summary(tid, days=1)
            total_requests += summary.get("total_requests", 0)
            total_tokens += summary.get("total_tokens", 0)
            total_cost += summary.get("total_cost_usd", 0)

            # Count active users from sessions
            try:
                sessions = session_store.list_tenant_sessions(tid)
                for sess in sessions:
                    uid = sess.get("user_id")
                    if uid:
                        active_users.add(uid)
            except Exception:
                pass

        # Count feedback across tenants
        feedback_count = 0
        feedback_types: dict[str, int] = {}
        for tid in tenant_ids:
            try:
                items = feedback_store.list_feedback(tid, limit=50)
                # Filter to last 24 hours
                cutoff = datetime.now(timezone.utc).strftime("%Y-%m-%dT")
                for item in items:
                    if item.get("created_at", "").startswith(cutoff):
                        feedback_count += 1
                        ft = item.get("feedback_type", "general")
                        feedback_types[ft] = feedback_types.get(ft, 0) + 1
            except Exception:
                pass

        yesterday = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        fb_breakdown = (
            ", ".join(f"{c} {t}" for t, c in feedback_types.items())
            if feedback_types
            else "none"
        )

        from .teams_cards import daily_summary_card

        payload = daily_summary_card(
            environment=ENVIRONMENT,
            date=yesterday,
            requests=total_requests,
            tokens=total_tokens,
            cost=total_cost,
            active_users=len(active_users),
            feedback_count=feedback_count,
            feedback_breakdown=fb_breakdown,
        )
        await _send(payload, "daily_summary")
    except Exception:
        logger.warning("Teams notifier: daily summary failed", exc_info=True)


def notify_startup() -> None:
    """Notify Teams when the container starts (ECS only — skips local dev)."""
    hostname = platform.node()
    is_ecs = os.getenv("ECS_CONTAINER_METADATA_URI") is not None
    logger.info(
        "Teams notifier configured: url=%s env=%s ecs=%s",
        WEBHOOK_URL[:60],
        ENVIRONMENT,
        is_ecs,
    )
    if not is_ecs:
        logger.info("Teams notifier: skipping startup notification (local dev)")
        return

    from .teams_cards import startup_card

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = startup_card(environment=ENVIRONMENT, hostname=hostname, timestamp=ts)
    _fire(payload, "deployment")


async def send_eval_report(
    tier1_pass: int,
    tier1_total: int,
    tier2_pass: int,
    tier2_total: int,
    tier3_pass: int,
    tier3_total: int,
    tier3_run: bool,
    failed_tests: list,
    elapsed_seconds: float,
) -> None:
    """Send an eval suite results card to Teams. Called from the mvp1-eval skill."""
    from datetime import datetime, timezone
    from .teams_cards import eval_report_card

    project_id = os.getenv("LANGFUSE_PROJECT_ID", "")
    langfuse_host = os.getenv("LANGFUSE_HOST", "https://us.cloud.langfuse.com")
    langfuse_url = f"{langfuse_host}/project/{project_id}/traces" if project_id else ""
    cloudwatch_url = (
        "https://console.aws.amazon.com/cloudwatch/home"
        "?region=us-east-1#logsV2:log-groups/log-group/%2Feagle%2Ftest-runs"
    )

    payload = eval_report_card(
        environment=ENVIRONMENT,
        date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        tier1_pass=tier1_pass,
        tier1_total=tier1_total,
        tier2_pass=tier2_pass,
        tier2_total=tier2_total,
        tier3_pass=tier3_pass,
        tier3_total=tier3_total,
        tier3_run=tier3_run,
        failed_tests=failed_tests,
        elapsed_seconds=elapsed_seconds,
        langfuse_url=langfuse_url,
        cloudwatch_url=cloudwatch_url,
    )
    await _send(payload, "daily_summary")


def notify_suspicious(
    event_type: str,
    detail: str,
    tenant_id: str = "",
    user_id: str = "",
) -> None:
    """Notify Teams about suspicious request patterns (404s, auth issues)."""
    from .teams_cards import suspicious_card

    payload = suspicious_card(
        environment=ENVIRONMENT,
        event_type=event_type,
        detail=detail,
        tenant_id=tenant_id,
        user_id=user_id,
    )
    _fire(payload, "suspicious")
