# Excel Formula Handling Fix — Implementation Plan

**Date**: 2026-03-24
**Owner**: EAGLE Engineering
**Status**: Draft
**Branch target**: `fix/excel-formula-handling`

---

## 1. Executive Summary

EAGLE's Excel (XLSX) handling has three critical issues:

| Issue | Symptom | Root Cause |
|-------|---------|------------|
| Formulas display as text | Users see `=B2*C2` instead of `3000` | Fallback to raw formula when cached value is `None` |
| No recalculation after edits | Totals stay stale after changing inputs | `openpyxl` has no formula engine |
| Poor preview UX | Hard to scan/review spreadsheet data | Minimal styling, no visual hierarchy |

This plan fixes all three issues using the `formulas` Python library for calculation and frontend improvements for UX.

---

## 2. Current State Analysis

### 2.1 Backend: Preview Extraction

**File**: `server/app/spreadsheet_edit_service.py`

```python
# Lines 117-118: Two workbook loads
wb = load_workbook(io.BytesIO(xlsx_bytes), data_only=False)      # formulas preserved
wb_values = load_workbook(io.BytesIO(xlsx_bytes), data_only=True) # cached values only

# Line 144: Problematic fallback
display_value = value_cell.value if value_cell.value is not None else raw_value
```

**Problem**: When `data_only=True`, openpyxl reads cached formula results. If the file was:
- Generated programmatically (by `XLSXPopulator`)
- Never opened in Excel after creation

Then cached values are `None`, and the fallback shows the raw formula string.

### 2.2 Backend: Template Population

**File**: `server/app/template_service.py`

`XLSXPopulator.populate()` creates/modifies XLSX files but never triggers formula recalculation. The saved file has formulas but no cached results.

### 2.3 Frontend: Preview Rendering

**File**: `client/app/documents/[id]/page.tsx` (lines 1778-1826)

Current issues:
- Fixed `min-w-[110px]` on all cells
- No sticky headers for scrolling
- Formula cells only get subtle `text-gray-500`
- No legend explaining cell types
- No tooltip showing actual formula

---

## 3. Solution Design

### 3.1 Formula Evaluation Library

**Choice**: `formulas` Python library

| Library | Pros | Cons |
|---------|------|------|
| `formulas` | Pure Python, lightweight, good coverage | Some complex functions unsupported |
| `xlcalc` | Good accuracy | Less maintained |
| LibreOffice headless | Most accurate | Heavy external dependency |
| `pycel` | Mature | Heavier, graph-based |

`formulas` is the best balance of simplicity and capability for IGCE-style spreadsheets (basic math, SUM, IF, etc.).

### 3.2 Architecture Change

```
Before:
  XLSX bytes → openpyxl (data_only=True) → cached values (often None) → raw formula fallback

After:
  XLSX bytes → formulas.ExcelModel.calculate() → XLSX with cached values → openpyxl → real values
```

### 3.3 Integration Points

1. **Preview extraction**: Evaluate before loading with `data_only=True`
2. **After cell edits**: Re-evaluate before saving new version
3. **Template population**: Evaluate after `XLSXPopulator.populate()`

---

## 4. Implementation Plan

### Phase 1: Add Formula Evaluation Service (Backend)

**New file**: `server/app/formula_evaluation.py`

```python
"""Excel formula evaluation using the formulas library."""

from __future__ import annotations

import io
import logging
from typing import Optional

logger = logging.getLogger("eagle.formula_evaluation")


def evaluate_workbook_formulas(xlsx_bytes: bytes) -> tuple[bytes, bool]:
    """
    Evaluate all formulas in an XLSX workbook and return with cached values.

    Args:
        xlsx_bytes: Raw XLSX file content

    Returns:
        Tuple of (processed_bytes, success_flag)
        If evaluation fails, returns original bytes with success=False
    """
    try:
        import formulas
    except ImportError:
        logger.warning("formulas library not installed, skipping evaluation")
        return xlsx_bytes, False

    try:
        # Load workbook into formulas engine
        xl_model = formulas.ExcelModel().loads(io.BytesIO(xlsx_bytes))

        # Calculate all formulas
        xl_model.calculate()

        # Save back to bytes with calculated values cached
        output = io.BytesIO()
        # The formulas library stores the workbook with key '[BOOK]' or similar
        for book in xl_model.books.values():
            book.save(output)
            break  # Single workbook expected

        output.seek(0)
        return output.getvalue(), True

    except Exception as exc:
        logger.warning("Formula evaluation failed: %s", exc, exc_info=True)
        return xlsx_bytes, False


def evaluate_workbook_formulas_safe(xlsx_bytes: bytes) -> bytes:
    """
    Evaluate formulas, returning original bytes on any failure.

    Use this wrapper when you want silent fallback behavior.
    """
    result, _ = evaluate_workbook_formulas(xlsx_bytes)
    return result
```

