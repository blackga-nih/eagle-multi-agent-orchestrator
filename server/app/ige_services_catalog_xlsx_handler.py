"""Template-aware XLSX population for the services IGE workbook."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable


SERVICE_ROW_SLOTS = tuple(range(5, 14))
BASE_SHEET = "Base Period"
OPTION_ONE_SHEET = "Option Period One"


@dataclass(frozen=True)
class IGEServiceItem:
    description: str
    quantity: float | int | None
    unit_price: float | int | None
    total: float | int | None


class IGEServicesCatalogWorkbookMapper:
    """Populate the services-based-on-catalog-price workbook."""

    BASE_TITLE = "INDEPENDENT GOVERNMENT ESTIMATE (IGE) FOR SERVICES"
    OPTION_ONE_TITLE = "INDEPENDENT GOVERNMENT COST ESTIMATE (IGCE)"

    @classmethod
    def matches(cls, workbook) -> bool:
        required_sheets = {BASE_SHEET, OPTION_ONE_SHEET}
        if not required_sheets.issubset(set(workbook.sheetnames)):
            return False
        base = workbook[BASE_SHEET]
        option = workbook[OPTION_ONE_SHEET]
        return (
            str(base["A1"].value or "").strip().upper() == cls.BASE_TITLE
            and str(option["A1"].value or "").strip().upper() == cls.OPTION_ONE_TITLE
            and cls._normalized_formula(base["E5"].value) == "=SUM(C5*D5)"
            and cls._normalized_formula(option["E5"].value) == "=SUM(C5*D5)"
            and cls._normalized_formula(base["E16"].value) == "=E14"
            and cls._normalized_formula(option["E16"].value) == "=E14"
        )

    @classmethod
    def populate(cls, workbook, data: dict[str, Any]) -> bool:
        if not cls.matches(workbook):
            return False

        base_sheet = workbook[BASE_SHEET]
        option_sheet = workbook[OPTION_ONE_SHEET]
        cls._prepare_sheet(base_sheet)
        cls._prepare_sheet(option_sheet)

        base_items = cls._normalize_items(data.get("line_items"))
        option_items = cls._normalize_items(
            data.get("option_period_one_items") or data.get("option_items")
        )

        if not base_items:
            fallback = cls._build_total_estimate_fallback_item(data)
            if fallback:
                base_items = [fallback]

        cls._populate_sheet(base_sheet, base_items)
        cls._populate_sheet(option_sheet, option_items)
        cls._apply_workbook_metadata(workbook)
        return True

    @staticmethod
    def _normalized_formula(value: Any) -> str:
        if not isinstance(value, str):
            return ""
        return re.sub(r"\s+", "", value).upper()

    @classmethod
    def _prepare_sheet(cls, sheet) -> None:
        # The source template merges C:D in work rows while formulas reference both cells.
        # Generated workbooks normalize those rows so C and D can hold quantity and unit price.
        for row in [*SERVICE_ROW_SLOTS, 14]:
            merged_ref = f"C{row}:D{row}"
            if any(str(rng) == merged_ref for rng in sheet.merged_cells.ranges):
                sheet.unmerge_cells(merged_ref)
        if sheet["E14"].value in (None, ""):
            sheet["E14"] = "=SUM(E5:E13)"
        cls._clear_sheet(sheet)

    @classmethod
    def _populate_sheet(cls, sheet, items: list[IGEServiceItem]) -> None:
        assignments = cls._assign_rows(items)
        for row, item in assignments:
            sheet[f"A{row}"] = item.description
            sheet[f"C{row}"] = item.quantity if item.quantity is not None else 1
            sheet[f"D{row}"] = item.unit_price if item.unit_price is not None else 0

    @staticmethod
    def _clear_sheet(sheet) -> None:
        for row in SERVICE_ROW_SLOTS:
            sheet[f"A{row}"] = None
            sheet[f"C{row}"] = None
            sheet[f"D{row}"] = None

    @classmethod
    def _normalize_items(cls, raw_items: Any) -> list[IGEServiceItem]:
        if not isinstance(raw_items, list):
            return []

        items: list[IGEServiceItem] = []
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue
            description = (
                raw_item.get("description")
                or raw_item.get("service")
                or raw_item.get("name")
                or raw_item.get("title")
                or ""
            )
            quantity = cls._coerce_number(
                raw_item.get("quantity")
                or raw_item.get("qty")
                or raw_item.get("period")
                or raw_item.get("months")
                or raw_item.get("hours")
            )
            unit_price = cls._coerce_number(
                raw_item.get("unit_price")
                or raw_item.get("price")
                or raw_item.get("rate")
                or raw_item.get("catalog_price")
                or raw_item.get("monthly_rate")
            )
            total = cls._coerce_number(
                raw_item.get("total") or raw_item.get("amount") or raw_item.get("estimated_amount")
            )
            if total is None and quantity is not None and unit_price is not None:
                total = quantity * unit_price
            items.append(
                IGEServiceItem(
                    description=str(description).strip(),
                    quantity=quantity,
                    unit_price=unit_price,
                    total=total,
                )
            )
        return items

    @classmethod
    def _build_total_estimate_fallback_item(
        cls, data: dict[str, Any]
    ) -> IGEServiceItem | None:
        total = cls._coerce_number(data.get("total_estimate"))
        if total is None:
            return None
        description = data.get("description") or data.get("title") or "Estimated Total"
        return IGEServiceItem(
            description=str(description).strip(),
            quantity=1,
            unit_price=total,
            total=total,
        )

    @staticmethod
    def _coerce_number(value: Any) -> float | int | None:
        if value in (None, ""):
            return None
        if isinstance(value, (int, float)):
            return value
        text = str(value).strip()
        if not text:
            return None
        cleaned = text.replace("$", "").replace(",", "").replace("%", "").strip()
        try:
            number = float(cleaned)
        except ValueError:
            return None
        if number.is_integer():
            return int(number)
        return number

    @classmethod
    def _assign_rows(cls, items: list[IGEServiceItem]) -> list[tuple[int, IGEServiceItem]]:
        if len(items) <= len(SERVICE_ROW_SLOTS):
            return list(zip(SERVICE_ROW_SLOTS, items))
        kept = list(items[: len(SERVICE_ROW_SLOTS) - 1])
        overflow = items[len(SERVICE_ROW_SLOTS) - 1 :]
        kept.append(cls._aggregate_items(overflow))
        return list(zip(SERVICE_ROW_SLOTS, kept))

    @classmethod
    def _aggregate_items(cls, items: Iterable[IGEServiceItem]) -> IGEServiceItem:
        items = list(items)
        quantity_total = sum(
            item.quantity for item in items if isinstance(item.quantity, (int, float))
        )
        total_cost = sum(
            item.total for item in items if isinstance(item.total, (int, float))
        )
        quantity = quantity_total if quantity_total else 1
        unit_price = total_cost / quantity if quantity else total_cost
        return IGEServiceItem(
            description=f"Additional services ({len(items)})",
            quantity=quantity,
            unit_price=unit_price,
            total=total_cost,
        )

    @staticmethod
    def _apply_workbook_metadata(workbook) -> None:
        calculation = getattr(workbook, "calculation", None)
        if calculation is not None:
            if hasattr(calculation, "calcMode"):
                calculation.calcMode = "auto"
            if hasattr(calculation, "fullCalcOnLoad"):
                calculation.fullCalcOnLoad = True
            if hasattr(calculation, "forceFullCalc"):
                calculation.forceFullCalc = True
