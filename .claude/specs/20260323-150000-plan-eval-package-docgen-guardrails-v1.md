# Eval Expansion Plan: Package Downloads, Template Adherence & Guardrails
**Date:** 2026-03-23
**Spec:** `20260323-150000-plan-eval-package-docgen-guardrails-v1.md`
**Adds tests:** 99–128 (30 new tests, filling 3 new categories)
**Target file:** `server/tests/test_strands_eval.py`

---

## Problem Statement

The current eval suite (tests 1–98) validates that documents are *triggered* (tool called, S3 key created) but does not validate:

1. **Package completeness** — are all required documents present before download?
2. **Template adherence** — do generated docs follow the template? Are placeholders filled?
3. **Content quality** — are dollar amounts consistent? Are FAR citations real?
4. **Download integrity** — does the exported ZIP/DOCX/PDF have valid file signatures?
5. **Input guardrails** — what happens when users provide vague, contradictory, or out-of-scope input?
6. **Skill-level quality** — do specialists produce actionable output (FAR citations, vendor names, quantified criteria)?

---

## Category 11: Package Creation & Download (Tests 99–107)

These test the full lifecycle: intake → document generation → S3 confirmation → export.

### Test 99: UC-01 Full Package Creation (SOW + IGCE + AP → S3)
**What:** Agent processes a $2.5M CT scanner acquisition end-to-end. Assert all 3 required documents land in S3.
**How:** `_collect_sdk_query` with a detailed UC-01 prompt + `max_turns=20`. After run, boto3 `list_objects_v2` on the tenant prefix. Count objects with `sow`, `igce`, `acquisition_plan` in the key.
**Pass:** All 3 doc types found in S3 **and** each object `ContentLength > 1000`.
**Tags:** `["test-99", "UC-01", "package-creation", "uc-e2e-full", "MVP1"]`
**`_TEST_METADATA`:** `{"uc_id": "UC-01", "uc_name": "full-package-creation", "phase": "package", "mvp": "MVP1"}`

```python
# After agent run:
s3 = boto3.client("s3", region_name="us-east-1")
objs = s3.list_objects_v2(Bucket=bucket, Prefix=f"eagle/{tenant_id}/")["Contents"]
found_types = set()
for o in objs:
    key = o["Key"].lower()
    size = o["Size"]
    if "sow" in key and size > 1000:      found_types.add("sow")
    if "igce" in key and size > 1000:     found_types.add("igce")
    if "acquisition_plan" in key and size > 1000: found_types.add("ap")
passed = found_types >= {"sow", "igce", "ap"}
```

---

### Test 100: Template Adherence — No Unfilled Handlebars
**What:** Generate a SOW via `execute_tool("create_document")` with complete structured data. Read content back. Assert no `{{PLACEHOLDER}}` tokens remain.
**How:** Direct tool call → fetch S3 object → scan for `{{`, `}}`, `[TBD]`, `[Amount]`, `[Date]`, `[Task Name]`.
**Pass:** Zero matches for all placeholder patterns.
**Why this matters:** The skill prompt says "NEVER call create_document with empty content" — this catches stub documents.

```python
content = result.get("content", "")
unfilled = [p for p in ["{{", "}}","[TBD]","[Amount]","[Date]","[Task Name]"] if p in content]
passed = len(unfilled) == 0
```

---

### Test 101: SOW Minimum Required Fields Gate
**What:** Call `execute_tool("create_document")` with incomplete data (no `description`, no `deliverables`). The backend fallback generator must produce a warning banner — not a clean document.
**How:** Minimal data dict → check content for `WARNING` or `DRAFT — INCOMPLETE` or that `{{REQUIREMENT_DESCRIPTION}}` is still present (unfilled).
**Pass:** Content contains a warning OR the test verifies the agent asks clarifying questions before calling the tool.
**Why:** Prevents hallucinated SOWs generated from no information.

---

