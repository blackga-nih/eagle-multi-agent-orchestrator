"""Template Registry — Maps doc_type to S3 template paths.

This module maps document types to their official NCI/HHS templates in S3.
Templates are stored in the eagle-knowledge-base bucket under:
    approved/supervisor-core/essential-templates/

When a template is not available, the system falls back to markdown generation.
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from botocore.exceptions import ClientError

from .db_client import get_s3
from .ai_document_schema import FIELD_NAME_ALIASES  # Canonical source (Phase 4)

logger = logging.getLogger("eagle.template_registry")

# ── S3 Location ───────────────────────────────────────────────────────
TEMPLATE_BUCKET = os.getenv(
    "TEMPLATE_BUCKET", os.getenv("S3_BUCKET", "eagle-documents-695681773636-dev")
)
TEMPLATE_PREFIX = os.getenv(
    "TEMPLATE_PREFIX",
    "eagle-knowledge-base/approved/supervisor-core/essential-templates",
)

# ── Acquisition Phase Categories ──────────────────────────────────────
ACQUISITION_PHASES = {
    "intake": "Intake & Requirements",
    "planning": "Acquisition Planning",
    "solicitation": "Solicitation",
    "evaluation": "Evaluation & Selection",
    "award": "Award & Contract",
    "administration": "Contract Administration",
}

# Maps doc_type to category metadata
TEMPLATE_CATEGORIES: Dict[str, Dict[str, str]] = {
    "sow": {"phase": "planning", "use_case": "competitive", "group": "requirements"},
    "igce": {"phase": "planning", "use_case": "competitive", "group": "cost"},
    "market_research": {
        "phase": "planning",
        "use_case": "competitive",
        "group": "research",
    },
    "justification": {
        "phase": "planning",
        "use_case": "sole_source",
        "group": "justification",
    },
    "acquisition_plan": {
        "phase": "planning",
        "use_case": "competitive",
        "group": "planning",
    },
    "cor_certification": {
        "phase": "award",
        "use_case": "compliance",
        "group": "compliance",
    },
    "son_products": {
        "phase": "intake",
        "use_case": "competitive",
        "group": "requirements",
    },
    "son_services": {
        "phase": "intake",
        "use_case": "competitive",
        "group": "requirements",
    },
    "buy_american": {
        "phase": "solicitation",
        "use_case": "compliance",
        "group": "compliance",
    },
    "subk_plan": {"phase": "award", "use_case": "competitive", "group": "compliance"},
    "conference_request": {
        "phase": "administration",
        "use_case": "compliance",
        "group": "compliance",
    },
}

# Pattern-based category inference for unregistered S3 files
FILENAME_CATEGORY_PATTERNS: List[Tuple[str, Dict[str, str]]] = [
    (
        r"j&a|justification|j_and_a|single.?source",
        {"phase": "planning", "use_case": "sole_source", "group": "justification"},
    ),
    (
        r"igce|ige|cost.?estimate",
        {"phase": "planning", "use_case": "competitive", "group": "cost"},
    ),
    (
        r"sow|statement.?of.?work",
        {"phase": "planning", "use_case": "competitive", "group": "requirements"},
    ),
    (
        r"son|statement.?of.?need",
        {"phase": "intake", "use_case": "competitive", "group": "requirements"},
    ),
    (
        r"market.?research|mr_|mrr",
        {"phase": "planning", "use_case": "competitive", "group": "research"},
    ),
    (
        r"acquisition.?plan|ap_|s-ap",
        {"phase": "planning", "use_case": "competitive", "group": "planning"},
    ),
    (
        r"cor|contracting.?officer",
        {"phase": "award", "use_case": "compliance", "group": "compliance"},
    ),
    (
        r"subk|subcontract",
        {"phase": "award", "use_case": "competitive", "group": "compliance"},
    ),
    (
        r"buy.?american",
        {"phase": "solicitation", "use_case": "compliance", "group": "compliance"},
    ),
    (
        r"conference|event.?request",
        {"phase": "administration", "use_case": "compliance", "group": "compliance"},
    ),
    (
        r"quotation|quote",
        {"phase": "solicitation", "use_case": "competitive", "group": "solicitation"},
    ),
    (
        r"receiving.?report",
        {"phase": "administration", "use_case": "compliance", "group": "compliance"},
    ),
    (
        r"srb|source.?review",
        {"phase": "evaluation", "use_case": "competitive", "group": "evaluation"},
    ),
    (
        r"bpa|blanket.?purchase",
        {"phase": "solicitation", "use_case": "competitive", "group": "solicitation"},
    ),
]

# ── S3 Template Cache ─────────────────────────────────────────────────
_s3_template_cache: Dict[str, Any] = {}
_s3_cache_expiry: float = 0.0
S3_CACHE_TTL_SECONDS = 300  # 5 minutes


@dataclass
class TemplateMapping:
    """Mapping from doc_type to S3 template."""

    doc_type: str
    s3_filename: str
    file_type: str  # "docx" | "xlsx" | "pdf" | "doc"
    placeholder_map: Dict[str, str] = field(default_factory=dict)
    alternates: List[str] = field(default_factory=list)
    description: str = ""
    display_name: str = ""  # Curated card title; falls back to auto-clean
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
        display_name="Statement of Work (SOW)",
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
            "4.a. IGE for Products.xlsx",
            "4.b. IGE for Services based on Catalog Price.xlsx",
        ],
        description="Independent Government Cost Estimate spreadsheet",
        display_name="IGCE — Commercial Organizations",
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
        display_name="Market Research Report",
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
        display_name="Justification & Approval (J&A) — Over $350K",
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
        display_name="Streamlined Acquisition Plan",
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
        display_name="COR Appointment Memorandum",
    ),
    # ── New doc types from S3 inventory ──
    "son_products": TemplateMapping(
        doc_type="son_products",
        s3_filename="3.a. SON - Products (including Equipment and Supplies).docx",
        file_type="docx",
        placeholder_map={},
        alternates=[],
        description="Statement of Need — Products (Equipment and Supplies)",
        display_name="Statement of Need — Products",
    ),
    "son_services": TemplateMapping(
        doc_type="son_services",
        s3_filename="3.b. SON - Services based on Catalog Pricing.docx",
        file_type="docx",
        placeholder_map={},
        alternates=[],
        description="Statement of Need — Services based on Catalog Pricing",
        display_name="Statement of Need — Services",
    ),
    "buy_american": TemplateMapping(
        doc_type="buy_american",
        s3_filename="DF_Buy_American_Non_Availability_Template.docx",
        file_type="docx",
        placeholder_map={},
        alternates=["DF_Buy_American_Other_Exceptions_Template.docx"],
        description="Buy American Act Determination Form",
        display_name="Buy American — Non-Availability",
    ),
    "subk_plan": TemplateMapping(
        doc_type="subk_plan",
        s3_filename="HHS SubK Plan Template - updated March 2022.doc",
        file_type="doc",
        placeholder_map={},
        alternates=["hhs_subk_review_form.docx"],
        description="HHS Subcontracting Plan template",
        display_name="Subcontracting Plan",
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
        display_name="Conference Request & Approval",
    ),
}

# ── Field Name Aliases ────────────────────────────────────────────────
# CONSOLIDATED: Imported from ai_document_schema.py (Phase 4 of schema propagation)
# The canonical source of truth is now server/app/ai_document_schema.py
# See FIELD_NAME_ALIASES import at top of file.


def normalize_field_names(data: Dict[str, Any], doc_type: str) -> Dict[str, Any]:
    """Normalize AI-sent field names to canonical placeholder_map names.

    Preserves unrecognized keys for downstream markdown generators.

    NOTE: For new code, prefer ai_document_schema.normalize_field_names() which
    provides doc-type-agnostic normalization. This function adds template-specific
    logic (checking against placeholder_map) on top of the canonical aliases.
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
MARKDOWN_ONLY_DOC_TYPES = frozenset(
    {
        "eval_criteria",
        "security_checklist",
        "section_508",
        "contract_type_justification",
    }
)

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


