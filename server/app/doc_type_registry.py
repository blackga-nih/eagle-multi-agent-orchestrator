"""Doc Type Registry — Single source of truth for document type normalization.

Loads all recognized categories from the template metadata index and provides
normalization, alias resolution, and validation for doc_type values used
throughout the EAGLE system.

Canonical format: lowercase with underscores (e.g., "acquisition_plan").
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
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


def _load_categories_from_index() -> frozenset[str]:
    """Load category names from the template metadata index file."""
    try:
        path = Path(_INDEX_PATH).resolve()
        with open(path, encoding="utf-8") as f:
            index = json.load(f)
        categories = frozenset(index.get("by_category", {}).keys())
        logger.debug("Loaded %d categories from template index", len(categories))
        return categories
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
        logger.warning("Could not load template index: %s — using fallback", e)
        return _FALLBACK_DOC_TYPES


# Fallback if _index.json is unavailable (e.g., during testing)
_FALLBACK_DOC_TYPES = frozenset({
    "sow", "igce", "acquisition_plan", "justification", "market_research",
    "son_products", "son_services", "conference_request", "conference_waiver",
    "promotional_item", "exemption_determination", "mandatory_use_waiver",
    "buy_american", "gfp_form", "subk_plan", "reference_guide",
    "bpa_call_order", "cor_certification", "technical_questionnaire",
    "quotation_abstract", "receiving_report", "srb_request", "subk_review",
    # Markdown-only doc types (used by agentic service, not in S3 templates)
    "eval_criteria", "security_checklist", "section_508",
    "contract_type_justification",
})

# All recognized doc types (loaded from index + markdown-only extras)
_MARKDOWN_ONLY_TYPES = frozenset({
    "eval_criteria", "security_checklist", "section_508",
    "contract_type_justification",
})

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
    "pws": "sow",
    "performance_work_statement": "sow",
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
