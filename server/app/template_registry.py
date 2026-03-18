"""Template Registry — Maps doc_type to S3 template paths.

This module maps document types to their official NCI/HHS templates in S3.
Templates are stored in the eagle-knowledge-base bucket under:
    approved/supervisor-core/essential-templates/

When a template is not available, the system falls back to markdown generation.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("eagle.template_registry")

# ── S3 Location ───────────────────────────────────────────────────────
TEMPLATE_BUCKET = os.getenv("TEMPLATE_BUCKET", os.getenv("S3_BUCKET", "eagle-documents-695681773636-dev"))
TEMPLATE_PREFIX = os.getenv(
    "TEMPLATE_PREFIX",
    "eagle-knowledge-base/approved/supervisor-core/essential-templates",
)


@dataclass
class TemplateMapping:
    """Mapping from doc_type to S3 template."""

    doc_type: str
    s3_filename: str
    file_type: str  # "docx" | "xlsx" | "pdf" | "doc"
    placeholder_map: Dict[str, str] = field(default_factory=dict)
    alternates: List[str] = field(default_factory=list)
    description: str = ""
    section_schema: Optional[Any] = field(default=None, repr=False)  # TemplateSchema


# ── Template Registry ─────────────────────────────────────────────────
# Maps doc_type → S3 template info
# Templates without a mapping will use markdown fallback

TEMPLATE_REGISTRY: Dict[str, TemplateMapping] = {
    "sow": TemplateMapping(
        doc_type="sow",
        s3_filename="statement-of-work-template-eagle-v2.docx",
        file_type="docx",
        placeholder_map={
            "title": "{{PROJECT_TITLE}}",
            "description": "{{DESCRIPTION}}",
            "period_of_performance": "{{PERIOD_OF_PERFORMANCE}}",
            "deliverables": "{{DELIVERABLES}}",
            "tasks": "{{TASKS}}",
            "place_of_performance": "{{PLACE_OF_PERFORMANCE}}",
            "security_requirements": "{{SECURITY_REQUIREMENTS}}",
        },
        alternates=["SOW_Template_Standard.docx"],
        description="Statement of Work template",
    ),
    "igce": TemplateMapping(
        doc_type="igce",
        s3_filename="01.D_IGCE_for_Commercial_Organizations.xlsx",
        file_type="xlsx",
        placeholder_map={
            "title": "{{PROJECT_TITLE}}",
            "contractor_name": "{{CONTRACTOR_NAME}}",
            "total_estimate": "{{TOTAL_ESTIMATE}}",
            "line_items": "{{LINE_ITEMS}}",  # Special: array of items
            "prepared_by": "{{PREPARED_BY}}",
            "prepared_date": "{{PREPARED_DATE}}",
        },
        alternates=[
            "02.D_IGCE_for_Educational_Institutions.xlsx",
            "03.D_IGCE_for_Nonprofit_Organizations.xlsx",
            "4.a. IGE for Products.xlsx",
            "4.b. IGE for Services based on Catalog Price.xlsx",
        ],
        description="Independent Government Cost Estimate spreadsheet",
    ),
    "market_research": TemplateMapping(
        doc_type="market_research",
        s3_filename="HHS_Streamlined_Market_Research_Template_FY26.docx",
        file_type="docx",
        placeholder_map={
            "title": "{{PROJECT_TITLE}}",
            "description": "{{REQUIREMENT_DESCRIPTION}}",
            "market_conditions": "{{MARKET_CONDITIONS}}",
            "vendors_identified": "{{VENDORS_IDENTIFIED}}",
            "set_aside_recommendation": "{{SET_ASIDE_RECOMMENDATION}}",
            "conclusion": "{{CONCLUSION}}",
        },
        alternates=[
            "Market_Research_Report_Template.docx",
            "Attachment 1 - HHS Market Research Template.docx",
            "FY26 Streamlined Market Research Report.docx",
        ],
        description="Market Research Report template",
    ),
    "justification": TemplateMapping(
        doc_type="justification",
        s3_filename="Justification_and_Approval_Over_350K_Template.docx",
        file_type="docx",
        placeholder_map={
            "title": "{{PROJECT_TITLE}}",
            "authority": "{{AUTHORITY_CITED}}",
            "contractor": "{{CONTRACTOR_NAME}}",
            "estimated_value": "{{ESTIMATED_VALUE}}",
            "rationale": "{{RATIONALE}}",
            "efforts_to_compete": "{{EFFORTS_TO_COMPETE}}",
        },
        alternates=[
            "Justification_and_Approval_Under_350K_Template.docx",
            "Limited_Sources_J_and_A_Template.docx",
            "6.a. Single Source J&A - up to SAT.docx",
        ],
        description="Justification & Approval (J&A) for sole source",
    ),
    "acquisition_plan": TemplateMapping(
        doc_type="acquisition_plan",
        s3_filename="HHS Streamlined Acquisition Plan Template.docx",
        file_type="docx",
        placeholder_map={
            "title": "{{PROJECT_TITLE}}",
            "description": "{{REQUIREMENT_DESCRIPTION}}",
            "estimated_value": "{{ESTIMATED_VALUE}}",
            "period_of_performance": "{{PERIOD_OF_PERFORMANCE}}",
            "competition": "{{COMPETITION_STRATEGY}}",
            "contract_type": "{{CONTRACT_TYPE}}",
            "set_aside": "{{SET_ASIDE}}",
            "funding_by_fy": "{{FUNDING_TABLE}}",
        },
        alternates=[
            "Acquisition_Plan_Full_Template.docx",
            "01.C_NCI_OA_Task_Order_Acquisition_Plan.docx",
            "1.a. AP Under SAT.docx",
            "1.b AP Above SAT.docx",
            "Streamlined Acquisition Plan (S-AP).docx",
            "Attch #1 - HHS Streamlined Acquisition Plan MS WORD Template_fillable_ver 2025.05.07_FINAL VERSION.docx",
        ],
        description="Streamlined Acquisition Plan template",
    ),
    "cor_certification": TemplateMapping(
        doc_type="cor_certification",
        s3_filename="NIH COR Appointment Memorandum.docx",
        file_type="docx",
        placeholder_map={
            "nominee_name": "{{COR_NAME}}",
            "nominee_title": "{{COR_TITLE}}",
            "nominee_org": "{{COR_ORGANIZATION}}",
            "nominee_phone": "{{COR_PHONE}}",
            "nominee_email": "{{COR_EMAIL}}",
            "fac_cor_level": "{{FAC_COR_LEVEL}}",
            "contract_number": "{{CONTRACT_NUMBER}}",
        },
        alternates=["COR_Designation_Letter_Template.docx"],
        description="COR Appointment/Certification memorandum",
    ),
    # ── New doc types from S3 inventory ──
    "son_products": TemplateMapping(
        doc_type="son_products",
        s3_filename="3.a. SON - Products (including Equipment and Supplies).docx",
        file_type="docx",
        placeholder_map={},
        alternates=[],
        description="Statement of Need — Products (Equipment and Supplies)",
    ),
    "son_services": TemplateMapping(
        doc_type="son_services",
        s3_filename="3.b. SON - Services based on Catalog Pricing.docx",
        file_type="docx",
        placeholder_map={},
        alternates=[],
        description="Statement of Need — Services based on Catalog Pricing",
    ),
    "buy_american": TemplateMapping(
        doc_type="buy_american",
        s3_filename="DF_Buy_American_Non_Availability_Template.docx",
        file_type="docx",
        placeholder_map={},
        alternates=["DF_Buy_American_Other_Exceptions_Template.docx"],
        description="Buy American Act Determination Form",
    ),
    "subk_plan": TemplateMapping(
        doc_type="subk_plan",
        s3_filename="HHS SubK Plan Template - updated March 2022.doc",
        file_type="doc",
        placeholder_map={},
        alternates=["hhs_subk_review_form.docx"],
        description="HHS Subcontracting Plan template",
    ),
    "conference_request": TemplateMapping(
        doc_type="conference_request",
        s3_filename="Attachment A - NIH Conference or Conference Grant Request and Approval 20151404_508.docx",
        file_type="docx",
        placeholder_map={},
        alternates=[
            "Attachment B - NIH Conference Request for Waiver 20151004_508.docx",
            "Attachment D - Promotional Item Approval Form 20172112_508.docx",
        ],
        description="NIH Conference/Event Request forms",
    ),
}

# ── Field Name Aliases ────────────────────────────────────────────────
# Maps common AI-sent field names to canonical placeholder_map keys.
# The AI often sends e.g. "competition_type" but the template expects "competition".
FIELD_NAME_ALIASES: Dict[str, str] = {
    # competition variants
    "competition_type": "competition",
    "competition_strategy": "competition",
    "full_open": "competition",
    # period variants
    "contract_period": "period_of_performance",
    "duration": "period_of_performance",
    "pop": "period_of_performance",
    "performance_period": "period_of_performance",
    # cost/value variants
    "estimated_cost": "estimated_value",
    "budget": "estimated_value",
    "total_cost": "total_estimate",
    "total_value": "estimated_value",
    # description variants
    "requirement": "description",
    "requirement_description": "description",
    "objective": "description",
    "requirement_summary": "description",
    # contractor variants
    "contractor_name": "contractor",
    "vendor": "contractor",
    "vendor_name": "contractor",
    # set-aside variants
    "set_aside_recommendation": "set_aside",
    "set_aside_type": "set_aside",
    "small_business": "set_aside",
    # justification variants
    "authority_cited": "authority",
    "far_authority": "authority",
    "justification_authority": "authority",
    "justification_rationale": "rationale",
    # market research variants
    "vendors": "vendors_identified",
    "vendor_list": "vendors_identified",
    "market_analysis": "market_conditions",
}


def normalize_field_names(data: Dict[str, Any], doc_type: str) -> Dict[str, Any]:
    """Normalize AI-sent field names to canonical placeholder_map names.

    Preserves unrecognized keys for downstream markdown generators.
    """
    mapping = get_template_mapping(doc_type)
    if not mapping:
        return data

    canonical_keys = set(mapping.placeholder_map.keys())
    normalized: Dict[str, Any] = {}
    for key, value in data.items():
        if key in canonical_keys:
            normalized[key] = value
        else:
            alias_target = FIELD_NAME_ALIASES.get(key)
            if alias_target and alias_target in canonical_keys:
                normalized.setdefault(alias_target, value)
            else:
                normalized[key] = value
    return normalized


# Document types that use markdown-only (no S3 template)
MARKDOWN_ONLY_DOC_TYPES = frozenset({
    "eval_criteria",
    "security_checklist",
    "section_508",
    "contract_type_justification",
})

# Form-only templates — official forms that don't need AI content generation
FORM_TEMPLATES: Dict[str, str] = {
    "exemption_determination": "Attachment G - Exemption Determination Template 20151305_508.docx",
    "mandatory_use_waiver": "DF for Mandatory-Use Waiver Template - Draft.pdf",
    "gfp_form": "GFP Form.pdf",
    "bpa_call_order": "LSJ-GSA-BPA-CallOrders.docx",
    "quotation_abstract": "Quotation Abstract.docx",
    "receiving_report": "Receiving Report Template 20201002.docx",
    "srb_request": "SRB Request form.docx",
    "technical_questionnaire": "Project_Officers_Technical_Questionnare.pdf",
}

# Reference guides (not templates, but discoverable)
REFERENCE_GUIDES: Dict[str, str] = {
    "ap_structure_guide": "HHS_AP_Structure_Guide.txt",
    "mr_template_guide": "HHS_Streamlined_MR_Template_FY26.txt",
}


# ── Schema Integration ────────────────────────────────────────────────

def _attach_schemas() -> None:
    """Attach template schemas to their registry mappings at module load."""
    try:
        from app.template_schema import load_template_schemas
        schemas = load_template_schemas()
        for doc_type, schema in schemas.items():
            mapping = TEMPLATE_REGISTRY.get(doc_type)
            if mapping:
                mapping.section_schema = schema
        logger.debug("Attached %d schemas to registry mappings", len(schemas))
    except Exception as e:
        logger.warning("Could not load template schemas: %s", e)


# Attach schemas at import time (lazy — won't fail if files missing)
_attach_schemas()


def get_template_mapping(doc_type: str) -> Optional[TemplateMapping]:
    """Get template mapping for a document type.

    Returns None if doc_type should use markdown fallback.
    """
    return TEMPLATE_REGISTRY.get(doc_type)


def get_template_s3_key(doc_type: str) -> Optional[str]:
    """Get full S3 key for a document type's template.

    Returns None if no template is registered.
    """
    mapping = get_template_mapping(doc_type)
    if mapping:
        return f"{TEMPLATE_PREFIX}/{mapping.s3_filename}"
    return None


def get_alternate_s3_keys(doc_type: str) -> List[str]:
    """Get S3 keys for alternate templates.

    Used when primary template is unavailable.
    """
    mapping = get_template_mapping(doc_type)
    if mapping and mapping.alternates:
        return [f"{TEMPLATE_PREFIX}/{alt}" for alt in mapping.alternates]
    return []


def has_template(doc_type: str) -> bool:
    """Check if a document type has an S3 template available."""
    return doc_type in TEMPLATE_REGISTRY


def is_markdown_only(doc_type: str) -> bool:
    """Check if a document type should only use markdown generation."""
    return doc_type in MARKDOWN_ONLY_DOC_TYPES


def list_registered_doc_types() -> List[str]:
    """List all document types that have S3 templates."""
    return list(TEMPLATE_REGISTRY.keys())


def list_all_doc_types() -> List[str]:
    """List all known document types (templates + markdown-only + forms)."""
    types = list(TEMPLATE_REGISTRY.keys())
    types.extend(MARKDOWN_ONLY_DOC_TYPES)
    types.extend(FORM_TEMPLATES.keys())
    return sorted(set(types))


def get_placeholder_map(doc_type: str) -> Dict[str, str]:
    """Get the data field to placeholder mapping for a doc_type."""
    mapping = get_template_mapping(doc_type)
    if mapping:
        return mapping.placeholder_map.copy()
    return {}


# ── Schema Accessors ──

def get_section_schema(doc_type: str):
    """Get the TemplateSchema for a doc_type, if available."""
    mapping = get_template_mapping(doc_type)
    if mapping and mapping.section_schema:
        return mapping.section_schema
    # Fallback: check the schema module directly
    try:
        from app.template_schema import TEMPLATE_SCHEMAS, _ensure_schemas_loaded
        _ensure_schemas_loaded()
        return TEMPLATE_SCHEMAS.get(doc_type)
    except ImportError:
        return None


def get_section_guidance(doc_type: str) -> str:
    """Get AI prompt section guidance for a doc_type."""
    try:
        from app.template_schema import build_section_guidance
        return build_section_guidance(doc_type)
    except ImportError:
        return ""


def validate_document_completeness(doc_type: str, content: str):
    """Validate document content completeness against schema."""
    try:
        from app.template_schema import validate_completeness
        return validate_completeness(doc_type, content)
    except ImportError:
        return None
