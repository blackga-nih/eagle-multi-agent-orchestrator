"""
Contract Requirements Matrix — Strands @tool

Deterministic FAR-grounded scoring engine for acquisition vehicle/method
recommendations, document checklists, compliance, and thresholds.

Ported from docs/contract-requirements-matrix.html (JavaScript).
"""

from __future__ import annotations

from strands import tool


# ============================================================
# DATA STRUCTURES (ported from HTML JS)
# ============================================================

METHODS = [
    {"id": "micro",      "label": "Micro-Purchase",            "sub": "FAR 13.2 — up to $15K",          "far": "13.2"},
    {"id": "sap",        "label": "Simplified (SAP)",          "sub": "FAR 13 — $15K to $350K",         "far": "13"},
    {"id": "negotiated", "label": "Negotiated",                "sub": "FAR 15 — above $350K",           "far": "15"},
    {"id": "fss",        "label": "FSS Direct Order",          "sub": "FAR 8.4 — Schedule pricing",     "far": "8.4"},
    {"id": "bpa-est",    "label": "BPA Establishment",         "sub": "FAR 8.4 — Blanket agreement",    "far": "8.4"},
    {"id": "bpa-call",   "label": "BPA Call Order",            "sub": "FAR 8.4 — Order under BPA",      "far": "8.4"},
    {"id": "idiq",       "label": "IDIQ Parent Award",         "sub": "FAR 16.5 — Indefinite delivery", "far": "16.5"},
    {"id": "idiq-order", "label": "IDIQ Task/Delivery Order",  "sub": "FAR 16.5 — Order under IDIQ",    "far": "16.5"},
    {"id": "sole",       "label": "Sole Source / J&A",         "sub": "FAR 6.3 — Limited competition",  "far": "6.3"},
]

TYPES = [
    {"id": "ffp",    "label": "Firm-Fixed-Price (FFP)",        "risk": 95, "category": "fp"},
    {"id": "fp-epa", "label": "FP w/ Economic Price Adj",      "risk": 80, "category": "fp"},
    {"id": "fpi",    "label": "Fixed-Price Incentive (FPIF)",   "risk": 65, "category": "fp"},
    {"id": "fp-af",  "label": "FP w/ Award Fee (FP/AF)",       "risk": 60, "category": "fp",     "feeCap": "Award fee variable"},
    {"id": "cpff",   "label": "Cost-Plus-Fixed-Fee (CPFF)",     "risk": 25, "category": "cr",     "feeCap": "10% est. cost (R&D: 15%)"},
    {"id": "cpif",   "label": "Cost-Plus-Incentive-Fee (CPIF)", "risk": 35, "category": "cr",     "feeCap": "Sharing ratio applies"},
    {"id": "cpaf",   "label": "Cost-Plus-Award-Fee (CPAF)",     "risk": 20, "category": "cr",     "feeCap": "No rollover allowed"},
    {"id": "tm",     "label": "Time & Materials (T&M)",         "risk": 15, "category": "loe",    "prereqs": ["D&F required"]},
    {"id": "lh",     "label": "Labor-Hour (LH)",                "risk": 15, "category": "loe",    "prereqs": ["D&F required"]},
    {"id": "letter", "label": "Letter Contract (Emergency)",    "risk": 5,  "category": "letter", "feeCap": "Definitize ≤180 days/40%", "prereqs": ["HCA determination required"]},
]

THRESHOLDS = [
    {"value": 15_000,       "label": "$15K MPT",       "short": "$15K"},
    {"value": 25_000,       "label": "$25K Synopsis",   "short": "$25K"},
    {"value": 150_000,      "label": "$150K VETS 4212", "short": "$150K"},
    {"value": 350_000,      "label": "$350K SAT",       "short": "$350K"},
    {"value": 750_000,      "label": "$750K SubK",      "short": "$750K"},
    {"value": 900_000,      "label": "$900K J&A",       "short": "$900K"},
    {"value": 2_500_000,    "label": "$2.5M TINA",      "short": "$2.5M"},
    {"value": 4_500_000,    "label": "$4.5M Congress",  "short": "$4.5M"},
    {"value": 7_500_000,    "label": "$7.5M IDIQ Enh",  "short": "$7.5M"},
    {"value": 20_000_000,   "label": "$20M AP",         "short": "$20M"},
    {"value": 50_000_000,   "label": "$50M HCA",        "short": "$50M"},
    {"value": 90_000_000,   "label": "$90M SPE J&A",    "short": "$90M"},
    {"value": 100_000_000,  "label": "$100M SPE",       "short": "$100M"},
    {"value": 150_000_000,  "label": "$150M OAP",       "short": "$150M"},
]

