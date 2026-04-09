"""AI Document Schema — Canonical schema for AI-generated document metadata.

This module is the single source of truth for:
- doc_type normalization and validation
- Field name aliases
- Contract type and acquisition method enums
- Per-doc-type data models

All AI-generated structured document data should pass through
`normalize_and_validate_document_payload()` before persistence.

Created: 2026-04-09 (Phase 1 of Canonical Schema Propagation)
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = logging.getLogger("eagle.ai_document_schema")


# ══════════════════════════════════════════════════════════════════════════════
# CANONICAL ENUMS
# ══════════════════════════════════════════════════════════════════════════════


class CanonicalDocType(str, Enum):
    """All recognized document types in the EAGLE system."""

    # Core document types (create_document supported)
    SOW = "sow"
    IGCE = "igce"
    MARKET_RESEARCH = "market_research"
    ACQUISITION_PLAN = "acquisition_plan"
    JUSTIFICATION = "justification"
    EVAL_CRITERIA = "eval_criteria"
    SECURITY_CHECKLIST = "security_checklist"
    SECTION_508 = "section_508"
    COR_CERTIFICATION = "cor_certification"
    CONTRACT_TYPE_JUSTIFICATION = "contract_type_justification"
    SON_PRODUCTS = "son_products"
    SON_SERVICES = "son_services"
    PURCHASE_REQUEST = "purchase_request"

    # Micro-purchase types
    PRICE_REASONABLENESS = "price_reasonableness"
    REQUIRED_SOURCES = "required_sources"

    # Template/form types
    SUBK_PLAN = "subk_plan"
    SUBK_REVIEW = "subk_review"
    BUY_AMERICAN = "buy_american"
    CONFERENCE_REQUEST = "conference_request"
    CONFERENCE_WAIVER = "conference_waiver"
    BPA_CALL_ORDER = "bpa_call_order"
    GFP_FORM = "gfp_form"
    SRB_REQUEST = "srb_request"
    QUOTATION_ABSTRACT = "quotation_abstract"
    RECEIVING_REPORT = "receiving_report"
    TECHNICAL_QUESTIONNAIRE = "technical_questionnaire"
    PROMOTIONAL_ITEM = "promotional_item"
    EXEMPTION_DETERMINATION = "exemption_determination"
    MANDATORY_USE_WAIVER = "mandatory_use_waiver"
    REFERENCE_GUIDE = "reference_guide"

    # Frontend-only types (kept for compatibility, may add backend support later)
    FUNDING_DOC = "funding_doc"
    D_F = "d_f"
    QASP = "qasp"
    SOURCE_SELECTION_PLAN = "source_selection_plan"
    SB_REVIEW = "sb_review"
    HUMAN_SUBJECTS = "human_subjects"


class CanonicalContractType(str, Enum):
    """Canonical contract type values."""

    FFP = "ffp"  # Firm Fixed Price
    FP_EPA = "fp-epa"  # Fixed Price with Economic Price Adjustment
    FPI = "fpi"  # Fixed Price Incentive
    CPFF = "cpff"  # Cost Plus Fixed Fee
    CPIF = "cpif"  # Cost Plus Incentive Fee
    CPAF = "cpaf"  # Cost Plus Award Fee
    T_AND_M = "t&m"  # Time and Materials
    LH = "lh"  # Labor Hour
    IDIQ = "idiq"  # Indefinite Delivery Indefinite Quantity
    BPA = "bpa"  # Blanket Purchase Agreement


class CanonicalAcquisitionMethod(str, Enum):
    """Canonical acquisition method values."""

    NEGOTIATED = "negotiated"  # FAR Part 15
    SAP = "sap"  # Simplified Acquisition Procedure (FAR 13)
    SOLE_SOURCE = "sole_source"  # Sole Source / Limited Competition
    MICRO = "micro"  # Micro-purchase (< $10K)
    EIGHT_A = "8a"  # 8(a) Set-Aside
    HUBZONE = "hubzone"  # HUBZone Set-Aside
    SDVOSB = "sdvosb"  # Service-Disabled Veteran-Owned Small Business
    WOSB = "wosb"  # Women-Owned Small Business


# ══════════════════════════════════════════════════════════════════════════════
# ALIAS MAPS — Consolidated from all sources
# ══════════════════════════════════════════════════════════════════════════════


# Doc type aliases (consolidated from doc_type_registry + create_document_support)
DOC_TYPE_ALIASES: Dict[str, str] = {
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
    "source_selection_plan": "acquisition_plan",  # From create_document_support
    "ssp": "acquisition_plan",  # From create_document_support
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
    # Eval criteria aliases (from create_document_support)
    "section_l": "eval_criteria",
    "instructions_to_offerors": "eval_criteria",
    "section_m": "eval_criteria",
    "evaluation_factors": "eval_criteria",
    "evaluation_criteria": "eval_criteria",
    # D&F aliases
    "determination_and_findings": "d_f",
    "determination_findings": "d_f",
    # QASP aliases
    "quality_assurance_surveillance_plan": "qasp",
    # Small business review aliases
    "small_business_review": "sb_review",
    "hhs_653": "sb_review",
}


# Field name aliases (consolidated from template_registry)
FIELD_NAME_ALIASES: Dict[str, str] = {
    # Competition variants
    "competition_type": "competition",
    "competition_strategy": "competition",
    "full_open": "competition",
    # Period variants
    "contract_period": "period_of_performance",
    "duration": "period_of_performance",
    "pop": "period_of_performance",
    "performance_period": "period_of_performance",
    # Cost/value variants
    "estimated_cost": "estimated_value",
    "budget": "estimated_value",
    "total_cost": "total_estimate",
    "total_value": "estimated_value",
    # Description variants
    "requirement": "description",
    "requirement_description": "description",
    "objective": "description",
    "requirement_summary": "description",
    "scope": "description",
    # Contractor variants
    "contractor_name": "contractor",
    "vendor": "contractor",
    "vendor_name": "contractor",
    # Set-aside variants
    "set_aside_recommendation": "set_aside",
    "set_aside_type": "set_aside",
    "small_business": "set_aside",
    # Justification variants
    "authority_cited": "authority",
    "far_authority": "authority",
    "justification_authority": "authority",
    "justification_rationale": "rationale",
    # Market research variants
    "vendors": "vendors_identified",
    "vendor_list": "vendors_identified",
    "market_analysis": "market_conditions",
}


# Contract type aliases (from compliance_matrix)
CONTRACT_TYPE_ALIASES: Dict[str, str] = {
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
    "time_and_materials": "t&m",
    "time and materials": "t&m",
    "t_and_m": "t&m",
    "t&m": "t&m",
    "tm": "t&m",
    # Labor Hour
    "labor_hour": "lh",
    "labor hour": "lh",
    # IDIQ
    "indefinite_delivery": "idiq",
    "indefinite_quantity": "idiq",
    # BPA
    "blanket_purchase": "bpa",
}


# Acquisition method aliases (from compliance_matrix)
ACQUISITION_METHOD_ALIASES: Dict[str, str] = {
    # Negotiated (FAR 15)
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
    # SAP (FAR 13)
    "simplified_acquisition": "sap",
    "simplified acquisition": "sap",
    "simplified": "sap",
    "far part 13": "sap",
    "part 13": "sap",
    "far_13": "sap",
    # Sole source
    "limited_competition": "sole_source",
    "limited competition": "sole_source",
    "single_source": "sole_source",
    "single source": "sole_source",
    # Micro
    "micro_purchase": "micro",
    "micro purchase": "micro",
    "micropurchase": "micro",
    # Set-asides
    "8(a)": "8a",
    "eight_a": "8a",
}


# Labor category aliases (from igce_generation_extractor)
LABOR_CATEGORY_ALIASES: Dict[str, str] = {
    "pm": "project manager",
    "project lead": "project manager",
    "program manager": "project manager",
    "senior developer": "senior software engineer",
    "senior dev": "senior software engineer",
    "sr engineer": "senior software engineer",
    "sr developer": "senior software engineer",
    "developer": "software engineer",
    "dev": "software engineer",
    "engineer": "software engineer",
    "programmer": "software engineer",
    "junior developer": "junior software engineer",
    "junior dev": "junior software engineer",
    "jr engineer": "junior software engineer",
    "jr developer": "junior software engineer",
    "solutions architect": "cloud architect",
    "aws architect": "cloud architect",
    "azure architect": "cloud architect",
    "data analyst": "data scientist",
    "ml engineer": "data scientist",
    "machine learning engineer": "data scientist",
    "site reliability engineer": "devops engineer",
    "sre": "devops engineer",
    "platform engineer": "devops engineer",
    "cybersecurity engineer": "security engineer",
    "infosec engineer": "security engineer",
    "security analyst": "security engineer",
    "test engineer": "qa engineer",
    "quality assurance": "qa engineer",
    "tester": "qa engineer",
    "documentation specialist": "technical writer",
    "tech writer": "technical writer",
    "ba": "business analyst",
    "requirements analyst": "business analyst",
    "sysadmin": "system administrator",
    "sys admin": "system administrator",
    "it administrator": "system administrator",
    "dba": "database administrator",
    "database engineer": "database administrator",
    "network administrator": "network engineer",
    "network admin": "network engineer",
    "support specialist": "help desk",
    "it support": "help desk",
    "technical support": "help desk",
}


# ══════════════════════════════════════════════════════════════════════════════
# NORMALIZATION FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════


def normalize_doc_type(raw: str) -> str:
    """Normalize a doc_type string to its canonical form.

    Handles: hyphens, spaces, case, and known aliases.
    Returns the normalized string (may still be invalid if not a known type).
    """
    if not raw:
        return ""
    cleaned = raw.strip().lower().replace("-", "_").replace(" ", "_")
    return DOC_TYPE_ALIASES.get(cleaned, cleaned)


def normalize_contract_type(raw: str) -> str | None:
    """Normalize a contract type string to its canonical form.

    Returns None if the input cannot be resolved.
    """
    if not raw or not raw.strip():
        return None
    cleaned = raw.strip().lower().replace("-", "_").replace(" ", "_")

    # Check if already canonical
    try:
        CanonicalContractType(cleaned)
        return cleaned
    except ValueError:
        pass

    # Check with hyphen variant (e.g., fp-epa)
    hyphenated = cleaned.replace("_", "-")
    try:
        CanonicalContractType(hyphenated)
        return hyphenated
    except ValueError:
        pass

    # Check aliases
    if cleaned in CONTRACT_TYPE_ALIASES:
        return CONTRACT_TYPE_ALIASES[cleaned]

    # Try original with spaces
    lowered = raw.strip().lower()
    if lowered in CONTRACT_TYPE_ALIASES:
        return CONTRACT_TYPE_ALIASES[lowered]

    return None


def normalize_acquisition_method(raw: str) -> str | None:
    """Normalize an acquisition method string to its canonical form.

    Returns None if the input cannot be resolved.
    """
    if not raw or not raw.strip():
        return None
    cleaned = raw.strip().lower().replace("-", "_").replace(" ", "_")

    # Check if already canonical
    try:
        CanonicalAcquisitionMethod(cleaned)
        return cleaned
    except ValueError:
        pass

    # Check aliases
    if cleaned in ACQUISITION_METHOD_ALIASES:
        return ACQUISITION_METHOD_ALIASES[cleaned]

    # Try original with spaces
    lowered = raw.strip().lower()
    if lowered in ACQUISITION_METHOD_ALIASES:
        return ACQUISITION_METHOD_ALIASES[lowered]

    return None


def normalize_field_names(data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize AI-sent field names to canonical names.

    Preserves unrecognized keys for downstream processing.
    """
    normalized: Dict[str, Any] = {}
    for key, value in data.items():
        canonical_key = FIELD_NAME_ALIASES.get(key, key)
        # Don't overwrite if canonical key already set
        if canonical_key not in normalized:
            normalized[canonical_key] = value
    return normalized


