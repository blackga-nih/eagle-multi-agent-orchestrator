# Canonical Schema Inventory — Phase 0

**Date**: 2026-04-09  
**Purpose**: Audit all schema sources to establish canonical values before Phase 1 implementation.  
**Status**: ✅ COMPLETE — Decisions approved 2026-04-09

---

## Phase 0 Completion Summary

**Completed**: 2026-04-09

### Decisions Made

| Decision | Resolution |
|----------|------------|
| Frontend-only types (`funding_doc`, `d_f`, `qasp`, etc.) | **Keep for now** — add to backend later if needed |
| Standardize naming (`subcontracting_plan` → `subk_plan`) | **Yes** — aliases protect user queries |
| Missing registry types | **Add** `purchase_request`, `price_reasonableness`, `required_sources` |

### Critical Finding: Alias Map Fragmentation

**Problem discovered**: `create_document` uses `create_document_support._DOC_TYPE_ALIASES` which is **incomplete** and **doesn't call** `doc_type_registry.normalize_doc_type()`.

**Impact**: User queries like "create a subcontracting plan" fail because:
1. `subcontracting_plan` not in `create_document_support._DOC_TYPE_ALIASES`
2. `subk_plan` not in `document_generation.valid_doc_types`

**Resolution**: Phase 1 will consolidate all alias maps into `ai_document_schema.py` and wire `create_document` to use it.

### Next Step

Proceed to **Phase 2**: Wire `ai_document_schema` into `exec_create_document()`

---

## Phase 1 Completion Summary

**Completed**: 2026-04-09

### Deliverables

| File | Description |
|------|-------------|
| `server/app/ai_document_schema.py` | Canonical schema module — enums, aliases, Pydantic models, validation |
| `server/tests/test_ai_document_schema.py` | 40 unit tests — all passing |

### What Was Built

**Canonical Enums**:
- `CanonicalDocType` — 32 document types
- `CanonicalContractType` — 10 contract types (FFP, CPFF, T&M, etc.)
- `CanonicalAcquisitionMethod` — 8 acquisition methods

**Consolidated Alias Maps**:
- `DOC_TYPE_ALIASES` — 50+ aliases (merged from `doc_type_registry` + `create_document_support`)
- `FIELD_NAME_ALIASES` — 28 field aliases (from `template_registry`)
- `CONTRACT_TYPE_ALIASES` — 25+ aliases (from `compliance_matrix`)
- `ACQUISITION_METHOD_ALIASES` — 20+ aliases (from `compliance_matrix`)
- `LABOR_CATEGORY_ALIASES` — 30+ aliases (from `igce_generation_extractor`)

**Pydantic Models**:
- `BaseDocumentData` — common fields
- `SowDocumentData`, `IgceDocumentData`, `MarketResearchDocumentData`, `JustificationDocumentData`, `AcquisitionPlanDocumentData`

**Validation Entrypoint**:
- `normalize_and_validate_document_payload()` — canonical boundary function

### Test Coverage

```
40 tests passed:
- TestNormalizeDocType: 9 tests
- TestIsValidDocType: 3 tests
- TestNormalizeContractType: 5 tests
- TestNormalizeAcquisitionMethod: 3 tests
- TestNormalizeFieldNames: 4 tests
- TestNormalizeLaborCategory: 2 tests
- TestNormalizeAndValidateDocumentPayload: 7 tests
- TestRegressionCases: 5 tests (Son, Sb Review, requirement→description, etc.)
- TestHelperFunctions: 2 tests
```

### Critical Fix Verified

`subcontracting_plan` → `subk_plan` alias is now in the canonical module and tested:

```python
# test_ai_document_schema.py
def test_subcontracting_plan_normalization(self):
    result = normalize_and_validate_document_payload(
        raw_doc_type="subcontracting_plan",
        ...
    )
    assert result.doc_type == "subk_plan"  # ✅ PASSES
```

### Remaining Work

~~Phase 2 will wire `exec_create_document()` to use this module instead of the fragmented alias maps~~

---

## Phase 2 Completion Summary

**Completed**: 2026-04-09

