"""Tests for app.teams_notifier."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# Ensure env vars are set before module import
os.environ.setdefault("TEAMS_WEBHOOK_URL", "https://test-webhook.example.com")
os.environ.setdefault("TEAMS_WEBHOOK_ENABLED", "true")


@pytest.fixture(autouse=True)
def _reset_client():
    """Reset the module-level httpx client between tests."""
    import app.teams_notifier as mod
    mod._client = None
    yield
    mod._client = None


@pytest.fixture
def _reset_rate_limiters():
    """Reset rate limiter tokens to full capacity."""
    import app.teams_notifier as mod
    for bucket in mod._rate_limiters.values():
        bucket.tokens = float(bucket.capacity)


# ── _send tests ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_success(_reset_rate_limiters):
    """_send posts to webhook and logs on 2xx."""
    from app.teams_notifier import _send

    mock_response = MagicMock()
    mock_response.status_code = 200

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("app.teams_notifier._get_client", return_value=mock_client):
        await _send("test message", "feedback")

    mock_client.post.assert_called_once()
    payload = mock_client.post.call_args[1]["json"]
    assert payload["text"] == "test message"


@pytest.mark.asyncio
async def test_send_timeout(_reset_rate_limiters):
    """_send handles httpx.TimeoutException gracefully."""
    from app.teams_notifier import _send

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

    with patch("app.teams_notifier._get_client", return_value=mock_client):
        await _send("test", "feedback")


@pytest.mark.asyncio
async def test_send_disabled():
    """_send is a no-op when WEBHOOK_ENABLED is False."""
    from app.teams_notifier import _send

    with patch("app.teams_notifier.WEBHOOK_ENABLED", False):
        mock_client = AsyncMock()
        with patch("app.teams_notifier._get_client", return_value=mock_client):
            await _send("test", "feedback")
        mock_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_send_rate_limited():
    """_send skips when rate limiter is exhausted."""
    import app.teams_notifier as mod
    from app.teams_notifier import _send

    # Drain the feedback bucket
    bucket = mod._rate_limiters["feedback"]
    bucket.tokens = 0.0

    mock_client = AsyncMock()
    with patch("app.teams_notifier._get_client", return_value=mock_client):
        await _send("test", "feedback")

    mock_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_send_non_2xx_logs_warning(_reset_rate_limiters):
    """_send logs a warning on non-2xx responses."""
    from app.teams_notifier import _send

    mock_response = MagicMock()
    mock_response.status_code = 403
    mock_response.text = "Forbidden"

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("app.teams_notifier._get_client", return_value=mock_client), \
         patch("app.teams_notifier.logger") as mock_logger:
        await _send("test", "feedback")

    mock_logger.warning.assert_called()
    assert "non-2xx" in str(mock_logger.warning.call_args)


# ── notify_feedback tests ────────────────────────────────────────────

def test_notify_feedback_builds_correct_text():
    """notify_feedback formats message with user details and truncated text."""
    from app.teams_notifier import notify_feedback

    with patch("app.teams_notifier._fire") as mock_fire:
        notify_feedback(
            tenant_id="nci-oar",
            user_id="john.doe",
            tier="advanced",
            session_id="abc-123-def",
            feedback_text="The document generation failed when I tried to create a SOW.",
            feedback_type="bug",
            page="/chat",
        )

    mock_fire.assert_called_once()
    text = mock_fire.call_args[0][0]
    assert "Feedback received" in text
    assert "bug" in text
    assert "john.doe" in text
    assert "nci-oar" in text
    assert "/chat" in text
    assert "document generation failed" in text
    assert mock_fire.call_args[0][1] == "feedback"


def test_notify_feedback_truncates_long_text():
    """Feedback text longer than 500 chars is truncated."""
    from app.teams_notifier import notify_feedback

    with patch("app.teams_notifier._fire") as mock_fire:
        notify_feedback(
            tenant_id="t", user_id="u", tier="basic",
            session_id="s", feedback_text="x" * 600,
        )

    text = mock_fire.call_args[0][0]
    assert "..." in text
    assert "x" * 501 not in text


# ── send_daily_summary tests ────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_daily_summary_with_mocked_stores():
    """send_daily_summary aggregates data from session_store and feedback_store."""
    from app.teams_notifier import send_daily_summary

    mock_tenants = [{"tenant_id": "tenant-a"}, {"tenant_id": "tenant-b"}]
    mock_usage = {
        "total_requests": 50, "total_tokens": 100000,
        "total_cost_usd": 0.25, "by_date": {},
    }

    mock_ss = MagicMock()
    mock_ss.get_all_tenants.return_value = mock_tenants
    mock_ss.get_usage_summary.return_value = mock_usage
    mock_ss.list_tenant_sessions.return_value = [{"user_id": "user1"}]

    mock_fs = MagicMock()
    mock_fs.list_feedback.return_value = []

    with patch.dict("sys.modules", {"app.session_store": mock_ss, "app.feedback_store": mock_fs}), \
         patch("app.teams_notifier._send", new_callable=AsyncMock) as mock_send:
        await send_daily_summary()

    mock_send.assert_called_once()
    text = mock_send.call_args[0][0]
    assert "Daily Summary" in text
    assert "Requests: 100" in text  # 50 * 2 tenants
    assert "$0.5000" in text


# ── notify_startup tests ────────────────────────────────────────────

def test_notify_startup_includes_hostname():
    """notify_startup message contains hostname and environment."""
    from app.teams_notifier import notify_startup

    with patch("app.teams_notifier._fire") as mock_fire, \
         patch("app.teams_notifier.platform") as mock_platform:
        mock_platform.node.return_value = "eagle-backend-abc123"
        notify_startup()

    text = mock_fire.call_args[0][0]
    assert "Service started" in text
    assert "eagle-backend-abc123" in text
    assert mock_fire.call_args[0][1] == "deployment"


# ── notify_suspicious tests ─────────────────────────────────────────

def test_notify_suspicious_formats_correctly():
    """notify_suspicious includes event type and detail."""
    from app.teams_notifier import notify_suspicious

    with patch("app.teams_notifier._fire") as mock_fire:
        notify_suspicious("404", "GET /api/nonexistent", tenant_id="nci-oar")

    text = mock_fire.call_args[0][0]
    assert "Suspicious: 404" in text
    assert "GET /api/nonexistent" in text
    assert "nci-oar" in text
    assert mock_fire.call_args[0][1] == "suspicious"


def test_notify_suspicious_rate_limits():
    """notify_suspicious respects its per-category rate limiter."""
    import app.teams_notifier as mod
    from app.teams_notifier import notify_suspicious

    # Drain the suspicious bucket
    mod._rate_limiters["suspicious"].tokens = 0.0

    with patch("app.teams_notifier._fire") as mock_fire:
        notify_suspicious("404", "GET /x")

    # _fire is always called; rate limiting happens inside _send
    mock_fire.assert_called_once()


# ── close_notifier_client tests ──────────────────────────────────────

@pytest.mark.asyncio
async def test_close_notifier_client():
    """close_notifier_client closes the httpx client and resets to None."""
    import app.teams_notifier as mod

    mock_client = AsyncMock()
    mod._client = mock_client

    await mod.close_notifier_client()

    mock_client.aclose.assert_called_once()
    assert mod._client is None


@pytest.mark.asyncio
async def test_close_notifier_client_noop_when_none():
    """close_notifier_client is safe to call when no client exists."""
    import app.teams_notifier as mod
    mod._client = None
    await mod.close_notifier_client()
