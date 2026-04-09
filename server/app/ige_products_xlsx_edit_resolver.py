"""Context extraction and deterministic edit resolution for the products IGE workbook."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .ige_products_xlsx_handler import PRODUCT_ROW_SLOTS, SPECIAL_ROWS


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
class ProductWorkbookItem:
    name: str
    row_index: int
    aliases: set[str] = field(default_factory=set)
    description: BoundCell | None = None
    quantity: BoundCell | None = None
    unit_price: BoundCell | None = None
    current_quantity: float | None = None
    current_unit_price: float | None = None


@dataclass
class ProductsWorkbookContext:
    sheet_id: str | None
    items: list[ProductWorkbookItem]

    @property
    def is_supported(self) -> bool:
        return bool(self.sheet_id)

    def find_items(self, query: str) -> list[ProductWorkbookItem]:
        normalized_query = _normalize_label(query)
        if not normalized_query:
            return []
        matches: list[ProductWorkbookItem] = []
        for item in self.items:
            names = {item.name, *item.aliases}
            normalized_names = {_normalize_label(name) for name in names if name}
            if any(name and name in normalized_query for name in normalized_names):
                matches.append(item)
                continue
            item_tokens = {
                token
                for name in normalized_names
                for token in name.split()
                if len(token) > 2
            }
            query_tokens = {token for token in normalized_query.split() if len(token) > 2}
            if item_tokens and item_tokens.intersection(query_tokens):
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


def build_ige_products_workbook_context(
    preview_sheets: list[dict[str, Any]],
) -> ProductsWorkbookContext:
    sheet = _sheet_by_title(preview_sheets, "Sheet1")
    items: list[ProductWorkbookItem] = []
    if not sheet:
        return ProductsWorkbookContext(sheet_id=None, items=items)

    for row in [*PRODUCT_ROW_SLOTS, *SPECIAL_ROWS.values()]:
        description = _bind_cell(sheet, f"B{row}", editable_only=True)
        quantity = _bind_cell(sheet, f"C{row}", editable_only=True)
        unit_price = _bind_cell(sheet, f"D{row}", editable_only=True)
        name = (description.display_value or description.value).strip() if description else ""
        if not (name or quantity or unit_price):
            continue
        aliases = set()
        if row == SPECIAL_ROWS["shipping"]:
            aliases.update({"shipping", "delivery", "freight"})
        elif row == SPECIAL_ROWS["installation"]:
            aliases.update({"installation", "install", "setup"})
        elif row == SPECIAL_ROWS["training"]:
            aliases.update({"training", "train"})
        item = ProductWorkbookItem(
            name=name or f"Row {row}",
            row_index=row,
            aliases=aliases,
            description=description,
            quantity=quantity,
            unit_price=unit_price,
        )
        item.current_quantity = _parse_number(
            (quantity.display_value or quantity.value) if quantity else None
        )
        item.current_unit_price = _parse_number(
            (unit_price.display_value or unit_price.value) if unit_price else None
        )
        items.append(item)

    return ProductsWorkbookContext(
        sheet_id=str(sheet.get("sheet_id", "")),
        items=items,
    )


def resolve_ige_products_edit_request(
    request: str,
    workbook: ProductsWorkbookContext,
) -> ResolvedEditRequest:
    if not request.strip():
        return ResolvedEditRequest(
            clarification="Tell me what product, quantity, or price you want to update in this workbook."
        )

    matches = workbook.find_items(request)
    if len(matches) > 1:
        names = ", ".join(item.name for item in matches[:3])
        return ResolvedEditRequest(
            clarification=f'I found multiple matching items in the workbook: {names}. Which one should I update?'
        )
    if len(matches) != 1:
        return ResolvedEditRequest(
            clarification="I could not match that request to a product row. Reference a specific item such as a product, shipping, installation, or training."
        )

    item = matches[0]
    normalized = _normalize_label(request)
    value = _extract_numeric_value(request)

    wants_quantity = any(
        token in normalized for token in ("quantity", "qty", "units", "licenses", "seats", "copies")
    )
    wants_price = any(
        token in normalized for token in ("price", "cost", "unit price", "rate")
    )

    if "one more" in normalized or "another" in normalized:
        if item.current_quantity is None:
            return ResolvedEditRequest(
                clarification=f'I found "{item.name}" but could not determine its current quantity.'
            )
        return ResolvedEditRequest(
            intents=[ResolvedIntent("update_quantity", _format_number(item.current_quantity + 1), item.name)]
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
            intents=[ResolvedIntent("update_quantity", _format_number(value), item.name)]
        )
    if wants_price:
        if value is None:
            return ResolvedEditRequest(
                clarification=f'What unit price should I set for "{item.name}"?'
            )
        return ResolvedEditRequest(
            intents=[ResolvedIntent("update_unit_price", _format_number(value), item.name)]
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


def apply_products_resolved_intents(
    workbook: ProductsWorkbookContext,
    resolved: ResolvedEditRequest,
) -> tuple[list[dict[str, str]], list[dict[str, str]], str | None]:
    item_lookup = {item.name: item for item in workbook.items}
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
        item = item_lookup.get(intent.item_name or "")
        if not item:
            return [], [], f'I could not match "{intent.item_name}" to a workbook row.'
        if intent.intent_type == "update_quantity":
            add(item.quantity, intent.value, f"{item.name} quantity")
        elif intent.intent_type == "update_unit_price":
            add(item.unit_price, intent.value, f"{item.name} unit price")

    return proposals, applied_changes, None
