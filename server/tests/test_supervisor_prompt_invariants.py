"""Static regression tests for supervisor prompt invariants.

These tests guard against silent prompt regressions where a refactor or
unrelated PR reverts a load-bearing rule in `eagle-plugin/agents/supervisor/agent.md`.

History: commit 04cd419 (May 6, 2026) strengthened the NIH/NCI Labor-Hour
exclusion rule because the model was interpreting "do not default to LH" as
"LH is still an option." PR #187 (3f172b6) inadvertently reverted that
strengthening back to the weak phrasing, and Labor-Hour started reappearing
in chat output. This file enforces the strong wording so that future reverts
fail in CI instead of in production.

Pure file-read assertions — no model, no AWS, no fixtures.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SUPERVISOR_AGENT_MD = REPO_ROOT / "eagle-plugin" / "agents" / "supervisor" / "agent.md"


@pytest.fixture(scope="module")
def supervisor_prompt() -> str:
    assert SUPERVISOR_AGENT_MD.exists(), f"missing supervisor prompt: {SUPERVISOR_AGENT_MD}"
    return SUPERVISOR_AGENT_MD.read_text(encoding="utf-8")


class TestLaborHourExclusion:
    """NIH/NCI Labor-Hour exclusion — see commit 04cd419 for context."""

    def test_lh_marked_non_preferred(self, supervisor_prompt: str) -> None:
        # Lead bullet must state LH is non-preferred at NIH/NCI, not just "do not default to LH".
        # The weak "do not default" phrasing was the original leakage source.
        assert "non-preferred" in supervisor_prompt.lower(), (
            "supervisor prompt no longer marks Labor-Hour as a non-preferred contract vehicle. "
            "See commit 04cd419 — the weak 'do not default to LH' phrasing was specifically "
            "called out as insufficient because the model treats it as 'LH is still an option'."
        )

    def test_tm_replaces_lh_without_forcing_all_tm(self, supervisor_prompt: str) -> None:
        # EAGLE-210 removes LH terminology; EAGLE-300 still requires FFP/hybrid analysis.
        assert "use t&m only for residual variable demand" in supervisor_prompt.lower(), (
            "supervisor prompt must replace LH with T&M only for the residual variable "
            "portion, not force the whole acquisition into T&M."
        )
        assert "This rule does NOT mean \"all T&M.\"" in supervisor_prompt, (
            "supervisor prompt must explicitly prevent the NIH LH rule from becoming "
            "a blanket all-T&M recommendation."
        )

    def test_forbids_mentioning_lh_as_option(self, supervisor_prompt: str) -> None:
        # Must forbid mentioning/listing/suggesting LH as an option.
        prompt_lower = supervisor_prompt.lower()
        assert "do not mention" in prompt_lower or "do not mention, list" in prompt_lower, (
            "supervisor prompt no longer forbids mentioning Labor-Hour as an option. "
            "The rule must say something like 'do NOT mention, list, suggest, or present LH'."
        )

    def test_forbids_lh_appendage(self, supervisor_prompt: str) -> None:
        # Must explicitly forbid appending "or Labor Hour (LH)" / "/LH" to T&M.
        # This is how LH most commonly leaks: "T&M or LH", "T&M/LH", etc.
        forbids_appendage = (
            'do NOT append "or Labor Hour (LH)"' in supervisor_prompt
            or 'do NOT append \'or Labor Hour (LH)\'' in supervisor_prompt
        )
        assert forbids_appendage, (
            "supervisor prompt no longer forbids appending 'or Labor Hour (LH)' / '/LH' / "
            "any LH variant to T&M. This is the most common leakage pattern — restore it."
        )

    def test_leakage_cleanup_rule_present(self, supervisor_prompt: str) -> None:
        # Must instruct the supervisor to preserve FAR/KB source meaning while
        # translating final NIH/NCI recommendations away from LH terminology.
        prompt_lower = supervisor_prompt.lower()
        has_cleanup_rule = (
            ("specialist" in prompt_lower or "kb" in prompt_lower)
            and "translate" in prompt_lower
            and "lh" in prompt_lower
        )
        assert has_cleanup_rule, (
            "supervisor prompt no longer instructs the supervisor to translate LH references "
            "from downstream sources into NIH/NCI T&M recommendation language. "
            "Without this rule, LH reappears via 'T&M/LH' in compliance-strategist or "
            "FAR 52.232-7 citations."
        )

    def test_weak_phrasing_not_present(self, supervisor_prompt: str) -> None:
        # The exact weak phrasing that commit 04cd419 identified as the leakage source
        # must NOT be present. If a future PR reverts to "do NOT default to Labor-Hour",
        # this test fails immediately.
        weak_phrase = "do NOT default to Labor-Hour"
        assert weak_phrase not in supervisor_prompt, (
            f"supervisor prompt contains the weak phrasing {weak_phrase!r} which commit "
            "04cd419 specifically identified as insufficient (the model interprets it as "
            "'LH is still an option'). This usually means a recent PR reverted the "
            "strengthened wording. Re-strengthen per commit 04cd419 / 7bca862."
        )


class TestRequiredDocumentsFormat:
    """EAGLE-299 required-documents table contract."""

    def test_required_documents_use_trigger_template(self, supervisor_prompt: str) -> None:
        assert "| Document | Trigger | Template |" in supervisor_prompt
        assert "| Required?" not in supervisor_prompt
        assert "D&F for T&M/LH" not in supervisor_prompt
        assert "| D&F for T&M | T&M contract |" in supervisor_prompt


class TestAipContractTypeReasoning:
    """EAGLE-300 AIP scenario contract-type reasoning invariants."""

    def test_uncertain_scope_with_types_frequency_uses_unit_pricing_rule(
        self, supervisor_prompt: str
    ) -> None:
        prompt_lower = supervisor_prompt.lower()
        assert "uncertain scope but" in prompt_lower
        assert "types/frequency" in prompt_lower or "types and frequency" in prompt_lower
        assert "ffp unit/event pricing" in prompt_lower
        assert "service type breakdown" in prompt_lower
        assert "hybrid structure" in prompt_lower
        assert "t&m only for residual" in prompt_lower