def normalize_labor_category(name: str) -> str:
    """Normalize a labor category name to its canonical form."""
    key = name.lower().strip()
    return LABOR_CATEGORY_ALIASES.get(key, name.title())


def is_valid_doc_type(doc_type: str) -> bool:
    """Check if a doc_type is recognized by the EAGLE system."""
    normalized = normalize_doc_type(doc_type)
    try:
        CanonicalDocType(normalized)
        return True
    except ValueError:
        return False


def get_all_doc_types() -> List[str]:
    """Return all canonical doc_type values."""
    return [dt.value for dt in CanonicalDocType]


def get_create_document_types() -> frozenset[str]:
    """Return doc_types supported by create_document tool.

    These types have markdown generators or templates available.
    """
    return frozenset({
        "sow",
        "igce",
        "market_research",
        "justification",
        "acquisition_plan",
        "eval_criteria",
        "security_checklist",
        "section_508",
        "cor_certification",
        "contract_type_justification",
        "son_products",
        "son_services",
        "purchase_request",
        "price_reasonableness",
        "required_sources",
        "subk_plan",
        "subk_review",
        "buy_american",
    })


# ══════════════════════════════════════════════════════════════════════════════
# PYDANTIC MODELS — Per doc-type data structures
# ══════════════════════════════════════════════════════════════════════════════


