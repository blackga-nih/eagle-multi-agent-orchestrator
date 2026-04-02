"""Tests for compliance_matrix.py — deterministic procurement compliance logic.

Validates: get_requirements(), search_far(), suggest_vehicle(), execute_operation(),
and module-level constants. Pure Python — no AWS dependencies or mocking needed.
"""

import pytest

from app.compliance_matrix import (
    METHODS,
    THRESHOLD_TIERS,
    TYPES,
    _normalize_method,
    _normalize_type,
    execute_operation,
    get_requirements,
    search_far,
    suggest_vehicle,
)


# ---------------------------------------------------------------------------
# 1. get_requirements()
# ---------------------------------------------------------------------------

class TestGetRequirements:
    """Core compliance analysis for various procurement scenarios."""

    def test_micro_purchase_valid(self):
        """$10K micro-purchase with FFP returns no errors."""
        result = get_requirements(10_000, "micro", "ffp")
        assert result["errors"] == []
        assert result["method"]["id"] == "micro"
        assert result["contract_type"]["id"] == "ffp"
        assert result["competition_rules"] == "Single quote acceptable. Government purchase card preferred."

    def test_sap_valid(self):
        """$200K SAP with FFP returns no errors and correct timeline."""
        result = get_requirements(200_000, "sap", "ffp")
        assert result["errors"] == []
        assert result["method"]["id"] == "sap"
        assert result["timeline_estimate"]["min_weeks"] == 2
        assert result["timeline_estimate"]["max_weeks"] == 6

    def test_negotiated_cost_reimbursement_warnings(self):
        """$1M negotiated CPFF triggers cost-reimbursement warning."""
        result = get_requirements(1_000_000, "negotiated", "cpff")
        assert result["errors"] == []
        cr_warnings = [w for w in result["warnings"] if "Cost-reimbursement" in w]
        assert len(cr_warnings) >= 1
        assert result["risk_allocation"]["category"] == "cr"

    def test_invalid_method_returns_error(self):
        """Unknown acquisition method produces an error."""
        result = get_requirements(100_000, "bogus_method", "ffp")
        assert len(result["errors"]) == 1
        assert "Unknown acquisition method" in result["errors"][0]

    def test_invalid_type_returns_error(self):
        """Unknown contract type produces an error."""
        result = get_requirements(100_000, "sap", "bogus_type")
        assert len(result["errors"]) == 1
        assert "Unknown contract type" in result["errors"][0]

    def test_threshold_500k_triggers_sat_not_tina(self):
        """$500K triggers SAT ($350K) but not TINA ($2M per matrix.json)."""
        result = get_requirements(500_000, "negotiated", "ffp")
        triggered_values = [t["value"] for t in result["thresholds_triggered"]]
        assert 350_000 in triggered_values, "SAT threshold should be triggered"
        assert 2_000_000 not in triggered_values, "TINA threshold should NOT be triggered"

    def test_threshold_3m_triggers_tina(self):
        """$3M triggers TINA ($2M per matrix.json FAC 2025-06)."""
        result = get_requirements(3_000_000, "negotiated", "ffp")
        triggered_values = [t["value"] for t in result["thresholds_triggered"]]
        assert 2_000_000 in triggered_values, "TINA threshold should be triggered at $3M"
        # TINA compliance item should be required
        tina_items = [c for c in result["compliance_items"] if "TINA" in c["name"]]
        assert len(tina_items) == 1
        assert tina_items[0]["status"] == "required"

    def test_flag_is_it_adds_it_requirements(self):
        """is_it=True adds IT Security and Section 508 documents."""
        result = get_requirements(200_000, "sap", "ffp", flags={"is_it": True})
        doc_names = [d["name"] for d in result["documents_required"]]
        assert "IT Security & Privacy Certification" in doc_names
        compliance_names = [c["name"] for c in result["compliance_items"]]
        assert "Section 508 ICT Accessibility" in compliance_names

    def test_flag_is_human_subjects_adds_irb(self):
        """is_human_subjects=True adds Human Subjects provisions."""
        result = get_requirements(200_000, "sap", "ffp", flags={"is_human_subjects": True})
        doc_names = [d["name"] for d in result["documents_required"]]
        assert "Human Subjects Provisions" in doc_names
        compliance_names = [c["name"] for c in result["compliance_items"]]
        assert "Human Subjects Protection (45 CFR 46)" in compliance_names

    def test_sole_source_triggers_ja(self):
        """Sole source method requires J&A documentation."""
        result = get_requirements(500_000, "sole", "ffp")
        ja_docs = [d for d in result["documents_required"] if "J&A" in d["name"]]
        assert len(ja_docs) == 1
        assert ja_docs[0]["required"] is True

    def test_sole_source_under_sat_simplified(self):
        """Sole source under SAT uses simplified FAR 13.106-1(b) path."""
        result = get_requirements(280_000, "sole", "ffp")
        ja = [d for d in result["documents_required"] if "J&A" in d["name"]][0]
        assert ja["required"] is True
        assert ja["variant"] == "simplified_under_sat"
        assert "13.106-1(b)" in ja["note"]
        assert ja["authority"] == "FAR 13.106-1(b)"
        assert ja["template_hint"] == "6.a. Single Source J&A - up to SAT.docx"
        assert "13.106-1(b)" in result["competition_rules"]

    def test_sole_source_over_sat_full_ja(self):
        """Sole source over SAT uses full FAR 6.302/6.304 path."""
        result = get_requirements(500_000, "sole", "ffp")
        ja = [d for d in result["documents_required"] if "J&A" in d["name"]][0]
        assert ja["required"] is True
        assert ja["variant"] == "full"
        assert "6.304" in ja["note"]
        assert "FAR 6.302" in result["competition_rules"]

    def test_sole_source_at_sat_boundary(self):
        """Sole source at exactly SAT ($350K) uses simplified path."""
        result = get_requirements(350_000, "sole", "ffp")
        ja = [d for d in result["documents_required"] if "J&A" in d["name"]][0]
        assert ja["variant"] == "simplified_under_sat"

    def test_sole_source_above_sat_boundary(self):
        """Sole source at $350,001 uses full J&A path."""
        result = get_requirements(350_001, "sole", "ffp")
        ja = [d for d in result["documents_required"] if "J&A" in d["name"]][0]
        assert ja["variant"] == "full"

    def test_micro_purchase_exceeds_mpt_error(self):
        """Micro-purchase above $15K produces an error."""
        result = get_requirements(20_000, "micro", "ffp")
        assert any("exceeds MPT" in e for e in result["errors"])

    def test_sap_exceeds_sat_error(self):
        """SAP above $350K produces an error."""
        result = get_requirements(400_000, "sap", "ffp")
        assert any("exceeds SAT" in e for e in result["errors"])

    def test_tm_loe_warning(self):
        """T&M contract type triggers LEAST PREFERRED warning."""
        result = get_requirements(200_000, "sap", "tm")
        assert any("LEAST PREFERRED" in w for w in result["warnings"])

    def test_fee_caps_for_cr_rd(self):
        """Cost-reimbursement R&D includes 15% fee cap."""
        result = get_requirements(1_000_000, "negotiated", "cpff", flags={"is_rd": True})
        assert any("15%" in fc for fc in result["fee_caps"])

    def test_subcontracting_plan_above_750k(self):
        """Non-SB contract > $750K requires subcontracting plan."""
        result = get_requirements(1_000_000, "negotiated", "ffp", flags={"is_small_business": False})
        subk = [d for d in result["documents_required"] if "Subcontracting" in d["name"]]
        assert len(subk) == 1
        assert subk[0]["required"] is True

    def test_subcontracting_plan_exempt_sb(self):
        """Small business awardee is exempt from subcontracting plan."""
        result = get_requirements(1_000_000, "negotiated", "ffp", flags={"is_small_business": True})
        subk = [d for d in result["documents_required"] if "Subcontracting" in d["name"]]
        assert len(subk) == 1
        assert subk[0]["required"] is False


