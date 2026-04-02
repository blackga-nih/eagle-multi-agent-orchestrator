"""
NCI/NIH Contract Requirements Decision Tree — Python port.

Deterministic compliance logic ported from contract-requirements-matrix.html.
Backed by JSON data files in eagle-plugin/data/:
  - matrix.json          — authoritative thresholds + rules (single source of truth)
  - contract-vehicles.json — vehicle catalog & selection guide
  - far-database.json    — FAR/HHSAR citation database
  - thresholds.json      — DEPRECATED: retained for backward compat on list_thresholds

All functions are read-only (no tenant state, no side effects).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Load JSON data files (cached at import time)
# ---------------------------------------------------------------------------

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "eagle-plugin" / "data"


def _load_json(filename: str) -> dict | list:
    path = _DATA_DIR / filename
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


_MATRIX_DATA: dict = _load_json("matrix.json")
_THRESHOLDS_DATA: dict = _load_json("thresholds.json")  # deprecated
_VEHICLES_DATA: dict = _load_json("contract-vehicles.json")
_FAR_DATABASE: list[dict] = _load_json("far-database.json")


# ---------------------------------------------------------------------------
# Constants (matching the HTML decision tree)
# ---------------------------------------------------------------------------

METHODS = [
    {
        "id": "micro",
        "label": "Micro-Purchase",
        "sub": "FAR 13.2 — up to $15K",
        "far": "13.2",
    },
    {
        "id": "sap",
        "label": "Simplified (SAP)",
        "sub": "FAR 13 — $15K to $350K",
        "far": "13",
    },
    {
        "id": "negotiated",
        "label": "Negotiated",
        "sub": "FAR 15 — above $350K",
        "far": "15",
    },
    {
        "id": "fss",
        "label": "FSS Direct Order",
        "sub": "FAR 8.4 — Schedule pricing",
        "far": "8.4",
    },
    {
        "id": "bpa-est",
        "label": "BPA Establishment",
        "sub": "FAR 8.4 — Blanket agreement",
        "far": "8.4",
    },
    {
        "id": "bpa-call",
        "label": "BPA Call Order",
        "sub": "FAR 8.4 — Order under BPA",
        "far": "8.4",
    },
    {
        "id": "idiq",
        "label": "IDIQ Parent Award",
        "sub": "FAR 16.5 — Indefinite delivery",
        "far": "16.5",
    },
    {
        "id": "idiq-order",
        "label": "IDIQ Task/Delivery Order",
        "sub": "FAR 16.5 — Order under IDIQ",
        "far": "16.5",
    },
    {
        "id": "sole",
        "label": "Sole Source / J&A",
        "sub": "FAR 6.3 — Limited competition",
        "far": "6.3",
    },
]

TYPES = [
    {"id": "ffp", "label": "Firm-Fixed-Price (FFP)", "risk": 95, "category": "fp"},
    {"id": "fp-epa", "label": "FP w/ Economic Price Adj", "risk": 80, "category": "fp"},
    {"id": "fpi", "label": "Fixed-Price Incentive (FPI)", "risk": 65, "category": "fp"},
    {"id": "cpff", "label": "Cost-Plus-Fixed-Fee (CPFF)", "risk": 25, "category": "cr"},
    {
        "id": "cpif",
        "label": "Cost-Plus-Incentive-Fee (CPIF)",
        "risk": 35,
        "category": "cr",
    },
    {"id": "cpaf", "label": "Cost-Plus-Award-Fee (CPAF)", "risk": 20, "category": "cr"},
    {"id": "tm", "label": "Time & Materials (T&M)", "risk": 15, "category": "loe"},
    {"id": "lh", "label": "Labor-Hour (LH)", "risk": 15, "category": "loe"},
]

# Thresholds sourced from matrix.json (single source of truth).
# Each entry has: value, label, short, triggers[].
THRESHOLD_TIERS: list[dict] = _MATRIX_DATA["thresholds"]


def _threshold(trigger: str) -> int:
    """Look up a threshold value by its trigger name from matrix.json."""
    for t in THRESHOLD_TIERS:
        if trigger in t.get("triggers", []):
            return t["value"]
    raise ValueError(f"Unknown threshold trigger: {trigger}")


# Convenience constants derived from matrix.json at import time.
_MPT = _threshold("micro_purchase_threshold")
_SAT = _threshold("simplified_acquisition_threshold")
_SYNOPSIS = _threshold("sam_gov_synopsis_required")
_SUBK = _threshold("subcontracting_plan_required")
_JA_HCA = _threshold("ja_hca_approval_required")
_TINA = _threshold("certified_cost_pricing_data_required")
_CONGRESS = _threshold("8a_sole_source_services_ceiling")  # $4.5M
_IDIQ_ENH = _threshold("idiq_enhanced_competition")
_AP_OA = _threshold("written_acquisition_plan_required")  # $20M
_HCA = _threshold("hca_approval_required")  # $50M
_SPE_JA = _threshold("spe_ja_approval_required")  # $90M
_OAP = _threshold("oap_approval_required")  # $150M

_METHODS_BY_ID = {m["id"]: m for m in METHODS}
_TYPES_BY_ID = {t["id"]: t for t in TYPES}


# ---------------------------------------------------------------------------
# Normalization: alias maps + resolve functions
# ---------------------------------------------------------------------------

_METHOD_ALIASES: dict[str, str] = {
    # Full and open / negotiated (FAR 15)
    "full_and_open": "negotiated",
    "full and open": "negotiated",
    "full_and_open_competition": "negotiated",
    "full_competition": "negotiated",
    "full competition": "negotiated",
    "far part 15": "negotiated",
    "part 15": "negotiated",
    "far_15": "negotiated",
    "sealed_bidding": "negotiated",
    "sealed bidding": "negotiated",
    "far part 14": "negotiated",
    "part 14": "negotiated",
    # SAP / simplified (FAR 13)
    "simplified_acquisition": "sap",
    "simplified acquisition": "sap",
    "simplified": "sap",
    "far part 13": "sap",
    "part 13": "sap",
    "far_13": "sap",
    # Micro-purchase
    "micro_purchase": "micro",
    "micro purchase": "micro",
    "micropurchase": "micro",
    "purchase_card": "micro",
    # Sole source
    "sole_source": "sole",
    "sole source": "sole",
    "j&a": "sole",
    "limited_competition": "sole",
    # IDIQ orders
    "task_order": "idiq-order",
    "task order": "idiq-order",
    "delivery_order": "idiq-order",
    "delivery order": "idiq-order",
    "idiq_order": "idiq-order",
    # IDIQ parent
    "idiq_parent": "idiq",
    "indefinite_delivery": "idiq",
    "indefinite delivery": "idiq",
    # BPA establishment
    "bpa": "bpa-est",
    "blanket_purchase_agreement": "bpa-est",
    "bpa_establishment": "bpa-est",
    "bpa_est": "bpa-est",
    # BPA call
    "bpa_call": "bpa-call",
    "bpa call": "bpa-call",
    "call_order": "bpa-call",
    # FSS / schedules
    "schedule": "fss",
    "gsa": "fss",
    "gsa_schedule": "fss",
    "gsa schedule": "fss",
    "gsa_schedules": "fss",
    "federal_supply_schedule": "fss",
    "far part 8": "fss",
    "part 8": "fss",
    # Note: "8a" / "sba 8(a)" should NOT map to FSS.
    # 8(a) uses is_8a=True flag with the appropriate method (sap/negotiated).
    # "far part 8" (FAR 8.4 schedules) correctly maps to fss above.
}

_TYPE_ALIASES: dict[str, str] = {
    # FFP
    "firm_fixed_price": "ffp",
    "firm fixed price": "ffp",
    "fixed_price": "ffp",
    "fixed price": "ffp",
    # FP-EPA
    "fp_epa": "fp-epa",
    "fixed_price_epa": "fp-epa",
    "economic_price_adjustment": "fp-epa",
    # FPI
    "fixed_price_incentive": "fpi",
    "fp_incentive": "fpi",
    "fpif": "fpi",
    # CPFF
    "cost_plus_fixed_fee": "cpff",
    "cost plus fixed fee": "cpff",
    "cost_plus": "cpff",
    "cost plus": "cpff",
    "cost_reimbursement": "cpff",
    # CPIF
    "cost_plus_incentive_fee": "cpif",
    "cost plus incentive fee": "cpif",
    # CPAF
    "cost_plus_award_fee": "cpaf",
    "cost plus award fee": "cpaf",
    # T&M
    "time_and_materials": "tm",
    "time and materials": "tm",
    "time_and_material": "tm",
    "t_and_m": "tm",
    "t&m": "tm",
    "t_m": "tm",
    # LH
    "labor_hour": "lh",
    "labor hour": "lh",
    "labor_hours": "lh",
}


def _normalize_method(raw: str) -> str | None:
    """Resolve a raw acquisition method string to a canonical method ID."""
    if not raw or not raw.strip():
        return None
    cleaned = raw.strip().lower().replace("-", "_").replace(" ", "_")
    if cleaned in _METHODS_BY_ID:
        return cleaned
    # Canonical IDs like bpa-est, bpa-call, idiq-order use hyphens
    hyphenated = cleaned.replace("_", "-")
    if hyphenated in _METHODS_BY_ID:
        return hyphenated
    # Alias lookup (underscore-normalized form, then original lowered)
    if cleaned in _METHOD_ALIASES:
        return _METHOD_ALIASES[cleaned]
    lowered = raw.strip().lower()
    if lowered in _METHOD_ALIASES:
        return _METHOD_ALIASES[lowered]
    return None


def _normalize_type(raw: str) -> str | None:
    """Resolve a raw contract type string to a canonical type ID."""
    if not raw or not raw.strip():
        return None
    cleaned = raw.strip().lower().replace("-", "_").replace(" ", "_")
    if cleaned in _TYPES_BY_ID:
        return cleaned
    # Canonical IDs like fp-epa use hyphens
    hyphenated = cleaned.replace("_", "-")
    if hyphenated in _TYPES_BY_ID:
        return hyphenated
    if cleaned in _TYPE_ALIASES:
        return _TYPE_ALIASES[cleaned]
    lowered = raw.strip().lower()
    if lowered in _TYPE_ALIASES:
        return _TYPE_ALIASES[lowered]
    return None


# ---------------------------------------------------------------------------
# Helper functions (ported from HTML)
# ---------------------------------------------------------------------------


def _ap_approval(v: float) -> str:
    if v > _OAP:
        return f"HHS/OAP approval required (> ${_OAP:,})"
    if v > _HCA:
        return f"HCA-NIH approval required (${_HCA:,}-${_OAP:,})"
    if v > _AP_OA:
        return f"OA Director approval by HCA (${_AP_OA:,}-${_HCA:,})"
    return f"One level above CO (SAT-${_AP_OA:,})"


def _ja_approval(v: float, is_simplified_sole: bool = False) -> str:
    if is_simplified_sole:
        return (
            "CO determination — FAR 13.106-1(b) simplified sole source. "
            "Legal basis: FAR 6.302-1 / 41 U.S.C. 3304(a)(1). "
            "No Competition Advocate or HCA approval required."
        )
    if v > _SPE_JA:
        return f"SPE through HHS/OAP (> ${_SPE_JA:,}) - FAR 6.304(a)(4)"
    if v > _AP_OA:
        return f"HCA + additional reviews (${_AP_OA:,}-${_SPE_JA:,}) - FAR 6.304(a)(3)"
    if v > _JA_HCA:
        return f"HCA + NIH Competition Advocate (${_JA_HCA:,}-${_AP_OA:,}) - FAR 6.304(a)(2)"
    return f"CO approval (<= ${_JA_HCA:,}) - FAR 6.304(a)(1)"


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
    m = _normalize_method(acquisition_method)
    t = _normalize_type(contract_type)

    flags = flags or {}
    f = flags  # short alias
    is_it = f.get("is_it", False)
    is_sb = f.get("is_small_business", False)
    is_rd = f.get("is_rd", False)
    is_hs = f.get("is_human_subjects", False)
    is_services = f.get("is_services", True)
    is_limited = f.get("is_limited_sources", False)
    is_8a = f.get("is_8a", False)
    is_mfg = f.get("is_manufacturing", False)

    t_obj = _TYPES_BY_ID.get(t) if t else None
    if not t_obj:
        valid_types = ", ".join(sorted(_TYPES_BY_ID.keys()))
        return {
            "errors": [
                f"Unknown contract type: {contract_type}. "
                f"Valid IDs: {valid_types}"
            ],
            "warnings": [],
        }

    m_obj = _METHODS_BY_ID.get(m) if m else None
    if not m_obj:
        valid_methods = ", ".join(sorted(_METHODS_BY_ID.keys()))
        return {
            "errors": [
                f"Unknown acquisition method: {acquisition_method}. "
                f"Valid IDs: {valid_methods}"
            ],
            "warnings": [],
        }

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
        if m == "bpa-est" and v > _SAT:
            warnings.append(
                "T&M/LH BPAs > 3 years require HCA approval (not just standard D&F)."
            )

    if t == "cpaf":
        warnings.append(
            "CPAF requires approved award-fee plan before award. "
            "Rollover of unearned fee is PROHIBITED (FAR 16.402-2)."
        )

    if m == "micro" and v > _MPT:
        errors.append(f"Micro-purchase threshold is ${_MPT:,} (HHS). Value exceeds MPT.")

    if m == "sap" and v > _SAT:
        errors.append(
            f"SAP threshold is ${_SAT:,} (SAT). Value exceeds SAT "
            "- use Negotiated (FAR 15)."
        )

    # --- Documents Required ---
    docs: list[dict] = []

    # Purchase Request — always
    docs.append(
        {"name": "Purchase Request", "required": True, "note": "FAR 4.803(a)(1)"}
    )

    # SOW/PWS
    if m != "micro":
        docs.append(
            {
                "name": "SOW / PWS" if is_services else "Statement of Need (SON)",
                "required": True,
                "note": "Performance-based with QASP (FAR 37.6)"
                if is_services
                else "Product specifications",
            }
        )
    else:
        docs.append(
            {
                "name": "SOW / PWS",
                "required": False,
                "note": "Not required for micro-purchase",
            }
        )

    # IGCE
    docs.append(
        {
            "name": "IGCE",
            "required": m != "micro",
            "note": "Detailed breakdown required (HHSAM 307.105-71)"
            if v > _SAT
            else "Sufficient detail/breakdown",
        }
    )

    # Market Research
    if v > _SAT:
        docs.append(
            {
                "name": "Market Research Report",
                "required": True,
                "note": "HHS template required (HHSAM 310.000)",
            }
        )
    elif v > _MPT:
        docs.append(
            {
                "name": "Market Research",
                "required": True,
                "note": "Documented justification (less formal)",
            }
        )
    else:
        docs.append(
            {
                "name": "Market Research",
                "required": False,
                "note": "Not required for micro-purchase",
            }
        )

    # Acquisition Plan
    if v > _SAT:
        docs.append(
            {"name": "Acquisition Plan", "required": True, "note": _ap_approval(v)}
        )
    else:
        docs.append(
            {
                "name": "Acquisition Plan",
                "required": False,
                "note": f"Not required below SAT (${_SAT:,})",
            }
        )

    # J&A
    is_simplified_sole = m == "sole" and v <= _SAT
    is_fss_limited = m == "fss" and is_limited
    is_bpa_call_limited = m == "bpa-call" and is_limited
    is_bpa_est_limited = m == "bpa-est" and is_limited

    needs_ja = (
        m == "sole"
        or (m == "fss" and (v > _SAT or is_limited))
        or (m == "bpa-call" and (v > _SAT or is_limited))
        or is_bpa_est_limited
    )
    ja_entry: dict = {
        "name": "J&A / Justification",
        "required": needs_ja,
        "note": _ja_approval(v, is_simplified_sole=is_simplified_sole)
        if needs_ja
        else "Only if sole source / limited competition",
    }
    if needs_ja and is_simplified_sole:
        ja_entry["variant"] = "simplified_under_sat"
        ja_entry["authority"] = "FAR 13.106-1(b)"
        ja_entry["template_hint"] = "6.a. Single Source J&A - up to SAT.docx"
    elif needs_ja and (is_fss_limited or is_bpa_call_limited or is_bpa_est_limited) and v <= _SAT:
        ja_entry["variant"] = "simplified_limited_sources"
        ja_entry["authority"] = "FAR 8.405-6"
        ja_entry["template_hint"] = "6.a. Single Source J&A - up to SAT.docx"
    elif needs_ja:
        ja_entry["variant"] = "full"
        ja_entry["authority"] = "FAR 6.302 / 6.303 / 6.304"
    docs.append(ja_entry)

    # D&F
    needs_df = is_loe or (is_cr and v > _SAT) or t == "fpi" or t == "cpaf"
    if is_loe:
        df_note = "Required: no other type suitable (FAR 16.601)"
    elif is_cr:
        df_note = "Required for cost-reimbursement"
    else:
        df_note = "Required for incentive/award-fee"
    docs.append(
        {
            "name": "D&F (Determination & Findings)",
            "required": needs_df,
            "note": df_note,
        }
    )

    # Source Selection Plan
    needs_ssp = m == "negotiated" and v > _SAT
    docs.append(
        {
            "name": "Source Selection Plan",
            "required": needs_ssp,
            "note": "Evaluation factors with relative importance"
            if needs_ssp
            else "N/A for this method",
        }
    )

    # Subcontracting Plan
    needs_subk = v > _SUBK and not is_sb
    if needs_subk:
        subk_note = f"Required for non-SB > ${_SUBK:,} (FAR 19.705)"
    elif is_sb:
        subk_note = "Exempt - small business awardee"
    else:
        subk_note = f"Below ${_SUBK:,} threshold"
    docs.append(
        {"name": "Subcontracting Plan", "required": needs_subk, "note": subk_note}
    )

    # QASP
    needs_qasp = is_services and m != "micro"
    docs.append(
        {
            "name": "QASP",
            "required": needs_qasp,
            "note": "Required for performance-based services (FAR 46)"
            if needs_qasp
            else "Products / micro-purchase",
        }
    )

    # SB Review
    docs.append(
        {
            "name": "HHS-653 Small Business Review",
            "required": v > _MPT,
            "note": "Required > MPT (AA 2023-02 Amendment 3)"
            if v > _MPT
            else "Below MPT",
        }
    )

    # IT-specific
    if is_it:
        docs.append(
            {
                "name": "IT Security & Privacy Certification",
                "required": True,
                "note": "HHSAM 339.101(c)(1)",
            }
        )
        docs.append(
            {
                "name": "Section 508 ICT Evaluation",
                "required": v > _MPT,
                "note": "Required for IT > MPT",
            }
        )

    # Human Subjects
    if is_hs:
        docs.append(
            {
                "name": "Human Subjects Provisions",
                "required": True,
                "note": "HHSAR 370.3, 45 CFR 46",
            }
        )

    # --- Thresholds ---
    triggered = [th for th in THRESHOLD_TIERS if v >= th["value"]]
    not_triggered = [th for th in THRESHOLD_TIERS if v < th["value"]]

    # --- Compliance Items ---
    compliance: list[dict] = []
    compliance.append(
        {
            "name": "Section 889 Compliance",
            "status": "required",
            "note": "FAR 52.204-25 - all solicitations/contracts",
        }
    )
    compliance.append(
        {
            "name": "BAA/TAA Checklist",
            "status": "required" if m != "micro" else "conditional",
            "note": "HHSAM 325.102-70",
        }
    )
    compliance.append(
        {
            "name": "SAM.gov Synopsis",
            "status": "required" if v > _SYNOPSIS else "n/a",
            "note": f"Required > ${_SYNOPSIS:,} (FAR 5.101)" if v > _SYNOPSIS else f"Below ${_SYNOPSIS:,}",
        }
    )
    compliance.append(
        {
            "name": "CPARS Evaluation",
            "status": "required" if v > _SAT else "n/a",
            "note": "Required > SAT" if v > _SAT else "Below SAT",
        }
    )
    compliance.append(
        {
            "name": "Congressional Notification",
            "status": "required" if v > _CONGRESS else "n/a",
            "note": f"Required > ${_CONGRESS:,} - email grantfax@hhs.gov"
            if v > _CONGRESS
            else f"Below ${_CONGRESS:,}",
        }
    )
    compliance.append(
        {
            "name": "Certified Cost/Pricing Data (TINA)",
            "status": "required" if v > _TINA else "n/a",
            "note": f"Required > ${_TINA:,} (with exceptions)"
            if v > _TINA
            else f"Below ${_TINA:,}",
        }
    )

    if is_it:
        compliance.append(
            {
                "name": "Section 508 ICT Accessibility",
                "status": "required",
                "note": "Required for IT acquisitions",
            }
        )
        compliance.append(
            {
                "name": "IT Security & Privacy Language",
                "status": "required",
                "note": "HHSAM Part 339.105",
            }
        )

    if is_hs:
        compliance.append(
            {
                "name": "Human Subjects Protection (45 CFR 46)",
                "status": "required",
                "note": "HHSAR 370.3",
            }
        )

    if is_services:
        compliance.append(
            {
                "name": "Severable Services <= 1yr/period",
                "status": "required",
                "note": "FAR 37.106(b), 32.703-3(b)",
            }
        )

    # --- Competition Rules ---
    competition = ""
    if m == "micro":
        competition = "Single quote acceptable. Government purchase card preferred."
    elif m == "sap":
        if v > _SYNOPSIS:
            competition = "Maximum practicable competition. Minimum 3 sources if practicable. Synopsis on SAM.gov."
        else:
            competition = "Reasonable competition. Minimum 3 sources if practicable."
    elif m == "negotiated":
        competition = "Full and open competition required (FAR Part 6). Synopsis, evaluation factors, source selection."
    elif m == "fss":
        if v > _SAT:
            competition = "eBuy posting OR RFQ to enough contractors for 3 quotes. Price reduction attempt required."
        else:
            competition = "Consider quotes from at least 3 schedule contractors."
    elif m == "bpa-est":
        if v > _SAT:
            competition = "eBuy posting to ALL schedule holders OR 3-quote effort. Document award decision."
        else:
            competition = "Seek quotes from at least 3 schedule holders."
    elif m == "bpa-call":
        if v > _SAT:
            competition = "RFQ to all BPA holders OR limited sources justification. Fair opportunity required."
        else:
            competition = "Fair opportunity to all BPA holders > MPT, or justification."
    elif m == "idiq":
        competition = "Full and open competition for parent contract. Multiple award preference unless exception (FAR 16.504)."
    elif m == "idiq-order":
        if v > _IDIQ_ENH:
            competition = (
                "Fair opportunity to all IDIQ holders. Clear requirements, "
                "evaluation factors with relative importance, post-award notifications/debriefings."
            )
        elif v > _SAT:
            competition = "Fair opportunity. Provide fair notice, issue solicitation/RFQ, document award basis."
        else:
            competition = "Fair opportunity. May place without further solicitation if fair consideration documented."
    elif m == "sole":
        if v <= _SAT:
            competition = (
                "Simplified sole source — FAR 13.106-1(b). CO determines competition "
                "is not practicable. Legal basis: FAR 6.302-1 (Only One Responsible Source) / "
                "41 U.S.C. 3304(a)(1). Simplified justification required, not full FAR Part 6 J&A."
            )
        else:
            competition = (
                "Exception to competition — FAR 6.302 authority required. "
                "Full J&A per FAR 6.303, approval per FAR 6.304."
            )

    # Enhanced IDIQ
    if m == "idiq-order" and v > _IDIQ_ENH:
        competition += (
            f" ENHANCED: Detailed evaluation factors + relative importance "
            f"+ post-award notification + debriefing (> ${_IDIQ_ENH:,})."
        )

    # 8(a) override — applies on top of the method-based competition rules
    if is_8a:
        _8a_ceiling = (
            _threshold("8a_sole_source_manufacturing_ceiling")
            if is_mfg
            else _threshold("8a_sole_source_services_ceiling")
        )
        _8a_type = "manufacturing" if is_mfg else "services"
        if v <= _8a_ceiling:
            competition = (
                f"SBA 8(a) sole source authorized — FAR 19.805-1. "
                f"{_8a_type.title()} ceiling: ${_8a_ceiling:,}. "
                f"Requires SBA acceptance and offering letter."
            )
        else:
            competition = (
                f"SBA 8(a) competitive required — value ${v:,.0f} exceeds "
                f"{_8a_type} sole source ceiling ${_8a_ceiling:,}. "
                f"FAR 19.805-1(a)(2)."
            )

    # --- PMR Checklist ---
    if m == "sap" or (m == "negotiated" and v <= _SAT):
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
    if v > _SPE_JA:
        time_min += 6
        time_max += 8
    elif v > _HCA:
        time_min += 4
        time_max += 6
    elif v > _AP_OA:
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
    if v > _SAT:
        approvals.append({"type": "Acquisition Plan", "authority": _ap_approval(v)})
    if needs_ja:
        approvals.append({"type": "J&A", "authority": _ja_approval(v)})
    if needs_df:
        approvals.append(
            {"type": "D&F", "authority": "One level above CO" if is_loe else "CO"}
        )
    if v > _TINA:
        approvals.append(
            {
                "type": "TINA / Cost Data",
                "authority": "Certified cost or pricing data required",
            }
        )

    return {
        "errors": errors,
        "warnings": warnings,
        "documents_required": docs,
        "compliance_items": compliance,
        "competition_rules": competition,
        "thresholds_triggered": triggered,
        "thresholds_not_triggered": not_triggered,
        "timeline_estimate": {"min_weeks": time_min, "max_weeks": time_max},
        "risk_allocation": {
            "contractor_risk_pct": risk_pct,
            "category": t_obj["category"],
        },
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

    Splits the query into terms and scores each entry by how many terms match.
    Returns entries sorted by relevance (most matching terms first).

    Args:
        keyword: Search term(s) (case-insensitive, space-separated).
        parts: Optional list of FAR part numbers to restrict search.

    Returns:
        List of matching FAR entries, sorted by relevance.
    """
    terms = keyword.lower().split()
    if not terms:
        return []
    scored = []
    for entry in _FAR_DATABASE:
        if parts and entry.get("part") not in parts:
            continue
        searchable = " ".join(
            [
                entry.get("title", ""),
                entry.get("summary", ""),
                entry.get("section", ""),
                " ".join(entry.get("keywords", [])),
            ]
        ).lower()
        score = sum(1 for t in terms if t in searchable)
        # Bonus for keyword exact matches
        entry_kw = [k.lower() for k in entry.get("keywords", [])]
        score += sum(2 for t in terms if t in entry_kw)
        if score > 0:
            scored.append((score, entry))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [entry for _, entry in scored]


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

    recommendations = _VEHICLES_DATA.get("selection_guide", {}).get(
        "recommendations", {}
    )
    vehicles = _VEHICLES_DATA.get("vehicles", {})

    suggested: list[dict] = []

    if is_it and is_services:
        key = "it_services_complex"
        suggested.append(
            {
                "recommendation": recommendations.get(key, ""),
                "vehicle": "nitaac",
                "detail": vehicles.get("nitaac", {}),
            }
        )
    elif is_it:
        key = "it_commodities"
        suggested.append(
            {
                "recommendation": recommendations.get(key, ""),
                "vehicle": "gsa_schedules",
                "detail": vehicles.get("gsa_schedules", {}),
            }
        )
    elif is_services:
        key = "professional_services"
        suggested.append(
            {
                "recommendation": recommendations.get(key, ""),
                "vehicle": "gsa_schedules",
                "detail": vehicles.get("gsa_schedules", {}),
            }
        )
    else:
        key = "unique_requirements"
        suggested.append(
            {
                "recommendation": recommendations.get(key, "Full and open competition"),
                "vehicle": "open_competition",
                "detail": {
                    "name": "Full and Open Competition",
                    "description": "Standard FAR Part 15 process",
                },
            }
        )

    return {
        "suggested_vehicles": suggested,
        "decision_factors": _VEHICLES_DATA.get("selection_guide", {}).get(
            "decision_factors", []
        ),
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
        return suggest_vehicle(
            flags={
                "is_it": params.get("is_it", False),
                "is_services": params.get("is_services", False),
                "is_small_business": params.get("is_small_business", False),
            }
        )

    return {
        "error": f"Unknown operation: {op}. Valid: query, list_methods, list_types, list_thresholds, search_far, suggest_vehicle"
    }
