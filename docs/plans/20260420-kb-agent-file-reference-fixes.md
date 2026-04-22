# KB Agent Prompt Remediation Plan

**Date**: 2026-04-20  
**Branch**: `feat/missing-agents`  
**Scope**: Fix broken document references in `rh-eagle-2/agents/`  
**Approach**: Option B — Keep folder paths as-is (they're conceptual hints), only remove missing document names

---

## Summary of Required Edits (Option B)

Folder paths are kept as-is (conceptual hints for agents). Only missing document references are removed.

| Agent File | Missing Docs | Action Required |
|------------|--------------|-----------------|
| `00-supervisor.txt` | 0 | No changes needed |
| `01-policy-supervisor.txt` | 0 | No changes needed |
| `02-legal.txt` | 1 | Remove 1 missing doc |
| `03-tech.txt` | 3 | Remove 3 missing docs |
| `04-market.txt` | 5 | Remove 5 missing docs |
| `05-public.txt` | 0 | No changes needed |
| `06-policy-librarian.txt` | 0 | No changes needed |
| `07-policy-analyst.txt` | 0 | No changes needed |
| `08-COMPLIANCE.txt` | 7 | Remove 7 missing docs |
| `09-FINANCIAL.txt` | 1 | Remove 1 missing doc |

**Total edits needed**: 5 agent files, 17 missing document references to remove

---

## Detailed Edits Per Agent (Option B - Documents Only)

### `02-legal.txt` (Legal Counselor)

**Remove this missing document reference**:
- `NIH_Source_Selection_Guidance_2018.txt` — does not exist

(Folder paths like `legal-counselor/GAO-decisions/` are kept as conceptual hints)

---

### `03-tech.txt` (Technical Translator)

**Remove these missing document references**:
- `NIH_SOW_Best_Practices_Guide.txt` — does not exist
- `Technical_Evaluation_Criteria_Template_NICHD_Example.txt` — does not exist
- `HHS_Technical_Evaluation_Best_Value_Guide.txt` — does not exist

(Folder paths like `technical-translator/SOW-examples/` are kept as conceptual hints)

---

### `04-market.txt` (Market Intelligence)

**Remove these missing document references**:
- `HHS_Market_Research_Report_Template.txt` — does not exist
- `HHS_Market_Research_Framework_Template_2025.txt` — does not exist
- `NCI_BPA_Portfolio_GSA_Summary.txt` — does not exist
- `OCIO_Master_Contractor_Roster.txt` — does not exist
- `GSA_Schedules_vs_Open_Market_Guide.txt` — does not exist

(Folder paths like `market-intelligence/pricing-data/` are kept as conceptual hints)

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

## Implementation Plan (Option B)

### Step 1: Remove missing document references from KB references lines

Edit these 5 agent files:
- `02-legal.txt` — remove 1 doc
- `03-tech.txt` — remove 3 docs  
- `04-market.txt` — remove 5 docs
- `08-COMPLIANCE.txt` — remove 7 docs
- `09-FINANCIAL.txt` — remove 1 doc

### Step 2: (Optional) Add replacement references
Replace removed references with existing files that cover similar content.

**Note**: Folder paths are NOT changed — they serve as conceptual hints for agents and don't affect S3 retrieval.

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

## How Retrieval Works (Why This Matters for S3)

The agent prompts don't use direct S3 paths. Here's the flow:

1. **Agent prompt says**: `KB references: HHS_Acquisition_Plan_Template_2024.txt`
2. **Agent calls**: `knowledge_search(query="HHS Acquisition Plan Template")`
3. **System searches**: DynamoDB metadata table + S3 key path matching
4. **S3 key format**: `eagle-knowledge-base/approved/{folder}/{filename}`

**If a referenced document doesn't exist**:
- It won't be in DynamoDB metadata
- Semantic search will return no match or wrong match
- Agent will either fail silently or use incorrect guidance

---

## S3 Validation Steps

### Pre-Deployment Check
After uploading KB to S3, verify each referenced document exists:

```bash
# List all files in S3 bucket
aws s3 ls s3://eagle-documents-695681773636-dev/eagle-knowledge-base/approved/ --recursive > s3_files.txt

# Check for specific referenced docs
grep -i "acquisition_plan" s3_files.txt
grep -i "source_selection" s3_files.txt
grep -i "market_research" s3_files.txt
```

### Post-Deployment Test
Run a search for each critical document reference:

```python
# Test that knowledge_search can find documents agents reference
test_queries = [
    "OAMS Security Checklist Template",  # should find HHSAR_CD_2024_01_OAMS...
    "PHS Policy Laboratory Animal",      # should find PHS_Policy_Laboratory_Animal_Welfare_2015.txt
    "ECP Evaluation Master Guide",       # should find ECP_Evaluation_Master_Guide.txt
    "NIH 6015 Financial Analysis",       # should find NIH_6015_1_*.txt
]

for query in test_queries:
    results = exec_knowledge_search({"query": query, "limit": 3}, tenant_id="test")
    print(f"{query}: {len(results['results'])} results")
    if results['results']:
        print(f"  Top match: {results['results'][0]['title']}")
```

### DynamoDB Metadata Check
Verify metadata entries exist:

```bash
# Query DynamoDB for expected documents
aws dynamodb scan \
  --table-name eagle-document-metadata-dev \
  --filter-expression "contains(s3_key, :key)" \
  --expression-attribute-values '{":key":{"S":"OAMS_Security"}}' \
  --query "Items[].{title: title.S, s3_key: s3_key.S}"
```

---

## Summary: What the Agent Prompt References Actually Mean

| Reference Type | Example | What Agent Does | What Must Exist |
|----------------|---------|-----------------|-----------------|
| Document name | `HHS_Acquisition_Plan_Template_2024.txt` | Searches for "HHS Acquisition Plan Template" | File in S3 + DynamoDB metadata |
| Folder path | `legal-counselor/GAO-decisions/` | Searches for docs with that path segment | Files in that S3 prefix |
| Policy number | `NIH Policy 6315-1` | Searches for "NIH 6315" or "6315-1" | Files containing that number |

**Bottom line**: Every document referenced in agent prompts must be:
1. Present in the KB folder that gets uploaded
2. Indexed in DynamoDB metadata
3. Discoverable via semantic search

---

## Source Files Analyzed

**KB baseline**: `/Users/hoquemi/Desktop/KB/rh-eagle-2/`
- 250 total files across all subfolders
- 10 agent definition files in `/agents/`

**Comparison document**: `/Users/hoquemi/Desktop/sm_eagle/docs/development/20260417-kb-agent-prompt-comparison.md`