# ---------------------------------------------------------------------------
# 1b. Normalization / alias resolution
# ---------------------------------------------------------------------------

class TestNormalization:
    """Verify alias resolution and normalization for method and type IDs."""

    # --- Method aliases ---

    def test_full_and_open_resolves_to_negotiated(self):
        result = get_requirements(500_000, "full_and_open", "ffp")
        assert result["errors"] == []
        assert result["method"]["id"] == "negotiated"

    def test_sealed_bidding_resolves_to_negotiated(self):
        result = get_requirements(500_000, "sealed_bidding", "ffp")
        assert result["errors"] == []
        assert result["method"]["id"] == "negotiated"

    def test_simplified_acquisition_resolves_to_sap(self):
        result = get_requirements(200_000, "simplified_acquisition", "ffp")
        assert result["errors"] == []
        assert result["method"]["id"] == "sap"

    def test_micro_purchase_resolves_to_micro(self):
        result = get_requirements(10_000, "micro_purchase", "ffp")
        assert result["errors"] == []
        assert result["method"]["id"] == "micro"

    def test_sole_source_resolves_to_sole(self):
        result = get_requirements(500_000, "sole_source", "ffp")
        assert result["errors"] == []
        assert result["method"]["id"] == "sole"

    def test_task_order_resolves_to_idiq_order(self):
        result = get_requirements(200_000, "task_order", "ffp")
        assert result["errors"] == []
        assert result["method"]["id"] == "idiq-order"

    def test_bpa_resolves_to_bpa_est(self):
        result = get_requirements(200_000, "bpa", "ffp")
        assert result["errors"] == []
        assert result["method"]["id"] == "bpa-est"

    def test_gsa_schedule_resolves_to_fss(self):
        result = get_requirements(200_000, "gsa_schedule", "ffp")
        assert result["errors"] == []
        assert result["method"]["id"] == "fss"

    # --- Type aliases ---

    def test_firm_fixed_price_resolves_to_ffp(self):
        result = get_requirements(200_000, "sap", "firm_fixed_price")
        assert result["errors"] == []
        assert result["contract_type"]["id"] == "ffp"

    def test_cost_plus_fixed_fee_resolves_to_cpff(self):
        result = get_requirements(1_000_000, "negotiated", "cost_plus_fixed_fee")
        assert result["errors"] == []
        assert result["contract_type"]["id"] == "cpff"

    def test_time_and_materials_resolves_to_tm(self):
        result = get_requirements(200_000, "sap", "time_and_materials")
        assert result["errors"] == []
        assert result["contract_type"]["id"] == "tm"

    def test_labor_hour_resolves_to_lh(self):
        result = get_requirements(200_000, "sap", "labor_hour")
        assert result["errors"] == []
        assert result["contract_type"]["id"] == "lh"

    def test_t_and_m_alias_resolves_to_tm(self):
        result = get_requirements(200_000, "sap", "t&m")
        assert result["errors"] == []
        assert result["contract_type"]["id"] == "tm"

    # --- Case / whitespace / hyphen tolerance ---

    def test_uppercase_method_resolves(self):
        result = get_requirements(200_000, "SAP", "ffp")
        assert result["errors"] == []
        assert result["method"]["id"] == "sap"

    def test_hyphen_underscore_equivalence_method(self):
        result = get_requirements(200_000, "bpa_est", "ffp")
        assert result["errors"] == []
        assert result["method"]["id"] == "bpa-est"

    def test_hyphen_underscore_equivalence_type(self):
        result = get_requirements(200_000, "sap", "fp_epa")
        assert result["errors"] == []
        assert result["contract_type"]["id"] == "fp-epa"

    def test_leading_trailing_whitespace(self):
        result = get_requirements(200_000, "  sap  ", "  ffp  ")
        assert result["errors"] == []

    # --- Still errors for truly unknown inputs ---

    def test_unknown_method_still_errors(self):
        result = get_requirements(100_000, "bogus_method", "ffp")
        assert len(result["errors"]) == 1
        assert "Unknown acquisition method" in result["errors"][0]

    def test_unknown_type_still_errors(self):
        result = get_requirements(100_000, "sap", "bogus_type")
        assert len(result["errors"]) == 1
        assert "Unknown contract type" in result["errors"][0]

    def test_empty_method_errors(self):
        result = get_requirements(100_000, "", "ffp")
        assert len(result["errors"]) == 1
        assert "Unknown acquisition method" in result["errors"][0]

    def test_empty_type_errors(self):
        result = get_requirements(100_000, "sap", "")
        assert len(result["errors"]) == 1
        assert "Unknown contract type" in result["errors"][0]

    # --- Error messages include valid IDs ---

    def test_error_lists_valid_method_ids(self):
        result = get_requirements(100_000, "xyz", "ffp")
        error_msg = result["errors"][0]
        assert "Valid IDs:" in error_msg
        assert "negotiated" in error_msg

    def test_error_lists_valid_type_ids(self):
        result = get_requirements(100_000, "sap", "xyz")
        error_msg = result["errors"][0]
        assert "Valid IDs:" in error_msg
        assert "ffp" in error_msg


