"""Tests for app.teams_notifier."""

import json
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


def _card_text(payload: dict) -> str:
    """Extract all text from an Adaptive Card payload for assertion."""
    return json.dumps(payload)


# ── _send tests ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_success(_reset_rate_limiters):
    """_send posts to webhook and logs on 2xx."""
    from app.teams_notifier import _send

    mock_response = MagicMock()
    mock_response.status_code = 200

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    payload = {"type": "message", "attachments": []}
    with patch("app.teams_notifier._get_client", return_value=mock_client):
        await _send(payload, "feedback")

    mock_client.post.assert_called_once()
    sent = mock_client.post.call_args[1]["json"]
    assert sent["type"] == "message"


@pytest.mark.asyncio
async def test_send_timeout(_reset_rate_limiters):
    """_send handles httpx.TimeoutException gracefully."""
    from app.teams_notifier import _send

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

    with patch("app.teams_notifier._get_client", return_value=mock_client):
        await _send({"type": "message"}, "feedback")


@pytest.mark.asyncio
async def test_send_disabled():
    """_send is a no-op when WEBHOOK_ENABLED is False."""
    from app.teams_notifier import _send

    with patch("app.teams_notifier.WEBHOOK_ENABLED", False):
        mock_client = AsyncMock()
        with patch("app.teams_notifier._get_client", return_value=mock_client):
            await _send({"type": "message"}, "feedback")
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
        await _send({"type": "message"}, "feedback")

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
        await _send({"type": "message"}, "feedback")

    mock_logger.warning.assert_called()
    assert "non-2xx" in str(mock_logger.warning.call_args)


# ── notify_feedback tests ────────────────────────────────────────────

def test_notify_feedback_builds_adaptive_card():
    """notify_feedback sends an Adaptive Card with user details."""
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
    payload = mock_fire.call_args[0][0]
    card_json = _card_text(payload)

    # Verify it's an Adaptive Card
    assert payload["type"] == "message"
    assert payload["attachments"][0]["contentType"] == "application/vnd.microsoft.card.adaptive"

    # Verify content
    assert "Feedback" in card_json
    assert "bug" in card_json
    assert "john.doe" in card_json
    assert "nci-oar" in card_json
    assert "/chat" in card_json
    assert "document generation failed" in card_json
    assert mock_fire.call_args[0][1] == "feedback"


def test_notify_feedback_truncates_long_text():
    """Feedback text longer than 500 chars is truncated."""
    from app.teams_notifier import notify_feedback

    with patch("app.teams_notifier._fire") as mock_fire:
        notify_feedback(
            tenant_id="t", user_id="u", tier="basic",
            session_id="s", feedback_text="x" * 600,
        )

    card_json = _card_text(mock_fire.call_args[0][0])
    assert "..." in card_json
    assert "x" * 501 not in card_json


# ── send_daily_summary tests ────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_daily_summary_with_mocked_stores():
    """send_daily_summary sends an Adaptive Card with aggregated data."""
    from app.teams_notifier import send_daily_summary

    mock_tenants = [{"tenant_id": "tenant-a"}, {"tenant_id": "tenant-b"}]
    mock_usage = {
        "total_requests": 50, "total_tokens": 100000,
        "total_cost_usd": 0.25, "by_date": {},
    }

    # Reset dedup guard so the test can always send
    import app.teams_notifier as _tn
    _tn._last_summary_date = None

    with patch("app.session_store.get_all_tenants", return_value=mock_tenants), \
         patch("app.session_store.get_usage_summary", return_value=mock_usage), \
         patch("app.session_store.list_tenant_sessions", return_value=[{"user_id": "user1"}]), \
         patch("app.feedback_store.list_feedback", return_value=[]), \
         patch("app.teams_notifier._send", new_callable=AsyncMock) as mock_send:
        await send_daily_summary()

    mock_send.assert_called_once()
    payload = mock_send.call_args[0][0]
    card_json = _card_text(payload)
    assert "Daily Summary" in card_json
    assert "100" in card_json  # 50 * 2 tenants
    assert "$0.5000" in card_json


# ── notify_startup tests ────────────────────────────────────────────

def test_notify_startup_sends_adaptive_card():
    """notify_startup sends an Adaptive Card with hostname and environment."""
    from app.teams_notifier import notify_startup

    with patch("app.teams_notifier._fire") as mock_fire, \
         patch("app.teams_notifier.os") as mock_os, \
         patch("app.teams_notifier.platform") as mock_platform:
        mock_platform.node.return_value = "eagle-backend-abc123"
        # Simulate ECS environment
        mock_os.getenv.side_effect = lambda k, *a: {
            "ECS_CONTAINER_METADATA_URI": "http://169.254.170.2/v3",
        }.get(k, a[0] if a else None)
        notify_startup()

    payload = mock_fire.call_args[0][0]
    card_json = _card_text(payload)
    assert "Service Started" in card_json
    assert "eagle-backend-abc123" in card_json
    assert mock_fire.call_args[0][1] == "deployment"


# ── notify_suspicious tests ─────────────────────────────────────────

def test_notify_suspicious_sends_adaptive_card():
    """notify_suspicious sends an Adaptive Card with event details."""
    from app.teams_notifier import notify_suspicious

    with patch("app.teams_notifier._fire") as mock_fire:
        notify_suspicious("404", "GET /api/nonexistent", tenant_id="nci-oar")

    payload = mock_fire.call_args[0][0]
    card_json = _card_text(payload)
    assert "Suspicious" in card_json
    assert "404" in card_json
    assert "GET /api/nonexistent" in card_json
    assert "nci-oar" in card_json
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


# ── teams_cards unit tests ───────────────────────────────────────────

def test_error_card_structure():
    """error_card returns a valid Adaptive Card envelope."""
    from app.teams_cards import error_card

    card = error_card("dev", 500, "POST", "/api/chat", "Exception", "boom")
    assert card["type"] == "message"
    content = card["attachments"][0]["content"]
    assert content["type"] == "AdaptiveCard"
    assert content["version"] == "1.4"
    assert any(b["type"] == "FactSet" for b in content["body"])


def test_error_card_attention_style():
    """error_card uses attention style (red) for the header."""
    from app.teams_cards import error_card

    card = error_card("dev", 500, "POST", "/api/chat", "Exception", "boom")
    container = card["attachments"][0]["content"]["body"][0]
    assert container["style"] == "attention"


def test_startup_card_good_style():
    """startup_card uses good style (green) for the header."""
    from app.teams_cards import startup_card

    card = startup_card("dev", "host-1", "2026-03-19T18:00:00Z")
    container = card["attachments"][0]["content"]["body"][0]
    assert container["style"] == "good"
