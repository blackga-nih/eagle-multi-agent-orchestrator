"""Tag Computation — Auto-derives system tags from entity metadata.

Computes system_tags, far_tags, threshold_tier, and approval_level
from document/package attributes using the compliance matrix and
template registry data.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

logger = logging.getLogger("eagle.tag_computation")


# ── Document Tags ─────────────────────────────────────────────────────


def compute_document_tags(doc: dict, package: Optional[dict] = None) -> list[str]:
    """Derive system tags for a document from its metadata and parent package.

    Tags produced:
        - phase:{phase}        from template registry ACQUISITION_PHASES
        - doc_type:{doc_type}  canonical document type
        - status:{status}      current document status
        - risk:{level}         low/medium/high based on package estimated_value
    """
    tags = []
    doc_type = doc.get("doc_type", "")
    status = doc.get("status", "draft")

    if doc_type:
        tags.append(f"doc_type:{doc_type}")

    if status:
        tags.append(f"status:{status}")

    # Derive phase from doc_type → acquisition phase mapping
    phase = _doc_type_to_phase(doc_type)
    if phase:
        tags.append(f"phase:{phase}")

    # Derive risk from package estimated_value
    if package:
        value = _to_float(package.get("estimated_value"))
        if value is not None:
            risk = _value_to_risk(value)
            tags.append(f"risk:{risk}")

        # Inherit package pathway
        pathway = package.get("acquisition_pathway", "")
        if pathway:
            tags.append(f"pathway:{pathway}")

    return tags


def compute_package_tags(package: dict) -> list[str]:
    """Derive system tags for a package from its metadata.

    Tags produced:
        - phase:{status}           from package lifecycle status
        - pathway:{pathway}        acquisition pathway
        - method:{method}          acquisition method
        - contract_type:{type}     contract type
        - threshold:{tier}         from estimated_value + thresholds
        - approval:{level}         required approval level
        - risk:{level}             low/medium/high
        - vehicle:{vehicle}        contract vehicle if set
        - requires:{doc_type}      for each required document
    """
    tags = []
    status = package.get("status", "intake")
    value = _to_float(package.get("estimated_value"))

    if status:
        tags.append(f"phase:{status}")

    pathway = package.get("acquisition_pathway", "")
    if pathway:
        tags.append(f"pathway:{pathway}")

    method = package.get("acquisition_method", "")
    if method:
        tags.append(f"method:{method}")

    contract_type = package.get("contract_type", "")
    if contract_type:
        tags.append(f"contract_type:{contract_type}")

    vehicle = package.get("contract_vehicle", "")
    if vehicle:
        tags.append(f"vehicle:{vehicle}")

    if value is not None:
        tags.append(f"risk:{_value_to_risk(value)}")

        tier = _value_to_threshold_tier(value)
        if tier:
            tags.append(f"threshold:{tier}")

    # Required documents as tags
    for doc in package.get("required_documents", []):
        tags.append(f"requires:{doc}")

    return tags


def compute_threshold_tier(estimated_value: float) -> str:
    """Return the FAR threshold tier name for a dollar value."""
    return _value_to_threshold_tier(estimated_value)


def compute_approval_level(
    estimated_value: float,
    acquisition_method: str = "",
    contract_type: str = "",
) -> str:
    """Return the required approval level for a package.

    Uses compliance matrix logic to determine who must approve.
    """
    try:
        from app.compliance_matrix import get_requirements

        result = get_requirements(estimated_value, acquisition_method, contract_type)
        approvals = result.get("approvals_required", [])
        if approvals:
            # Return highest authority
            return approvals[-1].get("role", "CO")
        return "CO"
    except Exception:
        if estimated_value > 50_000_000:
            return "SPE"
        elif estimated_value > 2_500_000:
            return "HCA"
        elif estimated_value > 350_000:
            return "Competition Advocate"
        return "CO"


def compute_far_tags_from_template(doc_type: str) -> list[str]:
    """Derive FAR clause tags from a template's clause reference sidecar.

    Reads the template-clause-references JSON for the given doc_type category
    and returns a flat list of clause numbers.
    """
    try:
        from app.template_schema import load_clause_references_by_category

        refs = load_clause_references_by_category(doc_type)
        clause_numbers = set()
        for ref_data in refs:
            for section_data in ref_data.get("section_clause_map", {}).values():
                for clause in section_data.get("clauses", []):
                    num = clause.get("clause_number", "").strip()
                    if num:
                        clause_numbers.add(num)
            for clause in ref_data.get("template_level_clauses", []):
                num = clause.get("clause_number", "").strip()
                if num:
                    clause_numbers.add(num)
        return sorted(clause_numbers)
    except Exception as e:
        logger.debug("compute_far_tags_from_template(%s) failed: %s", doc_type, e)
        return []


def compute_completeness_pct(doc_type: str, content: str) -> float:
    """Compute document completeness percentage from template schema validation.

    Returns 0-100 float.
    """
    try:
        from app.template_schema import validate_completeness

        report = validate_completeness(doc_type, content)
        if report:
            return report.completeness_pct
    except Exception as e:
        logger.debug("compute_completeness_pct(%s) failed: %s", doc_type, e)
    return 0.0


def compute_compliance_readiness(
    package: dict,
    documents: list[dict],
) -> dict:
    """Compute compliance readiness score for a package.

    Returns:
        Dict with score (0-100), missing_documents, draft_documents, last_computed
    """
    from datetime import datetime

    required = set(package.get("required_documents", []))

    # Check actual document statuses
    doc_by_type = {}
    for doc in documents:
        dt = doc.get("doc_type", "")
        if dt not in doc_by_type or doc.get("version", 0) > doc_by_type[dt].get(
            "version", 0
        ):
            doc_by_type[dt] = doc

    missing = []
    drafts = []
    finalized = 0

    for req_doc in required:
        if req_doc in doc_by_type:
            status = doc_by_type[req_doc].get("status", "draft")
            if status in ("final", "approved"):
                finalized += 1
            else:
                drafts.append(req_doc)
        else:
            missing.append(req_doc)

    total = len(required) if required else 1
    score = round((finalized / total) * 100, 1) if total else 100.0

    return {
        "score": score,
        "missing_documents": missing,
        "draft_documents": drafts,
        "finalized_count": finalized,
        "total_required": len(required),
        "last_computed": datetime.utcnow().isoformat(),
    }


# ── Helpers ───────────────────────────────────────────────────────────


_DOC_TYPE_PHASE_MAP = {
    "sow": "planning",
    "igce": "planning",
    "market_research": "planning",
    "acquisition_plan": "planning",
    "justification": "planning",
    "eval_criteria": "solicitation",
    "security_checklist": "planning",
    "section_508": "planning",
    "cor_certification": "award",
    "contract_type_justification": "planning",
    "son_products": "intake",
    "son_services": "intake",
    "buy_american": "planning",
    "subk_plan": "planning",
    "conference_request": "administration",
}


def _doc_type_to_phase(doc_type: str) -> str:
    """Map a doc_type to its acquisition phase."""
    # Normalize hyphens to underscores
    normalized = doc_type.replace("-", "_")
    return _DOC_TYPE_PHASE_MAP.get(normalized, "")


def _to_float(val) -> Optional[float]:
    """Safely convert a value to float."""
    if val is None:
        return None
    try:
        if isinstance(val, Decimal):
            return float(val)
        return float(val)
    except (TypeError, ValueError):
        return None


def _value_to_risk(value: float) -> str:
    """Map dollar value to risk level."""
    if value > 2_500_000:
        return "high"
    elif value > 350_000:
        return "medium"
    return "low"


_THRESHOLD_TIERS = [
    (15_000, "micro"),
    (25_000, "micro_plus"),
    (350_000, "sat"),
    (750_000, "subk_threshold"),
    (900_000, "commercial_simplified"),
    (2_500_000, "competition_advocate"),
    (4_500_000, "contract_review"),
    (6_000_000, "earned_value"),
    (20_000_000, "congressional_notification"),
    (50_000_000, "hca_approval"),
    (90_000_000, "tina_threshold"),
    (100_000_000, "agency_head"),
    (150_000_000, "spe_approval"),
]


def _value_to_threshold_tier(value: float) -> str:
    """Map dollar value to the highest triggered threshold tier."""
    tier = "micro"
    for threshold, name in _THRESHOLD_TIERS:
        if value >= threshold:
            tier = name
        else:
            break
    return tier