### Changes Made

| File | Change |
|------|--------|
| `server/app/tools/document_generation.py` | Wired `normalize_and_validate_document_payload()` into `exec_create_document()` |
| `server/app/tools/document_generation.py` | Replaced hardcoded `valid_doc_types` with `get_create_document_types()` |
| `server/app/tools/document_generation.py` | Added observability logging for warnings and normalized aliases |
| `server/app/tools/create_document_support.py` | Deprecated `_DOC_TYPE_ALIASES` with comment pointing to canonical schema |
| `server/app/tools/create_document_support.py` | Updated `_normalize_create_document_doc_type()` to delegate to canonical schema |

### Code Flow (After Phase 2)

```
User: "create a subcontracting plan"
         ↓
Agent calls create_document(doc_type="subcontracting_plan")
         ↓
exec_create_document() [document_generation.py]
         ↓
normalize_doc_type("subcontracting_plan")  ← ai_document_schema.py
         ↓
Returns: "subk_plan"  (canonical)
         ↓
_augment_document_data_from_context()
         ↓
normalize_and_validate_document_payload()  ← ai_document_schema.py
  - Normalizes field names (requirement → description)
  - Normalizes contract_type (firm_fixed_price → ffp)
  - Logs warnings and aliases
         ↓
get_create_document_types()  ← ai_document_schema.py
  - Returns canonical valid set (includes subk_plan)
         ↓
Document generated successfully ✅
```

### Test Results

```
53 tests passed:
- test_doc_type_aliases.py: 13 tests (now delegate to canonical schema)
- test_ai_document_schema.py: 40 tests
```

### Backward Compatibility

- `_normalize_create_document_doc_type()` kept for existing tests but delegates to canonical schema
- `_DOC_TYPE_ALIASES` kept but marked deprecated
- All existing tests pass without modification

### Next Steps

~~**Phase 3**: Unify runtime tool contracts~~
~~- Update `server/app/strands_agentic_service.py` EAGLE_TOOLS~~
~~- Sync `eagle-plugin/tools/tool-definitions.json`~~

---

## Phase 3 Completion Summary

**Completed**: 2026-04-09

### Changes Made

| File | Change |
|------|--------|
| `eagle-plugin/tools/tool-definitions.json` | Updated to v2.0.0 — synced doc_type enum (5 → 18 types), added canonical field names with explicit guidance |
| `server/app/strands_agentic_service.py` | Updated EAGLE_TOOLS `data` description to list canonical field names |

### Tool Schema Updates

**Before** (plugin had only 5 doc_types):
```json
"enum": ["sow", "igce", "market_research", "justification", "acquisition_plan"]
```

**After** (18 canonical doc_types):
```json
"enum": ["sow", "igce", "market_research", "justification", "acquisition_plan",
         "eval_criteria", "security_checklist", "section_508", "cor_certification",
         "contract_type_justification", "son_products", "son_services", "buy_american",
         "subk_plan", "conference_request", "purchase_request", "price_reasonableness",
         "required_sources"]
```

### Field Name Guidance Added

Tool descriptions now explicitly tell the AI to use canonical names:
- `description` (not `requirement`)
- `estimated_value` (not `estimated_cost`/`budget`)
- `period_of_performance` (not `duration`/`pop`)
- `vendors_identified` (not `vendors`)
- `contractor` (not `contractor_name`/`vendor`)
- `contract_type` (use `ffp`/`cpff`/`t&m`)

### Why This Matters

The AI model sees these tool schemas when deciding what parameters to use. By explicitly listing canonical field names in the schema, we **constrain the AI at generation time** — reducing the need for post-hoc normalization.

---

~~**Phase 4**: Consolidate remaining alias ownership~~
~~- Refactor `template_registry.py` to import from canonical schema~~
~~- Refactor `compliance_matrix.py` to share enum normalization~~

---

## Phase 4 Completion Summary

**Completed**: 2026-04-09

### Changes Made

| File | Change |
|------|--------|
| `server/app/template_registry.py` | Replaced local `FIELD_NAME_ALIASES` with import from `ai_document_schema` |
| `server/app/template_registry.py` | Added note to `normalize_field_names()` pointing to canonical schema |
| `server/app/compliance_matrix.py` | Added comment documenting relationship to canonical schema |