# Scoring weights: factor_key → { type_id → { yes, no, partial } }
FACTOR_WEIGHTS: dict[str, dict[str, dict[str, int]]] = {
    "commerciality":       {"ffp": {"yes": 4, "no": -2, "partial": 1}, "fp-epa": {"yes": 2, "no": -1, "partial": 0}, "fpi": {"yes": 0, "no": 1, "partial": 0}, "fp-af": {"yes": -1, "no": 1, "partial": 0}, "cpff": {"yes": -4, "no": 2, "partial": -1}, "cpif": {"yes": -4, "no": 2, "partial": -1}, "cpaf": {"yes": -3, "no": 1, "partial": -1}, "tm": {"yes": -2, "no": 0, "partial": -1}, "lh": {"yes": -2, "no": 0, "partial": -1}, "letter": {"yes": -1, "no": 0, "partial": 0}},
    "priceCompetition":    {"ffp": {"yes": 3, "no": -2, "partial": 1}, "fp-epa": {"yes": 1, "no": 0, "partial": 0}, "fpi": {"yes": -1, "no": 2, "partial": 0}, "fp-af": {"yes": -1, "no": 1, "partial": 0}, "cpff": {"yes": -2, "no": 1, "partial": -1}, "cpif": {"yes": -2, "no": 1, "partial": -1}, "cpaf": {"yes": -2, "no": 0, "partial": -1}, "tm": {"yes": -1, "no": 1, "partial": 0}, "lh": {"yes": -1, "no": 1, "partial": 0}, "letter": {"yes": -1, "no": 0, "partial": 0}},
    "priceAnalysis":       {"ffp": {"yes": 2, "no": -1, "partial": 1}, "fp-epa": {"yes": 1, "no": 0, "partial": 0}, "fpi": {"yes": 0, "no": 0, "partial": 0}, "fp-af": {"yes": 0, "no": 0, "partial": 0}, "cpff": {"yes": -1, "no": 1, "partial": 0}, "cpif": {"yes": -1, "no": 1, "partial": 0}, "cpaf": {"yes": -1, "no": 0, "partial": 0}, "tm": {"yes": 0, "no": 0, "partial": 0}, "lh": {"yes": 0, "no": 0, "partial": 0}, "letter": {"yes": 0, "no": 0, "partial": 0}},
    "costAnalysis":        {"ffp": {"yes": 0, "no": 0, "partial": 0}, "fp-epa": {"yes": 0, "no": 0, "partial": 0}, "fpi": {"yes": 1, "no": 0, "partial": 0}, "fp-af": {"yes": 1, "no": 0, "partial": 0}, "cpff": {"yes": 2, "no": -2, "partial": 0}, "cpif": {"yes": 2, "no": -2, "partial": 0}, "cpaf": {"yes": 1, "no": -1, "partial": 0}, "tm": {"yes": 1, "no": 0, "partial": 0}, "lh": {"yes": 1, "no": 0, "partial": 0}, "letter": {"yes": 0, "no": 0, "partial": 0}},
    "typeComplexity":      {"ffp": {"yes": -3, "no": 2, "partial": -1}, "fp-epa": {"yes": -1, "no": 1, "partial": 0}, "fpi": {"yes": 1, "no": 1, "partial": 1}, "fp-af": {"yes": 1, "no": 0, "partial": 0}, "cpff": {"yes": 3, "no": -2, "partial": 1}, "cpif": {"yes": 3, "no": -2, "partial": 1}, "cpaf": {"yes": 2, "no": -1, "partial": 1}, "tm": {"yes": 1, "no": -1, "partial": 0}, "lh": {"yes": 1, "no": -1, "partial": 0}, "letter": {"yes": 0, "no": 0, "partial": 0}},
    "combining":           {"ffp": {"yes": 0, "no": 0, "partial": 0}, "fp-epa": {"yes": 0, "no": 0, "partial": 0}, "fpi": {"yes": 1, "no": 0, "partial": 0}, "fp-af": {"yes": 1, "no": 0, "partial": 0}, "cpff": {"yes": 1, "no": 0, "partial": 0}, "cpif": {"yes": 1, "no": 0, "partial": 0}, "cpaf": {"yes": 0, "no": 0, "partial": 0}, "tm": {"yes": 0, "no": 0, "partial": 0}, "lh": {"yes": 0, "no": 0, "partial": 0}, "letter": {"yes": 0, "no": 0, "partial": 0}},
    "urgency":             {"ffp": {"yes": -2, "no": 1, "partial": -1}, "fp-epa": {"yes": -1, "no": 0, "partial": 0}, "fpi": {"yes": -1, "no": 0, "partial": 0}, "fp-af": {"yes": -1, "no": 0, "partial": 0}, "cpff": {"yes": -2, "no": 0, "partial": -1}, "cpif": {"yes": -2, "no": 0, "partial": -1}, "cpaf": {"yes": -2, "no": 0, "partial": -1}, "tm": {"yes": 2, "no": -1, "partial": 1}, "lh": {"yes": 2, "no": -1, "partial": 1}, "letter": {"yes": 5, "no": -2, "partial": 2}},
    "period":              {"ffp": {"yes": -1, "no": 1, "partial": 0}, "fp-epa": {"yes": 3, "no": -1, "partial": 1}, "fpi": {"yes": 0, "no": 0, "partial": 0}, "fp-af": {"yes": 0, "no": 0, "partial": 0}, "cpff": {"yes": 0, "no": 0, "partial": 0}, "cpif": {"yes": 0, "no": 0, "partial": 0}, "cpaf": {"yes": 0, "no": 0, "partial": 0}, "tm": {"yes": -1, "no": 0, "partial": 0}, "lh": {"yes": -1, "no": 0, "partial": 0}, "letter": {"yes": -2, "no": 0, "partial": -1}},
    "capabilityUncertain": {"ffp": {"yes": -2, "no": 2, "partial": -1}, "fp-epa": {"yes": -1, "no": 1, "partial": 0}, "fpi": {"yes": 2, "no": -1, "partial": 1}, "fp-af": {"yes": 1, "no": -1, "partial": 0}, "cpff": {"yes": 1, "no": -1, "partial": 0}, "cpif": {"yes": 2, "no": -1, "partial": 1}, "cpaf": {"yes": 1, "no": -1, "partial": 0}, "tm": {"yes": 0, "no": 0, "partial": 0}, "lh": {"yes": 0, "no": 0, "partial": 0}, "letter": {"yes": 0, "no": 0, "partial": 0}},
    "accountingSystem":    {"ffp": {"yes": 0, "no": 0, "partial": 0}, "fp-epa": {"yes": 0, "no": 0, "partial": 0}, "fpi": {"yes": 0, "no": 2, "partial": 1}, "fp-af": {"yes": 0, "no": 1, "partial": 0}, "cpff": {"yes": 2, "no": -5, "partial": -1}, "cpif": {"yes": 2, "no": -5, "partial": -1}, "cpaf": {"yes": 1, "no": -4, "partial": -1}, "tm": {"yes": 0, "no": 0, "partial": 0}, "lh": {"yes": 0, "no": 0, "partial": 0}, "letter": {"yes": 0, "no": 0, "partial": 0}},
    "concurrent":          {"ffp": {"yes": 1, "no": 0, "partial": 0}, "fp-epa": {"yes": 1, "no": 0, "partial": 0}, "fpi": {"yes": 1, "no": 0, "partial": 0}, "fp-af": {"yes": 0, "no": 0, "partial": 0}, "cpff": {"yes": -1, "no": 0, "partial": 0}, "cpif": {"yes": -1, "no": 0, "partial": 0}, "cpaf": {"yes": -1, "no": 0, "partial": 0}, "tm": {"yes": 0, "no": 0, "partial": 0}, "lh": {"yes": 0, "no": 0, "partial": 0}, "letter": {"yes": 0, "no": 0, "partial": 0}},
    "subcontracting":      {"ffp": {"yes": 0, "no": 0, "partial": 0}, "fp-epa": {"yes": 0, "no": 0, "partial": 0}, "fpi": {"yes": 1, "no": 0, "partial": 0}, "fp-af": {"yes": 0, "no": 0, "partial": 0}, "cpff": {"yes": 0, "no": 0, "partial": 0}, "cpif": {"yes": 0, "no": 0, "partial": 0}, "cpaf": {"yes": 0, "no": 0, "partial": 0}, "tm": {"yes": 0, "no": 0, "partial": 0}, "lh": {"yes": 0, "no": 0, "partial": 0}, "letter": {"yes": 0, "no": 0, "partial": 0}},
    "history":             {"ffp": {"yes": 3, "no": -2, "partial": 1}, "fp-epa": {"yes": 1, "no": 0, "partial": 0}, "fpi": {"yes": 1, "no": -1, "partial": 0}, "fp-af": {"yes": 0, "no": 0, "partial": 0}, "cpff": {"yes": -1, "no": 1, "partial": 0}, "cpif": {"yes": -1, "no": 1, "partial": 0}, "cpaf": {"yes": -1, "no": 0, "partial": 0}, "tm": {"yes": -1, "no": 0, "partial": 0}, "lh": {"yes": -1, "no": 0, "partial": 0}, "letter": {"yes": -2, "no": 0, "partial": -1}},
}

