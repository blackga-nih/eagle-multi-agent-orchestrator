# Plan: S3 Template Integration for Document Generation

**Created**: 2026-03-05T11:02:47Z
**Status**: Draft
**Type**: Feature Implementation
**Estimated Effort**: 2-3 days

---

## 1. Executive Summary

### 1.1 Problem Statement

The EAGLE `create_document` tool currently generates acquisition documents using **hardcoded markdown templates** embedded in Python functions (`_generate_sow()`, `_generate_igce()`, etc.). Meanwhile, **37 official NCI/HHS DOCX/XLSX templates** sit unused in S3 at:

```
s3://eagle-documents-695681773636-dev/eagle-knowledge-base/approved/supervisor-core/essential-templates/
```

**Issues with current approach:**
1. Generated documents are plain markdown — contracting officers expect official Word/Excel formats
2. Templates don't match the official HHS/NIH document standards
3. No branding, headers, or signature blocks from official templates
4. IGCE outputs markdown tables instead of proper Excel with formulas

### 1.2 Proposed Solution

Modify the `create_document` tool to:
1. Fetch official DOCX/XLSX templates from S3
2. Populate `{{PLACEHOLDER}}` tokens with user data
3. Save populated documents to user's S3 workspace
4. Return markdown preview for chat display
5. Fall back to existing markdown generators when templates unavailable

### 1.3 Success Criteria

- [ ] SOW, IGCE, Market Research, J&A, Acquisition Plan, COR Cert use S3 templates
- [ ] Generated documents are proper DOCX/XLSX files
- [ ] Fallback to markdown works for doc types without S3 templates
- [ ] No breaking changes to existing `create_document` API
- [ ] 60-second template caching reduces S3 calls
- [ ] Unit tests cover all new code paths

---

## 2. Current State Analysis

### 2.1 Document Generation Flow (Current)

```
POST /api/chat → "Create a SOW for..."
       │
       ▼
Strands Agent Tool Dispatch
       │
       ▼
_exec_create_document(params, tenant_id, session_id)
  [server/app/agentic_service.py:1084-1140]
       │
       ├── doc_type == "sow" → _generate_sow(title, data)
       ├── doc_type == "igce" → _generate_igce(title, data)
       ├── doc_type == "market_research" → _generate_market_research(title, data)
       ├── ... (10 document types)
       │
       ▼
Returns markdown string
       │
       ▼
Saves to S3: eagle/{tenant}/{user}/documents/{doc_type}_{timestamp}.md
       │
       ▼
Returns response with markdown content
```

### 2.2 Current Generator Functions

| Function | Location | Data Fields | Sections |
|----------|----------|-------------|----------|
| `_generate_sow()` | agentic_service.py:1143-1227 | description, period_of_performance, deliverables, tasks | Background, Scope, POP, Standards, Tasks, Deliverables, GFP, QASP, Place, Security |
| `_generate_igce()` | agentic_service.py:1230-1304 | line_items, overhead_rate, contingency_rate | Purpose, Methodology, Cost Breakdown Table, Totals, Assumptions, Confidence |
| `_generate_market_research()` | agentic_service.py:1307-1367 | description, naics_code, vendors | Need, Sources Consulted, Potential Sources, Small Business, Commercial, Strategy, Vehicle |
| `_generate_justification()` | agentic_service.py:1370-1435 | authority, contractor, estimated_value, rationale | Activity, Action, Supplies, Authority, Reason, Efforts, Determination, Barriers, Approval |
| `_generate_acquisition_plan()` | agentic_service.py:1438-1535 | description, estimated_value, period_of_performance, competition, contract_type, set_aside, funding_by_fy | Background, Objectives, Cost, Capability, Schedule, Competition, Source Selection, Considerations, Milestones, Approvals |
| `_generate_eval_criteria()` | agentic_service.py:1538-1600 | factors, evaluation_method, rating_scale | Factors, Rating Scale, Process, Basis for Award |
| `_generate_security_checklist()` | agentic_service.py:1603-1664 | it_systems_involved, impact_level, cloud_services | Questions, Impact Level, Required Clauses, Systems, Review |
| `_generate_section_508()` | agentic_service.py:1667-1735 | product_types, exception_claimed, vpat_status | Applicability, Product Types, Exceptions, VPAT Status, Contract Language |
| `_generate_cor_certification()` | agentic_service.py:1738-1808 | nominee_name, nominee_title, nominee_org, nominee_phone, nominee_email, fac_cor_level, contract_number | Nominee Info, FAC-COR Certification, Delegated Duties, Limitations, Signatures |
| `_generate_contract_type_justification()` | agentic_service.py:1811-1882 | contract_type, rationale, risk_to_government, risk_to_contractor, estimated_value | Findings, Contract Type Analysis Table, Rationale, Risk Assessment, Requirements, Determination, Approval |

### 2.3 S3 Templates Available

**Location**: `eagle-knowledge-base/approved/supervisor-core/essential-templates/`

```
01.C_NCI_OA_Task_Order_Acquisition_Plan.docx        (127 KB)
01.D_IGCE_for_Commercial_Organizations.xlsx         (35 KB)
1.a. AP Under SAT.docx                              (64 KB)
1.b AP Above SAT.docx                               (172 KB)
3.a. SON - Products (including Equipment).docx     (50 KB)
3.b. SON - Services based on Catalog Pricing.docx  (49 KB)
4.a. IGE for Products.xlsx                          (26 KB)
4.b. IGE for Services based on Catalog Price.xlsx  (34 KB)
6.a. Single Source J&A - up to SAT.docx            (51 KB)
Attachment 1 - HHS Market Research Template.docx   (48 KB)
HHS Streamlined Acquisition Plan Template.docx     (159 KB)
HHS_Streamlined_Market_Research_Template_FY26.docx (63 KB)
Justification_and_Approval_Over_350K_Template.docx (56 KB)
NIH COR Appointment Memorandum.docx                (40 KB)
statement-of-work-template-eagle-v2.docx           (33 KB)
... (37 total files)
```

### 2.4 Existing Infrastructure (Reusable)