### Alias Ownership After Phase 4

| Alias Type | Canonical Owner | Notes |
|------------|-----------------|-------|
| `DOC_TYPE_ALIASES` | `ai_document_schema.py` | Single source of truth |
| `FIELD_NAME_ALIASES` | `ai_document_schema.py` | Imported by `template_registry.py` |
| `CONTRACT_TYPE_ALIASES` | `ai_document_schema.py` | Common contract types |
| `ACQUISITION_METHOD_ALIASES` | `ai_document_schema.py` | Common acquisition methods |
| `LABOR_CATEGORY_ALIASES` | `ai_document_schema.py` | IGCE labor categories |
| `_METHOD_ALIASES` | `compliance_matrix.py` | **Extended** — compliance-specific (bpa-est, fss, idiq-order) |
| `_TYPE_ALIASES` | `compliance_matrix.py` | **Extended** — compliance-specific (tm vs t&m) |

### Why `compliance_matrix.py` Keeps Its Aliases

The compliance matrix has **specialized aliases** not needed elsewhere:
- `bpa-est`, `bpa-call` (BPA establishment vs call orders)
- `idiq-order` (task/delivery orders)
- `fss` (Federal Supply Schedule)
- FAR Part references (`far part 8`, `far part 13`)

These are specific to compliance logic and don't belong in the general canonical schema.

### Test Results

```
67 tests passed (template_service + ai_document_schema)
170 tests passed (full suite including compliance_matrix)
```

---

~~**Phase 5**: Frontend type propagation~~
~~- Align `client/types/schema.ts` DocumentType with canonical backend values~~

---

## Phase 5 Completion Summary

**Completed**: 2026-04-09

### Changes Made

| File | Change |
|------|--------|
| `client/types/schema.ts` | Updated `DocumentType` union — added 11 new types, organized by category |
| `client/types/schema.ts` | Updated `DOCUMENT_TYPE_LABELS` — added labels for new types |
| `client/types/schema.ts` | Updated `DOCUMENT_TYPE_ICONS` — added icons for new types |
| `client/lib/document-store.ts` | Updated slug mapping: `subcontracting-plan` → `subk_plan` |
| `client/components/chat-simple/state-change-card.tsx` | Added `subk_plan` label, kept legacy alias |

### DocumentType Changes

**Before** (18 types, some misaligned):
```typescript
export type DocumentType = 'sow' | 'igce' | ... | 'subcontracting_plan' | 'sb_review' | ...
```

**After** (28 types, aligned with canonical schema):
```typescript
export type DocumentType =
  // Core document types (create_document supported)
  | 'sow' | 'igce' | 'market_research' | 'acquisition_plan' | 'justification'
  | 'eval_criteria' | 'security_checklist' | 'section_508' | 'cor_certification'
  | 'contract_type_justification' | 'son_products' | 'son_services'
  | 'purchase_request' | 'price_reasonableness' | 'required_sources'
  // Template/form types
  | 'subk_plan' | 'subk_review' | 'buy_american' | 'conference_request'
  | 'conference_waiver' | 'bpa_call_order'
  // Frontend-only types (kept for compatibility)
  | 'funding_doc' | 'd_f' | 'qasp' | 'source_selection_plan' | 'sb_review' | 'human_subjects'
```

### Types Added

| Type | Label |
|------|-------|
| `son_products` | Statement of Need — Products |
| `son_services` | Statement of Need — Services |
| `price_reasonableness` | Price Reasonableness Determination |
| `required_sources` | Required Sources Checklist |
| `subk_plan` | Subcontracting Plan (renamed from subcontracting_plan) |
| `subk_review` | Subcontracting Review |
| `buy_american` | Buy American Determination |
| `conference_request` | Conference Request |
| `conference_waiver` | Conference Waiver |
| `bpa_call_order` | BPA Call Order |

### TypeScript Validation

```
npx tsc --noEmit → No errors in modified files
```

---