FACTOR_REASON_TEXT: dict[str, dict[str, str]] = {
    "commerciality":       {"yes": "Commercial item → fixed-price required (FAR 12.207)",         "no": "Non-commercial → CR types eligible"},
    "priceCompetition":    {"yes": "Competition establishes fair price → supports FFP",            "no": "No competition → cost analysis needed"},
    "priceAnalysis":       {"yes": "Price analysis feasible → FP types appropriate",               "no": "Price analysis insufficient → CR more appropriate"},
    "costAnalysis":        {"yes": "Cost data available → CR types administrable",                 "no": "No cost data → limits CR justification"},
    "typeComplexity":      {"yes": "R&D/complex → CR uncertainty justified (FAR 16.301-2)",        "no": "Well-defined requirements → fixed-price appropriate"},
    "urgency":             {"yes": "Urgency → T&M/Letter Contract for immediate start",            "no": "No urgency → proper type selection possible"},
    "period":              {"yes": "Long period → economic adjustments warranted (FP-EPA)",        "no": "Short period → economic adjustments not needed"},
    "capabilityUncertain": {"yes": "Capability uncertain → incentives motivate performance",       "no": "Established capability → firm pricing appropriate"},
    "accountingSystem":    {"yes": "Adequate accounting system → CR types eligible (FAR 16.301-3)", "no": "Inadequate accounting → CR types PROHIBITED (FAR 16.301-3)"},
    "concurrent":          {"yes": "High concurrent risk → FP limits cumulative exposure",         "no": "Low concurrent risk → no concern"},
    "history":             {"yes": "Established history → prior data supports firm pricing",        "no": "No history → uncertainty favors CR"},
    "combining":           {"yes": "Hybrid CLINs possible → mixed types acceptable (FAR 16.102)",  "no": ""},
    "subcontracting":      {"yes": "Extensive subcontracting → incentive type aligns primes/subs", "no": ""},
}


