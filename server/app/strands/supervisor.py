"""
EAGLE Strands Supervisor Prompt Building

Constructs the supervisor agent system prompt with available subagent
descriptions, progressive disclosure hints, and document output rules.
"""

from __future__ import annotations

import logging
import os
import sys
import time as _time
from datetime import datetime, timezone

logger = logging.getLogger("eagle.strands_agent")

# Add server/ to path for eagle_skill_constants
_server_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)

from eagle_skill_constants import AGENTS

from .registry import SKILL_AGENT_REGISTRY


def _build_doc_type_section_hints() -> str:
    """Build concise section hints for each doc type, for the supervisor prompt.

    Returns a compact string with one line per doc type listing section names.
    """
    try:
        from app.template_schema import load_template_schemas

        schemas = load_template_schemas()
    except Exception:
        return ""

    lines = []
    # Only include the primary doc types with rich schemas
    priority_types = [
        "sow",
        "igce",
        "acquisition_plan",
        "market_research",
        "justification",
    ]
    for dt in priority_types:
        schema = schemas.get(dt)
        if not schema or not schema.sections:
            continue
        section_names = [
            f"{s.number}. {s.title}" if s.number else s.title
            for s in schema.sections[:12]  # Cap at 12 for prompt brevity
        ]
        lines.append(f"    {dt.upper()}: {' | '.join(section_names)}")

    if lines:
        return "\n".join(lines) + "\n"
    return ""


# Pre-compute at module load — output is static (changes only on deployment)
_DOC_SECTION_HINTS: str = _build_doc_type_section_hints()

# Prompt cache with TTL
_supervisor_prompt_cache: dict[tuple, tuple[float, str]] = {}
_PROMPT_CACHE_TTL = 120  # seconds


