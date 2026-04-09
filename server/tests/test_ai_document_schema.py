"""Tests for ai_document_schema — canonical schema validation and normalization.

Phase 1 tests for the Canonical Schema Propagation implementation.
"""

import pytest

from app.ai_document_schema import (
    CanonicalDocType,
    CanonicalContractType,
    CanonicalAcquisitionMethod,
    normalize_doc_type,
    normalize_contract_type,
    normalize_acquisition_method,
    normalize_field_names,
    normalize_labor_category,
    is_valid_doc_type,
    get_all_doc_types,
    get_create_document_types,
    normalize_and_validate_document_payload,
    DOC_TYPE_ALIASES,
    FIELD_NAME_ALIASES,
)


# ══════════════════════════════════════════════════════════════════════════════
# DOC TYPE NORMALIZATION TESTS
# ══════════════════════════════════════════════════════════════════════════════


class TestNormalizeDocType:
    """Tests for doc_type normalization."""

    def test_already_canonical(self):
        """Canonical values pass through unchanged."""
        assert normalize_doc_type("sow") == "sow"
        assert normalize_doc_type("igce") == "igce"
        assert normalize_doc_type("market_research") == "market_research"

    def test_case_insensitive(self):
        """Doc types are normalized to lowercase."""
        assert normalize_doc_type("SOW") == "sow"
        assert normalize_doc_type("IGCE") == "igce"
        assert normalize_doc_type("Market_Research") == "market_research"

    def test_hyphen_to_underscore(self):
        """Hyphens are converted to underscores."""
        assert normalize_doc_type("market-research") == "market_research"
        assert normalize_doc_type("acquisition-plan") == "acquisition_plan"

    def test_space_to_underscore(self):
        """Spaces are converted to underscores."""
        assert normalize_doc_type("market research") == "market_research"
        assert normalize_doc_type("acquisition plan") == "acquisition_plan"

    def test_common_aliases(self):
        """Common aliases resolve to canonical values."""
        # IGCE aliases
        assert normalize_doc_type("ige") == "igce"
        assert normalize_doc_type("cost_estimate") == "igce"
        assert normalize_doc_type("independent_government_estimate") == "igce"

        # SOW aliases
        assert normalize_doc_type("statement_of_work") == "sow"
        assert normalize_doc_type("pws") == "sow"

        # J&A aliases
        assert normalize_doc_type("j&a") == "justification"
        assert normalize_doc_type("ja") == "justification"
        assert normalize_doc_type("sole_source") == "justification"

    def test_subcontracting_aliases(self):
        """Subcontracting aliases resolve correctly (critical user query fix)."""
        assert normalize_doc_type("subcontracting_plan") == "subk_plan"
        assert normalize_doc_type("subcontracting plan") == "subk_plan"
        assert normalize_doc_type("sub_k_plan") == "subk_plan"
        assert normalize_doc_type("subcontracting_review") == "subk_review"

    def test_eval_criteria_aliases(self):
        """RFP section aliases resolve to eval_criteria."""
        assert normalize_doc_type("section_l") == "eval_criteria"
        assert normalize_doc_type("section_m") == "eval_criteria"
        assert normalize_doc_type("evaluation_factors") == "eval_criteria"

    def test_empty_input(self):
        """Empty input returns empty string."""
        assert normalize_doc_type("") == ""
        assert normalize_doc_type("   ") == ""

    def test_unknown_type_passes_through(self):
        """Unknown types pass through normalized but unresolved."""
        assert normalize_doc_type("unknown_type") == "unknown_type"
        assert normalize_doc_type("UNKNOWN-TYPE") == "unknown_type"


class TestIsValidDocType:
    """Tests for doc_type validation."""

    def test_valid_core_types(self):
        """Core document types are valid."""
        assert is_valid_doc_type("sow") is True
        assert is_valid_doc_type("igce") is True
        assert is_valid_doc_type("market_research") is True
        assert is_valid_doc_type("acquisition_plan") is True
        assert is_valid_doc_type("justification") is True

    def test_valid_with_alias(self):
        """Aliases resolve to valid types."""
        assert is_valid_doc_type("ige") is True
        assert is_valid_doc_type("statement_of_work") is True
        assert is_valid_doc_type("subcontracting_plan") is True

    def test_invalid_type(self):
        """Unknown types are invalid."""
        assert is_valid_doc_type("unknown_type") is False
        assert is_valid_doc_type("not_a_real_type") is False


# ══════════════════════════════════════════════════════════════════════════════
# CONTRACT TYPE NORMALIZATION TESTS
# ══════════════════════════════════════════════════════════════════════════════


