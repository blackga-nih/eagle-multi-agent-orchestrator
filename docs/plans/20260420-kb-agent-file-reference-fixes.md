# KB Agent Prompt Remediation Plan

**Date**: 2026-04-20  
**Branch**: `feat/missing-agents`  
**Scope**: Fix all broken document/folder references in `rh-eagle-2/agents/`  
**Approach**: Edit each agent file to remove missing references and fix folder paths

---

## Summary of Required Edits

| Agent File | Issues | Action Required |
|------------|--------|-----------------|
| `00-supervisor.txt` | 0 | No changes needed - all refs valid |
| `01-policy-supervisor.txt` | 0 | No changes needed - refs to agent files only |
| `02-legal.txt` | 2 | Remove 1 missing doc, fix 1 folder path |
| `03-tech.txt` | 6 | Remove 3 missing docs, remove 3 missing folders |
| `04-market.txt` | 6 | Remove 5 missing docs, remove 1 missing folder |
| `05-public.txt` | 0 | No changes needed - no explicit KB refs |
| `06-policy-librarian.txt` | 0 | No changes needed - refs to folders that exist |
| `07-policy-analyst.txt` | 0 | No changes needed - refs to folders that exist |
| `08-COMPLIANCE.txt` | 7 | Remove 7 missing docs from KB references |
| `09-FINANCIAL.txt` | 1 | Remove 1 missing doc from KB references |

**Total edits needed**: 6 agent files, 22 issues to fix

---

## Detailed Edits Per Agent

### `02-legal.txt` (Legal Counselor)

**Location**: Lines 193-194, 230-231

**Issue 1 - Missing document**:
```
CURRENT:  KB references: NIH_Source_Selection_Guidance_2018.txt,
CHANGE TO: KB references: NIH_LISTSERV_Formal_Source_Selection_Common_Error_2018.txt,
```
(Alternative file exists at `compliance-strategist/NIH-policies/`)

**Issue 2 - Wrong folder path**:
```
CURRENT:  legal-counselor/GAO-decisions/
CHANGE TO: legal-counselor/case-law/
```
(GAO decisions are in subfolders: `case-law/evaluation/`, `case-law/scope/`, `case-law/consolidation/`, `case-law/past-performance/`)

---

### `03-tech.txt` (Technical Translator)

**Location**: Lines 210-212, 278-280

**Remove these missing document references**:
- `NIH_SOW_Best_Practices_Guide.txt` - does not exist
- `Technical_Evaluation_Criteria_Template_NICHD_Example.txt` - does not exist
- `HHS_Technical_Evaluation_Best_Value_Guide.txt` - does not exist

**Remove these missing folder references**:
- `technical-translator/SOW-examples/` - folder does not exist
- `technical-translator/PWS-examples/` - folder does not exist
- `technical-translator/evaluation-criteria/` - folder does not exist

**Replacement options** (folders that DO exist):
- `technical-translator/agile-contracting/`
- `technical-translator/technical-standards/`
- `shared/TechFAR_Hub_Agile_Acquisition_Guide.txt`

---

### `04-market.txt` (Market Intelligence)

**Location**: Lines 234-236, 257-258, 291-294, 318-320

**Remove these missing document references**:
- `HHS_Market_Research_Report_Template.txt` - does not exist
- `HHS_Market_Research_Framework_Template_2025.txt` - does not exist
- `NCI_BPA_Portfolio_GSA_Summary.txt` - does not exist
- `OCIO_Master_Contractor_Roster.txt` - does not exist
- `GSA_Schedules_vs_Open_Market_Guide.txt` - does not exist

**Remove this missing folder reference**:
- `market-intelligence/pricing-data/` - folder does not exist

**Replacement options** (files/folders that DO exist):
- `market-intelligence/market-research-guides/NCI_Market_Research_Guide_for_Project_Officers.txt`
- `market-intelligence/market-research-guides/FC_10_Market_Research_Guidance.txt`
- `market-intelligence/vehicle-information/NIH_Acquisition_Vehicles_Catalog.txt`
- `market-intelligence/vehicle-information/NIH_BPA_Commodity_List_September_2025.txt`
- `supervisor-core/essential-templates/Attachment 1 - HHS Market Research Template.docx`
- `supervisor-core/essential-templates/HHS_Streamlined_MR_Template_FY26.txt`