**Dependency**: Add to `server/requirements.txt`

```
formulas>=1.2.0
```

---

### Phase 2: Integrate Evaluation into Preview Extraction

**File**: `server/app/spreadsheet_edit_service.py`

**Changes**:

```python
# Add import at top
from .formula_evaluation import evaluate_workbook_formulas_safe

# Modify extract_xlsx_preview_payload function
def extract_xlsx_preview_payload(xlsx_bytes: bytes) -> dict[str, Any]:
    """Return text plus structured worksheets for browser preview/editing."""
    try:
        from openpyxl import load_workbook
    except ImportError:
        return {
            "content": "[XLSX preview unavailable - openpyxl not installed]",
            "preview_mode": "none",
            "preview_sheets": [],
        }

    # NEW: Evaluate formulas first so data_only=True gets real values
    evaluated_bytes = evaluate_workbook_formulas_safe(xlsx_bytes)

    wb = load_workbook(io.BytesIO(evaluated_bytes), data_only=False)
    wb_values = load_workbook(io.BytesIO(evaluated_bytes), data_only=True)
    # ... rest unchanged
```

**Also fix the fallback logic** (line 144):

```python
# Change from:
display_value = value_cell.value if value_cell.value is not None else raw_value

# To:
if value_cell.value is not None:
    display_value = value_cell.value
elif is_formula:
    # Formula with no cached value — show placeholder, not raw formula
    display_value = ""  # Or "[calc]" if you want visibility
else:
    display_value = raw_value
```

---

### Phase 3: Integrate Evaluation After Cell Edits

**File**: `server/app/spreadsheet_edit_service.py`

**Modify** `save_xlsx_preview_edits` function:

```python
def save_xlsx_preview_edits(
    *,
    tenant_id: str,
    user_id: Optional[str],
    doc_key: str,
    cell_edits: list[dict[str, Any]],
    session_id: Optional[str] = None,
    change_source: str = "user_edit",
) -> dict[str, Any]:
    # ... existing validation code ...

    try:
        updated_bytes, applied_count, missing = apply_xlsx_cell_edits(original_bytes, edits)
    except Exception as exc:
        logger.error("Failed to apply structured XLSX edits: %s", exc, exc_info=True)
        return {"error": f"Failed to apply spreadsheet edits: {exc}"}

    if applied_count == 0:
        return {"error": "No spreadsheet edits were applied.", "missing": missing}

    # NEW: Re-evaluate formulas after edits so totals update
    updated_bytes = evaluate_workbook_formulas_safe(updated_bytes)

    preview_payload = extract_xlsx_preview_payload(updated_bytes)
    # ... rest unchanged
```

---

### Phase 4: Integrate Evaluation into Template Population

**File**: `server/app/template_service.py`

**Modify** `XLSXPopulator.populate` to evaluate after population:

```python
# Add import
from .formula_evaluation import evaluate_workbook_formulas_safe

class XLSXPopulator:
    @staticmethod
    def populate(
        template_bytes: bytes,
        data: Dict[str, Any],
        placeholder_map: Dict[str, str],
    ) -> bytes:
        # ... existing population logic ...

        # Save to bytes
        output = io.BytesIO()
        wb.save(output)
        populated_bytes = output.getvalue()

        # NEW: Evaluate formulas so preview shows calculated values
        return evaluate_workbook_formulas_safe(populated_bytes)
```

---

### Phase 5: Frontend UX Improvements

**File**: `client/app/documents/[id]/page.tsx`

**Replace** the XLSX preview table (lines ~1778-1826) with improved version:

```tsx
{/* XLSX Preview Grid — Improved */}
<div className="space-y-3">
    {/* Sheet tabs */}
    <div className="flex flex-wrap gap-2">
        {displayedXlsxSheets.map((sheet) => (
            <button
                key={sheet.sheet_id}
                onClick={() => setActiveXlsxSheetId(sheet.sheet_id)}
                className={`rounded-lg px-3 py-1.5 text-sm font-medium transition ${
                    activeXlsxSheet?.sheet_id === sheet.sheet_id
                        ? 'bg-[#003366] text-white'
                        : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
            >
                {sheet.title}
            </button>
        ))}
    </div>

    {/* Truncation warning */}
    {activeXlsxSheet?.truncated && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
            Preview limited to {activeXlsxSheet.max_row} rows x {activeXlsxSheet.max_col} columns. Download for full view.
        </div>
    )}

    {/* Scrollable table container */}
    <div className="overflow-auto max-h-[500px] rounded-lg border border-gray-200 bg-white">
        <table className="min-w-full border-collapse text-sm">
            <thead className="bg-gray-100 sticky top-0 z-10">
                <tr>
                    <th className="border-b border-r border-gray-300 px-2 py-2 text-center font-semibold text-gray-500 w-10 text-xs">

                    </th>
                    {activeXlsxSheet?.rows[0]?.cells.map((cell) => (
                        <th
                            key={cell.cell_ref}
                            className="border-b border-r border-gray-300 px-2 py-2 text-center font-semibold text-gray-600 min-w-[70px] text-xs"
                        >
                            {cell.cell_ref.replace(/\d+/g, '')}
                        </th>
                    ))}
                </tr>
            </thead>
            <tbody>
                {activeXlsxSheet?.rows.map((row, rowIdx) => (
                    <tr key={row.row_index} className="group">
                        <td className="border-b border-r border-gray-200 bg-gray-50 px-2 py-1.5 text-center text-xs font-medium text-gray-400">
                            {row.row_index}
                        </td>
                        {row.cells.map((cell) => (
                            <td
                                key={cell.cell_ref}
                                className={`border-b border-r border-gray-200 px-1.5 py-1 ${
                                    cell.is_formula
                                        ? 'bg-sky-50'
                                        : cell.editable
                                            ? 'bg-white'
                                            : 'bg-gray-50'
                                }`}
                                title={cell.is_formula ? `Formula: ${cell.value}` : undefined}
                            >
                                {isEditing && cell.editable ? (
                                    <input
                                        type="text"
                                        value={cell.value}
                                        onChange={(e) => updateXlsxPreviewCell(
                                            activeXlsxSheet.sheet_id,
                                            cell.cell_ref,
                                            e.target.value
                                        )}
                                        className="w-full min-w-[60px] rounded border border-gray-300 px-1.5 py-1 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                                    />
                                ) : (
                                    <div
                                        className={`min-w-[60px] truncate text-sm ${
                                            cell.is_formula
                                                ? 'text-sky-700 font-medium'
                                                : cell.editable
                                                    ? 'text-gray-900'
                                                    : 'text-gray-500'
                                        }`}
                                    >
                                        {cell.display_value || (cell.is_formula ? '—' : '')}
                                    </div>
                                )}
                            </td>
                        ))}
                    </tr>
                ))}
            </tbody>
        </table>
    </div>

    {/* Legend */}
    <div className="flex flex-wrap gap-4 text-xs text-gray-500">
        <span className="flex items-center gap-1.5">
            <span className="inline-block w-3 h-3 bg-white border border-gray-300 rounded-sm" />
            Editable
        </span>
        <span className="flex items-center gap-1.5">
            <span className="inline-block w-3 h-3 bg-sky-50 border border-gray-300 rounded-sm" />
            Formula (auto-calculated)
        </span>
        <span className="flex items-center gap-1.5">
            <span className="inline-block w-3 h-3 bg-gray-50 border border-gray-300 rounded-sm" />
            Read-only
        </span>
    </div>
</div>
```

---

## 5. Testing Plan

### 5.1 Unit Tests

**New file**: `server/tests/test_formula_evaluation.py`

```python
"""Tests for Excel formula evaluation."""

import io
from openpyxl import Workbook

from app.formula_evaluation import evaluate_workbook_formulas


def _build_formula_xlsx() -> bytes:
    """Create test workbook with formulas."""
    wb = Workbook()
    ws = wb.active
    ws["A1"] = 10
    ws["B1"] = 20
    ws["C1"] = "=A1+B1"  # Should evaluate to 30
    ws["A2"] = 5
    ws["B2"] = "=A2*2"   # Should evaluate to 10
    ws["C2"] = "=SUM(A1:B2)"  # Should evaluate to 45
    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()


def test_evaluate_workbook_formulas_calculates_sum():
    """Formulas should be evaluated and cached."""
    xlsx_bytes = _build_formula_xlsx()
    result_bytes, success = evaluate_workbook_formulas(xlsx_bytes)

    assert success is True

    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(result_bytes), data_only=True)
    ws = wb.active

    assert ws["C1"].value == 30  # A1 + B1
    assert ws["B2"].value == 10  # A2 * 2
    assert ws["C2"].value == 45  # SUM(A1:B2)