class TestNormalizeFunctions:
    """Direct unit tests for normalization helpers."""

    def test_normalize_method_exact_match(self):
        assert _normalize_method("sap") == "sap"

    def test_normalize_method_hyphenated_id(self):
        assert _normalize_method("bpa-est") == "bpa-est"

    def test_normalize_method_underscore_to_hyphen(self):
        assert _normalize_method("bpa_call") == "bpa-call"

    def test_normalize_method_alias(self):
        assert _normalize_method("full_and_open") == "negotiated"

    def test_normalize_method_none_for_unknown(self):
        assert _normalize_method("nonexistent") is None

    def test_normalize_method_none_for_empty(self):
        assert _normalize_method("") is None

    def test_normalize_type_exact_match(self):
        assert _normalize_type("ffp") == "ffp"

    def test_normalize_type_hyphenated_id(self):
        assert _normalize_type("fp-epa") == "fp-epa"

    def test_normalize_type_alias(self):
        assert _normalize_type("firm_fixed_price") == "ffp"

    def test_normalize_type_none_for_unknown(self):
        assert _normalize_type("nonexistent") is None


# ---------------------------------------------------------------------------
# 2. search_far()
# ---------------------------------------------------------------------------

class TestSearchFar:
    """Keyword search across the FAR database."""

    def test_search_competition_returns_results(self):
        """Searching 'competition' returns at least one result."""
        results = search_far("competition")
        assert len(results) > 0

    def test_search_is_case_insensitive(self):
        """Search is case-insensitive."""
        upper = search_far("COMPETITION")
        lower = search_far("competition")
        assert len(upper) == len(lower)

    def test_search_with_parts_filter(self):
        """Parts filter restricts results to specified FAR parts."""
        all_results = search_far("contract")
        if all_results:
            target_part = all_results[0].get("part")
            filtered = search_far("contract", parts=[target_part])
            assert all(r.get("part") == target_part for r in filtered)
            assert len(filtered) <= len(all_results)

    def test_empty_keyword_returns_nothing(self):
        """Empty keyword string still runs but matches everything with empty substring."""
        results = search_far("")
        # Empty string is a substring of every string, so this returns all entries
        assert isinstance(results, list)

    def test_nonsense_keyword_returns_empty(self):
        """A nonsensical keyword returns no results."""
        results = search_far("xyzzy_no_match_99999")
        assert results == []


