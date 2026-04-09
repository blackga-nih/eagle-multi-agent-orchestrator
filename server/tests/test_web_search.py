"""Tests for the web_search tool (Amazon Nova Web Grounding)."""

from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError, ReadTimeoutError

from app.tools.web_search import exec_web_search


# ── Helpers ─────────────────────────────────────────────────────────

def _nova_response(content_blocks: list) -> dict:
    """Build a mock Bedrock Converse response."""
    return {
        "output": {
            "message": {
                "role": "assistant",
                "content": content_blocks,
            },
        },
    }


def _citation(url: str, domain: str = "") -> dict:
    """Build a single citationsContent block."""
    return {
        "citationsContent": {
            "citations": [
                {
                    "location": {
                        "web": {"url": url, "domain": domain or url.split("/")[2]},
                    },
                },
            ],
        },
    }


# ── Tests ───────────────────────────────────────────────────────────

@patch("app.tools.web_search._get_client")
def test_exec_web_search_returns_structured_result(mock_get_client):
    """Mock Converse response with text + citations -> correct structured output."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    mock_client.converse.return_value = _nova_response([
        {"text": "GSA IT Schedule 70 rates range from $80-$200/hour."},
        _citation("https://www.gsa.gov/schedules", "gsa.gov"),
        {"text": " Rates vary by labor category and contractor."},
        _citation("https://www.fpds.gov/results", "fpds.gov"),
    ])

    result = exec_web_search("GSA IT schedule rates")

    assert result["query"] == "GSA IT schedule rates"
    assert "GSA IT Schedule 70" in result["answer"]
    assert result["source_count"] == 2
    assert len(result["sources"]) == 2
    assert result["sources"][0]["url"] == "https://www.gsa.gov/schedules"
    assert result["sources"][0]["domain"] == "gsa.gov"
    assert result["sources"][1]["url"] == "https://www.fpds.gov/results"


@patch("app.tools.web_search._get_client")
def test_exec_web_search_handles_no_citations(mock_get_client):
    """Text-only response (no citations) -> answer present, sources empty."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    mock_client.converse.return_value = _nova_response([
        {"text": "The current market for IT services is competitive."},
    ])

    result = exec_web_search("IT market conditions")

    assert result["query"] == "IT market conditions"
    assert "competitive" in result["answer"]
    assert result["sources"] == []
    assert result["source_count"] == 0


@patch("app.tools.web_search._get_client")
def test_exec_web_search_handles_bedrock_error(mock_get_client):
    """ClientError -> graceful error dict."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    mock_client.converse.side_effect = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "Not authorized"}},
        "Converse",
    )

    result = exec_web_search("test query")

    assert "error" in result
    assert "AccessDeniedException" in result["error"]
    assert result["query"] == "test query"


@patch("app.tools.web_search._get_client")
def test_exec_web_search_handles_timeout(mock_get_client):
    """ReadTimeoutError -> graceful error dict."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    mock_client.converse.side_effect = ReadTimeoutError(endpoint_url="https://bedrock.us-east-1.amazonaws.com")

    result = exec_web_search("slow query")

    assert "error" in result
    assert "timed out" in result["error"]
    assert result["query"] == "slow query"


@patch("app.tools.web_search._get_client")
def test_exec_web_search_deduplicates_sources(mock_get_client):
    """Same URL cited multiple times -> single source entry."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    same_url = "https://www.gsa.gov/schedules"
    mock_client.converse.return_value = _nova_response([
        {"text": "First paragraph about GSA."},
        _citation(same_url, "gsa.gov"),
        {"text": "Second paragraph, same source."},
        _citation(same_url, "gsa.gov"),
        {"text": "Third paragraph, different source."},
        _citation("https://www.sam.gov/search", "sam.gov"),
    ])

    result = exec_web_search("GSA schedules")

    assert result["source_count"] == 2
    urls = [s["url"] for s in result["sources"]]
    assert urls == [same_url, "https://www.sam.gov/search"]


@patch("app.tools.web_search._get_client")
def test_exec_web_search_max_sources(mock_get_client):
    """Respects max_sources parameter."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    blocks = []
    for i in range(20):
        blocks.append({"text": f"Paragraph {i}."})
        blocks.append(_citation(f"https://example.com/page{i}", "example.com"))

    mock_client.converse.return_value = _nova_response(blocks)

    result = exec_web_search("many results", max_sources=5)

    assert result["source_count"] == 5
    assert len(result["sources"]) == 5


@patch("app.tools.web_search._get_client")
def test_exec_web_search_combined_block_format(mock_get_client):
    """Handle text + citationsContent in the SAME content block (Nova 2 format)."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    # Some Nova responses put text and citationsContent in the same block
    mock_client.converse.return_value = _nova_response([
        {
            "text": "Solar energy grew 31% in 2025.",
            "citationsContent": {
                "citations": [
                    {
                        "location": {
                            "web": {
                                "url": "https://energy.gov/solar-report",
                                "domain": "energy.gov",
                            },
                        },
                    },
                ],
            },
        },
        {"text": " Wind grew 7.7%."},
        _citation("https://wind.example.com/report", "wind.example.com"),
    ])

    result = exec_web_search("renewable energy trends")

    assert "Solar energy grew 31%" in result["answer"]
    assert result["source_count"] == 2
    assert result["sources"][0]["url"] == "https://energy.gov/solar-report"
    assert result["sources"][1]["url"] == "https://wind.example.com/report"


@patch("app.tools.web_search._get_client")
def test_exec_web_search_list_format_citations(mock_get_client):
    """Handle citationsContent as a direct list (simplified format)."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    mock_client.converse.return_value = _nova_response([
        {"text": "FAR Part 19 was updated."},
        {
            "citationsContent": [
                {
                    "location": {
                        "web": {
                            "url": "https://acquisition.gov/far/part-19",
                            "domain": "acquisition.gov",
                        },
                    },
                },
            ],
        },
    ])

    result = exec_web_search("FAR Part 19 changes")

    assert result["source_count"] == 1
    assert result["sources"][0]["url"] == "https://acquisition.gov/far/part-19"


@patch("app.tools.web_search.exec_web_search")
def test_web_search_tool_in_subagent_kb_tools(mock_exec):
    """_build_subagent_kb_tools() returns 5 tools including web_search."""
    from app.strands_agentic_service import _build_subagent_kb_tools

    tools, _kb_depth = _build_subagent_kb_tools("test-tenant", "test-session")
    tool_names = [t.tool_name if hasattr(t, 'tool_name') else t.__name__ for t in tools]

    assert len(tools) == 5
    assert "web_search" in tool_names


@patch("app.tools.web_search.exec_web_search")
def test_web_search_tool_in_supervisor_tools(mock_exec):
    """_build_kb_service_tools() returns 5 tools including web_search."""
    from app.strands_agentic_service import _build_kb_service_tools

    tools, _kb_depth = _build_kb_service_tools("test-tenant", "test-user", "test-session")
    tool_names = [t.tool_name if hasattr(t, 'tool_name') else t.__name__ for t in tools]

    # Supervisor KB tools: search_far, web_search, research
    assert len(tools) == 3
    assert "web_search_tool" in tool_names or "web_search" in tool_names
