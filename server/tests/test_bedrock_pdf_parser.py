"""Tests for Bedrock PDF document parser.

Unit tests mock the Bedrock Converse API.
Integration tests (TestRealBedrock*) hit real Bedrock with the sample PDF.
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from app.bedrock_document_parser import (
    BedrockParseResult,
    _parse_response,
    parse_pdf_with_bedrock,
)

PDF_PATH = os.path.join(
    os.path.expanduser("~"),
    "Downloads",
    "Market_Research_Report___NCI_Bioinformatics_ML_Pipeline_Development_and_Clinical_Data_Analysis_R_D_Services___3_5M_CPFF_.pdf",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def pdf_bytes():
    if not os.path.exists(PDF_PATH):
        pytest.skip(f"Sample PDF not found at {PDF_PATH}")
    with open(PDF_PATH, "rb") as f:
        return f.read()


def _make_converse_response(
    text: str,
    input_tokens: int = 500,
    output_tokens: int = 1000,
) -> dict:
    """Build a mock Converse API response."""
    return {
        "output": {
            "message": {
                "role": "assistant",
                "content": [{"text": text}],
            }
        },
        "usage": {
            "inputTokens": input_tokens,
            "outputTokens": output_tokens,
        },
    }


# ---------------------------------------------------------------------------
# Unit Tests — _parse_response
# ---------------------------------------------------------------------------


class TestParseResponse:
    """Tests for the response parsing logic."""

    def test_extracts_metadata_block(self):
        text = (
            "# Market Research Report\n\nSome content here.\n\n"
            '<!-- EAGLE_META {"doc_type": "market_research", "confidence": 0.95, "title": "MR Report"} -->'
        )
        markdown, doc_type, confidence, title = _parse_response(text)
        assert doc_type == "market_research"
        assert confidence == 0.95
        assert title == "MR Report"
        assert "EAGLE_META" not in markdown
        assert "# Market Research Report" in markdown

    def test_handles_missing_metadata(self):
        text = "# Just Markdown\n\nNo metadata here."
        markdown, doc_type, confidence, title = _parse_response(text)
        assert doc_type == "unknown"
        assert confidence == 0.0
        assert markdown == text

    def test_normalizes_doc_type_aliases(self):
        text = '<!-- EAGLE_META {"doc_type": "statement_of_work", "confidence": 0.9, "title": "SOW"} -->'
        _, doc_type, _, _ = _parse_response(text)
        assert doc_type == "sow"

    def test_unknown_for_invalid_doc_type(self):
        text = '<!-- EAGLE_META {"doc_type": "banana_report", "confidence": 0.9, "title": "?"} -->'
        _, doc_type, _, _ = _parse_response(text)
        assert doc_type == "unknown"

    def test_handles_malformed_json(self):
        text = "# Content\n<!-- EAGLE_META {bad json} -->"
        markdown, doc_type, confidence, _ = _parse_response(text)
        assert doc_type == "unknown"
        assert "# Content" in markdown

    def test_strips_code_fences(self):
        text = '```markdown\n# SOW\nContent\n```\n<!-- EAGLE_META {"doc_type": "sow", "confidence": 0.9, "title": "SOW"} -->'
        markdown, doc_type, _, _ = _parse_response(text)
        assert doc_type == "sow"
        assert not markdown.startswith("```")
        assert "# SOW" in markdown


# ---------------------------------------------------------------------------
# Unit Tests — parse_pdf_with_bedrock (mocked)
# ---------------------------------------------------------------------------


class TestParsePdfMocked:
    """Tests with mocked Bedrock client."""

    def test_successful_parse(self):
        response_text = (
            "# MARKET RESEARCH REPORT\n\n## Executive Summary\n\nContent.\n\n"
            '<!-- EAGLE_META {"doc_type": "market_research", "confidence": 0.95, "title": "Market Research"} -->'
        )

        mock_client = MagicMock()
        mock_client.converse.return_value = _make_converse_response(response_text)

        with patch("app.bedrock_document_parser._get_client", return_value=mock_client):
            result = parse_pdf_with_bedrock(b"%PDF-1.4 fake", "test.pdf")

        assert result.success is True
        assert result.classification == "market_research"
        assert result.confidence == 0.95
        assert result.markdown.startswith("# MARKET RESEARCH REPORT")
        assert result.input_tokens == 500
        assert result.output_tokens == 1000

    def test_empty_body_returns_failure(self):
        result = parse_pdf_with_bedrock(b"", "empty.pdf")
        assert result.success is False
        assert "Empty" in result.error

    def test_bedrock_exception_returns_failure(self):
        mock_client = MagicMock()
        mock_client.converse.side_effect = Exception("Bedrock timeout")

        with patch("app.bedrock_document_parser._get_client", return_value=mock_client):
            result = parse_pdf_with_bedrock(b"%PDF-1.4 fake", "test.pdf")

        assert result.success is False
        assert "timeout" in result.error.lower()

    def test_empty_response_returns_failure(self):
        mock_client = MagicMock()
        mock_client.converse.return_value = _make_converse_response("")

        with patch("app.bedrock_document_parser._get_client", return_value=mock_client):
            result = parse_pdf_with_bedrock(b"%PDF-1.4 fake", "test.pdf")

        assert result.success is False

    def test_filename_sanitized_for_converse_api(self):
        """Special characters stripped from document name field."""
        response_text = '# Doc\n<!-- EAGLE_META {"doc_type": "sow", "confidence": 0.8, "title": "Doc"} -->'

        mock_client = MagicMock()
        mock_client.converse.return_value = _make_converse_response(response_text)

        with patch("app.bedrock_document_parser._get_client", return_value=mock_client):
            parse_pdf_with_bedrock(
                b"%PDF-1.4 fake",
                "My $pecial (File) [v2].pdf",
            )

        # Check the name passed to converse
        call_args = mock_client.converse.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
        doc_block = messages[0]["content"][1]["document"]
        name = doc_block["name"]
        # Should only contain allowed chars
        assert "$" not in name
        assert "." not in name
        assert "(" in name or "[" in name  # parens/brackets are allowed

    def test_doc_type_hint_included_in_prompt(self):
        response_text = '# Doc\n<!-- EAGLE_META {"doc_type": "igce", "confidence": 0.8, "title": "Doc"} -->'

        mock_client = MagicMock()
        mock_client.converse.return_value = _make_converse_response(response_text)

        with patch("app.bedrock_document_parser._get_client", return_value=mock_client):
            parse_pdf_with_bedrock(
                b"%PDF-1.4 fake",
                "cost_estimate.pdf",
                doc_type_hint="igce",
            )

        call_args = mock_client.converse.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
        text_block = messages[0]["content"][0]["text"]
        assert "igce" in text_block.lower()


# ---------------------------------------------------------------------------
# Integration Tests — Real Bedrock + Real PDF
# ---------------------------------------------------------------------------


class TestRealBedrockPdfParser:
    """Tests that hit real Bedrock. Skipped if sample PDF is missing."""

    def test_parse_market_research_pdf(self, pdf_bytes):
        """Send the real PDF to Bedrock and verify quality output."""
        result = parse_pdf_with_bedrock(pdf_bytes, "Market_Research_Report.pdf")

        assert result.success is True, f"Parse failed: {result.error}"
        assert result.classification == "market_research", (
            f"Expected market_research, got {result.classification}"
        )
        assert result.confidence >= 0.7
        assert len(result.markdown) > 500, (
            f"Markdown too short: {len(result.markdown)} chars"
        )
        # Tables should be preserved as pipe format
        assert "|" in result.markdown, "No tables found in markdown"
        assert result.input_tokens > 0
        assert result.output_tokens > 0
        assert result.suggested_title, "Expected a suggested title"

    def test_markdown_has_structure(self, pdf_bytes):
        """Verify the markdown has proper headings and sections."""
        result = parse_pdf_with_bedrock(pdf_bytes, "Market_Research_Report.pdf")

        assert result.success
        md = result.markdown
        # Should have markdown headings
        assert "# " in md, "No headings found"
        # Should have multiple sections
        assert md.count("## ") >= 2, "Too few sections"
        # Content should mention relevant terms
        md_lower = md.lower()
        assert any(
            term in md_lower
            for term in ["market", "research", "nci", "bioinformatics"]
        ), f"Expected domain terms not found in first 500 chars: {md[:500]}"
