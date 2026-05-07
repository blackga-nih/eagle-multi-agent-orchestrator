"""Tests for value-based template hint selection.

Validates that _get_template_hint() returns the correct S3 template
filename based on document type and estimated contract value.
"""

import pytest

from app.tools.create_document_support import _get_template_hint


class TestGetTemplateHintAcquisitionPlan:
    """Test template hints for Acquisition Plans."""

    def test_ap_under_sat(self):
        """AP for $200K should use Under SAT template."""
        hint = _get_template_hint("acquisition_plan", 200_000)
        assert hint == "1.a. AP Under SAT.docx"

    def test_ap_above_sat(self):
        """AP for $500K should use Above SAT template."""
        hint = _get_template_hint("acquisition_plan", 500_000)
        assert hint == "1.b AP Above SAT.docx"

    def test_ap_at_sat_boundary(self):
        """AP at exactly $350K uses Under SAT (not above)."""
        hint = _get_template_hint("acquisition_plan", 350_000)
        assert hint == "1.a. AP Under SAT.docx"

    def test_ap_above_sat_boundary(self):
        """AP at $350,001 uses Above SAT."""
        hint = _get_template_hint("acquisition_plan", 350_001)
        assert hint == "1.b AP Above SAT.docx"

    def test_ap_just_above_mpt(self):
        """AP for $20K (just above MPT) uses Under SAT."""
        hint = _get_template_hint("acquisition_plan", 20_000)
        assert hint == "1.a. AP Under SAT.docx"

    def test_ap_micro_purchase(self):
        """AP for $10K (micro-purchase) returns None (not required above MPT)."""
        hint = _get_template_hint("acquisition_plan", 10_000)
        assert hint is None

    def test_ap_at_mpt_boundary(self):
        """AP at exactly $15K (MPT) returns None."""
        hint = _get_template_hint("acquisition_plan", 15_000)
        assert hint is None

    def test_ap_large_value(self):
        """AP for $5M uses Above SAT template."""
        hint = _get_template_hint("acquisition_plan", 5_000_000)
        assert hint == "1.b AP Above SAT.docx"


class TestGetTemplateHintJustification:
    """Test template hints for Justification & Approval (J&A)."""

    def test_ja_under_sat(self):
        """J&A for $200K should use simplified template."""
        hint = _get_template_hint("justification", 200_000)
        assert hint == "6.a. Single Source J&A - up to SAT.docx"

    def test_ja_above_sat(self):
        """J&A for $500K should use default (None = full template)."""
        hint = _get_template_hint("justification", 500_000)
        assert hint is None

    def test_ja_at_sat_boundary(self):
        """J&A at exactly $350K uses simplified template."""
        hint = _get_template_hint("justification", 350_000)
        assert hint == "6.a. Single Source J&A - up to SAT.docx"

    def test_ja_above_sat_boundary(self):
        """J&A at $350,001 uses full template (returns None)."""
        hint = _get_template_hint("justification", 350_001)
        assert hint is None


class TestGetTemplateHintOtherDocTypes:
    """Test template hints for other document types."""

    def test_sow_no_hint(self):
        """SOW doesn't have value-based templates."""
        hint = _get_template_hint("sow", 500_000)
        assert hint is None

    def test_igce_no_hint(self):
        """IGCE doesn't have value-based templates."""
        hint = _get_template_hint("igce", 500_000)
        assert hint is None

    def test_market_research_no_hint(self):
        """Market Research doesn't have value-based templates."""
        hint = _get_template_hint("market_research", 500_000)
        assert hint is None

    def test_unknown_doc_type(self):
        """Unknown doc type returns None."""
        hint = _get_template_hint("unknown_type", 500_000)
        assert hint is None


class TestGetTemplateHintEdgeCases:
    """Test edge cases for template hint selection."""

    def test_none_value(self):
        """None estimated_value returns None."""
        hint = _get_template_hint("acquisition_plan", None)
        assert hint is None

    def test_invalid_string_value(self):
        """Invalid string estimated_value returns None."""
        hint = _get_template_hint("acquisition_plan", "not a number")
        assert hint is None

    def test_string_numeric_value(self):
        """String numeric value is parsed correctly."""
        hint = _get_template_hint("acquisition_plan", "500000")
        assert hint == "1.b AP Above SAT.docx"

    def test_string_with_dollar_sign(self):
        """String with dollar sign is parsed correctly."""
        hint = _get_template_hint("acquisition_plan", "$500,000")
        assert hint == "1.b AP Above SAT.docx"

    def test_string_with_commas(self):
        """String with commas is parsed correctly."""
        hint = _get_template_hint("acquisition_plan", "500,000")
        assert hint == "1.b AP Above SAT.docx"

    def test_float_value(self):
        """Float value is handled correctly."""
        hint = _get_template_hint("acquisition_plan", 500000.50)
        assert hint == "1.b AP Above SAT.docx"

    def test_zero_value(self):
        """Zero value returns None (below MPT)."""
        hint = _get_template_hint("acquisition_plan", 0)
        assert hint is None

    def test_negative_value(self):
        """Negative value returns None."""
        hint = _get_template_hint("acquisition_plan", -100_000)
        assert hint is None