## Phase 6 Completion Summary

**Completed**: 2026-04-09

### Changes Made

| File | Change |
|------|--------|
| `server/app/tools/document_generation.py` | Added `schema.normalized` telemetry event emission |

### Telemetry Event Structure

When schema normalization occurs, a `schema.normalized` event is emitted to CloudWatch Logs:

```json
{
  "event_type": "schema.normalized",
  "tenant_id": "tenant-123",
  "session_id": "session-456",
  "doc_type": "subk_plan",
  "original_doc_type": "subcontracting_plan",
  "normalized_aliases": ["doc_type: subcontracting_plan → subk_plan"],
  "warnings": [],
  "unknown_fields": [],
  "alias_count": 1,
  "warning_count": 0,
  "unknown_field_count": 0
}
```

### CloudWatch Insights Queries

**Query 1: Top normalized doc_types (schema drift frequency)**
```sql
fields @timestamp, original_doc_type, doc_type, alias_count
| filter event_type = "schema.normalized"
| stats count() as occurrences by original_doc_type, doc_type
| sort occurrences desc
| limit 20
```

**Query 2: Unknown fields (potential schema gaps)**
```sql
fields @timestamp, doc_type, unknown_fields
| filter event_type = "schema.normalized" and unknown_field_count > 0
| stats count() as occurrences by unknown_fields
| sort occurrences desc
```

### Historical Data Cleanup Plan

**DO NOT RUN CLEANUP YET** — Wait for telemetry data (1-2 weeks minimum).

1. **Collect telemetry** (Weeks 1-2) — Monitor CloudWatch for `schema.normalized` events
2. **Analyze results** (Week 3) — Identify actual drift patterns
3. **Migrate data** (Week 4+) — Create targeted migration scripts based on evidence

---

## Implementation Complete

All 6 phases of the Canonical Schema Propagation are now complete.

| Phase | Status | Deliverable |
|-------|--------|-------------|
| 0 | ✅ | Inventory audit + decisions |
| 1 | ✅ | `ai_document_schema.py` — canonical module |
| 2 | ✅ | `exec_create_document()` wired to canonical |
| 3 | ✅ | Tool schemas synced (backend + plugin) |
| 4 | ✅ | Alias ownership consolidated |
| 5 | ✅ | Frontend `DocumentType` aligned |
| 6 | ✅ | Telemetry + cleanup plan |

---

## 1. doc_type Audit

### Source A: `server/app/doc_type_registry.py`

**Canonical doc_type values** (from `ALL_DOC_TYPES` + `_FALLBACK_DOC_TYPES`):

| doc_type | Category |
|----------|----------|
| `sow` | Core |
| `igce` | Core |
| `acquisition_plan` | Core |
| `justification` | Core |
| `market_research` | Core |
| `son_products` | Intake |
| `son_services` | Intake |
| `conference_request` | Compliance |
| `conference_waiver` | Compliance |
| `promotional_item` | Compliance |
| `exemption_determination` | Compliance |
| `mandatory_use_waiver` | Compliance |
| `buy_american` | Compliance |
| `gfp_form` | Form |
| `subk_plan` | Compliance |
| `subk_review` | Compliance |
| `reference_guide` | Reference |
| `bpa_call_order` | Solicitation |
| `cor_certification` | Award |
| `technical_questionnaire` | Form |
| `quotation_abstract` | Solicitation |
| `receiving_report` | Administration |
| `srb_request` | Evaluation |
| `eval_criteria` | Markdown-only |
| `security_checklist` | Markdown-only |
| `section_508` | Markdown-only |
| `contract_type_justification` | Markdown-only |

**Aliases** (from `_DOC_TYPE_ALIASES`):