def get_template_fields(filename: str) -> list[str] | None:
    """Return placeholder field names for a template filename."""
    for mapping in TEMPLATE_REGISTRY.values():
        if mapping.s3_filename == filename:
            return list(mapping.placeholder_map.keys()) if mapping.placeholder_map else None
        for alt in mapping.alternates:
            if alt == filename:
                return list(mapping.placeholder_map.keys()) if mapping.placeholder_map else None
    return None


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


# ── S3 Template Listing ───────────────────────────────────────────────


def _infer_doc_type_from_filename(filename: str) -> Optional[str]:
    """Infer doc_type from filename by matching against registered templates.

    Falls back to classify_document() for fuzzy matching when no exact
    registry match is found.
    """
    filename_lower = filename.lower()

    # Check if filename matches any registered template
    for doc_type, mapping in TEMPLATE_REGISTRY.items():
        if mapping.s3_filename.lower() == filename_lower:
            return doc_type
        for alt in mapping.alternates:
            if alt.lower() == filename_lower:
                return doc_type

    # Check form templates
    for doc_type, form_filename in FORM_TEMPLATES.items():
        if form_filename.lower() == filename_lower:
            return doc_type

    # Fallback: fuzzy classification via document_classification_service
    try:
        from .document_classification_service import classify_document

        result = classify_document(filename, None)
        if result.confidence >= 0.7:
            return result.doc_type
    except ImportError:
        pass

    return None


