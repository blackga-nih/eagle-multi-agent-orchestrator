"""Excel formula evaluation using the formulas library.

This module provides formula evaluation for XLSX files so that:
1. Preview extraction shows calculated values instead of formula strings
2. After cell edits, totals and dependent cells recalculate
3. Template population produces files with cached formula results
"""

from __future__ import annotations

import io
import logging
from typing import Tuple

logger = logging.getLogger("eagle.formula_evaluation")


def evaluate_workbook_formulas(xlsx_bytes: bytes) -> Tuple[bytes, bool]:
    """
    Evaluate all formulas in an XLSX workbook and return with cached values.

    Uses the `formulas` library to calculate Excel formulas and write the
    results back as cached values. This ensures openpyxl's data_only=True
    mode returns actual numbers instead of None.

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

        # The formulas library stores workbooks; get the first one
        for book in xl_model.books.values():
            book.save(output)
            break  # Single workbook expected

        output.seek(0)
        result_bytes = output.getvalue()

        # Validate we got valid output
        if len(result_bytes) == 0:
            logger.warning("Formula evaluation produced empty output")
            return xlsx_bytes, False

        return result_bytes, True

    except Exception as exc:
        logger.warning("Formula evaluation failed: %s", exc, exc_info=True)
        return xlsx_bytes, False


def evaluate_workbook_formulas_safe(xlsx_bytes: bytes) -> bytes:
    """
    Evaluate formulas, returning original bytes on any failure.

    Use this wrapper when you want silent fallback behavior without
    needing to check the success flag.

    Args:
        xlsx_bytes: Raw XLSX file content

    Returns:
        Processed bytes with cached formula values, or original bytes on failure
    """
    result, _ = evaluate_workbook_formulas(xlsx_bytes)
    return result