class BaseDocumentData(BaseModel):
    """Base model for all document data payloads."""

    model_config = ConfigDict(extra="allow")  # Allow additional fields

    title: Optional[str] = None
    description: Optional[str] = None
    estimated_value: Optional[float] = None
    period_of_performance: Optional[str] = None
    contract_type: Optional[str] = None
    acquisition_method: Optional[str] = None
    competition: Optional[str] = None

    @field_validator("contract_type", mode="before")
    @classmethod
    def normalize_contract_type_field(cls, v):
        if v is None:
            return None
        normalized = normalize_contract_type(str(v))
        return normalized if normalized else v

    @field_validator("acquisition_method", mode="before")
    @classmethod
    def normalize_acquisition_method_field(cls, v):
        if v is None:
            return None
        normalized = normalize_acquisition_method(str(v))
        return normalized if normalized else v


class IgceLineItem(BaseModel):
    """A labor line item in an IGCE."""

    description: str
    rate: Optional[float] = None
    hours: Optional[int] = None
    quantity: Optional[int] = None
    total: Optional[float] = None

    @field_validator("description", mode="before")
    @classmethod
    def normalize_labor_description(cls, v):
        if v is None:
            return ""
        return normalize_labor_category(str(v))


class IgceGoodsItem(BaseModel):
    """A goods/equipment line item in an IGCE."""

    product_name: str
    quantity: Optional[int] = None
    unit_price: Optional[float] = None
    total: Optional[float] = None


