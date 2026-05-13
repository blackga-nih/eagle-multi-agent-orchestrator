"""Research cascade contract tests.

Verify that the supervisor prompt enforces:
  KB -> compliance matrix -> web search ordering.
"""

from __future__ import annotations

import pathlib

import pytest

from app.strands_agentic_service import build_supervisor_prompt


@pytest.fixture
def supervisor_prompt():
    return build_supervisor_prompt(
        tenant_id="dev-tenant",
        user_id="dev-user",
        tier="advanced",
        agent_names=[],
    )


def test_cascade_steps_present(supervisor_prompt):
    assert "STEP 1" in supervisor_prompt
    assert "STEP 2" in supervisor_prompt
    assert "STEP 3" in supervisor_prompt


def test_cascade_step_ordering(supervisor_prompt):
    assert (
        supervisor_prompt.index("STEP 1")
        < supervisor_prompt.index("STEP 2")
        < supervisor_prompt.index("STEP 3")
    )


def test_kb_is_primary_source(supervisor_prompt):
    assert "primary research method" in supervisor_prompt


def test_no_skip_to_web(supervisor_prompt):
    # The prompt enforces KB-first ordering; assert the STEP 1 "NEVER skip" language is present
    assert "NEVER skip" in supervisor_prompt


def test_compliance_matrix_referenced(supervisor_prompt):
    assert "query_compliance_matrix" in supervisor_prompt
    assert "FAC 2025-06" in supervisor_prompt


def test_exceptions_listed(supervisor_prompt):
    assert "EXCEPTIONS" in supervisor_prompt


def test_citation_rule(supervisor_prompt):
    assert "CITATION" in supervisor_prompt
    assert "Sources section" in supervisor_prompt


def test_agent_md_cascade_section():
    # Resolve relative to repo root (one level up from server/)
    repo_root = pathlib.Path(__file__).resolve().parent.parent.parent
    agent_md = (
        repo_root / "eagle-plugin" / "agents" / "supervisor" / "agent.md"
    ).read_text(encoding="utf-8")
    assert "MANDATORY RESEARCH CASCADE" in agent_md
    assert "Step 1" in agent_md
    assert "Step 2" in agent_md
    assert "Step 3" in agent_md


def test_citation_canonical_format_in_agent_md():
    """EAGLE-254: supervisor prompt must prescribe a single canonical Sources format.

    Regression for Jitong Li's 2026-04-23 report — the LLM rendered citations
    three different ways across three consecutive answers (title only, proper
    filename+directory, missing entirely). The prompt now requires `## Sources`
    H2 with `` `<filename>` — <directory>`` per line. Changing this shape
    without also updating the downstream eval assertions WILL regress the bug.
    """
    repo_root = pathlib.Path(__file__).resolve().parent.parent.parent
    agent_md = (
        repo_root / "eagle-plugin" / "agents" / "supervisor" / "agent.md"
    ).read_text(encoding="utf-8")
    assert "## Sources" in agent_md, "H2 Sources header must be the canonical format"
    # Canonical line splits filename and directory. Use the literal em-dash
    # that the prompt file contains (not a transliteration) — on Windows the
    # default cp1252 read would mojibake this check.
    assert "<filename>` — <directory>" in agent_md, (
        "Canonical line format must split filename and directory with an em-dash"
    )
    assert "EAGLE-254" in agent_md, (
        "Citation rule must reference the originating ticket so the rationale "
        "survives future edits"
    )


def test_research_slow_threshold_configurable():
    """EAGLE-254: research_tool must log WARN when a single call exceeds the
    soft SLO, and the threshold must be overridable via env var for ops tuning.
    """
    from app import strands_agentic_service as svc

    assert hasattr(svc, "_RESEARCH_SLOW_SECONDS"), (
        "research-tool slow SLO must be a module-level constant"
    )
    assert svc._RESEARCH_SLOW_SECONDS > 0
    assert hasattr(svc, "_research_tracer"), (
        "research-tool must own a dedicated OTEL tracer for child spans"
    )


