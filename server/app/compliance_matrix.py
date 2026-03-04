"""
NCI/NIH Contract Requirements Decision Tree — Python port.

Deterministic compliance logic ported from contract-requirements-matrix.html.
Backed by three JSON data files in eagle-plugin/data/:
  - thresholds.json   — threshold tier definitions
  - contract-vehicles.json — vehicle catalog & selection guide
  - far-database.json — FAR/HHSAR citation database

All functions are read-only (no tenant state, no side effects).
"""

import json
from pathlib import Path

# ---------------------------------------------------------------------------
# Load JSON data files (cached at import time)
# ---------------------------------------------------------------------------

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "eagle-plugin" / "data"


def _load_json(filename: str) -> dict | list:
    path = _DATA_DIR / filename
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


_THRESHOLDS_DATA: dict = _load_json("thresholds.json")
_VEHICLES_DATA: dict = _load_json("contract-vehicles.json")
_FAR_DATABASE: list[dict] = _load_json("far-database.json")


# ---------------------------------------------------------------------------
# Constants (matching the HTML decision tree)
# ---------------------------------------------------------------------------

METHODS = [
    {"id": "micro", "label": "Micro-Purchase", "sub": "FAR 13.2 — up to $15K", "far": "13.2"},
    {"id": "sap", "label": "Simplified (SAP)", "sub": "FAR 13 — $15K to $350K", "far": "13"},
    {"id": "negotiated", "label": "Negotiated", "sub": "FAR 15 — above $350K", "far": "15"},
    {"id": "fss", "label": "FSS Direct Order", "sub": "FAR 8.4 — Schedule pricing", "far": "8.4"},
    {"id": "bpa-est", "label": "BPA Establishment", "sub": "FAR 8.4 — Blanket agreement", "far": "8.4"},
    {"id": "bpa-call", "label": "BPA Call Order", "sub": "FAR 8.4 — Order under BPA", "far": "8.4"},
    {"id": "idiq", "label": "IDIQ Parent Award", "sub": "FAR 16.5 — Indefinite delivery", "far": "16.5"},
    {"id": "idiq-order", "label": "IDIQ Task/Delivery Order", "sub": "FAR 16.5 — Order under IDIQ", "far": "16.5"},
    {"id": "sole", "label": "Sole Source / J&A", "sub": "FAR 6.3 — Limited competition", "far": "6.3"},
]

TYPES = [
    {"id": "ffp", "label": "Firm-Fixed-Price (FFP)", "risk": 95, "category": "fp"},
    {"id": "fp-epa", "label": "FP w/ Economic Price Adj", "risk": 80, "category": "fp"},
    {"id": "fpi", "label": "Fixed-Price Incentive (FPI)", "risk": 65, "category": "fp"},
    {"id": "cpff", "label": "Cost-Plus-Fixed-Fee (CPFF)", "risk": 25, "category": "cr"},
    {"id": "cpif", "label": "Cost-Plus-Incentive-Fee (CPIF)", "risk": 35, "category": "cr"},
    {"id": "cpaf", "label": "Cost-Plus-Award-Fee (CPAF)", "risk": 20, "category": "cr"},
    {"id": "tm", "label": "Time & Materials (T&M)", "risk": 15, "category": "loe"},
    {"id": "lh", "label": "Labor-Hour (LH)", "risk": 15, "category": "loe"},
]

THRESHOLD_TIERS = [
    {"value": 15_000, "label": "$15K MPT", "short": "$15K"},
    {"value": 25_000, "label": "$25K Synopsis", "short": "$25K"},
    {"value": 350_000, "label": "$350K SAT", "short": "$350K"},
    {"value": 750_000, "label": "$750K SubK", "short": "$750K"},
    {"value": 900_000, "label": "$900K J&A", "short": "$900K"},
    {"value": 2_500_000, "label": "$2.5M TINA", "short": "$2.5M"},
    {"value": 4_500_000, "label": "$4.5M Congress", "short": "$4.5M"},
    {"value": 6_000_000, "label": "$6M IDIQ Enh", "short": "$6M"},
    {"value": 20_000_000, "label": "$20M AP", "short": "$20M"},
    {"value": 50_000_000, "label": "$50M HCA", "short": "$50M"},
    {"value": 90_000_000, "label": "$90M SPE J&A", "short": "$90M"},
    {"value": 100_000_000, "label": "$100M SPE", "short": "$100M"},
    {"value": 150_000_000, "label": "$150M OAP", "short": "$150M"},
]

