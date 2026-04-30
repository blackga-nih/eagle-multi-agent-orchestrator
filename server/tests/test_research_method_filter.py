"""Tests for the method-aware doc filter in research_tool.

Closes A2 from .claude/specs/20260429-102357-plan-q4-uc21-coworker-feedback-triage-v1.md.

UC2.1 review (Hash, 2026-04-29) flagged that EAGLE pulled protest documentation
for a micro-purchase microscope request — wasted context and irrelevant. This
filter drops protest / J&A / appropriations docs from research results when
acquisition_method is detected as 'micro', UNLESS the user explicitly asks
about those topics.
"""

from __future__ import annotations

from app.tools.research_tool import (
    _MICRO_PURCHASE_DROP_BYPASS,
    _MICRO_PURCHASE_DROP_PREFIXES,
    _filter_results_by_method,
)


def _result(s3_key: str, title: str = "") -> dict:
    return {"s3_key": s3_key, "title": title or s3_key.rsplit("/", 1)[-1]}


# ---------------------------------------------------------------------------
# Filter behavior under method=micro
# ---------------------------------------------------------------------------


class TestMicroPurchaseFilter:

    def test_drops_protest_guidance(self):
        results = [
            _result("eagle-knowledge-base/approved/legal-counselor/protest-guidance/GAO_protest_basics.txt"),
            _result("eagle-knowledge-base/approved/supervisor-core/checklists/HHS_PMR_Common_Requirements.txt"),
        ]
        kept, dropped = _filter_results_by_method(results, "micro", "buy a microscope under 15k")
        kept_keys = [r["s3_key"] for r in kept]
        dropped_keys = [r["s3_key"] for r in dropped]
        assert any("protest-guidance" in k for k in dropped_keys), (
            f"Protest guidance should be dropped for micro-purchases. Got dropped={dropped_keys}"
        )
        assert any("PMR_Common_Requirements" in k for k in kept_keys), (
            "PMR checklist should be kept"
        )

    def test_drops_j_and_a_justifications(self):
        results = [
            _result("eagle-knowledge-base/approved/compliance-strategist/justifications/JA_template_full.txt"),
        ]
        kept, dropped = _filter_results_by_method(results, "micro", "lab equipment purchase request")
        assert kept == []
        assert len(dropped) == 1

    def test_drops_appropriations_law(self):
        results = [
            _result("eagle-knowledge-base/approved/legal-counselor/appropriations-law/severable_services.txt"),
        ]
        kept, dropped = _filter_results_by_method(results, "micro", "buy office supplies")
        assert kept == []
        assert len(dropped) == 1

    def test_keeps_relevant_micro_docs(self):
        """Items NOT in the drop-prefix list pass through unchanged."""
        results = [
            _result("eagle-knowledge-base/approved/supervisor-core/essential-templates/SON_Products.txt"),
            _result("eagle-knowledge-base/approved/compliance-strategist/FAR-guidance/FAR_Part_13_Simplified.txt"),
            _result("eagle-knowledge-base/approved/market-intelligence/vendor-research/GSA_Schedules.txt"),
        ]
        kept, dropped = _filter_results_by_method(results, "micro", "microscope purchase")
        assert len(kept) == 3
        assert dropped == []


# ---------------------------------------------------------------------------
# Bypass behavior — explicit topic mentions re-enable dropped folders
# ---------------------------------------------------------------------------


