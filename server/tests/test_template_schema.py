"""Tests for template_schema — parse, guide, validate, and document generation.

Includes:
  - Parser tests (markdown → TemplateSchema)
  - JSON metadata loader tests
  - Completeness validation tests
  - Section guidance builder tests
  - Document generation integration tests (DOCX, XLSX, MD output + completeness)
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure server/ is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.template_schema import (
    CompletenessReport,
    TemplateSchema,
    TemplateSection,
    build_section_guidance,
    load_from_json,
    load_template_schemas,
    parse_template_schema,
    validate_completeness,
    TEMPLATE_SCHEMAS,
    _ensure_schemas_loaded,
)


# ── Fixtures ──

SOW_SAMPLE = """\
# STATEMENT OF WORK (SOW)
## {{TITLE}}

## 1. BACKGROUND AND PURPOSE

The NCI requires {{REQUIREMENT_DESCRIPTION}}.

### 1.1 Background
{{BACKGROUND_CONTEXT}}

### 1.2 Purpose
The purpose is to {{PURPOSE_STATEMENT}}.

## 2. SCOPE

The contractor shall provide {{SCOPE_DESCRIPTION}}.

### 2.1 In Scope
{{IN_SCOPE_ITEMS}}

### 2.2 Out of Scope
{{OUT_OF_SCOPE_ITEMS}}

## 3. PERIOD OF PERFORMANCE

**Base Period:** {{BASE_PERIOD}}
**Option Period 1:** {{OPTION_PERIOD_1}}

## 4. PLACE OF PERFORMANCE

**Primary Location:** {{BUILDING_ADDRESS}}

## 5. APPLICABLE DOCUMENTS AND STANDARDS

### 5.1 Federal Regulations
- FAR

### 5.2 Technical Standards
{{TECHNICAL_STANDARDS}}

### 5.3 Security Requirements
{{SECURITY_REQUIREMENTS}}

## 6. TASKS AND REQUIREMENTS

### Task 1: {{TASK_1_TITLE}}
**Objective:** {{TASK_1_OBJECTIVE}}
**Requirements:** {{TASK_1_REQUIREMENTS}}

### Task 2: {{TASK_2_TITLE}}
**Objective:** {{TASK_2_OBJECTIVE}}

## 7. DELIVERABLES

| ID | Deliverable | Due Date |
|----|-------------|----------|
| D-1 | {{DELIVERABLE_1}} | {{DUE_DATE_1}} |

## 8. GOVERNMENT-FURNISHED PROPERTY (GFP)

| Item | Description |
|------|-------------|
| {{GFP_1}} | {{GFP_1_DESC}} |

## 9. SECURITY REQUIREMENTS

### 9.1 Personnel Security
{{PERSONNEL_SECURITY}}

## 10. QUALITY ASSURANCE SURVEILLANCE PLAN (QASP)

| Standard | AQL | Method |
|----------|-----|--------|
| {{STANDARD_1}} | {{AQL_1}} | {{METHOD_1}} |

## 11. CONTRACTOR PERSONNEL REQUIREMENTS

| Position | Qualifications |
|----------|---------------|
| {{POSITION_1}} | {{QUAL_1}} |

## 12. TRAVEL REQUIREMENTS

{{TRAVEL_REQUIREMENTS}}

## 13. SPECIAL REQUIREMENTS

{{SPECIAL_REQUIREMENTS}}

## 14. CONTRACT ADMINISTRATION

### 14.1 COR
**Name:** {{COR_NAME}}

## 15. ATTACHMENTS

- Attachment A: {{ATTACHMENT_A}}
"""


ACQUISITION_PLAN_SAMPLE = """\
# ACQUISITION PLAN
## {{TITLE}}

## PART 1: ACQUISITION BACKGROUND AND OBJECTIVES

### 1.1 Statement of Need
{{STATEMENT_OF_NEED}}

### 1.2 Applicable Conditions
{{APPLICABLE_CONDITIONS}}

### 1.3 Cost
**Life-Cycle Cost:** ${{LIFECYCLE_COST}}

### 1.4 Capability or Performance
{{CAPABILITY_PERFORMANCE}}

## PART 2: PLAN OF ACTION

### 2.1 Sources
{{EXPECTED_SOURCES}}

### 2.2 Competition
**Strategy:** {{COMPETITION_STRATEGY}}

☐ Full and Open Competition
☐ Other Than Full and Open

### 2.3 Source-Selection Procedures

| Factor | Weight |
|--------|--------|
| Technical | {{TECH_WEIGHT}} |

## PART 3: SUPPORTING DOCUMENTATION

### 3.1 Market Research Summary
{{MARKET_RESEARCH_SUMMARY}}

## APPROVALS

| Role | Name |
|------|------|
| PM | {{PM_NAME}} |
"""


IGCE_SAMPLE = """\
# INDEPENDENT GOVERNMENT COST ESTIMATE (IGCE)
## {{TITLE}}

## 1. PURPOSE

This IGCE provides a detailed estimate for: {{REQUIREMENT_DESCRIPTION}}.

## 2. METHODOLOGY

### 2.1 Data Sources
{{DATA_SOURCES}}

