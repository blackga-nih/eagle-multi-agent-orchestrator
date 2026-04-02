# Document Chat + IGCE XLSX Edit Implementation Plan

Status: proposed

## Goal

Make the bottom chat in the document view do two things reliably for IGCE Excel workbooks:

1. retain and use the original conversation and package context
2. apply safe, structured edits to the `.xlsx` workbook without destroying formulas

This plan is intentionally scoped to the current commercial IGCE workbook flow first.

## Problem

The current document chat path is only partially context-aware and is not safe for `.xlsx` editing.

### Current context behavior

File:

- `/Users/hoquemi/Desktop/sm_eagle/client/app/documents/[id]/page.tsx`

Current behavior:

- the bottom chat prompt pulls some local session context via `loadSession(sessionId)`
- it also includes a document excerpt and document metadata
- this works only when the right `sessionId` is present and the relevant browser session state still exists

Impact:

- opening a document later can lose the original generation context
- the document chat may not know the package, acquisition details, or source conversation that produced the IGCE

### Current XLSX edit behavior

Files:

- `/Users/hoquemi/Desktop/sm_eagle/client/app/documents/[id]/page.tsx`
- `/Users/hoquemi/Desktop/sm_eagle/server/app/tools/create_document_support.py`

Current behavior:

- for DOCX, the prompt tells the assistant to use `edit_docx_document`
- for non-DOCX binary docs, including `.xlsx`, the prompt tells the assistant to use `create_document` with `update_existing_key`
- `update_existing_key` routes into `_update_document_content()`, which is markdown/text oriented

Impact:

- the bottom chat does not use the safe XLSX edit route
- a model following the current prompt can regenerate markdown-like content instead of structured workbook edits
- there is no guarantee that workbook inputs, formulas, or cell targeting stay correct

### Existing safe XLSX path

Files:

- `/Users/hoquemi/Desktop/sm_eagle/server/app/routers/documents.py`
- `/Users/hoquemi/Desktop/sm_eagle/server/app/spreadsheet_edit_service.py`

Current behavior:

- the top-right spreadsheet editor already has a structured save flow
- `/xlsx-edit/{doc_key}` applies `cell_edits`
- formula cells remain read-only
- workbook formulas are preserved

Impact:

- the safe persistence mechanism already exists
- the missing piece is an AI-to-`cell_edits` translation layer and better context plumbing

## Desired Behavior

For a generated IGCE workbook:

1. opening the document later should still give the bottom chat the original acquisition context
2. the bottom chat should understand user requests like:
   - "set Cloud Architect to $190/hour"
   - "add one more AWS licensing month"
   - "change contract type to T&M"
3. the chat should resolve those requests into valid editable workbook cells
4. the save path should go through the existing structured XLSX editor flow
5. formula cells such as `IGCE!G7`, `IT Services!D12`, and `IT Goods!G10` must remain formulas
6. the document view should refresh and show recalculated display values after edits
7. ambiguous requests should produce a clarification question, not a guessed workbook edit

## Non-Goals

This plan does not attempt to:

- build full natural-language spreadsheet editing for arbitrary workbooks
- support all alternate IGCE templates in the first pass
- allow formula authoring or formula edits through chat
- support workbook layout changes, merged-cell changes, or print setup edits

## Scope

First implementation scope:

- commercial IGCE workbook only
- document-view bottom chat only
- edits limited to mapped non-formula input cells on:
  - `IGCE`
  - `IT Services`
  - `IT Goods`

Out of scope for the first pass:

- arbitrary uploaded Excel documents
- educational/nonprofit/product/service alternate IGCE templates
- hidden sheet logic
- row insertion/deletion

## Architecture Summary

The solution should be a three-layer pipeline:

1. `Document Context Resolver`
- reconstruct origin context for a document from server-side metadata, package data, and optionally stored session state

2. `IGCE XLSX AI Edit Resolver`
- convert a natural language request into structured edit intents against known IGCE fields/cells

3. `Structured XLSX Save`
- translate intents into `cell_edits`
- apply them through the existing `/xlsx-edit` backend path

## Implementation Plan

### Phase 1. Fix document-chat context ownership

Objective:

- stop relying on browser session state as the sole source of truth for document context

Files:

- `/Users/hoquemi/Desktop/sm_eagle/client/app/documents/[id]/page.tsx`
- `/Users/hoquemi/Desktop/sm_eagle/server/app/document_service.py`
- `/Users/hoquemi/Desktop/sm_eagle/server/app/routers/documents.py`
- `/Users/hoquemi/Desktop/sm_eagle/server/app/unified_document_store.py`

Changes:

1. Ensure generated package and workspace documents persist origin metadata needed by the document chat
- `session_id`
- `package_id`
- `doc_type`
- `template_id` when available
- optionally a compact structured `source_data` snapshot for generated IGCEs

2. Extend document fetch responses to include origin context metadata
- `session_id`
- `package_id`
- `document_type`
- `origin_context_available`
- optional `source_data_summary`