| Component | File | Line | Purpose |
|-----------|------|------|---------|
| `python-docx>=1.1.0` | server/requirements.txt | 17 | DOCX manipulation |
| `_get_s3()` | server/app/agentic_service.py | ~400 | Lazy S3 client singleton |
| `_cache_get/set` | server/app/template_store.py | 70-82 | 60s TTL cache pattern |
| `_extract_docx()` | infrastructure/.../file_processors.py | 58 | Text extraction from DOCX |
| `markdown_to_docx()` | server/app/document_export.py | 26 | Markdown → DOCX with NCI branding |
| `_extract_variables()` | server/app/template_store.py | 99 | `{{VARIABLE}}` regex extraction |
| `resolve_template()` | server/app/template_store.py | 294 | 4-layer template fallback |

---

## 3. Architecture Design

### 3.1 High-Level Flow (Proposed)

```
POST /api/chat → "Create a SOW for..."
       │
       ▼
Strands Agent Tool Dispatch
       │
       ▼
_exec_create_document(params, tenant_id, session_id)
  [server/app/agentic_service.py:1084]
       │
       ▼
TemplateService.generate_document(doc_type, title, data, output_format)
  [server/app/template_service.py - NEW]
       │
       ├──────────────────────────────────────────────┐
       ▼                                              ▼
TemplateRegistry.resolve(doc_type)           [Fallback Path]
  [server/app/template_registry.py - NEW]    _generate_*(title, data)
       │                                     [existing functions]
       ▼                                              │
S3 Template Fetch (with 60s cache)                   │
       │                                              │
       ▼                                              │
DOCXPopulator.populate() or XLSXPopulator.populate() │
       │                                              │
       ├──────────────────────────────────────────────┘
       ▼
Save to S3: eagle/{tenant}/{user}/documents/{doc_type}_{timestamp}.{docx|xlsx|md}
       │
       ▼
Return response:
  - content: markdown preview for chat
  - s3_key: path to saved file
  - file_type: "docx" | "xlsx" | "md"
  - source: "s3_template" | "markdown_fallback"
```

### 3.2 Component Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              create_document Tool                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         TemplateService                              │   │
│  │  [server/app/template_service.py]                                   │   │
│  │                                                                      │   │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  │   │
│  │  │ generate_document│  │ _fetch_template  │  │ _extract_preview │  │   │
│  │  │ (public API)     │  │ (S3 + cache)     │  │ (DOCX→MD)        │  │   │
│  │  └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘  │   │
│  │           │                     │                     │            │   │
│  └───────────┼─────────────────────┼─────────────────────┼────────────┘   │
│              │                     │                     │                │
│  ┌───────────▼─────────────────────▼─────────────────────▼────────────┐   │
│  │                        TemplateRegistry                             │   │
│  │  [server/app/template_registry.py]                                  │   │
│  │                                                                     │   │
│  │  TEMPLATE_REGISTRY = {                                              │   │
│  │    "sow": TemplateMapping(                                          │   │
│  │      s3_filename="statement-of-work-template-eagle-v2.docx",        │   │
│  │      placeholder_map={"title": "{{TITLE}}", ...},                   │   │
│  │      file_type="docx"                                               │   │
│  │    ),                                                               │   │
│  │    "igce": TemplateMapping(..., file_type="xlsx"),                  │   │
│  │    ...                                                              │   │
│  │  }                                                                  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌──────────────────────────────┐  ┌──────────────────────────────────┐   │
│  │       DOCXPopulator          │  │       XLSXPopulator              │   │
│  │  [template_service.py]       │  │  [template_service.py]           │   │
│  │                              │  │                                  │   │
│  │  + populate(bytes, data)     │  │  + populate(bytes, data)         │   │
│  │  + extract_text(bytes)       │  │  + extract_text(bytes)           │   │
│  │  + _replace_in_paragraph()   │  │  + _insert_line_items()          │   │
│  │  + _format_list()            │  │                                  │   │
│  │                              │  │  Uses: openpyxl                  │   │
│  │  Uses: python-docx           │  │                                  │   │
│  └──────────────────────────────┘  └──────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         Template Cache                               │   │
│  │                                                                      │   │
│  │  _template_cache: Dict[str, Dict] = {                               │   │
│  │    "bucket:key": {"ts": 1709640000, "data": bytes(...)},            │   │
│  │  }                                                                   │   │
│  │  CACHE_TTL_SECONDS = 60                                             │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Detailed Implementation

### 4.1 New File: `server/app/template_registry.py`