# ---------------------------------------------------------------------------
# 3. suggest_vehicle()
# ---------------------------------------------------------------------------

class TestSuggestVehicle:
    """Vehicle recommendation based on requirement flags."""

    def test_it_and_services_recommends_nitaac(self):
        """IT + services -> NITAAC vehicle."""
        result = suggest_vehicle(flags={"is_it": True, "is_services": True})
        vehicles = result["suggested_vehicles"]
        assert len(vehicles) >= 1
        assert vehicles[0]["vehicle"] == "nitaac"

    def test_it_only_recommends_gsa(self):
        """IT commodities (no services) -> GSA Schedules."""
        result = suggest_vehicle(flags={"is_it": True, "is_services": False})
        assert result["suggested_vehicles"][0]["vehicle"] == "gsa_schedules"

    def test_services_only_recommends_gsa(self):
        """Services (no IT) -> GSA Schedules."""
        result = suggest_vehicle(flags={"is_it": False, "is_services": True})
        assert result["suggested_vehicles"][0]["vehicle"] == "gsa_schedules"

    def test_neither_recommends_open_competition(self):
        """Neither IT nor services -> open competition."""
        result = suggest_vehicle(flags={"is_it": False, "is_services": False})
        assert result["suggested_vehicles"][0]["vehicle"] == "open_competition"

    def test_no_flags_defaults_to_open_competition(self):
        """No flags at all defaults to open competition."""
        result = suggest_vehicle()
        assert result["suggested_vehicles"][0]["vehicle"] == "open_competition"