---

### `08-COMPLIANCE.txt` (Compliance Strategist)

**Location**: Lines 141, 163-164, 186-189, 207, 239

**Remove these missing document references from `KB references:` lines**:
- `HHS_Acquisition_Plan_Template_2024.txt`
- `GSA_Schedules_vs_Open_Market_Guide.txt`
- `FAR_52212-5_Enhanced_Cheat_Sheet_2025.md`
- `HHS_Technical_Evaluation_Best_Value_Guide.txt`
- `NIH_Source_Selection_Guidance_2018.txt`
- `Technical_Evaluation_Criteria_Template_NICHD_Example.txt`
- `Determination_and_Findings_Template_FAR_1704.txt`

**Keep these references** (they exist):
- `PHS_Policy_Laboratory_Animal_Welfare_2015.txt` ✓
- NIH Policy 6304.71 (implicit - ok)
- NIH Policy 6315-1 ✓
- NIH Policy 6307-3 ✓
- NIH Policy 6325-1 ✓
- NIH Policy 6035 ✓

**Replacement options** (files that DO exist):
- `supervisor-core/core-procedures/EAGLE_Acquisition_Plan_Guide_FAR_7105.txt`
- `supervisor-core/essential-templates/HHS_AP_Structure_Guide.txt`
- `compliance-strategist/FAR-guidance/FAR_Part_52_Reference_Guide_RFO_2025.txt`
- `compliance-strategist/FAR-guidance/ACQuipedia_Source_Selection_Evaluation.txt`
- `supervisor-core/core-procedures/ECP_Evaluation_Master_Guide.txt`

---

### `09-FINANCIAL.txt` (Financial Advisor)

**Location**: Lines 131-132

**Remove this missing document reference**:
- `NIH_IGCE_IDIQ_Research_2017.txt` - does not exist

**Keep these references** (they exist):
- `ECP_Evaluation_Master_Guide.txt` ✓ (at `supervisor-core/core-procedures/`)
- NIH Policy 6015-1 ✓
- GAO B-413091 ✓

**No replacement needed** - the remaining references are sufficient for IGCE guidance.

---

## Implementation Plan

### Step 1: Fix folder path mismatches
Edit `02-legal.txt`:
- Change `legal-counselor/GAO-decisions/` → `legal-counselor/case-law/`

### Step 2: Remove missing document references
Edit KB references lines in:
- `02-legal.txt` (1 doc)
- `03-tech.txt` (3 docs)
- `04-market.txt` (5 docs)
- `08-COMPLIANCE.txt` (7 docs)
- `09-FINANCIAL.txt` (1 doc)

### Step 3: Remove missing folder references
Edit folder references in:
- `03-tech.txt` (3 folders)
- `04-market.txt` (1 folder)

### Step 4: (Optional) Add replacement references
Replace removed references with existing files that cover similar content.

---

## Validation After Edits

Run this check after edits:
```bash
# Extract all KB references and verify each exists
grep -h "KB references:" /path/to/agents/*.txt | \
  tr ',' '\n' | \
  while read ref; do
    find /path/to/kb -name "*$(basename $ref)*" | grep -q . || echo "MISSING: $ref"
  done
```

---

## Files That Need No Changes

These agents are clean - all their references are valid:

| Agent | Why No Changes Needed |
|-------|----------------------|
| `00-supervisor.txt` | All 4 document refs exist |
| `01-policy-supervisor.txt` | Only refs other agent files |
| `05-public.txt` | No explicit KB file refs |
| `06-policy-librarian.txt` | Refs folders that exist |
| `07-policy-analyst.txt` | Refs folders that exist |

---

## Source Files Analyzed

**KB baseline**: `/Users/hoquemi/Desktop/KB/rh-eagle-2/`
- 250 total files across all subfolders
- 10 agent definition files in `/agents/`

**Comparison document**: `/Users/hoquemi/Desktop/sm_eagle/docs/development/20260417-kb-agent-prompt-comparison.md`
