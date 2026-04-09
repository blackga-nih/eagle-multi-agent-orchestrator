"""Context extraction and deterministic edit resolution for the services IGE workbook."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .ige_services_catalog_xlsx_handler import BASE_SHEET, OPTION_ONE_SHEET, SERVICE_ROW_SLOTS


def _normalize_label(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _parse_number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    cleaned = text.replace("$", "").replace(",", "").strip()
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
class ServiceWorkbookItem:
    sheet_title: str
    name: str
    quantity: BoundCell | None = None
    unit_price: BoundCell | None = None
    current_quantity: float | None = None
    current_unit_price: float | None = None


@dataclass
class ServicesWorkbookContext:
    items: list[ServiceWorkbookItem]

    @property
    def is_supported(self) -> bool:
        return bool(self.items)

    def find_items(self, query: str) -> list[ServiceWorkbookItem]:
        normalized_query = _normalize_label(query)
        query_tokens = {token for token in normalized_query.split() if len(token) > 2}
        exact_matches: list[ServiceWorkbookItem] = []
        token_matches: list[ServiceWorkbookItem] = []
        for item in self.items:
            normalized_name = _normalize_label(item.name)
            if normalized_name and normalized_name in normalized_query:
                exact_matches.append(item)
                continue
            item_tokens = {token for token in normalized_name.split() if len(token) > 2}
            if item_tokens and item_tokens.intersection(query_tokens):
                token_matches.append(item)
        return exact_matches or token_matches


@dataclass
class ResolvedIntent:
    intent_type: str
    value: str
    item_name: str | None = None
    sheet_title: str | None = None


@dataclass
class ResolvedEditRequest:
    intents: list[ResolvedIntent] = field(default_factory=list)
    clarification: str | None = None


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


def build_ige_services_catalog_workbook_context(
    preview_sheets: list[dict[str, Any]],
) -> ServicesWorkbookContext:
    items: list[ServiceWorkbookItem] = []
    for sheet_title in (BASE_SHEET, OPTION_ONE_SHEET):
        sheet = _sheet_by_title(preview_sheets, sheet_title)
        if not sheet:
            continue
        for row in SERVICE_ROW_SLOTS:
            desc = _bind_cell(sheet, f"A{row}", editable_only=True)
            qty = _bind_cell(sheet, f"C{row}", editable_only=True)
            price = _bind_cell(sheet, f"D{row}", editable_only=True)
            name = (desc.display_value or desc.value).strip() if desc else ""
            if not (name or qty or price):
                continue
            item = ServiceWorkbookItem(
                sheet_title=sheet_title,
                name=name or f"{sheet_title} Row {row}",
                quantity=qty,
                unit_price=price,
            )
            item.current_quantity = _parse_number((qty.display_value or qty.value) if qty else None)
            item.current_unit_price = _parse_number((price.display_value or price.value) if price else None)
            items.append(item)
    return ServicesWorkbookContext(items=items)


def resolve_ige_services_catalog_edit_request(
    request: str,
    workbook: ServicesWorkbookContext,
) -> ResolvedEditRequest:
    if not request.strip():
        return ResolvedEditRequest(
            clarification="Tell me what service, quantity, or unit price you want to update in this workbook."
        )

    matches = workbook.find_items(request)
    if len(matches) > 1:
        names = ", ".join(f"{item.sheet_title}: {item.name}" for item in matches[:3])
        return ResolvedEditRequest(
            clarification=f"I found multiple matching service rows: {names}. Which one should I update?"
        )
    if len(matches) != 1:
        return ResolvedEditRequest(
            clarification="I could not match that request to a service row. Reference a specific service description."
        )

    item = matches[0]
    normalized = _normalize_label(request)
    value = _extract_numeric_value(request)
    wants_quantity = any(
        token in normalized for token in ("quantity", "qty", "months", "month", "period")
    )
    wants_price = any(
        token in normalized for token in ("price", "cost", "rate", "unit price")
    )

    if wants_quantity and wants_price:
        return ResolvedEditRequest(
            clarification=f'I found "{item.name}" in the workbook. Do you want to change the quantity or the unit price?'
        )
    if wants_quantity:
        if value is None:
            return ResolvedEditRequest(
                clarification=f'What quantity should I set for "{item.name}"?'
            )
        return ResolvedEditRequest(
            intents=[ResolvedIntent("update_quantity", _format_number(value), item.name, item.sheet_title)]
        )
    if wants_price:
        if value is None:
            return ResolvedEditRequest(
                clarification=f'What unit price should I set for "{item.name}"?'
            )
        return ResolvedEditRequest(
            intents=[ResolvedIntent("update_unit_price", _format_number(value), item.name, item.sheet_title)]
        )
    return ResolvedEditRequest(
        clarification=f'I found "{item.name}" in the workbook. Do you want to change the quantity or the unit price?'
    )


def _extract_numeric_value(request: str) -> float | None:
    matches = re.findall(r"\$?\s*([0-9][0-9,]*(?:\.\d+)?)", request)
    if not matches:
        return None
    try:
        return float(matches[-1].replace(",", ""))
    except ValueError:
        return None


def apply_services_resolved_intents(
    workbook: ServicesWorkbookContext,
    resolved: ResolvedEditRequest,
) -> tuple[list[dict[str, str]], list[dict[str, str]], str | None]:
    item_lookup = {(item.sheet_title, item.name): item for item in workbook.items}
    proposals: list[dict[str, str]] = []
    applied_changes: list[dict[str, str]] = []

    def add(binding: BoundCell | None, after: str, label: str) -> None:
        if not binding:
            return
        before = binding.display_value or binding.value
        if str(before or "") == str(after):
            return
        proposals.append(
            {
                "sheet_id": binding.sheet_id,
                "cell_ref": binding.cell_ref,
                "value": str(after),
            }
        )
        applied_changes.append(
            {
                "sheet_id": binding.sheet_id,
                "cell_ref": binding.cell_ref,
                "before": str(before or ""),
                "after": str(after),
                "label": label,
            }
        )

    for intent in resolved.intents:
        item = item_lookup.get((intent.sheet_title or "", intent.item_name or ""))
        if not item:
            return [], [], f'I could not match "{intent.item_name}" to a workbook row.'
        if intent.intent_type == "update_quantity":
            add(item.quantity, intent.value, f"{item.sheet_title} {item.name} quantity")
        elif intent.intent_type == "update_unit_price":
            add(item.unit_price, intent.value, f"{item.sheet_title} {item.name} unit price")

    return proposals, applied_changes, None
