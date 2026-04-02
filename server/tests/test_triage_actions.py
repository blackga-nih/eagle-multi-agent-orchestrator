"""
Tests for the triage plan action endpoint (GET /api/triage/action).

Covers HMAC signature verification, JIRA label updates, GitHub dispatch,
and HTML response rendering.
"""

from unittest.mock import MagicMock, patch

import pytest


# ── HMAC helpers ───────────────────────────────────────────────────────


def test_compute_sig_deterministic():
    """compute_sig returns a stable 16-char hex string."""
    from app.routers.triage_actions import compute_sig

    sig1 = compute_sig("approve", "triage-001")
    sig2 = compute_sig("approve", "triage-001")
    assert sig1 == sig2
    assert len(sig1) == 16


def test_compute_sig_differs_by_action():
    """Different actions produce different signatures."""
    from app.routers.triage_actions import compute_sig

    assert compute_sig("approve", "t1") != compute_sig("deny", "t1")


def test_compute_sig_differs_by_id():
    """Different triage IDs produce different signatures."""
    from app.routers.triage_actions import compute_sig

    assert compute_sig("approve", "t1") != compute_sig("approve", "t2")


def test_verify_sig_accepts_valid():
    """verify_sig returns True for a correctly computed signature."""
    from app.routers.triage_actions import compute_sig, verify_sig

    sig = compute_sig("approve", "triage-001")
    assert verify_sig("approve", "triage-001", sig) is True


def test_verify_sig_rejects_invalid():
    """verify_sig returns False for a wrong signature."""
    from app.routers.triage_actions import verify_sig

    assert verify_sig("approve", "triage-001", "bad_signature_00") is False


# ── Endpoint tests ────────────────────────────────────────────────────


