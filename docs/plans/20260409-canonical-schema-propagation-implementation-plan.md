# Canonical Schema Propagation Implementation Plan

## Metadata

- Date: 2026-04-09
- Source ticket: `docs/development/jira/jira-new-items-20260408.md`
- Ticket summary: Enforce canonical schema propagation for AI-generated data
- Status: Proposed implementation plan
- Priority: P1
- Estimated effort: 4-6 engineering days for the first production-safe iteration
- Recommended owner split:
  - Backend: primary owner
  - Frontend: secondary owner
  - QA/evals: shared follow-up

---

## Executive Summary

The ticket is valid, but the implementation should be narrower and more codebase-specific than a generic "single JSON schema for all AI-generated data" approach.

In the live EAGLE runtime, the primary AI document path is not structured-JSON-first. It is markdown-first with a supplemental `data` object:

- The active `create_document` tool instructs the model to provide full markdown `content`.
- The backend uses `data` only as supporting metadata for template population, package creation, checklist updates, and downstream extraction.
- The system already contains multiple partial normalization layers for the same conceptual data, which is the real source of schema drift risk.

The first implementation should therefore canonicalize these boundaries:

1. `doc_type`
2. `create_document.data`
3. Nested structured domains that materially affect persistence or business logic
   - IGCE structured fields such as `line_items`, `goods_items`, `contract_type`
   - acquisition/compliance fields such as `acquisition_method`, `competition`, `estimated_value`

It should not attempt to force a single schema over:

- full markdown document bodies
- every frontend document rendering payload
- every historical record in DynamoDB before validation is in place

The right architecture is:

- one canonical backend registry for AI-produced structured document metadata
- doc-type-aware validation at the `exec_create_document()` boundary
- shared canonical enums and aliases used by both backend and frontend
- controlled normalization first, hard rejection later

---

## Problem Statement

The ticket describes AI-generated schema drift such as:

- lowercase or inconsistent `doc_type` values
- variants like `Son` vs `sow` vs `Sb Review`
- changing field names such as `requirement`, `description`, `requirement_description`
- inconsistent enum-like values for contract type or acquisition method
- inconsistent nested structures such as IGCE line items or vendor lists

This creates instability across:

- template population
- package creation and checklist completion
- DynamoDB persistence
- SSE tool results
- frontend document type handling
- filtering, reporting, and future analytics

The risk is not theoretical. The current codebase already contains duplicated normalization rules to compensate for AI inconsistency.

---

## Current State Audit

### 1. `doc_type` canonicalization already exists, but it is duplicated

The repo already has a centralized document type registry:

- `server/app/doc_type_registry.py`

This file defines:

- canonical underscore-based `doc_type` values
- recognized document categories
- alias normalization such as `ige -> igce`, `statement_of_work -> sow`, `son -> son_products`

However, `create_document` does not fully rely on this registry. It also contains its own local alias logic:

- `server/app/tools/create_document_support.py`

That second alias map covers some overlapping values but is not the same source of truth. This is an architecture smell and a direct contributor to drift.

### 2. Field-name canonicalization exists, but only for template placeholder maps

The repo already has a field alias layer:

- `server/app/template_registry.py`

This layer maps variants such as:

- `requirement -> description`
- `estimated_cost -> estimated_value`
- `competition_type -> competition`
- `vendors -> vendors_identified`

This normalization is useful but limited:

- it is tied to placeholder maps
- it only normalizes known aliases
- it preserves unknown keys
- it does not validate nested structures
- it is not the sole registry for structured AI metadata

### 3. IGCE extraction has its own schema and aliasing rules

The IGCE path has additional structure:

- `server/app/igce_generation_extractor.py`

This file defines:

- labor category aliases
- extraction patterns for `line_items`, `goods_items`, `contract_type`, `period_months`, `delivery_date`

This is effectively another canonicalization layer, separate from:

- `doc_type` normalization
- template placeholder normalization
- compliance normalization

### 4. Compliance logic has its own enum normalization