3. Update the document page to prefer server-provided origin context over local-only browser state
- continue using `loadSession(sessionId)` as a supplemental source
- do not depend on it exclusively

Deliverable:

- opening a document later still gives the chat enough context to understand what the workbook is about

### Phase 2. Split XLSX chat editing from markdown document editing

Objective:

- stop sending `.xlsx` chat edits through `create_document update_existing_key`

Files:

- `/Users/hoquemi/Desktop/sm_eagle/client/app/documents/[id]/page.tsx`
- `/Users/hoquemi/Desktop/sm_eagle/server/app/tools/create_document_support.py`
- `/Users/hoquemi/Desktop/sm_eagle/server/app/routers/documents.py`

Changes:

1. Change the bottom-chat prompt logic for `.xlsx`
- do not instruct the model to use `create_document update_existing_key`
- introduce an XLSX-specific instruction path

2. Add a dedicated tool or route contract for spreadsheet AI edits
- suggested tool name: `edit_xlsx_document`
- input:
  - `document_key`
  - `request`
  - optional `doc_type`
  - optional `session_id`

3. Keep markdown update flow unchanged for text documents

Deliverable:

- `.xlsx` document chat no longer routes through markdown update semantics

### Phase 3. Add IGCE semantic edit resolver

Objective:

- convert user requests into workbook-safe edit intents

Files:

- new file:
  - `/Users/hoquemi/Desktop/sm_eagle/server/app/igce_xlsx_edit_resolver.py`
- possibly:
  - `/Users/hoquemi/Desktop/sm_eagle/server/app/igce_xlsx_mapper.py`
  - `/Users/hoquemi/Desktop/sm_eagle/server/app/spreadsheet_edit_service.py`

Changes:

1. Define normalized IGCE edit intent types

Examples:

- `update_labor_rate`
- `update_labor_hours`
- `update_goods_quantity`
- `update_goods_unit_price`
- `update_contract_type`
- `update_period_of_performance`
- `update_delivery_date`

2. Map known IGCE concepts to cell targets

Examples:

- `Cloud Architect` hourly rate
  - summary sheet: `IGCE!E7`
  - services sheet: `IT Services!C12`
- `AWS Licensing` quantity
  - goods sheet: `IT Goods!E10`
- contract type
  - `IT Services!B5`
  - `IT Goods!B5`

3. Restrict edits to editable input cells only
- do not target formula cells
- do not target literal template markers like `x` or `=`

4. Support multi-cell coordinated edits when needed
- if one business concept appears on multiple sheets, update both relevant input cells

5. Return unresolved intents when the request is ambiguous

Deliverable:

- a deterministic request-to-cell resolver for commercial IGCE workbooks

### Phase 4. Add AI-assisted intent extraction

Objective:

- let the bottom chat understand natural user language while still producing structured edit intents

Files:

- new file:
  - `/Users/hoquemi/Desktop/sm_eagle/server/app/xlsx_ai_edit_service.py`
- possibly:
  - `/Users/hoquemi/Desktop/sm_eagle/server/app/strands_agentic_service.py`

Changes:

1. Build a narrow prompt or tool schema for IGCE edit extraction
- input:
  - document metadata
  - document chat request
  - origin conversation summary
  - current known IGCE rows/items from preview data
- output:
  - structured intents only, not free-form regenerated content

2. Validate extracted intents before applying them
- item name must match a known row or known alias
- target cell must be editable
- numeric values must parse cleanly

3. If intent extraction confidence is low
- return clarification instead of applying edits

Deliverable:

- user language is translated into safe, structured edit intents

### Phase 5. Execute edits through the existing XLSX save flow

Objective:

- reuse the safe workbook persistence path already in place

Files:

- `/Users/hoquemi/Desktop/sm_eagle/server/app/routers/documents.py`
- `/Users/hoquemi/Desktop/sm_eagle/server/app/spreadsheet_edit_service.py`
- new file if needed:
  - `/Users/hoquemi/Desktop/sm_eagle/server/app/xlsx_ai_edit_service.py`

Changes:

1. Convert validated intents into `cell_edits`

2. Call the existing structured XLSX edit pipeline
- same persistence path as manual spreadsheet edits
- same formula-preserving behavior

3. Return refreshed preview payload
- `preview_sheets`
- `preview_mode`
- recalculated display values
- list of changed cells

Deliverable:

- AI chat edits and manual grid edits share the same safe backend save mechanism

### Phase 6. Refresh document UI after AI edit

Objective:

- make the chat-driven workbook changes immediately visible

Files:

- `/Users/hoquemi/Desktop/sm_eagle/client/app/documents/[id]/page.tsx`

Changes:

1. After AI edit success:
- replace local `xlsxPreviewSheets`
- replace local editable preview copy
- keep the active sheet if it still exists

2. Show an applied-changes summary in chat

Examples:

- `Updated IGCE!E7 from 175 to 190`
- `Updated IT Services!C12 from 175 to 190`

3. If partial success:
- show changed cells
- show unresolved requests separately

Deliverable:

- user sees what changed without needing to download immediately

## Data Model Additions

Suggested new metadata fields for generated documents:

- `session_id`
- `source_context_type`
  - `chat_generated`
  - `template_generated`
  - `uploaded`
- `source_data`
  - compact structured subset used for generation
- `document_capabilities`
  - `supports_docx_ai_edit`
  - `supports_xlsx_ai_edit`
  - `supports_manual_xlsx_edit`

Suggested new response fields for `GET /api/documents/...`:

- `session_id`
- `origin_context_available`
- `document_capabilities`
- `source_data_summary`

## IGCE Cell Mapping Strategy

Start with deterministic mapping for the commercial workbook only.

Suggested first-pass mappings:

### Summary Sheet

- labor description rows:
  - `A7`, `A8`, `A9`, `A11`, `A12`, `A13`, `A16`, `A17`, `A18`, `A21`, `A22`, `A23`
- labor quantity/hours:
  - column `C`
- labor rate:
  - column `E`
- ODC description rows:
  - `A30:A37`
- ODC total inputs:
  - `E30:E37`

### IT Services

- contract type:
  - `B5`
- period of performance:
  - `C6`, `E6`
- service rows:
  - descriptions in `A12:A18`
  - base year hours in `B12:B18`
  - base year rates in `C12:C18`

### IT Goods

- contract type:
  - `B5`
- delivery date:
  - `B6`
- goods rows:
  - description `A10:A17`
  - quantity `E10:E17`
  - unit price `F10:F17`

Rules:

- never edit formula columns directly
- never overwrite row labels unless the resolver explicitly targets them
- if a request references a known item by name, update every mapped input location for that item

## Ambiguity Rules

The system should ask a follow-up question instead of guessing when:

- the item name does not match any known row
- the request does not specify whether the user means quantity, rate, total, hours, or unit price
- the user requests a formula change
- the request implies row insertion beyond supported mapped rows
- the workbook variant is not the commercial IGCE template

Example clarification:

- `I found "Cloud Architect" in the workbook. Do you want to change the hourly rate, hours, or both?`

## Testing Plan

### Unit Tests

Files:

- new tests:
  - `/Users/hoquemi/Desktop/sm_eagle/server/tests/test_igce_xlsx_edit_resolver.py`
  - `/Users/hoquemi/Desktop/sm_eagle/server/tests/test_xlsx_ai_edit_service.py`

Coverage:

- natural-language request to intent extraction
- intent to cell mapping
- ambiguity detection
- invalid target rejection

### Integration Tests

Files:

- extend:
  - `/Users/hoquemi/Desktop/sm_eagle/server/tests/test_spreadsheet_edit_service.py`
  - `/Users/hoquemi/Desktop/sm_eagle/server/tests/test_template_service.py`

Coverage:

- generate commercial IGCE
- apply AI-driven edit intents
- confirm formulas remain formulas:
  - `IGCE!G7`
  - `IT Services!D12`
  - `IT Goods!G10`
- confirm display values update after edit

### UI Tests

Files:

- new or extended frontend/browser test

Coverage:

- open generated IGCE in document page
- bottom chat request updates workbook
- spreadsheet preview refreshes
- download remains valid `.xlsx`

## Acceptance Criteria

1. A generated commercial IGCE opened later still has enough origin context for meaningful follow-up edits.
2. The bottom chat for `.xlsx` no longer uses markdown regeneration semantics.
3. A request like `set Cloud Architect to $190/hour` updates the correct editable workbook cells.
4. Formula cells remain formulas after chat edits.
5. Recalculated display values appear in the in-app spreadsheet preview.
6. Ambiguous requests produce clarifying questions instead of silent workbook mutations.
7. Unsupported workbook variants or unsupported edit types fail safely with clear messaging.

## Rollout Order

Recommended order:

1. Context metadata plumbing
2. Prompt/path split for `.xlsx`
3. Deterministic commercial IGCE edit resolver
4. AI intent extraction wrapper
5. UI refresh and chat result summaries
6. Expanded coverage for alternate IGCE templates later

## Risks

### Risk 1. AI intent extraction may guess wrong

Mitigation:

- keep the extractor schema narrow
- validate against known workbook rows
- require clarification on low confidence

### Risk 2. Multiple-sheet synchronization may drift

Mitigation:

- centralize all IGCE business-to-cell mappings in one module
- test cross-sheet updates explicitly

### Risk 3. Context may be incomplete for older documents

Mitigation:

- add graceful fallback messaging
- allow user to continue with manual grid edit when origin context is unavailable

### Risk 4. Users may expect arbitrary spreadsheet editing

Mitigation:

- clearly label the feature as IGCE-aware workbook assistance
- keep the scope explicit in UI and error messages

## Recommended First Ticket Breakdown

1. Persist and expose document origin context for generated IGCE documents
2. Change `.xlsx` document chat prompt to stop using `create_document update_existing_key`
3. Add commercial IGCE request-to-cell resolver
4. Add backend AI spreadsheet edit service that emits `cell_edits`
5. Wire bottom chat success responses into the spreadsheet preview refresh
6. Add regression tests proving formulas survive AI-driven edits