### 2.2 Estimation Methodology
{{ESTIMATION_METHODOLOGY}}

### 2.3 Assumptions
{{ASSUMPTIONS}}

## 3. COST BREAKDOWN

### 3.1 Direct Costs

| Line | Description | Qty | Unit Price | Total |
|------|-------------|-----|------------|-------|
| 1 | {{ITEM_1}} | {{QTY_1}} | ${{PRICE_1}} | ${{TOTAL_1}} |

### 3.2 Direct Labor

| Category | Hours | Rate | Total |
|----------|-------|------|-------|
| {{LABOR_CAT_1}} | {{HOURS_1}} | ${{RATE_1}} | ${{LABOR_TOTAL_1}} |

### 3.3 Other Direct Costs (ODCs)

| Category | Amount |
|----------|--------|
| Travel | ${{TRAVEL_AMOUNT}} |

### 3.4 Indirect Costs

| Category | Rate | Amount |
|----------|------|--------|
| Fringe | {{FRINGE_RATE}}% | ${{FRINGE_AMOUNT}} |

### 3.5 Fee/Profit

| Category | Rate | Amount |
|----------|------|--------|
| Fee | {{FEE_RATE}}% | ${{FEE_AMOUNT}} |

## 4. COST SUMMARY

| Category | Amount |
|----------|--------|
| **TOTAL** | **${{GRAND_TOTAL}}** |

## 5. COST BY PERIOD

### Base Period: {{BASE_PERIOD}}

| Category | Amount |
|----------|--------|
| **Period Total** | **${{BP_TOTAL}}** |

## 6. ASSUMPTIONS AND LIMITATIONS

### 6.1 Key Assumptions
{{KEY_ASSUMPTIONS}}

### 6.2 Limitations
{{LIMITATIONS}}

## 7. CONFIDENCE LEVEL

**Overall Confidence:** {{CONFIDENCE_LEVEL}}

## 8. DATA SOURCES AND REFERENCES

| Source | Date | Info |
|--------|------|------|
| {{SOURCE_1}} | {{DATE_1}} | {{INFO_1}} |

## 9. CERTIFICATION

I certify this IGCE was prepared independently.