_METHODS_BY_ID = {m["id"]: m for m in METHODS}
_TYPES_BY_ID = {t["id"]: t for t in TYPES}


# ---------------------------------------------------------------------------
# Helper functions (ported from HTML)
# ---------------------------------------------------------------------------

def _ap_approval(v: float) -> str:
    if v > 150_000_000:
        return "HHS/OAP approval required (> $150M)"
    if v > 50_000_000:
        return "HCA-NIH approval required ($50M-$150M)"
    if v > 20_000_000:
        return "OA Director approval by HCA ($20M-$50M)"
    return "One level above CO (SAT-$20M)"


def _ja_approval(v: float) -> str:
    if v > 90_000_000:
        return "SPE through HHS/OAP (> $90M) - FAR 6.304(a)(4)"
    if v > 20_000_000:
        return "HCA + additional reviews ($20M-$90M) - FAR 6.304(a)(3)"
    if v > 900_000:
        return "HCA + NIH Competition Advocate ($900K-$20M) - FAR 6.304(a)(2)"
    return "CO approval (<= $900K) - FAR 6.304(a)(1)"


# ---------------------------------------------------------------------------
# Core: get_requirements()
# ---------------------------------------------------------------------------

def get_requirements(
    contract_value: float,
    acquisition_method: str,
    contract_type: str,
    flags: dict | None = None,
) -> dict:
    """Deterministic compliance analysis for a given procurement scenario.

    Args:
        contract_value: Estimated dollar value of the contract.
        acquisition_method: One of METHODS[].id (e.g. 'negotiated', 'sap').
        contract_type: One of TYPES[].id (e.g. 'ffp', 'cpff', 'tm').
        flags: Optional dict with boolean keys:
            is_it, is_small_business, is_rd, is_human_subjects, is_services

    Returns:
        Dict with keys: errors, warnings, documents_required,
        compliance_items, competition_rules, thresholds_triggered,
        thresholds_not_triggered, timeline_estimate, risk_allocation,
        fee_caps, pmr_checklist, approvals_required
    """
    v = float(contract_value)
    m = acquisition_method
    t = contract_type

    flags = flags or {}
    is_it = flags.get("is_it", False)
    is_sb = flags.get("is_small_business", False)
    is_rd = flags.get("is_rd", False)
    is_hs = flags.get("is_human_subjects", False)
    is_services = flags.get("is_services", True)

    t_obj = _TYPES_BY_ID.get(t)
    if not t_obj:
        return {"errors": [f"Unknown contract type: {t}"], "warnings": []}

    m_obj = _METHODS_BY_ID.get(m)
    if not m_obj:
        return {"errors": [f"Unknown acquisition method: {m}"], "warnings": []}

    is_cr = t_obj["category"] == "cr"
    is_loe = t_obj["category"] == "loe"

    # --- Warnings / Errors ---
    warnings: list[str] = []
    errors: list[str] = []

    if is_cr:
        warnings.append(
            "Cost-reimbursement requires written AP approval, adequate "
            "contractor accounting system, and designated COR (FAR 16.301)."
        )
        if is_rd:
            warnings.append("CPFF fee cap for R&D: 15% of estimated cost (FAR 16.304).")

    if is_loe:
        warnings.append(
            "T&M/LH is LEAST PREFERRED. CO must prepare D&F that no other "
            "contract type is suitable (FAR 16.601)."
        )
        if m == "bpa-est" and v > 350_000:
            warnings.append(
                "T&M/LH BPAs > 3 years require HCA approval (not just standard D&F)."
            )

    if t == "cpaf":
        warnings.append(
            "CPAF requires approved award-fee plan before award. "
            "Rollover of unearned fee is PROHIBITED (FAR 16.402-2)."
        )

    if m == "micro" and v > 15_000:
        errors.append("Micro-purchase threshold is $15,000 (HHS). Value exceeds MPT.")

    if m == "sap" and v > 350_000:
        errors.append(
            "SAP threshold is $350,000 (SAT). Value exceeds SAT "
            "- use Negotiated (FAR 15)."
        )

    # --- Documents Required ---
    docs: list[dict] = []

    # Purchase Request — always
    docs.append({"name": "Purchase Request", "required": True, "note": "FAR 4.803(a)(1)"})

    # SOW/PWS
    if m != "micro":
        docs.append({
            "name": "SOW / PWS" if is_services else "Statement of Need (SON)",
            "required": True,
            "note": "Performance-based with QASP (FAR 37.6)" if is_services else "Product specifications",
        })
    else:
        docs.append({"name": "SOW / PWS", "required": False, "note": "Not required for micro-purchase"})

    # IGCE
    docs.append({
        "name": "IGCE",
        "required": m != "micro",
        "note": "Detailed breakdown required (HHSAM 307.105-71)" if v > 350_000 else "Sufficient detail/breakdown",
    })

    # Market Research
    if v > 350_000:
        docs.append({"name": "Market Research Report", "required": True, "note": "HHS template required (HHSAM 310.000)"})
    elif v > 15_000:
        docs.append({"name": "Market Research", "required": True, "note": "Documented justification (less formal)"})
    else:
        docs.append({"name": "Market Research", "required": False, "note": "Not required for micro-purchase"})

    # Acquisition Plan
    if v > 350_000:
        docs.append({"name": "Acquisition Plan", "required": True, "note": _ap_approval(v)})
    else:
        docs.append({"name": "Acquisition Plan", "required": False, "note": "Not required below SAT ($350K)"})

    # J&A
    needs_ja = m == "sole" or (m == "fss" and v > 350_000) or (m == "bpa-call" and v > 350_000)
    docs.append({
        "name": "J&A / Justification",
        "required": needs_ja,
        "note": _ja_approval(v) if needs_ja else "Only if sole source / limited competition",
    })

    # D&F
    needs_df = is_loe or (is_cr and v > 350_000) or t == "fpi" or t == "cpaf"
    if is_loe:
        df_note = "Required: no other type suitable (FAR 16.601)"
    elif is_cr:
        df_note = "Required for cost-reimbursement"
    else:
        df_note = "Required for incentive/award-fee"
    docs.append({"name": "D&F (Determination & Findings)", "required": needs_df, "note": df_note})

    # Source Selection Plan
    needs_ssp = m == "negotiated" and v > 350_000
    docs.append({
        "name": "Source Selection Plan",
        "required": needs_ssp,
        "note": "Evaluation factors with relative importance" if needs_ssp else "N/A for this method",
    })

    # Subcontracting Plan
    needs_subk = v > 750_000 and not is_sb
    if needs_subk:
        subk_note = "Required for non-SB > $750K (FAR 19.705)"
    elif is_sb:
        subk_note = "Exempt - small business awardee"
    else:
        subk_note = "Below $750K threshold"
    docs.append({"name": "Subcontracting Plan", "required": needs_subk, "note": subk_note})

    # QASP
    needs_qasp = is_services and m != "micro"
    docs.append({
        "name": "QASP",
        "required": needs_qasp,
        "note": "Required for performance-based services (FAR 46)" if needs_qasp else "Products / micro-purchase",
    })

    # SB Review
    docs.append({
        "name": "HHS-653 Small Business Review",
        "required": v > 15_000,
        "note": "Required > MPT (AA 2023-02 Amendment 3)" if v > 15_000 else "Below MPT",
    })

    # IT-specific
    if is_it:
        docs.append({"name": "IT Security & Privacy Certification", "required": True, "note": "HHSAM 339.101(c)(1)"})
        docs.append({"name": "Section 508 ICT Evaluation", "required": v > 15_000, "note": "Required for IT > MPT"})

    # Human Subjects
    if is_hs:
        docs.append({"name": "Human Subjects Provisions", "required": True, "note": "HHSAR 370.3, 45 CFR 46"})

    # --- Thresholds ---
    triggered = [th for th in THRESHOLD_TIERS if v >= th["value"]]
    not_triggered = [th for th in THRESHOLD_TIERS if v < th["value"]]

    # --- Compliance Items ---
    compliance: list[dict] = []
    compliance.append({"name": "Section 889 Compliance", "status": "required", "note": "FAR 52.204-25 - all solicitations/contracts"})
    compliance.append({"name": "BAA/TAA Checklist", "status": "required" if m != "micro" else "conditional", "note": "HHSAM 325.102-70"})
    compliance.append({
        "name": "SAM.gov Synopsis",
        "status": "required" if v > 25_000 else "n/a",
        "note": "Required > $25K (FAR 5.101)" if v > 25_000 else "Below $25K",
    })
    compliance.append({
        "name": "CPARS Evaluation",
        "status": "required" if v > 350_000 else "n/a",
        "note": "Required > SAT" if v > 350_000 else "Below SAT",
    })
    compliance.append({
        "name": "Congressional Notification",
        "status": "required" if v > 4_500_000 else "n/a",
        "note": "Required > $4.5M - email grantfax@hhs.gov" if v > 4_500_000 else "Below $4.5M",
    })
    compliance.append({
        "name": "Certified Cost/Pricing Data (TINA)",
        "status": "required" if v > 2_500_000 else "n/a",
        "note": "Required > $2.5M (with exceptions)" if v > 2_500_000 else "Below $2.5M",
    })

    if is_it:
        compliance.append({"name": "Section 508 ICT Accessibility", "status": "required", "note": "Required for IT acquisitions"})
        compliance.append({"name": "IT Security & Privacy Language", "status": "required", "note": "HHSAM Part 339.105"})

    if is_hs:
        compliance.append({"name": "Human Subjects Protection (45 CFR 46)", "status": "required", "note": "HHSAR 370.3"})

    if is_services:
        compliance.append({"name": "Severable Services <= 1yr/period", "status": "required", "note": "FAR 37.106(b), 32.703-3(b)"})

    # --- Competition Rules ---
    competition = ""
    if m == "micro":
        competition = "Single quote acceptable. Government purchase card preferred."
    elif m == "sap":
        if v > 25_000:
            competition = "Maximum practicable competition. Minimum 3 sources if practicable. Synopsis on SAM.gov."
        else:
            competition = "Reasonable competition. Minimum 3 sources if practicable."
    elif m == "negotiated":
        competition = "Full and open competition required (FAR Part 6). Synopsis, evaluation factors, source selection."
    elif m == "fss":
        if v > 350_000:
            competition = "eBuy posting OR RFQ to enough contractors for 3 quotes. Price reduction attempt required."
        else:
            competition = "Consider quotes from at least 3 schedule contractors."
    elif m == "bpa-est":
        if v > 350_000:
            competition = "eBuy posting to ALL schedule holders OR 3-quote effort. Document award decision."
        else:
            competition = "Seek quotes from at least 3 schedule holders."
    elif m == "bpa-call":
        if v > 350_000:
            competition = "RFQ to all BPA holders OR limited sources justification. Fair opportunity required."
        else:
            competition = "Fair opportunity to all BPA holders > MPT, or justification."
    elif m == "idiq":
        competition = "Full and open competition for parent contract. Multiple award preference unless exception (FAR 16.504)."
    elif m == "idiq-order":
        if v > 7_500_000:
            competition = (
                "Fair opportunity to all IDIQ holders. Clear requirements, "
                "evaluation factors with relative importance, post-award notifications/debriefings."
            )
        elif v > 350_000:
            competition = "Fair opportunity. Provide fair notice, issue solicitation/RFQ, document award basis."
        else:
            competition = "Fair opportunity. May place without further solicitation if fair consideration documented."
    elif m == "sole":
        competition = "Exception to competition - FAR 6.302 authority required. Full J&A with CO certification."

    # Enhanced IDIQ
    if m == "idiq-order" and v > 6_000_000:
        competition += (
            " ENHANCED: Detailed evaluation factors + relative importance "
            "+ post-award notification + debriefing (> $6M)."
        )

    # --- PMR Checklist ---
    if m == "sap" or (m == "negotiated" and v <= 350_000):
        pmr = "HHS PMR SAP Checklist"
    elif m == "negotiated":
        pmr = "HHS PMR Negotiated + Common Requirements"
    elif m == "fss":
        pmr = "HHS PMR FSS Order Checklist"
    elif m in ("bpa-est", "bpa-call"):
        pmr = "HHS PMR BPA Checklist"
    elif m in ("idiq", "idiq-order"):
        pmr = "HHS PMR IDIQ Checklist"
    elif m == "sole":
        pmr = "HHS PMR SAP or Negotiated + J&A Requirements"
    elif m == "micro":
        pmr = "Micro-Purchase - Minimal file documentation"
    else:
        pmr = "HHS PMR Common Requirements"

    # --- Timeline (weeks) ---
    timelines = {
        "micro": (0, 1),
        "sap": (2, 6),
        "negotiated": (12, 36),
        "fss": (2, 8),
        "bpa-est": (4, 12),
        "bpa-call": (1, 4),
        "idiq": (16, 52),
        "idiq-order": (2, 12),
        "sole": (4, 16),
    }
    time_min, time_max = timelines.get(m, (1, 5))

    # Approval escalation adds time
    if v > 90_000_000:
        time_min += 6
        time_max += 8
    elif v > 50_000_000:
        time_min += 4
        time_max += 6
    elif v > 20_000_000:
        time_min += 2
        time_max += 4

    # --- Risk ---
    risk_pct = t_obj["risk"]

    # --- Fee Caps ---
    fee_caps: list[str] = []
    if is_cr:
        if is_rd:
            fee_caps.append("R&D: <= 15% of est. cost")
        fee_caps.append("Other CPFF: <= 10% of est. cost")
        fee_caps.append("A-E public works: <= 6% of est. construction")
        fee_caps.append("Cost-plus-%-of-cost: PROHIBITED")

    # --- Approvals Required ---
    approvals: list[dict] = []
    if v > 350_000:
        approvals.append({"type": "Acquisition Plan", "authority": _ap_approval(v)})
    if needs_ja:
        approvals.append({"type": "J&A", "authority": _ja_approval(v)})
    if needs_df:
        approvals.append({"type": "D&F", "authority": "One level above CO" if is_loe else "CO"})
    if v > 2_500_000:
        approvals.append({"type": "TINA / Cost Data", "authority": "Certified cost or pricing data required"})

    return {
        "errors": errors,
        "warnings": warnings,
        "documents_required": docs,
        "compliance_items": compliance,
        "competition_rules": competition,
        "thresholds_triggered": triggered,
        "thresholds_not_triggered": not_triggered,
        "timeline_estimate": {"min_weeks": time_min, "max_weeks": time_max},
        "risk_allocation": {"contractor_risk_pct": risk_pct, "category": t_obj["category"]},
        "fee_caps": fee_caps,
        "pmr_checklist": pmr,
        "approvals_required": approvals,
        "method": m_obj,
        "contract_type": t_obj,
    }