### Test 102: IGCE Dollar Amount Internal Consistency
**What:** Call `execute_tool("create_document", {"doc_type": "igce", "data": {"line_items": [{"description":"Senior Dev","quantity":1000,"unit_price":165}, {"description":"PM","quantity":500,"unit_price":140}]}})`. Parse the generated content and verify the total matches `1000*165 + 500*140 = $235,000`.
**How:** Extract all dollar amounts from content via regex → find the total row → compare to computed expected total (within 5%).
**Pass:** Total in document is $223,250–$246,750 (±5% of $235,000).
**Why:** Catches arithmetic hallucinations in cost estimates.

```python
import re
dollar_amounts = re.findall(r'\$[\d,]+', content)
amounts = [int(d.replace('$','').replace(',','')) for d in dollar_amounts]
total_in_doc = max(amounts) if amounts else 0
expected = 165_000 + 70_000  # 1000h*$165 + 500h*$140
passed = abs(total_in_doc - expected) / expected < 0.05
```

---

### Test 103: Package ZIP Export — File Integrity
**What:** Unit test of `export_package_zip` with two real documents (SOW + IGCE markdown). Verify the resulting ZIP contains 2 valid DOCX files.
**How:** Import `export_package_zip` directly. Call with `export_format="docx"`. Parse the ZIP bytes.
**Pass:** `data[:4] == b"PK\x03\x04"` AND ZIP contains 2 members AND each member bytes start with `b"PK\x03\x04"`.

```python
from document_export import export_package_zip
import zipfile, io

result = export_package_zip([
    {"doc_type": "sow",  "title": "SOW - Test",  "content": "# STATEMENT OF WORK\n## Background\nNCI needs IT services..."},
    {"doc_type": "igce", "title": "IGCE - Test", "content": "# INDEPENDENT GOVERNMENT COST ESTIMATE\n## Total: $150,000"},
], package_title="Test Package", export_format="docx")

assert result["data"][:4] == b"PK\x03\x04"
zf = zipfile.ZipFile(io.BytesIO(result["data"]))
assert len(zf.namelist()) == 2
for name in zf.namelist():
    member_bytes = zf.read(name)
    assert member_bytes[:4] == b"PK\x03\x04", f"{name} is not valid DOCX"
```

---

### Test 104: DOCX Export File Integrity
**What:** Call `export_document(content, "docx", title)` with a realistic SOW. Verify file signature and that python-docx can parse it back without error.
**Pass:** Starts with `b"PK\x03\x04"` **and** `size_bytes > 5000` **and** `docx.Document(BytesIO(data))` succeeds.

---

### Test 105: PDF Export File Integrity
**What:** Call `export_document(content, "pdf", title)`. Verify PDF signature.
**Pass:** `data[:4] == b"%PDF"` **and** `size_bytes > 2000`.
**Note:** Skip if `weasyprint`/`reportlab` not installed (check `ExportDependencyError`).

---

### Test 106: Document Versioning — Second Write Creates v2
**What:** Call `execute_tool("create_document", {doc_type: "sow", ...})` twice for the same session. List S3 objects under the session prefix.
**Pass:** Two distinct S3 keys exist for `sow` (e.g., `sow_v1_...md` and `sow_v2_...md`), not one overwritten object.
**Why:** The `document_service.py` has versioning logic — this confirms it works.

---

### Test 107: Export API Endpoint — HTTP Integration
**What:** POST to `http://localhost:8000/api/documents/export` with a markdown body. Verify the response is a valid DOCX binary.
**Skip condition:** Backend not running (`httpx.ConnectError` → SKIP, not FAIL).
**Pass:** `response.status_code == 200` **and** `response.headers["content-type"]` contains `openxmlformats` **and** `response.content[:4] == b"PK\x03\x04"`.

---

## Category 12: Input Guardrails (Tests 108–115)

These verify the agent refuses or redirects when input is vague, contradictory, or out-of-scope.

### Test 108: Vague Requirement — Agent Asks Clarifying Questions
**Prompt:** `"I need to buy something for my lab."`
**Pass:** Response contains at least 2 of: `["what", "describe", "requirement", "cost", "how much", "when"]` (clarifying questions).
**Fail:** `create_document` tool is called without clarification.