class TestNormalizeContractType:
    """Tests for contract_type normalization."""

    def test_already_canonical(self):
        """Canonical values pass through."""
        assert normalize_contract_type("ffp") == "ffp"
        assert normalize_contract_type("cpff") == "cpff"
        assert normalize_contract_type("t&m") == "t&m"

    def test_common_aliases(self):
        """Common aliases resolve to canonical values."""
        assert normalize_contract_type("firm_fixed_price") == "ffp"
        assert normalize_contract_type("firm fixed price") == "ffp"
        assert normalize_contract_type("fixed_price") == "ffp"
        assert normalize_contract_type("cost_plus_fixed_fee") == "cpff"
        assert normalize_contract_type("time_and_materials") == "t&m"
        assert normalize_contract_type("time and materials") == "t&m"

    def test_case_insensitive(self):
        """Contract types are case-insensitive."""
        assert normalize_contract_type("FFP") == "ffp"
        assert normalize_contract_type("CPFF") == "cpff"
        assert normalize_contract_type("T&M") == "t&m"

    def test_hyphenated_types(self):
        """Hyphenated types like fp-epa work."""
        assert normalize_contract_type("fp-epa") == "fp-epa"
        assert normalize_contract_type("fp_epa") == "fp-epa"

    def test_unknown_returns_none(self):
        """Unknown contract types return None."""
        assert normalize_contract_type("unknown") is None
        assert normalize_contract_type("") is None
        assert normalize_contract_type(None) is None


# ══════════════════════════════════════════════════════════════════════════════
# ACQUISITION METHOD NORMALIZATION TESTS
# ══════════════════════════════════════════════════════════════════════════════


class TestNormalizeAcquisitionMethod:
    """Tests for acquisition_method normalization."""

    def test_already_canonical(self):
        """Canonical values pass through."""
        assert normalize_acquisition_method("negotiated") == "negotiated"
        assert normalize_acquisition_method("sap") == "sap"
        assert normalize_acquisition_method("sole_source") == "sole_source"

    def test_common_aliases(self):
        """Common aliases resolve to canonical values."""
        assert normalize_acquisition_method("full_and_open") == "negotiated"
        assert normalize_acquisition_method("full and open") == "negotiated"
        assert normalize_acquisition_method("simplified_acquisition") == "sap"
        assert normalize_acquisition_method("simplified") == "sap"
        assert normalize_acquisition_method("far part 15") == "negotiated"
        assert normalize_acquisition_method("far part 13") == "sap"

    def test_unknown_returns_none(self):
        """Unknown methods return None."""
        assert normalize_acquisition_method("unknown") is None
        assert normalize_acquisition_method("") is None


# ══════════════════════════════════════════════════════════════════════════════
# FIELD NAME NORMALIZATION TESTS
# ══════════════════════════════════════════════════════════════════════════════


class TestNormalizeFieldNames:
    """Tests for field name normalization."""

    def test_common_aliases(self):
        """Common field aliases are normalized."""
        data = {
            "requirement": "Build a cloud platform",
            "estimated_cost": 500000,
            "competition_type": "full_and_open",
        }
        result = normalize_field_names(data)

        assert "description" in result
        assert result["description"] == "Build a cloud platform"
        assert "estimated_value" in result
        assert result["estimated_value"] == 500000
        assert "competition" in result

    def test_preserves_canonical_keys(self):
        """Canonical keys are preserved."""
        data = {
            "description": "Already canonical",
            "estimated_value": 100000,
        }
        result = normalize_field_names(data)

        assert result["description"] == "Already canonical"
        assert result["estimated_value"] == 100000

    def test_preserves_unknown_keys(self):
        """Unknown keys are preserved for downstream processing."""
        data = {
            "custom_field": "custom value",
            "another_field": 123,
        }
        result = normalize_field_names(data)

        assert result["custom_field"] == "custom value"
        assert result["another_field"] == 123

    def test_no_overwrite(self):
        """Canonical key is not overwritten if already present."""
        data = {
            "description": "Canonical value",
            "requirement": "Alias value",  # Should not overwrite description
        }
        result = normalize_field_names(data)

        assert result["description"] == "Canonical value"


# ══════════════════════════════════════════════════════════════════════════════
# LABOR CATEGORY NORMALIZATION TESTS
# ══════════════════════════════════════════════════════════════════════════════


class TestNormalizeLaborCategory:
    """Tests for labor category normalization."""

    def test_common_aliases(self):
        """Common labor aliases are normalized."""
        assert normalize_labor_category("pm") == "project manager"
        assert normalize_labor_category("senior dev") == "senior software engineer"
        assert normalize_labor_category("sr developer") == "senior software engineer"
        assert normalize_labor_category("sre") == "devops engineer"
        assert normalize_labor_category("dba") == "database administrator"

    def test_title_case_fallback(self):
        """Unknown categories get title-cased."""
        assert normalize_labor_category("custom role") == "Custom Role"
        assert normalize_labor_category("SPECIAL POSITION") == "Special Position"