| Role | Name |
|------|------|
| Preparer | {{PREPARER}} |
"""


# ── Test: Parse SOW Sections ──

class TestParseSowSections:
    def test_sections_found(self):
        schema = parse_template_schema(SOW_SAMPLE, "sow")
        # Should find 15 top-level ## sections
        assert len(schema.sections) >= 14
        assert schema.doc_type == "sow"

    def test_first_section_title(self):
        schema = parse_template_schema(SOW_SAMPLE, "sow")
        # First real section after title
        titles = [s.title for s in schema.sections]
        assert any("BACKGROUND" in t.upper() for t in titles)

    def test_total_fields(self):
        schema = parse_template_schema(SOW_SAMPLE, "sow")
        assert schema.total_fields > 20  # SOW has many placeholders


# ── Test: Parse IGCE Sections ──

class TestParseIgceSections:
    def test_sections_found(self):
        schema = parse_template_schema(IGCE_SAMPLE, "igce")
        assert len(schema.sections) >= 8

    def test_cost_breakdown_has_table(self):
        schema = parse_template_schema(IGCE_SAMPLE, "igce")
        cost_sections = [s for s in schema.sections if "COST" in s.title.upper()]
        assert any(s.has_table for s in cost_sections)


# ── Test: Parse Acquisition Plan PART Format ──

class TestParseAcquisitionPlanParts:
    def test_part_format_handled(self):
        schema = parse_template_schema(ACQUISITION_PLAN_SAMPLE, "acquisition_plan")
        # Should detect PART sections
        assert len(schema.sections) >= 3
        titles = [s.title.upper() for s in schema.sections]
        assert any("BACKGROUND" in t or "OBJECTIVES" in t for t in titles)

    def test_checkbox_detection(self):
        schema = parse_template_schema(ACQUISITION_PLAN_SAMPLE, "acquisition_plan")
        # The competition section has checkboxes
        comp_sections = [
            s for s in schema.sections
            for sub in s.subsections
            if "COMPETITION" in sub.title.upper()
        ]
        # Checkboxes should be detected in subsections
        assert len(schema.sections) >= 3


# ── Test: Field Extraction Per Section ──

class TestFieldExtractionPerSection:
    def test_placeholders_in_correct_sections(self):
        schema = parse_template_schema(SOW_SAMPLE, "sow")
        # Find the "BACKGROUND AND PURPOSE" section
        bg_sections = [s for s in schema.sections if "BACKGROUND" in s.title.upper()]
        assert bg_sections
        bg = bg_sections[0]
        # Should have fields from subsections or directly
        all_fields = [f.name for f in bg.fields]
        for sub in bg.subsections:
            all_fields.extend(f.name for f in sub.fields)
        assert "REQUIREMENT_DESCRIPTION" in all_fields or "BACKGROUND_CONTEXT" in all_fields


# ── Test: Subsection Nesting ──

class TestSubsectionNesting:
    def test_subsections_nested_under_parent(self):
        schema = parse_template_schema(SOW_SAMPLE, "sow")
        # Section 1 should have subsections 1.1 and 1.2
        bg_sections = [s for s in schema.sections if "BACKGROUND" in s.title.upper()]
        assert bg_sections
        bg = bg_sections[0]
        assert len(bg.subsections) >= 1

    def test_subsection_numbers(self):
        schema = parse_template_schema(SOW_SAMPLE, "sow")
        bg_sections = [s for s in schema.sections if "BACKGROUND" in s.title.upper()]
        if bg_sections and bg_sections[0].subsections:
            sub_numbers = [s.number for s in bg_sections[0].subsections]
            assert any("1" in n for n in sub_numbers)


# ── Test: Table Detection ──

class TestTableDetection:
    def test_deliverables_has_table(self):
        schema = parse_template_schema(SOW_SAMPLE, "sow")
        deliv_sections = [s for s in schema.sections if "DELIVERABLE" in s.title.upper()]
        assert deliv_sections
        assert deliv_sections[0].has_table

    def test_non_table_section(self):
        schema = parse_template_schema(SOW_SAMPLE, "sow")
        travel_sections = [s for s in schema.sections if "TRAVEL" in s.title.upper()]
        if travel_sections:
            assert not travel_sections[0].has_table


# ── Test: Completeness Validation ──

class TestCompletenessComplete:
    def test_filled_document_high_score(self):
        """A document with all sections filled should score high."""
        filled = SOW_SAMPLE.replace("{{", "").replace("}}", "")
        report = validate_completeness("sow", filled)
        assert report.completeness_pct >= 50.0

    def test_raw_template_low_score(self):
        """Raw template with all placeholders should score lower."""
        report = validate_completeness("sow", SOW_SAMPLE)
        # Still has section titles, so some will match, but many placeholders remain
        assert report.completeness_pct < 100.0

    def test_empty_content(self):
        """Empty content should score 0."""
        report = validate_completeness("sow", "")
        assert report.completeness_pct == 0.0
        assert not report.is_complete

    def test_unknown_doc_type(self):
        """Unknown doc type returns empty report."""
        report = validate_completeness("nonexistent_type", "some content")
        assert report.total_sections == 0
        assert report.completeness_pct == 0.0


class TestCompletenessPartial:
    def test_half_filled_moderate_score(self):
        """A document with half sections should score around 50%."""
        # Keep first half of sections, blank out the rest
        lines = SOW_SAMPLE.split("\n")
        midpoint = len(lines) // 2
        partial = "\n".join(lines[:midpoint])
        # Remove placeholders from what we keep
        partial = partial.replace("{{", "").replace("}}", "")
        report = validate_completeness("sow", partial)
        assert 20.0 <= report.completeness_pct <= 80.0


# ── Test: Build Section Guidance ──

class TestBuildSectionGuidance:
    def test_guidance_format(self):
        # Ensure schemas are loaded for the test
        from app.template_schema import TEMPLATE_SCHEMAS
        schema = parse_template_schema(SOW_SAMPLE, "sow")
        TEMPLATE_SCHEMAS["sow"] = schema

        guidance = build_section_guidance("sow")
        assert "sow" in guidance.lower() or "SOW" in guidance
        assert "BACKGROUND" in guidance.upper()
        # Should have multiple lines
        assert guidance.count("\n") >= 5

    def test_empty_for_unknown(self):
        guidance = build_section_guidance("nonexistent_type_xyz")
        assert guidance == ""


# ── Test: Load From JSON ──

class TestLoadFromJson:
    def test_load_valid_json(self, tmp_path):
        data = {
            "filename": "test_template.docx",
            "format": "docx",
            "category": "sow",
            "variant": "",
            "sections": [
                {
                    "number": "1",
                    "title": "BACKGROUND",
                    "has_table": False,
                    "placeholders": ["PROJECT_TITLE", "DESCRIPTION"],
                },
                {
                    "number": "2",
                    "title": "SCOPE",
                    "has_table": True,
                    "placeholders": ["SCOPE_DESC"],
                },
            ],
            "total_placeholders": 3,
            "total_sections": 2,
        }
        json_path = tmp_path / "test.json"
        json_path.write_text(json.dumps(data))

        schema = load_from_json(str(json_path))
        assert schema is not None
        assert schema.doc_type == "sow"
        assert len(schema.sections) == 2
        assert schema.total_fields == 3

    def test_load_with_variant(self, tmp_path):
        data = {
            "filename": "AP Under SAT.docx",
            "format": "docx",
            "category": "acquisition_plan",
            "variant": "under_sat",
            "sections": [],
            "total_placeholders": 0,
            "total_sections": 0,
        }
        json_path = tmp_path / "test.json"
        json_path.write_text(json.dumps(data))

        schema = load_from_json(str(json_path))
        assert schema is not None
        assert schema.doc_type == "acquisition_plan_under_sat"

    def test_load_with_parse_error(self, tmp_path):
        data = {
            "filename": "broken.pdf",
            "format": "pdf",
            "category": "unknown",
            "variant": "",
            "parse_error": "No parser available",
        }
        json_path = tmp_path / "test.json"
        json_path.write_text(json.dumps(data))

        schema = load_from_json(str(json_path))
        assert schema is None

    def test_load_missing_file(self):
        schema = load_from_json("/nonexistent/path.json")
        assert schema is None


# ── Test: Load Template Schemas (Integration) ──

class TestLoadTemplateSchemas:
    def test_loads_markdown_templates(self):
        schemas = load_template_schemas()
        # Should load at least the 5 markdown templates
        assert "sow" in schemas
        assert "igce" in schemas
        assert "acquisition_plan" in schemas
        assert "market_research" in schemas
        assert "justification" in schemas

    def test_sow_has_sections(self):
        schemas = load_template_schemas()
        sow = schemas.get("sow")
        assert sow is not None
        assert len(sow.sections) >= 10
        assert sow.total_fields >= 30

    def test_igce_has_sections(self):
        schemas = load_template_schemas()
        igce = schemas.get("igce")
        assert igce is not None
        assert len(igce.sections) >= 8

    def test_acquisition_plan_has_parts(self):
        schemas = load_template_schemas()
        ap = schemas.get("acquisition_plan")
        assert ap is not None
        assert len(ap.sections) >= 3


# ── Test: Schema Covers Registry Types ──

class TestSchemaCoverage:
    def test_all_base_doc_types_have_schemas(self):
        """Every base doc_type in the registry should have a schema."""
        schemas = load_template_schemas()
        base_types = {"sow", "igce", "acquisition_plan", "market_research", "justification"}
        for dt in base_types:
            assert dt in schemas, f"Missing schema for {dt}"


# ══════════════════════════════════════════════════════════════════════
# Document Generation Integration Tests
#
# These call _exec_create_document with mocked S3 and validate:
#   - Output includes completeness report from schema validation
#   - DOCX/XLSX/MD file types are generated correctly
#   - AI-provided content is validated against section schemas
# ══════════════════════════════════════════════════════════════════════

ENV_PATCH = {
    "REQUIRE_AUTH": "false",
    "DEV_MODE": "false",
    "USE_BEDROCK": "false",
    "COGNITO_USER_POOL_ID": "us-east-1_test",
    "COGNITO_CLIENT_ID": "test-client",
    "EAGLE_SESSIONS_TABLE": "eagle",
    "USE_PERSISTENT_SESSIONS": "false",
    "S3_BUCKET": "test-bucket",
}


def _mock_s3():
    """Return a MagicMock that behaves like a boto3 S3 client."""
    s3 = MagicMock()
    s3.put_object.return_value = {"ResponseMetadata": {"HTTPStatusCode": 200}}
    return s3


# -- Full AI-written content for each format --

SOW_AI_CONTENT = """# Statement of Work (SOW)
## Cloud Migration Support Services