# ---------------------------------------------------------------------------
# 4. execute_operation()
# ---------------------------------------------------------------------------

class TestExecuteOperation:
    """Dispatcher routes to correct sub-functions."""

    def test_query_dispatches_to_get_requirements(self):
        result = execute_operation({
            "operation": "query",
            "contract_value": 100_000,
            "acquisition_method": "sap",
            "contract_type": "ffp",
        })
        assert "documents_required" in result
        assert "errors" in result

    def test_list_methods(self):
        result = execute_operation({"operation": "list_methods"})
        assert result["methods"] is METHODS

    def test_list_types(self):
        result = execute_operation({"operation": "list_types"})
        assert result["types"] is TYPES

    def test_list_thresholds(self):
        result = execute_operation({"operation": "list_thresholds"})
        assert "threshold_tiers" in result
        assert result["threshold_tiers"] is THRESHOLD_TIERS
        assert "threshold_data" in result

    def test_search_far_with_keyword(self):
        result = execute_operation({"operation": "search_far", "keyword": "competition"})
        assert "results" in result
        assert len(result["results"]) > 0

    def test_search_far_without_keyword_returns_error(self):
        result = execute_operation({"operation": "search_far"})
        assert "error" in result

    def test_suggest_vehicle_dispatch(self):
        result = execute_operation({
            "operation": "suggest_vehicle",
            "is_it": True,
            "is_services": True,
        })
        assert "suggested_vehicles" in result

    def test_unknown_operation_returns_error(self):
        result = execute_operation({"operation": "nonexistent"})
        assert "error" in result
        assert "Unknown operation" in result["error"]


# ---------------------------------------------------------------------------
# 5. Constants Validation
# ---------------------------------------------------------------------------

class TestConstants:
    """Verify module-level constants are well-formed."""

    def test_methods_has_expected_ids(self):
        ids = {m["id"] for m in METHODS}
        for expected in ("micro", "sap", "negotiated", "sole", "fss", "idiq"):
            assert expected in ids, f"METHODS missing expected id '{expected}'"

    def test_types_has_expected_ids(self):
        ids = {t["id"] for t in TYPES}
        for expected in ("ffp", "cpff", "tm", "lh"):
            assert expected in ids, f"TYPES missing expected id '{expected}'"

    def test_threshold_tiers_sorted_ascending(self):
        values = [t["value"] for t in THRESHOLD_TIERS]
        assert values == sorted(values), "THRESHOLD_TIERS must be sorted ascending by value"

    def test_threshold_tiers_all_positive(self):
        assert all(t["value"] > 0 for t in THRESHOLD_TIERS)


# ---------------------------------------------------------------------------
# 6. Phase 2e: Flags wired through execute_operation
# ---------------------------------------------------------------------------

class TestExecuteOperationFlags:
    """Verify is_limited_sources, is_8a, is_manufacturing pass through."""

    def test_limited_sources_flag_passes_through(self):
        result = execute_operation({
            "operation": "query",
            "contract_value": 200_000,
            "acquisition_method": "fss",
            "contract_type": "ffp",
            "is_limited_sources": True,
        })
        ja = [d for d in result["documents_required"] if "J&A" in d["name"]][0]
        assert ja["required"] is True
        assert ja["variant"] == "simplified_limited_sources"

    def test_8a_flag_passes_through(self):
        result = execute_operation({
            "operation": "query",
            "contract_value": 3_000_000,
            "acquisition_method": "sap",
            "contract_type": "ffp",
            "is_8a": True,
        })
        assert "8(a) sole source authorized" in result["competition_rules"]

    def test_manufacturing_flag_passes_through(self):
        result = execute_operation({
            "operation": "query",
            "contract_value": 5_000_000,
            "acquisition_method": "sap",
            "contract_type": "ffp",
            "is_8a": True,
            "is_manufacturing": True,
        })
        assert "Manufacturing" in result["competition_rules"]


