"""Commercial IGCE workbook context extraction and edit resolution."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.igce_workbook_schema import (
    IGCE_GOODS_SUMMARY_ROWS,
    IGCE_LABOR_ROWS,
    IT_GOODS_ROWS,
    IT_SERVICES_LABOR_ROWS,
)

# Re-export for backwards compatibility (other modules may import from here)
LABOR_SUMMARY_ROWS = IGCE_LABOR_ROWS
GOODS_SUMMARY_ROWS = IGCE_GOODS_SUMMARY_ROWS
SERVICES_ROWS = IT_SERVICES_LABOR_ROWS
GOODS_ROWS = IT_GOODS_ROWS

SUPPORTED_INTENT_TYPES = {
    "update_labor_rate",
    "update_labor_hours",
    "update_goods_quantity",
    "update_goods_unit_price",
    "update_contract_type",
    "update_delivery_date",
    "update_period_of_performance",
}


def _normalize_label(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _parse_number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    cleaned = text.replace("$", "").replace(",", "").strip()
    if cleaned.endswith("%"):
        cleaned = cleaned[:-1]
    try:
        return float(cleaned)
    except ValueError:
        return None


def _format_number(value: float | int) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


@dataclass
class BoundCell:
    sheet_id: str
    cell_ref: str
    value: str = ""
    display_value: str = ""
    editable: bool = True


@dataclass
class WorkbookItem:
    name: str
    kind: str
    aliases: set[str] = field(default_factory=set)
    summary_hours: BoundCell | None = None
    summary_rate: BoundCell | None = None
    summary_total: BoundCell | None = None
    services_hours: BoundCell | None = None
    services_rate: BoundCell | None = None
    goods_quantity: BoundCell | None = None
    goods_unit_price: BoundCell | None = None
    current_hours: float | None = None
    current_rate: float | None = None
    current_quantity: float | None = None
    current_unit_price: float | None = None


@dataclass
class WorkbookFieldTargets:
    summary_period: BoundCell | None = None
    services_contract_type: BoundCell | None = None
    goods_contract_type: BoundCell | None = None
    goods_delivery_date: BoundCell | None = None


@dataclass
class CommercialIgceWorkbookContext:
    summary_sheet_id: str | None
    services_sheet_id: str | None
    goods_sheet_id: str | None
    items: list[WorkbookItem]
    fields: WorkbookFieldTargets

    @property
    def is_supported(self) -> bool:
        return bool(self.summary_sheet_id and self.services_sheet_id and self.goods_sheet_id)

    def find_items(self, query: str) -> list[WorkbookItem]:
        normalized_query = _normalize_label(query)
        if not normalized_query:
            return []
        matches: list[WorkbookItem] = []
        for item in self.items:
            names = {item.name, *item.aliases}
            normalized_names = {_normalize_label(name) for name in names if name}
            if any(name and name in normalized_query for name in normalized_names):
                matches.append(item)
        return matches


@dataclass
class ResolvedIntent:
    intent_type: str
    value: str
    item_name: str | None = None


@dataclass
class ResolvedEditRequest:
    intents: list[ResolvedIntent] = field(default_factory=list)
    clarification: str | None = None
    is_context_fill_request: bool = False


def _sheet_cell_map(sheet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    cells: dict[str, dict[str, Any]] = {}
    for row in sheet.get("rows", []):
        for cell in row.get("cells", []):
            cell_ref = str(cell.get("cell_ref", ""))
            if cell_ref:
                cells[cell_ref.upper()] = cell
    return cells


def _bind_cell(sheet: dict[str, Any] | None, cell_ref: str, *, editable_only: bool = False) -> BoundCell | None:
    if not sheet:
        return None
    cell = _sheet_cell_map(sheet).get(cell_ref.upper())
    if not cell:
        return None
    editable = bool(cell.get("editable"))
    if editable_only and not editable:
        return None
    return BoundCell(
        sheet_id=str(sheet.get("sheet_id", "")),
        cell_ref=str(cell.get("cell_ref", cell_ref)),
        value=str(cell.get("value", "")),
        display_value=str(cell.get("display_value", "")),
        editable=editable,
    )


def _sheet_by_title(preview_sheets: list[dict[str, Any]], title: str) -> dict[str, Any] | None:
    for sheet in preview_sheets:
        if str(sheet.get("title", "")).strip().lower() == title.lower():
            return sheet
    return None


def build_commercial_igce_workbook_context(
    preview_sheets: list[dict[str, Any]],
) -> CommercialIgceWorkbookContext:
    summary_sheet = _sheet_by_title(preview_sheets, "IGCE")
    services_sheet = _sheet_by_title(preview_sheets, "IT Services")
    goods_sheet = _sheet_by_title(preview_sheets, "IT Goods")

    items: list[WorkbookItem] = []

    for index, summary_row in enumerate(LABOR_SUMMARY_ROWS):
        summary_name = _bind_cell(summary_sheet, f"A{summary_row}")
        name = (summary_name.display_value or summary_name.value).strip() if summary_name else ""
        if not name:
            continue
        services_row = SERVICES_ROWS[index] if index < len(SERVICES_ROWS) else None
        services_name = _bind_cell(services_sheet, f"A{services_row}") if services_row else None
        item = WorkbookItem(
            name=name,
            kind="labor",
            aliases={services_name.display_value or services_name.value} if services_name else set(),
            summary_hours=_bind_cell(summary_sheet, f"C{summary_row}", editable_only=True),
            summary_rate=_bind_cell(summary_sheet, f"E{summary_row}", editable_only=True),
            services_hours=_bind_cell(services_sheet, f"B{services_row}", editable_only=True)
            if services_row
            else None,
            services_rate=_bind_cell(services_sheet, f"C{services_row}", editable_only=True)
            if services_row
            else None,
        )
        item.current_hours = _parse_number(
            (item.summary_hours.display_value or item.summary_hours.value)
            if item.summary_hours
            else None
        )
        item.current_rate = _parse_number(
            (item.summary_rate.display_value or item.summary_rate.value)
            if item.summary_rate
            else None
        )
        items.append(item)

    for index, summary_row in enumerate(GOODS_SUMMARY_ROWS):
        summary_name = _bind_cell(summary_sheet, f"A{summary_row}")
        name = (summary_name.display_value or summary_name.value).strip() if summary_name else ""
        if not name:
            continue
        goods_row = GOODS_ROWS[index] if index < len(GOODS_ROWS) else None
        goods_name = _bind_cell(goods_sheet, f"A{goods_row}") if goods_row else None
        item = WorkbookItem(
            name=name,
            kind="goods",
            aliases={goods_name.display_value or goods_name.value} if goods_name else set(),
            summary_total=_bind_cell(summary_sheet, f"E{summary_row}", editable_only=True),
            goods_quantity=_bind_cell(goods_sheet, f"E{goods_row}", editable_only=True)
            if goods_row
            else None,
            goods_unit_price=_bind_cell(goods_sheet, f"F{goods_row}", editable_only=True)
            if goods_row
            else None,
        )
        item.current_quantity = _parse_number(
            (item.goods_quantity.display_value or item.goods_quantity.value)
            if item.goods_quantity
            else None
        )
        item.current_unit_price = _parse_number(
            (item.goods_unit_price.display_value or item.goods_unit_price.value)
            if item.goods_unit_price
            else None
        )
        items.append(item)

    fields = WorkbookFieldTargets(
        summary_period=_bind_cell(summary_sheet, "C5", editable_only=True),
        services_contract_type=_bind_cell(services_sheet, "B5", editable_only=True),
        goods_contract_type=_bind_cell(goods_sheet, "B5", editable_only=True),
        goods_delivery_date=_bind_cell(goods_sheet, "B6", editable_only=True),
    )

    return CommercialIgceWorkbookContext(
        summary_sheet_id=str(summary_sheet.get("sheet_id", "")) if summary_sheet else None,
        services_sheet_id=str(services_sheet.get("sheet_id", "")) if services_sheet else None,
        goods_sheet_id=str(goods_sheet.get("sheet_id", "")) if goods_sheet else None,
        items=items,
        fields=fields,
    )


def _extract_numeric_value(request: str) -> float | None:
    matches = re.findall(r"\$?\s*([0-9][0-9,]*(?:\.\d+)?)", request)
    if not matches:
        return None
    try:
        return float(matches[-1].replace(",", ""))
    except ValueError:
        return None


def _resolve_item_change(
    request: str,
    item: WorkbookItem,
) -> ResolvedEditRequest:
    normalized = _normalize_label(request)
    value = _extract_numeric_value(request)

    if item.kind == "labor":
        wants_rate = any(
            marker in normalized
            for marker in ("rate", "hourly", "per hour", "hour", "hr")
        ) or "/hour" in request.lower()
        wants_hours = any(marker in normalized for marker in ("hours", "effort", "fte"))
        if wants_rate and wants_hours:
            return ResolvedEditRequest(
                clarification=f'I found "{item.name}" in the workbook. Do you want to change the hourly rate, hours, or both?'
            )
        if wants_rate:
            if value is None:
                return ResolvedEditRequest(
                    clarification=f'What hourly rate should I use for "{item.name}"?'
                )
            return ResolvedEditRequest(
                intents=[ResolvedIntent("update_labor_rate", _format_number(value), item.name)]
            )
        if wants_hours:
            if value is None:
                return ResolvedEditRequest(
                    clarification=f'How many hours should I set for "{item.name}"?'
                )
            return ResolvedEditRequest(
                intents=[ResolvedIntent("update_labor_hours", _format_number(value), item.name)]
            )
        return ResolvedEditRequest(
            clarification=f'I found "{item.name}" in the workbook. Do you want to change the hourly rate, hours, or both?'
        )

    wants_quantity = any(
        marker in normalized
        for marker in ("quantity", "qty", "months", "month", "units", "unit", "licenses", "license", "seats", "seat")
    )
    wants_price = any(
        marker in normalized
        for marker in ("price", "cost", "unit price", "monthly rate", "per month", "per unit")
    ) or "/month" in request.lower()
    if "one more" in normalized or "another" in normalized:
        if item.current_quantity is None:
            return ResolvedEditRequest(
                clarification=f'I found "{item.name}" but could not determine its current quantity.'
            )
        return ResolvedEditRequest(
            intents=[
                ResolvedIntent(
                    "update_goods_quantity",
                    _format_number(item.current_quantity + 1),
                    item.name,
                )
            ]
        )
    if wants_quantity and wants_price:
        return ResolvedEditRequest(
            clarification=f'I found "{item.name}" in the workbook. Do you want to change the quantity, the unit price, or both?'
        )
    if wants_quantity:
        if value is None:
            return ResolvedEditRequest(
                clarification=f'What quantity should I set for "{item.name}"?'
            )
        return ResolvedEditRequest(
            intents=[ResolvedIntent("update_goods_quantity", _format_number(value), item.name)]
        )
    if wants_price:
        if value is None:
            return ResolvedEditRequest(
                clarification=f'What unit price should I set for "{item.name}"?'
            )
        return ResolvedEditRequest(
            intents=[ResolvedIntent("update_goods_unit_price", _format_number(value), item.name)]
        )
    return ResolvedEditRequest(
        clarification=f'I found "{item.name}" in the workbook. Do you want to change the quantity or the unit price?'
    )


def resolve_igce_edit_request(
    request: str,
    workbook: CommercialIgceWorkbookContext,
) -> ResolvedEditRequest:
    lowered = (request or "").lower()
    if not request.strip():
        return ResolvedEditRequest(clarification="Tell me what you want to change in this IGCE workbook.")

    contract_match = re.search(r"contract type(?:\s+to|\s+as|\s+is)?\s+(.+)$", request, flags=re.IGNORECASE)
    if contract_match:
        value = contract_match.group(1).strip().rstrip(".")
        if value:
            return ResolvedEditRequest(intents=[ResolvedIntent("update_contract_type", value)])

    delivery_match = re.search(r"delivery date(?:\s+to|\s+as|\s+is)?\s+(.+)$", request, flags=re.IGNORECASE)
    if delivery_match:
        value = delivery_match.group(1).strip().rstrip(".")
        if value:
            return ResolvedEditRequest(intents=[ResolvedIntent("update_delivery_date", value)])

    period_match = re.search(
        r"(?:period of performance|period(?:\s+months)?)(?:\s+to|\s+as|\s+is)?\s+(.+)$",
        request,
        flags=re.IGNORECASE,
    )
    if period_match:
        value = period_match.group(1).strip().rstrip(".")
        if value:
            return ResolvedEditRequest(intents=[ResolvedIntent("update_period_of_performance", value)])

    matches = workbook.find_items(request)
    if len(matches) > 1:
        names = ", ".join(item.name for item in matches[:3])
        return ResolvedEditRequest(
            clarification=f'I found multiple matching items in the workbook: {names}. Which one should I update?'
        )
    if len(matches) == 1:
        return _resolve_item_change(request, matches[0])

    # Detect context-fill requests: "fill from context", "complete the IGCE", etc.
    context_fill_patterns = [
        "fill", "complete", "populate", "use our conversation", "from context",
        "use the context", "from our discussion", "from earlier", "rest of the igce",
        "fill in", "fill out", "auto fill", "autofill",
    ]
    if any(pattern in lowered for pattern in context_fill_patterns):
        return ResolvedEditRequest(is_context_fill_request=True)

    return ResolvedEditRequest(
        clarification="I could not match that request to a supported IGCE field or row. Reference a specific labor or goods item, contract type, period of performance, or delivery date."
    )


def validate_ai_intents(
    intents: list[dict[str, Any]],
    workbook: CommercialIgceWorkbookContext,
) -> ResolvedEditRequest:
    resolved: list[ResolvedIntent] = []
    for raw_intent in intents:
        intent_type = str(raw_intent.get("type", "")).strip()
        if intent_type not in SUPPORTED_INTENT_TYPES:
            continue
        value = str(raw_intent.get("value", "")).strip()
        if not value:
            continue
        item_name = str(raw_intent.get("item_name", "")).strip() or None
        if item_name:
            matches = workbook.find_items(item_name)
            if len(matches) != 1:
                return ResolvedEditRequest(
                    clarification=f'I could not confidently match "{item_name}" to a single workbook row.'
                )
            item_name = matches[0].name
        resolved.append(ResolvedIntent(intent_type=intent_type, item_name=item_name, value=value))
    return ResolvedEditRequest(intents=resolved)


@dataclass
class ContextFillResult:
    """Result of building intents from stored context."""
    intents: list[ResolvedIntent] = field(default_factory=list)
    skipped_fields: list[dict[str, str]] = field(default_factory=list)


def build_context_fill_intents(
    source_data: dict[str, Any] | None,
    workbook: CommercialIgceWorkbookContext,
) -> ContextFillResult:
    """Build edit intents from stored source_data to fill empty workbook cells.

    Only fills cells that are currently empty. Tracks skipped fields with reasons.

    Args:
        source_data: Stored extraction data with line_items, goods_items, etc.
        workbook: Current workbook context with existing values

    Returns:
        ContextFillResult with intents and skipped_fields
    """
    if not source_data:
        return ContextFillResult(
            skipped_fields=[{"field": "all", "reason": "No origin context available"}]
        )

    intents: list[ResolvedIntent] = []
    skipped: list[dict[str, str]] = []

    # Fill contract type if empty
    contract_type = source_data.get("contract_type")
    if contract_type:
        services_ct = workbook.fields.services_contract_type
        goods_ct = workbook.fields.goods_contract_type
        services_empty = services_ct and not (services_ct.display_value or services_ct.value).strip()
        goods_empty = goods_ct and not (goods_ct.display_value or goods_ct.value).strip()
        if services_empty or goods_empty:
            intents.append(ResolvedIntent("update_contract_type", str(contract_type)))
        else:
            skipped.append({"field": "contract_type", "reason": "already has value"})
    else:
        skipped.append({"field": "contract_type", "reason": "not in context"})

    # Fill period of performance if empty
    period_months = source_data.get("period_months")
    if period_months:
        period_cell = workbook.fields.summary_period
        period_empty = period_cell and not (period_cell.display_value or period_cell.value).strip()
        if period_empty:
            intents.append(ResolvedIntent("update_period_of_performance", str(period_months)))
        else:
            skipped.append({"field": "period_of_performance", "reason": "already has value"})
    else:
        skipped.append({"field": "period_of_performance", "reason": "not in context"})

    delivery_date = source_data.get("delivery_date")
    if delivery_date:
        delivery_cell = workbook.fields.goods_delivery_date
        delivery_empty = delivery_cell and not (delivery_cell.display_value or delivery_cell.value).strip()
        if delivery_empty:
            intents.append(ResolvedIntent("update_delivery_date", str(delivery_date)))
        else:
            skipped.append({"field": "delivery_date", "reason": "already has value"})
    else:
        skipped.append({"field": "delivery_date", "reason": "not in context"})

    # Build item lookup for matching
    item_lookup = {_normalize_label(item.name): item for item in workbook.items}

    # Fill labor items
    line_items = source_data.get("line_items", [])
    for idx, line_item in enumerate(line_items):
        description = line_item.get("description", "")
        rate = line_item.get("rate")
        hours = line_item.get("hours")

        # Try to match to existing workbook item
        normalized_desc = _normalize_label(description)
        matched_item = item_lookup.get(normalized_desc)

        if not matched_item:
            # Try partial match
            for key, item in item_lookup.items():
                if item.kind == "labor" and (normalized_desc in key or key in normalized_desc):
                    matched_item = item
                    break

        if not matched_item:
            # Use positional matching for unmatched items
            labor_items = [i for i in workbook.items if i.kind == "labor"]
            if idx < len(labor_items):
                matched_item = labor_items[idx]

        if matched_item and matched_item.kind == "labor":
            # Fill rate if provided and cell is empty
            if rate is not None:
                rate_empty = matched_item.current_rate is None or matched_item.current_rate == 0
                if rate_empty:
                    intents.append(ResolvedIntent("update_labor_rate", str(rate), matched_item.name))
                else:
                    skipped.append({"field": f"{matched_item.name} rate", "reason": "already has value"})

            # Fill hours if provided and cell is empty
            if hours is not None:
                hours_empty = matched_item.current_hours is None or matched_item.current_hours == 0
                if hours_empty:
                    intents.append(ResolvedIntent("update_labor_hours", str(hours), matched_item.name))
                else:
                    skipped.append({"field": f"{matched_item.name} hours", "reason": "already has value"})
        elif description:
            skipped.append({"field": description, "reason": "could not match to workbook row"})

    # Fill goods items
    goods_items = source_data.get("goods_items", [])
    for idx, goods_item in enumerate(goods_items):
        product_name = goods_item.get("product_name", "")
        quantity = goods_item.get("quantity")
        unit_price = goods_item.get("unit_price")

        # Try to match to existing workbook item
        normalized_name = _normalize_label(product_name)
        matched_item = item_lookup.get(normalized_name)

        if not matched_item:
            # Try partial match
            for key, item in item_lookup.items():
                if item.kind == "goods" and (normalized_name in key or key in normalized_name):
                    matched_item = item
                    break

        if not matched_item:
            # Use positional matching for unmatched items
            goods_workbook_items = [i for i in workbook.items if i.kind == "goods"]
            if idx < len(goods_workbook_items):
                matched_item = goods_workbook_items[idx]

        if matched_item and matched_item.kind == "goods":
            # Fill quantity if provided and cell is empty
            if quantity is not None:
                qty_empty = matched_item.current_quantity is None or matched_item.current_quantity == 0
                if qty_empty:
                    intents.append(ResolvedIntent("update_goods_quantity", str(quantity), matched_item.name))
                else:
                    skipped.append({"field": f"{matched_item.name} quantity", "reason": "already has value"})

            # Fill unit price if provided and cell is empty
            if unit_price is not None:
                price_empty = matched_item.current_unit_price is None or matched_item.current_unit_price == 0
                if price_empty:
                    intents.append(ResolvedIntent("update_goods_unit_price", str(unit_price), matched_item.name))
                else:
                    skipped.append({"field": f"{matched_item.name} unit_price", "reason": "already has value"})
        elif product_name:
            skipped.append({"field": product_name, "reason": "could not match to workbook row"})

    return ContextFillResult(intents=intents, skipped_fields=skipped)
