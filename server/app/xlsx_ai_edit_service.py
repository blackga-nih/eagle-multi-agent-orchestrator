"""AI-assisted XLSX editing for commercial IGCE workbooks."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from .db_client import get_s3
from .document_key_utils import (
    extract_package_document_ref,
    extract_workspace_document_ref,
    is_allowed_document_key,
)
from .package_document_store import get_document
from .igce_xlsx_edit_resolver import (
    CommercialIgceWorkbookContext,
    ResolvedEditRequest,
    build_commercial_igce_workbook_context,
    build_context_fill_intents,
    resolve_igce_edit_request,
    validate_ai_intents,
)
from .package_store import get_package
from .spreadsheet_edit_service import extract_xlsx_preview_payload, save_xlsx_preview_edits
from .tools.create_document_support import (
    _DOC_GEN_MODEL,
    _augment_document_data_from_context,
    _get_doc_gen_bedrock,
)
from .workbook_xlsx_edit_resolver import resolve_workbook_edit_request

logger = logging.getLogger("eagle.xlsx_ai_edit")

S3_BUCKET = os.getenv("S3_BUCKET", "eagle-documents-695681773636-dev")


def _build_origin_context(
    *,
    tenant_id: str,
    user_id: str,
    session_id: str | None,
    package_id: str | None,
    title: str,
    stored_source_data: dict[str, Any] | None = None,
    stored_source_context_type: str | None = None,
) -> dict[str, Any]:
    context = _augment_document_data_from_context("igce", title, {}, session_id)
    package = get_package(tenant_id, package_id) if package_id else None
    package_summary = None
    if package:
        package_summary = {
            "package_id": package.get("package_id"),
            "title": package.get("title"),
            "description": package.get("description"),
            "estimated_value": package.get("estimated_value"),
            "contract_type": package.get("contract_type"),
            "naics_code": package.get("naics_code"),
            "acquisition_pathway": package.get("acquisition_pathway"),
        }
    return {
        "session_id": session_id,
        "origin_context_available": bool(
            (session_id and context)
            or stored_source_context_type
            or stored_source_data
        ),
        "session_context": context,
        "package": package_summary,
        "source_context_type": stored_source_context_type,
        "source_data": stored_source_data or {},
    }


def _workbook_context_summary(workbook: CommercialIgceWorkbookContext) -> dict[str, Any]:
    labor_items = []
    goods_items = []
    for item in workbook.items:
        if item.kind == "labor":
            labor_items.append(
                {
                    "name": item.name,
                    "hours": item.current_hours,
                    "rate": item.current_rate,
                }
            )
        elif item.kind == "goods":
            goods_items.append(
                {
                    "name": item.name,
                    "quantity": item.current_quantity,
                    "unit_price": item.current_unit_price,
                }
            )
    return {
        "labor_items": labor_items,
        "goods_items": goods_items,
        "supported_fields": [
            "contract_type",
            "period_of_performance",
            "delivery_date",
            "labor_hours",
            "labor_rate",
            "goods_quantity",
            "goods_unit_price",
        ],
    }


def _extract_json_payload(text: str) -> dict[str, Any]:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in model output")
    return json.loads(cleaned[start : end + 1])


def _extract_intents_with_bedrock(
    *,
    request: str,
    workbook: CommercialIgceWorkbookContext,
    origin_context: dict[str, Any],
) -> ResolvedEditRequest:
    system_prompt = (
        "You convert requests about a commercial IGCE Excel workbook into safe structured edit intents.\n"
        "Return JSON only with this shape:\n"
        '{"action":"apply"|"clarify"|"unsupported","clarification":"",'
        '"intents":[{"type":"","item_name":"","value":""}]}\n'
        "Allowed intent types:\n"
        "- update_labor_rate\n"
        "- update_labor_hours\n"
        "- update_goods_quantity\n"
        "- update_goods_unit_price\n"
        "- update_contract_type\n"
        "- update_delivery_date\n"
        "- update_period_of_performance\n"
        "Rules:\n"
        "- Only use existing workbook item names.\n"
        "- Do not invent rows.\n"
        "- Do not return formula edits.\n"
        "- If the request is ambiguous, or the context is insufficient, return action=clarify.\n"
        "- If the request asks for unsupported layout or formula changes, return action=unsupported.\n"
    )

    user_prompt = json.dumps(
        {
            "request": request,
            "workbook": _workbook_context_summary(workbook),
            "origin_context": origin_context,
        },
        default=str,
        indent=2,
    )

    try:
        response = _get_doc_gen_bedrock().converse(
            modelId=_DOC_GEN_MODEL,
            system=[{"text": system_prompt}],
            messages=[{"role": "user", "content": [{"text": user_prompt}]}],
            inferenceConfig={"maxTokens": 1200, "temperature": 0},
        )
        text = response["output"]["message"]["content"][0]["text"]
        payload = _extract_json_payload(text)
    except Exception as exc:  # noqa: BLE001
        logger.warning("XLSX intent extraction failed: %s", exc)
        return ResolvedEditRequest()

    action = str(payload.get("action", "")).strip().lower()
    clarification = str(payload.get("clarification", "")).strip()
    if action in {"clarify", "unsupported"}:
        return ResolvedEditRequest(
            clarification=clarification or "I need a more specific IGCE edit request before I can update the workbook."
        )

    intents = payload.get("intents")
    if not isinstance(intents, list):
        return ResolvedEditRequest()
    return validate_ai_intents(intents, workbook)


def _upsert_cell_edit(
    proposals: dict[str, dict[str, str]],
    applied_changes: list[dict[str, str]],
    *,
    sheet_id: str | None,
    cell_ref: str | None,
    before: str | None,
    after: str | None,
    label: str,
) -> None:
    if not sheet_id or not cell_ref or after is None:
        return
    normalized_after = str(after)
    normalized_before = str(before or "")
    if normalized_after == normalized_before:
        return
    key = f"{sheet_id}:{cell_ref}"
    proposals[key] = {"sheet_id": sheet_id, "cell_ref": cell_ref, "value": normalized_after}
    applied_changes.append(
        {
            "sheet_id": sheet_id,
            "cell_ref": cell_ref,
            "before": normalized_before,
            "after": normalized_after,
            "label": label,
        }
    )


def _apply_resolved_intents(
    workbook: CommercialIgceWorkbookContext,
    resolved: ResolvedEditRequest,
) -> tuple[list[dict[str, str]], list[dict[str, str]], str | None]:
    proposals: dict[str, dict[str, str]] = {}
    applied_changes: list[dict[str, str]] = []

    def add(item_label: str, binding, value: str) -> None:
        if not binding:
            return
        _upsert_cell_edit(
            proposals,
            applied_changes,
            sheet_id=binding.sheet_id,
            cell_ref=binding.cell_ref,
            before=binding.display_value or binding.value,
            after=value,
            label=item_label,
        )

    item_lookup = {item.name: item for item in workbook.items}

    for intent in resolved.intents:
        if intent.intent_type == "update_contract_type":
            add("Contract Type", workbook.fields.services_contract_type, intent.value)
            add("Contract Type", workbook.fields.goods_contract_type, intent.value)
            continue
        if intent.intent_type == "update_period_of_performance":
            add("Period of Performance", workbook.fields.summary_period, intent.value)
            continue
        if intent.intent_type == "update_delivery_date":
            add("Delivery Date", workbook.fields.goods_delivery_date, intent.value)
            continue

        item = item_lookup.get(intent.item_name or "")
        if not item:
            return [], [], f'I could not match "{intent.item_name}" to a workbook row.'

        if intent.intent_type == "update_labor_rate":
            add(f"{item.name} rate", item.summary_rate, intent.value)
            add(f"{item.name} rate", item.services_rate, intent.value)
            continue
        if intent.intent_type == "update_labor_hours":
            add(f"{item.name} hours", item.summary_hours, intent.value)
            add(f"{item.name} hours", item.services_hours, intent.value)
            continue
        if intent.intent_type == "update_goods_quantity":
            add(f"{item.name} quantity", item.goods_quantity, intent.value)
            try:
                quantity = float(intent.value)
            except ValueError:
                return [], [], f'I could not parse "{intent.value}" as a quantity for "{item.name}".'
            unit_price = item.current_unit_price
            if unit_price is not None and item.summary_total:
                total = quantity * unit_price
                add(f"{item.name} total", item.summary_total, str(round(total, 2)))
            continue
        if intent.intent_type == "update_goods_unit_price":
            add(f"{item.name} unit price", item.goods_unit_price, intent.value)
            try:
                unit_price = float(intent.value)
            except ValueError:
                return [], [], f'I could not parse "{intent.value}" as a unit price for "{item.name}".'
            quantity = item.current_quantity
            if quantity is not None and item.summary_total:
                total = quantity * unit_price
                add(f"{item.name} total", item.summary_total, str(round(total, 2)))
            continue

    return list(proposals.values()), applied_changes, None


def _format_assistant_message(
    *,
    applied_changes: list[dict[str, str]],
    skipped_fields: list[dict[str, str]] | None = None,
    clarification: str | None = None,
    fallback: str = "",
) -> str:
    if clarification:
        return clarification
    if not applied_changes:
        return fallback or "No workbook changes were needed."
    lines = []
    for change in applied_changes[:6]:
        lines.append(
            f'Updated {change["label"]} ({change["cell_ref"]}) from {change["before"] or "[blank]"} to {change["after"]}.'
        )
    if len(applied_changes) > 6:
        lines.append(f"Updated {len(applied_changes) - 6} more workbook cells.")

    # Report skipped fields if any
    if skipped_fields:
        not_in_context = [s for s in skipped_fields if s.get("reason") == "not in context"]
        no_match = [s for s in skipped_fields if s.get("reason") == "could not match to workbook row"]

        if not_in_context and len(not_in_context) <= 3:
            field_names = ", ".join(s["field"] for s in not_in_context)
            lines.append(f"Could not determine: {field_names}.")
        if no_match:
            field_names = ", ".join(s["field"] for s in no_match[:3])
            lines.append(f"Could not match to workbook: {field_names}.")

    return " ".join(lines)


def _proposals_to_edits(
    proposals: list[Any],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    cell_edits: list[dict[str, str]] = []
    applied_changes: list[dict[str, str]] = []
    for proposal in proposals:
        cell_edits.append(
            {
                "sheet_id": proposal.sheet_id,
                "cell_ref": proposal.cell_ref,
                "value": proposal.after,
            }
        )
        applied_changes.append(
            {
                "sheet_id": proposal.sheet_id,
                "cell_ref": proposal.cell_ref,
                "before": proposal.before,
                "after": proposal.after,
                "label": proposal.label,
            }
        )
    return cell_edits, applied_changes


def edit_igce_xlsx_document(
    *,
    tenant_id: str,
    user_id: str,
    doc_key: str,
    request_text: str,
    session_id: str | None = None,
    package_id: str | None = None,
    change_source: str = "ai_edit",
) -> dict[str, Any]:
    if not doc_key:
        return {"error": "document_key is required"}
    if not request_text.strip():
        return {"error": "request is required"}
    if not doc_key.lower().endswith(".xlsx"):
        return {"error": "Only .xlsx documents are supported"}
    if not is_allowed_document_key(doc_key, tenant_id, user_id):
        return {"error": "Access denied for document key"}

    package_ref = extract_package_document_ref(doc_key)
    workspace_ref = extract_workspace_document_ref(doc_key)
    if package_ref and str(package_ref.get("doc_type")) != "igce":
        return {
            "success": True,
            "clarification_needed": True,
            "assistant_message": "This AI spreadsheet edit path currently supports only commercial IGCE workbooks.",
        }
    if not package_ref and not workspace_ref:
        return {
            "success": True,
            "clarification_needed": True,
            "assistant_message": "This AI spreadsheet edit path currently supports only commercial IGCE workbooks.",
        }

    try:
        s3 = get_s3()
        response = s3.get_object(Bucket=S3_BUCKET, Key=doc_key)
        xlsx_bytes = response["Body"].read()
    except (ClientError, BotoCoreError) as exc:
        logger.error("Failed to load XLSX AI edit source: %s", exc, exc_info=True)
        return {"error": "Failed to load spreadsheet."}

    preview_payload = extract_xlsx_preview_payload(xlsx_bytes)
    workbook = build_commercial_igce_workbook_context(preview_payload.get("preview_sheets", []))
    if not workbook.is_supported:
        return {
            "success": True,
            "clarification_needed": True,
            "assistant_message": "I can only apply chat edits to the commercial IGCE workbook layout right now.",
        }

    if package_ref:
        doc = get_document(
            tenant_id,
            str(package_ref["package_id"]),
            str(package_ref["doc_type"]),
            int(package_ref["version"]),
        )
        effective_package_id = package_id or str(package_ref["package_id"])
    else:
        from .user_document_store import find_document_by_s3_key

        doc = find_document_by_s3_key(tenant_id, user_id, doc_key)
        effective_package_id = package_id or (doc or {}).get("package_id")

    if workspace_ref and doc and str(doc.get("doc_type", "")).lower() != "igce":
        return {
            "success": True,
            "clarification_needed": True,
            "assistant_message": "This AI spreadsheet edit path currently supports only commercial IGCE workbooks.",
        }

    effective_session_id = session_id or (doc or {}).get("session_id")
    title = (doc or {}).get("title") or "IGCE"
    origin_context = _build_origin_context(
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=effective_session_id,
        package_id=effective_package_id,
        title=title,
        stored_source_data=(doc or {}).get("source_data"),
        stored_source_context_type=(doc or {}).get("source_context_type"),
    )

    preview_sheets = preview_payload.get("preview_sheets", [])
    resolved = resolve_igce_edit_request(request_text, workbook)
    fallback_clarification = resolved.clarification
    skipped_fields: list[dict[str, str]] = []
    generic_cell_edits: list[dict[str, str]] = []
    generic_applied_changes: list[dict[str, str]] = []

    # Handle context-fill requests: "fill from context", "complete the IGCE", etc.
    if resolved.is_context_fill_request:
        source_data = (doc or {}).get("source_data")
        if not source_data:
            return {
                "success": True,
                "clarification_needed": True,
                "assistant_message": "I don't have enough context from the original conversation to auto-fill this workbook. Please specify what values to update.",
                "origin_context_available": origin_context.get("origin_context_available", False),
                "skipped_fields": [{"field": "all", "reason": "No origin context available"}],
            }
        context_fill_result = build_context_fill_intents(source_data, workbook)
        if context_fill_result.intents:
            resolved = ResolvedEditRequest(intents=context_fill_result.intents)
            skipped_fields = context_fill_result.skipped_fields
        else:
            return {
                "success": True,
                "clarification_needed": True,
                "assistant_message": "The workbook already has values filled in, or I couldn't match the context data to empty cells. Try specifying what to update directly.",
                "origin_context_available": True,
                "skipped_fields": context_fill_result.skipped_fields,
            }
    elif not resolved.intents:
        ai_resolved = _extract_intents_with_bedrock(
            request=request_text,
            workbook=workbook,
            origin_context=origin_context,
        )
        if ai_resolved.intents or ai_resolved.clarification:
            resolved = ai_resolved
        elif fallback_clarification:
            resolved = ResolvedEditRequest(clarification=fallback_clarification)

    if not resolved.intents and not resolved.is_context_fill_request:
        generic_resolution = resolve_workbook_edit_request(request_text, preview_sheets)
        if generic_resolution.proposals:
            generic_cell_edits, generic_applied_changes = _proposals_to_edits(
                generic_resolution.proposals
            )
            resolved = ResolvedEditRequest()
        elif generic_resolution.clarification:
            return {
                "success": True,
                "clarification_needed": True,
                "assistant_message": generic_resolution.clarification,
                "origin_context_available": origin_context.get("origin_context_available", False),
            }

    if resolved.clarification:
        return {
            "success": True,
            "clarification_needed": True,
            "assistant_message": resolved.clarification,
            "origin_context_available": origin_context.get("origin_context_available", False),
        }

    if generic_cell_edits:
        cell_edits = generic_cell_edits
        applied_changes = generic_applied_changes
    else:
        cell_edits, applied_changes, resolution_error = _apply_resolved_intents(workbook, resolved)
        if resolution_error:
            return {
                "success": True,
                "clarification_needed": True,
                "assistant_message": resolution_error,
                "origin_context_available": origin_context.get("origin_context_available", False),
            }
        if not cell_edits:
            return {
                "success": True,
                "clarification_needed": True,
                "assistant_message": "I could not translate that request into editable workbook changes.",
                "origin_context_available": origin_context.get("origin_context_available", False),
            }

    save_result = save_xlsx_preview_edits(
        tenant_id=tenant_id,
        user_id=user_id,
        doc_key=doc_key,
        cell_edits=cell_edits,
        session_id=effective_session_id,
        change_source=change_source,
    )
    if save_result.get("error"):
        return {"error": save_result["error"]}

    return {
        **save_result,
        "assistant_message": _format_assistant_message(
            applied_changes=applied_changes,
            skipped_fields=skipped_fields if skipped_fields else None,
            fallback=save_result.get("message", "Spreadsheet updated."),
        ),
        "applied_changes": applied_changes,
        "skipped_fields": skipped_fields,
        "clarification_needed": False,
        "origin_context_available": origin_context.get("origin_context_available", False),
        "session_id": effective_session_id,
        "package_id": effective_package_id,
    }