# ---------------------------------------------------------------------------
# Operation: search_far
# ---------------------------------------------------------------------------

def search_far(keyword: str, parts: list[str] | None = None) -> list[dict]:
    """Keyword search across the FAR database entries.

    Args:
        keyword: Search term (case-insensitive).
        parts: Optional list of FAR part numbers to restrict search.

    Returns:
        List of matching FAR entries.
    """
    keyword_lower = keyword.lower()
    results = []
    for entry in _FAR_DATABASE:
        if parts and entry.get("part") not in parts:
            continue
        searchable = " ".join([
            entry.get("title", ""),
            entry.get("summary", ""),
            entry.get("section", ""),
            " ".join(entry.get("keywords", [])),
        ]).lower()
        if keyword_lower in searchable:
            results.append(entry)
    return results


# ---------------------------------------------------------------------------
# Operation: suggest_vehicle
# ---------------------------------------------------------------------------

def suggest_vehicle(flags: dict | None = None) -> dict:
    """Recommend contract vehicles based on requirement flags.

    Args:
        flags: Dict with boolean keys: is_it, is_services, is_small_business, etc.

    Returns:
        Dict with recommended vehicles and rationale.
    """
    flags = flags or {}
    is_it = flags.get("is_it", False)
    is_services = flags.get("is_services", False)

    recommendations = _VEHICLES_DATA.get("selection_guide", {}).get("recommendations", {})
    vehicles = _VEHICLES_DATA.get("vehicles", {})

    suggested: list[dict] = []

    if is_it and is_services:
        key = "it_services_complex"
        suggested.append({
            "recommendation": recommendations.get(key, ""),
            "vehicle": "nitaac",
            "detail": vehicles.get("nitaac", {}),
        })
    elif is_it:
        key = "it_commodities"
        suggested.append({
            "recommendation": recommendations.get(key, ""),
            "vehicle": "gsa_schedules",
            "detail": vehicles.get("gsa_schedules", {}),
        })
    elif is_services:
        key = "professional_services"
        suggested.append({
            "recommendation": recommendations.get(key, ""),
            "vehicle": "gsa_schedules",
            "detail": vehicles.get("gsa_schedules", {}),
        })
    else:
        key = "unique_requirements"
        suggested.append({
            "recommendation": recommendations.get(key, "Full and open competition"),
            "vehicle": "open_competition",
            "detail": {"name": "Full and Open Competition", "description": "Standard FAR Part 15 process"},
        })

    return {
        "suggested_vehicles": suggested,
        "decision_factors": _VEHICLES_DATA.get("selection_guide", {}).get("decision_factors", []),
        "notes": _VEHICLES_DATA.get("notes", []),
    }


