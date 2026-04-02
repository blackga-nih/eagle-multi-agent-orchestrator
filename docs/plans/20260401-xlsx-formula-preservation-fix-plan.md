# XLSX Formula Preservation Fix Plan

Status: proposed

## Problem

Generated IGCE workbooks are losing real Excel formulas during the template population pipeline.

Confirmed example:

- Generated workbook: `/Users/hoquemi/Downloads/Independent-Government-Cost-Estimate---I-need-an-I.xlsx`
- Source template: `/Users/hoquemi/Downloads/rh-eagle/supervisor-core/essential-templates/01.D_IGCE_for_Commercial_Organizations.xlsx`

Comparison result:

- `IGCE` sheet: `35` template formulas, `9` generated formulas, `26` missing/replaced
- `IT Services` sheet: `52` template formulas, `0` generated formulas, `52` missing/replaced
- `IT Goods` sheet: `9` template formulas, `0` generated formulas, `9` missing/replaced

Total missing/replaced formulas: `87`

Examples of formulas present in the template but replaced with `0` in the generated workbook:

- `IGCE!G7 = C7*E7`
- `IGCE!G26 = SUM(G7:G23)`
- `IGCE!G28 = G26*B28`
- `IT Services!D12 = B12*C12`
- `IT Services!G12 = E12*F12`
- `IT Goods!G10 = F10*E10`
- `IT Goods!B19 = SUM(G10:G17)`

## Root Causes

### 1. Formula evaluation is destructive

File:

- `/Users/hoquemi/Desktop/sm_eagle/server/app/formula_evaluation.py`

Current behavior:

- `evaluate_workbook_formulas()` calculates workbook formulas
- then overwrites formula cells by assigning `cell.value = computed_value`

Impact:

- the saved/exported workbook no longer contains formulas
- later edits cannot recalculate using Excel formulas
- the in-app preview can only show static values, not workbook logic

### 2. XLSX template generation returns evaluated bytes instead of workbook bytes

File:

- `/Users/hoquemi/Desktop/sm_eagle/server/app/template_service.py`

Current behavior:

- `XLSXPopulator.populate()` saves the workbook to bytes
- then immediately returns `evaluate_workbook_formulas_safe(populated_bytes)`

Impact:

- every generated `.xlsx` is passed through destructive formula flattening before it is stored or downloaded

### 3. Real IGCE template does not use `{{PLACEHOLDER}}` tokens

Files:

- `/Users/hoquemi/Desktop/sm_eagle/server/app/template_registry.py`
- `/Users/hoquemi/Desktop/sm_eagle/server/app/template_service.py`

Current behavior:

- the populator assumes the template contains `{{PROJECT_TITLE}}`, `{{LINE_ITEMS}}`, etc.
- the real commercial IGCE workbook contains zero `{{...}}` placeholders

Impact:

- placeholder-based replacement is not enough to populate the actual workbook
- the current generic strategy does not map cleanly to the real template structure

### 4. Hard-coded line-item insertion does not match the commercial IGCE workbook layout

File:

- `/Users/hoquemi/Desktop/sm_eagle/server/app/template_service.py`

Current behavior:

- `_insert_line_items()` writes:
  - column `A` item number
  - column `B` description
  - column `C` quantity
  - column `D` unit
  - column `E` unit price
  - column `F` total

But the real commercial IGCE sheet uses:

- `C` = hours/effort
- `D` = literal `x`
- `E` = hourly rate/base salary
- `F` = literal `=`
- `G` = total formula

Impact:

- generic insertion logic is not aligned with the workbook’s actual structure
- even after formula preservation is fixed, data mapping still needs template-specific logic

## Correct Target Behavior

For generated and edited `.xlsx` documents:

1. Save the workbook with formulas intact
2. Show calculated values in preview when possible
3. Keep formula cells read-only in the in-app editor
4. Allow non-formula input cells to be edited and saved
5. Preserve workbook fidelity so downloaded files continue recalculating in Excel

## Required Fixes

### Fix 1. Make formula evaluation non-destructive

File:

- `/Users/hoquemi/Desktop/sm_eagle/server/app/formula_evaluation.py`

Change:

- stop replacing formula cell contents with computed values
- preserve original formula strings in the workbook
- provide calculated values only for preview extraction

Implementation options:

1. Preferred:
- change `evaluate_workbook_formulas()` to return a separate calculated-value map keyed by `Sheet!Cell`
- use that map during preview extraction instead of mutating the workbook

2. Acceptable short-term:
- keep current evaluator API shape, but do not write computed values back into the workbook
- return original workbook bytes and a sidecar structure for preview use

Do not:

- assign `cell.value = val` for formula cells in the persisted/exported workbook

### Fix 2. Stop flattening formulas during XLSX generation

File:

- `/Users/hoquemi/Desktop/sm_eagle/server/app/template_service.py`

Change:

- in `XLSXPopulator.populate()`, return the populated workbook bytes directly
- do not call destructive formula evaluation before returning workbook content

Current problematic line:

- returns `evaluate_workbook_formulas_safe(populated_bytes)`

Target behavior:

- return `populated_bytes`
- preview calculation should happen later, outside the persisted workbook path

### Fix 3. Keep preview calculation as preview-only

Files:

- `/Users/hoquemi/Desktop/sm_eagle/server/app/spreadsheet_edit_service.py`
- `/Users/hoquemi/Desktop/sm_eagle/server/app/template_service.py`

