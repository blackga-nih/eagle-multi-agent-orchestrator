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
from typing import Dict, List, Optional

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
    file_type: str  # "docx" | "xlsx"
    placeholder_map: Dict[str, str] = field(default_factory=dict)
    alternates: List[str] = field(default_factory=list)
    description: str = ""


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
        alternates=["Market_Research_Report_Template.docx"],
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
        alternates=["Acquisition_Plan_Full_Template.docx"],
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
}

# Document types that use markdown-only (no S3 template)
MARKDOWN_ONLY_DOC_TYPES = frozenset({
    "eval_criteria",
    "security_checklist",
    "section_508",
    "contract_type_justification",
})


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


def get_placeholder_map(doc_type: str) -> Dict[str, str]:
    """Get the data field to placeholder mapping for a doc_type."""
    mapping = get_template_mapping(doc_type)
    if mapping:
        return mapping.placeholder_map.copy()
    return {}