```python
"""Template Registry — Maps doc_type to S3 template paths with metadata.

This module defines the mapping between document types (sow, igce, etc.)
and their corresponding S3 template files. Each mapping includes:
- Primary template filename
- Alternate templates (e.g., SAT vs over-SAT versions)
- Placeholder map (data field → template variable)
- File type (docx or xlsx)

S3 Location: eagle-knowledge-base/approved/supervisor-core/essential-templates/
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# ══════════════════════════════════════════════════════════════════════════════
# Configuration
# ══════════════════════════════════════════════════════════════════════════════

# S3 bucket containing templates (same as document storage bucket)
TEMPLATE_BUCKET = os.getenv("S3_BUCKET", "eagle-documents-695681773636-dev")

# S3 prefix for essential templates within the knowledge base
TEMPLATE_PREFIX = "eagle-knowledge-base/approved/supervisor-core/essential-templates/"


# ══════════════════════════════════════════════════════════════════════════════
# Data Classes
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class TemplateMapping:
    """Defines how a document type maps to an S3 template.

    Attributes:
        s3_filename: Primary template filename (without prefix).
                     Empty string means no S3 template available.
        alternates: List of alternate template filenames for selection
                    (e.g., different threshold versions).
        placeholder_map: Maps data field names to template placeholders.
                         Keys are field names from the data dict.
                         Values are placeholder strings in the template.
        file_type: Output file type - "docx" or "xlsx".
        description: Human-readable description of the template.
        version: Template version identifier.
    """
    s3_filename: str
    placeholder_map: Dict[str, str] = field(default_factory=dict)
    alternates: List[str] = field(default_factory=list)
    file_type: str = "docx"
    description: str = ""
    version: str = "v1"

    @property
    def has_template(self) -> bool:
        """Returns True if an S3 template is configured."""
        return bool(self.s3_filename)

    @property
    def s3_key(self) -> str:
        """Returns full S3 key for the primary template."""
        if not self.s3_filename:
            return ""
        return f"{TEMPLATE_PREFIX}{self.s3_filename}"


# ══════════════════════════════════════════════════════════════════════════════
# Template Registry
# ══════════════════════════════════════════════════════════════════════════════

TEMPLATE_REGISTRY: Dict[str, TemplateMapping] = {
    # ─────────────────────────────────────────────────────────────────────────
    # Statement of Work (SOW)
    # ─────────────────────────────────────────────────────────────────────────
    "sow": TemplateMapping(
        s3_filename="statement-of-work-template-eagle-v2.docx",
        alternates=[
            "statement-of-work-template-eagle.docx",
            "3.a. SON - Products (including Equipment and Supplies).docx",
            "3.b. SON - Services based on Catalog Pricing.docx",
        ],
        placeholder_map={
            "title": "{{TITLE}}",
            "description": "{{DESCRIPTION}}",
            "period_of_performance": "{{PERIOD_OF_PERFORMANCE}}",
            "deliverables": "{{DELIVERABLES}}",
            "tasks": "{{TASKS}}",
            "place_of_performance": "{{PLACE_OF_PERFORMANCE}}",
            "security_requirements": "{{SECURITY_REQUIREMENTS}}",
            "government_furnished_property": "{{GFP}}",
        },
        file_type="docx",
        description="Statement of Work / Statement of Need",
    ),

    # ─────────────────────────────────────────────────────────────────────────
    # Independent Government Cost Estimate (IGCE)
    # ─────────────────────────────────────────────────────────────────────────
    "igce": TemplateMapping(
        s3_filename="01.D_IGCE_for_Commercial_Organizations.xlsx",
        alternates=[
            "4.a. IGE for Products.xlsx",
            "4.b. IGE for Services based on Catalog Price.xlsx",
        ],
        placeholder_map={
            "title": "{{TITLE}}",
            "line_items": "{{LINE_ITEMS}}",  # Special: array of {description, quantity, unit_price}
            "overhead_rate": "{{OVERHEAD_RATE}}",
            "contingency_rate": "{{CONTINGENCY_RATE}}",
            "prepared_by": "{{PREPARED_BY}}",
            "date": "{{DATE}}",
        },
        file_type="xlsx",
        description="Independent Government Cost Estimate",
    ),

    # ─────────────────────────────────────────────────────────────────────────
    # Market Research Report
    # ─────────────────────────────────────────────────────────────────────────
    "market_research": TemplateMapping(
        s3_filename="HHS_Streamlined_Market_Research_Template_FY26.docx",
        alternates=[
            "FY26 Streamlined Market Research Report.docx",
            "Attachment 1 - HHS Market Research Template.docx",
        ],
        placeholder_map={
            "title": "{{TITLE}}",
            "description": "{{DESCRIPTION}}",
            "naics_code": "{{NAICS_CODE}}",
            "vendors": "{{VENDORS}}",  # Array of {name, size, vehicles}
            "sources_consulted": "{{SOURCES_CONSULTED}}",
            "small_business_analysis": "{{SMALL_BUSINESS_ANALYSIS}}",
            "recommended_strategy": "{{RECOMMENDED_STRATEGY}}",
            "date": "{{DATE}}",
        },
        file_type="docx",
        description="Market Research Report (Streamlined FY26)",
    ),

    # ─────────────────────────────────────────────────────────────────────────
    # Justification and Approval (J&A)
    # ─────────────────────────────────────────────────────────────────────────
    "justification": TemplateMapping(
        s3_filename="Justification_and_Approval_Over_350K_Template.docx",
        alternates=[
            "6.a. Single Source J&A - up to SAT.docx",
        ],
        placeholder_map={
            "title": "{{TITLE}}",
            "authority": "{{AUTHORITY}}",
            "contractor": "{{CONTRACTOR}}",
            "estimated_value": "{{ESTIMATED_VALUE}}",
            "rationale": "{{RATIONALE}}",
            "efforts_to_compete": "{{EFFORTS_TO_COMPETE}}",
            "actions_to_remove_barriers": "{{ACTIONS_TO_REMOVE_BARRIERS}}",
            "contracting_officer": "{{CONTRACTING_OFFICER}}",
            "date": "{{DATE}}",
        },
        file_type="docx",
        description="Justification and Approval (Sole Source)",
    ),

    # ─────────────────────────────────────────────────────────────────────────
    # Acquisition Plan
    # ─────────────────────────────────────────────────────────────────────────
    "acquisition_plan": TemplateMapping(
        s3_filename="HHS Streamlined Acquisition Plan Template.docx",
        alternates=[
            "01.C_NCI_OA_Task_Order_Acquisition_Plan.docx",
            "1.a. AP Under SAT.docx",
            "1.b AP Above SAT.docx",
            "Streamlined Acquisition Plan (S-AP).docx",
        ],
        placeholder_map={
            "title": "{{TITLE}}",
            "description": "{{DESCRIPTION}}",
            "estimated_value": "{{ESTIMATED_VALUE}}",
            "period_of_performance": "{{PERIOD_OF_PERFORMANCE}}",
            "competition": "{{COMPETITION}}",
            "contract_type": "{{CONTRACT_TYPE}}",
            "set_aside": "{{SET_ASIDE}}",
            "funding_by_fy": "{{FUNDING_BY_FY}}",  # Array of {fiscal_year, amount}
            "milestones": "{{MILESTONES}}",
            "contracting_officer": "{{CONTRACTING_OFFICER}}",
            "date": "{{DATE}}",
        },
        file_type="docx",
        description="Streamlined Acquisition Plan (HHS Format)",
    ),

    # ─────────────────────────────────────────────────────────────────────────
    # COR Certification
    # ─────────────────────────────────────────────────────────────────────────
    "cor_certification": TemplateMapping(
        s3_filename="NIH COR Appointment Memorandum.docx",
        placeholder_map={
            "nominee_name": "{{NOMINEE_NAME}}",
            "nominee_title": "{{NOMINEE_TITLE}}",
            "nominee_org": "{{NOMINEE_ORG}}",
            "nominee_phone": "{{NOMINEE_PHONE}}",
            "nominee_email": "{{NOMINEE_EMAIL}}",
            "fac_cor_level": "{{FAC_COR_LEVEL}}",
            "contract_number": "{{CONTRACT_NUMBER}}",
            "contracting_officer": "{{CONTRACTING_OFFICER}}",
            "date": "{{DATE}}",
        },
        file_type="docx",
        description="COR Appointment Memorandum",
    ),

    # ─────────────────────────────────────────────────────────────────────────
    # Document types WITHOUT S3 templates (markdown fallback only)
    # ─────────────────────────────────────────────────────────────────────────
    "eval_criteria": TemplateMapping(
        s3_filename="",  # No S3 template available
        placeholder_map={},
        file_type="md",
        description="Evaluation Criteria (markdown only)",
    ),

    "security_checklist": TemplateMapping(
        s3_filename="",  # No S3 template available
        placeholder_map={},
        file_type="md",
        description="IT Security Checklist (markdown only)",
    ),

    "section_508": TemplateMapping(
        s3_filename="",  # No S3 template available
        placeholder_map={},
        file_type="md",
        description="Section 508 Compliance Statement (markdown only)",
    ),

    "contract_type_justification": TemplateMapping(
        s3_filename="",  # No S3 template available
        placeholder_map={},
        file_type="md",
        description="Contract Type Justification D&F (markdown only)",
    ),
}


# ══════════════════════════════════════════════════════════════════════════════
# Helper Functions
# ══════════════════════════════════════════════════════════════════════════════

def get_template_mapping(doc_type: str) -> Optional[TemplateMapping]:
    """Get the template mapping for a document type.

    Args:
        doc_type: Document type identifier (e.g., "sow", "igce").

    Returns:
        TemplateMapping if found, None otherwise.
    """
    return TEMPLATE_REGISTRY.get(doc_type)


def list_available_templates() -> List[Dict[str, str]]:
    """List all registered templates with their metadata.

    Returns:
        List of dicts with doc_type, description, file_type, has_template.
    """
    return [
        {
            "doc_type": doc_type,
            "description": mapping.description,
            "file_type": mapping.file_type,
            "has_s3_template": mapping.has_template,
            "s3_filename": mapping.s3_filename,
        }
        for doc_type, mapping in TEMPLATE_REGISTRY.items()
    ]


def get_s3_key_for_template(doc_type: str, alternate_index: int = 0) -> Optional[str]:
    """Get the full S3 key for a template.

    Args:
        doc_type: Document type identifier.
        alternate_index: Index of alternate template (0 = primary).

    Returns:
        Full S3 key or None if not found.
    """
    mapping = TEMPLATE_REGISTRY.get(doc_type)
    if not mapping:
        return None

    if alternate_index == 0:
        return mapping.s3_key if mapping.has_template else None

    if alternate_index <= len(mapping.alternates):
        filename = mapping.alternates[alternate_index - 1]
        return f"{TEMPLATE_PREFIX}{filename}"

    return None
```

