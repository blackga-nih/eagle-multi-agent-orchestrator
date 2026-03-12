"""Agent-as-Tool document generator.

Loads a template markdown, builds a focused prompt with conversation context,
calls the model in a single turn (no tools), validates required fields, and
returns a structured DocumentResult.

Replaces the 10 hardcoded _generate_* functions with LLM-driven content
that uses NCI templates as structural guidelines.
"""
from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger("eagle.document_agent")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_PLUGIN_DIR = Path(__file__).resolve().parent.parent.parent / "eagle-plugin"
_TEMPLATE_DIR = _PLUGIN_DIR / "data" / "templates"
_REQUIRED_FIELDS_PATH = _TEMPLATE_DIR / "required_fields.yaml"

# Normalised doc_type → template filename
_TEMPLATE_MAP: dict[str, str] = {
    "sow": "sow-template.md",
    "igce": "igce-template.md",
    "acquisition_plan": "acquisition-plan-template.md",
    "justification": "justification-template.md",
    "market_research": "market-research-template.md",
    # These five have no dedicated template — we'll use a generic instruction.
    "eval_criteria": "",
    "security_checklist": "",
    "section_508": "",
    "cor_certification": "",
    "contract_type_justification": "",
}

# Cache for required_fields.yaml
_required_fields_cache: dict | None = None


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class OmissionEntry:
    section: str
    status: str        # "partial", "omitted", "default"
    reason: str
    info_needed: str


@dataclass
class JustificationEntry:
    decision: str
    reasoning: str
    far_basis: str
    confidence: str    # "high", "medium", "low"


@dataclass
class DocumentResult:
    success: bool
    doc_type: str
    title: str = ""
    content: str = ""
    main_body: str = ""
    omissions_appendix: str = ""
    reasoning_appendix: str = ""
    omissions: list[dict] = field(default_factory=list)
    justifications: list[dict] = field(default_factory=list)
    missing_required: list[str] = field(default_factory=list)
    word_count: int = 0
    error: str = ""


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def _load_template(doc_type: str) -> str:
    """Load the template markdown for *doc_type*.

    Returns the full file content or a short generic instruction if no
    dedicated template exists.
    """
    filename = _TEMPLATE_MAP.get(doc_type, "")
    if not filename:
        return (
            f"No dedicated template exists for '{doc_type}'. "
            "Use standard Federal Acquisition formatting with numbered sections, "
            "NCI/NIH header, and EAGLE footer."
        )

    path = _TEMPLATE_DIR / filename
    if not path.is_file():
        logger.warning("Template file not found: %s", path)
        return f"Template file missing for '{doc_type}'. Use standard formatting."

    return path.read_text(encoding="utf-8")


def _load_required_fields(doc_type: str) -> dict:
    """Load required/recommended fields for *doc_type* from YAML schema."""
    global _required_fields_cache
    if _required_fields_cache is None:
        if _REQUIRED_FIELDS_PATH.is_file():
            with open(_REQUIRED_FIELDS_PATH, encoding="utf-8") as f:
                _required_fields_cache = yaml.safe_load(f) or {}
        else:
            logger.warning("required_fields.yaml not found at %s", _REQUIRED_FIELDS_PATH)
            _required_fields_cache = {}

    return _required_fields_cache.get(doc_type, {})


# ---------------------------------------------------------------------------
# Context builders
# ---------------------------------------------------------------------------

def _load_conversation_context(
    session_id: str,
    tenant_id: str,
    user_id: str,
    max_messages: int = 20,
) -> str:
    """Build a text summary of recent conversation messages for the prompt."""
    try:
        from app.session_store import get_messages

        leaf = _extract_leaf(session_id)
        if not leaf:
            return "(no conversation history available)"

        messages = get_messages(leaf, tenant_id, user_id, limit=max_messages)
        if not messages:
            return "(no conversation history available)"

        lines: list[str] = []
        for msg in messages:
            role = msg.get("role", "unknown").upper()
            content = msg.get("content", "")
            if isinstance(content, list):
                parts = []
                for block in content:
                    if isinstance(block, dict):
                        t = block.get("text", "")
                        if t:
                            parts.append(t.strip())
                content = "\n".join(parts)
            if not content or not content.strip():
                continue
            # Truncate very long messages
            if len(content) > 1500:
                content = content[:1500] + " [truncated]"
            lines.append(f"[{role}]: {content.strip()}")

        return "\n\n".join(lines) if lines else "(no conversation history available)"
    except Exception as exc:
        logger.debug("Failed to load conversation context: %s", exc)
        return "(conversation history unavailable)"