The compliance engine defines canonical aliases for:

- acquisition methods
- contract types

File:

- `server/app/compliance_matrix.py`

This is yet another set of enum canonicalization rules that should be reused by the AI metadata boundary instead of left isolated.

### 5. The live runtime contract is in the backend, not only in plugin JSON

There are two different tool-schema surfaces:

- `eagle-plugin/tools/tool-definitions.json`
- `server/app/strands_agentic_service.py` (`EAGLE_TOOLS`)

The live service and streaming endpoints expose the backend `EAGLE_TOOLS`, not the plugin JSON alone.

Implication:

- changing plugin JSON only will not fix the active runtime path
- any canonical schema rollout must update backend tool definitions first

### 6. The active `create_document` path is markdown-first

The live `create_document` tool in `server/app/strands_agentic_service.py` explicitly tells the model:

- always provide full markdown `content`
- `data` is supplementary metadata, not the primary document body

The execution path in `server/app/tools/document_generation.py` confirms this:

- `content` is used when present
- `data` is augmented and normalized
- template population uses `data`
- package/workspace persistence stores the normalized `doc_type`

Implication:

- the canonical schema should focus on structured metadata, not the full document body

### 7. Frontend document types have already drifted from the backend

The frontend defines a manual `DocumentType` union in:

- `client/types/schema.ts`

This union contains values that do not match the current `create_document` valid set one-for-one. That means there is already backend/frontend type divergence before considering AI output drift.

---

## Root Cause Analysis

The current issue is caused by five overlapping problems.

### A. Multiple partial sources of truth

The codebase has separate normalization logic for:

- `doc_type`
- field names
- labor categories
- acquisition methods
- contract types

These should be coordinated through one canonical backend metadata model.

### B. Validation happens too late or not at all

`exec_create_document()` currently:

- normalizes `doc_type`
- normalizes some field names
- may extract IGCE structure
- proceeds to persistence and downstream generation

But it does not perform a canonical doc-type-aware validation step that:

- checks allowed fields
- checks nested structure
- checks enum values
- emits warnings for unknown fields
- returns one normalized typed object for downstream use

### C. Tool contracts are not synchronized

The plugin tool JSON and the live backend tool schema are not a single source of truth.

### D. The frontend is typing document categories separately

The frontend manual union for `DocumentType` is not clearly derived from backend canonical values.

### E. The system compensates for AI drift instead of constraining it centrally

The code currently handles drift by adding localized alias maps rather than enforcing a single boundary model.

---

## Recommended Scope

## In Scope for Iteration 1

- canonicalize `doc_type`
- canonicalize `create_document.data`
- canonicalize nested structured IGCE metadata
- canonicalize acquisition method and contract type enums used in structured AI data
- make backend runtime tool schema and plugin tool schema consistent
- align frontend `DocumentType` and related label maps to canonical backend values
- add boundary tests and regression coverage

## Explicitly Out of Scope for Iteration 1

- validating full markdown document bodies against a single JSON schema
- migrating every historical document record before runtime validation ships
- replacing all template schemas with JSON Schema
- solving every classification/document-type issue outside the `create_document` boundary
- broad DynamoDB cleanup without telemetry-backed inventory

---

## Target Architecture

### Canonical Backend Boundary

Introduce one canonical backend module for AI-generated structured document metadata.

Recommended new module:

- `server/app/ai_document_schema.py`

This module should own:

- canonical `doc_type` resolution
- canonical field names
- per-doc-type allowed fields
- per-doc-type required fields where appropriate
- canonical enums
- alias maps for known variants
- nested object and array structure definitions
- normalization + validation entrypoints

### Proposed Model Shape

Use Pydantic models as the runtime contract because:

- the backend already depends on Pydantic
- validation is needed at the Python boundary
- the initial problem is primarily backend-centric
- frontend types can be derived later from a small exported artifact if needed

Suggested model layers:

- `CanonicalDocType`
- `CanonicalContractType`
- `CanonicalAcquisitionMethod`
- `BaseDocumentData`
- `SowDocumentData`
- `IgceDocumentData`
- `MarketResearchDocumentData`
- `JustificationDocumentData`
- `AcquisitionPlanDocumentData`

Nested supporting models:

- `IgceLineItem`
- `IgceGoodsItem`
- `VendorCandidate`
- `DeliverableItem`
- `TaskItem`

Note:

The first iteration can allow `deliverables` and `tasks` to remain `list[str]` if that best matches current generators. Do not force object arrays unless the current code actually needs them.

### Canonical Boundary Function

Recommended public entrypoint:

```python
def normalize_and_validate_document_payload(
    *,
    raw_doc_type: str,
    title: str,
    data: dict[str, Any] | None,
) -> CanonicalDocumentPayload:
    ...
```

This function should:

1. normalize `doc_type`
2. apply shared alias mapping
3. apply doc-type-specific alias mapping
4. normalize enums such as contract type and acquisition method
5. validate nested structures
6. return typed normalized data plus warnings

Suggested response shape:

```python
class CanonicalDocumentPayload(BaseModel):
    doc_type: str
    title: str
    data: dict[str, Any]
    warnings: list[str] = []
    unknown_fields: list[str] = []
```

For iteration 1, warnings should be logged and returned internally. Unknown fields should not immediately hard-fail unless they are known to break downstream logic.

---

## Recommended Implementation Plan

## Phase 0. Inventory and Contract Freeze

### Goal

Stop adding new schema drift while implementation is underway.

### Tasks

1. Identify the current canonical `doc_type` list from:
   - `server/app/doc_type_registry.py`
   - live `create_document` valid set in `server/app/tools/document_generation.py`
   - frontend `DocumentType` in `client/types/schema.ts`
2. Reconcile naming mismatches and produce one approved list.
3. Record current field variants observed in:
   - `server/app/template_registry.py`
   - `server/app/igce_generation_extractor.py`
   - `server/app/compliance_matrix.py`
   - prompt-context extraction in `server/app/strands_agentic_service.py`
4. Freeze new aliases until the canonical module lands.

### Deliverable

- canonical inventory table checked into this plan or a follow-up schema inventory doc

### Exit Criteria

- approved canonical `doc_type` set
- approved canonical field names for the structured `data` boundary

---

## Phase 1. Create the Canonical Backend Schema Module

### Goal

Create one backend-owned source of truth for AI-generated structured document metadata.

### Tasks

1. Add a new module:
   - `server/app/ai_document_schema.py`
2. Move or wrap `doc_type` normalization so `create_document` uses the central registry rather than a local alias map.
3. Define shared canonical enums:
   - `doc_type`
   - `contract_type`
   - `acquisition_method`
4. Define a shared field alias registry covering current known variants:
   - `requirement -> description`
   - `requirement_description -> description`
   - `estimated_cost -> estimated_value`
   - `budget -> estimated_value`
   - `competition_type -> competition`
   - and other current known aliases from the existing code
5. Add doc-type-specific Pydantic models for `data`.
6. Add enum normalizers that reuse current compliance logic concepts rather than duplicating them again.
7. Add support for nested IGCE structures.

### Design Constraints

- preserve current behavior where possible
- do not reject fields that are still needed by markdown generators unless they are truly invalid
- preserve backward compatibility for known aliases

### Deliverables

- `server/app/ai_document_schema.py`
- unit tests for normalization and validation

### Exit Criteria

- one importable function can turn raw `doc_type` and `data` into a canonical payload

---

## Phase 2. Apply the Canonical Boundary in `exec_create_document()`

### Goal

Make the active execution path enforce canonicalization before persistence or generation.

### Primary file

- `server/app/tools/document_generation.py`

### Tasks

1. Replace direct local normalization flow:
   - raw `doc_type`
   - `normalize_field_names()`
   - IGCE extraction patch-up
2. Insert the canonical boundary after context augmentation and before generation.
3. Normalize and validate:
   - `doc_type`
   - `data`
   - contract/acquisition enums
