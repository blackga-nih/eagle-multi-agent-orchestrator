"""Tests for the debug-channel path in error_webhook + notify_debug_event.

The debug channel is a parallel Teams webhook that catches silent-failure
events the primary 5xx webhook never sees (tool-dispatch error dicts,
4xx HTTP, frontend crashes). Same Adaptive Card format, different URL.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

import app.error_webhook as error_webhook


# Mirror test_error_webhook.py's reset pattern — monkeypatch the module
# constants rather than reloading (WebhookConfig is a frozen singleton).
_DEBUG_DEFAULTS = {
    "DEBUG_WEBHOOK_URL": "https://example.com/debug-webhook",
    "DEBUG_WEBHOOK_ENABLED": True,
    "DEBUG_WEBHOOK_TIMEOUT": 5.0,
    "DEBUG_RATE_LIMIT": 30,
    "DEBUG_MIN_STATUS": 400,
    "DEBUG_INCLUDE_TRACEBACK": True,
    "DEBUG_MAX_PAYLOAD_BYTES": 50_000,
    # Primary defaults too — a few tests need to vary both channels.
    "WEBHOOK_URL": "https://example.com/primary-webhook",
    "WEBHOOK_ENABLED": True,
    "RATE_LIMIT": 10,
    "MIN_STATUS": 500,
}


@pytest.fixture(autouse=True)
def _reset_module(monkeypatch):
    for attr, value in _DEBUG_DEFAULTS.items():
        monkeypatch.setattr(error_webhook, attr, value)
    monkeypatch.setattr(error_webhook, "_client", None)
    monkeypatch.setattr(
        error_webhook, "_rate_limiter", error_webhook._TokenBucket(10)
    )
    monkeypatch.setattr(
        error_webhook, "_debug_rate_limiter", error_webhook._TokenBucket(30)
    )


class TestNotifyDebugEventEmit:
    def test_skips_when_disabled(self, monkeypatch):
        monkeypatch.setattr(error_webhook, "DEBUG_WEBHOOK_ENABLED", False)
        # Mock create_task so we can detect whether a send was scheduled.
        called = {}

        def fake_create_task(coro):
            called["scheduled"] = True
            coro.close()  # prevent "coroutine never awaited" warning
            return AsyncMock()

        monkeypatch.setattr("asyncio.create_task", fake_create_task)

        error_webhook.notify_debug_event(
            source="test", error_type="Foo", message="msg"
        )
        assert "scheduled" not in called

    def test_skips_when_url_empty(self, monkeypatch):
        monkeypatch.setattr(error_webhook, "DEBUG_WEBHOOK_URL", "")
        called = {}

        def fake_create_task(coro):
            called["scheduled"] = True
            coro.close()
            return AsyncMock()

        monkeypatch.setattr("asyncio.create_task", fake_create_task)

        error_webhook.notify_debug_event(
            source="test", error_type="Foo", message="msg"
        )
        assert "scheduled" not in called

    def test_skips_when_status_below_min(self, monkeypatch):
        # DEBUG_MIN_STATUS=400, so status_code=300 should be skipped.
        called = {}

        def fake_create_task(coro):
            called["scheduled"] = True
            coro.close()
            return AsyncMock()

        monkeypatch.setattr("asyncio.create_task", fake_create_task)

        error_webhook.notify_debug_event(
            source="test", error_type="Foo", message="msg", status_code=300
        )
        assert "scheduled" not in called

    def test_schedules_send_when_configured(self, monkeypatch):
        scheduled = []

        def fake_create_task(coro):
            scheduled.append(coro)
            return AsyncMock()

        monkeypatch.setattr("asyncio.create_task", fake_create_task)

        error_webhook.notify_debug_event(
            source="tool_dispatch",
            error_type="ToolError",
            message="something broke",
            context={"tool": "create_document"},
        )
        assert len(scheduled) == 1
        # Clean up un-awaited coroutine
        scheduled[0].close()

    def test_event_category_tag_in_payload(self, monkeypatch):
        """The debug card must carry event_category=debug so downstream
        consumers can distinguish it from primary-channel events."""
        captured = {}

        def fake_create_task(coro):
            # coro is send_debug_webhook(payload) — inspect its args via frame
            # Easier: replace send_debug_webhook to capture the payload.
            coro.close()
            return AsyncMock()

        # Monkeypatch send_debug_webhook directly so we can capture the payload.
        async def capture_send(payload):
            captured["payload"] = payload

        monkeypatch.setattr(error_webhook, "send_debug_webhook", capture_send)
        # Use a real running loop so create_task works.
        loop = asyncio.new_event_loop()
        try:
            async def _run():
                error_webhook.notify_debug_event(
                    source="tool_dispatch",
                    error_type="ToolError",
                    message="x",
                )
                # yield control so the scheduled task runs
                await asyncio.sleep(0)

            loop.run_until_complete(_run())
        finally:
            loop.close()
        assert captured["payload"].get("event_category") == "debug"

    def test_context_folded_into_message(self, monkeypatch):
        captured = {}

        async def capture_send(payload):
            captured["payload"] = payload

        monkeypatch.setattr(error_webhook, "send_debug_webhook", capture_send)
        loop = asyncio.new_event_loop()
        try:
            async def _run():
                error_webhook.notify_debug_event(
                    source="document_service",
                    error_type="UnknownDocType",
                    message="Unknown doc_type 'x'",
                    context={"doc_type": "x", "package_id": "pkg-1"},
                )
                await asyncio.sleep(0)

            loop.run_until_complete(_run())
        finally:
            loop.close()
        # The card body should mention both source tag and doc_type
        import json as _j

        card_str = _j.dumps(captured["payload"], default=str)
        assert "document_service" in card_str
        assert "pkg-1" in card_str


class TestDebugRateLimit:
    def test_rate_limit_drains(self, monkeypatch):
        """After DEBUG_RATE_LIMIT events, further events are skipped."""
        # Smaller bucket for speed.
        bucket = error_webhook._TokenBucket(2)
        monkeypatch.setattr(error_webhook, "_debug_rate_limiter", bucket)

        # Consume both tokens — two sends should succeed.
        assert bucket.consume() is True
        assert bucket.consume() is True
        # Third consume should fail (bucket drained).
        assert bucket.consume() is False


class TestDualSend:
    def test_primary_5xx_also_posts_to_debug(self, monkeypatch):
        """When the primary webhook fires on 5xx, the debug channel
        receives the same payload ADDITIVELY (not instead-of)."""
        posted_urls: list[str] = []

        async def fake_post(url, payload, channel):
            posted_urls.append(url)

        monkeypatch.setattr(error_webhook, "_post_webhook", fake_post)

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(error_webhook.send_error_webhook({"test": "x"}))
        finally:
            loop.close()

        assert "https://example.com/primary-webhook" in posted_urls
        assert "https://example.com/debug-webhook" in posted_urls

    def test_primary_only_when_debug_url_empty(self, monkeypatch):
        monkeypatch.setattr(error_webhook, "DEBUG_WEBHOOK_URL", "")
        posted_urls: list[str] = []

        async def fake_post(url, payload, channel):
            posted_urls.append(url)

        monkeypatch.setattr(error_webhook, "_post_webhook", fake_post)

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(error_webhook.send_error_webhook({"test": "x"}))
        finally:
            loop.close()

        assert posted_urls == ["https://example.com/primary-webhook"]

    def test_debug_only_when_primary_url_empty(self, monkeypatch):
        monkeypatch.setattr(error_webhook, "WEBHOOK_URL", "")
        posted_urls: list[str] = []

        async def fake_post(url, payload, channel):
            posted_urls.append(url)

        monkeypatch.setattr(error_webhook, "_post_webhook", fake_post)

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(error_webhook.send_error_webhook({"test": "x"}))
        finally:
            loop.close()

        assert posted_urls == ["https://example.com/debug-webhook"]


class TestSendDebugWebhookNoOps:
    def test_noops_when_disabled(self, monkeypatch):
        monkeypatch.setattr(error_webhook, "DEBUG_WEBHOOK_ENABLED", False)
        posted_urls: list[str] = []

        async def fake_post(url, payload, channel):
            posted_urls.append(url)

        monkeypatch.setattr(error_webhook, "_post_webhook", fake_post)

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(
                error_webhook.send_debug_webhook({"x": "y"})
            )
        finally:
            loop.close()

        assert posted_urls == []

    def test_noops_when_url_empty(self, monkeypatch):
        monkeypatch.setattr(error_webhook, "DEBUG_WEBHOOK_URL", "")
        posted_urls: list[str] = []

        async def fake_post(url, payload, channel):
            posted_urls.append(url)

        monkeypatch.setattr(error_webhook, "_post_webhook", fake_post)

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(
                error_webhook.send_debug_webhook({"x": "y"})
            )
        finally:
            loop.close()

        assert posted_urls == []
