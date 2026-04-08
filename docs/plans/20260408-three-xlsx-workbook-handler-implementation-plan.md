# Three XLSX Workbook Handler Implementation Plan

Status: proposed

Date: 2026-04-08

## Goal

Implement reliable generation, preview-safe editing, and chat-assisted editing for the three Excel workbook templates that are actually present locally:

1. `01.D_IGCE_for_Commercial_Organizations.xlsx`
2. `4.a. IGE for Products.xlsx`
3. `4.b. IGE for Services based on Catalog Price.xlsx`

This plan extends the current commercial IGCE implementation pattern to the two IGE workbooks without introducing unsafe generic spreadsheet mutation behavior.

## Why This Scope

The codebase currently registers five Excel workbook names under the `igce` template family, but the local template folder contains only three real workbooks:

- `01.D_IGCE_for_Commercial_Organizations.xlsx`
- `4.a. IGE for Products.xlsx`
- `4.b. IGE for Services based on Catalog Price.xlsx`

The educational and nonprofit variants remain out of scope until the real files are available for inspection and testing.

This preserves the original planning principle from the existing IGCE XLSX plans:

- do not support all workbook variants too early
- do not generalize spreadsheet editing before the workbook structure is known
- do not let AI mutate spreadsheets outside a validated mapped-cell path

## Existing Baseline

The commercial IGCE path already provides the reference implementation pattern:

- workbook-specific population mapper:
  - `/Users/hoquemi/Desktop/sm_eagle/server/app/igce_xlsx_mapper.py`
- workbook-specific schema:
  - `/Users/hoquemi/Desktop/sm_eagle/server/app/igce_workbook_schema.py`
- workbook-specific edit/context resolver:
  - `/Users/hoquemi/Desktop/sm_eagle/server/app/igce_xlsx_edit_resolver.py`
- XLSX AI edit orchestration:
  - `/Users/hoquemi/Desktop/sm_eagle/server/app/xlsx_ai_edit_service.py`
- template population entry:
  - `/Users/hoquemi/Desktop/sm_eagle/server/app/template_service.py`

Current behavior:

- commercial IGCE generation uses a workbook-specific mapper
- commercial IGCE AI edits use a workbook-specific resolver
- spreadsheet save path is already structured and formula-safe
- workbook variants other than commercial are not implemented as first-class handlers

## Design Principle

Each workbook variant should have its own handler.

Do not try to make one generic "cost spreadsheet mapper" own all workbook semantics.

Instead:

- share infrastructure
- isolate workbook-specific cell mappings
- isolate workbook-specific edit semantics
- dispatch by template identity and workbook fingerprint

## Target Architecture

Introduce a workbook-handler layer with one handler per supported workbook.

### Shared Infrastructure

Shared infrastructure should remain generic:

- S3 template fetch and persistence
- preview extraction
- formula evaluation for preview only
- structured `cell_edits` save path
- common result dataclasses
- common parsing helpers
- common workbook dispatcher

### Workbook-Specific Logic

Workbook-specific logic should be isolated per workbook:

- workbook schema / mapped cells
- workbook fingerprint detection
- first-pass population logic
- item normalization logic
- context extraction from preview sheets
- semantic edit resolution
- context-fill logic from stored `source_data`

## Supported Workbooks In This Plan

### Workbook 1. Commercial IGCE

File:

- `01.D_IGCE_for_Commercial_Organizations.xlsx`

Role:

- current canonical implementation

Required action:

- refactor into the new handler architecture without behavior loss
- fix any current generation/edit drift before cloning the pattern

### Workbook 2. IGE for Products

File:

- `4.a. IGE for Products.xlsx`

Expected semantic shape:

- product/equipment line items
- quantity and unit-price style editing
- likely different metadata and totals from labor-based IGCE

Required action:

- inspect real workbook structure
- define its own schema
- build its own mapper
- build its own edit resolver

### Workbook 3. IGE for Services Based on Catalog Price

File:

- `4.b. IGE for Services based on Catalog Price.xlsx`

Expected semantic shape:

- services priced from catalog or schedule-like rates
- likely labor-like rows but not guaranteed to match the commercial IGCE workbook

Required action:

- inspect real workbook structure
- determine whether it is labor-row based, catalog-item based, or mixed
- build a dedicated schema and resolver rather than assuming commercial reuse

## Non-Goals

This plan does not attempt to:

- support arbitrary uploaded Excel files
- support educational or nonprofit IGCE files before the real files are available
- permit formula editing
- permit row insertion/deletion
- support layout changes, merged-cell edits, print settings, or styling edits
- unify all workbook families into one semantic model prematurely