def _infer_category_from_filename(filename: str) -> Optional[Dict[str, str]]:
    """Infer category from filename using pattern matching."""
    filename_lower = filename.lower()

    for pattern, category in FILENAME_CATEGORY_PATTERNS:
        if re.search(pattern, filename_lower):
            return category

    return None


def _get_file_type(filename: str) -> str:
    """Extract file extension as file type."""
    if "." in filename:
        return filename.rsplit(".", 1)[-1].lower()
    return "unknown"


ALTERNATE_DISPLAY_NAMES: Dict[str, str] = {
    # IGCE variants
    "02.D_IGCE_for_Educational_Institutions.xlsx": "IGCE — Educational Institutions",
    "03.D_IGCE_for_Nonprofit_Organizations.xlsx": "IGCE — Nonprofit Organizations",
    "4.a. IGE for Products.xlsx": "IGE — Products",
    "4.b. IGE for Services based on Catalog Price.xlsx": "IGE — Services (Catalog Price)",
    # SOW
    "SOW_Template_Standard.docx": "SOW — Standard Template",
    # Market Research
    "Market_Research_Report_Template.docx": "Market Research Report",
    "Attachment 1 - HHS Market Research Template.docx": "HHS Market Research Template",
    "FY26 Streamlined Market Research Report.docx": "Market Research Report (FY26)",
    # J&A
    "Justification_and_Approval_Under_350K_Template.docx": "J&A — Under $350K",
    "Limited_Sources_J_and_A_Template.docx": "J&A — Limited Sources",
    "6.a. Single Source J&A - up to SAT.docx": "J&A — Single Source (Under SAT)",
    # Acquisition Plan
    "Acquisition_Plan_Full_Template.docx": "Full Acquisition Plan",
    "01.C_NCI_OA_Task_Order_Acquisition_Plan.docx": "NCI Task Order Acquisition Plan",
    "1.a. AP Under SAT.docx": "Acquisition Plan — Under SAT",
    "1.b AP Above SAT.docx": "Acquisition Plan — Above SAT",
    "Streamlined Acquisition Plan (S-AP).docx": "Streamlined Acquisition Plan (S-AP)",
    "Attch #1 - HHS Streamlined Acquisition Plan MS WORD Template_fillable_ver 2025.05.07_FINAL VERSION.docx": "HHS Streamlined Acquisition Plan (Fillable)",
    # COR
    "COR_Designation_Letter_Template.docx": "COR Designation Letter",
    # Buy American
    "DF_Buy_American_Other_Exceptions_Template.docx": "Buy American — Other Exceptions",
    # SubK
    "hhs_subk_review_form.docx": "HHS Subcontracting Review Form",
    # Conference
    "Attachment B - NIH Conference Request for Waiver 20151004_508.docx": "NIH Conference Waiver Request",
    "Attachment D - Promotional Item Approval Form 20172112_508.docx": "Promotional Item Approval Form",
}

# Acronyms that .title() mangles — maps wrong form to correct form
_ACRONYM_FIXES: Dict[str, str] = {
    "Hhs": "HHS",
    "Nih": "NIH",
    "Nci": "NCI",
    "Igce": "IGCE",
    "Ige": "IGE",
    "Cor": "COR",
    "Son": "SON",
    "Sat": "SAT",
    "Sow": "SOW",
    "Oa": "OA",
    "Subk": "SubK",
    "Df": "DF",
    "Fy26": "FY26",
    "Fy25": "FY25",
    "Fy24": "FY24",
    "J&a": "J&A",
    "S-Ap": "S-AP",
    "Bpa": "BPA",
}


