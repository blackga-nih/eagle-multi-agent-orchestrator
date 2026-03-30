"""Tests for document classification service.

Note on filename patterns: The FILENAME_PATTERNS regexes use `\b` word-boundary
anchors.  In Python's `re` module, underscore is a word character, so `SOW_` has
no word boundary between `W` and `_`.  Filenames must use hyphens, spaces, or
dots as word separators for `\b` to fire.  The tests below use hyphens, which
is a common real-world convention and is correctly matched by the patterns.
"""

from __future__ import annotations

import io
import json
import pathlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

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


# ---------------------------------------------------------------------------
# TestClassifyExtendedTypes — 17 new categories
# ---------------------------------------------------------------------------


class TestClassifyExtendedTypesByFilename:
    """Test filename classification for all 17 new doc types."""

    @pytest.mark.parametrize("filename,expected", [
        ("3.a. SON - Products (including Equipment and Supplies).docx", "son_products"),
        ("SON-Products-FY26.docx", "son_products"),
        ("3.b. SON - Services based on Catalog Pricing.docx", "son_services"),
        ("SON-Services-IT.docx", "son_services"),
        ("NIH COR Appointment Memorandum.docx", "cor_certification"),
        ("COR-Certification-2026.docx", "cor_certification"),
        ("DF_Buy_American_Non_Availability_Template.docx", "buy_american"),
        ("Buy-American-Exception.docx", "buy_american"),
        ("HHS SubK Plan Template - updated March 2022.doc", "subk_plan"),
        ("Subcontracting-Plan-v2.docx", "subk_plan"),
        ("hhs_subk_review_form.docx", "subk_review"),
        ("Subcontracting-Review-Report.docx", "subk_review"),
        ("Attachment A - NIH Conference or Conference Grant Request and Approval 20151404_508.docx", "conference_request"),
        ("Conference-Request-FY26.docx", "conference_request"),
        ("Attachment B - NIH Conference Request for Waiver 20151004_508.docx", "conference_waiver"),
        ("Conference-Waiver-2026.docx", "conference_waiver"),
        ("Attachment D - Promotional Item Approval Form 20172112_508.docx", "promotional_item"),
        ("Promotional-Item-Request.docx", "promotional_item"),
        ("Attachment G - Exemption Determination Template 20151305_508.docx", "exemption_determination"),
        ("Exemption-Determination-IT.docx", "exemption_determination"),
        ("DF for Mandatory-Use Waiver Template - Draft.pdf", "mandatory_use_waiver"),
        ("Mandatory-Use-Waiver.pdf", "mandatory_use_waiver"),
        ("GFP Form.pdf", "gfp_form"),
        ("GFP-Form-FY26.pdf", "gfp_form"),
        ("LSJ-GSA-BPA-CallOrders.docx", "bpa_call_order"),
        ("BPA-Call-Order-2026.docx", "bpa_call_order"),
        ("Project_Officers_Technical_Questionnare.pdf", "technical_questionnaire"),
        ("Technical-Questionnaire-v2.pdf", "technical_questionnaire"),
        ("Quotation Abstract.docx", "quotation_abstract"),
        ("Quotation-Abstract-FY26.docx", "quotation_abstract"),
        ("Receiving Report Template 20201002.docx", "receiving_report"),
        ("Receiving-Report-Q3.docx", "receiving_report"),
        ("SRB Request form.docx", "srb_request"),
        ("SRB-Request-2026.docx", "srb_request"),
    ])
    def test_extended_filename_classification(self, filename, expected):
        result = classify_by_filename(filename)
        assert result is not None, f"Failed to classify: {filename}"
        assert result.doc_type == expected, f"Expected {expected} for {filename}, got {result.doc_type}"
        assert result.confidence >= 0.9