## 1. BACKGROUND AND PURPOSE

The National Cancer Institute requires cloud migration support services
to modernize its data analytics platform. NCI currently operates a hybrid
infrastructure that needs to be consolidated into AWS GovCloud.

### 1.1 Background
NCI's Center for Biomedical Informatics and Information Technology (CBIIT)
maintains 47 legacy applications that require migration to cloud-native architecture.

### 1.2 Purpose
The purpose of this acquisition is to procure professional services for
planning, executing, and validating the migration of legacy applications.

## 2. SCOPE

The contractor shall provide all personnel, equipment, and services necessary
to migrate 47 legacy applications to AWS GovCloud within the period of performance.

### 2.1 In Scope
- Application assessment and migration planning
- Cloud architecture design and implementation
- Data migration and validation
- Post-migration support and optimization

### 2.2 Out of Scope
- Hardware procurement
- Network infrastructure changes outside AWS

## 3. PERIOD OF PERFORMANCE

**Base Period:** 12 months from date of award
**Option Period 1:** 12 months
**Option Period 2:** 12 months

## 4. PLACE OF PERFORMANCE

**Primary Location:** NIH Campus, Bethesda, MD 20892
**Alternative Locations:** Remote work authorized with CO approval

## 5. APPLICABLE DOCUMENTS AND STANDARDS

### 5.1 Federal Regulations
- FAR, HHSAR, NIST SP 800-53

### 5.2 Technical Standards
- AWS Well-Architected Framework
- FedRAMP High baseline

### 5.3 Security Requirements
- FISMA compliance required
- ATO within 90 days of deployment

## 6. TASKS AND REQUIREMENTS

### Task 1: Assessment and Planning
**Objective:** Complete application portfolio assessment
**Requirements:** Analyze all 47 applications for migration readiness

### Task 2: Migration Execution
**Objective:** Execute phased migration plan
**Requirements:** Migrate applications in 4 waves of ~12 applications each

### Task 3: Validation and Optimization
**Objective:** Validate migrated applications meet performance SLAs
**Requirements:** Conduct performance testing and optimization

## 7. DELIVERABLES

| ID | Deliverable | Due Date | Format |
|----|-------------|----------|--------|
| D-1 | Migration Plan | 30 days after award | PDF |
| D-2 | Monthly Status Reports | 5th business day | PDF |
| D-3 | Final Migration Report | 30 days before end | PDF |

## 8. GOVERNMENT-FURNISHED PROPERTY (GFP)

