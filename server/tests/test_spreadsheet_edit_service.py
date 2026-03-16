"""Tests for XLSX preview and structured editing helpers."""

import io
import os
import sys
from unittest.mock import MagicMock, patch

_server_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)

from app.spreadsheet_edit_service import (
    SpreadsheetCellEdit,
    apply_xlsx_cell_edits,
    extract_xlsx_preview_payload,
    save_xlsx_preview_edits,
)


def _build_sample_xlsx() -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "IGCE"
    ws["A1"] = "Item"
    ws["B1"] = "Qty"
    ws["C1"] = "Price"
    ws["D1"] = "Total"
    ws["A2"] = "Microscope"
    ws["B2"] = 2
    ws["C2"] = 1500
    ws["D2"] = "=B2*C2"
    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()


def test_extract_xlsx_preview_payload_returns_structured_sheets():
    payload = extract_xlsx_preview_payload(_build_sample_xlsx())

    assert payload["preview_mode"] == "xlsx_grid"
    assert "IGCE" in payload["content"]
    assert payload["preview_sheets"]
    first_sheet = payload["preview_sheets"][0]
    first_row = first_sheet["rows"][0]
    assert first_sheet["title"] == "IGCE"
    assert any(cell["cell_ref"] == "A1" and cell["display_value"] == "Item" for cell in first_row["cells"])


def test_apply_xlsx_cell_edits_updates_only_input_cells():
    updated_bytes, applied_count, missing = apply_xlsx_cell_edits(
        _build_sample_xlsx(),
        [
            SpreadsheetCellEdit(sheet_id="0:igce", cell_ref="A2", value="Updated microscope"),
            SpreadsheetCellEdit(sheet_id="0:igce", cell_ref="D2", value="9999"),
        ],
    )

    assert applied_count == 1
    assert missing == ["0:igce:D2"]

    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(updated_bytes), data_only=False)
    ws = wb["IGCE"]
    assert ws["A2"].value == "Updated microscope"
    assert ws["D2"].value == "=B2*C2"


def test_save_xlsx_preview_edits_versions_package_doc():
    xlsx_bytes = _build_sample_xlsx()
    s3 = MagicMock()
    s3.get_object.return_value = {"Body": io.BytesIO(xlsx_bytes)}

    with patch("app.spreadsheet_edit_service._get_s3", return_value=s3), patch(
        "app.spreadsheet_edit_service.get_document",
        return_value={"title": "IGCE", "template_id": "tmpl-xlsx"},
    ), patch(
        "app.spreadsheet_edit_service.create_package_document_version",
        return_value=MagicMock(success=True, document_id="doc-xlsx-2", s3_key="eagle/dev-tenant/packages/PKG-1/igce/v2/IGCE.xlsx", version=2),
    ) as create_mock:
        result = save_xlsx_preview_edits(
            tenant_id="dev-tenant",
            user_id="dev-user",
            doc_key="eagle/dev-tenant/packages/PKG-1/igce/v1/source.xlsx",
            cell_edits=[{"sheet_id": "0:igce", "cell_ref": "A2", "value": "Updated microscope"}],
            session_id="session-xlsx",
            change_source="user_edit",
        )

    assert result["success"] is True
    assert result["version"] == 2
    assert result["file_type"] == "xlsx"
    assert result["preview_mode"] == "xlsx_grid"

    saved_bytes = create_mock.call_args.kwargs["content"]
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(saved_bytes))
    assert wb["IGCE"]["A2"].value == "Updated microscope"
    assert create_mock.call_args.kwargs["file_type"] == "xlsx"