| Alias | Canonical |
|-------|-----------|
| `ige` | `igce` |
| `independent_government_estimate` | `igce` |
| `independent_government_cost_estimate` | `igce` |
| `cost_estimate` | `igce` |
| `statement_of_work` | `sow` |
| `pws` | `sow` |
| `performance_work_statement` | `sow` |
| `ap` | `acquisition_plan` |
| `acq_plan` | `acquisition_plan` |
| `j_a` | `justification` |
| `j&a` | `justification` |
| `ja` | `justification` |
| `sole_source` | `justification` |
| `sole_source_justification` | `justification` |
| `mr` | `market_research` |
| `mrr` | `market_research` |
| `son` | `son_products` |
| `statement_of_need` | `son_products` |
| `statement_of_need_products` | `son_products` |
| `statement_of_need_services` | `son_services` |
| `cor` | `cor_certification` |
| `cor_appointment` | `cor_certification` |
| `subcontracting_plan` | `subk_plan` |
| `sub_k_plan` | `subk_plan` |
| `subcontracting_review` | `subk_review` |
| `sub_k_review` | `subk_review` |
| `baa` | `buy_american` |
| `buy_american_act` | `buy_american` |
| `bpa` | `bpa_call_order` |
| `blanket_purchase_agreement` | `bpa_call_order` |
| `conference` | `conference_request` |
| `conf_request` | `conference_request` |
| `conf_waiver` | `conference_waiver` |
| `gfp` | `gfp_form` |
| `government_furnished_property` | `gfp_form` |
| `srb` | `srb_request` |
| `source_review_board` | `srb_request` |
| `receiving` | `receiving_report` |
| `tech_questionnaire` | `technical_questionnaire` |
| `quotation` | `quotation_abstract` |
| `promo_item` | `promotional_item` |
| `exemption` | `exemption_determination` |
| `mandatory_waiver` | `mandatory_use_waiver` |

---

### Source B: `server/app/tools/document_generation.py`

**`valid_doc_types` set** (runtime validation):

```python
valid_doc_types = {
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
    "purchase_request",      # NOT in doc_type_registry
    "price_reasonableness",  # NOT in doc_type_registry
    "required_sources",      # NOT in doc_type_registry
}
```

**Gap Analysis**: 3 types in `valid_doc_types` but NOT in `doc_type_registry`:
- `purchase_request`
- `price_reasonableness`
- `required_sources`

---

### Source C: `server/app/tools/create_document_support.py`

**`_DOC_TYPE_ALIASES`** (duplicate alias map):

| Alias | Canonical |
|-------|-----------|
| `ige` | `igce` |
| `igce` | `igce` |
| `independent_government_estimate` | `igce` |
| `independent_government_cost_estimate` | `igce` |
| `cost_estimate` | `igce` |
| `statement_of_work` | `sow` |
| `section_l` | `eval_criteria` |
| `instructions_to_offerors` | `eval_criteria` |
| `section_m` | `eval_criteria` |
| `evaluation_factors` | `eval_criteria` |
| `evaluation_criteria` | `eval_criteria` |
| `source_selection_plan` | `acquisition_plan` |
| `ssp` | `acquisition_plan` |

**Gap Analysis**: 
- `section_l`, `section_m`, `evaluation_factors`, `ssp` aliases exist here but NOT in `doc_type_registry.py`
- This is a **duplicate alias map** that should be consolidated

---

### Source D: `client/types/schema.ts`

**Frontend `DocumentType` union**:

```typescript
export type DocumentType =
  | 'sow'
  | 'igce'
  | 'market_research'
  | 'acquisition_plan'
  | 'justification'
  | 'funding_doc'           // NOT in backend
  | 'eval_criteria'
  | 'security_checklist'
  | 'section_508'
  | 'cor_certification'
  | 'contract_type_justification'
  | 'd_f'                   // NOT in backend
  | 'qasp'                  // NOT in backend
  | 'source_selection_plan' // NOT in backend
  | 'subcontracting_plan'   // Backend uses subk_plan
  | 'sb_review'             // NOT in backend (similar to subk_review?)
  | 'purchase_request'
  | 'human_subjects';       // NOT in backend
```

**Gap Analysis — Frontend types NOT in backend**:
- `funding_doc`
- `d_f` (Determination & Findings)
- `qasp` (Quality Assurance Surveillance Plan)
- `source_selection_plan`
- `sb_review` vs `subk_review` naming mismatch
- `human_subjects`
- `subcontracting_plan` vs `subk_plan` naming mismatch