def _load_state_snapshot(session_id: str, tenant_id: str, user_id: str) -> str:
    """Load the current Strands agent state snapshot, if available.

    In the Strands service, state is held in ``agent.state`` and synced to
    DynamoDB via the SessionManager. We attempt to read the latest persisted
    state for this session.
    """
    try:
        from app.session_store import get_messages

        leaf = _extract_leaf(session_id)
        if not leaf:
            return "(no state available)"

        # Look for the most recent state snapshot stored as a special message
        messages = get_messages(leaf, tenant_id, user_id, limit=50)
        # Walk backwards to find the latest assistant message that looks like state
        for msg in reversed(messages):
            content = msg.get("content", "")
            if isinstance(content, str) and "STATE#" in content:
                return content[:3000]

        return "(no structured state found — agent will infer from conversation)"
    except Exception:
        return "(state unavailable)"


def _extract_leaf(session_id: str) -> str | None:
    """Extract raw session id from composite format."""
    if not session_id:
        return None
    if "#" in session_id:
        parts = session_id.split("#", 3)
        if len(parts) >= 4 and parts[3]:
            return parts[3]
        return None
    return session_id


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are a Federal Acquisition document specialist for the National Cancer Institute (NCI), \
part of the National Institutes of Health (NIH), Department of Health and Human Services.

You produce professional, regulation-compliant acquisition documents. Your output is the document itself — \
no preamble, no conversational text, no explanation outside the document.

## Quality standards
- Write full prose for every section — no placeholders like [TBD], [To be determined], or {{VARIABLE}}
- Infer reasonable NCI/NIH defaults when specific data is unavailable (e.g., Bethesda location, FAR applicability)
- Use active voice and concise government writing style
- Cite applicable FAR/HHSAR clauses where appropriate
- Number sections consistently following the template structure
"""

_USER_PROMPT_TEMPLATE = """## Your Task
Write a complete **{display_name}** document based on the conversation context below.

## Template Reference
Use these sections as structural guidelines. Adapt, expand, merge, or reorganize sections \
based on the available context. The template shows the expected structure — you write the content.

<template>
{template_content}
</template>

## Conversation Context
<context>
{conversation_context}
</context>

## Current State
<state>
{state_snapshot}
</state>

{special_instructions_block}

## Required Fields
The following sections MUST appear in your document (even if with limited information):
{required_fields_list}

## Recommended Fields (include if you have enough context)
{recommended_fields_list}

## Appendix Instructions
After the main document, include TWO appendices:

### Appendix A: Omissions & Information Gaps
A markdown table with these columns:
| Section | Status | Reason | Information Needed |

Status values: Partial (some info available), Omitted (no info available), Default (used NCI standard default).
Include every section where you lacked specific information from the conversation.

### Appendix B: AI Decision Rationale
For each significant decision you made while writing (e.g., contract type selection, set-aside \
recommendation, pricing methodology, authority cited, competition strategy), write a short entry:

**[Decision Title]**
[2-3 sentence explanation of the reasoning and the FAR/HHSAR/policy basis]

