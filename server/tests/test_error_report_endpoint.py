"""Tests for POST /api/errors/report — frontend error forwarding endpoint.

Verifies the router validates the payload, forwards to notify_debug_event,
returns 204 on success, and rejects malformed or oversized payloads.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import app.routers.errors as errors_router


@pytest.fixture(autouse=True)
def _mock_notify(monkeypatch):
    """Capture notify_debug_event calls instead of firing real webhooks."""
    mock = MagicMock()
    monkeypatch.setattr(errors_router, "notify_debug_event", mock)
    return mock


@pytest.fixture
def client():
    import app.main as _main

    return TestClient(_main.app, raise_server_exceptions=False)


class TestReportErrorEndpoint:
    def test_valid_payload_returns_204(self, client, _mock_notify):
        resp = client.post(
            "/api/errors/report",
            json={
                "source": "react_error_boundary",
                "error_type": "TypeError",
                "message": "Cannot read properties of undefined",
                "stack": "at Foo (bar.tsx:1)",
                "component_stack": "at Foo\n  at App",
                "path": "/chat",
            },
        )
        assert resp.status_code == 204
        assert _mock_notify.call_count == 1
        call = _mock_notify.call_args
        assert call.kwargs["source"] == "react_error_boundary"
        assert call.kwargs["error_type"] == "TypeError"
        assert "Cannot read properties" in call.kwargs["message"]

    def test_minimal_payload_accepted(self, client, _mock_notify):
        resp = client.post(
            "/api/errors/report",
            json={"source": "window_error", "message": "boom"},
        )
        assert resp.status_code == 204
        assert _mock_notify.call_count == 1
        # error_type defaults to FrontendError when empty
        assert _mock_notify.call_args.kwargs["error_type"] == "FrontendError"

    def test_missing_message_returns_422(self, client, _mock_notify):
        resp = client.post(
            "/api/errors/report",
            json={"source": "window_error"},  # no message
        )
        # FastAPI/pydantic returns 422 for validation errors
        assert resp.status_code == 422
        _mock_notify.assert_not_called()

    def test_missing_source_returns_422(self, client, _mock_notify):
        resp = client.post(
            "/api/errors/report",
            json={"message": "boom"},  # no source
        )
        assert resp.status_code == 422
        _mock_notify.assert_not_called()

    def test_empty_message_returns_422(self, client, _mock_notify):
        resp = client.post(
            "/api/errors/report",
            json={"source": "window_error", "message": ""},
        )
        assert resp.status_code == 422
        _mock_notify.assert_not_called()

    def test_huge_stack_field_clamped_by_pydantic(self, client, _mock_notify):
        # The per-field stack cap is 8000 chars (Field max_length=8000).
        huge_stack = "x" * 20_000
        resp = client.post(
            "/api/errors/report",
            json={
                "source": "window_error",
                "message": "boom",
                "stack": huge_stack,
            },
        )
        assert resp.status_code == 422
        _mock_notify.assert_not_called()

    def test_notify_failure_does_not_leak_to_client(
        self, client, _mock_notify
    ):
        """Even if notify_debug_event raises, the client still gets 204."""
        _mock_notify.side_effect = RuntimeError("boom")
        resp = client.post(
            "/api/errors/report",
            json={"source": "window_error", "message": "x"},
        )
        assert resp.status_code == 204

    def test_path_falls_back_to_slash(self, client, _mock_notify):
        client.post(
            "/api/errors/report",
            json={"source": "window_error", "message": "x"},
        )
        # No path in request → endpoint passes "/" (or whatever report.path was)
        call = _mock_notify.call_args
        # Path is either "/" (fallback) or whatever was in report.path (None here → "/")
        assert call.kwargs["path"] == "/"

    def test_context_includes_user_agent_from_header(self, client, _mock_notify):
        client.post(
            "/api/errors/report",
            json={"source": "window_error", "message": "x"},
            headers={"user-agent": "EagleTest/1.0"},
        )
        ctx = _mock_notify.call_args.kwargs["context"]
        assert ctx["user_agent"] == "EagleTest/1.0"