---

## 2. doc_type Reconciliation — Proposed Canonical Set

### Tier 1: Core Document Types (create_document supported)

| Canonical | Backend | Frontend | Status |
|-----------|---------|----------|--------|
| `sow` | ✅ | ✅ | Aligned |
| `igce` | ✅ | ✅ | Aligned |
| `market_research` | ✅ | ✅ | Aligned |
| `acquisition_plan` | ✅ | ✅ | Aligned |
| `justification` | ✅ | ✅ | Aligned |
| `eval_criteria` | ✅ | ✅ | Aligned |
| `security_checklist` | ✅ | ✅ | Aligned |
| `section_508` | ✅ | ✅ | Aligned |
| `cor_certification` | ✅ | ✅ | Aligned |
| `contract_type_justification` | ✅ | ✅ | Aligned |
| `son_products` | ✅ | ❌ | Add to frontend |
| `son_services` | ✅ | ❌ | Add to frontend |
| `purchase_request` | ✅ | ✅ | Aligned |

### Tier 2: Template/Form Types (registry only)

| Canonical | Backend | Frontend | Status |
|-----------|---------|----------|--------|
| `subk_plan` | ✅ | ❌ (`subcontracting_plan`) | Rename frontend |
| `subk_review` | ✅ | ❌ (`sb_review`?) | Clarify |
| `buy_american` | ✅ | ❌ | Add to frontend |
| `conference_request` | ✅ | ❌ | Add to frontend |
| `conference_waiver` | ✅ | ❌ | Add to frontend |
| `bpa_call_order` | ✅ | ❌ | Add to frontend |
| `gfp_form` | ✅ | ❌ | Add to frontend |
| `srb_request` | ✅ | ❌ | Add to frontend |

### Tier 3: Frontend-Only Types (need backend support or removal)

| Frontend Type | Decision |
|---------------|----------|
| `funding_doc` | Remove or add to backend |
| `d_f` | Remove or add to backend |
| `qasp` | Remove or add to backend |
| `source_selection_plan` | Remove — alias to `acquisition_plan` |
| `human_subjects` | Remove or add to backend |

---

## 3. Field Name Alias Audit

### Source A: `server/app/template_registry.py` — `FIELD_NAME_ALIASES`

| Alias | Canonical |
|-------|-----------|
| `competition_type` | `competition` |
| `competition_strategy` | `competition` |
| `full_open` | `competition` |
| `contract_period` | `period_of_performance` |
| `duration` | `period_of_performance` |
| `pop` | `period_of_performance` |
| `performance_period` | `period_of_performance` |
| `estimated_cost` | `estimated_value` |
| `budget` | `estimated_value` |
| `total_cost` | `total_estimate` |
| `total_value` | `estimated_value` |
| `requirement` | `description` |
| `requirement_description` | `description` |
| `objective` | `description` |
| `requirement_summary` | `description` |
| `contractor_name` | `contractor` |
| `vendor` | `contractor` |
| `vendor_name` | `contractor` |
| `set_aside_recommendation` | `set_aside` |
| `set_aside_type` | `set_aside` |
| `small_business` | `set_aside` |
| `authority_cited` | `authority` |
| `far_authority` | `authority` |
| `justification_authority` | `authority` |
| `justification_rationale` | `rationale` |
| `vendors` | `vendors_identified` |
| `vendor_list` | `vendors_identified` |
| `market_analysis` | `market_conditions` |

---

### Source B: `server/app/compliance_matrix.py` — Enum Aliases

#### `_METHOD_ALIASES` (Acquisition Method)

| Alias | Canonical |
|-------|-----------|
| `full_and_open` | `negotiated` |
| `full and open` | `negotiated` |
| `full_and_open_competition` | `negotiated` |
| `full_competition` | `negotiated` |
| `full competition` | `negotiated` |
| `far part 15` | `negotiated` |
| `part 15` | `negotiated` |
| `far_15` | `negotiated` |
| `sealed_bidding` | `negotiated` |
| `sealed bidding` | `negotiated` |
| `far part 14` | `negotiated` |
| `part 14` | `negotiated` |
| `simplified_acquisition` | `sap` |
| `simplified acquisition` | `sap` |
| `simplified` | `sap` |
| `far part 13` | `sap` |
| `part 13` | `sap` |
| `far_13` | `sap` |

