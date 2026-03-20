"""
EAGLE Strands Prompt Utilities

Functions for parsing, normalizing, and extracting information from prompts.
Used by fast-path document generation and service tools.
"""

from __future__ import annotations

import re
from typing import Any

# Fast-path document generation hints
DOC_TYPE_HINTS: list[tuple[str, list[str]]] = [
    ("sow", ["statement of work", " sow"]),
    ("igce", ["igce", "ige", "independent government estimate", "independent government cost estimate", "cost estimate"]),
    ("market_research", ["market research"]),
    ("acquisition_plan", ["acquisition plan"]),
    ("justification", ["justification", "j&a", "j and a", "sole source"]),
    ("eval_criteria", ["evaluation criteria", "eval criteria"]),
    ("security_checklist", ["security checklist"]),
    ("section_508", ["section 508", "508 compliance"]),
    ("cor_certification", ["cor certification"]),
    ("contract_type_justification", ["contract type justification"]),
]

DOC_TYPE_LABELS: dict[str, str] = {
    "sow": "Statement of Work",
    "igce": "Independent Government Cost Estimate",
    "market_research": "Market Research",
    "acquisition_plan": "Acquisition Plan",
    "justification": "Justification & Approval",
    "eval_criteria": "Evaluation Criteria",
    "security_checklist": "Security Checklist",
    "section_508": "Section 508 Compliance",
    "cor_certification": "COR Certification",
    "contract_type_justification": "Contract Type Justification",
}

DIRECT_DOC_VERBS = ("generate", "draft", "create", "write", "produce")
DOC_EDIT_VERBS = ("edit", "update", "revise", "modify", "fill", "rewrite", "adjust", "amend")
SLOW_PATH_HINTS = ("research", "far", "dfars", "policy", "compare", "analyze")
DOC_REQUEST_BLOCKERS = (
    "what is",
    "what's",
    "how do i",
    "how to",
    "explain",
    "difference between",
)

PROMPT_SECTION_ALIASES = {
    "project description": "project_description",
    "technical requirements": "technical_requirements",
    "scope of work": "scope_of_work",
    "deliverables": "deliverables",
    "environment tiers": "environment_tiers",
    "security": "security",
}


def normalize_prompt(prompt: str) -> str:
    """Normalize whitespace and lowercase a prompt for matching."""
    return re.sub(r"\s+", " ", prompt.strip().lower())


def extract_user_request_from_prompt(prompt: str) -> str:
    """Extract the [USER REQUEST] block from document-viewer prompts."""
    if not prompt:
        return ""
    marker = "[USER REQUEST]"
    if marker not in prompt:
        return ""

    tail = prompt.split(marker, 1)[1]
    for stop in ("\n[", "\nInstruction:"):
        idx = tail.find(stop)
        if idx >= 0:
            tail = tail[:idx]
            break
    return tail.strip()


def extract_document_context_from_prompt(prompt: str) -> dict[str, str]:
    """Extract document viewer context blocks from wrapped prompts."""
    if not prompt:
        return {}

    out: dict[str, str] = {}

    title_match = re.search(r"(?im)^\s*Title:\s*(.+?)\s*$", prompt)
    if title_match:
        out["title"] = title_match.group(1).strip()

    type_match = re.search(r"(?im)^\s*Type:\s*([a-z0-9_ -]+)\s*$", prompt)
    if type_match:
        out["document_type"] = type_match.group(1).strip().lower().replace(" ", "_")

    excerpt_match = re.search(
        r"(?is)Current Content Excerpt:\s*(.+?)(?:\n\s*\[ORIGIN SESSION CONTEXT\]|\n\s*\[USER REQUEST\]|$)",
        prompt,
    )
    if excerpt_match:
        out["current_content"] = excerpt_match.group(1).strip()

    user_request = extract_user_request_from_prompt(prompt)
    if user_request:
        out["user_request"] = user_request

    return out


def infer_doc_type_from_prompt(prompt: str) -> str | None:
    """Infer document type from prompt text using hint patterns."""
    lowered = f" {normalize_prompt(prompt)} "
    for doc_type, hints in DOC_TYPE_HINTS:
        if any(hint in lowered for hint in hints):
            return doc_type
    return None


def is_document_generation_request(prompt: str) -> tuple[bool, str | None]:
    """Check if prompt is a document generation request."""
    lowered = normalize_prompt(prompt)
    doc_type = infer_doc_type_from_prompt(prompt)
    if not doc_type:
        return False, None
    if any(lowered.startswith(blocker) for blocker in DOC_REQUEST_BLOCKERS):
        return False, None
    if any(v in lowered for v in DIRECT_DOC_VERBS):
        return True, doc_type

    # Document-viewer prompts include explicit wrappers
    if "[document context]" in lowered and "[user request]" in lowered:
        user_req = extract_user_request_from_prompt(prompt).lower()
        if any(v in user_req for v in DIRECT_DOC_VERBS) or any(v in user_req for v in DOC_EDIT_VERBS):
            return True, doc_type

    phrase = DOC_TYPE_LABELS.get(doc_type, doc_type.replace("_", " ")).lower()
    if lowered.startswith(phrase):
        return True, doc_type
    if re.search(rf"\b(need|want|please)\b.*\b{re.escape(phrase)}\b", lowered):
        return True, doc_type

    return False, None