# ---------------------------------------------------------------------------
# Dispatcher: execute_operation()
# ---------------------------------------------------------------------------

def execute_operation(params: dict) -> dict:
    """Dispatch a compliance matrix operation.

    Args:
        params: Dict with 'operation' key and operation-specific parameters.

    Returns:
        Operation result as a dict.
    """
    op = params.get("operation", "")

    if op == "query":
        return get_requirements(
            contract_value=params.get("contract_value", 0),
            acquisition_method=params.get("acquisition_method", "sap"),
            contract_type=params.get("contract_type", "ffp"),
            flags={
                "is_it": params.get("is_it", False),
                "is_small_business": params.get("is_small_business", False),
                "is_rd": params.get("is_rd", False),
                "is_human_subjects": params.get("is_human_subjects", False),
                "is_services": params.get("is_services", True),
            },
        )

    if op == "list_methods":
        return {"methods": METHODS}

    if op == "list_types":
        return {"types": TYPES}

    if op == "list_thresholds":
        return {
            "threshold_tiers": THRESHOLD_TIERS,
            "threshold_data": _THRESHOLDS_DATA,
        }

    if op == "search_far":
        keyword = params.get("keyword", "")
        parts = params.get("parts")
        if not keyword:
            return {"error": "keyword is required for search_far operation"}
        return {"results": search_far(keyword, parts)}

    if op == "suggest_vehicle":
        return suggest_vehicle(flags={
            "is_it": params.get("is_it", False),
            "is_services": params.get("is_services", False),
            "is_small_business": params.get("is_small_business", False),
        })

    return {"error": f"Unknown operation: {op}. Valid: query, list_methods, list_types, list_thresholds, search_far, suggest_vehicle"}