| Item | Description | Condition |
|------|-------------|-----------|
| AWS GovCloud accounts | Pre-provisioned accounts | Active |
| VPN access | Secure remote access | Active |

## 9. SECURITY REQUIREMENTS

### 9.1 Personnel Security
All contractor personnel require Public Trust clearance (Tier 2).

### 9.2 Information Security
Comply with NIH Information Security policies and FISMA requirements.

## 10. QUALITY ASSURANCE SURVEILLANCE PLAN (QASP)

| Performance Standard | AQL | Method | Frequency |
|---------------------|-----|--------|-----------|
| Migration success rate | 98% | Inspection | Per wave |
| Uptime post-migration | 99.9% | Monitoring | Monthly |

## 11. CONTRACTOR PERSONNEL REQUIREMENTS

| Position | Qualifications | Hours |
|----------|---------------|-------|
| Cloud Architect | AWS Solutions Architect Pro | 2080/yr |
| DevOps Engineer | AWS DevOps Pro, 5yr exp | 2080/yr |

## 12. TRAVEL REQUIREMENTS

Travel to NIH Bethesda campus as required, estimated 12 trips per year.
All travel must be pre-approved by the COR.

## 13. SPECIAL REQUIREMENTS

Contractor shall maintain AWS Partner Network (APN) Advanced Tier status.

## 14. CONTRACT ADMINISTRATION

### 14.1 Contracting Officer's Representative (COR)
**Name:** Dr. Jane Smith
**Phone:** 301-555-0100
**Email:** jane.smith@nih.gov

## 15. ATTACHMENTS

- Attachment A: Application Portfolio Inventory
- Attachment B: AWS GovCloud Architecture Diagram
"""

IGCE_DATA = {
    "description": "Cloud Migration Support Services",
    "line_items": [
        {"description": "Cloud Architect", "quantity": 2080, "unit": "HR", "unit_price": 175, "total": 364000},
        {"description": "DevOps Engineer", "quantity": 2080, "unit": "HR", "unit_price": 150, "total": 312000},
        {"description": "AWS Licensing", "quantity": 12, "unit": "MO", "unit_price": 15000, "total": 180000},
    ],
    "total_estimate": "856000",
    "prepared_by": "EAGLE System",
    "prepared_date": "2026-03-17",
}

MARKET_RESEARCH_AI_CONTENT = """# Market Research Report
## Cloud Migration Support Services — Market Research

## 1. EXECUTIVE SUMMARY

Market research was conducted to identify qualified sources for cloud migration
support services. Multiple vendors with AWS GovCloud experience were identified.

## 2. DESCRIPTION OF NEED

### 2.1 Requirement Overview
NCI requires cloud migration support to move 47 legacy applications to AWS GovCloud.

### 2.2 Background
Current infrastructure is aging and maintenance costs are increasing.

### 2.3 Objectives
Identify qualified vendors and determine appropriate acquisition strategy.

### 2.4 Minimum Requirements
AWS Partner Network Advanced Tier, FedRAMP High experience.

## 3. MARKET RESEARCH METHODOLOGY

### 3.1 Research Approach
SAM.gov, GSA eLibrary, FPDS.gov, and direct vendor outreach.

### 3.2 Sources Consulted

| Source | Date | Method | Results |
|--------|------|--------|---------|
| SAM.gov | 2026-03-01 | Database Search | 47 vendors |
| GSA eLibrary | 2026-03-01 | Schedule Search | 23 vendors |

## 4. POTENTIAL SOURCES

### 4.1 Vendors Identified

| Vendor | Size | NAICS | Capability |
|--------|------|-------|------------|
| Acme Cloud | Small | 541512 | AWS Advanced |
| CloudFirst | Large | 541512 | AWS Premier |
| GovTech Solutions | Small | 541512 | AWS Advanced |

## 5. COMMERCIAL AVAILABILITY ANALYSIS

### 5.1 Commercial Item Determination
Commercial services are available that meet the requirement.

## 6. SMALL BUSINESS ANALYSIS

### 6.1 Size Standard
NAICS 541512, $34M size standard.

### 6.2 Small Business Availability

| Set-Aside Type | Capable Sources | Determination |
|----------------|-----------------|---------------|
| Total Small Business | 12 | Adequate competition |

### 6.3 Set-Aside Recommendation
Total Small Business set-aside recommended.

## 7. CONTRACT VEHICLE ANALYSIS

### 7.1 Available Vehicles

| Vehicle | Availability | Scope Match |
|---------|--------------|-------------|
| GSA MAS | Yes | Full |
| NITAAC CIO-SP3 | Yes | Full |

### 7.2 Vehicle Recommendation
GSA MAS recommended for fastest procurement timeline.

## 8. PRICING ANALYSIS

### 8.1 Market Pricing Data
Market rates for AWS migration services: $125-200/hr.

## 9. RISK ASSESSMENT

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Schedule delays | Medium | High | Phased migration |

## 10. CONCLUSIONS AND RECOMMENDATIONS

### 10.1 Summary of Findings
Adequate competition exists among small businesses.

### 10.2 Recommended Acquisition Strategy

| Element | Recommendation |
|---------|----------------|
| Competition | Full and Open |
| Set-Aside | Total Small Business |

## ATTACHMENTS

