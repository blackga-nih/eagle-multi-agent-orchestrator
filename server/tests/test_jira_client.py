"""
Tests for jira_client.py — add_attachment() and update_labels().

Uses httpx mock responses to verify correct API calls and error handling
without hitting a real JIRA server.
"""

from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ────────────────────────────────────────────────────────────


def _mock_config(base_url="https://jira.example.com", api_token="test-token"):
    """Return a mock JiraConfig dataclass."""
    cfg = MagicMock()
    cfg.base_url = base_url
    cfg.api_token = api_token
    cfg.project_key = "EAGLE"
    cfg.timeout = 5.0
    return cfg


def _mock_response(status_code, json_data=None, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    if json_data is not None:
        resp.json.return_value = json_data
    return resp


# ── add_attachment ─────────────────────────────────────────────────────


def test_add_attachment_success():
    """add_attachment uploads file and returns True on 200."""
    mock_client = MagicMock()
    mock_client.post.return_value = _mock_response(200)

    with patch("app.jira_client._get_client", return_value=mock_client), \
         patch("app.jira_client._headers", return_value={"Authorization": "Bearer tok", "Content-Type": "application/json"}):
        from app.jira_client import add_attachment

        result = add_attachment("EAGLE-42", "plan.md", b"# Fix plan")

    assert result is True
    mock_client.post.assert_called_once()
    call_kwargs = mock_client.post.call_args
    assert "/attachments" in call_kwargs[0][0] or "/attachments" in str(call_kwargs)
    # Verify X-Atlassian-Token header is set
    headers = call_kwargs[1]["headers"] if "headers" in call_kwargs[1] else call_kwargs[0][1]
    assert headers.get("X-Atlassian-Token") == "no-check"
    # Content-Type should NOT be set (httpx sets multipart boundary)
    assert "Content-Type" not in headers


def test_add_attachment_failure_returns_false():
    """add_attachment returns False on non-2xx response."""
    mock_client = MagicMock()
    mock_client.post.return_value = _mock_response(403, text="Forbidden")

    with patch("app.jira_client._get_client", return_value=mock_client), \
         patch("app.jira_client._headers", return_value={"Authorization": "Bearer tok", "Content-Type": "application/json"}):
        from app.jira_client import add_attachment

        result = add_attachment("EAGLE-42", "plan.md", b"data")

    assert result is False


def test_add_attachment_exception_returns_false():
    """add_attachment returns False on network exception (never raises)."""
    mock_client = MagicMock()
    mock_client.post.side_effect = Exception("Connection refused")

    with patch("app.jira_client._get_client", return_value=mock_client), \
         patch("app.jira_client._headers", return_value={"Authorization": "Bearer tok", "Content-Type": "application/json"}):
        from app.jira_client import add_attachment

        result = add_attachment("EAGLE-42", "plan.md", b"data")

    assert result is False


def test_add_attachment_no_config_returns_false():
    """add_attachment returns False when JIRA is not configured."""
    mock_cfg = _mock_config(base_url="", api_token="")
    with patch("app.config.jira", mock_cfg):
        from app.jira_client import add_attachment

        result = add_attachment("EAGLE-42", "plan.md", b"data")

    assert result is False


# ── update_labels ──────────────────────────────────────────────────────


def test_update_labels_add_success():
    """update_labels adds labels and returns True on 204."""
    mock_client = MagicMock()
    mock_client.put.return_value = _mock_response(204)

    with patch("app.jira_client._get_client", return_value=mock_client), \
         patch("app.jira_client._headers", return_value={"Authorization": "Bearer tok", "Content-Type": "application/json"}):
        from app.jira_client import update_labels

        result = update_labels("EAGLE-42", add=["triage-approved"])

    assert result is True
    mock_client.put.assert_called_once()
    call_kwargs = mock_client.put.call_args[1]
    payload = call_kwargs["json"]
    assert payload == {"update": {"labels": [{"add": "triage-approved"}]}}


def test_update_labels_add_and_remove():
    """update_labels can add and remove labels in one call."""
    mock_client = MagicMock()
    mock_client.put.return_value = _mock_response(204)

    with patch("app.jira_client._get_client", return_value=mock_client), \
         patch("app.jira_client._headers", return_value={"Authorization": "Bearer tok", "Content-Type": "application/json"}):
        from app.jira_client import update_labels

        result = update_labels("EAGLE-42", add=["approved"], remove=["pending"])

    assert result is True
    payload = mock_client.put.call_args[1]["json"]
    ops = payload["update"]["labels"]
    assert {"add": "approved"} in ops
    assert {"remove": "pending"} in ops


def test_update_labels_empty_ops_returns_true():
    """update_labels with no add/remove is a no-op that returns True."""
    from app.jira_client import update_labels

    result = update_labels("EAGLE-42")
    assert result is True


def test_update_labels_failure_returns_false():
    """update_labels returns False on non-2xx response."""
    mock_client = MagicMock()
    mock_client.put.return_value = _mock_response(400, text="Bad request")

    with patch("app.jira_client._get_client", return_value=mock_client), \
         patch("app.jira_client._headers", return_value={"Authorization": "Bearer tok", "Content-Type": "application/json"}):
        from app.jira_client import update_labels

        result = update_labels("EAGLE-42", add=["bad-label"])

    assert result is False


def test_update_labels_exception_returns_false():
    """update_labels returns False on exception (never raises)."""
    mock_client = MagicMock()
    mock_client.put.side_effect = Exception("Timeout")

    with patch("app.jira_client._get_client", return_value=mock_client), \
         patch("app.jira_client._headers", return_value={"Authorization": "Bearer tok", "Content-Type": "application/json"}):
        from app.jira_client import update_labels

        result = update_labels("EAGLE-42", add=["label"])

    assert result is False


def test_update_labels_no_config_returns_false():
    """update_labels returns False when JIRA is not configured."""
    mock_cfg = _mock_config(base_url="", api_token="")
    with patch("app.config.jira", mock_cfg):
        from app.jira_client import update_labels

        result = update_labels("EAGLE-42", add=["label"])

    assert result is False