## High-Level Phases

1. Create a workbook-handler abstraction
2. Refactor commercial IGCE behind it
3. Inspect and model `IGE for Products`
4. Implement `IGE for Products` generation/edit path
5. Inspect and model `IGE for Services based on Catalog Price`
6. Implement `IGE for Services based on Catalog Price` generation/edit path
7. Add dispatch by template identity and fingerprint
8. Add full regression coverage

## Phase 0. Preconditions And Baseline Verification

Objective:

- confirm the existing commercial XLSX pipeline remains the standard to preserve

Files to verify:

- `/Users/hoquemi/Desktop/sm_eagle/server/app/template_service.py`
- `/Users/hoquemi/Desktop/sm_eagle/server/app/spreadsheet_edit_service.py`
- `/Users/hoquemi/Desktop/sm_eagle/server/app/xlsx_ai_edit_service.py`
- `/Users/hoquemi/Desktop/sm_eagle/server/app/formula_evaluation.py`
- `/Users/hoquemi/Desktop/sm_eagle/server/tests/test_template_service.py`
- `/Users/hoquemi/Desktop/sm_eagle/server/tests/test_xlsx_ai_edit_service.py`

Required checks:

- formulas are preserved in generated commercial workbook files
- formulas remain read-only in preview/editor flows
- AI edit path uses structured `cell_edits`
- existing tests continue to pass

Important baseline issue to resolve:

- align generation and edit mapping for period-of-performance before using the commercial handler as the copy pattern

Exit criteria:

- commercial IGCE behavior is stable enough to serve as the reference implementation

## Phase 1. Introduce A Workbook Handler Contract

Objective:

- create one extensible interface for all supported workbook variants

New file:

- `/Users/hoquemi/Desktop/sm_eagle/server/app/xlsx_workbook_handlers.py`

Alternative structure if preferred:

- `/Users/hoquemi/Desktop/sm_eagle/server/app/xlsx_handlers/__init__.py`
- `/Users/hoquemi/Desktop/sm_eagle/server/app/xlsx_handlers/base.py`
- `/Users/hoquemi/Desktop/sm_eagle/server/app/xlsx_handlers/commercial_igce.py`
- `/Users/hoquemi/Desktop/sm_eagle/server/app/xlsx_handlers/ige_products.py`
- `/Users/hoquemi/Desktop/sm_eagle/server/app/xlsx_handlers/ige_services_catalog.py`

Recommended contract:

```python
class WorkbookHandler(Protocol):
    handler_id: str
    supported_template_filenames: tuple[str, ...]

    def matches_workbook(self, workbook) -> bool: ...
    def matches_preview(self, preview_sheets: list[dict[str, Any]]) -> bool: ...
    def populate(self, workbook, data: dict[str, Any]) -> bool: ...
    def build_context(self, preview_sheets: list[dict[str, Any]]) -> Any: ...
    def resolve_edit_request(self, request: str, context: Any) -> Any: ...
    def build_context_fill_intents(self, source_data: dict[str, Any] | None, context: Any) -> Any: ...
```

Dispatcher helpers to add:

- `get_handler_for_template_filename(filename: str) -> WorkbookHandler | None`
- `get_handler_for_template_id(template_id: str | None) -> WorkbookHandler | None`
- `get_handler_for_workbook(workbook) -> WorkbookHandler | None`
- `get_handler_for_preview(preview_sheets) -> WorkbookHandler | None`

Rules:

- prefer `template_id` / `template_path` based dispatch
- fall back to workbook fingerprint only if template identity is unavailable
- never fall back from one mapped handler to another by loose similarity

Exit criteria:

- shared handler interface exists
- no variant-specific branching remains embedded directly in orchestration code

## Phase 2. Refactor Commercial IGCE Into The Handler Architecture

Objective:

- preserve current commercial behavior while making it one instance of the new pattern

Files to refactor:

- `/Users/hoquemi/Desktop/sm_eagle/server/app/igce_xlsx_mapper.py`
- `/Users/hoquemi/Desktop/sm_eagle/server/app/igce_xlsx_edit_resolver.py`
- `/Users/hoquemi/Desktop/sm_eagle/server/app/igce_workbook_schema.py`
- `/Users/hoquemi/Desktop/sm_eagle/server/app/xlsx_ai_edit_service.py`
- `/Users/hoquemi/Desktop/sm_eagle/server/app/template_service.py`

Changes:

1. Wrap the current commercial mapper and resolver in `CommercialIGCEWorkbookHandler`
2. Keep the existing workbook schema module as the source of truth for that handler
3. Update `template_service` to ask the dispatcher for a matching handler instead of directly calling `CommercialIGCEWorkbookMapper.populate(...)`
4. Update `xlsx_ai_edit_service` to ask the dispatcher for the handler based on `template_id` or workbook preview instead of hard-coding commercial-only behavior
5. Preserve all existing commercial tests

Required cleanup:

- fix the commercial PoP mapping inconsistency so the commercial handler is internally coherent
- keep all current commercial acceptance tests intact

Exit criteria:

- commercial IGCE still works
- orchestration code no longer depends on direct commercial-specific imports for its core control flow

## Phase 3. Inventory And Reverse-Engineer `IGE for Products`

Objective:

- create a factual workbook map before implementation

Real file to inspect:

- `/Users/hoquemi/Downloads/rh-eagle/supervisor-core/essential-templates/4.a. IGE for Products.xlsx`

Artifacts to produce:

- sheet inventory
- sentinel formulas used for `matches()`
- editable input cells
- non-editable formula cells
- product row ranges
- metadata cells
- totals / summary sections
- visible labels and aliases needed for matching

Implementation note:

- do this from the real workbook, not from filename assumptions

Recommended output:

- new schema module:
  - `/Users/hoquemi/Desktop/sm_eagle/server/app/ige_products_workbook_schema.py`

Schema should define:

- sheet names
- metadata cells
- product row range(s)
- summary cells
- quantity / unit price / total columns
- any manufacturer, item number, shipping, warranty, or delivery fields if present

Required validation:

- inspect whether the workbook has one sheet or multiple
- inspect whether totals are formulas or literals
- inspect whether line items appear in a detailed tab, summary tab, or both

Exit criteria:

- `IGE for Products` workbook structure is fully documented in code constants before mapper logic begins

## Phase 4. Implement `IGE for Products` Generation Path

Objective:

- support first-pass workbook population for the products workbook

New files:

- `/Users/hoquemi/Desktop/sm_eagle/server/app/ige_products_xlsx_mapper.py`

Likely changes:

- `/Users/hoquemi/Desktop/sm_eagle/server/app/template_service.py`
- `/Users/hoquemi/Desktop/sm_eagle/server/app/tools/document_generation.py`
- `/Users/hoquemi/Desktop/sm_eagle/server/app/igce_generation_extractor.py`

Mapper responsibilities:

- `matches(workbook)` using sheet names plus sentinel formulas/labels
- normalize product line items from incoming data
- populate only editable input cells
- preserve formula columns intact
- set workbook calculation flags

Normalization logic to add:

- map `line_items`, `goods_items`, or equivalent data into a product row model
- accept fields like:
  - `description`
  - `product_name`
  - `manufacturer`
  - `manufacturer_number`
  - `part_number`
  - `quantity`
  - `unit`
  - `unit_price`
  - `delivery_date`
- derive totals only if the workbook expects literal inputs in non-formula cells

Do not:

- manually overwrite formula totals
- assume commercial IGCE labor-vs-goods splitting applies

Exit criteria:

- generation can populate the products workbook from structured data
- formulas remain intact

## Phase 5. Implement `IGE for Products` Edit And Chat Path

Objective:

- support safe semantic editing of the products workbook

New file:

- `/Users/hoquemi/Desktop/sm_eagle/server/app/ige_products_xlsx_edit_resolver.py`

Responsibilities:

- build workbook context from preview sheets
- bind editable cells for:
  - quantity
  - unit price
  - delivery date
  - contract type if present
  - product description / manufacturer fields only if truly editable
- resolve natural-language requests into structured edit intents
- support context-fill from stored `source_data`

Example supported requests:

- `Set microscope quantity to 3`
- `Change centrifuge unit price to 12500`
- `Set delivery date to 2026-10-15`
- `Increase freezer quantity by one`

Example likely unsupported requests:

- formula authoring
- row insertion
- adding a brand-new product row if no editable slot exists

Context-fill expectations:

- fill only empty cells
- report skipped fields with reasons
- never overwrite populated user inputs unless explicitly requested

Exit criteria:

- products workbook can be edited by chat and by manual structured save path without formula loss

## Phase 6. Inventory And Reverse-Engineer `IGE for Services based on Catalog Price`

Objective:

- determine the exact workbook family and avoid false reuse

Real file to inspect:

- `/Users/hoquemi/Downloads/rh-eagle/supervisor-core/essential-templates/4.b. IGE for Services based on Catalog Price.xlsx`

Artifacts to produce:

- sheet inventory
- metadata fields
- service item row ranges
- whether pricing is hourly, monthly, catalog lot, or mixed
- whether rows map to labor categories, fixed catalog offerings, or CLIN-like items
- sentinel formulas and labels for `matches()`