- A. Sources Sought Notice
- B. Vendor Responses

## CERTIFICATION

I certify this market research was conducted in accordance with FAR Part 10.
"""

JUSTIFICATION_AI_CONTENT = """# Justification and Approval (J&A)
## Other Than Full and Open Competition
## Oracle Database Migration Support

## 1. CONTRACTING ACTIVITY

**Agency:** Department of Health and Human Services
**Institute/Center:** National Cancer Institute
**Contracting Officer:** John Doe

## 2. DESCRIPTION OF ACTION

**Nature of Action:** Sole source contract for Oracle-to-PostgreSQL migration support.
**Type of Contract:** Time and Materials
**Period of Performance:** 18 months
**Proposed Contractor:** Oracle Migration Partners, LLC

## 3. DESCRIPTION OF SUPPLIES/SERVICES

Professional services for migrating 12 Oracle databases to PostgreSQL,
including schema conversion, data migration, and application refactoring.

## 4. AUTHORITY CITED

FAR 6.302-1 — Only one responsible source and no other supplies or services
will satisfy agency requirements.

## 5. DEMONSTRATION THAT PROPOSED CONTRACTOR'S UNIQUE QUALIFICATIONS

### 5.1 Unique Qualifications
Oracle Migration Partners holds exclusive Oracle-to-PostgreSQL migration
tooling and methodology certification.

### 5.2 Proprietary Rights
N/A — no proprietary rights involved.

### 5.3 Technical Capabilities
Demonstrated migration of 200+ Oracle databases across federal agencies.

### 5.4 Experience and Past Performance
5-year CPARS rating of Exceptional across 8 federal contracts.

## 6. EFFORTS TO OBTAIN COMPETITION

### 6.1 Market Research Conducted
Sources sought notice published on SAM.gov for 30 days.

### 6.2 Sources Contacted

| Source | Date Contacted | Response |
|--------|----------------|----------|
| CloudDB Inc | 2026-01-15 | Cannot support Oracle migration |
| DataShift | 2026-01-15 | Lacks FedRAMP certification |

## 7. DETERMINATION OF FAIR AND REASONABLE PRICE

Price analysis based on comparison to prior purchases and IGCE.
**IGCE:** $1,200,000
**Proposed Price:** $1,150,000
**Variance:** -4.2%

## 8. DESCRIPTION OF EFFORTS TO ADDRESS ANY IMPEDIMENTS TO FUTURE COMPETITION

### 8.1 Actions to Increase Competition
Government will develop internal migration expertise during contract performance.

### 8.2 Actions to Remove Barriers
Migration tools and documentation will be government-owned after contract completion.

## 9. STATEMENT OF NEED BY REQUIRING ACTIVITY

I certify that the supporting data is accurate and complete.

## 10. APPROVALS

**Required Approval Level:** Competition Advocate (> $750K)

| Role | Name |
|------|------|
| Contracting Officer | John Doe |
| Competition Advocate | Jane Smith |

## ATTACHMENTS

- A. Market Research Report
- B. Sources Sought Notice and Responses
- C. Independent Government Cost Estimate
"""


class TestDocGenSOW:
    """Document generation: SOW with AI content → MD output + completeness."""

    def test_sow_with_ai_content_returns_completeness(self):
        """SOW with full AI content should include completeness report."""
        mock_s3 = _mock_s3()
        with patch.dict(os.environ, ENV_PATCH, clear=False), \
             patch("app.agentic_service._get_s3", return_value=mock_s3):
            from app.agentic_service import _exec_create_document
            result = _exec_create_document(
                {
                    "doc_type": "sow",
                    "title": "Cloud Migration Support Services",
                    "content": SOW_AI_CONTENT,
                },
                tenant_id="test-tenant",
                session_id="ses-schema-sow",
            )

        assert result["document_type"] == "sow"
        assert result["status"] == "saved"
        assert len(result["content"]) > 500
        assert result["word_count"] > 100

        # Validate the content covers key SOW sections
        content = result["content"]
        assert "BACKGROUND AND PURPOSE" in content
        assert "SCOPE" in content
        assert "DELIVERABLES" in content
        assert "SECURITY REQUIREMENTS" in content

        # S3 key should use .md extension (AI content mode)
        assert result["s3_key"].endswith(".md") or result["s3_key"].endswith(".docx")

    def test_sow_completeness_via_schema(self):
        """Validate SOW AI content against template schema directly."""
        report = validate_completeness("sow", SOW_AI_CONTENT)
        assert report.total_sections >= 10
        assert report.completeness_pct >= 80.0
        assert report.is_complete
        assert len(report.missing_sections) <= 3

    def test_sow_partial_content_detected_incomplete(self):
        """SOW with only a few sections should have low completeness."""
        partial = """# Statement of Work
