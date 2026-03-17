"""
Tests for endpoints in app/main.py:
  - POST /api/feedback  +  GET /api/feedback

Run: pytest server/tests/test_new_endpoints.py -v
"""

import os
import sys
from typing import AsyncGenerator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Ensure server/ is on sys.path so "app.main" resolves
_server_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)


# ── Mock sdk_query before importing main ─────────────────────────────

async def _mock_sdk_query(*args, **kwargs) -> AsyncGenerator:
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "Mock response from EAGLE."

    assistant_msg = MagicMock()
    assistant_msg.__class__.__name__ = "AssistantMessage"
    assistant_msg.content = [text_block]

    result_msg = MagicMock()
    result_msg.__class__.__name__ = "ResultMessage"
    result_msg.usage = {"input_tokens": 10, "output_tokens": 5}
    result_msg.result = "Mock response from EAGLE."

    yield assistant_msg
    yield result_msg


# ── Fixtures ──────────────────────────────────────────────────────────

_ENV_PATCH = {
    "REQUIRE_AUTH": "false",
    "DEV_MODE": "false",
    "USE_BEDROCK": "false",
    "COGNITO_USER_POOL_ID": "us-east-1_test",
    "COGNITO_CLIENT_ID": "test-client",
    "EAGLE_SESSIONS_TABLE": "eagle",
    "USE_PERSISTENT_SESSIONS": "false",
}


@pytest.fixture(scope="module")
def app_instance():
    """FastAPI app with REQUIRE_AUTH=false, sdk_query mocked, and feedback_store mocked."""
    with patch.dict(os.environ, _ENV_PATCH, clear=False):
        with patch("app.strands_agentic_service.sdk_query", side_effect=_mock_sdk_query):
            import importlib
            import app.main as main_module
            importlib.reload(main_module)
            yield main_module


@pytest.fixture(scope="module")
def client(app_instance):
    """TestClient scoped to the module."""
    with TestClient(app_instance.app) as c:
        yield c


# ══════════════════════════════════════════════════════════════════════
# POST /api/feedback  +  GET /api/feedback
# ══════════════════════════════════════════════════════════════════════

class TestFeedbackEndpoints:

    def test_post_feedback_success(self, client):
        """POST /api/feedback creates a feedback record and returns status ok."""
        fake_item = {"feedback_id": "fb-001", "tenant_id": "default", "feedback_text": "Great tool!"}
        with patch("app.feedback_store.write_feedback", return_value=fake_item), \
             patch("app.main._fetch_cloudwatch_logs_for_session", return_value=[]):
            resp = client.post("/api/feedback", json={
                "feedback_text": "Great tool!",
                "page": "/chat",
                "session_id": "sess-1",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_post_feedback_empty_text_returns_400(self, client):
        """POST /api/feedback with empty feedback_text returns 400."""
        resp = client.post("/api/feedback", json={
            "feedback_text": "",
            "page": "/chat",
        })
        assert resp.status_code == 400

    def test_post_feedback_minimal_body(self, client):
        """POST /api/feedback with feedback_text succeeds."""
        fake_item = {"feedback_id": "fb-002", "tenant_id": "default"}
        with patch("app.feedback_store.write_feedback", return_value=fake_item), \
             patch("app.main._fetch_cloudwatch_logs_for_session", return_value=[]):
            resp = client.post("/api/feedback", json={
                "feedback_text": "Needs improvement",
            })
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_get_feedback_returns_list(self, client):
        """GET /api/feedback returns a list of feedback items."""
        fake_items = [
            {"feedback_id": "fb-001", "feedback_text": "good", "page": "/chat"},
            {"feedback_id": "fb-002", "feedback_text": "ok", "page": "/admin"},
        ]
        with patch("app.main.list_feedback", return_value=fake_items):
            resp = client.get("/api/feedback")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        assert len(data["feedback"]) == 2

    def test_get_feedback_empty(self, client):
        """GET /api/feedback returns empty list when no feedback exists."""
        with patch("app.main.list_feedback", return_value=[]):
            resp = client.get("/api/feedback")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0
        assert data["feedback"] == []
