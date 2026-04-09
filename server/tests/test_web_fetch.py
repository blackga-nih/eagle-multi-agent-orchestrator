"""Tests for the web_fetch tool (URL → clean markdown)."""

from unittest.mock import MagicMock, patch

import httpx

from app.tools.web_fetch import exec_web_fetch


# ── Helpers ─────────────────────────────────────────────────────────

SAMPLE_HTML = """
<html>
<head><title>GSA IT Schedule Rates</title></head>
<body>
<nav><a href="/">Home</a></nav>
<main>
<h1>IT Schedule 70 Rates</h1>
<p>Labor rates for <strong>2026</strong> range from $80 to $200 per hour.</p>
<ul>
<li>Software Developer: $120/hr</li>
<li>Project Manager: $150/hr</li>
</ul>
<table>
<tr><th>Category</th><th>Rate</th></tr>
<tr><td>Junior Dev</td><td>$80</td></tr>
</table>
</main>
<footer>Copyright GSA</footer>
</body>
</html>
"""


def _mock_response(html: str, status_code: int = 200, content_type: str = "text/html"):
    """Build a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = html
    resp.headers = {"content-type": content_type}
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"HTTP {status_code}", request=MagicMock(), response=resp,
        )
    return resp


# ── Tests ───────────────────────────────────────────────────────────

@patch("app.tools.web_fetch.httpx.Client")
def test_exec_web_fetch_returns_markdown(mock_client_cls):
    """HTML page → clean markdown with title."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
    mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = _mock_response(SAMPLE_HTML)

    result = exec_web_fetch("https://www.gsa.gov/schedules")

    assert result["url"] == "https://www.gsa.gov/schedules"
    assert result["domain"] == "www.gsa.gov"
    assert result["title"] == "GSA IT Schedule Rates"
    assert "IT Schedule 70 Rates" in result["content"]
    assert "$120/hr" in result["content"]
    assert result["truncated"] is False
    # Boilerplate should be stripped
    assert "Copyright GSA" not in result["content"]
    assert "Home" not in result["content"]  # nav stripped


@patch("app.tools.web_fetch.httpx.Client")
def test_exec_web_fetch_strips_scripts_and_styles(mock_client_cls):
    """Scripts and styles should be removed."""
    html = """
    <html><head><title>Test</title><style>body{color:red}</style></head>
    <body><script>alert('xss')</script><p>Clean content</p></body></html>
    """
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
    mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = _mock_response(html)

    result = exec_web_fetch("https://example.com/page")

    assert "alert" not in result["content"]
    assert "color:red" not in result["content"]
    assert "Clean content" in result["content"]


@patch("app.tools.web_fetch.httpx.Client")
def test_exec_web_fetch_handles_timeout(mock_client_cls):
    """Timeout → graceful error."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
    mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
    mock_client.get.side_effect = httpx.TimeoutException("timed out")

    result = exec_web_fetch("https://slow.example.com")

    assert "error" in result
    assert "timed out" in result["error"]


@patch("app.tools.web_fetch.httpx.Client")
def test_exec_web_fetch_handles_http_error(mock_client_cls):
    """HTTP 404 → error dict."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
    mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = _mock_response("Not Found", status_code=404)

    result = exec_web_fetch("https://example.com/missing")

    assert "error" in result
    assert "404" in result["error"]


def test_exec_web_fetch_rejects_invalid_scheme():
    """Non-http/https URL → error."""
    result = exec_web_fetch("ftp://files.example.com/data.csv")

    assert "error" in result
    assert "scheme" in result["error"].lower()


def test_exec_web_fetch_rejects_empty_domain():
    """URL with no domain → error."""
    result = exec_web_fetch("https://")

    assert "error" in result


@patch("app.tools.web_fetch.httpx.Client")
def test_exec_web_fetch_rejects_non_html(mock_client_cls):
    """PDF/JSON → error (not HTML)."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
    mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = _mock_response("{}", content_type="application/json")

    result = exec_web_fetch("https://api.example.com/data")

    assert "error" in result
    assert "Not an HTML page" in result["error"]


@patch("app.tools.web_fetch.httpx.Client")
def test_exec_web_fetch_truncates_long_content(mock_client_cls):
    """Content over MAX_CONTENT_CHARS (50K) → truncated=True."""
    long_html = f"<html><body><p>{'x' * 60000}</p></body></html>"
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
    mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = _mock_response(long_html)

    result = exec_web_fetch("https://example.com/long")

    assert result["truncated"] is True
    assert len(result["content"]) <= 50000


@patch("app.tools.web_fetch.exec_web_fetch")
def test_web_fetch_tool_in_subagent_kb_tools(mock_exec):
    """_build_subagent_kb_tools() returns 5 tools including web_fetch."""
    from app.strands_agentic_service import _build_subagent_kb_tools

    tools, _kb_depth = _build_subagent_kb_tools("test-tenant", "test-session")
    tool_names = [t.tool_name if hasattr(t, 'tool_name') else t.__name__ for t in tools]

    assert len(tools) == 5
    assert "web_fetch" in tool_names


@patch("app.tools.web_fetch.exec_web_fetch")
def test_web_fetch_not_in_supervisor_tools(mock_exec):
    """web_fetch was removed from supervisor — exec_web_search auto-fetches top pages."""
    from app.strands_agentic_service import _build_kb_service_tools

    tools, _kb_depth = _build_kb_service_tools("test-tenant", "test-user", "test-session")
    tool_names = [t.tool_name if hasattr(t, 'tool_name') else t.__name__ for t in tools]

    # Supervisor KB tools: search_far, web_search, research (web_fetch removed — auto-fetched)
    assert len(tools) == 3
    assert "web_fetch" not in tool_names
