"""Tests for document type aliases and title-based inference.

Validates:
  - RFP Section L/M aliases resolve to eval_criteria
  - Source selection plan aliases resolve to acquisition_plan
  - Existing doc types are not broken by new aliases
  - Title pattern matching for RFP section names
"""
import pytest


class TestDocTypeAliases:
    """Verify _normalize_create_document_doc_type resolves aliases."""

    def test_section_l_alias_resolves(self):
        from app.tools.create_document_support import _normalize_create_document_doc_type

        assert _normalize_create_document_doc_type("section_l", "") == "eval_criteria"

    def test_section_m_alias_resolves(self):
        from app.tools.create_document_support import _normalize_create_document_doc_type

        assert _normalize_create_document_doc_type("section_m", "") == "eval_criteria"

    def test_instructions_to_offerors_alias_resolves(self):
        from app.tools.create_document_support import _normalize_create_document_doc_type

        assert _normalize_create_document_doc_type("instructions_to_offerors", "") == "eval_criteria"

    def test_evaluation_factors_alias_resolves(self):
        from app.tools.create_document_support import _normalize_create_document_doc_type

        assert _normalize_create_document_doc_type("evaluation_factors", "") == "eval_criteria"

    def test_evaluation_criteria_alias_resolves(self):
        from app.tools.create_document_support import _normalize_create_document_doc_type

        assert _normalize_create_document_doc_type("evaluation_criteria", "") == "eval_criteria"

    def test_source_selection_plan_alias_resolves(self):
        from app.tools.create_document_support import _normalize_create_document_doc_type

        assert _normalize_create_document_doc_type("source_selection_plan", "") == "acquisition_plan"

    def test_ssp_alias_resolves(self):
        from app.tools.create_document_support import _normalize_create_document_doc_type

        assert _normalize_create_document_doc_type("ssp", "") == "acquisition_plan"

    def test_existing_types_unchanged(self):
        """All 10 valid doc types should normalize to themselves."""
        from app.tools.create_document_support import _normalize_create_document_doc_type

        valid_types = [
            "sow", "igce", "market_research", "justification",
            "acquisition_plan", "eval_criteria", "security_checklist",
            "section_508", "cor_certification", "contract_type_justification",
        ]
        for dt in valid_types:
            result = _normalize_create_document_doc_type(dt, "")
            assert result == dt, f"{dt} normalized to {result} instead of itself"


class TestTitleDocTypePatterns:
    """Verify _infer_doc_type_from_title handles RFP section names."""

    def test_title_instructions_to_offerors(self):
        from app.tools.create_document_support import _infer_doc_type_from_title

        assert _infer_doc_type_from_title("RFP Section L - Instructions to Offerors") == "eval_criteria"

    def test_title_section_l(self):
        from app.tools.create_document_support import _infer_doc_type_from_title

        assert _infer_doc_type_from_title("Section L Evaluation Instructions") == "eval_criteria"

    def test_title_section_m(self):
        from app.tools.create_document_support import _infer_doc_type_from_title

        assert _infer_doc_type_from_title("Section M Evaluation Criteria") == "eval_criteria"

    def test_title_source_selection_plan(self):
        from app.tools.create_document_support import _infer_doc_type_from_title

        assert _infer_doc_type_from_title("Source Selection Plan for Cloud Services") == "acquisition_plan"

    def test_existing_title_patterns_still_work(self):
        """Existing title patterns should not be broken."""
        from app.tools.create_document_support import _infer_doc_type_from_title

        assert _infer_doc_type_from_title("Statement of Work") == "sow"
        assert _infer_doc_type_from_title("IGCE for IT Services") == "igce"
        assert _infer_doc_type_from_title("Market Research Report") == "market_research"
        assert _infer_doc_type_from_title("Acquisition Plan") == "acquisition_plan"
        assert _infer_doc_type_from_title("J&A Sole Source Justification") == "justification"