def _build_display_name(filename: str) -> str:
    """Build a human-readable display name from filename.

    Priority: curated alternate names > registry display_name > auto-clean.
    """
    # 1. Check curated alternate names
    if filename in ALTERNATE_DISPLAY_NAMES:
        return ALTERNATE_DISPLAY_NAMES[filename]

    # 2. Check primary registry entries
    for mapping in TEMPLATE_REGISTRY.values():
        if mapping.s3_filename == filename and mapping.display_name:
            return mapping.display_name

    # 3. Auto-clean with improved logic
    from .document_classification_service import _clean_filename_for_title

    name = _clean_filename_for_title(filename)

    # Strip numbering prefixes (e.g., "01.D ", "1.A. ", "3.a. ")
    name = re.sub(r"^\d+\.?[a-zA-Z]?\.?\s*", "", name)

    # Strip noise words
    for pattern in [r"\bTemplate\b", r"\bEagle\b", r"\bAttachment\s+[A-Z]\b"]:
        name = re.sub(pattern, "", name, flags=re.IGNORECASE)

    # Restore acronyms that .title() mangled
    for wrong, right in _ACRONYM_FIXES.items():
        name = re.sub(rf"\b{re.escape(wrong)}\b", right, name)

    # Clean trailing/leading whitespace, dashes, em-dashes
    name = re.sub(r"\s+", " ", name).strip().strip("-— ")

    return name or "Untitled Template"


def list_s3_templates(
    refresh: bool = False, phase_filter: Optional[str] = None
) -> List[Dict[str, Any]]:
    """List all templates from S3 bucket with metadata.

    Args:
        refresh: Force cache refresh
        phase_filter: Filter by acquisition phase

    Returns:
        List of template metadata dicts
    """
    global _s3_template_cache, _s3_cache_expiry

    cache_key = "all"
    now = time.time()

    # Check cache
    if not refresh and _s3_cache_expiry > now and cache_key in _s3_template_cache:
        templates = _s3_template_cache[cache_key]
    else:
        # Fetch from S3
        templates = []
        try:
            s3 = get_s3()
            paginator = s3.get_paginator("list_objects_v2")

            for page in paginator.paginate(
                Bucket=TEMPLATE_BUCKET, Prefix=TEMPLATE_PREFIX
            ):
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    # Skip directory markers
                    if key.endswith("/"):
                        continue

                    filename = key.rsplit("/", 1)[-1] if "/" in key else key
                    file_type = _get_file_type(filename)

                    # Skip non-document files
                    if file_type not in ("docx", "xlsx", "pdf", "doc", "xls"):
                        continue

                    doc_type = _infer_doc_type_from_filename(filename)

                    # Get category from registry or infer from filename
                    category = None
                    if doc_type and doc_type in TEMPLATE_CATEGORIES:
                        category = TEMPLATE_CATEGORIES[doc_type]
                    else:
                        category = _infer_category_from_filename(filename)

                    templates.append(
                        {
                            "s3_key": key,
                            "filename": filename,
                            "file_type": file_type,
                            "size_bytes": obj.get("Size", 0),
                            "last_modified": obj.get("LastModified").isoformat()
                            if obj.get("LastModified")
                            else None,
                            "doc_type": doc_type,
                            "category": category,
                            "display_name": _build_display_name(filename),
                            "registered": doc_type is not None,
                        }
                    )

            # Sort by display name
            templates.sort(key=lambda t: t["display_name"])

            # Update cache
            _s3_template_cache[cache_key] = templates
            _s3_cache_expiry = now + S3_CACHE_TTL_SECONDS

            logger.info(
                "Listed %d S3 templates from %s/%s",
                len(templates),
                TEMPLATE_BUCKET,
                TEMPLATE_PREFIX,
            )

        except ClientError as e:
            logger.error("Failed to list S3 templates: %s", e)
            raise

    # Apply phase filter
    if phase_filter:
        templates = [
            t for t in templates if t.get("category", {}).get("phase") == phase_filter
        ]

    return templates


def get_s3_template_by_key(s3_key: str) -> Optional[bytes]:
    """Fetch a template's content from S3 by key.

    Args:
        s3_key: Full S3 key path

    Returns:
        Template file content as bytes, or None if not found
    """
    try:
        s3 = get_s3()
        response = s3.get_object(Bucket=TEMPLATE_BUCKET, Key=s3_key)
        return response["Body"].read()
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchKey":
            logger.warning("S3 template not found: %s", s3_key)
            return None
        logger.error("Failed to fetch S3 template %s: %s", s3_key, e)
        raise
