"""Utilities for ranking and extracting package attachment context."""

from __future__ import annotations

import re
from typing import Any, Optional

from .package_attachment_store import list_package_attachments


_DOC_TYPE_CATEGORY_PREFERENCES: dict[str, list[str]] = {
    "sow": ["requirements_evidence", "technical_evidence", "prior_artifact"],
    "igce": ["pricing_evidence", "prior_artifact", "requirements_evidence"],
    "market_research": [
        "market_research_evidence",
        "prior_artifact",
        "requirements_evidence",
    ],
    "acquisition_plan": [
        "requirements_evidence",
        "approval_evidence",
        "prior_artifact",
    ],
    "justification": ["approval_evidence", "prior_artifact", "requirements_evidence"],
}

_DOC_TYPE_RELATED_HINTS: dict[str, set[str]] = {
    "sow": {"son_products", "son_services", "technical_questionnaire", "sow"},
    "igce": {"igce"},
    "market_research": {"market_research"},
    "acquisition_plan": {"acquisition_plan", "justification"},
    "justification": {"justification", "acquisition_plan"},
}


def _clean_excerpt(text: str, max_chars: int) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "")).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3].rstrip() + "..."


def score_attachment_for_doc_type(
    attachment: dict[str, Any],
    target_doc_type: Optional[str],
) -> int:
    """Score a package attachment for a requested output document type."""
    score = 0
    usage = attachment.get("usage") or "reference"
    category = attachment.get("category") or "other"
    attachment_doc_type = (attachment.get("doc_type") or "").strip().lower()
    linked_doc_type = (attachment.get("linked_doc_type") or "").strip().lower()
    title = f"{attachment.get('title', '')} {attachment.get('filename', '')}".lower()

    if usage == "official_document":
        score += 80
    elif usage == "official_candidate":
        score += 60
    elif usage == "checklist_support":
        score += 50
    else:
        score += 40

    if attachment.get("extracted_text"):
        score += 10
    elif attachment.get("attachment_type") in {"image", "screenshot"}:
        score -= 10

    if not target_doc_type:
        return score

    if attachment_doc_type == target_doc_type:
        score += 100
    elif attachment_doc_type in _DOC_TYPE_RELATED_HINTS.get(target_doc_type, set()):
        score += 55

    if linked_doc_type == target_doc_type:
        score += 120
    elif linked_doc_type in _DOC_TYPE_RELATED_HINTS.get(target_doc_type, set()):
        score += 65

    preferences = _DOC_TYPE_CATEGORY_PREFERENCES.get(target_doc_type, [])
    if category in preferences:
        score += 50 - (preferences.index(category) * 10)

    if target_doc_type.replace("_", " ") in title:
        score += 15

    return score


def select_relevant_attachment_context(
    attachments: list[dict[str, Any]],
    target_doc_type: Optional[str],
    limit: int = 3,
    excerpt_chars: int = 500,
) -> list[dict[str, Any]]:
    """Return the highest-signal attachment snippets for a target doc type."""
    ranked = sorted(
        attachments,
        key=lambda item: (
            score_attachment_for_doc_type(item, target_doc_type),
            item.get("updated_at") or item.get("created_at") or "",
        ),
        reverse=True,
    )

    selected: list[dict[str, Any]] = []
    for attachment in ranked[:limit]:
        excerpt = _clean_excerpt(attachment.get("extracted_text") or "", excerpt_chars)
        selected.append(
            {
                "attachment_id": attachment.get("attachment_id"),
                "title": attachment.get("title") or attachment.get("filename") or "attachment",
                "doc_type": attachment.get("doc_type") or "attachment",
                "linked_doc_type": attachment.get("linked_doc_type"),
                "category": attachment.get("category") or "other",
                "usage": attachment.get("usage") or "reference",
                "score": score_attachment_for_doc_type(attachment, target_doc_type),
                "excerpt": excerpt,
            }
        )
    return selected


def load_relevant_package_attachment_context(
    tenant_id: str,
    package_id: str,
    target_doc_type: Optional[str],
    limit: int = 3,
    excerpt_chars: int = 500,
) -> list[dict[str, Any]]:
    attachments = list_package_attachments(tenant_id, package_id, limit=50)
    return select_relevant_attachment_context(
        attachments,
        target_doc_type=target_doc_type,
        limit=limit,
        excerpt_chars=excerpt_chars,
    )


def enrich_generation_data_from_attachments(
    tenant_id: str,
    package_id: str,
    target_doc_type: Optional[str],
    data: Optional[dict[str, Any]] = None,
    limit: int = 3,
) -> dict[str, Any]:
    """Attach ranked source-material context to generation data."""
    merged = dict(data or {})
    selected = load_relevant_package_attachment_context(
        tenant_id,
        package_id,
        target_doc_type,
        limit=limit,
        excerpt_chars=900,
    )
    if not selected:
        return merged

    merged.setdefault("source_attachments", selected)
    merged.setdefault(
        "source_material_summary",
        "\n\n".join(
            f"{item['title']} [{item['category']}, {item['usage']}]\n{item['excerpt']}"
            for item in selected
            if item.get("excerpt")
        )[:3000],
    )

    first_excerpt = next((item.get("excerpt") for item in selected if item.get("excerpt")), "")
    if first_excerpt:
        merged.setdefault("description", first_excerpt[:500])
        merged.setdefault("requirement", first_excerpt[:500])
        merged.setdefault("objective", first_excerpt[:500])
        if target_doc_type == "sow":
            merged.setdefault("scope", first_excerpt[:700])

    return merged