#### `_TYPE_ALIASES` (Contract Type)

| Alias | Canonical |
|-------|-----------|
| `firm_fixed_price` | `ffp` |
| `firm fixed price` | `ffp` |
| `fixed_price` | `ffp` |
| `fixed price` | `ffp` |
| `fp_epa` | `fp-epa` |
| `fixed_price_epa` | `fp-epa` |
| `economic_price_adjustment` | `fp-epa` |
| `fixed_price_incentive` | `fpi` |
| `fp_incentive` | `fpi` |
| `fpif` | `fpi` |
| `cost_plus_fixed_fee` | `cpff` |
| `cost plus fixed fee` | `cpff` |
| `cost_plus` | `cpff` |
| `cost plus` | `cpff` |
| `cost_reimbursement` | `cpff` |

---

### Source C: `server/app/igce_generation_extractor.py` — Labor Categories

| Canonical | Aliases |
|-----------|---------|
| `project manager` | `pm`, `project lead`, `program manager` |
| `senior software engineer` | `senior developer`, `senior dev`, `sr engineer`, `sr developer` |
| `software engineer` | `developer`, `dev`, `engineer`, `programmer` |
| `junior software engineer` | `junior developer`, `junior dev`, `jr engineer`, `jr developer` |
| `cloud architect` | `solutions architect`, `aws architect`, `azure architect` |
| `data scientist` | `data analyst`, `ml engineer`, `machine learning engineer` |
| `devops engineer` | `site reliability engineer`, `sre`, `platform engineer` |
| `security engineer` | `cybersecurity engineer`, `infosec engineer`, `security analyst` |
| `qa engineer` | `test engineer`, `quality assurance`, `tester` |
| `technical writer` | `documentation specialist`, `tech writer` |
| `business analyst` | `ba`, `requirements analyst` |
| `system administrator` | `sysadmin`, `sys admin`, `it administrator` |
| `database administrator` | `dba`, `database engineer` |
| `network engineer` | `network administrator`, `network admin` |
| `help desk` | `support specialist`, `it support`, `technical support` |

---

## 4. Proposed Canonical Field Set by Doc Type

### Cross-Document Common Fields

| Field | Type | Description |
|-------|------|-------------|
| `title` | string | Document title |
| `description` | string | Requirement/objective description |
| `estimated_value` | number | Total estimated cost |
| `period_of_performance` | string | Duration or date range |
| `contract_type` | enum | FFP, T&M, CPFF, etc. |
| `acquisition_method` | enum | negotiated, sap, sole_source, micro |
| `competition` | enum | full_open, limited, sole_source |

### SOW-Specific Fields

| Field | Type |
|-------|------|
| `deliverables` | list[string] or list[object] |
| `tasks` | list[string] or list[object] |
| `place_of_performance` | string |
| `security_requirements` | string |

### IGCE-Specific Fields

| Field | Type |
|-------|------|
| `line_items` | list[object] — labor categories |
| `goods_items` | list[object] — equipment/licenses |
| `period_months` | number |
| `delivery_date` | string (ISO date) |
| `overhead_rate` | number |
| `contingency_rate` | number |

### Market Research Fields

| Field | Type |
|-------|------|
| `naics_code` | string |
| `vendors_identified` | list[string] or list[object] |
| `market_conditions` | string |
| `set_aside` | enum |
| `conclusion` | string |

### Justification Fields

| Field | Type |
|-------|------|
| `authority` | string (FAR citation) |
| `contractor` | string |
| `rationale` | string |
| `efforts_to_compete` | string |

### Acquisition Plan Fields

| Field | Type |
|-------|------|
| `funding_by_fy` | object |
| `milestones` | list[object] |
| `set_aside` | enum |

---

## 5. Issues Requiring Resolution

### Issue 1: Duplicate Alias Maps