4. Log warnings for:
   - remapped aliases
   - unknown fields
   - invalid enum variants that were auto-corrected
5. Keep `content` markdown behavior unchanged for iteration 1.
6. Replace the hardcoded `valid_doc_types` set with a canonical approved set sourced from the central registry.

### Important sequencing

Order should be:

1. contextual augmentation
2. canonical normalization/validation
3. IGCE post-processing only if still needed
4. document generation and persistence

If IGCE extraction still needs to enrich the payload after normalization, that enrichment must run through the canonical model again or return already-canonical fields.

### Deliverables

- updated `exec_create_document()`
- structured warning logs
- regression tests around accepted legacy aliases

### Exit Criteria

- all `create_document` runtime paths pass through the canonical boundary

---

## Phase 3. Unify the Runtime Tool Contracts

### Goal

Ensure the model-facing tool schema reflects the same canonical structure as the backend.

### Primary files

- `server/app/strands_agentic_service.py`
- `eagle-plugin/tools/tool-definitions.json`

### Tasks

1. Update the live backend `create_document` tool schema in `EAGLE_TOOLS`.
2. Keep plugin tool JSON synchronized as a secondary artifact.
3. Tighten descriptions for `data` fields to match canonical names.
4. Ensure the prompt guidance references canonical names consistently.
5. Do not attempt full output-schema enforcement on markdown `content`.
6. If tool metadata supports it later, add a documented schema artifact reference for `data`, not for the whole response body.

### Important note

The live Strands runtime is the priority because:

- `streaming_routes.py` exports `strands_agentic_service.EAGLE_TOOLS`
- plugin JSON is not the sole runtime contract

### Deliverables

- synchronized backend and plugin tool schemas
- updated tool docstrings/prompts

### Exit Criteria

- model-visible tool descriptions and backend validation agree on canonical field names

---

## Phase 4. Consolidate Alias Ownership

### Goal

Remove duplicated schema knowledge scattered across the codebase.

### Tasks

1. Refactor `server/app/tools/create_document_support.py` to stop owning its own overlapping `doc_type` alias map where possible.
2. Refactor `server/app/template_registry.py` so field aliases come from the canonical schema module.
3. Refactor `server/app/igce_generation_extractor.py` so labor and IGCE-related canonicalization is either:
   - owned by the extractor but exported through the canonical module
   - or consumed by the canonical module directly
4. Refactor `server/app/compliance_matrix.py` consumers to reuse its enum normalization rather than shadowing it elsewhere.

### Deliverables

- reduced duplicate alias definitions
- clearer ownership boundaries

### Exit Criteria

- no second or third competing source of truth for `doc_type` and key structured metadata

---

## Phase 5. Frontend Type Propagation

### Goal

Align frontend document category types and parsing with backend canonical values.

### Primary files

- `client/types/schema.ts`
- `client/hooks/use-agent-stream.ts`
- any components relying on manual `DocumentType` unions or label maps

### Tasks

1. Replace or refactor the frontend `DocumentType` union so it matches the backend approved set.
2. Update `DOCUMENT_TYPE_LABELS` and related maps accordingly.
3. Ensure SSE parsing accepts the canonical backend `doc_type`/`document_type` values without guessing.
4. Add validation at the frontend parsing boundary for tool results if practical.
5. Keep fallback behavior permissive enough for partial rollout.

### Recommendation

For iteration 1, do not over-engineer code generation. A shared generated file is acceptable later, but the immediate need is convergence and regression protection.

### Deliverables

- aligned frontend document type definitions
- tests for tool-result parsing

### Exit Criteria

- frontend no longer carries a divergent document-type vocabulary

---

## Phase 6. Observability and Safe Cleanup

### Goal

Measure remaining drift before any historical migration.

### Tasks

1. Add structured logging in the canonical boundary:
   - normalized alias used
   - unknown field names
   - invalid enum corrected
   - rejected payloads if/when strict mode is enabled