def should_use_fast_document_path(prompt: str) -> tuple[bool, str | None]:
    """Determine if fast-path document generation should be used."""
    should_generate, doc_type = is_document_generation_request(prompt)
    if not should_generate or not doc_type:
        return False, None

    lowered = normalize_prompt(prompt)
    if "[document context]" in lowered:
        return False, None
    if any(h in lowered for h in SLOW_PATH_HINTS):
        return False, None
    return True, doc_type


def extract_prompt_sections(prompt: str) -> dict[str, list[str]]:
    """Extract structured sections from a prompt."""
    sections: dict[str, list[str]] = {}
    current: str | None = None

    for raw_line in (prompt or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        heading = line.rstrip(":").strip().lower()
        if heading in PROMPT_SECTION_ALIASES:
            current = PROMPT_SECTION_ALIASES[heading]
            sections.setdefault(current, [])
            continue

        if line.startswith("- ") or line.startswith("* "):
            item = line[2:].strip().strip('"')
            if not item:
                continue
            bucket = current or "general"
            sections.setdefault(bucket, []).append(item)

    return sections


def extract_context_data_from_prompt(prompt: str, doc_type: str) -> dict[str, Any]:
    """Derive create_document data fields from the user prompt."""
    if not prompt:
        return {}

    data: dict[str, Any] = {}
    doc_ctx = extract_document_context_from_prompt(prompt)
    if doc_ctx.get("current_content"):
        data["current_content"] = doc_ctx["current_content"]
    if doc_ctx.get("user_request"):
        data["edit_request"] = doc_ctx["user_request"]

    sections = extract_prompt_sections(prompt)

    project_description = " ".join(sections.get("project_description", [])).strip()
    if project_description:
        data["description"] = project_description[:500]
        data["requirement"] = project_description[:500]
    else:
        user_req = extract_user_request_from_prompt(prompt)
        if user_req:
            data["description"] = user_req[:500]
            data["requirement"] = user_req[:500]

    scope_items = sections.get("scope_of_work", [])
    tech_items = sections.get("technical_requirements", [])
    if doc_type == "sow":
        tasks = (scope_items + tech_items)[:20]
        if tasks:
            data["tasks"] = tasks
        if sections.get("deliverables"):
            data["deliverables"] = sections["deliverables"][:15]
        if sections.get("security"):
            data["security_requirements"] = "; ".join(sections["security"])[:600]
        if sections.get("environment_tiers"):
            data["place_of_performance"] = "; ".join(sections["environment_tiers"])[:300]
        if scope_items:
            data["scope"] = " ".join(scope_items)[:500]

    # Common budget/timeline extraction
    m_money = re.search(r"\$[0-9][0-9,]*(?:\.[0-9]+)?", prompt)
    if m_money:
        money = m_money.group(0)
        data.setdefault("estimated_cost", money)
        data.setdefault("estimated_value", money)
        data.setdefault("total_estimate", money)

    m_period = re.search(r"\b\d+\s*(?:month|months|year|years)\b(?:[^.,;\n]{0,40})", prompt, flags=re.IGNORECASE)
    if m_period:
        period = m_period.group(0).strip()
        data.setdefault("period_of_performance", period)
        data.setdefault("timeline", period)

    return data


def fast_path_title(prompt: str, doc_type: str) -> str:
    """Generate a descriptive title from the user prompt and doc type."""
    base = DOC_TYPE_LABELS.get(doc_type, doc_type.replace("_", " ").title())
    if not prompt:
        return base

    lowered = prompt.lower()
    for marker in ("for ", "regarding ", "about "):
        idx = lowered.find(marker)
        if idx == -1:
            continue
        tail = prompt[idx + len(marker) :].strip()
        for stop in (".", "\n", "?", "!", ";"):
            stop_idx = tail.find(stop)
            if 0 < stop_idx < 80:
                tail = tail[:stop_idx]
                break
        tail = tail.strip().rstrip(",").strip()
        if tail and len(tail) > 3:
            return f"{base} - {tail[:80]}"

    return base


def build_scoped_session_id(
    tenant_id: str,
    user_id: str,
    session_id: str | None,
) -> str:
    """Build a scoped session ID for S3/DynamoDB operations."""
    if session_id and "#" in session_id:
        return session_id
    return f"{tenant_id}#advanced#{user_id}#{session_id or ''}"