@pytest.fixture
def triage_client():
    """Create a TestClient with the triage actions router mounted."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.routers.triage_actions import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_invalid_sig_returns_403(triage_client):
    """A bad HMAC signature returns 403 with error HTML."""
    resp = triage_client.get(
        "/api/triage/action",
        params={
            "action": "approve",
            "triage_id": "t-001",
            "ticket": "EAGLE-1",
            "sig": "0000000000000000",
        },
    )
    assert resp.status_code == 403
    assert "Invalid Link" in resp.text


def test_unknown_action_returns_400(triage_client):
    """An unrecognized action returns 400."""
    from app.routers.triage_actions import compute_sig

    sig = compute_sig("bogus", "t-001")
    resp = triage_client.get(
        "/api/triage/action",
        params={"action": "bogus", "triage_id": "t-001", "sig": sig},
    )
    assert resp.status_code == 400
    assert "Unknown Action" in resp.text


def test_approve_updates_jira_and_dispatches(triage_client):
    """Approve action adds JIRA label and fires GitHub dispatch."""
    from app.routers.triage_actions import compute_sig

    sig = compute_sig("approve", "t-001")

    with patch("app.routers.triage_actions.update_labels") as mock_labels, \
         patch("app.routers.triage_actions.add_comment") as mock_comment, \
         patch("app.routers.triage_actions._dispatch_github", return_value=True) as mock_dispatch:

        resp = triage_client.get(
            "/api/triage/action",
            params={
                "action": "approve",
                "triage_id": "t-001",
                "ticket": "EAGLE-42",
                "sig": sig,
            },
        )

    assert resp.status_code == 200
    assert "Approved" in resp.text
    mock_labels.assert_called_once_with("EAGLE-42", add=["triage-approved"])
    mock_comment.assert_called_once()
    assert "EAGLE-42" in mock_comment.call_args[0][0]
    mock_dispatch.assert_called_once_with("triage-approved", "EAGLE-42", "t-001")


def test_deny_updates_jira_no_dispatch(triage_client):
    """Deny action adds JIRA label but does NOT fire GitHub dispatch."""
    from app.routers.triage_actions import compute_sig

    sig = compute_sig("deny", "t-002")

    with patch("app.routers.triage_actions.update_labels") as mock_labels, \
         patch("app.routers.triage_actions.add_comment") as mock_comment, \
         patch("app.routers.triage_actions._dispatch_github") as mock_dispatch:

        resp = triage_client.get(
            "/api/triage/action",
            params={
                "action": "deny",
                "triage_id": "t-002",
                "ticket": "EAGLE-43",
                "sig": sig,
            },
        )

    assert resp.status_code == 200
    assert "Denied" in resp.text
    mock_labels.assert_called_once_with("EAGLE-43", add=["triage-denied"])
    mock_comment.assert_called_once()
    mock_dispatch.assert_not_called()


def test_delay_updates_jira_no_dispatch(triage_client):
    """Delay action adds JIRA label but does NOT fire GitHub dispatch."""
    from app.routers.triage_actions import compute_sig

    sig = compute_sig("delay", "t-003")

    with patch("app.routers.triage_actions.update_labels") as mock_labels, \
         patch("app.routers.triage_actions.add_comment") as mock_comment, \
         patch("app.routers.triage_actions._dispatch_github") as mock_dispatch:

        resp = triage_client.get(
            "/api/triage/action",
            params={
                "action": "delay",
                "triage_id": "t-003",
                "ticket": "EAGLE-44",
                "sig": sig,
            },
        )

    assert resp.status_code == 200
    assert "Delayed" in resp.text
    mock_labels.assert_called_once_with("EAGLE-44", add=["triage-delayed"])
    mock_comment.assert_called_once()
    mock_dispatch.assert_not_called()


def test_no_ticket_skips_jira(triage_client):
    """When ticket is empty, JIRA operations are skipped."""
    from app.routers.triage_actions import compute_sig

    sig = compute_sig("approve", "t-004")

    with patch("app.routers.triage_actions.update_labels") as mock_labels, \
         patch("app.routers.triage_actions.add_comment") as mock_comment, \
         patch("app.routers.triage_actions._dispatch_github", return_value=True):

        resp = triage_client.get(
            "/api/triage/action",
            params={"action": "approve", "triage_id": "t-004", "sig": sig},
        )

    assert resp.status_code == 200
    mock_labels.assert_not_called()
    mock_comment.assert_not_called()


# ── _dispatch_github unit test ────────────────────────────────────────


def test_dispatch_github_no_token():
    """_dispatch_github returns False when GH_DISPATCH_TOKEN is empty."""
    with patch("app.routers.triage_actions._GH_TOKEN", ""):
        from app.routers.triage_actions import _dispatch_github

        assert _dispatch_github("triage-approved", "EAGLE-1", "t-001") is False


def test_dispatch_github_success():
    """_dispatch_github posts to GitHub API and returns True on 204."""
    mock_resp = MagicMock()
    mock_resp.status_code = 204

    with patch("app.routers.triage_actions._GH_TOKEN", "ghp_test123"), \
         patch("app.routers.triage_actions._GH_REPO", "CBIIT/sm_eagle"), \
         patch("app.routers.triage_actions.httpx") as mock_httpx:
        mock_httpx.post.return_value = mock_resp

        from app.routers.triage_actions import _dispatch_github

        result = _dispatch_github("triage-approved", "EAGLE-1", "t-001")

    assert result is True
    mock_httpx.post.assert_called_once()
    call_args = mock_httpx.post.call_args
    assert "CBIIT/sm_eagle" in call_args[0][0]
    assert call_args[1]["json"]["event_type"] == "triage-approved"


def test_dispatch_github_failure():
    """_dispatch_github returns False on non-2xx response."""
    mock_resp = MagicMock()
    mock_resp.status_code = 422
    mock_resp.text = "Unprocessable"

    with patch("app.routers.triage_actions._GH_TOKEN", "ghp_test123"), \
         patch("app.routers.triage_actions.httpx") as mock_httpx:
        mock_httpx.post.return_value = mock_resp

        from app.routers.triage_actions import _dispatch_github

        result = _dispatch_github("triage-approved", "EAGLE-1", "t-001")

    assert result is False