def _build_supervisor_prompt_body(
    tenant_id: str,
    user_id: str,
    tier: str,
    agent_names: list[str] | None,
    workspace_id: str | None,
) -> str:
    """Build the supervisor prompt body (everything except the timestamp header).

    Resolves through the 4-layer chain: workspace override → DynamoDB →
    bundled content → fallback.
    """
    names = agent_names or list(SKILL_AGENT_REGISTRY.keys())
    agent_list = "\n".join(
        f"- {name}: {SKILL_AGENT_REGISTRY[name]['description']}"
        for name in names
        if name in SKILL_AGENT_REGISTRY
    )

    # Resolve supervisor prompt via workspace chain
    base_prompt = ""
    if workspace_id:
        try:
            from ..workspace_override_store import resolve_agent

            base_prompt, _source = resolve_agent(tenant_id, user_id, workspace_id, "supervisor")
        except Exception as exc:
            logger.warning(
                "workspace_override_store.resolve_agent failed for supervisor: %s -- using bundled",
                exc,
            )

    if not base_prompt:
        supervisor_entry = AGENTS.get("supervisor")
        base_prompt = (
            supervisor_entry["body"].strip()
            if supervisor_entry
            else "You are the EAGLE Supervisor Agent for NCI Office of Acquisitions."
        )

    return (
        f"{base_prompt}\n\n"
        f"--- ACTIVE SPECIALISTS ---\n"
        f"Available specialists for delegation:\n{agent_list}\n\n"
        "Progressive Disclosure (how to find information):\n"
        "  You have layered access to skills and data. Use the lightest layer that answers the question:\n"
        "  Layer 1 — System prompt hints (you already have short descriptions above).\n"
        "  Layer 2 — list_skills(): Discover available skills, agents, and data files with descriptions.\n"
        "  Layer 3 — load_skill(name): Read full skill instructions/workflows to follow them yourself.\n"
        "  Layer 4 — load_data(name, section?): Fetch reference data (thresholds, vehicles, doc rules).\n"
        "  Only spawn a specialist subagent when you need expert reasoning, not for simple lookups.\n\n"
        "KB Retrieval Rules:\n"
        "1) For policy/regulation/procedure/template questions, call knowledge_search first.\n"
        "2) If search returns results, call knowledge_fetch on the top 1-3 relevant docs.\n"
        "3) In final answer, include a Sources section with title + s3_key.\n"
        "4) If no results, explicitly say no KB match and ask a refinement question.\n"
        "5) Prefer knowledge_search/knowledge_fetch over search_far when KB can answer.\n"
        "6) When search_far returns results with non-empty s3_keys, you MUST call "
        "knowledge_fetch on the top result's s3_key to read the full FAR document "
        "BEFORE responding. Never answer from the summary alone — summaries are partial "
        "and may omit critical clauses, exceptions, or requirements.\n"
        "7) If a search_far result has empty s3_keys, the summary is the best available — "
        "note that no full-text source was available for that clause.\n\n"
        "Document Output Rules:\n"
        "0) CHECK BEFORE CREATE: Before generating any document, call get_latest_document "
        "with the package_id and doc_type to check if one already exists. If it does:\n"
        "   - For CONTENT changes (add sections, rewrite, regenerate): call create_document "
        "with update_existing_key set to the existing document's s3_key. Write the FULL "
        "updated content incorporating the requested changes.\n"
        "   - For TARGETED edits (fix a typo, change a name, toggle a checkbox): call "
        "edit_docx_document with the document_key and specific edits.\n"
        "   - Only create a brand-new document (no update_existing_key) if no existing "
        "document was found for that doc_type.\n"
        "1) If the user asks to generate/draft/create a document, you MUST call create_document.\n"
        "1a) CRITICAL: Write the COMPLETE document content as the 'content' field (markdown with "
        "section headings, filled-in details from the conversation). Do NOT leave template "
        "placeholders — fill every section with specifics from the intake discussion.\n"
        "1b) Also pass structured fields in 'data' (description, estimated_value, "
        "period_of_performance, competition, contract_type, deliverables, tasks, etc.) "
        "for template population.\n"
        "1c) If the user asks to revise an existing DOCX document, use edit_docx_document "
        "for targeted edits and checkbox_edits for checklist toggles.\n"
        "1d) SECTION GUIDANCE — each document type has required sections. Fill ALL of them:\n"
        f"{_DOC_SECTION_HINTS}"
        "2) Do not paste full document bodies in chat unless the user explicitly asks for inline text.\n"
        "3) After create_document, respond briefly and direct the user to open/edit the document card.\n\n"
        "FAST vs DEEP routing:\n"
        "  FAST (seconds):\n"
        "    - load_data('matrix', 'thresholds') for threshold lookups.\n"
        "    - load_data('contract-vehicles', 'nitaac') for vehicle details.\n"
        "    - query_compliance_matrix for computed compliance decisions.\n"
        "    - search_far → knowledge_fetch(s3_key) for FAR/DFARS clause lookups (search, then read full doc).\n"
        "    - knowledge_search → knowledge_fetch for KB documents.\n"
        "    - load_skill(name) to read a workflow and follow it yourself.\n"
        "  DEEP (specialist): Delegate to specialist subagents only for complex analysis,\n"
        "    multi-factor evaluation, or expert reasoning — not simple factual lookups.\n"
        "  ALWAYS prefer FAST tools first. Only delegate to a specialist when FAST tools don't suffice.\n\n"
        "IMPORTANT: Use the available tool functions to delegate to specialists. "
        "Include relevant context in the query you pass to each specialist. "
        "Do not try to answer specialized questions yourself -- delegate to the expert."
    )


def build_supervisor_prompt(
    tenant_id: str = "demo-tenant",
    user_id: str = "demo-user",
    tier: str = "advanced",
    agent_names: list[str] | None = None,
    workspace_id: str | None = None,
) -> str:
    """Build the supervisor system prompt with available subagent descriptions.

    Caches the prompt body per (tenant_id, workspace_id, tier) with 120s TTL.
    Only the timestamp header is dynamic on every call.
    """
    cache_key = (tenant_id, workspace_id or "", tier)
    now = _time.time()
    entry = _supervisor_prompt_cache.get(cache_key)

    if entry and now < entry[0]:
        body = entry[1]
    else:
        body = _build_supervisor_prompt_body(tenant_id, user_id, tier, agent_names, workspace_id)
        _supervisor_prompt_cache[cache_key] = (now + _PROMPT_CACHE_TTL, body)

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S UTC")
    return f"Tenant: {tenant_id} | User: {user_id} | Tier: {tier} | Current datetime: {now_utc}\n\n{body}"
