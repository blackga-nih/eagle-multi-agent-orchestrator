"""Compliance Gap Analysis Service — Cross-references compliance requirements with template coverage.

Given package parameters (value, method, type), determines which compliance requirements
are covered by templates, which have gaps, and which are only partially covered.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger("eagle.compliance_gap_service")

# Maps compliance matrix document names to template categories
_DOC_TO_CATEGORY = {
    "SOW / PWS": "sow",
    "Statement of Need (SON)": "son_products",
    "IGCE": "igce",
    "Market Research Report": "market_research",
    "Market Research": "market_research",
    "Acquisition Plan": "acquisition_plan",
    "J&A / Justification": "justification",
    "D&F (Determination & Findings)": "buy_american",
    "Source Selection Plan": "acquisition_plan",
    "Subcontracting Plan": "subk_plan",
    "QASP": "sow",
    "HHS-653 Small Business Review": "subk_review",
    "Purchase Request": "quotation_abstract",
    "IT Security & Privacy Certification": "sow",
    "Section 508 ICT Evaluation": "sow",
    "Human Subjects Provisions": "sow",
}

# Regex to extract FAR citations from compliance matrix text
_FAR_PATTERN = re.compile(r"FAR\s+(\d+[\.\d\-\(\)a-z]*)", re.IGNORECASE)
_DFARS_PATTERN = re.compile(r"DFARS\s+([\d\.\-]+)", re.IGNORECASE)


def analyze_compliance_gaps(
    contract_value: float,
    acquisition_method: str,
    contract_type: str,
    flags: Optional[dict] = None,
) -> dict:
    """Analyze compliance coverage gaps across templates.

    Args:
        contract_value: Estimated contract value in dollars
        acquisition_method: FAR acquisition method (negotiated, sap, etc.)
        contract_type: Contract type (ffp, cpff, etc.)
        flags: Optional flags dict (is_it, is_services, is_small_business)

    Returns:
        Dict with covered, gaps, partial lists, and coverage_pct
    """
    from app.compliance_matrix import get_requirements

    # Get compliance requirements
    result = get_requirements(contract_value, acquisition_method, contract_type, flags)

    documents_required = result.get("documents_required", [])
    compliance_items = result.get("compliance_items", [])

    # Load all clause references
    try:
        from app.template_schema import load_all_clause_references
        all_refs = load_all_clause_references()
    except Exception:
        all_refs = {}

    # Build a set of all clauses covered by templates, keyed by clause number
    template_clause_coverage: dict[str, list[str]] = {}  # clause_number -> [template_filenames]
    for filename, ref_data in all_refs.items():
        for sec_data in ref_data.get("section_clause_map", {}).values():
            for clause in sec_data.get("clauses", []):
                cn = clause.get("clause_number", "").strip()
                if cn:
                    template_clause_coverage.setdefault(cn, []).append(
                        ref_data.get("template_filename", filename)
                    )
        for clause in ref_data.get("template_level_clauses", []):
            cn = clause.get("clause_number", "").strip()
            if cn:
                template_clause_coverage.setdefault(cn, []).append(
                    ref_data.get("template_filename", filename)
                )

    # Build category coverage set
    category_coverage = set()
    for ref_data in all_refs.values():
        cat = ref_data.get("category", "")
        if cat:
            category_coverage.add(cat)

    covered = []
    gaps = []
    partial = []

    # Analyze document requirements
    for doc_req in documents_required:
        name = doc_req.get("name", "")
        required = doc_req.get("required", False)
        note = doc_req.get("note", "")

        if not required:
            continue

        category = _DOC_TO_CATEGORY.get(name)
        has_template = category and category in category_coverage

        # Extract FAR citations from the note
        cited_clauses = _extract_far_citations(note)

        # Check if cited clauses are covered by templates
        clauses_covered = []
        clauses_missing = []
        for clause in cited_clauses:
            if _find_clause_in_coverage(clause, template_clause_coverage):
                clauses_covered.append(clause)
            else:
                clauses_missing.append(clause)

        entry = {
            "requirement": name,
            "category": category,
            "has_template": has_template,
            "cited_clauses": cited_clauses,
            "clauses_covered": clauses_covered,
            "clauses_missing": clauses_missing,
            "note": note,
        }

        if has_template and not clauses_missing:
            covered.append(entry)
        elif has_template and clauses_missing:
            partial.append(entry)
        else:
            gaps.append(entry)

    # Analyze compliance items
    for item in compliance_items:
        name = item.get("name", "")
        required = item.get("required", False)
        note = item.get("note", "")

        if not required:
            continue

        cited_clauses = _extract_far_citations(note)
        clauses_covered = []
        clauses_missing = []
        for clause in cited_clauses:
            if _find_clause_in_coverage(clause, template_clause_coverage):
                clauses_covered.append(clause)
            else:
                clauses_missing.append(clause)

        entry = {
            "requirement": name,
            "category": "compliance_item",
            "has_template": False,
            "cited_clauses": cited_clauses,
            "clauses_covered": clauses_covered,
            "clauses_missing": clauses_missing,
            "note": note,
        }

        if clauses_covered and not clauses_missing:
            covered.append(entry)
        elif clauses_covered and clauses_missing:
            partial.append(entry)
        elif cited_clauses:
            gaps.append(entry)

    total = len(covered) + len(gaps) + len(partial)
    coverage_pct = round((len(covered) / total) * 100, 1) if total else 100.0

    return {
        "covered": covered,
        "gaps": gaps,
        "partial": partial,
        "coverage_pct": coverage_pct,
        "total_requirements": total,
    }


def _extract_far_citations(text: str) -> list[str]:
    """Extract FAR and DFARS citation numbers from text."""
    citations = []
    for match in _FAR_PATTERN.finditer(text):
        citations.append(f"FAR {match.group(1)}")
    for match in _DFARS_PATTERN.finditer(text):
        citations.append(f"DFARS {match.group(1)}")
    return citations


def _find_clause_in_coverage(
    clause: str,
    coverage: dict[str, list[str]],
) -> bool:
    """Check if a clause is covered, with prefix matching.

    E.g., "FAR 52.219" matches "FAR 52.219-8" and "FAR 52.219-9".
    """
    clause_lower = clause.lower()
    for covered_clause in coverage:
        if covered_clause.lower().startswith(clause_lower) or clause_lower.startswith(covered_clause.lower()):
            return True
    return False