# ============================================================
# CORE LOGIC
# ============================================================

def _find_type(type_id: str) -> dict | None:
    return next((t for t in TYPES if t["id"] == type_id), None)


def _find_method(method_id: str) -> dict | None:
    return next((m for m in METHODS if m["id"] == method_id), None)


def _is_type_disabled(method: str, type_id: str) -> bool:
    if method == "micro" and type_id != "ffp":
        return True
    if method in ("fss", "bpa-call", "bpa-est"):
        if type_id in ("cpff", "cpif", "cpaf", "letter"):
            return True
    if type_id == "letter" and method not in ("negotiated", "sole", "idiq"):
        return True
    if type_id == "fp-af" and method in ("micro", "sap"):
        return True
    return False


def _ap_approval(v: int) -> str:
    if v > 150_000_000:
        return "HHS/OAP approval required (> $150M)"
    if v > 50_000_000:
        return "HCA-NIH approval required ($50M–$150M)"
    if v > 20_000_000:
        return "OA Director approval by HCA ($20M–$50M)"
    return "One level above CO (SAT–$20M)"


def _ja_approval(v: int) -> str:
    if v > 90_000_000:
        return "SPE through HHS/OAP (> $90M) — FAR 6.304(a)(4)"
    if v > 20_000_000:
        return "HCA + additional reviews ($20M–$90M) — FAR 6.304(a)(3)"
    if v > 900_000:
        return "HCA + NIH Competition Advocate ($900K–$20M) — FAR 6.304(a)(2)"
    return "CO approval (≤ $900K) — FAR 6.304(a)(1)"


