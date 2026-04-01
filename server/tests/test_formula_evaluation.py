"""Tests for Excel formula evaluation."""

import io
import os
import sys

# Add server directory to path for imports
_server_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)

from openpyxl import Workbook

from app.formula_evaluation import (
    evaluate_formulas_for_preview,
    evaluate_workbook_formulas,
    evaluate_workbook_formulas_safe,
)


def _build_formula_xlsx() -> bytes:
    """Create test workbook with various formulas."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Calculations"

    # Simple values
    ws["A1"] = 10
    ws["B1"] = 20
    ws["C1"] = "=A1+B1"  # Should evaluate to 30

    ws["A2"] = 5
    ws["B2"] = "=A2*2"  # Should evaluate to 10
    ws["C2"] = "=SUM(A1:B2)"  # Should evaluate to 45 (10+20+5+10)

    # More complex formulas
    ws["A3"] = 100
    ws["B3"] = 0.15
    ws["C3"] = "=A3*B3"  # Should evaluate to 15

    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()


def _build_simple_xlsx() -> bytes:
    """Create test workbook without formulas."""
    wb = Workbook()
    ws = wb.active
    ws["A1"] = "Name"
    ws["B1"] = "Value"
    ws["A2"] = "Item 1"
    ws["B2"] = 100

    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()


class TestEvaluateWorkbookFormulas:
    """Tests for evaluate_workbook_formulas function."""

    def test_preserves_formulas(self):
        """evaluate_workbook_formulas should keep formulas intact."""
        xlsx_bytes = _build_formula_xlsx()
        result_bytes, success = evaluate_workbook_formulas(xlsx_bytes)

        assert success is True

        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(result_bytes), data_only=False)
        ws = wb.active

        # Formulas must be preserved (not replaced with values)
        assert ws["C1"].value == "=A1+B1"
        assert ws["B2"].value == "=A2*2"
        assert ws["C2"].value == "=SUM(A1:B2)"

    def test_sets_full_calc_on_load(self):
        """Workbook should have fullCalcOnLoad so Excel recalculates."""
        xlsx_bytes = _build_formula_xlsx()
        result_bytes, success = evaluate_workbook_formulas(xlsx_bytes)

        assert success is True

        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(result_bytes))
        assert wb.calculation is not None
        assert wb.calculation.fullCalcOnLoad is True

    def test_handles_workbook_without_formulas(self):
        """Workbooks without formulas should pass through unchanged."""
        xlsx_bytes = _build_simple_xlsx()
        result_bytes, success = evaluate_workbook_formulas(xlsx_bytes)

        assert success is True

        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(result_bytes), data_only=True)
        ws = wb.active

        assert ws["A1"].value == "Name"
        assert ws["B2"].value == 100

    def test_handles_invalid_xlsx(self):
        """Invalid XLSX should return original bytes with success=False."""
        invalid_bytes = b"not a valid xlsx file"
        result_bytes, success = evaluate_workbook_formulas(invalid_bytes)

        assert success is False
        assert result_bytes == invalid_bytes

    def test_handles_empty_bytes(self):
        """Empty bytes should return original with success=False."""
        empty_bytes = b""
        result_bytes, success = evaluate_workbook_formulas(empty_bytes)

        assert success is False
        assert result_bytes == empty_bytes


class TestEvaluateFormulasForPreview:
    """Tests for evaluate_formulas_for_preview (value-only for previews)."""

    def test_flattens_simple_addition(self):
        """Preview version should replace =A1+B1 with 30."""
        xlsx_bytes = _build_formula_xlsx()
        result_bytes = evaluate_formulas_for_preview(xlsx_bytes)

        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(result_bytes), data_only=False)
        ws = wb.active

        assert ws["C1"].value == 30
        assert ws["B2"].value == 10
        assert ws["C2"].value == 45

    def test_flattens_multiplication(self):
        """Preview: =A2*2 should become 10."""
        xlsx_bytes = _build_formula_xlsx()
        result_bytes = evaluate_formulas_for_preview(xlsx_bytes)

        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(result_bytes), data_only=True)
        ws = wb.active
        assert ws["B2"].value == 10

    def test_flattens_sum_function(self):
        """Preview: =SUM(A1:B2) should become 45."""
        xlsx_bytes = _build_formula_xlsx()
        result_bytes = evaluate_formulas_for_preview(xlsx_bytes)

        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(result_bytes), data_only=True)
        ws = wb.active
        assert ws["C2"].value == 45


class TestEvaluateWorkbookFormulasSafe:
    """Tests for the safe wrapper function."""

    def test_returns_formula_preserving_bytes(self):
        """Should return bytes with formulas intact."""
        xlsx_bytes = _build_formula_xlsx()
        result_bytes = evaluate_workbook_formulas_safe(xlsx_bytes)

        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(result_bytes), data_only=False)
        ws = wb.active

        # Formulas preserved
        assert ws["C1"].value == "=A1+B1"

    def test_returns_original_bytes_on_failure(self):
        """Should return original bytes on failure without raising."""
        invalid_bytes = b"invalid xlsx"
        result_bytes = evaluate_workbook_formulas_safe(invalid_bytes)

        # Should return original, not raise
        assert result_bytes == invalid_bytes


class TestIGCEStyleFormulas:
    """Tests simulating IGCE spreadsheet patterns."""

    def _build_igce_xlsx(self) -> bytes:
        wb = Workbook()
        ws = wb.active
        ws.title = "IGCE"

        ws["A1"] = "Item"
        ws["B1"] = "Qty"
        ws["C1"] = "Unit Price"
        ws["D1"] = "Total"

        ws["A2"] = "Microscope"
        ws["B2"] = 2
        ws["C2"] = 1500
        ws["D2"] = "=B2*C2"

        ws["A3"] = "Centrifuge"
        ws["B3"] = 1
        ws["C3"] = 5000
        ws["D3"] = "=B3*C3"

        ws["D4"] = "=SUM(D2:D3)"

        output = io.BytesIO()
        wb.save(output)
        return output.getvalue()

    def test_formulas_preserved_in_output(self):
        """evaluate_workbook_formulas should keep IGCE formulas live."""
        xlsx_bytes = self._build_igce_xlsx()
        result_bytes, success = evaluate_workbook_formulas(xlsx_bytes)
        assert success is True

        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(result_bytes), data_only=False)
        ws = wb.active

        assert ws["D2"].value == "=B2*C2"
        assert ws["D3"].value == "=B3*C3"
        assert ws["D4"].value == "=SUM(D2:D3)"

    def test_preview_flattens_line_item_totals(self):
        """evaluate_formulas_for_preview should compute IGCE totals."""
        xlsx_bytes = self._build_igce_xlsx()
        result_bytes = evaluate_formulas_for_preview(xlsx_bytes)

        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(result_bytes), data_only=True)
        ws = wb.active

        assert ws["D2"].value == 3000
        assert ws["D3"].value == 5000
        assert ws["D4"].value == 8000