# ---------------------------------------------------------------------------
# 7. Phase 2: J&A / Competition Paths — FSS, BPA, 8(a)
# ---------------------------------------------------------------------------

class TestJACompetitionPaths:
    """Expanded J&A coverage: FSS limited, BPA limited, 8(a) ceilings."""

    def test_fss_limited_sources_under_sat(self):
        """FSS limited sources under SAT → simplified J&A."""
        result = get_requirements(200_000, "fss", "ffp", flags={"is_limited_sources": True})
        ja = [d for d in result["documents_required"] if "J&A" in d["name"]][0]
        assert ja["required"] is True
        assert ja["variant"] == "simplified_limited_sources"
        assert ja["authority"] == "FAR 8.405-6"

    def test_fss_limited_sources_over_sat(self):
        """FSS limited sources over SAT → full J&A."""
        result = get_requirements(500_000, "fss", "ffp", flags={"is_limited_sources": True})
        ja = [d for d in result["documents_required"] if "J&A" in d["name"]][0]
        assert ja["required"] is True
        assert ja["variant"] == "full"

    def test_bpa_call_limited_under_sat(self):
        """BPA-call limited under SAT → simplified J&A."""
        result = get_requirements(100_000, "bpa-call", "ffp", flags={"is_limited_sources": True})
        ja = [d for d in result["documents_required"] if "J&A" in d["name"]][0]
        assert ja["required"] is True
        assert ja["variant"] == "simplified_limited_sources"
        assert ja["authority"] == "FAR 8.405-6"

    def test_bpa_est_sole_source(self):
        """BPA-est limited → J&A required."""
        result = get_requirements(100_000, "bpa-est", "ffp", flags={"is_limited_sources": True})
        ja = [d for d in result["documents_required"] if "J&A" in d["name"]][0]
        assert ja["required"] is True

    def test_8a_sole_source_services_under_ceiling(self):
        """8(a) services under $4.5M → sole source authorized."""
        result = get_requirements(3_000_000, "sap", "ffp", flags={"is_8a": True})
        assert "8(a) sole source authorized" in result["competition_rules"]
        assert "19.805-1" in result["competition_rules"]

    def test_8a_sole_source_services_over_ceiling(self):
        """8(a) services over $4.5M → competitive required."""
        result = get_requirements(5_000_000, "negotiated", "ffp", flags={"is_8a": True})
        assert "8(a) competitive required" in result["competition_rules"]

    def test_8a_sole_source_manufacturing_ceiling(self):
        """8(a) manufacturing ceiling is $7M, not $4.5M."""
        result = get_requirements(5_000_000, "sap", "ffp", flags={"is_8a": True, "is_manufacturing": True})
        assert "8(a) sole source authorized" in result["competition_rules"]
        assert "Manufacturing" in result["competition_rules"]

    def test_8a_alias_removed(self):
        """'8a' should NOT map to 'fss' anymore."""
        from app.compliance_matrix import _normalize_method
        assert _normalize_method("8a") is None


# ---------------------------------------------------------------------------
# 8. Phase 3: Tool Consolidation — _related_far
# ---------------------------------------------------------------------------

class TestRelatedFar:
    """_related_far enrichment in get_requirements() output."""

    def test_sole_source_includes_related_far(self):
        result = get_requirements(280_000, "sole", "ffp")
        assert "_related_far" in result
        assert isinstance(result["_related_far"], list)
        assert len(result["_related_far"]) > 0

    def test_fss_includes_related_far(self):
        result = get_requirements(200_000, "fss", "ffp")
        assert len(result["_related_far"]) > 0

    def test_negotiated_includes_related_far(self):
        result = get_requirements(1_000_000, "negotiated", "ffp")
        assert len(result["_related_far"]) > 0

    def test_search_far_op_returns_deprecation_note(self):
        result = execute_operation({"operation": "search_far", "keyword": "competition"})
        assert "note" in result
        assert "search_far tool directly" in result["note"]
        assert len(result["results"]) > 0