def get_requirements(
    dollar_value: int,
    method: str = "sap",
    contract_type: str = "ffp",
    is_it: bool = False,
    is_services: bool = True,
    is_small_business: bool = False,
    is_rd: bool = False,
    is_human_subjects: bool = False,
    is_animal_welfare: bool = False,
    is_foreign: bool = False,
    is_conference: bool = False,
) -> dict:
    """Core requirements engine — ported from getRequirements() in HTML."""
    v = dollar_value
    m = method
    t = contract_type
    t_obj = _find_type(t) or TYPES[0]
    is_cr = t_obj["category"] == "cr"
    is_loe = t_obj["category"] == "loe"
    _ = t_obj["category"] == "fp"  # reserved for future use

    warnings: list[str] = []
    errors: list[str] = []

    # Warnings
    if is_cr:
        warnings.append("Cost-reimbursement requires written AP approval, adequate contractor accounting system, and designated COR (FAR 16.301).")
        if is_rd:
            warnings.append("CPFF fee cap for R&D: 15% of estimated cost (FAR 16.304).")
    if is_loe:
        warnings.append("T&M/LH is LEAST PREFERRED. CO must prepare D&F that no other contract type is suitable (FAR 16.601).")
    if t == "cpaf":
        warnings.append("CPAF requires approved award-fee plan before award. Rollover of unearned fee is PROHIBITED (FAR 16.402-2).")
    if t == "letter":
        warnings.append("Letter Contract: Must definitize within 180 days OR before 40% of work is complete. 50% government liability cap applies.")
    if m == "idiq-order" and v > 10_000_000:
        warnings.append("IDIQ task order protests to GAO: Civilian agencies — protestable if order >$10M (FAR 16.508).")

    # Errors (incompatible combos)
    if m == "micro" and v > 15_000:
        errors.append("Micro-purchase threshold is $15,000 (HHS). Value exceeds MPT.")
    if m == "sap" and v > 350_000:
        errors.append("SAP threshold is $350,000 (SAT). Value exceeds SAT — use Negotiated (FAR 15).")

    # Documents
    docs: list[dict] = []
    docs.append({"name": "Purchase Request", "required": True, "note": "FAR 4.803(a)(1)"})

    if m != "micro":
        name = "SOW / PWS" if is_services else "Statement of Need (SON)"
        note = "Performance-based with QASP (FAR 37.6)" if is_services else "Product specifications"
        docs.append({"name": name, "required": True, "note": note})
    else:
        docs.append({"name": "SOW / PWS", "required": False, "note": "Not required for micro-purchase"})

    docs.append({"name": "IGCE", "required": m != "micro",
                 "note": "Detailed breakdown required (HHSAM 307.105-71)" if v > 350_000 else "Sufficient detail/breakdown"})

    if v > 350_000:
        docs.append({"name": "Market Research Report", "required": True, "note": "HHS template required (HHSAM 310.000)"})
    elif v > 15_000:
        docs.append({"name": "Market Research", "required": True, "note": "Documented justification (less formal)"})
    else:
        docs.append({"name": "Market Research", "required": False, "note": "Not required for micro-purchase"})

    if v > 350_000:
        docs.append({"name": "Acquisition Plan", "required": True, "note": _ap_approval(v)})
    else:
        docs.append({"name": "Acquisition Plan", "required": False, "note": "Not required below SAT ($350K)"})

    needs_ja = m == "sole" or (m == "fss" and v > 350_000) or (m == "bpa-call" and v > 350_000)
    docs.append({"name": "J&A / Justification", "required": needs_ja,
                 "note": _ja_approval(v) if needs_ja else "Only if sole source / limited competition"})

    needs_df = is_loe or (is_cr and v > 350_000) or t in ("fpi", "cpaf")
    docs.append({"name": "D&F (Determination & Findings)", "required": needs_df,
                 "note": "Required: no other type suitable (FAR 16.601)" if is_loe else "Required for cost-reimbursement" if is_cr else "Required for incentive/award-fee"})

    needs_ssp = m == "negotiated" and v > 350_000
    docs.append({"name": "Source Selection Plan", "required": needs_ssp,
                 "note": "Evaluation factors with relative importance" if needs_ssp else "N/A for this method"})

    needs_subk = v > 750_000 and not is_small_business
    docs.append({"name": "Subcontracting Plan", "required": needs_subk,
                 "note": "Required for non-SB > $750K (FAR 19.705)" if needs_subk else ("Exempt — small business awardee" if is_small_business else "Below $750K threshold")})

    needs_qasp = is_services and m != "micro"
    docs.append({"name": "QASP", "required": needs_qasp,
                 "note": "Required for performance-based services (FAR 46)" if needs_qasp else "Products / micro-purchase"})

    docs.append({"name": "HHS-653 Small Business Review", "required": v > 15_000,
                 "note": "Required > MPT (AA 2023-02 Amendment 3)" if v > 15_000 else "Below MPT"})

    if is_it:
        docs.append({"name": "IT Security & Privacy Certification", "required": True, "note": "HHSAM 339.101(c)(1)"})
        docs.append({"name": "Section 508 ICT Evaluation", "required": v > 15_000, "note": "Required for IT > MPT"})

    if is_human_subjects:
        docs.append({"name": "Human Subjects Provisions", "required": True, "note": "HHSAR 370.3, 45 CFR 46"})

    if v > 150_000 and m != "micro":
        docs.append({"name": "VETS 4212 Compliance", "required": True, "note": "FAR 22.1312 — contracts ≥$150K"})

    if is_animal_welfare:
        docs.append({"name": "Animal Welfare Assurance", "required": True, "note": "HHSAR 370.4 — PHS Policy + IACUC"})

    if is_foreign:
        docs.append({"name": "Foreign Acquisition Clearance", "required": True, "note": "NIH Policy 6325.1"})
        docs.append({"name": "Buy American / TAA Compliance", "required": True, "note": "FAR Part 25"})

    if is_conference:
        docs.append({"name": "Conference Approval (NIH)", "required": True, "note": "NIH Efficient Spending Policy 2015"})

    # Thresholds
    triggered = [th for th in THRESHOLDS if v >= th["value"]]
    not_triggered = [th for th in THRESHOLDS if v < th["value"]]

    # Compliance
    compliance: list[dict] = []
    compliance.append({"name": "Section 889 Compliance", "status": "required", "note": "FAR 52.204-25 — all solicitations/contracts"})
    compliance.append({"name": "BAA/TAA Checklist", "status": "required" if m != "micro" else "conditional", "note": "HHSAM 325.102-70"})
    compliance.append({"name": "SAM.gov Synopsis", "status": "required" if v > 25_000 else "na", "note": "Required > $25K (FAR 5.101)" if v > 25_000 else "Below $25K"})
    compliance.append({"name": "CPARS Evaluation", "status": "required" if v > 350_000 else "na", "note": "Required > SAT" if v > 350_000 else "Below SAT"})
    compliance.append({"name": "Congressional Notification", "status": "required" if v > 4_500_000 else "na", "note": "Required > $4.5M" if v > 4_500_000 else "Below $4.5M"})
    compliance.append({"name": "Certified Cost/Pricing Data (TINA)", "status": "required" if v > 2_500_000 else "na", "note": "Required > $2.5M (with exceptions)" if v > 2_500_000 else "Below $2.5M"})

    # Competition
    competition_map = {
        "micro": "Single quote acceptable. Government purchase card preferred.",
        "sap": ("Maximum practicable competition. Minimum 3 sources if practicable. Synopsis on SAM.gov." if v > 25_000
                else "Reasonable competition. Minimum 3 sources if practicable."),
        "negotiated": "Full and open competition required (FAR Part 6). Synopsis, evaluation factors, source selection.",
        "fss": ("eBuy posting OR RFQ to enough contractors for 3 quotes." if v > 350_000
                else "Consider quotes from at least 3 schedule contractors."),
        "sole": "Exception to competition — FAR 6.302 authority required. Full J&A with CO certification.",
    }
    competition = competition_map.get(m, "Fair opportunity required.")

    # Timeline (weeks)
    timeline_map = {
        "micro": (0, 1), "sap": (2, 6), "negotiated": (12, 36), "fss": (2, 8),
        "bpa-est": (4, 12), "bpa-call": (1, 4), "idiq": (16, 52),
        "idiq-order": (2, 12), "sole": (4, 16),
    }
    time_min, time_max = timeline_map.get(m, (1, 5))
    if v > 90_000_000:
        time_min += 6
        time_max += 8
    elif v > 50_000_000:
        time_min += 4
        time_max += 6
    elif v > 20_000_000:
        time_min += 2
        time_max += 4

    # PMR
    pmr_map = {
        "micro": "Micro-Purchase — Minimal file documentation",
        "sap": "HHS PMR SAP Checklist",
        "negotiated": "HHS PMR Negotiated + Common Requirements",
        "fss": "HHS PMR FSS Order Checklist",
        "bpa-est": "HHS PMR BPA Checklist", "bpa-call": "HHS PMR BPA Checklist",
        "idiq": "HHS PMR IDIQ Checklist", "idiq-order": "HHS PMR IDIQ Checklist",
        "sole": "HHS PMR SAP or Negotiated + J&A Requirements",
    }
    pmr = pmr_map.get(m, "HHS PMR Common Requirements")

    return {
        "required_documents": [d for d in docs if d["required"]],
        "optional_documents": [d for d in docs if not d["required"]],
        "thresholds_triggered": [th["label"] for th in triggered],
        "thresholds_not_triggered": [th["label"] for th in not_triggered],
        "compliance_items": compliance,
        "competition": competition,
        "timeline_weeks": {"min": time_min, "max": time_max},
        "risk_pct": t_obj["risk"],
        "pmr_checklist": pmr,
        "approval_chain": _ap_approval(v) if v > 350_000 else "Not required below SAT",
        "warnings": warnings,
        "errors": errors,
    }