Recommended output:

- new schema module:
  - `/Users/hoquemi/Desktop/sm_eagle/server/app/ige_services_catalog_workbook_schema.py`

Questions this phase must answer:

- is this workbook structurally closer to the commercial IGCE labor tab?
- or is it closer to a product-style row grid with service descriptions and catalog rates?
- are totals formula-driven?
- are period / option year inputs present?

Exit criteria:

- real workbook structure is encoded in constants before mapper logic is written

## Phase 7. Implement `IGE for Services based on Catalog Price` Generation Path

Objective:

- support first-pass population for the catalog-services workbook

New file:

- `/Users/hoquemi/Desktop/sm_eagle/server/app/ige_services_catalog_xlsx_mapper.py`

Likely changes:

- `/Users/hoquemi/Desktop/sm_eagle/server/app/template_service.py`
- `/Users/hoquemi/Desktop/sm_eagle/server/app/tools/document_generation.py`
- `/Users/hoquemi/Desktop/sm_eagle/server/app/igce_generation_extractor.py`

Mapper responsibilities:

- identify workbook layout deterministically
- normalize service items into workbook rows
- populate only editable cells
- preserve formulas and structural template content

Potential normalized fields:

- `description`
- `catalog_item`
- `labor_category`
- `quantity`
- `hours`
- `period`
- `unit_price`
- `catalog_rate`
- `contract_type`
- `period_of_performance`

Important rule:

- only reuse commercial normalization logic if the inspected workbook proves that the same business meaning applies

Exit criteria:

- generation can materially populate the services-catalog workbook from structured data

## Phase 8. Implement `IGE for Services based on Catalog Price` Edit And Chat Path

Objective:

- support safe semantic edits for the services-catalog workbook

New file:

- `/Users/hoquemi/Desktop/sm_eagle/server/app/ige_services_catalog_xlsx_edit_resolver.py`

Responsibilities:

- context extraction from preview sheets
- row/item alias matching
- semantic edit resolution for the workbook’s real editable fields
- context-fill from stored `source_data`

Example supported requests may include:

- `Set Program Analyst rate to 125`
- `Change quantity to 12 months`
- `Update contract type to FFP`

But these examples must be validated against the actual workbook layout first.

Exit criteria:

- services-catalog workbook supports the same safe edit path as the commercial workbook, tailored to its own semantics

## Phase 9. Generalize Orchestration To Variant Dispatch

Objective:

- make generation and edit flows handler-driven instead of commercial-specific

### Template Generation Dispatch

Files:

- `/Users/hoquemi/Desktop/sm_eagle/server/app/template_service.py`

Change:

- replace direct commercial check with dispatcher lookup

Target behavior:

1. fetch template bytes
2. determine handler by:
   - `template_hint` filename first
   - fetched S3 key filename second
   - workbook fingerprint third
3. if a handler applies:
   - call `handler.populate(workbook, data)`
4. else:
   - keep generic placeholder XLSX fallback behavior

### AI Edit Dispatch

Files:

- `/Users/hoquemi/Desktop/sm_eagle/server/app/xlsx_ai_edit_service.py`

Change:

- replace commercial-specific context building and resolver calls with handler dispatch

Target behavior:

1. load workbook preview
2. identify handler by persisted `template_id` if available
3. fall back to workbook preview fingerprint if needed
4. build handler-specific context
5. resolve request using handler-specific semantics
6. save via `save_xlsx_preview_edits`

### Document Generation Metadata

Files:

- `/Users/hoquemi/Desktop/sm_eagle/server/app/tools/document_generation.py`
- `/Users/hoquemi/Desktop/sm_eagle/server/app/document_service.py`
- `/Users/hoquemi/Desktop/sm_eagle/server/app/user_document_store.py`

Required behavior:

- persist `template_id` or actual template path on every generated workbook
- preserve `source_data` snapshots when variant-specific structured extraction runs

Exit criteria:

- orchestration becomes variant-aware without becoming workbook-specific itself

## Phase 10. Structured Extraction Strategy

Objective:

- avoid forcing one extraction schema across incompatible workbook families

Current state:

- `extract_igce_generation_data(...)` enriches commercial-like IGCE generation payloads

Target approach:

### Shared Extraction Layer

Shared fields that may be reused across all three workbooks:

- `description`
- `contract_type`
- `period_of_performance`
- `delivery_date`
- `prepared_by`
- `prepared_date`
- `total_estimate`

### Variant-Specific Normalization Layers

Commercial IGCE:

- labor rows
- goods rows
- labor rates and hours