## Output Format
- Clean markdown
- Start with the document title as H1
- End with: `*This document was generated by EAGLE — NCI Acquisition Assistant*`
- Do NOT include any text before the document title or after the EAGLE footer
"""


def _build_prompt(
    doc_type: str,
    template_content: str,
    conversation_context: str,
    state_snapshot: str,
    required_fields: dict,
    special_instructions: str = "",
) -> str:
    """Build the user prompt for document generation."""
    display_name = required_fields.get("display_name", doc_type.replace("_", " ").title())

    req_sections = required_fields.get("required_sections", [])
    rec_sections = required_fields.get("recommended_sections", [])

    required_list = "\n".join(f"- {s.replace('_', ' ').title()}" for s in req_sections) or "- (none specified)"
    recommended_list = "\n".join(f"- {s.replace('_', ' ').title()}" for s in rec_sections) or "- (none specified)"

    special_block = ""
    if special_instructions:
        special_block = f"""## Special Instructions from User
{special_instructions}
"""

    return _USER_PROMPT_TEMPLATE.format(
        display_name=display_name,
        template_content=template_content,
        conversation_context=conversation_context,
        state_snapshot=state_snapshot,
        special_instructions_block=special_block,
        required_fields_list=required_list,
        recommended_fields_list=recommended_list,
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_required_fields(content: str, required_sections: list[str]) -> list[str]:
    """Check that required sections appear (by keyword) in the generated content.

    Returns a list of section names that appear to be missing.
    """
    if not content or not required_sections:
        return []

    lower = content.lower()
    missing: list[str] = []

    # Map section keys to search patterns
    _patterns: dict[str, list[str]] = {
        "title": [],  # Title is always present if content exists
        "background_and_purpose": ["background", "purpose"],
        "scope": ["scope"],
        "period_of_performance": ["period of performance"],
        "tasks": ["task"],
        "deliverables": ["deliverable"],
        "applicable_standards": ["applicable", "standards"],
        "place_of_performance": ["place of performance"],
        "security_requirements": ["security"],
        "qasp": ["quality assurance", "qasp"],
        "purpose": ["purpose"],
        "methodology": ["methodology", "method"],
        "cost_breakdown": ["cost breakdown", "cost summary", "direct cost", "line item"],
        "total_estimated_cost": ["total", "estimated cost", "grand total"],
        "assumptions": ["assumption"],
        "confidence_level": ["confidence"],
        "data_sources": ["data source", "reference"],
        "statement_of_need": ["statement of need", "background"],
        "competition_strategy": ["competition", "competitive"],
        "contract_type": ["contract type"],
        "milestones": ["milestone", "schedule"],
        "authority_cited": ["authority", "far 6.302"],
        "contractor_name": ["contractor", "proposed source"],
        "description_of_action": ["description of action", "description"],
        "rationale": ["rationale", "justification", "reason"],
        "market_research_summary": ["market research"],
        "description_of_need": ["description of need", "description"],
        "sources_consulted": ["sources consulted", "sources"],
        "potential_sources": ["potential source", "vendor"],
        "recommendation": ["recommendation", "conclusion"],
        "evaluation_factors": ["evaluation factor", "factor"],
        "rating_scale": ["rating", "scale"],
        "basis_for_award": ["basis for award", "award"],
        "security_assessment": ["security assessment", "assessment"],
        "impact_level": ["impact level", "fips"],
        "far_clauses": ["far clause", "clause"],
        "applicability": ["applicability", "applicable"],
        "product_types": ["product type"],
        "exception_determination": ["exception"],
        "nominee_information": ["nominee"],
        "fac_cor_level": ["fac-cor", "cor level"],
        "delegated_duties": ["delegated", "duties"],
        "findings": ["finding"],
        "determination": ["determination"],
        "risk_assessment": ["risk"],
        "contractor_personnel": ["personnel", "key personnel"],
        "travel_requirements": ["travel"],
    }

    for section in required_sections:
        if section == "title":
            # Title is always present if there's any content
            continue
        patterns = _patterns.get(section, [section.replace("_", " ")])
        found = any(p in lower for p in patterns)
        if not found:
            missing.append(section)

    return missing


# ---------------------------------------------------------------------------
# Appendix parsing
# ---------------------------------------------------------------------------

def _parse_appendices(content: str) -> tuple[str, str, str]:
    """Split generated content into (main_body, omissions_appendix, reasoning_appendix).

    Looks for 'Appendix A' and 'Appendix B' headings.
    """
    # Find Appendix A
    app_a_pattern = re.compile(
        r"^#{1,3}\s+Appendix\s+A[:\s]",
        re.MULTILINE | re.IGNORECASE,
    )
    app_b_pattern = re.compile(
        r"^#{1,3}\s+Appendix\s+B[:\s]",
        re.MULTILINE | re.IGNORECASE,
    )

    main_body = content
    omissions = ""
    reasoning = ""

    match_a = app_a_pattern.search(content)
    match_b = app_b_pattern.search(content)

    if match_a and match_b and match_a.start() < match_b.start():
        main_body = content[:match_a.start()].rstrip()
        omissions = content[match_a.start():match_b.start()].rstrip()
        reasoning = content[match_b.start():].rstrip()
    elif match_a and not match_b:
        main_body = content[:match_a.start()].rstrip()
        omissions = content[match_a.start():].rstrip()
    elif match_b and not match_a:
        main_body = content[:match_b.start()].rstrip()
        reasoning = content[match_b.start():].rstrip()

    return main_body, omissions, reasoning


def _parse_omission_table(omissions_md: str) -> list[dict]:
    """Parse the omissions appendix markdown table into structured data."""
    entries: list[dict] = []
    for line in omissions_md.splitlines():
        line = line.strip()
        if not line.startswith("|") or line.startswith("| Section") or line.startswith("|---"):
            continue
        parts = [p.strip() for p in line.split("|")]
        # Filter empty strings from split
        parts = [p for p in parts if p]
        if len(parts) >= 4:
            entries.append({
                "section": parts[0],
                "status": parts[1],
                "reason": parts[2],
                "info_needed": parts[3],
            })
    return entries


def _parse_justification_entries(reasoning_md: str) -> list[dict]:
    """Parse the reasoning appendix into structured entries."""
    entries: list[dict] = []
    current_decision = ""
    current_text: list[str] = []

    for line in reasoning_md.splitlines():
        if line.startswith("**") and line.endswith("**"):
            # Save previous entry
            if current_decision and current_text:
                entries.append({
                    "decision": current_decision,
                    "reasoning": " ".join(current_text).strip(),
                })
            current_decision = line.strip("* ")
            current_text = []
        elif line.strip() and not line.startswith("#") and not line.startswith("|"):
            current_text.append(line.strip())

    # Save last entry
    if current_decision and current_text:
        entries.append({
            "decision": current_decision,
            "reasoning": " ".join(current_text).strip(),
        })

    return entries


# ---------------------------------------------------------------------------
# Title extraction
# ---------------------------------------------------------------------------

def _extract_title(content: str, doc_type: str) -> str:
    """Extract the document title from the first H1 or H2 heading."""
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line.lstrip("# ").strip()
        if line.startswith("## "):
            return line.lstrip("# ").strip()
    display = _load_required_fields(doc_type).get("display_name", doc_type.replace("_", " ").title())
    return f"Untitled {display}"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_document(
    doc_type: str,
    session_id: str,
    tenant_id: str,
    user_id: str,
    special_instructions: str = "",
    model: Optional[object] = None,
) -> DocumentResult:
    """Generate an acquisition document using LLM-driven content.

    This is the Agent-as-Tool entry point. The supervisor calls this via a
    @tool wrapper in strands_agentic_service.py.

    Args:
        doc_type: One of the 10 supported document types.
        session_id: Composite session ID (tenant#tier#user#session).
        tenant_id: Tenant identifier.
        user_id: User identifier.
        special_instructions: Optional user guidance for this generation.
        model: Optional pre-configured model instance (BedrockModel or similar).
               If None, creates a new BedrockModel.

    Returns:
        DocumentResult with the generated content, appendices, and metadata.
    """
    start = time.monotonic()

    # Validate doc_type
    valid_types = set(_TEMPLATE_MAP.keys())
    if doc_type not in valid_types:
        return DocumentResult(
            success=False,
            doc_type=doc_type,
            error=f"Unknown doc_type '{doc_type}'. Valid: {sorted(valid_types)}",
        )

    # 1. Load template
    template_content = _load_template(doc_type)

    # 2. Load required fields schema
    req_fields = _load_required_fields(doc_type)

    # 3. Load conversation context + state
    conversation_context = _load_conversation_context(session_id, tenant_id, user_id)
    state_snapshot = _load_state_snapshot(session_id, tenant_id, user_id)

    # 4. Build prompt
    user_prompt = _build_prompt(
        doc_type=doc_type,
        template_content=template_content,
        conversation_context=conversation_context,
        state_snapshot=state_snapshot,
        required_fields=req_fields,
        special_instructions=special_instructions,
    )

    # 5. Call model
    try:
        content = _call_model(user_prompt, model)
    except Exception as exc:
        logger.error("Model call failed for doc_type=%s: %s", doc_type, exc)
        return DocumentResult(
            success=False,
            doc_type=doc_type,
            error=f"Model call failed: {exc}",
        )

    if not content or not content.strip():
        return DocumentResult(
            success=False,
            doc_type=doc_type,
            error="Model returned empty content",
        )

    # 6. Parse appendices
    main_body, omissions_md, reasoning_md = _parse_appendices(content)

    # 7. Validate required fields
    required_sections = req_fields.get("required_sections", [])
    missing = _validate_required_fields(main_body, required_sections)

    # 8. Parse structured appendix data
    omission_entries = _parse_omission_table(omissions_md)
    justification_entries = _parse_justification_entries(reasoning_md)

    # 9. Extract title
    title = _extract_title(content, doc_type)

    elapsed = time.monotonic() - start
    logger.info(
        "Document generated: type=%s title=%s words=%d missing=%d elapsed=%.1fs",
        doc_type, title, len(content.split()), len(missing), elapsed,
    )

    return DocumentResult(
        success=True,
        doc_type=doc_type,
        title=title,
        content=content,
        main_body=main_body,
        omissions_appendix=omissions_md,
        reasoning_appendix=reasoning_md,
        omissions=omission_entries,
        justifications=justification_entries,
        missing_required=missing,
        word_count=len(content.split()),
    )


# ---------------------------------------------------------------------------
# Model call
# ---------------------------------------------------------------------------

def _call_model(user_prompt: str, model: Optional[object] = None) -> str:
    """Call the model with the document generation prompt.

    Uses a Strands Agent with no tools for a single-turn text generation,
    or falls back to direct Bedrock converse() if Agent isn't available.
    """
    if model is None:
        model = _get_default_model()

    try:
        from strands import Agent

        agent = Agent(
            model=model,
            system_prompt=_SYSTEM_PROMPT,
            tools=[],
        )
        result = agent(user_prompt)
        # Strands Agent returns an AgentResult; extract text
        return str(result)
    except ImportError:
        logger.info("Strands not available, falling back to direct model call")
        return _direct_model_call(user_prompt, model)


def _get_default_model():
    """Create a default BedrockModel instance."""
    from strands.models import BedrockModel
    from botocore.config import Config

    config = Config(
        read_timeout=120,
        retries={"max_attempts": 3, "mode": "adaptive"},
    )
    return BedrockModel(
        model_id=os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-20250514"),
        region_name=os.getenv("AWS_REGION", "us-east-1"),
        boto_client_config=config,
    )


def _direct_model_call(user_prompt: str, model: object) -> str:
    """Fallback: direct model.converse() call without Strands Agent."""
    try:
        messages = [{"role": "user", "content": [{"text": user_prompt}]}]
        response = model.converse(
            messages=messages,
            system=[{"text": _SYSTEM_PROMPT}],
            inferenceConfig={
                "maxTokens": 8192,
                "temperature": 0.3,
            },
        )
        output = response.get("output", {})
        message = output.get("message", {})
        content_blocks = message.get("content", [])
        text_parts = [b["text"] for b in content_blocks if "text" in b]
        return "\n".join(text_parts)
    except Exception as exc:
        logger.error("Direct model call failed: %s", exc)
        raise