class TestClassifyExtendedTypesByContent:
    """Test content-based classification for extended doc types."""

    @pytest.mark.parametrize("content,expected", [
        ("This statement of need covers products including equipment and supplies for the lab.", "son_products"),
        ("Statement of need for IT services including catalog pricing and maintenance.", "son_services"),
        ("COR appointment memorandum for the contracting officer representative.", "cor_certification"),
        ("Buy American Act determination. Non-availability of domestic products.", "buy_american"),
        ("Small business subcontracting plan required under FAR 19.705.", "subk_plan"),
        ("Annual subcontracting review of contractor performance.", "subk_review"),
        ("NIH conference request for the annual research symposium.", "conference_request"),
        ("Request for conference waiver due to exceptional circumstances.", "conference_waiver"),
        ("This is a promotional item approval form for branded materials and merchandise for the event.", "promotional_item"),
        ("Exemption determination for the acquisition requirement.", "exemption_determination"),
        ("Mandatory-use waiver request for alternative sourcing.", "mandatory_use_waiver"),
        ("Government furnished property form for lab equipment.", "gfp_form"),
        ("BPA call order under the blanket purchase agreement.", "bpa_call_order"),
        ("Technical questionnaire for the project officer assessment.", "technical_questionnaire"),
        ("This quotation abstract document summarizes the vendor proposals received for the acquisition requirement.", "quotation_abstract"),
        ("Receiving report for delivered equipment and materials.", "receiving_report"),
        ("This SRB request is submitted for source review board evaluation of the proposed acquisition strategy.", "srb_request"),
    ])
    def test_extended_content_classification(self, content, expected):
        result = classify_by_content(content)
        assert result is not None, f"Failed to classify content for {expected}"
        assert result.doc_type == expected, f"Expected {expected}, got {result.doc_type}"


class TestClassificationBackwardCompatible:
    """Ensure original 5 types still work at high confidence."""

    @pytest.mark.parametrize("filename,expected", [
        ("SOW-Alpha.docx", "sow"),
        ("IGCE-FY26.xlsx", "igce"),
        ("Market-Research-Report.pdf", "market_research"),
        ("J&A Sole Source.docx", "justification"),
        ("Acquisition-Plan-v2.docx", "acquisition_plan"),
    ])
    def test_core_5_filename_still_work(self, filename, expected):
        result = classify_by_filename(filename)
        assert result is not None
        assert result.doc_type == expected
        assert result.confidence >= 0.95

    def test_classify_document_integration(self):
        """Full classify_document path for a core type."""
        result = classify_document("SOW-Project.docx")
        assert result.doc_type == "sow"
        assert result.method == "filename"


class TestClassifyAllIndexCategories:
    """Verify every category in _index.json has at least one filename match."""

    @pytest.mark.skipif(
        not (pathlib.Path(__file__).resolve().parents[2] / "eagle-plugin" / "data" / "template-metadata" / "_index.json").exists(),
        reason="_index.json not in repo (generated locally)",
    )
    def test_all_index_filenames_classified(self):
        index_path = Path(__file__).resolve().parent.parent.parent / "eagle-plugin" / "data" / "template-metadata" / "_index.json"
        with open(index_path, encoding="utf-8") as f:
            index = json.load(f)

        unclassified = []
        for category, filenames in index["by_category"].items():
            classified = False
            for fn in filenames:
                result = classify_by_filename(fn)
                if result and result.doc_type == category:
                    classified = True
                    break
            if not classified:
                # Try content-based as fallback (use category name as content)
                unclassified.append((category, filenames))

        # reference_guide is intentionally low-priority and may not match all filenames
        allowed_misses = {"reference_guide"}
        actual_misses = {cat for cat, _ in unclassified} - allowed_misses
        assert not actual_misses, f"Categories with no filename match: {actual_misses}"


class TestXlsxTextExtraction:
    """Test XLSX text extraction for classification."""

    def test_xlsx_extraction(self):
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "IGCE"
        ws.append(["Item", "Cost"])
        ws.append(["Labor", "8500"])
        buf = io.BytesIO()
        wb.save(buf)

        result = extract_text_preview(
            buf.getvalue(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        assert result is not None
        assert "Labor" in result
        assert "8500" in result