2. Add a temporary log query or report for:
   - top unknown fields
   - top remapped `doc_type` values
   - top remapped contract/acquisition enums
3. After 1-2 release cycles, evaluate persisted data cleanup.
4. Only then write targeted migration scripts for:
   - document metadata records
   - package document metadata
   - any reporting tables that rely on stale values

### Deliverables

- drift telemetry
- cleanup backlog with actual evidence

### Exit Criteria

- historical cleanup scope is based on measured drift, not assumptions

---

## Detailed File-by-File Recommendations

## New Files

### `server/app/ai_document_schema.py`

Add:

- canonical enums
- alias maps
- doc-type-specific Pydantic models
- normalization helpers
- validation entrypoint

### `server/tests/test_ai_document_schema.py`

Add:

- `doc_type` normalization tests
- field alias normalization tests
- enum normalization tests
- IGCE nested structure validation tests
- legacy compatibility tests

---

## Existing Files to Modify

### `server/app/tools/document_generation.py`

Modify to:

- use canonical boundary model
- remove ad hoc hardcoded validation logic where redundant
- log normalization warnings

### `server/app/strands_agentic_service.py`

Modify to:

- sync backend runtime `create_document` schema and descriptions
- ensure prompt-context-derived `data` uses canonical field names where feasible

### `server/app/template_registry.py`

Modify to:

- consume shared field alias registry from canonical module
- reduce independent schema ownership

### `server/app/tools/create_document_support.py`

Modify to:

- defer `doc_type` canonicalization to central registry
- remove local alias duplication where possible

### `server/app/igce_generation_extractor.py`

Modify to:

- expose canonical IGCE structures compatible with the shared schema

### `client/types/schema.ts`

Modify to:

- align `DocumentType` with canonical backend values
- update labels and icons as needed

### `client/hooks/use-agent-stream.ts`

Modify to:

- ensure `create_document` tool results are treated as canonical backend output
- add lightweight validation if warranted

### `eagle-plugin/tools/tool-definitions.json`

Modify to:

- sync with live runtime tool schema after backend changes land

---

## Proposed Canonical Field Set by Domain

## Cross-Document Common Fields

- `description`
- `estimated_value`
- `period_of_performance`
- `contract_type`
- `acquisition_method`
- `competition`
- `template_reference`

## SOW

- `description`
- `period_of_performance`
- `deliverables`
- `tasks`
- `place_of_performance`
- `security_requirements`

## IGCE

- `description`
- `line_items`
- `goods_items`
- `contract_type`
- `period_months`
- `period_of_performance`
- `delivery_date`
- `estimated_value`
- `overhead_rate`
- `contingency_rate`

## Market Research

- `description`
- `naics_code`
- `vendors_identified`
- `market_conditions`
- `set_aside`
- `conclusion`

## Justification

- `description`
- `authority`
- `contractor`
- `estimated_value`
- `rationale`
- `efforts_to_compete`

## Acquisition Plan

- `description`
- `estimated_value`
- `period_of_performance`
- `competition`
- `contract_type`
- `funding_by_fy`
- `milestones`

Note:

This field list should be confirmed against actual template population needs before enforcement is made strict.

---

## Validation Strategy

## Iteration 1: Normalize and Warn

Behavior:

- normalize known aliases
- normalize known enum variants
- preserve unknown fields unless dangerous
- emit warnings and telemetry
- reject only malformed structures that are known to break generation or persistence

## Iteration 2: Soft Strict Mode

Behavior:

- reject unknown enum values
- reject invalid nested object structure
- optionally reject unknown top-level fields per doc type in controlled contexts

## Iteration 3: Hard Strict Mode

Behavior:

- reject all non-canonical structured payloads by default
- allow compatibility escape hatches only where explicitly documented

---

## Testing Plan

## Unit Tests

Add tests for:

- `doc_type` alias normalization
- conflicting aliases resolving to the approved canonical value
- field-name alias normalization
- enum normalization for acquisition method and contract type
- IGCE line item structure validation
- preservation of compatible legacy payloads