### 4.2 New File: `server/app/template_service.py`

```python
"""Template Service — Orchestrates S3 template fetching, population, and export.

This service handles:
1. Fetching DOCX/XLSX templates from S3 (with caching)
2. Populating {{PLACEHOLDER}} tokens with user data
3. Generating markdown previews for chat display
4. Falling back to markdown generators when templates unavailable

Usage:
    service = TemplateService(tenant_id, user_id)
    result = service.generate_document("sow", "IT Support SOW", {"description": "..."})
    # result.content_bytes -> populated DOCX
    # result.content_markdown -> preview for chat
"""

from __future__ import annotations

import io
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger("eagle.template_service")

# ══════════════════════════════════════════════════════════════════════════════
# Configuration
# ══════════════════════════════════════════════════════════════════════════════

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
CACHE_TTL_SECONDS = 60  # Template cache TTL (matches template_store.py)
S3_FETCH_TIMEOUT = 10   # Seconds before falling back to markdown


# ══════════════════════════════════════════════════════════════════════════════
# Lazy S3 Singleton (same pattern as agentic_service.py)
# ══════════════════════════════════════════════════════════════════════════════

_s3 = None


def _get_s3():
    """Get or create singleton S3 client."""
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3", region_name=AWS_REGION)
    return _s3


# ══════════════════════════════════════════════════════════════════════════════
# Template Cache (60-second TTL, same pattern as template_store.py)
# ══════════════════════════════════════════════════════════════════════════════

_template_cache: Dict[str, Dict] = {}


def _cache_get(bucket: str, key: str) -> Optional[bytes]:
    """Get cached template bytes if still fresh."""
    cache_key = f"{bucket}:{key}"
    entry = _template_cache.get(cache_key)
    if entry and time.time() < entry["ts"] + CACHE_TTL_SECONDS:
        logger.debug("Template cache hit: %s", key)
        return entry["data"]
    return None


def _cache_set(bucket: str, key: str, data: bytes) -> None:
    """Cache template bytes with current timestamp."""
    cache_key = f"{bucket}:{key}"
    _template_cache[cache_key] = {"ts": time.time(), "data": data}
    logger.debug("Template cached: %s (%d bytes)", key, len(data))


def _cache_invalidate(bucket: str, key: str) -> None:
    """Remove template from cache."""
    cache_key = f"{bucket}:{key}"
    _template_cache.pop(cache_key, None)


# ══════════════════════════════════════════════════════════════════════════════
# Result Data Class
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class TemplateResult:
    """Result of template-based document generation.

    Attributes:
        content_bytes: Populated document as bytes (DOCX/XLSX/MD).
        content_markdown: Markdown preview for chat display.
        file_type: Output format - "docx", "xlsx", or "md".
        source: Where the content came from - "s3_template" or "markdown_fallback".
        template_path: S3 key of template used (None for markdown fallback).
        error: Error message if generation partially failed.
    """
    content_bytes: bytes
    content_markdown: str
    file_type: str
    source: str
    template_path: Optional[str] = None
    error: Optional[str] = None


# ══════════════════════════════════════════════════════════════════════════════
# Template Service
# ══════════════════════════════════════════════════════════════════════════════

class TemplateService:
    """Main service for template-based document generation."""

    def __init__(self, tenant_id: str, user_id: str):
        """Initialize service with tenant and user context.

        Args:
            tenant_id: Tenant identifier for multi-tenancy.
            user_id: User identifier for per-user document paths.
        """
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.bucket = os.getenv("S3_BUCKET", "eagle-documents-695681773636-dev")

    def generate_document(
        self,
        doc_type: str,
        title: str,
        data: Dict[str, Any],
        output_format: str = "docx",
    ) -> TemplateResult:
        """Generate a document from S3 template or markdown fallback.

        This is the main entry point for document generation. It attempts to:
        1. Look up the template mapping for the doc_type
        2. Fetch the DOCX/XLSX template from S3
        3. Populate placeholders with the provided data
        4. Return the populated document with a markdown preview

        If any step fails, it falls back to the existing markdown generators.

        Args:
            doc_type: Document type (sow, igce, market_research, etc.).
            title: Document title.
            data: Dict of field values for placeholder population.
            output_format: Desired output - "docx", "xlsx", or "md".

        Returns:
            TemplateResult with populated content and metadata.
        """
        from .template_registry import get_template_mapping, TEMPLATE_BUCKET

        mapping = get_template_mapping(doc_type)

        # Attempt S3 template path
        if mapping and mapping.has_template:
            try:
                result = self._generate_from_template(
                    doc_type, title, data, mapping, TEMPLATE_BUCKET
                )
                if result:
                    return result
            except Exception as e:
                logger.warning(
                    "Template generation failed for %s, falling back to markdown: %s",
                    doc_type, e
                )

        # Markdown fallback
        return self._generate_markdown_fallback(doc_type, title, data, output_format)

    def _generate_from_template(
        self,
        doc_type: str,
        title: str,
        data: Dict[str, Any],
        mapping,  # TemplateMapping
        bucket: str,
    ) -> Optional[TemplateResult]:
        """Generate document by fetching and populating S3 template.

        Returns None if template fetch or population fails.
        """
        s3_key = mapping.s3_key

        # Fetch template (from cache or S3)
        template_bytes = self._fetch_template(bucket, s3_key)
        if not template_bytes:
            return None

        # Add title to data for placeholder replacement
        full_data = {"title": title, "date": datetime.utcnow().strftime("%Y-%m-%d"), **data}

        # Populate based on file type
        if mapping.file_type == "xlsx":
            populated_bytes = XLSXPopulator.populate(
                template_bytes, full_data, mapping.placeholder_map
            )
            preview = XLSXPopulator.extract_text(populated_bytes)
        else:
            populated_bytes = DOCXPopulator.populate(
                template_bytes, full_data, mapping.placeholder_map
            )
            preview = DOCXPopulator.extract_text(populated_bytes)

        return TemplateResult(
            content_bytes=populated_bytes,
            content_markdown=preview,
            file_type=mapping.file_type,
            source="s3_template",
            template_path=s3_key,
        )

    def _fetch_template(self, bucket: str, key: str) -> Optional[bytes]:
        """Fetch template from S3 with caching.

        Returns None if fetch fails.
        """
        # Check cache first
        cached = _cache_get(bucket, key)
        if cached:
            return cached

        # Fetch from S3
        try:
            s3 = _get_s3()
            response = s3.get_object(Bucket=bucket, Key=key)
            data = response["Body"].read()
            _cache_set(bucket, key, data)
            logger.info("Template fetched from S3: %s (%d bytes)", key, len(data))
            return data
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "NoSuchKey":
                logger.warning("Template not found in S3: %s", key)
            else:
                logger.error("S3 fetch error for %s: %s", key, e)
            return None
        except BotoCoreError as e:
            logger.error("S3 connection error for %s: %s", key, e)
            return None

    def _generate_markdown_fallback(
        self,
        doc_type: str,
        title: str,
        data: Dict[str, Any],
        output_format: str,
    ) -> TemplateResult:
        """Generate document using existing markdown generators.

        Falls back to this when S3 template is unavailable or population fails.
        """
        # Import existing generators from agentic_service
        from .agentic_service import (
            _generate_sow, _generate_igce, _generate_market_research,
            _generate_justification, _generate_acquisition_plan,
            _generate_eval_criteria, _generate_security_checklist,
            _generate_section_508, _generate_cor_certification,
            _generate_contract_type_justification,
        )

        generators = {
            "sow": _generate_sow,
            "igce": _generate_igce,
            "market_research": _generate_market_research,
            "justification": _generate_justification,
            "acquisition_plan": _generate_acquisition_plan,
            "eval_criteria": _generate_eval_criteria,
            "security_checklist": _generate_security_checklist,
            "section_508": _generate_section_508,
            "cor_certification": _generate_cor_certification,
            "contract_type_justification": _generate_contract_type_justification,
        }

        generator = generators.get(doc_type)
        if generator:
            markdown_content = generator(title, data)
        else:
            markdown_content = f"# {title}\n\nDocument type '{doc_type}' not supported."

        # Convert to DOCX if requested
        if output_format == "docx":
            from .document_export import markdown_to_docx
            content_bytes = markdown_to_docx(markdown_content, title)
            file_type = "docx"
        else:
            content_bytes = markdown_content.encode("utf-8")
            file_type = "md"

        return TemplateResult(
            content_bytes=content_bytes,
            content_markdown=markdown_content,
            file_type=file_type,
            source="markdown_fallback",
            template_path=None,
        )


# ══════════════════════════════════════════════════════════════════════════════
# DOCX Populator
# ══════════════════════════════════════════════════════════════════════════════

class DOCXPopulator:
    """Populate DOCX templates by replacing {{PLACEHOLDER}} tokens."""

    @staticmethod
    def populate(
        template_bytes: bytes,
        data: Dict[str, Any],
        placeholder_map: Dict[str, str],
    ) -> bytes:
        """Replace {{PLACEHOLDER}} tokens in DOCX with data values.

        Searches and replaces in:
        - Paragraphs (body text)
        - Table cells
        - Headers and footers

        Args:
            template_bytes: Raw DOCX file bytes.
            data: Dict of field values.
            placeholder_map: Maps data keys to placeholder strings.

        Returns:
            Populated DOCX as bytes.
        """
        from docx import Document

        doc = Document(io.BytesIO(template_bytes))

        # Build replacement map: placeholder string → formatted value
        replacements = {}
        for data_key, placeholder in placeholder_map.items():
            value = data.get(data_key, "")
            if isinstance(value, list):
                value = DOCXPopulator._format_list(value)
            elif isinstance(value, dict):
                value = DOCXPopulator._format_dict(value)
            replacements[placeholder] = str(value) if value else ""

        # Replace in body paragraphs
        for para in doc.paragraphs:
            DOCXPopulator._replace_in_paragraph(para, replacements)

        # Replace in tables
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for para in cell.paragraphs:
                        DOCXPopulator._replace_in_paragraph(para, replacements)

        # Replace in headers and footers
        for section in doc.sections:
            if section.header:
                for para in section.header.paragraphs:
                    DOCXPopulator._replace_in_paragraph(para, replacements)
            if section.footer:
                for para in section.footer.paragraphs:
                    DOCXPopulator._replace_in_paragraph(para, replacements)

        # Save to bytes
        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        return buffer.read()

    @staticmethod
    def _replace_in_paragraph(para, replacements: Dict[str, str]) -> None:
        """Replace placeholders in a paragraph while preserving formatting.

        Note: This simplified approach concatenates all runs into the first run.
        For complex formatting preservation, consider run-by-run replacement.
        """
        # Concatenate all run text
        full_text = "".join(run.text for run in para.runs)

        # Check if any replacements apply
        modified = False
        for placeholder, value in replacements.items():
            if placeholder in full_text:
                full_text = full_text.replace(placeholder, value)
                modified = True

        # Only modify if changes were made
        if modified and para.runs:
            # Put all text in first run, clear others
            para.runs[0].text = full_text
            for run in para.runs[1:]:
                run.text = ""

    @staticmethod
    def _format_list(items: list) -> str:
        """Format a list for insertion into DOCX.

        Handles both simple lists and lists of dicts.
        """
        if not items:
            return ""

        formatted = []
        for item in items:
            if isinstance(item, dict):
                # Format dict items (e.g., deliverables with dates)
                parts = [f"{k}: {v}" for k, v in item.items()]
                formatted.append(" - ".join(parts))
            else:
                formatted.append(str(item))

        return "\n".join(f"• {item}" for item in formatted)

    @staticmethod
    def _format_dict(data: dict) -> str:
        """Format a dict for insertion into DOCX."""
        return "\n".join(f"{k}: {v}" for k, v in data.items())

    @staticmethod
    def extract_text(content_bytes: bytes) -> str:
        """Extract text from DOCX for markdown preview.

        Returns paragraph text with basic formatting hints.
        """
        from docx import Document

        try:
            doc = Document(io.BytesIO(content_bytes))
            paragraphs = []

            for para in doc.paragraphs:
                text = para.text.strip()
                if not text:
                    continue

                # Add markdown heading markers based on style
                style_name = para.style.name if para.style else ""
                if "Heading 1" in style_name:
                    paragraphs.append(f"# {text}")
                elif "Heading 2" in style_name:
                    paragraphs.append(f"## {text}")
                elif "Heading 3" in style_name:
                    paragraphs.append(f"### {text}")
                else:
                    paragraphs.append(text)

            return "\n\n".join(paragraphs)
        except Exception as e:
            logger.warning("Failed to extract text from DOCX: %s", e)
            return "[Document preview unavailable]"


# ══════════════════════════════════════════════════════════════════════════════
# XLSX Populator
# ══════════════════════════════════════════════════════════════════════════════

class XLSXPopulator:
    """Populate XLSX templates by replacing {{PLACEHOLDER}} tokens in cells."""

    @staticmethod
    def populate(
        template_bytes: bytes,
        data: Dict[str, Any],
        placeholder_map: Dict[str, str],
    ) -> bytes:
        """Replace {{PLACEHOLDER}} tokens in XLSX cells with data values.

        Special handling for:
        - {{LINE_ITEMS}}: Inserts multiple rows for IGCE line items
        - Numeric values: Preserves as numbers for formula compatibility

        Args:
            template_bytes: Raw XLSX file bytes.
            data: Dict of field values.
            placeholder_map: Maps data keys to placeholder strings.

        Returns:
            Populated XLSX as bytes.
        """
        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(template_bytes))

        # Build replacement map
        replacements = {}
        for data_key, placeholder in placeholder_map.items():
            value = data.get(data_key, "")
            replacements[placeholder] = value

        # Process all sheets
        for sheet in wb.worksheets:
            for row in sheet.iter_rows():
                for cell in row:
                    if cell.value and isinstance(cell.value, str):
                        for placeholder, value in replacements.items():
                            if placeholder in cell.value:
                                # Special handling for line items (IGCE)
                                if placeholder == "{{LINE_ITEMS}}" and isinstance(value, list):
                                    XLSXPopulator._insert_line_items(sheet, cell, value)
                                else:
                                    # Replace placeholder with value
                                    new_value = cell.value.replace(placeholder, str(value) if value else "")
                                    # Try to preserve numeric types
                                    try:
                                        if new_value.replace(".", "").replace("-", "").isdigit():
                                            cell.value = float(new_value) if "." in new_value else int(new_value)
                                        else:
                                            cell.value = new_value
                                    except (ValueError, AttributeError):
                                        cell.value = new_value

        # Save to bytes
        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        return buffer.read()

    @staticmethod
    def _insert_line_items(sheet, start_cell, items: list) -> None:
        """Insert IGCE line items starting at the placeholder cell.

        Expected item format: {"description": str, "quantity": int, "unit_price": float}

        Inserts columns: Description | Quantity | Unit Price | Total
        """
        row = start_cell.row
        col = start_cell.column

        # Clear the placeholder cell
        start_cell.value = None

        for i, item in enumerate(items):
            desc = item.get("description", "")
            qty = item.get("quantity", 1)
            unit_price = item.get("unit_price", 0)
            total = qty * unit_price

            current_row = row + i
            sheet.cell(row=current_row, column=col).value = desc
            sheet.cell(row=current_row, column=col + 1).value = qty
            sheet.cell(row=current_row, column=col + 2).value = unit_price
            sheet.cell(row=current_row, column=col + 3).value = total

            # Add formula for total column (optional)
            # sheet.cell(row=current_row, column=col + 3).value = f"=B{current_row}*C{current_row}"

    @staticmethod
    def extract_text(content_bytes: bytes) -> str:
        """Extract text from XLSX for markdown preview.

        Creates a markdown table representation of the first sheet.
        """
        from openpyxl import load_workbook

        try:
            wb = load_workbook(io.BytesIO(content_bytes))
            lines = []

            for sheet in wb.worksheets:
                lines.append(f"## {sheet.title}")
                lines.append("")

                # Get max columns with data
                max_col = sheet.max_column or 1

                # Build markdown table (limit to first 20 rows)
                for row_idx, row in enumerate(sheet.iter_rows(max_row=20, max_col=max_col)):
                    cells = [str(cell.value) if cell.value is not None else "" for cell in row]
                    if any(cells):  # Skip empty rows
                        lines.append("| " + " | ".join(cells) + " |")

                        # Add header separator after first row
                        if row_idx == 0:
                            lines.append("| " + " | ".join(["---"] * len(cells)) + " |")

                lines.append("")

            return "\n".join(lines)
        except Exception as e:
            logger.warning("Failed to extract text from XLSX: %s", e)
            return "[Spreadsheet preview unavailable]"
```

