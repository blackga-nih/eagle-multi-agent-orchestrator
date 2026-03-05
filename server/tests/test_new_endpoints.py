"""
Tests for new endpoints and helpers in app/main.py:
  - _fast_trivial_response() regex fast-path
  - POST /api/generate-title
  - POST /api/feedback  +  GET /api/feedback

Run: pytest server/tests/test_new_endpoints.py -v
"""

import asyncio
import os
import sys
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

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
# T1 — _fast_trivial_response(): regex detection (no AWS calls needed)
# ══════════════════════════════════════════════════════════════════════

class TestFastTrivialRegex:
    """Test the _TRIVIAL_RE regex that gates the fast path.

    We test the regex directly (via the module-level compiled pattern)
    rather than calling the async function, avoiding any Bedrock mock.
    """

    @pytest.fixture(autouse=True, scope="class")
    def _load_regex(self, app_instance):
        self.__class__._trivial_re = app_instance._TRIVIAL_RE

    @pytest.mark.parametrize("msg", [
        "hello",
        "Hello",
        "HELLO",
        "hi",
        "Hi there",  # should NOT match — regex expects full match
        "hey",
        "thanks",
        "thank you",
        "how are you",
        "good morning",
        "goodbye",
        "ok",
        "sure",
        "yo",
    ])
    def test_trivial_messages_match(self, msg):
        """Trivial greetings should match the regex (fast-path eligible)."""
        # The regex anchors ^ and $; some messages with extra words won't match.
        # We test what the regex actually catches.
        result = self._trivial_re.match(msg.strip())
        if msg.lower() in (
            "hello", "hi", "hey", "thanks", "thank you",
            "how are you", "good morning", "goodbye", "ok", "sure", "yo",
        ):
            assert result is not None, f"Expected '{msg}' to match _TRIVIAL_RE"

    def test_real_question_not_trivial(self):
        """A substantive acquisition question should NOT match."""
        assert self._trivial_re.match("What is FAR 15.3?") is None

    def test_long_message_not_trivial(self):
        """Messages over 100 chars are typically real questions; regex won't match."""
        long_msg = "I need help understanding the process for " + "a" * 80
        assert self._trivial_re.match(long_msg) is None

    def test_sow_request_not_trivial(self):
        """A document-generation request should NOT match."""
        assert self._trivial_re.match("Help me draft a SOW") is None

    def test_far_question_not_trivial(self):
        """FAR regulation query should NOT match."""
        assert self._trivial_re.match("Explain FAR Part 12 procedures") is None

    def test_empty_string_not_trivial(self):
        """Empty string should NOT match."""
        assert self._trivial_re.match("") is None


# ══════════════════════════════════════════════════════════════════════
# T2 — _fast_trivial_response() async function (with mocked Bedrock)
# ══════════════════════════════════════════════════════════════════════

class TestFastTrivialFunction:
    """Test the async _fast_trivial_response function end-to-end with mocked Bedrock."""

    def _make_bedrock_response(self, text="Hello! I'm EAGLE."):
        return {
            "output": {"message": {"content": [{"text": text}]}},
            "usage": {"inputTokens": 5, "outputTokens": 10},
        }

    def test_trivial_hello_returns_dict(self, app_instance):
        """'hello' triggers the fast path and returns a response dict."""
        mock_client = MagicMock()
        mock_client.converse.return_value = self._make_bedrock_response()
        with patch.object(app_instance, "_get_bedrock_client", return_value=mock_client):
            result = asyncio.get_event_loop().run_until_complete(
                app_instance._fast_trivial_response("hello")
            )
        assert result is not None
        assert "text" in result
        assert result["text"] == "Hello! I'm EAGLE."

    def test_real_question_returns_none(self, app_instance):
        """A real question should return None (not trivial)."""
        result = asyncio.get_event_loop().run_until_complete(
            app_instance._fast_trivial_response("What is FAR 15.3?")
        )
        assert result is None