## Integration Tests

Update or add tests covering:

- `exec_create_document()` with legacy field names
- package document creation with canonicalized `doc_type`
- workspace document creation with canonicalized `doc_type`
- SSE `tool_result` parsing on the frontend

## Regression Tests

Add fixtures for cases like:

- `Son`
- `Sb Review`
- `statement_of_work`
- `requirement_description`
- `estimated_cost`
- `time_and_materials`
- `full_and_open`

## Observability Tests

Verify:

- warnings are logged when alias normalization occurs
- unknown fields are visible in telemetry/logging

---

## Risk Assessment

## Primary Risks

### 1. Breaking permissive legacy flows

The current system often succeeds because it is permissive. If validation becomes strict too early, document generation may regress.

Mitigation:

- use normalize-and-warn mode first
- add compatibility fixtures from existing alias maps

### 2. Duplicated ownership persists

If the new canonical module is added but old alias maps remain authoritative in practice, the plan will fail.

Mitigation:

- explicitly refactor callers to import the shared canonical module
- remove or deprecate duplicate maps after migration

### 3. Frontend/backend type mismatch remains

If backend canonicalization lands without frontend convergence, UI bugs may persist.

Mitigation:

- treat frontend type alignment as part of the same ticket, not a follow-up nice-to-have

### 4. Historical cleanup is attempted too early

Migrating stored records before the runtime boundary is stable can create unnecessary churn.

Mitigation:

- ship validation and telemetry first
- migrate only after evidence is collected

---

## Acceptance Criteria Mapping

### Ticket AC: A canonical schema is defined for the relevant AI-generated payloads

Satisfied by:

- canonical backend schema module for `doc_type` and `create_document.data`

### Ticket AC: Approved keys, casing, enums, and nested structure are documented

Satisfied by:

- canonical models and this implementation plan
- code-level enums and field definitions

### Ticket AC: AI output is constrained or validated against the canonical schema

Satisfied by:

- backend boundary validation in `exec_create_document()`
- updated live backend tool schema and prompt guidance

### Ticket AC: Non-canonical keys are rejected, mapped, or normalized in a controlled way

Satisfied by:

- alias normalization registry
- warning telemetry
- phased strictness rollout

### Ticket AC: Backend and frontend consumers are updated to rely on the canonical schema

Satisfied by:

- backend canonical boundary
- frontend `DocumentType` convergence
- SSE parsing alignment

### Ticket AC: Existing inconsistent key usage is identified and cleaned up where required

Satisfied by:

- drift telemetry first
- targeted cleanup second

### Ticket AC: Tests cover schema validation and propagation behavior

Satisfied by:

- unit, integration, and regression tests described above

---

## Recommended Delivery Sequence

1. Implement canonical backend schema module.
2. Wire it into `exec_create_document()`.
3. Reconcile live backend tool schema.
4. Align frontend `DocumentType`.
5. Add tests and telemetry.
6. Evaluate historical cleanup after observing real drift.

This sequence minimizes risk because it fixes the active runtime boundary before attempting documentation-only or migration-only work.

---

## Concrete Recommendation

Do not implement this ticket as "one global JSON schema for every AI-generated payload."

Implement it as:

- a backend-owned canonical schema for AI-produced structured document metadata
- enforced at the `create_document` execution boundary
- shared across `doc_type`, field aliases, and enum normalization
- propagated outward to frontend types and tool descriptions

That approach directly addresses the real drift in this codebase and avoids overfitting the solution to markdown content that is not actually structured in the same way.

---

## Suggested Follow-Up Tickets

If this work is split, use these follow-ups:

### Follow-Up A

Backend canonical schema boundary for `create_document`

### Follow-Up B

Frontend `DocumentType` and SSE contract alignment

### Follow-Up C

Schema drift telemetry and historical metadata cleanup

### Follow-Up D

Strict-mode validation rollout for AI-generated structured document metadata