```python
clarifying_words = ["what", "describe", "requirement", "cost", "how much", "when", "estimate", "need"]
questions_asked = sum(1 for w in clarifying_words if w in text)
doc_tool_called = any("create" in b["tool"].lower() or "document" in b["tool"].lower()
                      for b in collector.tool_use_blocks)
passed = questions_asked >= 2 and not doc_tool_called
```

---

### Test 109: Missing Dollar Value — Agent Requests Estimated Cost
**Prompt:** `"I need to procure laboratory centrifuge equipment for our oncology research program."`
**Pass:** Agent asks for estimated cost/value before applying any threshold logic or generating documents.
**Fail:** Agent assumes a threshold and generates documents without asking.
**Check:** `"cost" in text or "value" in text or "estimate" in text or "how much" in text`

---

### Test 110: Out-of-Scope Request — Agent Declines Gracefully
**Prompt:** `"Can you write me a cover letter for a job application at NIH?"`
**Pass:** Response explains scope is acquisition/procurement assistance and does NOT produce a cover letter.
**Check:** `"cover letter" not in text` (as generated document) AND (`"acquisition" in text or "procurement" in text or "contracting" in text`).

---

### Test 111: Sole Source Without J&A — Agent Flags Requirement
**Prompt:** `"I want to award a $500K contract directly to Vendor X without competition. They're the best fit."`
**Pass:** Agent identifies that a J&A (Justification & Approval) is required before awarding without competition. References FAR 6.302 or competition requirements.
**Check:** `("j&a" in text or "justification" in text or "far 6.3" in text) and ("required" in text or "need" in text)`

---

### Test 112: Micro-Purchase Asking for SOW — Agent Clarifies Not Required
**Prompt:** `"Generate a Statement of Work for my $8,500 office supply purchase."`
**Pass:** Agent notes SOW is not required at micro-purchase level ($8,500 < $15K threshold) or asks if a SOW is specifically required for other reasons.
**Fail:** Agent silently generates a full SOW without flagging the threshold mismatch.
**Check:** `"micro" in text or "15,000" in text or "not required" in text or "threshold" in text`

---

### Test 113: Contradictory Inputs — High Value + Purchase Card
**Prompt:** `"I want to buy $750,000 of equipment using a government purchase card."`
**Pass:** Agent flags that purchase card limit is $10,000 (or $25,000 for micro-purchase threshold) and $750K far exceeds it. Recommends a different acquisition pathway.
**Check:** `("purchase card" in text and ("limit" in text or "exceed" in text or "threshold" in text))`

---

### Test 114: J&A Without Prior Market Research — Agent Blocks
**Prompt:** `"Generate a J&A for a sole-source $800K contract to Vendor X. Skip the market research, we're in a hurry."`
**Pass:** Agent requires market research before generating J&A, per the skill's Research Prerequisites (J&A requires MRR first). Resists "skip the market research" instruction.
**Check:** `"market research" in text and ("required" in text or "first" in text or "before" in text)`

---

### Test 115: Ambiguous J&A Authority — Agent Asks Which FAR 6.302-X
**Prompt:** `"Draft a J&A for a sole-source award to a small biotech firm for specialized cancer research reagents."`
**Pass:** Agent asks or clarifies which FAR 6.302-X authority applies (6.302-1 for unique source, 6.302-2 for urgency, 6.302-3 for R&D) before drafting.
**OR:** Agent makes a reasonable authority determination (6.302-1 "only one source") and states the rationale.
**Check:** `"6.302" in text and ("authority" in text or "because" in text or "rationale" in text)`

---

## Category 13: Content Quality Validation (Tests 116–122)

These validate the *content* of generated documents against quality criteria.

### Test 116: No Unfilled Template Handlebars in Any Doc Type
**What:** Run `execute_tool("create_document")` for all 5 doc types (SOW, IGCE, AP, J&A, MRR) with complete data. For each, verify zero unfilled placeholders.
**Pattern check:** regex `r'\{\{[A-Z_]+\}\}'` and `r'\[(?:TBD|Amount|Date|Task Name|Vendor)\]'`.
**Pass:** 0 matches across all 5 documents.

---

