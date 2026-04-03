# IGCE XLSX Generation And Editing Phased Plan

Status: reviewed

## Goal

Implement a two-stage commercial IGCE Excel workflow that is XLSX-specific:

1. General chat generates a first-pass IGCE `.xlsx` that is filled out as much as possible from conversation and package context.
2. The generated workbook preserves Excel formulas and template behavior.
3. The document-screen chat and manual spreadsheet edits both update the workbook through the same safe structured XLSX edit path.

## Scope Guardrails

This plan is intentionally limited to:

- `file_type == "xlsx"`
- `document_type == "igce"`
- the commercial IGCE workbook layout only

This plan must not change:

- DOCX generation behavior
- DOCX edit behavior
- markdown document generation behavior
- non-IGCE spreadsheet generation/editing

Out of scope:

- concurrent manual and AI edits (user will not edit while AI is working)

## Feasibility Summary

This plan is implementable in the current codebase because the key seams already exist:

- general chat already creates documents via `create_document`
- IGCE `.xlsx` generation already routes through `TemplateService`
- manual `.xlsx` edits already route through `save_xlsx_preview_edits`
- document metadata already persists `session_id`, `template_id`, and provenance
- the document viewer already supports spreadsheet preview/edit state

The missing piece is not workbook persistence. The missing piece is first-pass structured IGCE data extraction for workbook population.

## Core Design

Use one shared commercial IGCE workbook model for both:

- first-pass generation
- post-generation AI edits

That shared model must own:

- labor row mappings
- goods row mappings
- contract metadata cell mappings
- editable input cells
- protected formula cells
- item name normalization / alias matching

## Phase 0. Preconditions

Objective:

- ensure the branch has the workbook-safe Excel foundation before expanding generation behavior

Required state:

- formula-preserving workbook generation
- formula-safe XLSX preview extraction
- reliable IGCE commercial workbook mapping
- structured XLSX document-chat edit path

Files to verify or port from the Excel rebuild work if needed:

- `/Users/hoquemi/Desktop/sm_eagle/server/app/formula_evaluation.py`
- `/Users/hoquemi/Desktop/sm_eagle/server/app/template_service.py`
- `/Users/hoquemi/Desktop/sm_eagle/server/app/routers/documents.py`
- `/Users/hoquemi/Desktop/sm_eagle/server/app/spreadsheet_edit_service.py`

Exit criteria:

- generated IGCE `.xlsx` files retain formulas
- manual XLSX edits retain formulas
- document fetch returns both sidecar text and spreadsheet preview

## Phase 1. Create One Shared IGCE Workbook Model

Objective:

- stop duplicating workbook coordinates between generation and editing

New or refactored files:

- new shared workbook model module:
  - `/Users/hoquemi/Desktop/sm_eagle/server/app/igce_workbook_schema.py`
- refactor current edit resolver to consume that model:
  - `/Users/hoquemi/Desktop/sm_eagle/server/app/igce_xlsx_edit_resolver.py`
- refactor generation mapper to consume that model:
  - `/Users/hoquemi/Desktop/sm_eagle/server/app/template_service.py`
  - or extract commercial mapper from earlier branch into:
  - `/Users/hoquemi/Desktop/sm_eagle/server/app/igce_xlsx_mapper.py`

Functions / classes to add or refactor:

- `CommercialIGCEWorkbookSchema`
- `CommercialIGCEWorkbookContext`
- `build_commercial_igce_workbook_context(...)`
- `CommercialIGCEWorkbookMapper.populate(...)`
- `resolve_igce_edit_request(...)`

Required mappings:

- summary sheet labor rows
- summary sheet ODC / goods rows
- IT Services labor rows
- IT Goods rows
- contract type cells
- period of performance cells
- delivery date cells

Rules:

- formula cells are never editable
- summary total formulas are never overwritten unless the template expects a literal input cell
- all business-to-cell mappings live in one module