def test_append_kb_sources_emits_canonical_format():
    """EAGLE-254: _append_kb_sources emits the canonical `## Sources` block
    with `` `<filename>` — <directory>`` lines, regardless of what the LLM
    produced. This is the deterministic fallback that eliminates the
    Q1/Q2/Q3 rendering variance Jitong reported."""
    from app.strands_agentic_service import _append_kb_sources

    kb_depth = {
        "fetched_keys": {
            "eagle-knowledge-base/approved/compliance-strategist/regulatory-policies/appropriations_law_severable_services.txt",
            "eagle-knowledge-base/approved/legal-counselor/appropriations-law/GAO_B-321640_ADA_Bonafide_Need_IDIQ.txt",
        }
    }

    # Case 1 — LLM emitted no Sources at all (Q3 failure mode).
    answer = "Severability determines which fiscal year funds a contract..."
    out, newly_surfaced = _append_kb_sources(answer, kb_depth)
    assert "## Sources" in out
    assert "`appropriations_law_severable_services.txt` — eagle-knowledge-base/approved/compliance-strategist/regulatory-policies/" in out
    assert "`GAO_B-321640_ADA_Bonafide_Need_IDIQ.txt` — eagle-knowledge-base/approved/legal-counselor/appropriations-law/" in out
    assert len(newly_surfaced) == 2

    # Case 2 — LLM emitted legacy `**Sources:**` bold format (old pattern).
    # Must be replaced with canonical H2, not duplicated.
    legacy = (
        "Answer body.\n\n"
        "**Sources:**\n"
        "- `eagle-knowledge-base/approved/compliance-strategist/regulatory-policies/appropriations_law_severable_services.txt`\n"
    )
    out2, _ = _append_kb_sources(legacy, kb_depth)
    assert out2.count("## Sources") == 1, "must emit exactly one canonical header"
    assert "**Sources:**" not in out2, "legacy bold header must be stripped"

    # Case 3 — LLM emitted `## Sources` in non-canonical line format (Q1 mode,
    # title-only). Must be rebuilt with canonical lines.
    wrong_format = (
        "Answer body.\n\n"
        "## Sources\n"
        "- HHS PMR Threshold Matrix; HHS GPC Streamlined Guide 2025\n"
    )
    out3, _ = _append_kb_sources(wrong_format, kb_depth)
    assert out3.count("## Sources") == 1
    assert "HHS PMR Threshold Matrix; HHS GPC Streamlined Guide" not in out3, (
        "non-canonical title-only line must be stripped"
    )
    assert "`appropriations_law_severable_services.txt` — " in out3

    # Case 4 — no docs fetched → no-op.
    out4, keys4 = _append_kb_sources("hi", {"fetched_keys": set()})
    assert out4 == "hi"
    assert keys4 == set()


def test_append_kb_sources_filters_templates():
    """EAGLE-308: Template files are filtered from the Sources section."""
    from app.strands_agentic_service import _append_kb_sources

    kb_depth = {
        "fetched_keys": {
            "eagle-knowledge-base/approved/templates/01.D_IGCE.xlsx",
            "eagle-knowledge-base/approved/templates/SOW_Template.docx",
            "eagle-knowledge-base/approved/compliance-strategist/FAR-guidance/FAR_Part_16.txt",
        }
    }

    out, newly_surfaced = _append_kb_sources("Answer text.", kb_depth)

    # Templates should be filtered out
    assert "IGCE" not in out, "template files must be filtered"
    assert "SOW_Template" not in out, "template files must be filtered"

    # Actual reference docs should be included
    assert "FAR_Part_16.txt" in out

    # Only non-template keys should be returned
    assert len(newly_surfaced) == 1
    assert "FAR_Part_16.txt" in list(newly_surfaced)[0]


def test_append_kb_sources_incremental():
    """EAGLE-308: Only new sources are shown in follow-up turns."""
    from app.strands_agentic_service import _append_kb_sources

    kb_depth = {
        "fetched_keys": {
            "eagle-knowledge-base/approved/doc1.txt",
            "eagle-knowledge-base/approved/doc2.txt",
        }
    }

    # First turn — both sources shown
    out1, keys1 = _append_kb_sources("First answer.", kb_depth)
    assert "## Sources" in out1
    assert "doc1.txt" in out1
    assert "doc2.txt" in out1
    assert len(keys1) == 2

    # Second turn — same sources already surfaced, nothing new
    out2, keys2 = _append_kb_sources("Second answer.", kb_depth, surfaced_keys=keys1)
    assert "## Sources" not in out2, "no sources section when all already surfaced"
    assert "Additional Sources" not in out2
    assert keys2 == set()

    # Third turn — one new source added
    kb_depth_new = {
        "fetched_keys": {
            "eagle-knowledge-base/approved/doc1.txt",
            "eagle-knowledge-base/approved/doc2.txt",
            "eagle-knowledge-base/approved/doc3.txt",
        }
    }
    out3, keys3 = _append_kb_sources("Third answer.", kb_depth_new, surfaced_keys=keys1)
    assert "## Additional Sources" in out3, "follow-up uses Additional Sources header"
    assert "doc3.txt" in out3
    assert "doc1.txt" not in out3, "already-surfaced sources not repeated"
    assert "doc2.txt" not in out3
    assert len(keys3) == 1