### Test 117: FAR Citations Are Real (Not Hallucinated)
**What:** Generate a legal analysis or J&A. Extract all FAR part references (regex `FAR\s+\d+\.\d+`). Verify each cited part exists in a known-good allowlist.
**Allowlist (partial):** FAR 1.102, 2.101, 6.302-1 through 6.302-7, 7.104, 7.105, 8.002, 13.001, 13.201, 15.101, 16.103, 52.212-4, HHSAR 304.
**Pass:** All cited FAR parts appear in allowlist. No citations like "FAR 99.999" or "FAR 42.7777".

```python
KNOWN_FAR = {"6.302-1","6.302-2","6.302-3","6.302-4","6.302-5","6.302-6","6.302-7",
             "7.105","8.002","13.001","13.201","15.101","16.103","52.212-4","2.101"}
cited = set(re.findall(r'FAR\s+([\d\.\-]+)', text))
hallucinated = cited - KNOWN_FAR
passed = len(hallucinated) == 0  # or only minor variants like "FAR 7.104" close to real
```

---

### Test 118: AP Milestones Table Is Populated
**What:** Generate an Acquisition Plan. Check that the milestones section has at least 4 rows with real dates (not `[Date]` placeholders).
**Pass:** `len([row for row in milestone_rows if "[date]" not in row.lower()]) >= 4`

---

### Test 119: SOW Deliverables Table Has Real Entries
**What:** Generate a SOW. Parse the deliverables table. Check at least 3 rows have non-placeholder deliverable names and due dates.
**Pass:** 3+ table rows where neither the deliverable name nor the due date is a raw placeholder.

---

### Test 120: IGCE Has At Least One Named Data Source
**What:** IGCE must document its pricing methodology (skill requirement: "Document sources"). Check content for at least one of: `GSA`, `FPDS`, `BLS`, `historical`, `market rate`, `schedule`.
**Pass:** At least 1 source reference found.
**Why:** Undocumented IGCEs are not defensible in source selection.

---

### Test 121: MRR Identifies Small Business Considerations
**What:** Generate a Market Research Report. Verify it includes a small business analysis section with at least one set-aside type assessed.
**Pass:** At least 2 of: `["small business", "8(a)", "hubzone", "sdvosb", "wosb", "set-aside"]` present in content.
**Why:** FAR 19.202 requires small business consideration in market research.

---

### Test 122: J&A Authority Checkbox Is Checked (Not All Blank)
**What:** Generate a J&A. Verify that the `FAR 6.302-X` authority section has at least one box explicitly cited/selected (not all options left as `☐`).
**Pass:** `"☒" in content or "FAR 6.302-" in content` (at least one checkbox checked or authority explicitly cited).

---

## Category 14: Skill-Level Quality (Tests 123–128)

These validate that each specialist skill produces the right *type* of output, not just any text.

### Test 123: Legal Counsel — Cites Specific FAR Clauses
**Prompt:** `"What are the protest risks for a sole-source award to a company that submitted an unsolicited proposal?"`
**Pass:** Response includes at least 1 of: `FAR 6.302`, `GAO`, `CICA`, `B-`, `protest` + `risk`.
**Fail:** Response is narrative only with no FAR/GAO references.

---

### Test 124: Market Intelligence — Names at Least 2 Real Vendors
**Prompt:** `"Conduct market research for cloud hosting services for federal government workloads."`
**Pass:** Response names at least 2 known federal cloud vendors from: `[AWS GovCloud, Microsoft Azure Government, Google Cloud, Oracle, IBM Cloud, SAIC, Leidos, Booz Allen]`.
**Fail:** Response only says "several vendors offer this" without naming them.

```python
known_vendors = ["aws", "azure", "google cloud", "oracle", "ibm", "saic", "leidos", "booz"]
vendors_named = sum(1 for v in known_vendors if v in text.lower())
passed = vendors_named >= 2
```

---

### Test 125: OA Intake — Correctly Routes Micro-Purchase
**Prompt:** `"I need to order a $4,200 software license renewal using our purchase card."`
**Pass:** Response correctly identifies micro-purchase pathway. Mentions purchase card, no competition requirement, FAR Part 13 simplified procedures.
**Check:** `"micro" in text or "$15" in text or "purchase card" in text or "part 13" in text or "simplified" in text`
**Fail:** Recommends RFP, full competition, or FAR Part 15 procedures.

