"""Tests for the intake-required-facts backend validator.

Covers _check_intake_required_facts() and _fact_present() in
server/app/strands_agentic_service.py. This is the chokepoint that fires
for every create_document caller (supervisor tool-dispatch AND subagent
direct path). See the 4/16 EAGLE output review + 2026-04-22 handoff for
the originating issues (PWS without cadence, IGCE inflated to budget,
reconcile-question prompts).
"""

import json

from app.strands_agentic_service import (
    _check_intake_required_facts,
    _fact_present,
)


class TestFactPresent:
    """Pattern-based detectors for individual facts."""

    def test_scope_via_explicit_prefix(self):
        assert _fact_present("scope", {}, "Scope: cloud migration services.", {}) is True

    def test_scope_via_requirement_prefix(self):
        assert _fact_present("scope", {}, "Requirement: migrate legacy systems.", {}) is True

    def test_scope_via_data_key(self):
        assert _fact_present("scope", {"scope": "cloud migration"}, "", {}) is True

    def test_scope_via_requirement_description_key(self):
        assert _fact_present("scope", {"requirement_description": "migrate"}, "", {}) is True

    def test_scope_missing_short_content(self):
        assert _fact_present("scope", {}, "Short note.", {}) is False

    def test_event_cadence_monthly_report_does_not_count(self):
        """4/16 regression — 'monthly report' is a deliverable, not event cadence."""
        text = "Deliverables: monthly report sent to the COR."
        assert _fact_present("event_cadence", {}, text, {}) is False

    def test_event_cadence_training_events_held_monthly(self):
        text = "Training events held monthly throughout the PoP."
        assert _fact_present("event_cadence", {}, text, {}) is True

    def test_event_cadence_sessions_per_year(self):
        text = "The contractor will deliver 12 training sessions per year."
        assert _fact_present("event_cadence", {}, text, {}) is True

    def test_event_cadence_data_key(self):
        assert _fact_present("event_cadence", {"event_cadence": "monthly"}, "", {}) is True

    def test_event_cadence_via_session_ctx(self):
        assert _fact_present("event_cadence", {}, "", {"event_cadence": "quarterly"}) is True

    def test_place_of_performance_explicit(self):
        assert _fact_present("place_of_performance", {}, "Place of performance: Bethesda, MD.", {}) is True

    def test_place_of_performance_remote(self):
        assert _fact_present("place_of_performance", {}, "Work is remote / telework.", {}) is True

    def test_pop_period_of_performance(self):
        assert _fact_present("pop", {}, "Period of performance: 12 months base plus 4 option years.", {}) is True

    def test_pop_data_key(self):
        assert _fact_present("pop", {"period_of_performance": "12mo"}, "", {}) is True

    def test_budget_ceiling_dollar_amount_in_content(self):
        assert _fact_present("budget_ceiling", {}, "Not-to-exceed $2,000,000.", {}) is True

    def test_budget_ceiling_data_via_estimated_value(self):
        assert _fact_present("budget_ceiling", {"estimated_value": "$2M"}, "", {}) is True

    def test_naics_code_in_content(self):
        assert _fact_present("naics_or_category", {}, "NAICS 541512 applies.", {}) is True

    def test_contract_type_detection(self):
        assert _fact_present("contract_type", {}, "Planned as FFP.", {}) is True
        assert _fact_present("contract_type", {}, "Time and materials with ceiling.", {}) is True

    def test_authority_far_6302_detection(self):
        assert _fact_present("authority_far_6_302_x", {}, "Citing FAR 6.302-1 unusual and compelling urgency.", {}) is True

    def test_session_ctx_overrides_missing_data(self):
        """session_ctx fills in what data/content lack."""
        assert _fact_present("scope", {}, "", {"scope": "migrate"}) is True

    def test_explicit_tbd_not_accepted(self):
        assert _fact_present("scope", {"scope": "TBD"}, "", {}) is False
        assert _fact_present("scope", {"scope": "unknown"}, "", {}) is False