# ══════════════════════════════════════════════════════════════════════════════
# PAYLOAD VALIDATION TESTS
# ══════════════════════════════════════════════════════════════════════════════


class TestNormalizeAndValidateDocumentPayload:
    """Tests for the canonical validation entrypoint."""

    def test_basic_normalization(self):
        """Basic payload normalization works."""
        result = normalize_and_validate_document_payload(
            raw_doc_type="statement_of_work",
            title="Cloud Hosting SOW",
            data={"requirement": "Build a cloud platform"},
        )

        assert result.doc_type == "sow"
        assert result.title == "Cloud Hosting SOW"
        assert result.data["description"] == "Build a cloud platform"
        assert "doc_type: statement_of_work → sow" in result.normalized_aliases

    def test_subcontracting_plan_normalization(self):
        """Subcontracting plan aliases work (critical user query fix)."""
        result = normalize_and_validate_document_payload(
            raw_doc_type="subcontracting_plan",
            title="Subcontracting Plan",
            data={},
        )

        assert result.doc_type == "subk_plan"
        assert "doc_type: subcontracting_plan → subk_plan" in result.normalized_aliases

    def test_contract_type_normalization(self):
        """Contract type in data is normalized."""
        result = normalize_and_validate_document_payload(
            raw_doc_type="sow",
            title="Test SOW",
            data={"contract_type": "firm_fixed_price"},
        )

        assert result.data["contract_type"] == "ffp"

    def test_unknown_doc_type_warning(self):
        """Unknown doc_type generates a warning."""
        result = normalize_and_validate_document_payload(
            raw_doc_type="unknown_type",
            title="Test",
            data={},
        )

        assert result.doc_type == "unknown_type"
        assert any("Unknown doc_type" in w for w in result.warnings)

    def test_unknown_contract_type_warning(self):
        """Unknown contract_type generates a warning."""
        result = normalize_and_validate_document_payload(
            raw_doc_type="sow",
            title="Test SOW",
            data={"contract_type": "invalid_contract_type"},
        )

        assert any("Unknown contract_type" in w for w in result.warnings)

    def test_igce_specific_fields(self):
        """IGCE-specific fields are handled."""
        result = normalize_and_validate_document_payload(
            raw_doc_type="igce",
            title="Test IGCE",
            data={
                "line_items": [{"description": "pm", "rate": 150, "hours": 1000}],
                "period_months": 12,
            },
        )

        assert result.doc_type == "igce"
        assert "line_items" in result.data
        assert "period_months" in result.data

    def test_empty_data_handled(self):
        """Empty or None data is handled gracefully."""
        result = normalize_and_validate_document_payload(
            raw_doc_type="sow",
            title="Test",
            data=None,
        )

        assert result.doc_type == "sow"
        assert result.warnings == []  # No warnings for empty data
        assert result.title == "Test"


# ══════════════════════════════════════════════════════════════════════════════
# REGRESSION TESTS — Known drift cases
# ══════════════════════════════════════════════════════════════════════════════


class TestRegressionCases:
    """Regression tests for known schema drift cases."""

    def test_son_alias(self):
        """'Son' variant mentioned in ticket resolves correctly."""
        # The ticket mentioned "Son" as a drift variant
        assert normalize_doc_type("son") == "son_products"
        assert normalize_doc_type("SON") == "son_products"

    def test_sb_review_alias(self):
        """'Sb Review' variant resolves correctly."""
        # The ticket mentioned "Sb Review" as a drift variant
        assert normalize_doc_type("sb_review") == "sb_review"
        assert normalize_doc_type("small_business_review") == "sb_review"

    def test_requirement_to_description(self):
        """'requirement' field normalizes to 'description'."""
        data = {"requirement": "Test requirement text"}
        result = normalize_field_names(data)
        assert result.get("description") == "Test requirement text"

    def test_estimated_cost_to_estimated_value(self):
        """'estimated_cost' field normalizes to 'estimated_value'."""
        data = {"estimated_cost": 500000}
        result = normalize_field_names(data)
        assert result.get("estimated_value") == 500000

    def test_full_and_open_to_negotiated(self):
        """'full_and_open' acquisition method normalizes to 'negotiated'."""
        assert normalize_acquisition_method("full_and_open") == "negotiated"
        assert normalize_acquisition_method("full and open") == "negotiated"


# ══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTION TESTS
# ══════════════════════════════════════════════════════════════════════════════


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_get_all_doc_types(self):
        """get_all_doc_types returns all enum values."""
        all_types = get_all_doc_types()
        assert "sow" in all_types
        assert "igce" in all_types
        assert len(all_types) > 20  # We have many doc types

    def test_get_create_document_types(self):
        """get_create_document_types returns supported types."""
        types = get_create_document_types()
        assert "sow" in types
        assert "igce" in types
        assert "subk_plan" in types  # Now included after fix
        assert isinstance(types, frozenset)