Change:

- preview extraction may calculate formulas
- saved/exported workbook bytes must remain untouched

Desired boundary:

- source workbook: formulas preserved
- preview payload: computed values shown where available

### Fix 4. Replace generic IGCE XLSX population with template-specific mapping

Files:

- `/Users/hoquemi/Desktop/sm_eagle/server/app/template_service.py`
- optionally a new module such as:
  - `/Users/hoquemi/Desktop/sm_eagle/server/app/igce_xlsx_mapper.py`

Change:

- add a dedicated population routine for the commercial IGCE workbook
- target known cells/ranges directly instead of relying on `{{PLACEHOLDER}}`

Suggested mapping for `IGCE` sheet:

- metadata/header cells:
  - title/program info
  - acquisition plan references
  - prepared by
  - prepared date
- labor rows:
  - map item rows explicitly
  - write effort/hours into column `C`
  - preserve literal `x` in column `D`
  - write hourly rate into column `E`
  - preserve literal `=` in column `F`
  - preserve total formula in column `G`

For `IT Services` and `IT Goods`:

- either:
  - preserve template sheets untouched unless the selected template variant requires them
- or:
  - add explicit mapping logic for those tabs too

Do not:

- write totals into formula columns manually when the template already defines the formula
- overwrite cells that should remain formulas

### Fix 5. Preserve formulas during spreadsheet edits

File:

- `/Users/hoquemi/Desktop/sm_eagle/server/app/spreadsheet_edit_service.py`

Current behavior is mostly correct here:

- editable cells are restricted to non-formula cells
- formula cells are treated as read-only

Required confirmation after formula fix:

- saving cell edits must continue writing only user-editable cells
- formula cells must remain present in the saved workbook
- preview refresh must display recalculated values after editable inputs change

## Code-Level Change Summary

### `server/app/formula_evaluation.py`

Refactor:

- `evaluate_workbook_formulas()` should no longer mutate workbook formulas into values
- add a helper to build preview calculation results without changing persisted workbook bytes

Potential API shape:

```python
def calculate_workbook_formulas(xlsx_bytes: bytes) -> tuple[dict[str, Any], bool]:
    ...
```

or:

```python
def evaluate_workbook_formulas_for_preview(xlsx_bytes: bytes) -> tuple[bytes, dict[str, Any], bool]:
    ...
```

But the key rule is:

- exported workbook must still contain `=...`

### `server/app/template_service.py`

Refactor:

- `XLSXPopulator.populate()` should:
  - populate workbook
  - save workbook to bytes
  - return workbook bytes without destructive evaluation

Add:

- IGCE-specific sheet mapping logic
- explicit row/column mapping for the commercial workbook

### `server/app/spreadsheet_edit_service.py`

Refactor:

- preview extraction should use preview-only calculation results
- formula display should come from computed values when available
- saved bytes must remain formula-preserving

## Test Updates Required

### Update formula evaluation tests

File:

- `/Users/hoquemi/Desktop/sm_eagle/server/tests/test_formula_evaluation.py`

Current tests incorrectly lock in destructive behavior:

- `test_replaces_formulas_with_computed_values`

Replace with tests that assert:

1. `data_only=True` returns computed values for preview
2. `data_only=False` still shows original formulas
3. workbooks with formulas remain formula-bearing after generation/editing

### Add real-template regression test

New test coverage should:

1. load the real IGCE commercial template fixture
2. run `XLSXPopulator.populate()` with sample data
3. assert that formula coordinates still contain formulas:
   - `IGCE!G7`
   - `IGCE!G26`
   - `IT Services!D12`
   - `IT Goods!G10`
4. assert preview values are available where inputs are populated

### Add end-to-end document generation regression test

Cover:

- create IGCE document
- download resulting `.xlsx`
- reopen with `openpyxl(data_only=False)`
- confirm formulas survive

## Rollout Order

### Phase 1. Safe preservation fix

1. patch `template_service.py` so generated workbooks are not returned as evaluated/destructive bytes
2. patch `formula_evaluation.py` so formulas are preserved
3. update formula-evaluation tests

Outcome:

- generated workbooks retain formulas again

### Phase 2. Preview correctness

1. make preview extraction consume calculated values without mutating formulas
2. verify formula cells display computed totals in the UI

Outcome:

- in-app lightweight editor remains usable
- users see totals/calculated fields

### Phase 3. IGCE-specific template mapping

1. replace generic placeholder-only population for IGCE
2. map commercial workbook cells/ranges explicitly
3. validate generated workbook against real template structure

Outcome:

- generated IGCE workbook is structurally faithful to the actual Excel template

## Acceptance Criteria

The fix is complete when all of the following are true:

1. Generated IGCE `.xlsx` files preserve the real formulas from the source template
2. Downloaded workbooks open in Excel with formulas intact
3. In-app preview shows calculated values for formula cells where calculation succeeds
4. Editing non-formula cells and saving does not remove dependent formulas
5. Formula regression tests pass using the real commercial IGCE workbook structure

## Non-Goals

- Full Excel authoring in browser
- Editing formula cells in-app
- Recreating every Excel behavior in the lightweight preview

The correct boundary remains:

- lightweight in-app patch editing for input cells
- workbook fidelity preserved for download/use in Excel