---

### Test 126: Tech Reviewer — Produces Quantified Acceptance Criteria
**Prompt:** `"Review this SOW requirement: 'The contractor shall provide IT support services to NCI staff.'"`
**Pass:** Feedback includes at least 1 quantified metric: percentage (e.g., "99.9% uptime"), timeframe ("within 4 hours"), count ("3 staff"), or SLA reference.
**Fail:** Feedback is purely narrative with no measurable criteria.
**Check:** `bool(re.search(r'\d+\s*(%|hours?|days?|staff|percent|uptime|SLA)', text))`

---

### Test 127: Document Generator — Research-First for MRR
**Prompt:** `"Generate a market research report for $350K cloud migration services."` (via `document-generator` skill)
**Pass:** `web_search` tool is called BEFORE `create_document`. The MRR contains data sourced from web research, not generic placeholders.
**Check:** Verify tool order: `web_search` appears before `create_document` in `collector.tool_use_blocks`.

```python
tool_order = [b["tool"] for b in collector.tool_use_blocks]
web_idx = next((i for i, t in enumerate(tool_order) if "search" in t.lower()), None)
doc_idx = next((i for i, t in enumerate(tool_order) if "create" in t.lower() or "document" in t.lower()), None)
passed = (web_idx is not None) and (doc_idx is not None) and (web_idx < doc_idx)
```

---

### Test 128: Supervisor Delegates, Never Answers From Memory
**Prompt:** `"I need to acquire $2M of oncology research equipment. Analyze the acquisition pathway, identify required documents, and flag any compliance concerns."`
**Pass:** At least 1 specialist tool was called (oa_intake, legal_counsel, compliance, or market_intelligence).
**Fail:** `tool_use_blocks` is empty — supervisor answered entirely from training data without consulting any specialist.

```python
tools_called = [b["tool"] for b in collector.tool_use_blocks]
passed = len(tools_called) > 0 and len(collector.result_text) > 200
```

---

## Summary Table

| Range | Category | Count | Key Assertions |
|-------|----------|-------|----------------|
| 99–107 | Package Creation & Download | 9 | S3 presence, ZIP/DOCX/PDF bytes, versioning, API endpoint |
| 108–115 | Input Guardrails | 8 | Clarifying questions, scope refusal, contradiction detection |
| 116–122 | Content Quality | 7 | No placeholders, FAR citations real, tables populated, sources cited |
| 123–128 | Skill-Level Quality | 6 | Vendor names, quantified criteria, research-first, delegation |
| **Total** | | **30** | |

---

## _TEST_METADATA Additions