Exit criteria:

- generation code and edit code read cell locations from the same schema
- no duplicate hard-coded row maps remain across mapper and edit resolver

## Phase 2. Add Structured IGCE Generation Data Extraction

Objective:

- make first-pass `.xlsx` generation workbook-aware instead of markdown-first

New file:

- `/Users/hoquemi/Desktop/sm_eagle/server/app/igce_generation_extractor.py`

Existing files to change:

- `/Users/hoquemi/Desktop/sm_eagle/server/app/tools/document_generation.py`
- `/Users/hoquemi/Desktop/sm_eagle/server/app/tools/create_document_support.py`
- `/Users/hoquemi/Desktop/sm_eagle/server/app/strands_agentic_service.py`

Functions to add:

- `extract_igce_generation_data(...)`
- `merge_igce_generation_context(...)`
- optional narrow LLM helper:
  - `extract_igce_generation_data_with_bedrock(...)`

Inputs:

- current user prompt
- recent session messages
- active package metadata
- explicit `data` passed by the agent, if any

Outputs:

- normalized structured payload with keys like:
  - `line_items`
  - `goods_items`
  - `contract_type`
  - `period_of_performance`
  - `delivery_date`
  - `estimated_value`
  - `description`
  - `prepared_by`
  - `prepared_date`

Implementation approach:

1. deterministic extraction first
- money / dates / contract type / period parsing
- list-item extraction from bullets or numbered lines
- package metadata merge

2. narrow LLM JSON extraction second
- only when deterministic extraction is insufficient
- output schema is strict and workbook-oriented
- do not generate document prose here

Latency note:

- narrow LLM extraction adds ~500ms–1.5s (Haiku) or ~1–3s (Sonnet)
- acceptable for first-pass generation where users already expect a few seconds
- caching extraction results is a future optimization (inputs are stable)

Changes in `strands_agentic_service.py`:

- keep `create_document` generic for DOCX/markdown
- add an IGCE XLSX-specific enrichment path before tool dispatch
- exact area:
  - `create_document_tool(...)`
  - `_extract_context_data_from_prompt(...)`

Changes in `document_generation.py`:

- for `doc_type == "igce"` and `output_format == "xlsx"`, run `extract_igce_generation_data(...)` before template generation
- merge extracted fields into `data`

Exit criteria:

- first-pass IGCE generation has structured line items often enough to meaningfully populate workbook rows
- DOCX and markdown generation paths remain unchanged

## Phase 3. Use Structured Extraction In The IGCE XLSX Creation Path

Objective:

- ensure general chat creates a substantially filled workbook on first pass

Primary files:

- `/Users/hoquemi/Desktop/sm_eagle/server/app/tools/document_generation.py`
- `/Users/hoquemi/Desktop/sm_eagle/server/app/template_service.py`
- `/Users/hoquemi/Desktop/sm_eagle/server/app/formula_evaluation.py`

Functions to change:

- `exec_create_document(...)`
- `TemplateService.generate_document(...)`
- `TemplateService._generate_from_template(...)`
- `IGCEPositionPopulator.populate(...)` or replacement mapper
- `evaluate_workbook_formulas(...)`

Required behavior:

- for IGCE XLSX:
  - populate workbook from structured extraction output
  - preserve formulas in saved workbook
  - use preview-only evaluation for in-app rendering
- for DOCX / markdown:
  - leave behavior unchanged

Important note:

The current `main` branch still uses `IGCEPositionPopulator` directly. If the commercial mapper from `fix/excel-docs-rebuild` is stronger, port it and make it the canonical commercial IGCE population path.

Exit criteria:

- general chat can create an IGCE `.xlsx` with labor lines, goods lines, and contract metadata populated on the first pass
- downloaded workbook still contains live formulas

## Phase 4. Persist Origin Creation Context With The Workbook

Objective:

- let post-generation edits use the same context the workbook was created from

Files to change:

- `/Users/hoquemi/Desktop/sm_eagle/server/app/document_service.py`
- `/Users/hoquemi/Desktop/sm_eagle/server/app/document_store.py`
- `/Users/hoquemi/Desktop/sm_eagle/server/app/unified_document_store.py`
- `/Users/hoquemi/Desktop/sm_eagle/server/app/tools/document_generation.py`

Fields to persist for generated IGCE `.xlsx` docs:

- `session_id`
- `package_id`
- `template_id`
- `template_provenance`
- `source_context_type`
- compact `source_data_summary`
- optional compact `source_data`

Rules:

- do not persist full raw conversation text into document metadata
- store only compact structured generation context needed for follow-up edits

Exit criteria:

- a generated IGCE opened later still has enough origin context for follow-up chat edits

## Phase 5. Expose Origin Context And Capabilities On Document Fetch

Objective:

- make the document page reliably aware of edit capability and context availability

Files to change:

- `/Users/hoquemi/Desktop/sm_eagle/server/app/routers/documents.py`
- `/Users/hoquemi/Desktop/sm_eagle/client/types/chat.ts`
- `/Users/hoquemi/Desktop/sm_eagle/client/lib/document-store.ts`
- `/Users/hoquemi/Desktop/sm_eagle/client/app/documents/[id]/page.tsx`

Response fields to include:

- `session_id`
- `origin_context_available`
- `document_capabilities`
- `source_data_summary`

Rules:

- spreadsheet preview and sidecar text must both be returned for previewable `.xlsx`
- capability flags must be format-specific

Exit criteria:

- document page can reliably decide whether bottom-chat XLSX editing is available

## Phase 6. Expand Document Chat From Targeted Edits To Context-Based Fill

Objective:

- allow document chat to fill missing workbook fields using original context, not just direct update commands

Files to change:

- `/Users/hoquemi/Desktop/sm_eagle/server/app/xlsx_ai_edit_service.py`
- `/Users/hoquemi/Desktop/sm_eagle/server/app/igce_xlsx_edit_resolver.py`
- `/Users/hoquemi/Desktop/sm_eagle/client/app/documents/[id]/page.tsx`

Functions to add or expand:

- `resolve_context_fill_request(...)`
- `build_context_fill_intents(...)`
- `edit_igce_xlsx_document(...)`

Supported request shapes:

- targeted edit:
  - `Set Cloud Architect to $190/hour`
- context-backed follow-up:
  - `Use our earlier discussion to fill out the rest of the IGCE`
  - `Complete the pricing details from the package context`

Rules:

- only fill mapped supported fields
- do not invent workbook rows beyond the supported row slots
- if a value cannot be inferred confidently, leave it unchanged and report it

Unfillable field reporting (error UX):

- AI edit response includes `skipped_fields` array with reasons
- frontend displays inline banner above spreadsheet: "Could not determine: [field list]. Provide these values directly."
- chat message echoes what was updated and what was skipped

Exit criteria:

- document chat can apply multi-cell updates from origin context without damaging the workbook
- unfillable fields are reported clearly to the user via banner and chat message

## Phase 7. Keep Manual And AI Spreadsheet Edits On The Same Save Path

Objective:

- ensure one workbook-safe persistence path

Files:

- `/Users/hoquemi/Desktop/sm_eagle/server/app/spreadsheet_edit_service.py`
- `/Users/hoquemi/Desktop/sm_eagle/server/app/xlsx_ai_edit_service.py`
- `/Users/hoquemi/Desktop/sm_eagle/client/app/documents/[id]/page.tsx`

Rule:

- AI-generated edits must always become `cell_edits`
- manual and AI edits both call the same `save_xlsx_preview_edits(...)`

Exit criteria:

- formulas stay intact regardless of whether the change was manual or AI-driven

## Phase 8. Test Matrix

### Backend Unit Tests

Add or extend:

- `/Users/hoquemi/Desktop/sm_eagle/server/tests/test_igce_generation_extractor.py`
- `/Users/hoquemi/Desktop/sm_eagle/server/tests/test_xlsx_ai_edit_service.py`
- `/Users/hoquemi/Desktop/sm_eagle/server/tests/test_template_service.py`
- `/Users/hoquemi/Desktop/sm_eagle/server/tests/test_formula_evaluation.py`

Coverage:

- structured IGCE extraction from prompt + session data
- mapper population for commercial workbook
- targeted AI edits
- context-based fill edits
- formula preservation
- skipped_fields array populated for unfillable values

### Backend Integration Tests

Add or extend:

- `/Users/hoquemi/Desktop/sm_eagle/server/tests/test_document_generation.py`
- `/Users/hoquemi/Desktop/sm_eagle/server/tests/test_spreadsheet_edit_service.py`
- `/Users/hoquemi/Desktop/sm_eagle/server/tests/test_document_helpers.py`

Coverage:

- general chat generation path creates a populated IGCE `.xlsx`
- generated workbook keeps formulas
- document fetch returns sidecar content plus preview sheets
- post-generation AI edits preserve formulas

### Frontend Verification

Files:

- `/Users/hoquemi/Desktop/sm_eagle/client/app/documents/[id]/page.tsx`
- `/Users/hoquemi/Desktop/sm_eagle/client/app/api/documents/[id]/xlsx-ai-edit/route.ts`

Coverage:

- open generated IGCE workbook
- bottom chat updates workbook
- spreadsheet preview refreshes
- manual edits still save correctly
- unfillable field banner displays when AI cannot determine values

## Risks And Mitigations

### Risk 1. Generation mapping and edit mapping drift

Addressed by this plan:

- yes

Mitigation:

- Phase 1 creates one shared workbook schema module
- both creation and editing must consume that same schema

### Risk 2. First-pass workbook population is inconsistent because general chat is markdown-first

Addressed by this plan:

- yes

Mitigation:

- Phase 2 adds a dedicated structured IGCE extractor
- Phase 3 makes IGCE XLSX generation consume that structured payload

### Risk 3. DOCX behavior regresses while adding XLSX logic

Addressed by this plan:

- yes, if scope guards are enforced

Mitigation:

- all new generation/edit behavior is gated by:
  - `doc_type == "igce"`
  - `output_format == "xlsx"` or `file_type == "xlsx"`
- DOCX routes and DOCX prompt behavior remain separate

### Risk 4. AI overreaches and invents unsupported workbook changes

Addressed by this plan:

- yes

Mitigation:

- only mapped editable cells may be changed
- unsupported requests produce clarification or refusal
- AI output is converted into validated structured intents, not direct workbook mutations

### Risk 5. Formula loss during first pass or later edits

Addressed by this plan:

- yes, assuming Phase 0 preconditions hold

Mitigation:

- workbook generation preserves formulas
- preview evaluation is non-destructive
- manual and AI edits both use the same structured XLSX save path

### Risk 6. Trying to support all workbook variants too early

Addressed by this plan:

- yes

Mitigation:

- commercial IGCE only in first implementation
- alternate templates remain out of scope until the commercial path is stable

## Recommended Implementation Order

1. Phase 0
2. Phase 1
3. Phase 2
4. Phase 3
5. Phase 4
6. Phase 5
7. Phase 6
8. Phase 7
9. Phase 8

## Acceptance Criteria

1. General chat generates a commercial IGCE `.xlsx` with meaningful first-pass population from context.
2. Generated workbook preserves Excel formulas and recalculates in Excel.
3. Document-screen chat can use stored origin context for follow-up workbook edits.
4. Manual spreadsheet edits and AI chat edits both preserve formulas.
5. DOCX generation and DOCX editing behavior remain unchanged.
6. Unsupported or ambiguous requests fail safely with clarification instead of corrupting the workbook.
