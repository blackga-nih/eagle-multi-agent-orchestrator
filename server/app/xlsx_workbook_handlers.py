"""Registry for workbook-specific XLSX handlers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Callable, Protocol

from .ige_services_catalog_xlsx_handler import IGEServicesCatalogWorkbookMapper
from .igce_xlsx_mapper import CommercialIGCEWorkbookMapper
from .ige_products_xlsx_handler import IGEProductsWorkbookMapper


class XLSXWorkbookMapper(Protocol):
    @classmethod
    def matches(cls, workbook) -> bool: ...

    @classmethod
    def populate(cls, workbook, data: dict[str, Any]) -> bool: ...


@dataclass(frozen=True)
class RegisteredXLSXHandler:
    handler_id: str
    template_filenames: tuple[str, ...]
    mapper: type[XLSXWorkbookMapper]
    preview_matcher: Callable[[list[dict[str, Any]]], bool] | None = None

    def matches_workbook(self, workbook) -> bool:
        return self.mapper.matches(workbook)

    def populate(self, workbook, data: dict[str, Any]) -> bool:
        return self.mapper.populate(workbook, data)


def _preview_sheet(preview_sheets: list[dict[str, Any]], title: str) -> dict[str, Any] | None:
    for sheet in preview_sheets:
        if str(sheet.get("title", "")).strip().lower() == title.lower():
            return sheet
    return None


def _preview_cell_text(
    preview_sheets: list[dict[str, Any]], title: str, cell_ref: str
) -> str:
    sheet = _preview_sheet(preview_sheets, title)
    if not sheet:
        return ""
    for row in sheet.get("rows", []):
        for cell in row.get("cells", []):
            if str(cell.get("cell_ref", "")).upper() == cell_ref.upper():
                return str(cell.get("display_value") or cell.get("value") or "")
    return ""


COMMERCIAL_IGCE_HANDLER = RegisteredXLSXHandler(
    handler_id="commercial_igce",
    template_filenames=("01.D_IGCE_for_Commercial_Organizations.xlsx",),
    mapper=CommercialIGCEWorkbookMapper,
    preview_matcher=lambda preview_sheets: {
        str(sheet.get("title", "")).strip().lower() for sheet in preview_sheets
    } >= {"igce", "it services", "it goods"},
)

IGE_PRODUCTS_HANDLER = RegisteredXLSXHandler(
    handler_id="ige_products",
    template_filenames=("4.a. IGE for Products.xlsx",),
    mapper=IGEProductsWorkbookMapper,
    preview_matcher=lambda preview_sheets: (
        bool(_preview_sheet(preview_sheets, "Sheet1"))
        and _preview_cell_text(preview_sheets, "Sheet1", "A1").strip().upper()
        == IGEProductsWorkbookMapper.TEMPLATE_TITLE
    ),
)

IGE_SERVICES_CATALOG_HANDLER = RegisteredXLSXHandler(
    handler_id="ige_services_catalog",
    template_filenames=("4.b. IGE for Services based on Catalog Price.xlsx",),
    mapper=IGEServicesCatalogWorkbookMapper,
    preview_matcher=lambda preview_sheets: (
        bool(_preview_sheet(preview_sheets, "Base Period"))
        and bool(_preview_sheet(preview_sheets, "Option Period One"))
    ),
)

REGISTERED_XLSX_HANDLERS: tuple[RegisteredXLSXHandler, ...] = (
    COMMERCIAL_IGCE_HANDLER,
    IGE_PRODUCTS_HANDLER,
    IGE_SERVICES_CATALOG_HANDLER,
)


def detect_xlsx_handler_for_workbook(workbook) -> RegisteredXLSXHandler | None:
    for handler in REGISTERED_XLSX_HANDLERS:
        if handler.matches_workbook(workbook):
            return handler
    return None


def detect_xlsx_handler_for_template_id(
    template_id: str | None,
) -> RegisteredXLSXHandler | None:
    if not template_id:
        return None
    filename = PurePosixPath(str(template_id)).name
    for handler in REGISTERED_XLSX_HANDLERS:
        if filename in handler.template_filenames:
            return handler
    return None


def detect_xlsx_handler_for_preview(
    preview_sheets: list[dict[str, Any]],
) -> RegisteredXLSXHandler | None:
    for handler in REGISTERED_XLSX_HANDLERS:
        if handler.preview_matcher and handler.preview_matcher(preview_sheets):
            return handler
    return None


def populate_supported_xlsx_workbook(workbook, data: dict[str, Any]) -> bool:
    handler = detect_xlsx_handler_for_workbook(workbook)
    if not handler:
        return False
    return handler.populate(workbook, data)
