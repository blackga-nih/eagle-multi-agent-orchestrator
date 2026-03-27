"""Tests for the EAGLE error webhook module."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.error_webhook as error_webhook


# ── Helpers ──────────────────────────────────────────────────────────

# Default test values that all tests start from.  Each test that needs
# non-default config should override exactly the attrs it cares about via
# monkeypatch.setattr(error_webhook, "<ATTR>", <value>).
_DEFAULTS = {
    "WEBHOOK_URL": "https://example.com/webhook",
    "WEBHOOK_ENABLED": True,
    "WEBHOOK_TIMEOUT": 5.0,
    "RATE_LIMIT": 10,
    "INCLUDE_TRACEBACK": True,
    "MIN_STATUS": 500,
    "EXCLUDE_PATHS": ["/api/health"],
}


@pytest.fixture(autouse=True)
def reset_module_state(monkeypatch):
    """Reset all module-level config constants to known defaults before every test.

    This replaces the old _reload_module() pattern.  Instead of reloading the
    module (which fails because app.config.webhooks is a frozen singleton
    instantiated once at import time), we simply set the constants directly on
    the already-imported module object.  monkeypatch restores each attribute
    automatically after the test completes, so tests are fully isolated.
    """
    for attr, value in _DEFAULTS.items():
        monkeypatch.setattr(error_webhook, attr, value)

    # Always reset the lazy httpx client so no state leaks between tests.
    monkeypatch.setattr(error_webhook, "_client", None)

    # Give every test a fresh rate-limiter at full capacity.
    monkeypatch.setattr(error_webhook, "_rate_limiter", error_webhook._TokenBucket(10))


def _make_request(path="/api/chat", method="POST"):
    req = MagicMock()
    req.url = MagicMock()
    req.url.path = path
    req.method = method
    return req


# ── Config ───────────────────────────────────────────────────────────

class TestErrorWebhookConfig:
    def test_default_enabled(self):
        assert error_webhook.WEBHOOK_ENABLED is True

    def test_disabled_via_env(self, monkeypatch):
        monkeypatch.setattr(error_webhook, "WEBHOOK_ENABLED", False)
        assert error_webhook.WEBHOOK_ENABLED is False

    def test_reads_url(self, monkeypatch):
        monkeypatch.setattr(error_webhook, "WEBHOOK_URL", "https://hooks.slack.com/test")
        assert error_webhook.WEBHOOK_URL == "https://hooks.slack.com/test"

    def test_reads_timeout(self, monkeypatch):
        monkeypatch.setattr(error_webhook, "WEBHOOK_TIMEOUT", 3.0)
        assert error_webhook.WEBHOOK_TIMEOUT == 3.0

    def test_reads_rate_limit(self, monkeypatch):
        monkeypatch.setattr(error_webhook, "RATE_LIMIT", 20)
        assert error_webhook.RATE_LIMIT == 20

    def test_reads_min_status(self, monkeypatch):
        monkeypatch.setattr(error_webhook, "MIN_STATUS", 400)
        assert error_webhook.MIN_STATUS == 400

    def test_parses_exclude_paths(self, monkeypatch):
        monkeypatch.setattr(error_webhook, "EXCLUDE_PATHS", ["/api/health", "/api/ping"])
        assert error_webhook.EXCLUDE_PATHS == ["/api/health", "/api/ping"]

    def test_empty_exclude_paths(self, monkeypatch):
        monkeypatch.setattr(error_webhook, "EXCLUDE_PATHS", [])
        assert error_webhook.EXCLUDE_PATHS == []


# ── _should_report ───────────────────────────────────────────────────

class TestShouldReport:
    def test_500_reports(self):
        assert error_webhook._should_report(500, "/api/chat") is True

    def test_503_reports(self):
        assert error_webhook._should_report(503, "/api/chat") is True

    def test_404_skips(self):
        assert error_webhook._should_report(404, "/api/chat") is False

    def test_health_excluded(self):
        assert error_webhook._should_report(500, "/api/health") is False

    def test_custom_min_status(self, monkeypatch):
        monkeypatch.setattr(error_webhook, "MIN_STATUS", 400)
        assert error_webhook._should_report(400, "/api/chat") is True
        assert error_webhook._should_report(399, "/api/chat") is False


# ── Rate Limiter ─────────────────────────────────────────────────────

class TestRateLimiter:
    def test_allows_up_to_capacity(self):
        bucket = error_webhook._TokenBucket(3)
        assert bucket.consume() is True
        assert bucket.consume() is True
        assert bucket.consume() is True

    def test_rejects_after_capacity(self):
        bucket = error_webhook._TokenBucket(2)
        bucket.consume()
        bucket.consume()
        assert bucket.consume() is False

    def test_refills_after_wait(self):
        bucket = error_webhook._TokenBucket(1)
        bucket.consume()
        assert bucket.consume() is False
        # Simulate time passing (> 60s/1 = 60s per token)
        bucket._last_refill -= 61.0
        assert bucket.consume() is True


# ── send_error_webhook ───────────────────────────────────────────────

class TestSendErrorWebhook:
    @pytest.mark.asyncio
    async def test_sends_post(self, monkeypatch):
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        monkeypatch.setattr(error_webhook, "_client", mock_client)
        monkeypatch.setattr(error_webhook, "_rate_limiter", error_webhook._TokenBucket(10))

        await error_webhook.send_error_webhook({"test": True})
        mock_client.post.assert_called_once_with(error_webhook.WEBHOOK_URL, json={"test": True})

    @pytest.mark.asyncio
    async def test_disabled_skips(self, monkeypatch):
        monkeypatch.setattr(error_webhook, "WEBHOOK_ENABLED", False)
        mock_client = AsyncMock()
        monkeypatch.setattr(error_webhook, "_client", mock_client)

        await error_webhook.send_error_webhook({"test": True})
        mock_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_url_skips(self, monkeypatch):
        monkeypatch.setattr(error_webhook, "WEBHOOK_URL", "")
        mock_client = AsyncMock()
        monkeypatch.setattr(error_webhook, "_client", mock_client)

        await error_webhook.send_error_webhook({"test": True})
        mock_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_timeout_suppressed(self, monkeypatch):
        import httpx as _httpx
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=_httpx.TimeoutException("timeout"))
        monkeypatch.setattr(error_webhook, "_client", mock_client)
        monkeypatch.setattr(error_webhook, "_rate_limiter", error_webhook._TokenBucket(10))

        # Should not raise
        await error_webhook.send_error_webhook({"test": True})

    @pytest.mark.asyncio
    async def test_connection_error_suppressed(self, monkeypatch):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=ConnectionError("refused"))
        monkeypatch.setattr(error_webhook, "_client", mock_client)
        monkeypatch.setattr(error_webhook, "_rate_limiter", error_webhook._TokenBucket(10))

        # Should not raise
        await error_webhook.send_error_webhook({"test": True})

    @pytest.mark.asyncio
    async def test_rate_limited_skips(self, monkeypatch):
        mock_client = AsyncMock()
        monkeypatch.setattr(error_webhook, "_client", mock_client)
        exhausted = error_webhook._TokenBucket(1)
        exhausted.consume()  # exhaust
        monkeypatch.setattr(error_webhook, "_rate_limiter", exhausted)

        await error_webhook.send_error_webhook({"test": True})
        mock_client.post.assert_not_called()


# ── notify_error ─────────────────────────────────────────────────────

class TestNotifyError:
    @pytest.mark.asyncio
    async def test_builds_payload_from_request(self, monkeypatch):
        monkeypatch.setattr(error_webhook, "_rate_limiter", error_webhook._TokenBucket(10))

        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        mock_client.post = AsyncMock(return_value=mock_resp)
        monkeypatch.setattr(error_webhook, "_client", mock_client)

        request = _make_request("/api/chat", "POST")
        exc = RuntimeError("Something broke")

        # Set contextvars
        from app.telemetry.log_context import _tenant_id, _user_id, _session_id
        t1 = _tenant_id.set("nci-acme")
        t2 = _user_id.set("user-123")
        t3 = _session_id.set("sess-abc")

        try:
            error_webhook.notify_error(request=request, status_code=500, exception=exc, traceback_str="tb here")
            # Let the fire-and-forget task run
            await asyncio.sleep(0.1)

            mock_client.post.assert_called_once()
            payload = mock_client.post.call_args[1]["json"]
            # Payload is now a Teams Adaptive Card envelope
            assert payload["type"] == "message"
            card_str = str(payload)
            assert "500" in card_str
            assert "/api/chat" in card_str
            assert "POST" in card_str
            assert "RuntimeError" in card_str
            assert "nci-acme" in card_str
            assert "user-123" in card_str
            assert "sess-abc" in card_str
            assert "EAGLE" in card_str
        finally:
            _tenant_id.reset(t1)
            _user_id.reset(t2)
            _session_id.reset(t3)

    @pytest.mark.asyncio
    async def test_skips_4xx(self, monkeypatch):
        mock_client = AsyncMock()
        monkeypatch.setattr(error_webhook, "_client", mock_client)

        request = _make_request("/api/sessions", "GET")
        error_webhook.notify_error(request=request, status_code=404, exception=Exception("not found"))
        await asyncio.sleep(0.05)

        mock_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_health_endpoint(self, monkeypatch):
        mock_client = AsyncMock()
        monkeypatch.setattr(error_webhook, "_client", mock_client)

        request = _make_request("/api/health", "GET")
        error_webhook.notify_error(request=request, status_code=500, exception=Exception("boom"))
        await asyncio.sleep(0.05)

        mock_client.post.assert_not_called()


# ── notify_streaming_error ───────────────────────────────────────────

class TestNotifyStreamingError:
    @pytest.mark.asyncio
    async def test_builds_streaming_payload(self, monkeypatch):
        monkeypatch.setattr(error_webhook, "_rate_limiter", error_webhook._TokenBucket(10))

        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        mock_client.post = AsyncMock(return_value=mock_resp)
        monkeypatch.setattr(error_webhook, "_client", mock_client)

        exc = ValueError("stream broke")
        error_webhook.notify_streaming_error(
            "/api/chat/stream", "POST", exc,
            tenant_id="nci-acme", user_id="user-1", session_id="sess-1",
        )
        await asyncio.sleep(0.1)

        mock_client.post.assert_called_once()
        payload = mock_client.post.call_args[1]["json"]
        assert payload["type"] == "message"
        card_str = str(payload)
        assert "500" in card_str
        assert "/api/chat/stream" in card_str
        assert "ValueError" in card_str
        assert "nci-acme" in card_str


# ── Integration (exception handlers in main.py) ─────────────────────

class TestExceptionHandlerIntegration:
    @pytest.mark.asyncio
    async def test_500_triggers_webhook(self, monkeypatch):
        """Simulate calling the unhandled_exception_handler."""
        monkeypatch.setattr(error_webhook, "_rate_limiter", error_webhook._TokenBucket(10))

        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        mock_client.post = AsyncMock(return_value=mock_resp)
        monkeypatch.setattr(error_webhook, "_client", mock_client)

        request = _make_request("/api/documents", "POST")
        exc = RuntimeError("DB connection lost")

        # Directly call notify_error as the exception handler would
        error_webhook.notify_error(request=request, status_code=500, exception=exc, traceback_str="Traceback ...")
        await asyncio.sleep(0.1)

        mock_client.post.assert_called_once()
        payload = mock_client.post.call_args[1]["json"]
        assert payload["type"] == "message"
        assert "DB connection lost" in str(payload)

    @pytest.mark.asyncio
    async def test_404_does_not_trigger(self, monkeypatch):
        mock_client = AsyncMock()
        monkeypatch.setattr(error_webhook, "_client", mock_client)

        request = _make_request("/api/sessions/xyz", "GET")
        error_webhook.notify_error(request=request, status_code=404, exception=Exception("not found"))
        await asyncio.sleep(0.05)

        mock_client.post.assert_not_called()


# ── close_webhook_client ─────────────────────────────────────────────

class TestCloseWebhookClient:
    @pytest.mark.asyncio
    async def test_close_resets_client(self, monkeypatch):
        mock_client = AsyncMock()
        monkeypatch.setattr(error_webhook, "_client", mock_client)

        await error_webhook.close_webhook_client()
        mock_client.aclose.assert_called_once()
        assert error_webhook._client is None

    @pytest.mark.asyncio
    async def test_close_noop_when_no_client(self, monkeypatch):
        monkeypatch.setattr(error_webhook, "_client", None)
        # Should not raise
        await error_webhook.close_webhook_client()


# ── Payload structure ────────────────────────────────────────────────

class TestBuildPayload:
    def test_payload_has_required_fields(self):
        exc = RuntimeError("test error")
        payload = error_webhook._build_payload(
            path="/api/chat",
            method="POST",
            status_code=500,
            exc=exc,
            tenant_id="nci-acme",
            user_id="user-1",
            session_id="sess-1",
            traceback_str="Traceback ...",
        )
        # Payload is now a Teams Adaptive Card envelope
        assert payload["type"] == "message"
        assert "attachments" in payload
        assert len(payload["attachments"]) == 1
        card_str = str(payload)
        # Key fields must appear somewhere in the card
        assert "RuntimeError" in card_str
        assert "nci-acme" in card_str
        assert "500" in card_str
        assert "/api/chat" in card_str
        assert "EAGLE" in card_str

    def test_traceback_excluded_when_disabled(self, monkeypatch):
        monkeypatch.setattr(error_webhook, "INCLUDE_TRACEBACK", False)
        exc = RuntimeError("test")
        payload = error_webhook._build_payload(
            path="/api/test", method="GET", status_code=500, exc=exc,
            traceback_str="Traceback ...",
        )
        assert "traceback" not in payload

    def test_payload_contains_status_and_path(self):
        exc = RuntimeError("Internal server error")
        payload = error_webhook._build_payload(
            path="/api/chat", method="POST", status_code=500, exc=exc,
            tenant_id="nci-acme",
        )
        # Adaptive Card — status code and path must appear in the card
        card_str = str(payload)
        assert "500" in card_str
        assert "/api/chat" in card_str
        assert "nci-acme" in card_str
