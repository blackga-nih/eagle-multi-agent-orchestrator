"""Excel formula evaluation using the formulas library.

This module provides formula evaluation for XLSX files so that:
1. Preview extraction shows calculated values instead of formula strings
2. After cell edits, totals and dependent cells recalculate
3. Template population produces files with cached formula results
"""

from __future__ import annotations

import io
import logging
import tempfile
import os
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

    tmp_path = None
    try:
        from openpyxl import load_workbook
        import numpy as np

        # formulas.ExcelModel requires a file path, not BytesIO
        fd, tmp_path = tempfile.mkstemp(suffix=".xlsx")
        os.write(fd, xlsx_bytes)
        os.close(fd)

        # Load workbook into formulas engine and calculate
        logger.info("Loading workbook into formulas engine: %s", tmp_path)
        xl_model = formulas.ExcelModel().loads(tmp_path).finish()
        logger.info("Calculating formulas...")
        solution = xl_model.calculate()
        logger.info("Formula calculation complete, %d results", len(solution))

        # Build a lookup from UPPER sheet name -> actual openpyxl sheet name
        wb = load_workbook(tmp_path)
        sheet_lookup = {name.upper(): name for name in wb.sheetnames}

        # Write calculated values into the openpyxl workbook
        for ref, value in solution.items():
            # ref looks like "'[tmp.xlsx]CALCULATIONS'!C1"
            try:
                sheet_part, cell_ref = str(ref).rsplit("!", 1)
                # Strip quotes and book name
                sheet_name = sheet_part.strip("'")
                if "]" in sheet_name:
                    sheet_name = sheet_name.split("]", 1)[1]

                actual_name = sheet_lookup.get(sheet_name.upper())
                if not actual_name:
                    continue

                # Extract scalar from Ranges object
                val = value.value[0, 0] if hasattr(value, "value") else value
                # Convert numpy types to native Python
                if isinstance(val, (np.integer,)):
                    val = int(val)
                elif isinstance(val, (np.floating,)):
                    val = float(val)
                elif isinstance(val, np.ndarray):
                    val = val.item()

                cell = wb[actual_name][cell_ref.upper()]
                # Only overwrite formula cells with their computed value
                if isinstance(cell.value, str) and cell.value.startswith("="):
                    cell.value = val
            except Exception:
                continue  # skip unparseable refs

        output = io.BytesIO()
        wb.save(output)
        result_bytes = output.getvalue()

        # Validate we got valid output
        if len(result_bytes) == 0:
            logger.warning("Formula evaluation produced empty output")
            return xlsx_bytes, False

        return result_bytes, True

    except Exception as exc:
        logger.warning("Formula evaluation failed: %s", exc, exc_info=False)
        # Log more details for debugging
        logger.debug("Formula evaluation exception details:", exc_info=True)
        return xlsx_bytes, False
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


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
