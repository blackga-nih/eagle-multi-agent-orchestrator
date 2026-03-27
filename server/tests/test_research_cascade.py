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
    assert "primary source of truth" in supervisor_prompt


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
    agent_md = (repo_root / "eagle-plugin" / "agents" / "supervisor" / "agent.md").read_text()
    assert "MANDATORY RESEARCH CASCADE" in agent_md
    assert "Step 1" in agent_md
    assert "Step 2" in agent_md
    assert "Step 3" in agent_md
