"""Tests for compliance_matrix.py — deterministic procurement compliance logic.

Validates: get_requirements(), search_far(), suggest_vehicle(), execute_operation(),
and module-level constants. Pure Python — no AWS dependencies or mocking needed.
"""

import pytest

from app.compliance_matrix import (
    METHODS,
    THRESHOLD_TIERS,
    TYPES,
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
        """$500K triggers SAT ($350K) but not TINA ($2.5M)."""
        result = get_requirements(500_000, "negotiated", "ffp")
        triggered_values = [t["value"] for t in result["thresholds_triggered"]]
        assert 350_000 in triggered_values, "SAT threshold should be triggered"
        assert 2_500_000 not in triggered_values, "TINA threshold should NOT be triggered"

    def test_threshold_3m_triggers_tina(self):
        """$3M triggers TINA ($2.5M)."""
        result = get_requirements(3_000_000, "negotiated", "ffp")
        triggered_values = [t["value"] for t in result["thresholds_triggered"]]
        assert 2_500_000 in triggered_values, "TINA threshold should be triggered at $3M"
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