**Location**: `create_document_support.py:_DOC_TYPE_ALIASES` duplicates `doc_type_registry.py:_DOC_TYPE_ALIASES`

**Resolution**: Delete `create_document_support._DOC_TYPE_ALIASES`, use `doc_type_registry.normalize_doc_type()` instead.

---

### Issue 2: Frontend/Backend doc_type Mismatch

**Frontend types not in backend**:
- `funding_doc`, `d_f`, `qasp`, `source_selection_plan`, `human_subjects`

**Backend types not in frontend**:
- `son_products`, `son_services`, `buy_american`, `conference_request`, etc.

**Resolution**: Align frontend `DocumentType` with backend `ALL_DOC_TYPES`. Remove or add types as needed.

---

### Issue 3: Naming Inconsistency

| Frontend | Backend | Resolution |
|----------|---------|------------|
| `subcontracting_plan` | `subk_plan` | Use `subk_plan` |
| `sb_review` | `subk_review` | Use `subk_review` |

---

### Issue 4: `valid_doc_types` Drift

`document_generation.py:valid_doc_types` contains types not in `doc_type_registry`:
- `purchase_request`, `price_reasonableness`, `required_sources`

**Resolution**: Add these to `doc_type_registry.py` or remove from `valid_doc_types`.

---

## 6. Approved Canonical Values (Pending Team Review)

### Canonical doc_type Enum

```python
CANONICAL_DOC_TYPES = {
    # Core (create_document supported)
    "sow",
    "igce",
    "market_research",
    "acquisition_plan",
    "justification",
    "eval_criteria",
    "security_checklist",
    "section_508",
    "cor_certification",
    "contract_type_justification",
    "son_products",
    "son_services",
    "purchase_request",
    # Templates/Forms
    "subk_plan",
    "subk_review",
    "buy_american",
    "conference_request",
    "conference_waiver",
    "bpa_call_order",
    "gfp_form",
    "srb_request",
    "quotation_abstract",
    "receiving_report",
    "technical_questionnaire",
    "promotional_item",
    "exemption_determination",
    "mandatory_use_waiver",
    # Micro-purchase
    "price_reasonableness",
    "required_sources",
}
```

### Canonical contract_type Enum

```python
CANONICAL_CONTRACT_TYPES = {
    "ffp",      # Firm Fixed Price
    "fp-epa",   # Fixed Price with Economic Price Adjustment
    "fpi",      # Fixed Price Incentive
    "cpff",     # Cost Plus Fixed Fee
    "cpif",     # Cost Plus Incentive Fee
    "cpaf",     # Cost Plus Award Fee
    "t&m",      # Time and Materials
    "lh",       # Labor Hour
    "idiq",     # Indefinite Delivery Indefinite Quantity
    "bpa",      # Blanket Purchase Agreement
}
```

### Canonical acquisition_method Enum

```python
CANONICAL_ACQUISITION_METHODS = {
    "negotiated",   # FAR Part 15
    "sap",          # Simplified Acquisition Procedure (FAR 13)
    "sole_source",  # Sole Source / Limited Competition
    "micro",        # Micro-purchase (< $10K)
    "8a",           # 8(a) Set-Aside
    "hubzone",      # HUBZone Set-Aside
    "sdvosb",       # Service-Disabled Veteran-Owned Small Business
    "wosb",         # Women-Owned Small Business
}
```

---

## 7. Next Steps

1. **Review this inventory** — confirm canonical values with team
2. **Freeze aliases** — no new aliases until Phase 1 module lands
3. **Proceed to Phase 1** — create `server/app/ai_document_schema.py` based on approved values

---

## Appendix: File References

| File | Content |
|------|---------|
| `server/app/doc_type_registry.py` | Canonical doc_type registry |
| `server/app/tools/document_generation.py` | Runtime valid_doc_types |
| `server/app/tools/create_document_support.py` | Duplicate alias map |
| `server/app/template_registry.py` | Field name aliases |
| `server/app/compliance_matrix.py` | Method/type enum aliases |
| `server/app/igce_generation_extractor.py` | Labor category aliases |
| `client/types/schema.ts` | Frontend DocumentType |
