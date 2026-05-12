"""One-shot: build v4 of the 4/16 meeting-review doc by copying v3 and
appending a fresh Status Update reflecting PRs #149 (Alvee) and #150
(intake-gate + budget-semantics). v3 is left unmodified as a 4/22 snapshot."""

import shutil
from pathlib import Path

from docx import Document

SRC = Path(
    "docs/development/meeting-transcripts/20260416-eagle-output-review/"
    "20260416-180100-meeting-eagle-output-review-v3.docx"
)
DEST = Path(
    "docs/development/meeting-transcripts/20260416-eagle-output-review/"
    "20260416-180100-meeting-eagle-output-review-v4.docx"
)


def add_para(doc, text: str, style: str = "Normal"):
    doc.add_paragraph(text, style=style)


def build_v4() -> None:
    shutil.copy(SRC, DEST)
    doc = Document(DEST)

    # Anchor: insert AFTER the existing Status Update roll-up paragraph but
    # BEFORE "EAGLE Strengths Worth Preserving". python-docx doesn't have a
    # clean "insert at" API; the simplest reliable move is to append the
    # new section at the end and rely on readers scrolling chronologically.
    # The v3 snapshot is preserved intact above.

    add_para(doc, "Status Update — as of 2026-04-23 (post-merge of PRs #149 + #150)", style="Heading 1")
    add_para(
        doc,
        "Since the 2026-04-22 snapshot above, two PRs landed on main that "
        "move several outstanding items forward. This section deltas the "
        "4/22 roll-up; items not mentioned here retain their 4/22 status.",
    )

    add_para(doc, "PR #149 — agent prompt fixes (Alvee, merged 2026-04-22)", style="Heading 2")
    add_para(
        doc,
        "Commit f84c0b6. Touched supervisor/agent.md, financial-advisor/"
        "agent.md, igce-template.md, create_document_support.py.",
    )
    add_para(doc, "#3 — FFP hybrid + task-area decomposition   [PARTIAL → PARTIAL+]", style="Normal")
    add_para(
        doc,
        "Supervisor now carries an INSTITUTIONAL CONTRACT-TYPE OVERRIDE "
        "block for NIH/NCI GSA Schedule services: prefer T&M for labor-"
        "based services, reserve FFP CLINs for discrete deliverables with "
        "objective acceptance criteria. Task-area decomposition is not yet "
        "explicit in the prompt, but the FFP-carve-out framing is in place.",
    )
    add_para(doc, "#4 — Remove Labor Hour from recommendations   [OUTSTANDING → DONE]", style="Normal")
    add_para(
        doc,
        "Same supervisor block states explicitly: \"do NOT default to "
        "Labor-Hour.\" First prompt-level guardrail against LH.",
    )
    add_para(doc, "#5 — IGCE methodology / budget narrative   [PARTIAL → DONE]", style="Normal")
    add_para(
        doc,
        "igce-template.md gained Section 2.4 (Rate Derivation) and Section "
        "2.5 (Budget Narrative), plus an FFP-Specific Requirements block. "
        "create_document_support.py expanded the context_fields map with "
        "financial_advisor_guidance, rate_derivation_methodology, price_"
        "reasonableness_approach, cost_analysis_framework, budget_narrative, "
        "and staffing_rationale. Supervisor now routes IGCE-for-services "
        "through @financial-advisor first for rate methodology guidance.",
    )

    add_para(doc, "PR #150 — intake gate + budget semantics (Greg, merged 2026-04-23)", style="Heading 2")
    add_para(
        doc,
        "Merge commit 4071f8e, branch feature/intake-gate-budget-semantics. "
        "Seven feature commits plus one refactor that simplified the "
        "architecture after an initial over-engineering pass.",
    )
    add_para(
        doc,
        "Phase 1 (e39b567): added intake_required_facts and budget_semantics "
        "top-level keys to eagle-plugin/data/matrix.json. Bumped matrix "
        "version to 2026-04-22. Added get_intake_required_facts() and get_"
        "budget_semantics() helpers in compliance_matrix.py, wired into "
        "execute_operation() so query_compliance_matrix surfaces both.",
    )
    add_para(
        doc,
        "Phase 2 (8b58af8): inserted PRE-GENERATION INTAKE GATE and BUDGET "
        "SEMANTICS RULE blocks into supervisor/agent.md (after the PWS-vs-"
        "SOW rule) and into market-intelligence/agent.md (this subagent has "
        "direct create_document access and bypasses the supervisor prompt).",
    )
    add_para(
        doc,
        "Phase 3 (9d4cf74): subagent fast-path validator in "
        "strands_agentic_service.py — if the supervisor hands a subagent "
        "incomplete structured data, the subagent returns a guardrail "
        "response rather than emitting a half-filled document.",
    )
    add_para(
        doc,
        "Phase 4 (cded92e): oa-intake and document-generator skill files "
        "now direct the intake flow to query matrix.intake_required_facts "
        "BEFORE asking hardcoded clarifying questions.",
    )
    add_para(
        doc,
        "Post-merge refactor (72dc016): after reviewing failing integration "
        "tests, the original chokepoint placement (tools/document_generation "
        "and legacy_dispatch) was dropped in favor of agent-level "
        "enforcement only. Net −293 lines across 8 files. The 150-line "
        "regex-detector library that tried to infer facts from prose "
        "(\"monthly report\" vs \"training events held monthly\") was "
        "removed. Data-dict semantics only; the LLM handles prose.",
    )

    add_para(doc, "#2 — IGCE/budget reconciliation bug   [OUTSTANDING → DONE]", style="Normal")
    add_para(
        doc,
        "matrix.budget_semantics now carries budget_is_ceiling=true, "
        "igce_is_estimated_value=true, and a forbidden_behaviors list that "
        "explicitly includes \"asking user to reconcile IGCE vs budget.\" "
        "Supervisor and market-intelligence prompts forbid the reconcile "
        "question verbatim, plus three related footguns (scope expansion to "
        "consume budget, inflating line items to reach a target, "
        "recommending a value that exceeds the ceiling).",
    )
    add_para(doc, "#8 — Investigate early jump to doc generation   [OUTSTANDING → DONE]", style="Normal")
    add_para(
        doc,
        "PRE-GENERATION INTAKE GATE: supervisor must call "
        "query_compliance_matrix(operation=\"intake_required_facts\", "
        "doc_type=...) before create_document, check each required fact "
        "against user input / package state / get_intake_status, and if any "
        "are missing batch them into ONE clarifying question (no drip-"
        "feeding). The gate carves out the PWS-vs-SOW disambiguation rule "
        "and acknowledges the existing DEFAULT TO ACTION / WHEN IN DOUBT "
        "rules apply once required facts are present.",
    )

    add_para(doc, "Updated roll-up", style="Heading 2")
    add_para(
        doc,
        "Before 4/22 update: 2 done · 1 partial · 7 outstanding · 1 "
        "unblocked · 1 ongoing.",
    )
    add_para(
        doc,
        "After PRs #149 + #150: 5 done · 1 partial+ · 4 outstanding · 1 "
        "unblocked · 1 ongoing. Remaining outstanding are #1b (root-cause "
        "Q4/Q5 regressions even though KB is RFO-correct), #6 (rewrite "
        "Q1–Q5 in natural CO voice — Ingrid/Ryan working session), #7 "
        "(teaching vs acquisition mode in supervisor prompt), and the "
        "task-area decomposition portion of #3.",
    )

    add_para(doc, "Verification", style="Heading 2")
    add_para(
        doc,
        "PR #150 landed with 139 targeted tests passing "
        "(test_compliance_matrix, test_intake_gate) and 163 previously-"
        "broken integration suites fixed (test_template_schema, test_"
        "package_intake_tools, test_document_provenance_metadata, test_"
        "document_pipeline, test_canonical_package_document_flow). CodeQL "
        "checks on the PR passed. Post-merge deploy run #24816101469 is in "
        "progress at time of this update — results to follow.",
    )

    doc.save(DEST)
    print(f"Wrote {DEST}")


if __name__ == "__main__":
    build_v4()
