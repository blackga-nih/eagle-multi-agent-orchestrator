"""Generic workbook-wide XLSX edit resolution for visible preview sheets."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorkbookEditProposal:
    sheet_id: str
    sheet_title: str
    cell_ref: str
    before: str
    after: str
    label: str


@dataclass
class WorkbookEditResolution:
    proposals: list[WorkbookEditProposal] = field(default_factory=list)
    clarification: str | None = None


@dataclass
class IndexedEditableCell:
    sheet_id: str
    sheet_title: str
    row_index: int
    col_index: int
    cell_ref: str
    value: str
    display_value: str
    row_label: str
    column_context: str


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _normalize_for_compare(text: str) -> str:
    return re.sub(r"\s+", " ", _normalize(text))


def _extract_numeric_value(request: str) -> str | None:
    matches = re.findall(r"\$?\s*([0-9][0-9,]*(?:\.\d+)?)", request)
    if not matches:
        return None
    return matches[-1].replace(",", "")


def _extract_string_value(request: str, trigger: str) -> str | None:
    pattern = rf"{trigger}(?:\s+to|\s+as|\s+is|\s+should be|\s*=)?\s+(.+)$"
    match = re.search(pattern, request, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1).strip().rstrip(".")


def _sheet_by_title(preview_sheets: list[dict[str, Any]], title: str) -> dict[str, Any] | None:
    for sheet in preview_sheets:
        if str(sheet.get("title", "")).strip().lower() == title.lower():
            return sheet
    return None


def _row_label_for_row(cells: list[dict[str, Any]]) -> str:
    for cell in sorted(cells, key=lambda item: int(item.get("col", 0) or 0)):
        value = str(cell.get("display_value") or cell.get("value") or "").strip()
        if value and not re.fullmatch(r"[-+]?\d+(?:\.\d+)?", value):
            return value
    return ""


def _column_context(sheet: dict[str, Any], row_index: int, col_index: int) -> str:
    headers: list[str] = []
    for row in reversed(sheet.get("rows", [])):
        candidate_row = int(row.get("row_index", 0) or 0)
        if candidate_row >= row_index:
            continue
        for cell in row.get("cells", []):
            if int(cell.get("col", 0) or 0) != col_index:
                continue
            value = str(cell.get("display_value") or cell.get("value") or "").strip()
            if not value or re.fullmatch(r"[-+]?\d+(?:\.\d+)?", value):
                continue
            if value and value not in headers:
                headers.append(value)
                break
        if len(headers) >= 3:
            break
    headers.reverse()
    return " | ".join(headers)


def _index_editable_cells(preview_sheets: list[dict[str, Any]]) -> list[IndexedEditableCell]:
    indexed: list[IndexedEditableCell] = []
    for sheet in preview_sheets:
        row_labels: dict[int, str] = {}
        for row in sheet.get("rows", []):
            row_index = int(row.get("row_index", 0) or 0)
            row_labels[row_index] = _row_label_for_row(row.get("cells", []))

        for row in sheet.get("rows", []):
            row_index = int(row.get("row_index", 0) or 0)
            row_label = row_labels.get(row_index, "")
            for cell in row.get("cells", []):
                if not bool(cell.get("editable")):
                    continue
                col_index = int(cell.get("col", 0) or 0)
                indexed.append(
                    IndexedEditableCell(
                        sheet_id=str(sheet.get("sheet_id", "")),
                        sheet_title=str(sheet.get("title", "")),
                        row_index=row_index,
                        col_index=col_index,
                        cell_ref=str(cell.get("cell_ref", "")),
                        value=str(cell.get("value", "")),
                        display_value=str(cell.get("display_value", "")),
                        row_label=row_label,
                        column_context=_column_context(sheet, row_index, col_index),
                    )
                )
    return indexed


def _match_sheet_titles(request: str, preview_sheets: list[dict[str, Any]]) -> list[str]:
    normalized_request = _normalize(request)
    matches: list[str] = []
    for sheet in preview_sheets:
        title = str(sheet.get("title", ""))
        if _normalize(title) and _normalize(title) in normalized_request:
            matches.append(title)
    return matches


def _resolve_direct_cell_request(
    request: str,
    indexed_cells: list[IndexedEditableCell],
    sheet_titles: list[str],
) -> WorkbookEditResolution | None:
    cell_match = re.search(r"\b([A-Z]{1,3}\d{1,5})\b", request)
    if not cell_match:
        return None
    cell_ref = cell_match.group(1).upper()
    value = _extract_numeric_value(request)
    if value is None:
        quoted = re.findall(r'"([^"]+)"', request)
        if quoted:
            value = quoted[-1]
    if value is None:
        return WorkbookEditResolution(
            clarification=f"What value should I set in {cell_ref}?"
        )

    matches = [cell for cell in indexed_cells if cell.cell_ref.upper() == cell_ref]
    if sheet_titles:
        matches = [cell for cell in matches if cell.sheet_title in sheet_titles]
    if not matches:
        return WorkbookEditResolution(
            clarification=f"I could not find an editable cell {cell_ref} in this workbook."
        )
    if len(matches) > 1:
        titles = ", ".join(sorted({cell.sheet_title for cell in matches}))
        return WorkbookEditResolution(
            clarification=f"Cell {cell_ref} exists on multiple sheets: {titles}. Which sheet should I update?"
        )
    cell = matches[0]
    return WorkbookEditResolution(
        proposals=[
            WorkbookEditProposal(
                sheet_id=cell.sheet_id,
                sheet_title=cell.sheet_title,
                cell_ref=cell.cell_ref,
                before=cell.display_value or cell.value,
                after=value,
                label=f"{cell.sheet_title} {cell.cell_ref}",
            )
        ]
    )


def _semantic_for_request(request: str) -> str | None:
    normalized = _normalize(request)
    if any(token in normalized for token in ("hourly rate", "rate", "salary", "per hour", " hr", "hour ")):
        return "rate"
    if any(token in normalized for token in ("hours", "effort", "fte")):
        return "hours"
    if any(token in normalized for token in ("unit price", "price", "cost", "monthly rate", "per month")):
        return "unit_price"
    if any(token in normalized for token in ("quantity", "qty", "months", "month", "units", "licenses", "seats")):
        return "quantity"
    return None


def _header_matches_semantic(header: str, semantic: str) -> bool:
    normalized = _normalize(header)
    if semantic == "rate":
        return any(token in normalized for token in ("hourly rate", "rate", "salary"))
    if semantic == "hours":
        return any(token in normalized for token in ("hours", "effort"))
    if semantic == "unit_price":
        return any(token in normalized for token in ("unit price", "price", "cost"))
    if semantic == "quantity":
        return any(token in normalized for token in ("qty", "quantity"))
    return False


def _position_matches_semantic(cell: IndexedEditableCell, semantic: str) -> bool:
    title = cell.sheet_title.strip().lower()
    if title == "igce":
        if semantic == "hours":
            return cell.col_index == 3
        if semantic == "rate":
            return cell.col_index == 5
    if title == "it services":
        if semantic == "hours":
            return cell.col_index in {2, 5, 8, 11, 14}
        if semantic == "rate":
            return cell.col_index in {3, 6, 9, 12, 15}
    if title == "it goods":
        if semantic == "quantity":
            return cell.col_index == 5
        if semantic == "unit_price":
            return cell.col_index == 6
    return False


def _extract_candidate_row_labels(indexed_cells: list[IndexedEditableCell]) -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()
    for cell in indexed_cells:
        label = cell.row_label.strip()
        normalized = _normalize_for_compare(label)
        if not label or not normalized or normalized in seen:
            continue
        seen.add(normalized)
        labels.append(label)
    return labels


def _match_row_labels(request: str, labels: list[str]) -> list[str]:
    normalized_request = _normalize_for_compare(request)
    ranked: list[tuple[int, str]] = []
    for label in labels:
        normalized_label = _normalize_for_compare(label)
        if not normalized_label:
            continue
        score = 0
        if normalized_label in normalized_request:
            score = max(score, 3)
        label_tokens = [token for token in normalized_label.split() if len(token) > 2]
        if label_tokens and all(token in normalized_request for token in label_tokens):
            score = max(score, 2)
        if len(label_tokens) == 1 and label_tokens[0] in normalized_request:
            score = max(score, 2)
        if score:
            ranked.append((score, label))
    if not ranked:
        return []
    best = max(score for score, _ in ranked)
    return sorted({label for score, label in ranked if score == best})


def _resolve_metadata_request(
    request: str,
    indexed_cells: list[IndexedEditableCell],
    sheet_titles: list[str],
) -> WorkbookEditResolution | None:
    metadata_patterns = [
        ("contract type", "contract type"),
        ("delivery date", "delivery date"),
        ("period of performance", "period of performance"),
    ]
    normalized_request = _normalize(request)
    for trigger, label in metadata_patterns:
        if trigger not in normalized_request:
            continue
        value = _extract_string_value(request, trigger)
        if not value:
            return WorkbookEditResolution(clarification=f"What {label} should I use?")
        matches = [
            cell
            for cell in indexed_cells
            if _normalize(cell.row_label).startswith(trigger)
        ]
        if sheet_titles:
            matches = [cell for cell in matches if cell.sheet_title in sheet_titles]
        if not matches:
            return WorkbookEditResolution(
                clarification=f"I could not find an editable {label} field in this workbook."
            )
        return WorkbookEditResolution(
            proposals=[
                WorkbookEditProposal(
                    sheet_id=cell.sheet_id,
                    sheet_title=cell.sheet_title,
                    cell_ref=cell.cell_ref,
                    before=cell.display_value or cell.value,
                    after=value,
                    label=f"{cell.sheet_title} {label}",
                )
                for cell in matches
            ]
        )
    return None


def resolve_workbook_edit_request(
    request: str,
    preview_sheets: list[dict[str, Any]],
) -> WorkbookEditResolution:
    if not request.strip():
        return WorkbookEditResolution(
            clarification="Tell me what cell, row, or field you want to update in this workbook."
        )

    indexed_cells = _index_editable_cells(preview_sheets)
    sheet_titles = _match_sheet_titles(request, preview_sheets)

    direct = _resolve_direct_cell_request(request, indexed_cells, sheet_titles)
    if direct is not None:
        return direct

    metadata = _resolve_metadata_request(request, indexed_cells, sheet_titles)
    if metadata is not None:
        return metadata

    semantic = _semantic_for_request(request)
    if not semantic:
        return WorkbookEditResolution()

    value = _extract_numeric_value(request)
    if value is None:
        return WorkbookEditResolution(
            clarification="I found the workbook field to update, but I still need the new value."
        )

    labels = _extract_candidate_row_labels(indexed_cells)
    row_matches = _match_row_labels(request, labels)
    if len(row_matches) > 1:
        return WorkbookEditResolution(
            clarification=(
                "I found multiple matching workbook rows: "
                + ", ".join(row_matches[:4])
                + ". Which one should I update?"
            )
        )
    if not row_matches:
        return WorkbookEditResolution()

    matched_label = row_matches[0]
    candidates = [
        cell
        for cell in indexed_cells
        if _normalize_for_compare(cell.row_label) == _normalize_for_compare(matched_label)
        and (
            _header_matches_semantic(cell.column_context, semantic)
            or _position_matches_semantic(cell, semantic)
        )
    ]
    if sheet_titles:
        candidates = [cell for cell in candidates if cell.sheet_title in sheet_titles]

    if not candidates:
        return WorkbookEditResolution(
            clarification=f'I found "{matched_label}" in the workbook, but not an editable field matching that request.'
        )

    return WorkbookEditResolution(
        proposals=[
            WorkbookEditProposal(
                sheet_id=cell.sheet_id,
                sheet_title=cell.sheet_title,
                cell_ref=cell.cell_ref,
                before=cell.display_value or cell.value,
                after=value,
                label=f"{cell.row_label or cell.sheet_title} {semantic.replace('_', ' ')}",
            )
            for cell in candidates
        ]
    )
