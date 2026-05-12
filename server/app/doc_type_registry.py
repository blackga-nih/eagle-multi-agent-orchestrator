"""Doc Type Registry — Single source of truth for document type normalization.

Loads all recognized categories from the template metadata index and provides
normalization, alias resolution, and validation for doc_type values used
throughout the EAGLE system.

Canonical format: lowercase with underscores (e.g., "acquisition_plan").

Per-category metadata
---------------------
Beyond the bare slug set, the registry also exposes per-category metadata
(label, kind, aliases, compliance display names, system-prompt key) loaded
from the same _index.json under the ``category_metadata`` block. Consumers
that need richer metadata than ALL_DOC_TYPES use the ``get_label`` /
``get_kind`` / ``get_category_metadata`` accessors. The metadata block is
optional — modules that don't need it keep working with the existing
ALL_DOC_TYPES / normalize_doc_type / is_valid_doc_type API unchanged.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("eagle.doc_type_registry")

# ── Load categories from template metadata index ──────────────────────

_INDEX_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "..",
    "eagle-plugin",
    "data",
    "template-metadata",
    "_index.json",
)


def _load_index() -> dict[str, Any]:
    """Load and return the raw _index.json. Returns {} on failure."""
    try:
        path = Path(_INDEX_PATH).resolve()
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
        logger.warning("Could not load template index: %s", e)
        return {}


def _load_categories_from_index() -> frozenset[str]:
    """Load category names from the template metadata index file."""
    index = _load_index()
    if not index:
        return _FALLBACK_DOC_TYPES
    categories = frozenset(index.get("by_category", {}).keys())
    logger.debug("Loaded %d categories from template index", len(categories))
    return categories


# Fallback if _index.json is unavailable (e.g., during testing)
_FALLBACK_DOC_TYPES = frozenset(
    {
        "sow",
        "igce",
        "acquisition_plan",
        "justification",
        "market_research",
        "son_products",
        "son_services",
        "conference_request",
        "conference_waiver",
        "promotional_item",
        "exemption_determination",
        "mandatory_use_waiver",
        "buy_american",
        "gfp_form",
        "subk_plan",
        "reference_guide",
        "bpa_call_order",
        "cor_certification",
        "technical_questionnaire",
        "quotation_abstract",
        "receiving_report",
        "srb_request",
        "subk_review",
        # Markdown-only doc types (used by agentic service, not in S3 templates)
        "eval_criteria",
        "security_checklist",
        "section_508",
        "contract_type_justification",
    }
)

# All recognized doc types (loaded from index + markdown-only extras)
_MARKDOWN_ONLY_TYPES = frozenset(
    {
        "eval_criteria",
        "security_checklist",
        "section_508",
        "contract_type_justification",
        # PWS is a distinct canonical doc_type (performance-based counterpart
        # to SOW). It reuses the SOW docx template via template_registry.py
        # short-term, so the template metadata _index.json does not list it
        # separately — we add it here so normalization + validation succeed.
        "pws",
        # Simplified-acquisition / purchase-card flow doc types. The metadata
        # index may not list these yet, so keep them valid for create_document;
        # template_registry.py decides whether a given type uses S3 or markdown.
        "purchase_request",
        "price_reasonableness",
        "required_sources",
    }
)

ALL_DOC_TYPES: frozenset[str] = _load_categories_from_index() | _MARKDOWN_ONLY_TYPES


# ── Alias map ─────────────────────────────────────────────────────────

_DOC_TYPE_ALIASES: dict[str, str] = {
    # IGCE aliases
    "ige": "igce",
    "independent_government_estimate": "igce",
    "independent_government_cost_estimate": "igce",
    "cost_estimate": "igce",
    # SOW aliases
    "statement_of_work": "sow",
    # PWS is a DISTINCT doc_type from SOW (performance-based vs task-based).
    # See ai_document_schema.py DOC_TYPE_ALIASES for the authoritative note.
    "performance_work_statement": "pws",
    # Acquisition plan aliases
    "ap": "acquisition_plan",
    "acq_plan": "acquisition_plan",
    # Justification aliases
    "j_a": "justification",
    "j&a": "justification",
    "ja": "justification",
    "sole_source": "justification",
    "sole_source_justification": "justification",
    # Market research aliases
    "mr": "market_research",
    "mrr": "market_research",
    # SON aliases
    "son": "son_products",
    "statement_of_need": "son_products",
    "statement_of_need_products": "son_products",
    "statement_of_need_services": "son_services",
    # COR aliases
    "cor": "cor_certification",
    "cor_appointment": "cor_certification",
    # Subcontracting aliases
    "subcontracting_plan": "subk_plan",
    "sub_k_plan": "subk_plan",
    "subcontracting_review": "subk_review",
    "sub_k_review": "subk_review",
    # Buy American aliases
    "baa": "buy_american",
    "buy_american_act": "buy_american",
    # BPA aliases
    "bpa": "bpa_call_order",
    "blanket_purchase_agreement": "bpa_call_order",
    # Conference aliases
    "conference": "conference_request",
    "conf_request": "conference_request",
    "conf_waiver": "conference_waiver",
    # GFP aliases
    "gfp": "gfp_form",
    "government_furnished_property": "gfp_form",
    # SRB aliases
    "srb": "srb_request",
    "source_review_board": "srb_request",
    # Misc aliases
    "receiving": "receiving_report",
    "tech_questionnaire": "technical_questionnaire",
    "quotation": "quotation_abstract",
    "promo_item": "promotional_item",
    "exemption": "exemption_determination",
    "mandatory_waiver": "mandatory_use_waiver",
}


# ── Public API ────────────────────────────────────────────────────────


def normalize_doc_type(raw: str) -> str:
    """Normalize a doc_type string to its canonical underscore form.

    Handles: hyphens, spaces, case, and known aliases.
    Returns the normalized string (may still be invalid if not in ALL_DOC_TYPES).
    """
    if not raw:
        return ""
    cleaned = raw.strip().lower().replace("-", "_").replace(" ", "_")
    return _DOC_TYPE_ALIASES.get(cleaned, cleaned)


def is_valid_doc_type(doc_type: str) -> bool:
    """Check if a doc_type is recognized by the EAGLE system."""
    return normalize_doc_type(doc_type) in ALL_DOC_TYPES


def get_template_categories() -> frozenset[str]:
    """Return the set of doc types that have S3 templates (excludes markdown-only types)."""
    return ALL_DOC_TYPES - _MARKDOWN_ONLY_TYPES


# ── Category metadata (label / kind / compliance) ─────────────────────
#
# Loaded from the `category_metadata` block in _index.json. Optional — if the
# block is missing or a slug isn't in it, accessors return safe defaults
# (label = title-cased slug, kind = "generated", etc.).

_CATEGORY_METADATA: dict[str, dict[str, Any]] = (
    _load_index().get("category_metadata") or {}
)


def _aliases_from_metadata() -> dict[str, str]:
    """Build alias→canonical map from per-category `aliases` lists in _index.json.

    Augments (does not replace) the hardcoded `_DOC_TYPE_ALIASES` dict above —
    in case of collision the hardcoded value wins, since that one is the long-
    standing source of truth and tests assert against it. New aliases in
    `_index.json` are merged in as an additive layer.
    """
    out: dict[str, str] = {}
    for slug, meta in _CATEGORY_METADATA.items():
        for alias in meta.get("aliases", []) or []:
            if alias and alias not in _DOC_TYPE_ALIASES:
                out[alias] = slug
    return out


# Merge plugin-data aliases under the hardcoded ones. Hardcoded wins on collision.
_DOC_TYPE_ALIASES = {**_aliases_from_metadata(), **_DOC_TYPE_ALIASES}


def get_category_metadata(slug: str) -> dict[str, Any]:
    """Return the raw metadata dict for a slug, or {} if not in the metadata block.

    The slug must already be canonical — call normalize_doc_type() first if
    you have a raw user input.
    """
    return _CATEGORY_METADATA.get(slug, {})


def get_label(slug: str) -> str:
    """Display label for a doc-type. Falls back to a title-cased slug if absent."""
    meta = _CATEGORY_METADATA.get(slug, {})
    if "label" in meta:
        return meta["label"]
    return slug.replace("_", " ").title()


def get_kind(slug: str) -> str:
    """Doc-type 'kind' (generated, evidence, form_only, ...). Defaults to 'generated'."""
    return _CATEGORY_METADATA.get(slug, {}).get("kind", "generated")


def get_compliance_display_name(slug: str) -> str | None:
    """Name as it appears in the HHS compliance matrix, or None if not mapped."""
    return _CATEGORY_METADATA.get(slug, {}).get("compliance_display_name")


def get_compliance_aliases(slug: str) -> list[str]:
    """Additional names that historically refer to this slug in compliance maps."""
    return list(_CATEGORY_METADATA.get(slug, {}).get("compliance_aliases") or [])


def get_system_prompt_key(slug: str) -> str | None:
    """Key into the system-prompt store (e.g., 'sow' → 'SOW_PROMPT' constant).

    Returns None if this slug has no associated LLM prompt (form-only doc types,
    evidence attachments, etc.). PR A3 will land the actual prompt store —
    this accessor just exposes the key so future migrations don't churn signatures.
    """
    return _CATEGORY_METADATA.get(slug, {}).get("system_prompt_key")


def get_all_metadata() -> dict[str, dict[str, Any]]:
    """Return a defensive copy of the full per-category metadata block.

    Useful for downstream callers that want to enumerate all doc-types with
    their metadata in one shot rather than calling N accessors.
    """
    return {k: dict(v) for k, v in _CATEGORY_METADATA.items()}