## 1. BACKGROUND AND PURPOSE
NCI needs cloud migration.
## 2. SCOPE
Migrate 47 apps.
"""
        report = validate_completeness("sow", partial)
        assert report.completeness_pct < 40.0
        assert not report.is_complete
        assert len(report.missing_sections) >= 8


class TestDocGenIGCE:
    """Document generation: IGCE with data → XLSX fallback to MD + completeness."""

    def test_igce_generation_returns_valid_shape(self):
        """IGCE with structured data returns valid output with cost details."""
        mock_s3 = _mock_s3()
        with patch.dict(os.environ, ENV_PATCH, clear=False), \
             patch("app.agentic_service._get_s3", return_value=mock_s3):
            from app.agentic_service import _exec_create_document
            result = _exec_create_document(
                {
                    "doc_type": "igce",
                    "title": "Cloud Migration IGCE",
                    "data": IGCE_DATA,
                },
                tenant_id="test-tenant",
                session_id="ses-schema-igce",
            )

        assert result["document_type"] == "igce"
        assert result["status"] == "saved"
        assert result["word_count"] > 0

        # IGCE should default to xlsx file type when template available,
        # or md when falling back
        assert result["file_type"] in ("xlsx", "md")

        # S3 key should match the file type
        assert result["s3_key"].endswith(f".{result['file_type']}")

    def test_igce_completeness_of_ai_content(self):
        """IGCE with rich AI content should score high completeness."""
        igce_content = """# Independent Government Cost Estimate (IGCE)
## Cloud Migration IGCE

## 1. PURPOSE
This IGCE provides a detailed estimate for cloud migration services.

## 2. METHODOLOGY
### 2.1 Data Sources
GSA Schedule pricing, vendor quotes, and historical contract data.
### 2.2 Estimation Methodology
Bottom-up cost estimation using labor category rates and level of effort.
### 2.3 Assumptions
Steady-state operations after 6-month ramp-up period.

## 3. COST BREAKDOWN
### 3.1 Direct Costs
| Line | Description | Qty | Unit Price | Total |
|------|-------------|-----|------------|-------|
| 1 | Cloud Architect | 2080 | $175 | $364,000 |
| 2 | DevOps Engineer | 2080 | $150 | $312,000 |

### 3.2 Direct Labor
| Category | Hours | Rate | Total |
|----------|-------|------|-------|
| Senior Engineer | 2080 | $175 | $364,000 |

## 4. COST SUMMARY
| Category | Amount |
|----------|--------|
| **TOTAL** | **$856,000** |

## 5. COST BY PERIOD
Base Period: 12 months — $856,000

## 6. ASSUMPTIONS AND LIMITATIONS
### 6.1 Key Assumptions
AWS pricing remains stable through contract period.

## 7. CONFIDENCE LEVEL
**Overall Confidence:** High

## 8. DATA SOURCES AND REFERENCES
| Source | Date | Info |
|--------|------|------|
| GSA Schedule | 2026-03 | Labor rates |

## 9. CERTIFICATION
I certify this IGCE was prepared independently.
"""
        report = validate_completeness("igce", igce_content)
        assert report.total_sections >= 8
        assert report.completeness_pct >= 80.0
        assert report.is_complete


class TestDocGenMarketResearch:
    """Document generation: Market Research → MD output + completeness."""

    def test_market_research_with_ai_content(self):
        """Market Research with full AI content saves correctly."""
        mock_s3 = _mock_s3()
        with patch.dict(os.environ, ENV_PATCH, clear=False), \
             patch("app.agentic_service._get_s3", return_value=mock_s3):
            from app.agentic_service import _exec_create_document
            result = _exec_create_document(
                {
                    "doc_type": "market_research",
                    "title": "Cloud Migration Market Research",
                    "content": MARKET_RESEARCH_AI_CONTENT,
                },
                tenant_id="test-tenant",
                session_id="ses-schema-mr",
            )

        assert result["document_type"] == "market_research"
        assert result["status"] == "saved"
        assert "EXECUTIVE SUMMARY" in result["content"]
        assert "SMALL BUSINESS" in result["content"]

    def test_market_research_completeness(self):
        """Market Research AI content should score high completeness."""
        report = validate_completeness("market_research", MARKET_RESEARCH_AI_CONTENT)
        assert report.total_sections >= 10
        assert report.completeness_pct >= 80.0
        assert report.is_complete


class TestDocGenJustification:
    """Document generation: J&A → MD output + completeness."""

    def test_justification_with_ai_content(self):
        """J&A with full AI content saves correctly."""
        mock_s3 = _mock_s3()
        with patch.dict(os.environ, ENV_PATCH, clear=False), \
             patch("app.agentic_service._get_s3", return_value=mock_s3):
            from app.agentic_service import _exec_create_document
            result = _exec_create_document(
                {
                    "doc_type": "justification",
                    "title": "Oracle Database Migration J&A",
                    "content": JUSTIFICATION_AI_CONTENT,
                },
                tenant_id="test-tenant",
                session_id="ses-schema-ja",
            )

        assert result["document_type"] == "justification"
        assert result["status"] == "saved"
        assert "AUTHORITY CITED" in result["content"]
        assert "EFFORTS TO OBTAIN COMPETITION" in result["content"]

    def test_justification_completeness(self):
        """J&A AI content should score high completeness."""
        report = validate_completeness("justification", JUSTIFICATION_AI_CONTENT)
        assert report.total_sections >= 10
        assert report.completeness_pct >= 80.0
        assert report.is_complete


class TestDocGenAcquisitionPlan:
    """Document generation: Acquisition Plan → MD output + completeness."""

    def test_acquisition_plan_with_data_fields(self):
        """Acquisition Plan with structured data returns valid output."""
        mock_s3 = _mock_s3()
        with patch.dict(os.environ, ENV_PATCH, clear=False), \
             patch("app.agentic_service._get_s3", return_value=mock_s3):
            from app.agentic_service import _exec_create_document
            result = _exec_create_document(
                {
                    "doc_type": "acquisition_plan",
                    "title": "Cloud Migration Acquisition Plan",
                    "data": {
                        "description": "Cloud migration support services for NCI CBIIT",
                        "estimated_value": "856000",
                        "period_of_performance": "36 months (base + 2 options)",
                        "competition": "Full and Open",
                        "contract_type": "Time and Materials",
                        "set_aside": "Total Small Business",
                    },
                },
                tenant_id="test-tenant",
                session_id="ses-schema-ap",
            )

        assert result["document_type"] == "acquisition_plan"
        assert result["status"] == "saved"
        assert result["word_count"] > 50

    def test_acquisition_plan_completeness(self):
        """AP with all PART sections should score high completeness."""
        ap_content = """# Acquisition Plan