IGE Products:

- product item rows
- quantities and unit prices
- manufacturer/part details where applicable

IGE Services Based on Catalog Price:

- service rows
- catalog or schedule pricing fields
- quantity / period / rate fields according to actual structure

Recommended implementation:

- keep one shared extraction entry point
- route into a variant-specific normalizer after handler selection

Do not:

- encode `IGE for Products` semantics inside the commercial extractor
- treat product rows as goods rows just because the names sound similar

Exit criteria:

- structured data extraction is variant-aware where needed and shared only where appropriate

## Testing Plan

## Unit Tests

### Commercial Regression

Keep and extend:

- `/Users/hoquemi/Desktop/sm_eagle/server/tests/test_template_service.py`
- `/Users/hoquemi/Desktop/sm_eagle/server/tests/test_xlsx_ai_edit_service.py`

Add tests for:

- handler dispatch preserves current commercial behavior
- current commercial formula preservation remains intact
- PoP mapping is internally consistent between generation and edit paths

### `IGE for Products`

New tests:

- `/Users/hoquemi/Desktop/sm_eagle/server/tests/test_ige_products_mapper.py`
- `/Users/hoquemi/Desktop/sm_eagle/server/tests/test_ige_products_edit_resolver.py`

Coverage:

- workbook fingerprint detection
- correct editable cell bindings
- correct population of quantity and unit price
- formulas remain formulas
- ambiguous requests clarify safely
- unsupported requests refuse safely

### `IGE for Services based on Catalog Price`

New tests:

- `/Users/hoquemi/Desktop/sm_eagle/server/tests/test_ige_services_catalog_mapper.py`
- `/Users/hoquemi/Desktop/sm_eagle/server/tests/test_ige_services_catalog_edit_resolver.py`

Coverage:

- workbook fingerprint detection
- correct field mapping
- formula preservation
- safe semantic edits
- context-fill behavior

## Integration Tests

New integration tests:

- `/Users/hoquemi/Desktop/sm_eagle/server/tests/test_xlsx_workbook_handler_dispatch.py`

Coverage:

- generation dispatch chooses the correct handler by template path
- AI edit dispatch chooses the correct handler by persisted `template_id`
- fallback by workbook fingerprint works when metadata is missing

## UI / End-To-End Tests

Extend existing document-flow/browser tests to cover:

- open generated workbook
- apply chat edit
- preview refreshes with recalculated display values
- download remains valid `.xlsx`

At minimum:

- one e2e path per workbook variant

## Rollout Order

Recommended order:

1. Refactor commercial IGCE into handler architecture
2. Fix commercial inconsistencies
3. Implement `IGE for Products`
4. Implement `IGE for Services based on Catalog Price`
5. Expand UI/e2e coverage
6. Revisit educational/nonprofit only after real files are available

## Risks

### Risk 1. Copying commercial assumptions into IGE workbooks

Mitigation:

- inspect real workbook structures first
- require schema constants before implementation
- write workbook-specific tests from real structures

### Risk 2. Dispatch chooses the wrong handler

Mitigation:

- prefer persisted `template_id`
- use strict filename match next
- use fingerprint fallback only when necessary

### Risk 3. AI invents unsupported edits

Mitigation:

- handler-specific intent validation
- editable-cell-only save path
- clarification on ambiguity

### Risk 4. Formula loss or workbook corruption

Mitigation:

- never write formula cells directly
- retain current non-destructive preview evaluation model
- test real formulas in every variant

### Risk 5. Over-generalization makes later maintenance harder

Mitigation:

- share infrastructure only
- keep workbook semantics local to each handler

## Acceptance Criteria

1. The current commercial IGCE workbook continues to generate and edit correctly through the new handler architecture.
2. `IGE for Products` has a first-pass generation mapper and a safe semantic edit path.
3. `IGE for Services based on Catalog Price` has a first-pass generation mapper and a safe semantic edit path.
4. All three workbooks preserve formulas after generation and after manual/AI edits.
5. Generation and edit dispatch use persisted template provenance when available.
6. Unsupported workbook variants fail safely with explicit messaging.
7. No DOCX behavior regresses.
8. No generic XLSX fallback path is allowed to silently replace workbook-specific mapped behavior for these three files.

## Deliverables

Code deliverables:

- workbook-handler dispatcher
- commercial handler refactor
- products schema + mapper + resolver
- services-catalog schema + mapper + resolver
- orchestration updates
- new unit and integration tests

Documentation deliverables:

- this implementation plan
- brief per-workbook notes summarizing sheet structure and supported edit semantics once each workbook has been reverse-engineered