### 4.3 Modified: `server/app/agentic_service.py`

Update `_exec_create_document()` (replace lines 1084-1140):

```python
def _exec_create_document(params: dict, tenant_id: str, session_id: str = None) -> dict:
    """Generate acquisition documents using S3 templates or markdown fallback.

    This function orchestrates document generation by:
    1. Validating the requested doc_type
    2. Delegating to TemplateService for template-based generation
    3. Saving the result to the user's S3 workspace
    4. Returning document metadata with markdown preview

    Args:
        params: Tool input containing:
            - doc_type: Document type (sow, igce, market_research, etc.)
            - title: Document title
            - data: Dict of field values for placeholder population
            - output_format: Optional output format (docx, xlsx, md)
        tenant_id: Tenant identifier for multi-tenancy
        session_id: Session identifier for user extraction

    Returns:
        Dict with document metadata and status
    """
    from .template_service import TemplateService

    doc_type = params.get("doc_type", "sow")
    title = params.get("title", "Untitled Acquisition")
    data = params.get("data", {})
    output_format = params.get("output_format", "docx")
    timestamp = time.strftime("%Y%m%d_%H%M%S")

    # Validate doc_type
    valid_types = {
        "sow", "igce", "market_research", "justification", "acquisition_plan",
        "eval_criteria", "security_checklist", "section_508",
        "cor_certification", "contract_type_justification"
    }
    if doc_type not in valid_types:
        return {
            "error": f"Unknown document type: {doc_type}",
            "supported_types": sorted(valid_types),
        }

    # Extract user_id from session
    user_id = _extract_user_id(session_id)

    # Generate document via TemplateService
    service = TemplateService(tenant_id, user_id)

    try:
        result = service.generate_document(doc_type, title, data, output_format)
    except Exception as e:
        logger.error("Document generation failed: %s", e, exc_info=True)
        return {
            "error": f"Document generation failed: {str(e)}",
            "document_type": doc_type,
            "title": title,
        }

    # Determine file extension and content type
    ext = result.file_type
    content_types = {
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "md": "text/markdown",
    }
    content_type = content_types.get(ext, "application/octet-stream")

    # Build S3 key for user's document workspace
    s3_key = f"eagle/{tenant_id}/{user_id}/documents/{doc_type}_{timestamp}.{ext}"
    bucket = os.getenv("S3_BUCKET", "eagle-documents-695681773636-dev")

    # Save to S3
    try:
        s3 = _get_s3()
        s3.put_object(
            Bucket=bucket,
            Key=s3_key,
            Body=result.content_bytes,
            ContentType=content_type,
        )
        save_status = "saved"
        save_location = f"s3://{bucket}/{s3_key}"
        logger.info("Document saved: %s (%d bytes)", s3_key, len(result.content_bytes))
    except (ClientError, BotoCoreError) as e:
        save_status = "generated_but_not_saved"
        save_location = f"S3 save failed: {str(e)}"
        logger.warning("Failed to save document to S3: %s", e)

    return {
        "document_type": doc_type,
        "title": title,
        "status": save_status,
        "s3_location": save_location,
        "s3_key": s3_key,
        "file_type": result.file_type,
        "source": result.source,
        "template_path": result.template_path,
        "content": result.content_markdown,
        "word_count": len(result.content_markdown.split()),
        "generated_at": datetime.utcnow().isoformat(),
        "note": "This is a draft document. Review and customize before official use.",
    }
```

