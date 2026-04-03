"""Template-aware XLSX population for the commercial IGCE workbook."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable, List, Sequence


SUMMARY_LABOR_ROWS: Sequence[int] = (7, 8, 9, 11, 12, 13, 16, 17, 18, 21, 22, 23)
SUMMARY_ODC_ROWS: Sequence[int] = (30, 31, 32, 33, 34, 35, 36, 37)
IT_SERVICES_ROWS: Sequence[int] = (12, 13, 14, 15, 16, 17, 18)
IT_GOODS_ROWS: Sequence[int] = (10, 11, 12, 13, 14, 15, 16, 17)

_LABOR_UNITS = {"HR", "HOUR", "HOURS", "FTE", "DAY", "DAYS", "WK", "WEEK", "WEEKS"}
_LABOR_KEYWORDS = (
    "architect",
    "analyst",
    "consultant",
    "controller",
    "coordinator",
    "developer",
    "engineer",
    "manager",
    "programmer",
    "project",
    "scientist",
    "specialist",
    "support",
    "technical",
)


@dataclass(frozen=True)
class IGCEWorkbookItem:
    """Normalized line item used by the commercial IGCE mapper."""

    description: str
    quantity: float | int | None
    unit: str
    unit_price: float | int | None
    total: float | int | None
    manufacturer: str = ""
    manufacturer_number: str = ""
    brand_name_only: str = ""


class CommercialIGCEWorkbookMapper:
    """Populate the official commercial IGCE workbook by cell coordinates."""

    @classmethod
    def matches(cls, workbook) -> bool:
        """Return True when the workbook matches the commercial IGCE layout."""
        required_sheets = {"IGCE", "IT Services", "IT Goods"}
        if not required_sheets.issubset(set(workbook.sheetnames)):
            return False

        return (
            cls._normalized_formula(workbook["IGCE"]["G7"].value) == "=C7*E7"
            and cls._normalized_formula(workbook["IT Services"]["D12"].value)
            == "=B12*C12"
            and cls._normalized_formula(workbook["IT Goods"]["G10"].value)
            == "=F10*E10"
        )

    @classmethod
    def populate(cls, workbook, data: dict[str, Any]) -> bool:
        """Populate workbook in place and return True when the mapper applies."""
        if not cls.matches(workbook):
            return False

        items = cls._normalize_items(data.get("line_items"))
        service_items = [item for item in items if cls._is_service_item(item)]
        goods_items = [item for item in items if not cls._is_service_item(item)]

        if not items:
            fallback_item = cls._build_total_estimate_fallback_item(data)
            if fallback_item is not None:
                goods_items = [fallback_item]

        summary_sheet = workbook["IGCE"]
        services_sheet = workbook["IT Services"]
        goods_sheet = workbook["IT Goods"]

        cls._populate_summary_sheet(summary_sheet, service_items, goods_items)
        cls._populate_it_services_sheet(services_sheet, service_items, data)
        cls._populate_it_goods_sheet(goods_sheet, goods_items, data)
        cls._apply_workbook_metadata(workbook, data)
        return True

    @staticmethod
    def _normalized_formula(value: Any) -> str:
        if not isinstance(value, str):
            return ""
        return re.sub(r"\s+", "", value).upper()

    @staticmethod
    def _normalize_items(raw_items: Any) -> List[IGCEWorkbookItem]:
        if not isinstance(raw_items, list):
            return []

        items: List[IGCEWorkbookItem] = []
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue

            description = (
                raw_item.get("description")
                or raw_item.get("name")
                or raw_item.get("title")
                or ""
            )
            quantity = CommercialIGCEWorkbookMapper._coerce_number(
                raw_item.get("quantity") or raw_item.get("qty") or raw_item.get("hours")
            )
            unit_price = CommercialIGCEWorkbookMapper._coerce_number(
                raw_item.get("unit_price")
                or raw_item.get("price")
                or raw_item.get("rate")
                or raw_item.get("hourly_rate")
            )
            total = CommercialIGCEWorkbookMapper._coerce_number(
                raw_item.get("total")
                or raw_item.get("amount")
                or raw_item.get("extended_price")
            )
            if total is None and quantity is not None and unit_price is not None:
                total = quantity * unit_price

            items.append(
                IGCEWorkbookItem(
                    description=str(description).strip(),
                    quantity=quantity,
                    unit=str(raw_item.get("unit") or raw_item.get("uom") or "EA").strip(),
                    unit_price=unit_price,
                    total=total,
                    manufacturer=str(raw_item.get("manufacturer") or "").strip(),
                    manufacturer_number=str(
                        raw_item.get("manufacturer_number")
                        or raw_item.get("part_number")
                        or raw_item.get("sku")
                        or ""
                    ).strip(),
                    brand_name_only=CommercialIGCEWorkbookMapper._normalize_brand_flag(
                        raw_item.get("brand_name_only")
                    ),
                )
            )
        return items

    @staticmethod
    def _normalize_brand_flag(value: Any) -> str:
        if value is True:
            return "Yes"
        if value is False:
            return "No"
        if value in (None, ""):
            return ""
        text = str(value).strip().lower()
        if text in {"y", "yes", "true"}:
            return "Yes"
        if text in {"n", "no", "false"}:
            return "No"
        return str(value).strip()

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

    @staticmethod
    def _is_service_item(item: IGCEWorkbookItem) -> bool:
        unit = item.unit.upper()
        description = item.description.lower()
        if unit in _LABOR_UNITS:
            return True
        return any(keyword in description for keyword in _LABOR_KEYWORDS)

    @classmethod
    def _build_total_estimate_fallback_item(
        cls, data: dict[str, Any]
    ) -> IGCEWorkbookItem | None:
        total = cls._coerce_number(data.get("total_estimate"))
        if total is None:
            return None
        description = (
            data.get("description")
            or data.get("title")
            or "Estimated Total"
        )
        return IGCEWorkbookItem(
            description=str(description).strip(),
            quantity=1,
            unit="EA",
            unit_price=total,
            total=total,
        )

    @classmethod
    def _apply_workbook_metadata(cls, workbook, data: dict[str, Any]) -> None:
        calculation = getattr(workbook, "calculation", None)
        if calculation is not None:
            if hasattr(calculation, "calcMode"):
                calculation.calcMode = "auto"
            if hasattr(calculation, "fullCalcOnLoad"):
                calculation.fullCalcOnLoad = True
            if hasattr(calculation, "forceFullCalc"):
                calculation.forceFullCalc = True

        contract_type = cls._string_value(
            data.get("contract_type") or data.get("expected_contract_type")
        )
        if contract_type:
            workbook["IT Services"]["B5"] = contract_type
            workbook["IT Goods"]["B5"] = contract_type

        period = cls._string_value(data.get("period_of_performance"))
        if period:
            start, end = cls._split_period(period)
            if start or end:
                workbook["IT Services"]["C6"] = start
                workbook["IT Services"]["E6"] = end
            else:
                workbook["IT Services"]["C6"] = period

        delivery_date = cls._string_value(
            data.get("delivery_date") or data.get("required_delivery_date")
        )
        if delivery_date:
            workbook["IT Goods"]["B6"] = delivery_date

    @staticmethod
    def _string_value(value: Any) -> str:
        if value in (None, ""):
            return ""
        return str(value).strip()

    @staticmethod
    def _split_period(value: str) -> tuple[str, str]:
        separators = (" to ", " - ", " through ", " thru ")
        lower = value.lower()
        for separator in separators:
            if separator in lower:
                index = lower.index(separator)
                start = value[:index].strip()
                end = value[index + len(separator) :].strip()
                if start or end:
                    return start, end
        return "", ""

    @classmethod
    def _populate_summary_sheet(
        cls,
        sheet,
        service_items: Sequence[IGCEWorkbookItem],
        goods_items: Sequence[IGCEWorkbookItem],
    ) -> None:
        cls._clear_summary_sheet(sheet)

        for row, item in zip(SUMMARY_LABOR_ROWS, cls._compress_items(service_items, len(SUMMARY_LABOR_ROWS))):
            sheet[f"A{row}"] = item.description
            sheet[f"C{row}"] = item.quantity
            sheet[f"E{row}"] = item.unit_price

        for row, item in zip(SUMMARY_ODC_ROWS, cls._compress_items(goods_items, len(SUMMARY_ODC_ROWS))):
            sheet[f"A{row}"] = item.description
            sheet[f"E{row}"] = item.total

    @classmethod
    def _populate_it_services_sheet(
        cls,
        sheet,
        service_items: Sequence[IGCEWorkbookItem],
        data: dict[str, Any],
    ) -> None:
        cls._clear_it_services_sheet(sheet)

        for row, item in zip(IT_SERVICES_ROWS, cls._compress_items(service_items, len(IT_SERVICES_ROWS))):
            quantity = item.quantity if item.quantity is not None else 0
            rate = item.unit_price if item.unit_price is not None else 0
            sheet[f"A{row}"] = item.description
            sheet[f"B{row}"] = quantity
            sheet[f"C{row}"] = rate
            for hours_col in ("E", "H", "K", "N"):
                sheet[f"{hours_col}{row}"] = 0
            for rate_col in ("F", "I", "L", "O"):
                sheet[f"{rate_col}{row}"] = 0

        prepared_by = cls._string_value(data.get("prepared_by"))
        if prepared_by and sheet["B2"].value in (None, "", "-"):
            sheet["B2"] = prepared_by

    @classmethod
    def _populate_it_goods_sheet(
        cls,
        sheet,
        goods_items: Sequence[IGCEWorkbookItem],
        data: dict[str, Any],
    ) -> None:
        cls._clear_it_goods_sheet(sheet)

        for row, item in zip(IT_GOODS_ROWS, cls._compress_items(goods_items, len(IT_GOODS_ROWS))):
            quantity = item.quantity if item.quantity is not None else 1
            unit_price = item.unit_price
            if unit_price is None:
                unit_price = item.total if item.total is not None else 0
            sheet[f"A{row}"] = item.description
            sheet[f"B{row}"] = item.manufacturer
            sheet[f"C{row}"] = item.manufacturer_number
            sheet[f"D{row}"] = item.brand_name_only
            sheet[f"E{row}"] = quantity
            sheet[f"F{row}"] = unit_price

        prepared_date = cls._string_value(data.get("prepared_date"))
        if prepared_date and sheet["B2"].value in (None, "", "-"):
            sheet["B2"] = prepared_date

    @classmethod
    def _clear_summary_sheet(cls, sheet) -> None:
        for row in SUMMARY_LABOR_ROWS:
            for col in ("A", "C", "E"):
                sheet[f"{col}{row}"] = None
        for row in SUMMARY_ODC_ROWS:
            for col in ("A", "E"):
                sheet[f"{col}{row}"] = None

    @classmethod
    def _clear_it_services_sheet(cls, sheet) -> None:
        sheet["B2"] = "-"
        for cell in ("B5", "C6", "E6"):
            sheet[cell] = None
        for row in IT_SERVICES_ROWS:
            for col in ("A", "B", "C", "E", "F", "H", "I", "K", "L", "N", "O"):
                sheet[f"{col}{row}"] = None

    @classmethod
    def _clear_it_goods_sheet(cls, sheet) -> None:
        sheet["B2"] = "-"
        for cell in ("B5", "B6"):
            sheet[cell] = None
        for row in IT_GOODS_ROWS:
            for col in ("A", "B", "C", "D", "E", "F"):
                sheet[f"{col}{row}"] = None

    @classmethod
    def _compress_items(
        cls,
        items: Sequence[IGCEWorkbookItem],
        limit: int,
    ) -> List[IGCEWorkbookItem]:
        material_items = [item for item in items if item.description or item.total is not None]
        if len(material_items) <= limit:
            return material_items

        kept = list(material_items[: limit - 1])
        overflow = material_items[limit - 1 :]
        kept.append(cls._aggregate_items(overflow))
        return kept

    @classmethod
    def _aggregate_items(cls, items: Iterable[IGCEWorkbookItem]) -> IGCEWorkbookItem:
        items = list(items)
        quantity_total = sum(
            item.quantity for item in items if isinstance(item.quantity, (int, float))
        )
        total_cost = sum(
            cls._item_total(item) for item in items if cls._item_total(item) is not None
        )
        quantity = quantity_total if quantity_total else 1
        unit_price = total_cost / quantity if quantity else total_cost
        return IGCEWorkbookItem(
            description=f"Additional items ({len(items)})",
            quantity=quantity,
            unit="EA",
            unit_price=unit_price,
            total=total_cost,
        )

    @staticmethod
    def _item_total(item: IGCEWorkbookItem) -> float | int | None:
        if item.total is not None:
            return item.total
        if item.quantity is not None and item.unit_price is not None:
            return item.quantity * item.unit_price
        return None