class TestBypassWhenUserAsksAboutTopic:

    def test_bypass_when_query_mentions_protest(self):
        """User asking 'is there a protest risk on a micro-purchase' should
        get protest guidance even on a micro-purchase."""
        results = [
            _result("eagle-knowledge-base/approved/legal-counselor/protest-guidance/GAO_basics.txt"),
        ]
        kept, dropped = _filter_results_by_method(
            results, "micro", "is there a protest risk for this micro-purchase?"
        )
        assert len(kept) == 1
        assert dropped == []

    def test_bypass_when_query_mentions_j_and_a(self):
        results = [
            _result("eagle-knowledge-base/approved/compliance-strategist/justifications/JA_full.txt"),
        ]
        kept, dropped = _filter_results_by_method(
            results, "micro", "do I need a J&A for this micro-purchase?"
        )
        assert len(kept) == 1

    def test_bypass_when_query_mentions_appropriation(self):
        results = [
            _result("eagle-knowledge-base/approved/legal-counselor/appropriations-law/severable.txt"),
        ]
        kept, dropped = _filter_results_by_method(
            results, "micro", "appropriation question on micro-purchase color of money"
        )
        assert len(kept) == 1

    def test_each_bypass_keyword_actually_bypasses(self):
        """Every keyword in _MICRO_PURCHASE_DROP_BYPASS should bypass the filter."""
        for keyword in _MICRO_PURCHASE_DROP_BYPASS:
            results = [
                _result("eagle-knowledge-base/approved/legal-counselor/protest-guidance/x.txt"),
            ]
            kept, dropped = _filter_results_by_method(
                results, "micro", f"micro-purchase question about {keyword}"
            )
            assert len(kept) == 1, (
                f"Bypass keyword {keyword!r} did not re-enable filter bypass"
            )


# ---------------------------------------------------------------------------
# Non-micro methods — filter is a no-op
# ---------------------------------------------------------------------------


class TestNonMicroMethodsUnaffected:
    """For SAP / negotiated / etc. the filter must NOT drop anything —
    those methods legitimately need protest guidance, J&A docs, etc."""

    def test_sap_keeps_protest_guidance(self):
        results = [
            _result("eagle-knowledge-base/approved/legal-counselor/protest-guidance/x.txt"),
        ]
        kept, dropped = _filter_results_by_method(results, "sap", "SAP procurement question")
        assert len(kept) == 1
        assert dropped == []

    def test_negotiated_keeps_appropriations(self):
        results = [
            _result("eagle-knowledge-base/approved/legal-counselor/appropriations-law/x.txt"),
        ]
        kept, dropped = _filter_results_by_method(results, "negotiated", "Part 15 question")
        assert len(kept) == 1

    def test_sole_keeps_j_and_a(self):
        results = [
            _result("eagle-knowledge-base/approved/compliance-strategist/justifications/x.txt"),
        ]
        kept, dropped = _filter_results_by_method(results, "sole", "sole source J&A")
        assert len(kept) == 1


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:

    def test_empty_results_returns_empty(self):
        kept, dropped = _filter_results_by_method([], "micro", "anything")
        assert kept == []
        assert dropped == []

    def test_none_results_returns_empty(self):
        kept, dropped = _filter_results_by_method(None, "micro", "anything")
        assert kept == []
        assert dropped == []

    def test_empty_method_treated_as_non_micro(self):
        results = [
            _result("eagle-knowledge-base/approved/legal-counselor/protest-guidance/x.txt"),
        ]
        kept, dropped = _filter_results_by_method(results, "", "anything")
        assert len(kept) == 1
        assert dropped == []

    def test_case_insensitive_s3_key_matching(self):
        """Real S3 keys may have inconsistent casing. The filter lowercases
        the key before comparing prefixes."""
        results = [
            _result("Eagle-Knowledge-Base/Approved/Legal-Counselor/Protest-Guidance/X.txt"),
        ]
        kept, dropped = _filter_results_by_method(results, "micro", "micro-purchase")
        assert len(dropped) == 1, (
            "Filter must be case-insensitive on s3_key to handle real S3 path drift"
        )

    def test_drop_prefixes_constant_is_non_empty(self):
        """Sanity check — the constant must be populated or the filter is a no-op."""
        assert len(_MICRO_PURCHASE_DROP_PREFIXES) >= 3
        # Each prefix must end in / so we don't accidentally match the wrong
        # folder (e.g. 'protest-guidance' shouldn't match 'protest-guidance-summary').
        for p in _MICRO_PURCHASE_DROP_PREFIXES:
            assert p.endswith("/"), f"Prefix {p!r} must end in '/'"
