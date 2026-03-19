"""Tests for document classification service.

Note on filename patterns: The FILENAME_PATTERNS regexes use `\b` word-boundary
anchors.  In Python's `re` module, underscore is a word character, so `SOW_` has
no word boundary between `W` and `_`.  Filenames must use hyphens, spaces, or
dots as word separators for `\b` to fire.  The tests below use hyphens, which
is a common real-world convention and is correctly matched by the patterns.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.document_classification_service import (
    ClassificationResult,
    _clean_filename_for_title,
    classify_by_content,
    classify_by_filename,
    classify_document,
    extract_text_preview,
)


# ---------------------------------------------------------------------------
# TestClassifyDocumentByFilename
# ---------------------------------------------------------------------------


class TestClassifyDocumentByFilename:
    def test_sow_filename(self):
        # Hyphen separator gives \b boundary between "SOW" and "-"
        result = classify_by_filename("SOW-Project-Alpha.docx")
        assert result is not None
        assert result.doc_type == "sow"

    def test_igce_filename(self):
        result = classify_by_filename("IGCE-FY26.xlsx")
        assert result is not None
        assert result.doc_type == "igce"

    def test_market_research_filename(self):
        # "market-research" matches the market[-_\s]?research pattern
        result = classify_by_filename("Market-Research-Report.pdf")
        assert result is not None
        assert result.doc_type == "market_research"

    def test_justification_filename(self):
        # "J&A" is matched by j[&]?a — the & is not a word char so \b fires
        result = classify_by_filename("J&A Sole Source.docx")
        assert result is not None
        assert result.doc_type == "justification"

    def test_acquisition_plan_filename(self):
        # "acquisition-plan" with hyphen separator
        result = classify_by_filename("Acquisition-Plan-v2.docx")
        assert result is not None
        assert result.doc_type == "acquisition_plan"

    def test_unknown_filename(self):
        result = classify_by_filename("random-notes.txt")
        assert result is None

    def test_case_insensitive(self):
        upper_result = classify_by_filename("SOW-Alpha.docx")
        lower_result = classify_by_filename("sow-alpha.docx")
        assert upper_result is not None
        assert lower_result is not None
        assert upper_result.doc_type == lower_result.doc_type == "sow"

    def test_confidence_high_for_filename_match(self):
        result = classify_by_filename("SOW-Project-Alpha.docx")
        assert result is not None
        assert result.confidence >= 0.9


# ---------------------------------------------------------------------------
# TestClassifyDocumentByContent
# ---------------------------------------------------------------------------


class TestClassifyDocumentByContent:
    def test_sow_keywords_in_content(self):
        content = (
            "This is the statement of work for the project. "
            "The period of performance shall be twelve months. "
            "All deliverables must meet the requirements listed herein."
        )
        result = classify_by_content(content)
        assert result is not None
        assert result.doc_type == "sow"

    def test_igce_keywords_in_content(self):
        content = (
            "This document presents the independent government cost estimate "
            "for the proposed acquisition. Labor rates and overhead are included."
        )
        result = classify_by_content(content)
        assert result is not None
        assert result.doc_type == "igce"

    def test_market_research_keywords(self):
        content = (
            "The market research conducted by the contracting office identified "
            "three qualified vendors. The vendor analysis shows competitive pricing."
        )
        result = classify_by_content(content)
        assert result is not None
        assert result.doc_type == "market_research"

    def test_justification_keywords(self):
        content = (
            "This justification and approval is prepared in accordance with FAR 6.3. "
            "Sole source justification is required because only one responsible source exists."
        )
        result = classify_by_content(content)
        assert result is not None
        assert result.doc_type == "justification"

    def test_mixed_keywords_highest_confidence_wins(self):
        # IGCE "independent government cost estimate" scores 0.95.
        # SOW "period of performance" scores only 0.7.
        # The IGCE pattern must win.
        content = (
            "This independent government cost estimate covers the period of performance. "
            "The total estimated cost accounts for all labor and overhead."
        )
        result = classify_by_content(content)
        assert result is not None
        assert result.doc_type == "igce"
        assert result.confidence == 0.95


# ---------------------------------------------------------------------------
# TestExtractTextPreview
# ---------------------------------------------------------------------------


class TestExtractTextPreview:
    def test_plain_text_extraction(self):
        body = b"This is plain text content for classification."
        result = extract_text_preview(body, "text/plain")
        assert result == "This is plain text content for classification."

    def test_markdown_extraction(self):
        body = b"# Heading\n\nSome **markdown** content."
        result = extract_text_preview(body, "text/markdown")
        assert result == "# Heading\n\nSome **markdown** content."

    def test_docx_extraction(self):
        with patch("app.document_classification_service._extract_docx_text") as mock_extract:
            mock_extract.return_value = (
                "Statement of Work paragraph one.\nPeriod of performance is twelve months."
            )
            result = extract_text_preview(
                b"fake-docx-bytes",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        assert result is not None
        assert "Statement of Work" in result

    def test_pdf_extraction(self):
        with patch("app.document_classification_service._extract_pdf_text") as mock_extract:
            mock_extract.return_value = "Independent Government Cost Estimate page one text."
            result = extract_text_preview(b"fake-pdf-bytes", "application/pdf")
        assert result is not None
        assert "Independent Government Cost Estimate" in result

    def test_unsupported_type_returns_none(self):
        result = extract_text_preview(b"\x89PNG\r\n\x1a\n", "image/png")
        assert result is None

    def test_max_chars_truncation(self):
        body = b"A" * 10000
        result = extract_text_preview(body, "text/plain", max_chars=100)
        assert result is not None
        assert len(result) == 100


# ---------------------------------------------------------------------------
# TestCleanFilenameForTitle
# ---------------------------------------------------------------------------


class TestCleanFilenameForTitle:
    def test_removes_extension(self):
        result = _clean_filename_for_title("document.docx")
        assert result == "Document"

    def test_removes_version_numbers(self):
        # "SOW_v2.docx" → strip ext → "SOW_v2"
        # replace separators → "SOW v2"
        # remove version token → "SOW "
        # strip + title case → "Sow"
        result = _clean_filename_for_title("SOW_v2.docx")
        assert result == "Sow"

    def test_title_cases(self):
        result = _clean_filename_for_title("market_research_report.pdf")
        assert result == "Market Research Report"
