"""Tests for the intake-required-facts subagent fast-path validator.

Covers _check_intake_required_facts() in server/app/strands_agentic_service.py.
The validator runs inside the subagent create_document_tool as a fast-path
that returns a guardrail message when the supervisor handed the subagent
incomplete data. Enforcement proper lives in the supervisor prompt +
market-intelligence prompt blocks (see PRE-GENERATION INTAKE GATE sections).

Data-dict semantics only — no prose parsing. Facts must be present as
structured keys in parsed['data'] or session_ctx.
"""

import json

from app.strands_agentic_service import _check_intake_required_facts


class TestCheckIntakeRequiredFacts:
    """Subagent fast-path guardrail or None, based on data-dict presence."""

    def test_pws_missing_cadence_blocks(self):
        """4/16 regression — PWS handed to subagent without event_cadence must block."""
        parsed = {
            "doc_type": "pws",
            "data": {
                "scope": "training program",
                "pop": "12 months",
                "place_of_performance": "Bethesda",
                "deliverable_format": "monthly report",
                # event_cadence missing
            },
        }
        result = _check_intake_required_facts(parsed)
        assert result is not None, "expected a guardrail block"
        payload = json.loads(result)
        assert payload["guardrail"] == "intake_required_facts"
        assert payload["doc_type"] == "pws"
        assert "event_cadence" in payload["missing_facts"]
        assert payload["status"] == "guardrail"

    def test_pws_all_present_passes(self):
        parsed = {
            "doc_type": "pws",
            "data": {
                "scope": "training program",
                "pop": "12 months",
                "place_of_performance": "Bethesda",
                "event_cadence": "monthly",
                "deliverable_format": "reports",
            },
        }
        assert _check_intake_required_facts(parsed) is None

    def test_session_ctx_fills_missing_data(self):
        """Values in session_ctx count equivalently to values in parsed['data']."""
        parsed = {"doc_type": "pws", "data": {"scope": "training", "pop": "12mo"}}
        session_ctx = {
            "place_of_performance": "Bethesda",
            "event_cadence": "monthly",
            "deliverable_format": "reports",
        }
        assert _check_intake_required_facts(parsed, session_ctx=session_ctx) is None

    def test_igce_missing_budget_ceiling_blocks(self):
        parsed = {
            "doc_type": "igce",
            "data": {"scope": "labor services", "pop": "12 months", "labor_categories": "analyst, engineer"},
        }
        result = _check_intake_required_facts(parsed)
        assert result is not None
        payload = json.loads(result)
        assert "budget_ceiling" in payload["missing_facts"]

    def test_igce_accepts_estimated_value_alias_for_budget_ceiling(self):
        """The data-dict aliases let common key names satisfy the requirement."""
        parsed = {
            "doc_type": "igce",
            "data": {
                "scope": "labor services",
                "pop": "12 months",
                "labor_categories": "analyst, engineer",
                "estimated_value": 2000000,
            },
        }
        assert _check_intake_required_facts(parsed) is None

    def test_market_research_missing_value_range_blocks(self):
        parsed = {
            "doc_type": "market_research",
            "data": {"scope": "cloud services", "naics_code": "541512"},
        }
        result = _check_intake_required_facts(parsed)
        assert result is not None
        payload = json.loads(result)
        assert "estimated_value_range" in payload["missing_facts"]

    def test_unknown_doc_type_passes(self):
        parsed = {"doc_type": "custom_unknown", "data": {}}
        assert _check_intake_required_facts(parsed) is None

    def test_empty_doc_type_passes(self):
        parsed = {"data": {}}
        assert _check_intake_required_facts(parsed) is None

    def test_guardrail_structure(self):
        result = _check_intake_required_facts({"doc_type": "pws", "data": {}})
        payload = json.loads(result)
        for key in ("status", "guardrail", "doc_type", "message", "missing_facts", "word_count"):
            assert key in payload, f"guardrail missing key: {key}"
        assert isinstance(payload["missing_facts"], list)
        assert payload["word_count"] == 0

    def test_guardrail_message_directs_to_supervisor(self):
        """Subagent guardrail message must tell the subagent to report back, not retry."""
        result = _check_intake_required_facts({"doc_type": "pws", "data": {}})
        payload = json.loads(result)
        assert "supervisor" in payload["message"].lower()
        assert "batched" in payload["message"].lower()

    def test_data_dict_as_json_string_is_parsed(self):
        """create_document sometimes receives `data` as a JSON string — handle it."""
        parsed = {
            "doc_type": "igce",
            "data": json.dumps({
                "scope": "engineering services",
                "pop": "12 months",
                "labor_categories_or_line_items": "engineer, analyst",
                "budget_ceiling": 2000000,
            }),
        }
        assert _check_intake_required_facts(parsed) is None

    def test_ja_and_justification_use_same_spec(self):
        """Both 'ja' and 'justification' block identically on empty data."""
        for dt in ("ja", "justification"):
            parsed = {"doc_type": dt, "data": {}}
            result = _check_intake_required_facts(parsed)
            assert result is not None, f"{dt} with empty data should block"
            payload = json.loads(result)
            assert "proposed_contractor" in payload["missing_facts"]

    def test_blank_and_sentinel_values_are_treated_as_missing(self):
        parsed = {
            "doc_type": "pws",
            "data": {
                "scope": "",
                "pop": "N/A",
                "place_of_performance": "TBD",
                "event_cadence": None,
                "deliverable_format": "unknown",
            },
        }
        result = _check_intake_required_facts(parsed)
        assert result is not None
        payload = json.loads(result)
        assert set(payload["missing_facts"]) == {
            "scope", "pop", "place_of_performance", "event_cadence", "deliverable_format"
        }
