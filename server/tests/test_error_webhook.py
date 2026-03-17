"""Tests for the EAGLE error webhook module."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Reload with controlled env vars
import importlib


# ── Helpers ──────────────────────────────────────────────────────────

def _reload_module(**env_overrides):
    """Reload error_webhook with custom env vars."""
    defaults = {
        "ERROR_WEBHOOK_URL": "https://example.com/webhook",
        "ERROR_WEBHOOK_ENABLED": "true",
        "ERROR_WEBHOOK_TIMEOUT": "5.0",
        "ERROR_WEBHOOK_RATE_LIMIT": "10",
        "ERROR_WEBHOOK_INCLUDE_TRACEBACK": "true",
        "ERROR_WEBHOOK_MIN_STATUS": "500",
        "ERROR_WEBHOOK_EXCLUDE_PATHS": "/api/health",
        "EAGLE_ENVIRONMENT": "test",
    }
    defaults.update(env_overrides)
    with patch.dict("os.environ", defaults, clear=False):
        import app.error_webhook as mod
        importlib.reload(mod)
        return mod


def _make_request(path="/api/chat", method="POST"):
    req = MagicMock()
    req.url = MagicMock()
    req.url.path = path
    req.method = method
    return req


# ── Config ───────────────────────────────────────────────────────────

class TestErrorWebhookConfig:
    def test_default_enabled(self):
        mod = _reload_module()
        assert mod.WEBHOOK_ENABLED is True

    def test_disabled_via_env(self):
        mod = _reload_module(ERROR_WEBHOOK_ENABLED="false")
        assert mod.WEBHOOK_ENABLED is False

    def test_reads_url(self):
        mod = _reload_module(ERROR_WEBHOOK_URL="https://hooks.slack.com/test")
        assert mod.WEBHOOK_URL == "https://hooks.slack.com/test"

    def test_reads_timeout(self):
        mod = _reload_module(ERROR_WEBHOOK_TIMEOUT="3.0")
        assert mod.WEBHOOK_TIMEOUT == 3.0

    def test_reads_rate_limit(self):
        mod = _reload_module(ERROR_WEBHOOK_RATE_LIMIT="20")
        assert mod.RATE_LIMIT == 20

    def test_reads_min_status(self):
        mod = _reload_module(ERROR_WEBHOOK_MIN_STATUS="400")
        assert mod.MIN_STATUS == 400

    def test_parses_exclude_paths(self):
        mod = _reload_module(ERROR_WEBHOOK_EXCLUDE_PATHS="/api/health,/api/ping")
        assert mod.EXCLUDE_PATHS == ["/api/health", "/api/ping"]

    def test_empty_exclude_paths(self):
        mod = _reload_module(ERROR_WEBHOOK_EXCLUDE_PATHS="")
        assert mod.EXCLUDE_PATHS == []


# ── _should_report ───────────────────────────────────────────────────

class TestShouldReport:
    def test_500_reports(self):
        mod = _reload_module()
        assert mod._should_report(500, "/api/chat") is True

    def test_503_reports(self):
        mod = _reload_module()
        assert mod._should_report(503, "/api/chat") is True

    def test_404_skips(self):
        mod = _reload_module()
        assert mod._should_report(404, "/api/chat") is False

    def test_health_excluded(self):
        mod = _reload_module()
        assert mod._should_report(500, "/api/health") is False

    def test_custom_min_status(self):
        mod = _reload_module(ERROR_WEBHOOK_MIN_STATUS="400")
        assert mod._should_report(400, "/api/chat") is True
        assert mod._should_report(399, "/api/chat") is False


# ── Rate Limiter ─────────────────────────────────────────────────────

class TestRateLimiter:
    def test_allows_up_to_capacity(self):
        mod = _reload_module(ERROR_WEBHOOK_RATE_LIMIT="3")
        bucket = mod._TokenBucket(3)
        assert bucket.consume() is True
        assert bucket.consume() is True
        assert bucket.consume() is True

    def test_rejects_after_capacity(self):
        mod = _reload_module(ERROR_WEBHOOK_RATE_LIMIT="2")
        bucket = mod._TokenBucket(2)
        bucket.consume()
        bucket.consume()
        assert bucket.consume() is False

    def test_refills_after_wait(self):
        mod = _reload_module(ERROR_WEBHOOK_RATE_LIMIT="1")
        bucket = mod._TokenBucket(1)
        bucket.consume()
        assert bucket.consume() is False
        # Simulate time passing (> 60s/1 = 60s per token)
        bucket._last_refill -= 61.0
        assert bucket.consume() is True


# ── send_error_webhook ───────────────────────────────────────────────

class TestSendErrorWebhook:
    @pytest.mark.asyncio
    async def test_sends_post(self):
        mod = _reload_module()
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mod._client = mock_client
        mod._rate_limiter = mod._TokenBucket(10)

        await mod.send_error_webhook({"test": True})
        mock_client.post.assert_called_once_with(mod.WEBHOOK_URL, json={"test": True})
        mod._client = None

    @pytest.mark.asyncio
    async def test_disabled_skips(self):
        mod = _reload_module(ERROR_WEBHOOK_ENABLED="false")
        mock_client = AsyncMock()
        mod._client = mock_client

        await mod.send_error_webhook({"test": True})
        mock_client.post.assert_not_called()
        mod._client = None

    @pytest.mark.asyncio
    async def test_empty_url_skips(self):
        mod = _reload_module(ERROR_WEBHOOK_URL="")
        mock_client = AsyncMock()
        mod._client = mock_client

        await mod.send_error_webhook({"test": True})
        mock_client.post.assert_not_called()
        mod._client = None

    @pytest.mark.asyncio
    async def test_timeout_suppressed(self):
        import httpx as _httpx
        mod = _reload_module()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=_httpx.TimeoutException("timeout"))
        mod._client = mock_client
        mod._rate_limiter = mod._TokenBucket(10)

        # Should not raise
        await mod.send_error_webhook({"test": True})
        mod._client = None

    @pytest.mark.asyncio
    async def test_connection_error_suppressed(self):
        mod = _reload_module()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=ConnectionError("refused"))
        mod._client = mock_client
        mod._rate_limiter = mod._TokenBucket(10)

        # Should not raise
        await mod.send_error_webhook({"test": True})
        mod._client = None

    @pytest.mark.asyncio
    async def test_rate_limited_skips(self):
        mod = _reload_module(ERROR_WEBHOOK_RATE_LIMIT="1")
        mock_client = AsyncMock()
        mod._client = mock_client
        mod._rate_limiter = mod._TokenBucket(1)
        mod._rate_limiter.consume()  # exhaust

        await mod.send_error_webhook({"test": True})
        mock_client.post.assert_not_called()
        mod._client = None


# ── notify_error ─────────────────────────────────────────────────────

class TestNotifyError:
    @pytest.mark.asyncio
    async def test_builds_payload_from_request(self):
        mod = _reload_module()
        mod._rate_limiter = mod._TokenBucket(10)

        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        mock_client.post = AsyncMock(return_value=mock_resp)
        mod._client = mock_client

        request = _make_request("/api/chat", "POST")
        exc = RuntimeError("Something broke")

        # Set contextvars
        from app.telemetry.log_context import _tenant_id, _user_id, _session_id
        t1 = _tenant_id.set("nci-acme")
        t2 = _user_id.set("user-123")
        t3 = _session_id.set("sess-abc")

        try:
            mod.notify_error(request=request, status_code=500, exception=exc, traceback_str="tb here")
            # Let the fire-and-forget task run
            await asyncio.sleep(0.1)

            mock_client.post.assert_called_once()
            payload = mock_client.post.call_args[1]["json"]
            assert payload["status_code"] == 500
            assert payload["endpoint_path"] == "/api/chat"
            assert payload["http_method"] == "POST"
            assert payload["error_type"] == "RuntimeError"
            assert payload["tenant_id"] == "nci-acme"
            assert payload["user_id"] == "user-123"
            assert payload["session_id"] == "sess-abc"
            assert payload["traceback"] == "tb here"
            assert "EAGLE test" in payload["text"]
        finally:
            _tenant_id.reset(t1)
            _user_id.reset(t2)
            _session_id.reset(t3)
            mod._client = None

    @pytest.mark.asyncio
    async def test_skips_4xx(self):
        mod = _reload_module()
        mock_client = AsyncMock()
        mod._client = mock_client

        request = _make_request("/api/sessions", "GET")
        mod.notify_error(request=request, status_code=404, exception=Exception("not found"))
        await asyncio.sleep(0.05)

        mock_client.post.assert_not_called()
        mod._client = None

    @pytest.mark.asyncio
    async def test_skips_health_endpoint(self):
        mod = _reload_module()
        mock_client = AsyncMock()
        mod._client = mock_client

        request = _make_request("/api/health", "GET")
        mod.notify_error(request=request, status_code=500, exception=Exception("boom"))
        await asyncio.sleep(0.05)

        mock_client.post.assert_not_called()
        mod._client = None


# ── notify_streaming_error ───────────────────────────────────────────

class TestNotifyStreamingError:
    @pytest.mark.asyncio
    async def test_builds_streaming_payload(self):
        mod = _reload_module()
        mod._rate_limiter = mod._TokenBucket(10)

        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        mock_client.post = AsyncMock(return_value=mock_resp)
        mod._client = mock_client

        exc = ValueError("stream broke")
        mod.notify_streaming_error(
            "/api/chat/stream", "POST", exc,
            tenant_id="nci-acme", user_id="user-1", session_id="sess-1",
        )
        await asyncio.sleep(0.1)

        mock_client.post.assert_called_once()
        payload = mock_client.post.call_args[1]["json"]
        assert payload["status_code"] == 500
        assert payload["endpoint_path"] == "/api/chat/stream"
        assert payload["error_type"] == "ValueError"
        assert payload["tenant_id"] == "nci-acme"
        mod._client = None


# ── Integration (exception handlers in main.py) ─────────────────────

class TestExceptionHandlerIntegration:
    @pytest.mark.asyncio
    async def test_500_triggers_webhook(self):
        """Simulate calling the unhandled_exception_handler."""
        mod = _reload_module()
        mod._rate_limiter = mod._TokenBucket(10)

        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        mock_client.post = AsyncMock(return_value=mock_resp)
        mod._client = mock_client

        request = _make_request("/api/documents", "POST")
        exc = RuntimeError("DB connection lost")

        # Directly call notify_error as the exception handler would
        mod.notify_error(request=request, status_code=500, exception=exc, traceback_str="Traceback ...")
        await asyncio.sleep(0.1)

        mock_client.post.assert_called_once()
        payload = mock_client.post.call_args[1]["json"]
        assert payload["status_code"] == 500
        assert "DB connection lost" in payload["text"]
        mod._client = None

    @pytest.mark.asyncio
    async def test_404_does_not_trigger(self):
        mod = _reload_module()
        mock_client = AsyncMock()
        mod._client = mock_client

        request = _make_request("/api/sessions/xyz", "GET")
        mod.notify_error(request=request, status_code=404, exception=Exception("not found"))
        await asyncio.sleep(0.05)

        mock_client.post.assert_not_called()
        mod._client = None


# ── close_webhook_client ─────────────────────────────────────────────

class TestCloseWebhookClient:
    @pytest.mark.asyncio
    async def test_close_resets_client(self):
        mod = _reload_module()
        mock_client = AsyncMock()
        mod._client = mock_client

        await mod.close_webhook_client()
        mock_client.aclose.assert_called_once()
        assert mod._client is None

    @pytest.mark.asyncio
    async def test_close_noop_when_no_client(self):
        mod = _reload_module()
        mod._client = None
        # Should not raise
        await mod.close_webhook_client()


# ── Payload structure ────────────────────────────────────────────────

class TestBuildPayload:
    def test_payload_has_required_fields(self):
        mod = _reload_module()
        exc = RuntimeError("test error")
        payload = mod._build_payload(
            path="/api/chat",
            method="POST",
            status_code=500,
            exc=exc,
            tenant_id="nci-acme",
            user_id="user-1",
            session_id="sess-1",
            traceback_str="Traceback ...",
        )
        required = [
            "timestamp", "service", "environment", "request_id",
            "endpoint_path", "http_method", "status_code",
            "error_type", "error_message", "tenant_id", "user_id",
            "session_id", "text", "traceback",
        ]
        for field in required:
            assert field in payload, f"Missing field: {field}"

        assert payload["service"] == "eagle-backend"
        assert payload["environment"] == "test"
        assert payload["error_type"] == "RuntimeError"
        assert "nci-acme" in payload["text"]

    def test_traceback_excluded_when_disabled(self):
        mod = _reload_module(ERROR_WEBHOOK_INCLUDE_TRACEBACK="false")
        exc = RuntimeError("test")
        payload = mod._build_payload(
            path="/api/test", method="GET", status_code=500, exc=exc,
            traceback_str="Traceback ...",
        )
        assert "traceback" not in payload

    def test_text_field_is_slack_compatible(self):
        mod = _reload_module()
        exc = RuntimeError("Internal server error")
        payload = mod._build_payload(
            path="/api/chat", method="POST", status_code=500, exc=exc,
            tenant_id="nci-acme",
        )
        assert payload["text"].startswith("[EAGLE test] 500 POST /api/chat")