class TestCheckIntakeRequiredFacts:
    """Top-level validator returning guardrail JSON or None."""

    def test_pws_missing_cadence_blocks(self):
        """The original 4/16 issue — PWS without cadence must be blocked."""
        parsed = {
            "doc_type": "pws",
            "content": "Scope: website maintenance. PoP 12 months. Place of performance: on-site Bethesda, MD. Deliverables: monthly report.",
            "data": {},
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
            "content": (
                "Scope: training program delivery. PoP 12 months. "
                "Place of performance: on-site Bethesda, MD. "
                "Training events held monthly. Deliverables: monthly event report."
            ),
            "data": {},
        }
        assert _check_intake_required_facts(parsed) is None

    def test_pws_all_present_via_data_dict(self):
        parsed = {
            "doc_type": "pws",
            "content": "",
            "data": {
                "scope": "training program",
                "pop": "12 months",
                "place_of_performance": "Bethesda",
                "event_cadence": "monthly",
                "deliverable_format": "reports",
            },
        }
        assert _check_intake_required_facts(parsed) is None

    def test_pws_all_present_via_session_ctx(self):
        parsed = {"doc_type": "pws", "content": "", "data": {}}
        session_ctx = {
            "scope": "training",
            "pop": "12mo",
            "place_of_performance": "Bethesda",
            "event_cadence": "monthly",
            "deliverable_format": "reports",
        }
        assert _check_intake_required_facts(parsed, session_ctx=session_ctx) is None

    def test_igce_missing_budget_ceiling_blocks(self):
        parsed = {
            "doc_type": "igce",
            "content": "Scope: labor analyst engineer. PoP 12 months.",
            "data": {},
        }
        result = _check_intake_required_facts(parsed)
        assert result is not None
        payload = json.loads(result)
        assert "budget_ceiling" in payload["missing_facts"]

    def test_market_research_missing_value_range_blocks(self):
        parsed = {
            "doc_type": "market_research",
            "content": "Scope: cloud migration services. NAICS 541512.",
            "data": {},
        }
        result = _check_intake_required_facts(parsed)
        assert result is not None
        payload = json.loads(result)
        assert "estimated_value_range" in payload["missing_facts"]

    def test_unknown_doc_type_passes(self):
        """Unknown doc types (e.g. a custom one) must not spuriously block."""
        parsed = {"doc_type": "custom_unknown", "content": "", "data": {}}
        assert _check_intake_required_facts(parsed) is None

    def test_empty_doc_type_passes(self):
        parsed = {"content": "", "data": {}}
        assert _check_intake_required_facts(parsed) is None

    def test_guardrail_structure(self):
        """Verify the returned JSON has all the fields downstream expects."""
        result = _check_intake_required_facts(
            {"doc_type": "pws", "content": "Scope: short.", "data": {}}
        )
        payload = json.loads(result)
        for key in ("status", "guardrail", "doc_type", "message", "missing_facts", "word_count"):
            assert key in payload, f"guardrail missing key: {key}"
        assert "missing_facts" in payload
        assert isinstance(payload["missing_facts"], list)
        assert payload["word_count"] == 0

    def test_guardrail_message_mentions_batched_question(self):
        """The guardrail message must instruct the caller to batch, not drip-feed."""
        result = _check_intake_required_facts(
            {"doc_type": "pws", "content": "Scope: short.", "data": {}}
        )
        payload = json.loads(result)
        assert "batched" in payload["message"].lower() or "one" in payload["message"].lower()
        assert "drip" in payload["message"].lower() or "batched" in payload["message"].lower()

    def test_data_dict_string_json_is_parsed(self):
        """create_document is sometimes called with `data` as a JSON string."""
        parsed = {
            "doc_type": "igce",
            "content": "",
            "data": json.dumps({
                "scope": "engineering services",
                "pop": "12 months",
                "labor_categories": "engineer, analyst",
                "budget_ceiling": "$2,000,000",
            }),
        }
        assert _check_intake_required_facts(parsed) is None

    def test_ja_justification_aliases(self):
        """Both 'ja' and 'justification' have the same required-facts spec."""
        for dt in ("ja", "justification"):
            parsed = {"doc_type": dt, "content": "", "data": {}}
            result = _check_intake_required_facts(parsed)
            assert result is not None, f"{dt} with empty data should block"
            payload = json.loads(result)
            assert "proposed_contractor" in payload["missing_facts"]


class TestChokepointExecCreateDocument:
    """Verify the chokepoint in tools/document_generation.exec_create_document
    enforces the intake-facts guardrail for ANY caller (supervisor, subagent,
    or forced-call path), not just the subagent fast-path."""

    def test_exec_create_document_rejects_missing_facts(self):
        """Call exec_create_document directly with an incomplete PWS payload.

        Must return a guardrail dict BEFORE any S3/template work happens —
        this is the universal backstop that catches misses the subagent
        fast-path doesn't.
        """
        from app.tools.document_generation import exec_create_document

        # Missing event_cadence (and most other required PWS facts). Has a
        # title and a minimal content body so earlier prerequisite checks
        # can't short-circuit before the intake gate.
        params = {
            "doc_type": "pws",
            "title": "PWS - Training Program",
            "content": "Deliverables: monthly status report.",
            "data": {},
        }
        result = exec_create_document(params, tenant_id="test-tenant", session_id=None)
        assert isinstance(result, dict)
        assert result.get("status") == "guardrail", (
            f"expected guardrail status, got: {result}"
        )
        assert result.get("guardrail") == "intake_required_facts"
        assert "event_cadence" in result.get("missing_facts", [])

    def test_exec_create_document_guardrail_is_json_serializable(self):
        """Downstream consumers JSON-serialize the result — must round-trip."""
        from app.tools.document_generation import exec_create_document

        result = exec_create_document(
            {"doc_type": "igce", "title": "IGCE", "content": "", "data": {}},
            tenant_id="test-tenant",
            session_id=None,
        )
        json.dumps(result)  # must not raise
        assert result["status"] == "guardrail"
