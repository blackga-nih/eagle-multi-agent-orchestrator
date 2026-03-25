"""Shared support code for active document generation tools."""

from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime
from typing import Any

from ..db_client import get_s3
from ..session_scope import extract_leaf_session_id, extract_tenant_id, extract_user_id
from ..template_registry import get_template_mapping

logger = logging.getLogger("eagle.document_generation")


def _normalize_context_text(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    marker = "[USER REQUEST]"
    if marker in cleaned:
        tail = cleaned.split(marker, 1)[1].strip()
        if "Instruction:" in tail:
            tail = tail.split("Instruction:", 1)[0].strip()
        if tail:
            cleaned = tail
    return cleaned


def _load_recent_user_context(session_id: str | None = None) -> list[str]:
    leaf_session_id = extract_leaf_session_id(session_id)
    if not leaf_session_id:
        return []

    tenant_id = extract_tenant_id(session_id)
    user_id = extract_user_id(session_id)

    try:
        from ..session_store import get_messages

        messages = get_messages(leaf_session_id, tenant_id, user_id, limit=30)
        context_texts: list[str] = []
        for msg in messages:
            role = msg.get("role", "")
            if role not in ("user", "assistant"):
                continue

            content = msg.get("content", "")
            text = ""
            if isinstance(content, str):
                text = _normalize_context_text(content)
            elif isinstance(content, list):
                text_parts: list[str] = []
                for block in content:
                    if isinstance(block, dict):
                        block_text = block.get("text")
                        if isinstance(block_text, str) and block_text.strip():
                            text_parts.append(block_text.strip())
                if text_parts:
                    text = _normalize_context_text("\n".join(text_parts))

            if text:
                prefix = "" if role == "user" else "[ASSISTANT] "
                context_texts.append(prefix + text)

        return context_texts[-12:]
    except Exception as exc:
        logger.debug("Could not load session context for create_document: %s", exc)
        return []


def _extract_first_money_value(text: str) -> str | None:
    if not text:
        return None

    match = re.search(r"\$[0-9][0-9,]*(?:\.[0-9]+)?", text)
    if match:
        return match.group(0)

    match = re.search(r"\b[0-9][0-9,]*(?:\.[0-9]+)?\s*(?:million|billion|k|m)\b", text, flags=re.IGNORECASE)
    if match:
        return match.group(0)
    return None


def _extract_period(text: str) -> str | None:
    if not text:
        return None
    match = re.search(r"\b\d+\s*(?:month|months|year|years)\b(?:[^.,;\n]{0,40})", text, flags=re.IGNORECASE)
    if match:
        return match.group(0).strip()
    return None


_GENERATION_TRIGGER_RE = re.compile(
    r"^(generate|create|draft|write|produce|prepare|build|make)\s+"
    r"(the|a|an|my|our)?\s*"
    r"(statement of work|sow|igce|ige|cost estimate|market research|"
    r"acquisition plan|justification|document|report)",
    re.IGNORECASE,
)


def _is_generation_trigger(text: str) -> bool:
    t = text.strip()
    if len(t) > 200:
        return False
    return bool(_GENERATION_TRIGGER_RE.search(t))


def _extract_section_bullets(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    aliases = {
        "project description": "project_description",
        "technical requirements": "technical_requirements",
        "scope of work": "scope_of_work",
        "deliverables": "deliverables",
        "environment tiers": "environment_tiers",
        "security": "security",
    }

    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        heading_key = line.rstrip(":").strip().lower()
        if heading_key in aliases:
            current = aliases[heading_key]
            sections.setdefault(current, [])
            continue

        if line.startswith("- ") or line.startswith("* "):
            item = line[2:].strip().strip('"')
            if item:
                sections.setdefault(current or "general", []).append(item)

    return sections


def _augment_document_data_from_context(
    doc_type: str,
    title: str,
    data: dict | None,
    session_id: str | None,
) -> dict:
    merged = dict(data or {})
    context_messages = _load_recent_user_context(session_id)
    if not context_messages:
        return merged

    user_msgs = [m for m in context_messages if not m.startswith("[ASSISTANT] ")]
    assistant_msgs = [m.removeprefix("[ASSISTANT] ") for m in context_messages if m.startswith("[ASSISTANT] ")]
    substantive_user_msgs = [m for m in user_msgs if not _is_generation_trigger(m)]
    last_user_text = (substantive_user_msgs or user_msgs)[-1] if user_msgs else ""
    context_blob = " ".join(context_messages[-8:])

    requirement = (last_user_text or context_blob).strip()
    if requirement:
        requirement = requirement[:500]

    money = _extract_first_money_value(context_blob)
    period = _extract_period(context_blob)

    if requirement:
        merged.setdefault("description", requirement)
        merged.setdefault("requirement", requirement)
        merged.setdefault("objective", requirement)
    if money:
        merged.setdefault("estimated_cost", money)
        merged.setdefault("estimated_value", money)
        merged.setdefault("budget", money)
        merged.setdefault("total_estimate", money)
    if period:
        merged.setdefault("period_of_performance", period)
        merged.setdefault("timeline", period)

    parsed_sections = _extract_section_bullets("\n".join(context_messages[-3:]))
    project_description = " ".join(parsed_sections.get("project_description", [])).strip()
    if project_description:
        existing_desc = str(merged.get("description", "")).strip()
        if not existing_desc or "project description" in existing_desc.lower() or len(existing_desc) > 320:
            merged["description"] = project_description[:500]
        merged.setdefault("requirement", project_description[:500])
        merged.setdefault("objective", project_description[:500])
    if parsed_sections.get("deliverables"):
        merged.setdefault("deliverables", parsed_sections["deliverables"][:15])
    if parsed_sections.get("security"):
        merged.setdefault("security_requirements", "; ".join(parsed_sections["security"])[:600])
    if parsed_sections.get("environment_tiers"):
        merged.setdefault("place_of_performance", "; ".join(parsed_sections["environment_tiers"])[:300])

    if doc_type == "igce":
        merged.setdefault("item_name", title or "Primary acquisition item")
    if doc_type == "market_research":
        merged.setdefault("requirement_summary", requirement or title)
    if doc_type == "sow":
        scope_items = parsed_sections.get("scope_of_work", [])
        tech_items = parsed_sections.get("technical_requirements", [])
        combined_tasks = (scope_items + tech_items)[:20]
        if combined_tasks:
            merged.setdefault("tasks", combined_tasks)
        if scope_items:
            merged.setdefault("scope", "\n".join(f"- {item}" for item in scope_items[:10]))
        elif substantive_user_msgs:
            merged.setdefault("scope", max(substantive_user_msgs[-6:], key=len)[:500])

    if assistant_msgs:
        clean_assistant = [
            msg for msg in assistant_msgs
            if not re.search(
                r"Your task is to create a detailed summary|"
                r"You are an? .{0,30}(?:assistant|agent|specialist)|"
                r"SYSTEM PROMPT|"
                r"<instructions>",
                msg[:200],
                re.IGNORECASE,
            )
        ]
        source = clean_assistant or assistant_msgs
        merged.setdefault("conversation_context", max(source[-4:], key=len)[:3000])

    all_msgs = []
    for message in context_messages:
        if message.startswith("[ASSISTANT] "):
            all_msgs.append({"role": "assistant", "text": message[12:]})
        else:
            all_msgs.append({"role": "user", "text": message})
    if all_msgs:
        merged.setdefault("conversation_history", all_msgs)

    return merged


_DOC_TYPE_ALIASES = {
    "ige": "igce",
    "igce": "igce",
    "independent_government_estimate": "igce",
    "independent_government_cost_estimate": "igce",
    "cost_estimate": "igce",
    "statement_of_work": "sow",
}

_TITLE_DOC_TYPE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(statement\s+of\s+work|sow)\b", re.IGNORECASE), "sow"),
    (re.compile(r"\b(igce|ige|independent\s+government\s+(?:cost\s+)?estimate|cost\s+estimate)\b", re.IGNORECASE), "igce"),
    (re.compile(r"\bmarket\s+research\b", re.IGNORECASE), "market_research"),
    (re.compile(r"\bacquisition\s+plan\b", re.IGNORECASE), "acquisition_plan"),
    (re.compile(r"\b(j\s*(?:&|and)\s*a|justification(?:\s*&\s*approval)?|sole\s+source)\b", re.IGNORECASE), "justification"),
]


def _infer_doc_type_from_title(title: str) -> str | None:
    if not title:
        return None
    for pattern, doc_type in _TITLE_DOC_TYPE_PATTERNS:
        if pattern.search(title):
            return doc_type
    return None


def _normalize_create_document_doc_type(raw_doc_type: Any, title: str) -> str:
    requested = str(raw_doc_type or "").strip().lower().replace("-", "_").replace(" ", "_")
    normalized = _DOC_TYPE_ALIASES.get(requested, requested)
    inferred = _infer_doc_type_from_title(title)

    if normalized == "sow" and inferred == "igce":
        logger.info("Overriding create_document doc_type from sow to igce based on title=%r", title)
        return inferred
    if normalized:
        return normalized
    if inferred:
        return inferred
    return "sow"


def _default_output_format_for_doc_type(doc_type: str) -> str:
    mapping = get_template_mapping(doc_type)
    if mapping:
        return mapping.file_type
    return "md"


def _looks_like_unfilled_template_preview(doc_type: str, preview: str) -> bool:
    if not preview:
        return False
    try:
        from ..template_registry import validate_document_completeness

        report = validate_document_completeness(doc_type, preview)
        if report is not None:
            return report.completeness_pct < 30.0
    except ImportError:
        pass

    if re.search(r"\{\{[A-Z_]{3,}\}\}", preview):
        return True

    markers = {
        "sow": [
            "this section should provide brief description of the project",
            "the background information should identify the requirement in very general terms",
            "sample language",
            "table of contents",
        ],
        "acquisition_plan": [
            "this section should describe the requirement",
            "describe the competition strategy",
            "[tbd]",
            "revised july 2024",
            "far 7.1",
        ],
        "market_research": [
            "[analysis of small business availability",
            "[analysis of whether commercial",
            "this section should describe the market",
            "[insert requirement description",
        ],
        "justification": [
            "[contractor name]",
            "[provide detailed rationale",
            "[describe efforts to compete",
            "[insert authority",
        ],
        "cor_certification": [
            "[nominee name]",
            "[nominee title]",
            "[contract number]",
        ],
    }.get(doc_type, [])
    return sum(1 for marker in markers if marker.lower() in " ".join(preview.lower().split())) >= 2


_SOW_SECTION_HINTS: dict[str, str] = {
    "1": "background and purpose",
    "2": "scope",
    "3": "period of performance",
    "4": "applicable documents and standards",
    "5": "tasks and requirements",
    "6": "deliverables",
    "7": "government-furnished property",
    "8": "quality assurance surveillance plan",
    "9": "place of performance",
    "10": "security requirements",
}


def _extract_sow_clear_targets(edit_request: str) -> list[str]:
    req = (edit_request or "").strip().lower()
    if not req:
        return []
    clear_intent = "clear" in req or "blank" in req or "to be completed" in req or "remove" in req
    if not clear_intent:
        return []

    targets: list[str] = []
    for section_num in re.findall(r"\bsection\s*(\d{1,2})\b", req):
        hint = _SOW_SECTION_HINTS.get(section_num)
        if hint and hint not in targets:
            targets.append(hint)

    for alias in (
        "background and purpose",
        "scope",
        "period of performance",
        "applicable documents and standards",
        "tasks and requirements",
        "deliverables",
        "government-furnished property",
        "quality assurance surveillance plan",
        "place of performance",
        "security requirements",
    ):
        if alias in req and alias not in targets:
            targets.append(alias)

    if "scope" in req and "scope" not in targets:
        targets.append("scope")
    return targets


def _apply_sow_clear_edits(current_content: str, edit_request: str) -> str | None:
    if not isinstance(current_content, str) or not current_content.strip():
        return None

    targets = _extract_sow_clear_targets(edit_request)
    if not targets:
        return None

    heading_matches = list(re.finditer(r"(?m)^##\s+(.+?)\s*$", current_content))
    if not heading_matches:
        return None

    rebuilt: list[str] = []
    cursor = 0
    changed = False

    for idx, heading_match in enumerate(heading_matches):
        heading_end = heading_match.end()
        next_start = heading_matches[idx + 1].start() if idx + 1 < len(heading_matches) else len(current_content)
        heading_text = heading_match.group(1).strip().lower()
        body_text = current_content[heading_end:next_start]
        rebuilt.append(current_content[cursor:heading_end])

        if any(target in heading_text for target in targets):
            if body_text.strip() != "[To be completed]":
                changed = True
            rebuilt.append("\n\n[To be completed]\n\n")
        else:
            rebuilt.append(body_text)
        cursor = next_start

    updated = "".join(rebuilt)
    return updated if changed else None


def _update_document_content(
    tenant_id: str,
    doc_key: str,
    content: str,
    change_source: str = "ai_edit",
    session_id: str | None = None,
) -> dict:
    if not doc_key:
        return {"error": "update_existing_key is required but empty"}
    if not content:
        return {"error": "content is required for update. Provide the full document markdown in the content parameter."}

    user_id = extract_user_id(session_id)
    bucket = os.getenv("S3_BUCKET", "eagle-documents-695681773636-dev")

    if not doc_key.startswith(f"eagle/{tenant_id}/{user_id}/"):
        return {"error": "Access denied: document key must be within user's prefix"}

    if "/packages/" in doc_key:
        from ..document_service import create_package_document_version

        parts = doc_key.split("/")
        try:
            pkg_idx = parts.index("packages")
            package_id = parts[pkg_idx + 1]
            filename = parts[-1]
            doc_type = filename.split("_v")[0] if "_v" in filename else filename.rsplit(".", 1)[0]
            title = doc_type.replace("_", " ").title()
        except (ValueError, IndexError):
            return {"error": "Invalid package document key format"}

        result = create_package_document_version(
            tenant_id=tenant_id,
            package_id=package_id,
            doc_type=doc_type,
            content=content,
            title=title,
            file_type="md",
            created_by_user_id=user_id,
            session_id=session_id,
            change_source=change_source,
        )
        if not result.success:
            return {"error": result.error or "Failed to create document version"}
        return {
            "success": True,
            "mode": "update_package",
            "key": result.s3_key,
            "version": result.version,
            "document_id": result.document_id,
            "message": f"Document updated (version {result.version})",
        }

    try:
        s3 = get_s3()
        s3.put_object(
            Bucket=bucket,
            Key=doc_key,
            Body=content.encode("utf-8"),
            ContentType="text/markdown; charset=utf-8",
        )
        from ..changelog_store import write_document_changelog_entry

        write_document_changelog_entry(
            tenant_id=tenant_id,
            document_key=doc_key,
            change_type="update",
            change_source=change_source,
            change_summary="Updated document content",
            actor_user_id=user_id,
            session_id=session_id,
        )
        return {"success": True, "mode": "update_workspace", "key": doc_key, "message": "Document updated"}
    except Exception as exc:
        logger.warning("Failed to update workspace document %s: %s", doc_key, exc)
        return {"error": f"Failed to update document: {exc}"}


def _extract_sow_sections_from_history(history: list[dict], description: str) -> tuple[list[str], list[str]]:
    scope_parts: list[str] = []
    bg_parts: list[str] = []
    user_texts: list[str] = []
    assistant_texts: list[str] = []

    for msg in history:
        text = msg.get("text", "").strip()
        if not text:
            continue
        if msg["role"] == "user":
            if not _is_generation_trigger(text):
                user_texts.append(text)
        else:
            assistant_texts.append(text)

    if not user_texts and not assistant_texts:
        return scope_parts, bg_parts

    combined_reqs = " ".join(user_texts[-6:])[:2000]
    if combined_reqs:
        scope_parts.extend(
            [
                "The contractor shall provide all personnel, equipment, supplies, facilities, transportation, tools, materials, supervision, and other items and non-personal services necessary to "
                f"{description}, as defined in this SOW.",
                "",
                "Specifically, the contractor shall address the following requirements identified during the acquisition intake:",
                "",
            ]
        )
        for user_text in user_texts[-6:]:
            if len(user_text) >= 30:
                scope_parts.append(f"- {user_text[:300].rstrip('.')}")

    if assistant_texts:
        paragraphs = [part.strip() for part in max(assistant_texts[-4:], key=len).split("\n\n") if len(part.strip()) > 50]
        if paragraphs:
            bg_parts.append(paragraphs[0][:500])
    return scope_parts, bg_parts


def _generate_sow(title: str, data: dict) -> str:
    desc = data.get("description", "the required supplies/services")
    pop = data.get("period_of_performance", "12 months from date of award")
    conv_ctx = data.get("conversation_context", "")
    deliverables = data.get(
        "deliverables",
        [
            "Project Management Plan — within 30 days of award",
            "Monthly Status Reports — NLT 5th business day of each month",
            "Final Delivery/Acceptance Report — within 30 days of contract completion",
        ],
    )
    tasks = data.get(
        "tasks",
        [
            "Planning and Requirements Analysis",
            "Implementation and Delivery",
            "Testing and Quality Assurance",
            "Training and Knowledge Transfer",
            "Ongoing Support and Maintenance",
        ],
    )

    conv_history = data.get("conversation_history", [])
    scope_override = str(data.get("scope", "") or "").strip()
    background_extra = ""
    if conv_history and not scope_override:
        scope_parts, bg_parts = _extract_sow_sections_from_history(conv_history, desc)
        if scope_parts:
            scope_override = "\n".join(scope_parts)
        if bg_parts:
            background_extra = "\n\n" + "\n".join(bg_parts)

    if scope_override:
        scope_text = scope_override
    else:
        scope_text = (
            "The contractor shall provide all personnel, equipment, supplies/services, facilities,\n"
            "transportation, tools, materials, supervision, and other items and non-personal\n"
            f"services necessary to {desc}, as defined in this SOW."
        )

    security_req = data.get("security_requirements", "")
    place = data.get("place_of_performance", "")
    deliverables_text = "\n".join(f"   {idx+1}. {item}" for idx, item in enumerate(deliverables))
    tasks_text = "\n".join(f"   5.{idx+1} Task {idx+1}: {item}" for idx, item in enumerate(tasks))
    context_section = ""
    if conv_ctx:
        context_section = f"""

## APPENDIX A: ACQUISITION CONTEXT

The following context was captured during the intake and analysis phase
and should be incorporated into the final document:

{conv_ctx[:2500]}
"""

    security_section = security_req if security_req else "[To be determined based on data sensitivity and access requirements]"
    place_section = place if place else "National Cancer Institute\nNational Institutes of Health\nBethesda, MD 20892\n\n[Or as otherwise specified in the contract]"

    return f"""# STATEMENT OF WORK (SOW)
## {title}
### National Cancer Institute (NCI)

**Document Status:** DRAFT — Generated {time.strftime('%Y-%m-%d %H:%M UTC')}

---

## 1. BACKGROUND AND PURPOSE

The National Cancer Institute (NCI), part of the National Institutes of Health (NIH),
requires {desc}. This Statement of Work (SOW) describes the tasks, deliverables,
and performance requirements for this acquisition.{background_extra}

## 2. SCOPE

{scope_text}

## 3. PERIOD OF PERFORMANCE

{pop}

## 4. APPLICABLE DOCUMENTS AND STANDARDS

- Federal Acquisition Regulation (FAR)
- Health and Human Services Acquisition Regulation (HHSAR)
- FAR 52.212-4 Contract Terms and Conditions — Commercial Products/Services
- Section 508 Accessibility Standards (if applicable)
- ISO 13485 Quality Management for Medical Devices (if applicable)
- NIH Information Security Standards

## 5. TASKS AND REQUIREMENTS

{tasks_text}

## 6. DELIVERABLES

{deliverables_text}

## 7. GOVERNMENT-FURNISHED PROPERTY (GFP)

[To be determined based on final requirements]

## 8. QUALITY ASSURANCE SURVEILLANCE PLAN (QASP)

The Government will evaluate contractor performance using a Quality Assurance
Surveillance Plan (QASP). Performance standards and acceptable quality levels
will be defined for each major task area.

## 9. PLACE OF PERFORMANCE

{place_section}

## 10. SECURITY REQUIREMENTS

{security_section}
{context_section}
---
*This document was generated by EAGLE — NCI Acquisition Assistant*
"""


def _generate_igce(title: str, data: dict) -> str:
    line_items = data.get("line_items", [])
    overhead_rate = data.get("overhead_rate", 12)
    contingency_rate = data.get("contingency_rate", 10)
    rows = []
    subtotal = 0
    for item in line_items:
        desc = item.get("description", "Item")
        qty = item.get("quantity", 1)
        unit = item.get("unit_price", 0)
        total = qty * unit
        subtotal += total
        rows.append(f"| {desc} | {qty} | ${unit:,.2f} | ${total:,.2f} |")
    overhead = subtotal * (overhead_rate / 100)
    contingency = subtotal * (contingency_rate / 100)
    grand_total = subtotal + overhead + contingency
    items_table = "\n".join(rows) if rows else "| [No line items provided] | - | - | - |"
    return f"""# INDEPENDENT GOVERNMENT COST ESTIMATE (IGCE)
## {title}
### National Cancer Institute (NCI)

**Prepared:** {time.strftime('%Y-%m-%d')}
**Document Status:** DRAFT — For Budget Planning Purposes

---

## 1. PURPOSE

This Independent Government Cost Estimate (IGCE) provides a detailed estimate
of the anticipated costs for: {title}.

## 2. METHODOLOGY

This estimate is based on:
- GSA Schedule pricing and published rates
- Historical contract award data from FPDS
- Market research and vendor quotations
- Bureau of Labor Statistics data

## 3. COST BREAKDOWN

| Description | Qty | Unit Price | Total |
|---|---|---|---|
{items_table}

**Subtotal:** ${subtotal:,.2f}

**Overhead ({overhead_rate}%):** ${overhead:,.2f}

**Contingency ({contingency_rate}%):** ${contingency:,.2f}

---

### **TOTAL ESTIMATED COST: ${grand_total:,.2f}**

---

## 4. ASSUMPTIONS AND LIMITATIONS

- Estimates based on current market conditions
- Prices subject to change based on competition
- Contingency included for unforeseen requirements
- Does not include Government-furnished equipment costs

## 5. CONFIDENCE LEVEL

**Medium** — Recommend validating with current market data and vendor quotes.

---
*This document was generated by EAGLE — NCI Acquisition Assistant*
"""


def _generate_market_research(title: str, data: dict) -> str:
    description = data.get("description", title)
    naics = data.get("naics_code", "TBD")
    vendors = data.get("vendors", [])
    vendor_text = ""
    if vendors:
        for vendor in vendors:
            vendor_text += f"- **{vendor.get('name', 'TBD')}** — {vendor.get('size', 'TBD')}, Contract vehicles: {', '.join(vendor.get('vehicles', ['TBD']))}\n"
    else:
        vendor_text = "- **WARNING: No vendor data provided. Web research was not performed before document generation. This document requires revision with actual market data.**\n"
    return f"""# MARKET RESEARCH REPORT
## {title}
### National Cancer Institute (NCI)

**Date:** {time.strftime('%Y-%m-%d')}
**NAICS Code:** {naics}
**Document Status:** DRAFT

---

## 1. DESCRIPTION OF NEED

{description}

## 2. SOURCES CONSULTED

- SAM.gov (System for Award Management)
- GSA Advantage / GSA eLibrary
- FPDS.gov (Federal Procurement Data System)
- Industry publications and conferences
- Previous NIH/NCI contract history
- Sources Sought notice responses

## 3. POTENTIAL SOURCES

{vendor_text}

## 4. SMALL BUSINESS ANALYSIS

**WARNING: Small business analysis not performed. Run web_search for SAM.gov data.**

## 5. COMMERCIAL AVAILABILITY

**WARNING: Commercial availability not analyzed. Requires web research.**

## 6. RECOMMENDED ACQUISITION STRATEGY

**WARNING: No acquisition strategy data. Complete market research before finalizing.**

## 7. RECOMMENDED CONTRACT VEHICLE

- [ ] GSA Multiple Award Schedule (MAS)
- [ ] NIH NITAAC CIO-SP3
- [ ] Full and Open Competition (FAR Part 15)
- [ ] Small Business Set-Aside (FAR Part 19)

---
*This document was generated by EAGLE — NCI Acquisition Assistant*
"""


def _generate_justification(title: str, data: dict) -> str:
    authority = data.get("authority", "FAR 6.302-1 — Only One Responsible Source")
    contractor = data.get("contractor", "[Contractor Name]")
    value = data.get("estimated_value", "[Estimated Value]")
    rationale = data.get("rationale", "[Provide detailed rationale for sole source]")
    return f"""# JUSTIFICATION AND APPROVAL (J&A)
## Other Than Full and Open Competition
### {title}
### National Cancer Institute (NCI)

**Date:** {time.strftime('%Y-%m-%d')}
**Estimated Value:** {value}
**Document Status:** DRAFT

---

## 1. CONTRACTING ACTIVITY

National Cancer Institute (NCI)
National Institutes of Health (NIH)
Bethesda, MD 20892

## 2. DESCRIPTION OF ACTION

Sole source award to {contractor} for {title}.

## 3. DESCRIPTION OF SUPPLIES/SERVICES

[Detailed description of requirements]

## 4. AUTHORITY CITED

{authority}

## 5. REASON FOR AUTHORITY

{rationale}

## 6. EFFORTS TO OBTAIN COMPETITION

[Description of market research and efforts to identify competitive sources]

## 7. DETERMINATION BY THE CONTRACTING OFFICER

The Contracting Officer has determined that the anticipated cost to the
Government will be fair and reasonable based on:
- Market research
- Price analysis
- Historical pricing data

## 8. ACTIONS TO REMOVE BARRIERS TO COMPETITION

[Actions planned for future competitive acquisitions]

## 9. APPROVAL

| Role | Name | Signature | Date |
|---|---|---|---|
| Contracting Officer | | | |
| Competition Advocate | | | |
| [Additional approvals as required by FAR 6.304] | | | |

---
*This document was generated by EAGLE — NCI Acquisition Assistant*
"""


def _generate_acquisition_plan(title: str, data: dict) -> str:
    desc = data.get("description", "the required supplies/services")
    value = data.get("estimated_value", "[TBD]")
    pop = data.get("period_of_performance", "12 months from date of award")
    competition = data.get("competition", "Full and Open Competition")
    contract_type = data.get("contract_type", "Firm-Fixed-Price")
    set_aside = data.get("set_aside", "To be determined based on market research")
    funding_by_fy = data.get("funding_by_fy", [])
    funding_table = ""
    if funding_by_fy:
        for entry in funding_by_fy:
            funding_table += f"| {entry.get('fiscal_year', 'FY20XX')} | {entry.get('amount', '$0')} |\n"
    else:
        funding_table = "| FY2026 | [TBD] |\n| FY2027 | [TBD] |\n"
    return f"""# ACQUISITION PLAN (AP) — Streamlined Format
## {title}
### National Cancer Institute (NCI)

**Date:** {time.strftime('%Y-%m-%d')}
**Estimated Value:** {value}
**Document Status:** DRAFT

---

## SECTION 1: ACQUISITION BACKGROUND AND OBJECTIVES

### 1.1 Statement of Need

{desc}

### 1.2 Applicable Conditions

- **Period of Performance:** {pop}
- **Estimated Total Value:** {value}
- **Funding by Fiscal Year:**

| Fiscal Year | Amount |
|-------------|--------|
{funding_table}

### 1.3 Cost

The estimated cost is based on independent government cost estimates,
market research, and historical pricing data for similar acquisitions.

### 1.4 Capability and Performance

The contractor must demonstrate capability to deliver the required
services/supplies in accordance with the Statement of Work.

### 1.5 Delivery and Schedule

Delivery schedule will be defined in the SOW. Key milestones are
tied to the period of performance: {pop}.

## SECTION 2: PLAN OF ACTION

### 2.1 Competitive Requirements

**Competition Strategy:** {competition}

### 2.2 Source Selection

Evaluation factors will be established in accordance with FAR Part 15.
Best value tradeoff or lowest price technically acceptable as appropriate.

### 2.3 Acquisition Considerations

- **Contract Type:** {contract_type}
- **Set-Aside:** {set_aside}
- **Applicable FAR/HHSAR Clauses:** To be determined

## SECTION 3: MILESTONES

| Milestone | Target Date |
|-----------|-------------|
| Acquisition Plan Approval | [TBD] |
| Solicitation Issue | [TBD] |
| Proposals Due | [TBD] |
| Evaluation Complete | [TBD] |
| Award | [TBD] |

## SECTION 4: APPROVALS

| Role | Name | Signature | Date |
|------|------|-----------|------|
| Program/Project Officer | | __________ | |
| Contracting Officer | | __________ | |
| Competition Advocate | | __________ | |

---
*This document was generated by EAGLE — NCI Acquisition Assistant*
"""


def _generate_eval_criteria(title: str, data: dict) -> str:
    factors = data.get(
        "factors",
        [
            {"name": "Technical Approach", "weight": "Most Important"},
            {"name": "Past Performance", "weight": "Important"},
            {"name": "Price", "weight": "Least Important"},
        ],
    )
    method = data.get("evaluation_method", "Best Value Tradeoff")
    rating_scale = data.get(
        "rating_scale",
        [
            ("Outstanding", "Exceeds requirements; very high probability of success"),
            ("Good", "Meets requirements; high probability of success"),
            ("Acceptable", "Meets minimum requirements; reasonable probability of success"),
            ("Marginal", "Does not clearly meet some requirements; low probability of success"),
            ("Unacceptable", "Fails to meet minimum requirements; no probability of success"),
        ],
    )
    factors_text = ""
    for idx, factor in enumerate(factors, 1):
        name = factor if isinstance(factor, str) else factor.get("name", f"Factor {idx}")
        weight = "" if isinstance(factor, str) else f" ({factor.get('weight', '')})"
        factors_text += f"### Factor {idx}: {name}{weight}\n\n[Detailed description of evaluation criteria]\n\n"
    scale_text = "".join(f"| {rating} | {desc} |\n" for rating, desc in rating_scale)
    return f"""# EVALUATION CRITERIA
## {title}
### National Cancer Institute (NCI)

**Date:** {time.strftime('%Y-%m-%d')}
**Evaluation Method:** {method}
**Document Status:** DRAFT

---

## 1. EVALUATION FACTORS

Evaluation factors are listed in descending order of importance.

{factors_text}

## 2. RATING SCALE

| Rating | Description |
|--------|-------------|
{scale_text}

## 3. EVALUATION PROCESS

- Technical proposals will be evaluated by a Technical Evaluation Panel (TEP)
- Past performance will be assessed using CPARS and references
- Price will be evaluated for reasonableness and realism
- Evaluation will follow FAR 15.305 procedures

## 4. BASIS FOR AWARD

Award will be made to the offeror whose proposal represents the
best value to the Government, considering technical merit and price.

---
*This document was generated by EAGLE — NCI Acquisition Assistant*
"""


def _generate_security_checklist(title: str, data: dict) -> str:
    it_systems = data.get("it_systems_involved", "[TBD]")
    impact_level = data.get("impact_level", "Moderate")
    cloud_services = data.get("cloud_services", False)
    return f"""# IT SECURITY CHECKLIST
## {title}
### National Cancer Institute (NCI)

**Date:** {time.strftime('%Y-%m-%d')}
**Document Status:** DRAFT

---

## 1. SECURITY ASSESSMENT QUESTIONS

| # | Question | Yes | No | N/A |
|---|----------|-----|----|-----|
| 1 | Will contractor access IT systems or networks? | | | |
| 2 | Will contractor access the NIH network? | | | |
| 3 | Will contractor handle Personally Identifiable Information (PII)? | | | |
| 4 | Is FISMA compliance required? | | | |
| 5 | Are security clearances required? | | | |
| 6 | Will data leave NIH facilities or networks? | | | |
| 7 | Are cloud services involved? | {'[x]' if cloud_services else '[ ]'} | {'[ ]' if cloud_services else '[x]'} | |
| 8 | Is FedRAMP authorization required? | | | |
| 9 | Will contractor develop or modify software? | | | |
| 10 | Are there data encryption requirements? | | | |

## 2. IMPACT LEVEL DETERMINATION

**Selected Impact Level:** {impact_level}

| Level | Description |
|-------|-------------|
| Low | Limited adverse effect on operations |
| Moderate | Serious adverse effect on operations |
| High | Severe or catastrophic adverse effect |

## 3. REQUIRED FAR/HHSAR CLAUSES

- [ ] FAR 52.239-1 — Privacy or Security Safeguards
- [ ] HHSAR 352.239-73 — Electronic Information and Technology Accessibility
- [ ] FAR 52.204-21 — Basic Safeguarding of Covered Contractor Information Systems
- [ ] NIST SP 800-171 — Protecting Controlled Unclassified Information (if applicable)

## 4. IT SYSTEMS INVOLVED

{it_systems}

## 5. ISSM/ISSO REVIEW

| Role | Name | Signature | Date |
|------|------|-----------|------|
| ISSM | | __________ | |
| ISSO | | __________ | |
| COR | | __________ | |

---
*This document was generated by EAGLE — NCI Acquisition Assistant*
"""


def _generate_section_508(title: str, data: dict) -> str:
    product_types = data.get("product_types", [])
    exception_claimed = data.get("exception_claimed", False)
    vpat_status = data.get("vpat_status", "Not yet reviewed")
    all_types = [
        "Software Applications",
        "Web-based Information",
        "Telecommunications Products",
        "Video and Multimedia",
        "Self-Contained Products",
        "Desktop and Portable Computers",
        "Electronic Documents",
    ]
    product_checklist = "".join(f"- {'[x]' if product_type in product_types else '[ ]'} {product_type}\n" for product_type in all_types)
    return f"""# SECTION 508 COMPLIANCE STATEMENT
## {title}
### National Cancer Institute (NCI)

**Date:** {time.strftime('%Y-%m-%d')}
**Document Status:** DRAFT

---

## 1. APPLICABILITY DETERMINATION

Does this acquisition include Electronic and Information Technology (EIT)?

- [ ] Yes — Section 508 applies
- [ ] No — Section 508 does not apply (provide justification below)

## 2. PRODUCT TYPE CHECKLIST

{product_checklist}

## 3. EXCEPTION DETERMINATION

**Exception Claimed:** {'Yes' if exception_claimed else 'No'}

| Exception Type | Applicable |
|---------------|------------|
| National Security | [ ] |
| Acquired by contractor incidental to contract | [ ] |
| Located in spaces frequented only by service personnel | [ ] |
| Micro-purchase | [ ] |
| Fundamental alteration | [ ] |
| Undue burden | [ ] |

## 4. VPAT/ACR STATUS

**Status:** {vpat_status}

- [ ] Vendor has provided VPAT/Accessibility Conformance Report
- [ ] VPAT reviewed and acceptable
- [ ] Remediation plan required
- [ ] Not applicable

## 5. CONTRACT LANGUAGE

Include FAR 39.2 and Section 508 requirements in:
- [ ] Statement of Work
- [ ] Evaluation Criteria
- [ ] Contract Clauses

---
*This document was generated by EAGLE — NCI Acquisition Assistant*
"""


def _generate_cor_certification(title: str, data: dict) -> str:
    nominee_name = data.get("nominee_name", "[Nominee Name]")
    nominee_title = data.get("nominee_title", "[Title]")
    nominee_org = data.get("nominee_org", "National Cancer Institute")
    nominee_phone = data.get("nominee_phone", "[Phone]")
    nominee_email = data.get("nominee_email", "[Email]")
    fac_cor_level = data.get("fac_cor_level", "II")
    contract_number = data.get("contract_number", "[TBD]")
    return f"""# CONTRACTING OFFICER'S REPRESENTATIVE (COR) CERTIFICATION
## {title}
### National Cancer Institute (NCI)

**Date:** {time.strftime('%Y-%m-%d')}
**Contract Number:** {contract_number}
**Document Status:** DRAFT

---

## 1. COR NOMINEE INFORMATION

| Field | Value |
|-------|-------|
| Name | {nominee_name} |
| Title | {nominee_title} |
| Organization | {nominee_org} |
| Phone | {nominee_phone} |
| Email | {nominee_email} |
| FAC-COR Level | Level {fac_cor_level} |

## 2. FAC-COR CERTIFICATION

| Level | Requirements | Applicable |
|-------|-------------|------------|
| I | 8 hours CLC training, low-risk contracts | {'[x]' if fac_cor_level == 'I' else '[ ]'} |
| II | 40 hours CLC training, moderate-risk contracts | {'[x]' if fac_cor_level == 'II' else '[ ]'} |
| III | 60 hours CLC training, high-risk contracts | {'[x]' if fac_cor_level == 'III' else '[ ]'} |

## 3. DELEGATED DUTIES

The COR is authorized to perform the following duties:

- [x] Provide technical direction (within scope of contract)
- [x] Review and approve invoices for payment
- [x] Accept or reject deliverables
- [x] Monitor contractor performance
- [x] Maintain COR files and documentation
- [x] Report issues to the Contracting Officer

## 4. LIMITATIONS

The COR may NOT:

- Direct changes to the scope of work
- Authorize additional costs or funding
- Extend the period of performance
- Make any contractual commitments or modifications
- Direct the contractor to perform work outside the contract

## 5. SIGNATURES

| Role | Name | Signature | Date |
|------|------|-----------|------|
| COR Nominee | {nominee_name} | __________ | |
| Contracting Officer | | __________ | |
| Supervisor | | __________ | |

---
*This document was generated by EAGLE — NCI Acquisition Assistant*
"""


def _generate_contract_type_justification(title: str, data: dict) -> str:
    contract_type = data.get("contract_type", "Firm-Fixed-Price")
    rationale = data.get("rationale", "[Provide rationale for selected contract type]")
    risk_to_govt = data.get("risk_to_government", "Low")
    risk_to_contractor = data.get("risk_to_contractor", "Moderate")
    value = data.get("estimated_value", "[TBD]")
    return f"""# CONTRACT TYPE JUSTIFICATION
## Determination and Findings (D&F)
### {title}
### National Cancer Institute (NCI)

**Date:** {time.strftime('%Y-%m-%d')}
**Estimated Value:** {value}
**Recommended Contract Type:** {contract_type}
**Document Status:** DRAFT

---

## 1. FINDINGS

### 1.1 Description of Acquisition

{title}

### 1.2 Contract Type Analysis

| Contract Type | Risk to Govt | Risk to Contractor | Recommended |
|--------------|-------------|-------------------|-------------|
| Firm-Fixed-Price (FFP) | Low | High | {'[x]' if 'fixed' in contract_type.lower() else '[ ]'} |
| Time & Materials (T&M) | High | Low | {'[x]' if 't&m' in contract_type.lower() or 'time' in contract_type.lower() else '[ ]'} |
| Cost-Reimbursement (CR) | High | Low | {'[x]' if 'cost' in contract_type.lower() else '[ ]'} |
| Labor-Hour (LH) | Moderate | Moderate | {'[x]' if 'labor' in contract_type.lower() else '[ ]'} |

### 1.3 Rationale for Contract Type Selection

{rationale}

### 1.4 Risk Assessment

- **Risk to Government:** {risk_to_govt}
- **Risk to Contractor:** {risk_to_contractor}

### 1.5 Requirements Definition

The selected contract type is appropriate based on the degree to which
the requirement can be clearly defined and performance risk allocated.

---
*This document was generated by EAGLE — NCI Acquisition Assistant*
"""