def compute_type_scores(factor_answers: dict[str, str]) -> list[dict]:
    """Score contract types based on FAR 16.104 factor answers.

    Args:
        factor_answers: e.g. {"commerciality": "yes", "priceCompetition": "no"}

    Returns:
        Ranked list of types with scores and top reasons.
    """
    scores: dict[str, int] = {t["id"]: 0 for t in TYPES}

    for factor_key, answer in factor_answers.items():
        if factor_key not in FACTOR_WEIGHTS:
            continue
        fw = FACTOR_WEIGHTS[factor_key]
        for type_id, weights in fw.items():
            scores[type_id] += weights.get(answer, 0)

    # Build ranked results with reasons
    results = []
    for t in TYPES:
        reasons = []
        for factor_key, answer in factor_answers.items():
            if factor_key not in FACTOR_WEIGHTS:
                continue
            fw = FACTOR_WEIGHTS[factor_key]
            if t["id"] not in fw:
                continue
            contribution = fw[t["id"]].get(answer, 0)
            if abs(contribution) >= 2:
                text = FACTOR_REASON_TEXT.get(factor_key, {}).get(answer, "")
                if text:
                    reasons.append({"text": text, "score": contribution})

        reasons.sort(key=lambda r: abs(r["score"]), reverse=True)
        results.append({
            "id": t["id"],
            "label": t["label"],
            "score": scores[t["id"]],
            "category": t["category"],
            "risk": t["risk"],
            "fee_cap": t.get("feeCap"),
            "reasons": reasons[:4],
        })

    results.sort(key=lambda r: r["score"], reverse=True)
    return results


