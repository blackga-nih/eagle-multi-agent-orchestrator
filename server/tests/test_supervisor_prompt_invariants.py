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

    def test_tm_only_directive_present(self, supervisor_prompt: str) -> None:
        # Must explicitly say T&M only for GSA Schedule labor-based services.
        assert "T&M only" in supervisor_prompt, (
            "supervisor prompt no longer contains the explicit 'T&M only' directive for "
            "GSA Schedule labor-based services. Restore the strong wording from commit 04cd419."
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
        # Must instruct the supervisor to drop LH references that leak in from
        # specialists, KB excerpts, FAR cites, or templates (e.g. "T&M/LH" in
        # compliance-strategist/agent.md, "FAR 52.232-7 Payments under T&M/LH").
        prompt_lower = supervisor_prompt.lower()
        has_cleanup_rule = (
            ("specialist" in prompt_lower or "kb" in prompt_lower)
            and "drop" in prompt_lower
            and "lh" in prompt_lower
        )
        assert has_cleanup_rule, (
            "supervisor prompt no longer instructs the supervisor to strip LH references "
            "that leak in from downstream sources (specialist output, KB, FAR cites, templates). "
            "Without this rule, LH reappears via 'T&M/LH' in compliance-strategist or "
            "FAR 52.232-7 citations. Restore the leakage-cleanup bullet."
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