### 4.4 Modified: `server/requirements.txt`

Add after line 17 (python-docx):

```
openpyxl>=3.1.0
```

---

## 5. Testing Strategy

### 5.1 Unit Tests

**New file**: `server/tests/test_template_service.py`

```python
"""Unit tests for template_service.py"""

import io
import pytest
from unittest.mock import MagicMock, patch

from app.template_service import (
    TemplateService, DOCXPopulator, XLSXPopulator, TemplateResult,
    _cache_get, _cache_set, _cache_invalidate,
)
from app.template_registry import (
    TEMPLATE_REGISTRY, TemplateMapping, get_template_mapping,
    list_available_templates, get_s3_key_for_template,
)


class TestTemplateRegistry:
    """Tests for template_registry.py"""

    def test_all_doc_types_have_mappings(self):
        """All 10 document types have registry entries."""
        expected_types = {
            "sow", "igce", "market_research", "justification", "acquisition_plan",
            "eval_criteria", "security_checklist", "section_508",
            "cor_certification", "contract_type_justification"
        }
        assert set(TEMPLATE_REGISTRY.keys()) == expected_types

    def test_get_template_mapping_returns_mapping(self):
        """get_template_mapping returns TemplateMapping for valid doc_type."""
        mapping = get_template_mapping("sow")
        assert isinstance(mapping, TemplateMapping)
        assert mapping.s3_filename == "statement-of-work-template-eagle-v2.docx"

    def test_get_template_mapping_returns_none_for_invalid(self):
        """get_template_mapping returns None for unknown doc_type."""
        assert get_template_mapping("invalid_type") is None

    def test_has_template_property(self):
        """has_template returns True for templates with S3 files."""
        sow = get_template_mapping("sow")
        eval_criteria = get_template_mapping("eval_criteria")

        assert sow.has_template is True
        assert eval_criteria.has_template is False

    def test_list_available_templates(self):
        """list_available_templates returns all templates with metadata."""
        templates = list_available_templates()
        assert len(templates) == 10
        assert all("doc_type" in t for t in templates)
        assert all("has_s3_template" in t for t in templates)


class TestTemplateCache:
    """Tests for template caching functions."""

    def test_cache_set_and_get(self):
        """Cache stores and retrieves template bytes."""
        _cache_set("bucket", "test/key.docx", b"test content")
        result = _cache_get("bucket", "test/key.docx")
        assert result == b"test content"

    def test_cache_miss_returns_none(self):
        """Cache returns None for missing entries."""
        result = _cache_get("bucket", "nonexistent/key.docx")
        assert result is None

    def test_cache_invalidate(self):
        """Cache invalidation removes entry."""
        _cache_set("bucket", "to/invalidate.docx", b"content")
        _cache_invalidate("bucket", "to/invalidate.docx")
        result = _cache_get("bucket", "to/invalidate.docx")
        assert result is None


class TestDOCXPopulator:
    """Tests for DOCXPopulator class."""

    def test_format_list_simple(self):
        """_format_list handles simple string lists."""
        items = ["Item 1", "Item 2", "Item 3"]
        result = DOCXPopulator._format_list(items)
        assert "• Item 1" in result
        assert "• Item 2" in result

    def test_format_list_dicts(self):
        """_format_list handles list of dicts."""
        items = [{"name": "Task 1", "due": "2026-01-01"}]
        result = DOCXPopulator._format_list(items)
        assert "name: Task 1" in result

    def test_format_dict(self):
        """_format_dict converts dict to string."""
        data = {"key1": "value1", "key2": "value2"}
        result = DOCXPopulator._format_dict(data)
        assert "key1: value1" in result


class TestXLSXPopulator:
    """Tests for XLSXPopulator class."""

    def test_insert_line_items_calculates_total(self):
        """Line items calculate total = qty * unit_price."""
        # This would require a real XLSX fixture
        pass


class TestTemplateService:
    """Integration tests for TemplateService."""

    @patch("app.template_service._get_s3")
    def test_generate_document_uses_s3_template(self, mock_get_s3):
        """generate_document fetches S3 template when available."""
        # Setup mock S3 client
        mock_s3 = MagicMock()
        mock_get_s3.return_value = mock_s3

        # Create minimal DOCX for testing
        from docx import Document
        doc = Document()
        doc.add_paragraph("{{TITLE}}")
        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)

        mock_s3.get_object.return_value = {"Body": io.BytesIO(buffer.read())}

        service = TemplateService("test-tenant", "test-user")
        result = service.generate_document("sow", "Test SOW", {"description": "Test"})

        assert result.source == "s3_template"
        assert result.file_type == "docx"

    @patch("app.template_service._get_s3")
    def test_generate_document_falls_back_to_markdown(self, mock_get_s3):
        """generate_document falls back to markdown when S3 fails."""
        mock_s3 = MagicMock()
        mock_get_s3.return_value = mock_s3
        mock_s3.get_object.side_effect = Exception("S3 error")

        service = TemplateService("test-tenant", "test-user")
        result = service.generate_document("sow", "Test SOW", {})

        assert result.source == "markdown_fallback"
        assert "STATEMENT OF WORK" in result.content_markdown
```