class SowDocumentData(BaseDocumentData):
    """Data model for Statement of Work documents."""

    deliverables: Optional[Union[List[str], List[Dict[str, Any]]]] = None
    tasks: Optional[Union[List[str], List[Dict[str, Any]]]] = None
    place_of_performance: Optional[str] = None
    security_requirements: Optional[str] = None


class IgceDocumentData(BaseDocumentData):
    """Data model for IGCE documents."""

    line_items: Optional[Union[List[IgceLineItem], List[Dict[str, Any]]]] = Field(
        default=None, description="Labor categories with hours/rates"
    )
    goods_items: Optional[Union[List[IgceGoodsItem], List[Dict[str, Any]]]] = Field(
        default=None, description="Equipment/license items"
    )
    period_months: Optional[int] = None
    delivery_date: Optional[str] = None
    overhead_rate: Optional[float] = None
    contingency_rate: Optional[float] = None


class MarketResearchDocumentData(BaseDocumentData):
    """Data model for Market Research documents."""

    naics_code: Optional[str] = None
    vendors_identified: Optional[Union[List[str], List[Dict[str, Any]]]] = None
    market_conditions: Optional[str] = None
    set_aside: Optional[str] = None
    conclusion: Optional[str] = None


class JustificationDocumentData(BaseDocumentData):
    """Data model for Justification (J&A) documents."""

    authority: Optional[str] = None
    contractor: Optional[str] = None
    rationale: Optional[str] = None
    efforts_to_compete: Optional[str] = None


class AcquisitionPlanDocumentData(BaseDocumentData):
    """Data model for Acquisition Plan documents."""

    funding_by_fy: Optional[Dict[str, float]] = None
    milestones: Optional[List[Dict[str, Any]]] = None
    set_aside: Optional[str] = None


# Map doc_type to its specific model
DOC_TYPE_MODELS: Dict[str, type[BaseDocumentData]] = {
    "sow": SowDocumentData,
    "igce": IgceDocumentData,
    "market_research": MarketResearchDocumentData,
    "justification": JustificationDocumentData,
    "acquisition_plan": AcquisitionPlanDocumentData,
}