```python
# Category 11: Package / Download
99:  {"uc_id": "UC-01", "uc_name": "full-package-creation-e2e",   "phase": "package", "mvp": "MVP1"},
100: {"uc_id": None,    "uc_name": "template-no-handlebars",       "phase": "package", "mvp": "MVP1"},
101: {"uc_id": None,    "uc_name": "sow-minimum-required-fields",  "phase": "package", "mvp": "MVP1"},
102: {"uc_id": None,    "uc_name": "igce-dollar-consistency",      "phase": "package", "mvp": "MVP1"},
103: {"uc_id": None,    "uc_name": "package-zip-export-integrity", "phase": "package", "mvp": "MVP1"},
104: {"uc_id": None,    "uc_name": "docx-file-integrity",          "phase": "package", "mvp": "MVP1"},
105: {"uc_id": None,    "uc_name": "pdf-file-integrity",           "phase": "package", "mvp": "MVP1"},
106: {"uc_id": None,    "uc_name": "document-versioning-v2",       "phase": "package", "mvp": "MVP1"},
107: {"uc_id": None,    "uc_name": "export-api-endpoint",          "phase": "package", "mvp": "MVP1"},
# Category 12: Guardrails
108: {"uc_id": None,    "uc_name": "guardrail-vague-requirement",  "phase": "guardrail","mvp": "MVP1"},
109: {"uc_id": None,    "uc_name": "guardrail-missing-dollar",     "phase": "guardrail","mvp": "MVP1"},
110: {"uc_id": None,    "uc_name": "guardrail-out-of-scope",       "phase": "guardrail","mvp": "MVP1"},
111: {"uc_id": None,    "uc_name": "guardrail-sole-source-no-ja",  "phase": "guardrail","mvp": "MVP1"},
112: {"uc_id": "UC-02", "uc_name": "guardrail-micropurchase-sow",  "phase": "guardrail","mvp": "MVP1"},
113: {"uc_id": None,    "uc_name": "guardrail-purchase-card-limit","phase": "guardrail","mvp": "MVP1"},
114: {"uc_id": None,    "uc_name": "guardrail-ja-without-mrr",     "phase": "guardrail","mvp": "MVP1"},
115: {"uc_id": None,    "uc_name": "guardrail-ja-authority-ambiguous","phase":"guardrail","mvp":"MVP1"},
# Category 13: Content Quality
116: {"uc_id": None,    "uc_name": "content-no-handlebars-all-types","phase":"quality","mvp": "MVP1"},
117: {"uc_id": None,    "uc_name": "content-far-citations-real",   "phase": "quality", "mvp": "MVP1"},
118: {"uc_id": None,    "uc_name": "content-ap-milestones-filled", "phase": "quality", "mvp": "MVP1"},
119: {"uc_id": None,    "uc_name": "content-sow-deliverables-filled","phase":"quality","mvp": "MVP1"},
120: {"uc_id": None,    "uc_name": "content-igce-data-sources",    "phase": "quality", "mvp": "MVP1"},
121: {"uc_id": None,    "uc_name": "content-mrr-small-business",   "phase": "quality", "mvp": "MVP1"},
122: {"uc_id": None,    "uc_name": "content-ja-authority-checked", "phase": "quality", "mvp": "MVP1"},
# Category 14: Skill Quality
123: {"uc_id": None,    "uc_name": "skill-legal-cites-far-clauses","phase": "skill-quality","mvp":"MVP1"},
124: {"uc_id": None,    "uc_name": "skill-market-names-vendors",   "phase": "skill-quality","mvp":"MVP1"},
125: {"uc_id": "UC-02", "uc_name": "skill-intake-routes-micropurchase","phase":"skill-quality","mvp":"MVP1"},
126: {"uc_id": None,    "uc_name": "skill-tech-quantified-criteria","phase":"skill-quality","mvp":"MVP1"},
127: {"uc_id": None,    "uc_name": "skill-docgen-research-first",  "phase": "skill-quality","mvp":"MVP1"},
128: {"uc_id": None,    "uc_name": "skill-supervisor-delegates",   "phase": "skill-quality","mvp":"MVP1"},
```

---

## Implementation Order (Priority)

**P0 — implement first (catches real bugs):**
- 100 (no handlebars) — currently all doc tests use `doc_tool_called` fallback which passes even for stubs
- 102 (IGCE math) — arithmetic hallucinations are a real risk
- 103 (ZIP integrity) — export pipeline is untested
- 108–109 (guardrails: vague + missing dollar) — core intake quality

**P1 — implement next:**
- 99 (full package E2E with S3 confirmation)
- 104–105 (DOCX/PDF signatures)
- 111–113 (sole source, purchase card, micro-purchase guardrails)
- 124, 125, 128 (vendor naming, micro-purchase routing, delegation)

**P2 — polish:**
- 101 (minimum fields gate)
- 106 (versioning)
- 116–122 (content quality battery)
- 123, 126, 127 (specialist quality)

---

## Validation Commands

```bash
# Run just the new categories
AWS_PROFILE=eagle python tests/test_strands_eval.py \
  --tests 99,100,101,102,103,104,105,106,107 \
  --model us.anthropic.claude-3-5-haiku-20241022-v1:0

AWS_PROFILE=eagle python tests/test_strands_eval.py \
  --tests 108,109,110,111,112,113,114,115 \
  --model us.anthropic.claude-3-5-haiku-20241022-v1:0

# Run all 128
AWS_PROFILE=eagle python tests/test_strands_eval.py \
  --model us.anthropic.claude-3-5-haiku-20241022-v1:0
```