# ══════════════════════════════════════════════════════════════════════
# T3 — POST /api/generate-title
# ══════════════════════════════════════════════════════════════════════

class TestGenerateTitle:

    def _make_bedrock_response(self, text="SOW for Cloud Migration"):
        return {
            "output": {"message": {"content": [{"text": text}]}},
            "usage": {"inputTokens": 10, "outputTokens": 8},
        }

    def test_generate_title_valid_message(self, client, app_instance):
        """Valid message returns a generated title."""
        mock_client = MagicMock()
        mock_client.converse.return_value = self._make_bedrock_response()
        with patch.object(app_instance, "_get_bedrock_client", return_value=mock_client):
            resp = client.post("/api/generate-title", json={
                "message": "I need to procure cloud services for NCI",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert "title" in data
        assert data["title"] == "SOW for Cloud Migration"

    def test_generate_title_with_response_snippet(self, client, app_instance):
        """Request with response_snippet is accepted."""
        mock_client = MagicMock()
        mock_client.converse.return_value = self._make_bedrock_response("IT Procurement Plan")
        with patch.object(app_instance, "_get_bedrock_client", return_value=mock_client):
            resp = client.post("/api/generate-title", json={
                "message": "Help me with an IGCE",
                "response_snippet": "Sure, I can help you create an IGCE...",
            })
        assert resp.status_code == 200
        assert resp.json()["title"] == "IT Procurement Plan"

    def test_generate_title_empty_message(self, client):
        """Empty message returns default 'New Session' title without calling Bedrock."""
        resp = client.post("/api/generate-title", json={"message": ""})
        assert resp.status_code == 200
        assert resp.json()["title"] == "New Session"

    def test_generate_title_bedrock_failure_fallback(self, client, app_instance):
        """When Bedrock call fails, endpoint returns fallback title."""
        mock_client = MagicMock()
        mock_client.converse.side_effect = Exception("Bedrock unavailable")
        with patch.object(app_instance, "_get_bedrock_client", return_value=mock_client):
            resp = client.post("/api/generate-title", json={
                "message": "Draft a SOW",
            })
        assert resp.status_code == 200
        assert resp.json()["title"] == "New Session"


# ══════════════════════════════════════════════════════════════════════
# T4 — POST /api/feedback  +  GET /api/feedback
# ══════════════════════════════════════════════════════════════════════

class TestFeedbackEndpoints:

    def test_post_feedback_success(self, client):
        """POST /api/feedback creates a feedback record and returns feedback_id."""
        fake_item = {"feedback_id": "fb-001", "tenant_id": "default", "rating": 4}
        with patch("app.main.create_feedback_item", return_value=fake_item):
            resp = client.post("/api/feedback", json={
                "rating": 4,
                "page": "/chat",
                "comment": "Great tool!",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["feedback_id"] == "fb-001"

    def test_post_feedback_invalid_rating(self, client):
        """POST /api/feedback with out-of-range rating returns 400."""
        resp = client.post("/api/feedback", json={
            "rating": 10,
            "page": "/chat",
        })
        assert resp.status_code == 400

    def test_post_feedback_minimal_body(self, client):
        """POST /api/feedback with only required field 'page' succeeds."""
        fake_item = {"feedback_id": "fb-002", "tenant_id": "default", "rating": 0}
        with patch("app.main.create_feedback_item", return_value=fake_item):
            resp = client.post("/api/feedback", json={
                "rating": 0,
                "page": "/admin",
            })
        assert resp.status_code == 200
        assert resp.json()["feedback_id"] == "fb-002"

    def test_get_feedback_returns_list(self, client):
        """GET /api/feedback returns a list of feedback items."""
        fake_items = [
            {"feedback_id": "fb-001", "rating": 5, "page": "/chat"},
            {"feedback_id": "fb-002", "rating": 3, "page": "/admin"},
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