# ══════════════════════════════════════════════════════════════════════════════
# VALIDATION ENTRYPOINT
# ══════════════════════════════════════════════════════════════════════════════


class CanonicalDocumentPayload(BaseModel):
    """Result of normalize_and_validate_document_payload()."""

    doc_type: str
    title: str
    data: Dict[str, Any]
    warnings: List[str] = Field(default_factory=list)
    unknown_fields: List[str] = Field(default_factory=list)
    normalized_aliases: List[str] = Field(default_factory=list)


def normalize_and_validate_document_payload(
    *,
    raw_doc_type: str,
    title: str,
    data: Dict[str, Any] | None,
) -> CanonicalDocumentPayload:
    """Normalize and validate an AI-generated document payload.

    This is the canonical boundary function. All create_document calls should
    pass through here before persistence or template population.

    Args:
        raw_doc_type: The doc_type from the AI (may need normalization)
        title: Document title
        data: Structured metadata from the AI

    Returns:
        CanonicalDocumentPayload with normalized data and any warnings
    """
    warnings: List[str] = []
    normalized_aliases: List[str] = []
    unknown_fields: List[str] = []

    # Normalize doc_type
    doc_type = normalize_doc_type(raw_doc_type)
    if doc_type != raw_doc_type.strip().lower().replace("-", "_").replace(" ", "_"):
        normalized_aliases.append(f"doc_type: {raw_doc_type} → {doc_type}")
        logger.info("Normalized doc_type: %s → %s", raw_doc_type, doc_type)

    # Validate doc_type
    if not is_valid_doc_type(doc_type):
        warnings.append(f"Unknown doc_type: {doc_type}")
        logger.warning("Unknown doc_type: %s (original: %s)", doc_type, raw_doc_type)

    # Normalize field names in data
    raw_data = data or {}
    normalized_data = normalize_field_names(raw_data)

    # Track which fields were normalized
    for original_key in raw_data.keys():
        canonical_key = FIELD_NAME_ALIASES.get(original_key)
        if canonical_key and canonical_key != original_key:
            normalized_aliases.append(f"field: {original_key} → {canonical_key}")

    # Normalize contract_type if present
    if "contract_type" in normalized_data and normalized_data["contract_type"]:
        original_ct = normalized_data["contract_type"]
        normalized_ct = normalize_contract_type(str(original_ct))
        if normalized_ct:
            if normalized_ct != str(original_ct).lower():
                normalized_aliases.append(f"contract_type: {original_ct} → {normalized_ct}")
            normalized_data["contract_type"] = normalized_ct
        else:
            warnings.append(f"Unknown contract_type: {original_ct}")

    # Normalize acquisition_method if present
    if "acquisition_method" in normalized_data and normalized_data["acquisition_method"]:
        original_am = normalized_data["acquisition_method"]
        normalized_am = normalize_acquisition_method(str(original_am))
        if normalized_am:
            if normalized_am != str(original_am).lower():
                normalized_aliases.append(f"acquisition_method: {original_am} → {normalized_am}")
            normalized_data["acquisition_method"] = normalized_am
        else:
            warnings.append(f"Unknown acquisition_method: {original_am}")

    # Validate against doc-type-specific model (if available)
    model_class = DOC_TYPE_MODELS.get(doc_type, BaseDocumentData)
    try:
        validated = model_class(**normalized_data)
        # Get the validated data back as dict
        normalized_data = validated.model_dump(exclude_none=False, exclude_unset=False)

        # Check for unknown fields (fields in data but not in model)
        model_fields = set(model_class.model_fields.keys())
        for key in raw_data.keys():
            canonical_key = FIELD_NAME_ALIASES.get(key, key)
            if canonical_key not in model_fields and canonical_key not in ("extra",):
                unknown_fields.append(canonical_key)

    except Exception as e:
        warnings.append(f"Validation warning: {e}")
        logger.warning("Document data validation warning for %s: %s", doc_type, e)

    # Log warnings for observability
    if warnings:
        logger.info(
            "Document payload normalized with warnings: doc_type=%s, warnings=%s",
            doc_type,
            warnings,
        )

    return CanonicalDocumentPayload(
        doc_type=doc_type,
        title=title or "",
        data=normalized_data,
        warnings=warnings,
        unknown_fields=unknown_fields,
        normalized_aliases=normalized_aliases,
    )