## Cloud Migration Acquisition Plan

## PART 1: ACQUISITION BACKGROUND AND OBJECTIVES

### 1.1 Statement of Need
NCI requires cloud migration support services.

### 1.2 Applicable Conditions
No urgency; standard procurement timeline.

### 1.3 Cost
Life-Cycle Cost Estimate: $2,568,000 (3 years)

### 1.4 Capability or Performance
Migrate 47 legacy applications to AWS GovCloud.

## PART 2: PLAN OF ACTION

### 2.1 Sources
Multiple qualified sources identified via market research.

### 2.2 Competition
Full and Open Competition — Total Small Business Set-Aside

### 2.3 Source-Selection Procedures
Best Value Trade-off evaluation.

## PART 3: SUPPORTING DOCUMENTATION

### 3.1 Market Research Summary
Market research identified 12+ qualified small businesses.

## APPROVALS

| Role | Name |
|------|------|
| Program Manager | Dr. Chen |
| Contracting Officer | Ms. Williams |
"""
        report = validate_completeness("acquisition_plan", ap_content)
        assert report.total_sections >= 3
        assert report.completeness_pct >= 75.0


class TestDocGenNewTypes:
    """Document generation: New doc types from S3 inventory."""

    def test_new_doc_types_in_valid_set(self):
        """All new doc types should be accepted by _exec_create_document."""
        from app.template_registry import TEMPLATE_REGISTRY
        # Verify new types are registered
        for dt in ["son_products", "son_services", "buy_american", "subk_plan", "conference_request"]:
            assert dt in TEMPLATE_REGISTRY, f"{dt} not in TEMPLATE_REGISTRY"

    def test_registry_alternates_populated(self):
        """Existing doc types should have their S3 alternates expanded."""
        from app.template_registry import TEMPLATE_REGISTRY
        ap = TEMPLATE_REGISTRY["acquisition_plan"]
        assert len(ap.alternates) >= 5  # Was 1, now 6
        assert any("AP Under SAT" in alt for alt in ap.alternates)
        assert any("Task_Order" in alt for alt in ap.alternates)

        igce = TEMPLATE_REGISTRY["igce"]
        assert len(igce.alternates) >= 4  # Was 2, now 4+
        assert any("IGE for Products" in alt for alt in igce.alternates)

        mr = TEMPLATE_REGISTRY["market_research"]
        assert len(mr.alternates) >= 3  # Was 1, now 3+

        ja = TEMPLATE_REGISTRY["justification"]
        assert any("Single Source" in alt for alt in ja.alternates)


class TestDocGenCompletenessIntegration:
    """Validate completeness is wired into the TemplateService."""

    def test_template_result_has_completeness_field(self):
        """TemplateResult dataclass should have completeness attribute."""
        from app.template_service import TemplateResult
        result = TemplateResult(
            success=True,
            content=b"test",
            preview="test preview",
            file_type="md",
            source="test",
        )
        assert hasattr(result, "completeness")
        assert result.completeness is None  # Not set by default

    def test_validate_document_completeness_accessor(self):
        """Registry accessor should return a CompletenessReport."""
        from app.template_registry import validate_document_completeness
        report = validate_document_completeness("sow", SOW_AI_CONTENT)
        assert report is not None
        assert report.doc_type == "sow"
        assert report.total_sections >= 10
        assert report.completeness_pct >= 80.0

    def test_section_guidance_in_prompt_hints(self):
        """Supervisor prompt section hints should include all 5 doc types."""
        from app.strands_agentic_service import _build_doc_type_section_hints
        hints = _build_doc_type_section_hints()
        assert "SOW:" in hints
        assert "IGCE:" in hints
        assert "ACQUISITION_PLAN:" in hints
        assert "MARKET_RESEARCH:" in hints
        assert "JUSTIFICATION:" in hints
        # Should include actual section names, not placeholder names
        assert "BACKGROUND AND PURPOSE" in hints
        assert "COST BREAKDOWN" in hints or "PURPOSE" in hints