### 5.2 Validation Commands

```bash
# 1. Install dependencies
cd server
pip install -r requirements.txt

# 2. Run new unit tests
python -m pytest tests/test_template_service.py -v

# 3. Run existing document pipeline tests (regression)
python -m pytest tests/test_document_pipeline.py -v

# 4. Lint new files
ruff check app/template_registry.py app/template_service.py

# 5. Type hints (optional)
mypy app/template_registry.py app/template_service.py --ignore-missing-imports

# 6. Start server and test manually
uvicorn app.main:app --reload --port 8000

# 7. Test via curl
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: test-tenant" \
  -H "X-User-ID: test-user" \
  -d '{
    "message": "Create a Statement of Work for cloud migration services",
    "session_id": "test-session-001"
  }'

# 8. Verify DOCX saved to S3
aws s3 ls s3://eagle-documents-695681773636-dev/eagle/test-tenant/test-user/documents/ \
  | grep -E "\.docx$"

# 9. Download and inspect generated DOCX
aws s3 cp s3://eagle-documents-695681773636-dev/eagle/test-tenant/test-user/documents/sow_*.docx ./test-output.docx
open test-output.docx  # macOS
```

---

## 6. Error Handling Matrix

| Scenario | Detection | Response | User Impact |
|----------|-----------|----------|-------------|
| S3 template not found | `ClientError` with `NoSuchKey` | Log warning, use markdown fallback | Document generated with basic formatting |
| S3 timeout | `BotoCoreError` or timeout | Fall back to markdown | Slight delay, then document generated |
| Template corrupted | python-docx `PackageNotFoundError` | Fall back to markdown | Document generated with basic formatting |
| Placeholder not found | No match in text | Leave placeholder as-is, log warning | Document has `{{UNFILLED}}` markers |
| openpyxl not installed | `ImportError` | Fall back to markdown for XLSX | IGCE as markdown table |
| S3 save failure | `ClientError` on put_object | Return `generated_but_not_saved` | Content in response, not persisted |
| Invalid doc_type | Not in valid_types set | Return error with supported types | Clear error message |

---

## 7. Future Enhancements (Out of Scope)

1. **Tenant-specific template overrides** — Integrate with `template_store.py` for tenant customization
2. **Admin UI for template management** — Upload/preview/activate templates
3. **Template versioning** — Select v1, v2, etc. via API parameter
4. **PDF output option** — Convert populated DOCX to PDF
5. **Template placeholder audit** — Script to verify S3 templates have `{{PLACEHOLDER}}` markers
6. **A/B testing** — Feature flag for gradual rollout
7. **Metrics** — Track template vs fallback usage rates

---

## 8. Rollback Plan

If issues arise after deployment:

1. **Immediate**: Set `USE_TEMPLATE_SERVICE=false` env var (requires env var check in code)
2. **Quick fix**: Revert `_exec_create_document()` to previous implementation
3. **Full rollback**: Remove new files, revert requirements.txt

The existing `_generate_*()` functions remain unchanged and serve as the fallback, ensuring no regression in baseline functionality.