# ---------------------------------------------------------------------------
# 9. Phase 4: FAR Citation Verification — _verify
# ---------------------------------------------------------------------------

class TestVerifyCitations:
    """_verify.far_citations extracted from matrix output text."""

    def test_get_requirements_includes_verify(self):
        result = get_requirements(280_000, "sole", "ffp")
        assert "_verify" in result
        assert "far_citations" in result["_verify"]
        assert isinstance(result["_verify"]["far_citations"], list)

    def test_sole_source_cites_far_6302(self):
        """Sole source over SAT should cite FAR 6.302."""
        result = get_requirements(500_000, "sole", "ffp")
        citations = result["_verify"]["far_citations"]
        assert any("6.302" in c for c in citations)

    def test_simplified_sole_cites_far_13106(self):
        """Simplified sole source under SAT should cite FAR 13.106-1(b)."""
        result = get_requirements(200_000, "sole", "ffp")
        citations = result["_verify"]["far_citations"]
        assert any("13.106" in c for c in citations)

    def test_extract_far_citations_helper(self):
        from app.compliance_matrix import _extract_far_citations
        text = "See FAR 6.302-1 and DFARS 215.404-1 for details. Also FAR 19.805-1(a)(2)."
        citations = _extract_far_citations(text)
        assert "6.302-1" in citations
        assert "215.404-1" in citations
        assert "19.805-1(a)(2)." in citations or "19.805-1(a)(2)" in citations


# ---------------------------------------------------------------------------
# 10. Phase 5: Template Field Visibility
# ---------------------------------------------------------------------------

class TestTemplateFieldVisibility:
    """Template fields surfaced in compliance matrix output."""

    def test_sole_source_ja_has_template_hint(self):
        """Simplified sole source J&A should have template_hint."""
        result = get_requirements(280_000, "sole", "ffp")
        ja = [d for d in result["documents_required"] if "J&A" in d["name"]][0]
        assert "template_hint" in ja

    def test_get_template_fields_known_template(self):
        from app.template_registry import get_template_fields
        # SOW template has fields
        fields = get_template_fields("statement-of-work-template-eagle-v2.docx")
        assert fields is not None
        assert "title" in fields

    def test_get_template_fields_unknown_template(self):
        from app.template_registry import get_template_fields
        assert get_template_fields("nonexistent-template.docx") is None


# ---------------------------------------------------------------------------
# 11. Phase 6: Confidence Signals
# ---------------------------------------------------------------------------

class TestConfidenceSignals:
    """Confidence scores on documents, compliance items, and overall."""

    def test_documents_have_confidence(self):
        result = get_requirements(500_000, "negotiated", "ffp")
        for doc in result["documents_required"]:
            assert "confidence" in doc, f"Missing confidence on {doc['name']}"
            assert 0.0 < doc["confidence"] <= 1.0

    def test_compliance_items_have_confidence(self):
        result = get_requirements(500_000, "negotiated", "ffp")
        for item in result["compliance_items"]:
            assert "confidence" in item, f"Missing confidence on {item['name']}"
            assert 0.0 < item["confidence"] <= 1.0

    def test_overall_confidence_present(self):
        result = get_requirements(500_000, "negotiated", "ffp")
        assert "confidence" in result
        assert "overall" in result["confidence"]
        assert 0.0 < result["confidence"]["overall"] <= 1.0

    def test_timeline_has_confidence(self):
        result = get_requirements(500_000, "negotiated", "ffp")
        assert "confidence" in result["timeline_estimate"]
        assert result["timeline_estimate"]["confidence"] == 0.60

    def test_confidence_in_valid_range(self):
        """All confidence values must be between 0 and 1."""
        result = get_requirements(3_000_000, "sole", "cpff", flags={"is_8a": True})
        for doc in result["documents_required"]:
            assert 0.0 < doc["confidence"] <= 1.0, f"Bad confidence on {doc['name']}"

    def test_8a_confidence_lower_than_standard(self):
        """8(a) items should have lower confidence than standard rules."""
        from app.compliance_matrix import _CONFIDENCE
        assert _CONFIDENCE["8a_ceiling"] < _CONFIDENCE["document_requirement"]
