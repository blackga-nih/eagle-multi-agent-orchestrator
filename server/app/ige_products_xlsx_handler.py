"""Template-aware XLSX population for the products IGE workbook."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable


PRODUCT_ROW_SLOTS = (5, 6, 7, 8, 9, 13)
SPECIAL_ROWS = {
    "shipping": 10,
    "installation": 11,
    "training": 12,
}
_SPECIAL_KEYWORDS = {
    "shipping": ("shipping", "freight", "delivery"),
    "installation": ("installation", "install", "setup"),
    "training": ("training", "train"),
}


@dataclass(frozen=True)
class IGEProductItem:
    description: str
    quantity: float | int | None
    unit_price: float | int | None
    total: float | int | None
    manufacturer: str = ""
    part_number: str = ""


class IGEProductsWorkbookMapper:
    """Populate the products IGE workbook by explicit cell mapping."""

    TEMPLATE_TITLE = "INDEPENDENT GOVERNMENT ESTIMATE (IGE) FOR PRODUCTS"

    @classmethod
    def matches(cls, workbook) -> bool:
        if "Sheet1" not in workbook.sheetnames:
            return False
        sheet = workbook["Sheet1"]
        title = str(sheet["A1"].value or "").strip().upper()
        return (
            title == cls.TEMPLATE_TITLE
            and cls._normalized_formula(sheet["E5"].value) == "=SUM(C5*D5)"
            and cls._normalized_formula(sheet["E14"].value) == "=SUM(E5:E13)"
            and cls._normalized_formula(sheet["E16"].value) == "=E14"
        )

    @classmethod
    def populate(cls, workbook, data: dict[str, Any]) -> bool:
        if not cls.matches(workbook):
            return False

        sheet = workbook["Sheet1"]
        items = cls._normalize_items(data)
        row_assignments = cls._assign_rows(items)
        cls._clear_rows(sheet)

        item_number = 1
        for row, item in row_assignments:
            if row not in SPECIAL_ROWS.values():
                sheet[f"A{row}"] = item_number
                item_number += 1
            sheet[f"B{row}"] = cls._row_description(row, item)
            sheet[f"C{row}"] = item.quantity if item.quantity is not None else 1
            sheet[f"D{row}"] = item.unit_price if item.unit_price is not None else 0
            if row == SPECIAL_ROWS["training"]:
                # Template omits the row formula, so write the literal total.
                total = item.total
                if total is None and item.quantity is not None and item.unit_price is not None:
                    total = item.quantity * item.unit_price
                sheet["E12"] = total if total is not None else 0

        cls._apply_workbook_metadata(workbook)
        return True

    @staticmethod
    def _normalized_formula(value: Any) -> str:
        if not isinstance(value, str):
            return ""
        return re.sub(r"\s+", "", value).upper()

    @classmethod
    def _normalize_items(cls, data: dict[str, Any]) -> list[IGEProductItem]:
        candidates: list[dict[str, Any]] = []
        line_items = data.get("line_items")
        if isinstance(line_items, list):
            candidates.extend(item for item in line_items if isinstance(item, dict))
        goods_items = data.get("goods_items")
        if isinstance(goods_items, list):
            candidates.extend(item for item in goods_items if isinstance(item, dict))

        if not candidates:
            fallback = cls._build_total_estimate_fallback_item(data)
            return [fallback] if fallback else []

        items: list[IGEProductItem] = []
        for raw in candidates:
            description = (
                raw.get("description")
                or raw.get("product_name")
                or raw.get("name")
                or raw.get("title")
                or ""
            )
            quantity = cls._coerce_number(raw.get("quantity") or raw.get("qty"))
            unit_price = cls._coerce_number(
                raw.get("unit_price")
                or raw.get("price")
                or raw.get("unit_cost")
                or raw.get("catalog_price")
            )
            total = cls._coerce_number(
                raw.get("total") or raw.get("amount") or raw.get("extended_price")
            )
            if total is None and quantity is not None and unit_price is not None:
                total = quantity * unit_price

            manufacturer = str(raw.get("manufacturer") or "").strip()
            part_number = str(
                raw.get("manufacturer_number")
                or raw.get("part_number")
                or raw.get("sku")
                or ""
            ).strip()
            items.append(
                IGEProductItem(
                    description=str(description).strip(),
                    quantity=quantity,
                    unit_price=unit_price,
                    total=total,
                    manufacturer=manufacturer,
                    part_number=part_number,
                )
            )
        return items

    @classmethod
    def _build_total_estimate_fallback_item(
        cls, data: dict[str, Any]
    ) -> IGEProductItem | None:
        total = cls._coerce_number(data.get("total_estimate"))
        if total is None:
            return None
        description = data.get("description") or data.get("title") or "Estimated Total"
        return IGEProductItem(
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
    def _assign_rows(cls, items: list[IGEProductItem]) -> list[tuple[int, IGEProductItem]]:
        assignments: list[tuple[int, IGEProductItem]] = []
        general_rows = list(PRODUCT_ROW_SLOTS)
        overflow: list[IGEProductItem] = []

        for item in items:
            special_row = cls._special_row_for_item(item)
            if special_row is not None:
                assignments.append((special_row, item))
                continue
            if general_rows:
                assignments.append((general_rows.pop(0), item))
            else:
                overflow.append(item)

        if overflow:
            row = PRODUCT_ROW_SLOTS[-1]
            assignments = [entry for entry in assignments if entry[0] != row]
            assignments.append((row, cls._aggregate_items(overflow)))
        return sorted(assignments, key=lambda entry: entry[0])

    @classmethod
    def _special_row_for_item(cls, item: IGEProductItem) -> int | None:
        description = item.description.lower()
        for name, keywords in _SPECIAL_KEYWORDS.items():
            if any(keyword in description for keyword in keywords):
                return SPECIAL_ROWS[name]
        return None

    @classmethod
    def _aggregate_items(cls, items: Iterable[IGEProductItem]) -> IGEProductItem:
        items = list(items)
        quantity_total = sum(
            item.quantity for item in items if isinstance(item.quantity, (int, float))
        )
        total_cost = sum(
            item.total for item in items if isinstance(item.total, (int, float))
        )
        quantity = quantity_total if quantity_total else 1
        unit_price = total_cost / quantity if quantity else total_cost
        return IGEProductItem(
            description=f"Additional items ({len(items)})",
            quantity=quantity,
            unit_price=unit_price,
            total=total_cost,
        )

    @staticmethod
    def _row_description(row: int, item: IGEProductItem) -> str:
        base = item.description
        details = [value for value in (item.manufacturer, item.part_number) if value]
        if row == SPECIAL_ROWS["shipping"]:
            return "Shipping (include as needed)"
        if row == SPECIAL_ROWS["installation"]:
            return "Installation (include as needed)"
        if row == SPECIAL_ROWS["training"]:
            return "Training (include as needed)"
        if details:
            return " / ".join([base, *details]) if base else " / ".join(details)
        return base

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

    @staticmethod
    def _clear_rows(sheet) -> None:
        for row in range(5, 14):
            for col in ("A", "B", "C", "D"):
                if row in (10, 11, 12) and col == "B":
                    continue
                sheet[f"{col}{row}"] = None
        sheet["E12"] = None