def test_evaluate_workbook_preserves_formulas():
    """Original formulas should still exist after evaluation."""
    xlsx_bytes = _build_formula_xlsx()
    result_bytes, _ = evaluate_workbook_formulas(xlsx_bytes)

    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(result_bytes), data_only=False)
    ws = wb.active

    assert ws["C1"].value == "=A1+B1"
    assert ws["B2"].value == "=A2*2"


def test_evaluate_handles_invalid_xlsx():
    """Invalid XLSX should return original bytes with success=False."""
    invalid_bytes = b"not a valid xlsx"
    result_bytes, success = evaluate_workbook_formulas(invalid_bytes)

    assert success is False
    assert result_bytes == invalid_bytes
```

### 5.2 Integration Tests

**Add to**: `server/tests/test_spreadsheet_edit_service.py`

```python
def test_extract_preview_shows_calculated_values_not_formulas():
    """Formula cells should show calculated values, not =A1+B1."""
    xlsx_bytes = _build_formula_xlsx()  # Has =B2*C2 formula
    payload = extract_xlsx_preview_payload(xlsx_bytes)

    # Find the formula cell
    formula_cell = None
    for sheet in payload["preview_sheets"]:
        for row in sheet["rows"]:
            for cell in row["cells"]:
                if cell["is_formula"]:
                    formula_cell = cell
                    break

    assert formula_cell is not None
    # Should NOT start with "="
    assert not formula_cell["display_value"].startswith("=")


def test_save_edits_recalculates_formulas():
    """After editing input cells, formula results should update."""
    # Create workbook: A1=2, B1=3, C1=A1*B1 (=6)
    # Edit A1 to 5, C1 should become 15
    ...
```

### 5.3 Manual QA Checklist

| Scenario | Expected Result |
|----------|-----------------|
| Open IGCE template preview | All totals show numbers, not formulas |
| Edit quantity cell, save | Line total and grand total update |
| Hover formula cell | Tooltip shows formula like `=B2*C2` |
| Scroll large spreadsheet | Headers stay visible |
| View on mobile | Horizontal scroll works |

---

## 6. Rollout Plan

| Step | Task | Validation |
|------|------|------------|
| 1 | Add `formulas` to requirements.txt | `pip install -r requirements.txt` succeeds |
| 2 | Create `formula_evaluation.py` | Unit tests pass |
| 3 | Integrate into `spreadsheet_edit_service.py` | Existing tests still pass |
| 4 | Integrate into `template_service.py` | IGCE generation shows calculated values |
| 5 | Deploy backend to dev | Preview IGCE in browser — no formulas visible |
| 6 | Frontend UX changes | Visual review in browser |
| 7 | E2E test | Edit cell → save → verify totals updated |

---

## 7. Risks and Mitigations

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `formulas` library doesn't support some Excel function | Medium | Graceful fallback; log warning; show "[calc]" |
| Performance impact on large spreadsheets | Low | Evaluation is O(cells); add timeout if needed |
| Breaking change to preview API shape | Low | `display_value` field unchanged; only values differ |
| LibreOffice needed for complex workbooks | Low | Document limitation; offer "download and open in Excel" |

---

## 8. Files Changed

| File | Change Type | Description |
|------|-------------|-------------|
| `server/requirements.txt` | Modify | Add `formulas>=1.2.0` |
| `server/app/formula_evaluation.py` | Create | New evaluation service |
| `server/app/spreadsheet_edit_service.py` | Modify | Integrate evaluation |
| `server/app/template_service.py` | Modify | Evaluate after population |
| `server/tests/test_formula_evaluation.py` | Create | Unit tests |
| `server/tests/test_spreadsheet_edit_service.py` | Modify | Add integration tests |
| `client/app/documents/[id]/page.tsx` | Modify | Improved preview UI |

---

## 9. Definition of Done

- [ ] `formulas` library added to dependencies
- [ ] Formula evaluation service created with tests
- [ ] Preview extraction shows calculated values, not formula strings
- [ ] Cell edits trigger recalculation before save
- [ ] Template population includes formula evaluation
- [ ] Frontend shows visual distinction for formula cells
- [ ] Sticky headers work on scroll
- [ ] Legend explains cell types
- [ ] All existing tests pass
- [ ] Manual QA checklist completed

---

## 10. Commands

```bash
# Install new dependency
cd server && pip install formulas>=1.2.0

# Run backend tests
cd server && python -m pytest tests/test_formula_evaluation.py tests/test_spreadsheet_edit_service.py -v

# Type check frontend
cd client && npx tsc --noEmit

# Run full validation
ruff check server/app/ && cd client && npx tsc --noEmit && cd ../server && python -m pytest tests/ -v
```