def score_methods(
    dollar_value: int,
    is_it: bool = False,
    is_services: bool = True,
    is_small_business: bool = False,
) -> list[dict]:
    """Score and rank acquisition methods with reasoning."""
    v = dollar_value
    candidates = []

    # Micro-purchase
    if v <= 15_000:
        candidates.append({
            "id": "micro", "label": "Micro-Purchase",
            "score": 95,
            "pros": ["Fastest — same day to 1 week", "Single quote acceptable", "Purchase card preferred"],
            "cons": ["Limited to $15K", "No competition required"],
        })

    # GSA Schedule
    if is_it or is_services:
        score = 70
        pros = ["Pre-competed pricing", "Streamlined ordering process"]
        cons = ["Limited to schedule scope"]
        if v < 350_000:
            score += 15
            pros.append("Below SAT — simplified ordering")
        if is_it:
            score += 10
            pros.append("IT services commonly available on schedule")
        candidates.append({"id": "fss", "label": "GSA Schedule (e.g., CIO-SP3, STARS III)", "score": score, "pros": pros, "cons": cons})

    # NITAAC — IT specific
    if is_it and v > 50_000:
        score = 65
        pros = ["NIH-managed GWAC for IT", "Pre-competed vendors"]
        cons = ["IT-only scope"]
        if v > 350_000:
            score += 10
            pros.append("Strong for large IT services")
        candidates.append({"id": "idiq-order", "label": "NITAAC (CIO-SP3 Small Business, VETS 2)", "score": score, "pros": pros, "cons": cons})

    # Simplified (SAP)
    if 15_000 < v <= 350_000:
        score = 75
        candidates.append({
            "id": "sap", "label": "Simplified Acquisition (SAP)",
            "score": score,
            "pros": ["Streamlined procedures", "Faster than full FAR 15", "3 quotes minimum"],
            "cons": ["Limited to $350K SAT"],
        })

    # Negotiated (FAR Part 15) — always available above SAT
    if v > 350_000:
        score = 50
        pros = ["Maximum flexibility", "Full and open competition"]
        cons = ["60-180 day timeline", "Full documentation required"]
        if not is_it and not is_services:
            score += 10  # supplies often need open market
        candidates.append({"id": "negotiated", "label": "Negotiated (FAR Part 15)", "score": score, "pros": pros, "cons": cons})

    # Sole source
    if v > 15_000:
        score = 20
        candidates.append({
            "id": "sole", "label": "Sole Source / J&A",
            "score": score,
            "pros": ["Only option when single source exists"],
            "cons": ["Requires J&A with FAR 6.302 authority", "Approval escalates with value", "Protest risk"],
        })

    # Small business set-aside consideration
    if is_small_business and v > 15_000:
        for c in candidates:
            if c["id"] in ("fss", "sap", "negotiated"):
                c["pros"].append("Small business set-aside eligible")
                c["score"] += 5

    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates


# ============================================================
# STRANDS @tool
# ============================================================

@tool
def query_contract_matrix(
    dollar_value: int,
    method: str = "",
    contract_type: str = "",
    is_it: bool = False,
    is_services: bool = True,
    is_small_business: bool = False,
    is_rd: bool = False,
    factors: str = "",
) -> dict:
    """Query the NCI contract requirements matrix for acquisition recommendations.

    Returns ranked vehicle/method recommendations, required documents,
    compliance items, thresholds, warnings, and contract type scoring.

    Args:
        dollar_value: Estimated acquisition value in dollars.
        method: Acquisition method if known (micro, sap, negotiated, fss, idiq-order, sole).
        contract_type: Contract type if known (ffp, cpff, tm, etc.).
        is_it: Whether this involves IT systems or services.
        is_services: Whether this is a services acquisition (vs supplies).
        is_small_business: Whether small business set-aside applies.
        is_rd: Whether this involves research and development.
        factors: JSON string of FAR 16.104 factor answers, e.g. '{"commerciality": "yes"}'.
    """
    import json

    # Parse factor answers
    factor_answers: dict[str, str] = {}
    if factors:
        try:
            factor_answers = json.loads(factors) if isinstance(factors, str) else factors
        except (json.JSONDecodeError, TypeError):
            pass

    # Auto-detect method from dollar value if not specified
    if not method:
        if dollar_value <= 15_000:
            method = "micro"
        elif dollar_value <= 350_000:
            method = "sap"
        else:
            method = "negotiated"

    if not contract_type:
        contract_type = "ffp"

    # Get requirements
    reqs = get_requirements(
        dollar_value=dollar_value,
        method=method,
        contract_type=contract_type,
        is_it=is_it,
        is_services=is_services,
        is_small_business=is_small_business,
        is_rd=is_rd,
    )

    # Score methods (vehicles)
    ranked_methods = score_methods(
        dollar_value=dollar_value,
        is_it=is_it,
        is_services=is_services,
        is_small_business=is_small_business,
    )

    # Score contract types if factors provided
    ranked_types = compute_type_scores(factor_answers) if factor_answers else []

    # Build response
    result = {
        **reqs,
        "ranked_methods": ranked_methods,
        "recommended_method": ranked_methods[0] if ranked_methods else None,
        "ranked_types": ranked_types[:5] if ranked_types else [],
        "recommended_type": ranked_types[0] if ranked_types else None,
        "selected_method": method,
        "selected_type": contract_type,
        "dollar_value": dollar_value,
    }

    return result
