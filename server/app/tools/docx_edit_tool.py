"""Active DOCX edit tool handler."""

from __future__ import annotations

from ..session_scope import extract_user_id


def exec_edit_docx_document(
    params: dict, tenant_id: str, session_id: str | None = None
) -> dict:
    """Apply targeted edits to an existing DOCX document."""
    from app.document_ai_edit_service import (
        DocxCheckboxEdit,
        DocxEdit,
        edit_docx_document,
    )

    doc_key = params.get("document_key", "")
    edits_input = params.get("edits") or []
    checkbox_edits_input = params.get("checkbox_edits") or []
    if edits_input and not isinstance(edits_input, list):
        return {"error": "edits must be an array"}
    if checkbox_edits_input and not isinstance(checkbox_edits_input, list):
        return {"error": "checkbox_edits must be an array"}
    if not edits_input and not checkbox_edits_input:
        return {"error": "Provide edits or checkbox_edits"}

    edits: list[DocxEdit] = []
    for idx, edit in enumerate(edits_input, start=1):
        if not isinstance(edit, dict):
            return {"error": f"edit #{idx} must be an object"}
        search_text = str(edit.get("search_text", "") or "").strip()
        replacement_text = str(edit.get("replacement_text", "") or "")
        if not search_text:
            return {"error": f"edit #{idx} is missing search_text"}
        edits.append(
            DocxEdit(search_text=search_text, replacement_text=replacement_text)
        )

    checkbox_edits: list[DocxCheckboxEdit] = []
    for idx, edit in enumerate(checkbox_edits_input, start=1):
        if not isinstance(edit, dict):
            return {"error": f"checkbox_edit #{idx} must be an object"}
        label_text = str(edit.get("label_text", "") or "").strip()
        checked = edit.get("checked")
        if not label_text:
            return {"error": f"checkbox_edit #{idx} is missing label_text"}
        if not isinstance(checked, bool):
            return {"error": f"checkbox_edit #{idx} must provide boolean checked"}
        checkbox_edits.append(DocxCheckboxEdit(label_text=label_text, checked=checked))

    return edit_docx_document(
        tenant_id=tenant_id,
        user_id=extract_user_id(session_id),
        doc_key=doc_key,
        edits=edits,
        checkbox_edits=checkbox_edits,
        session_id=session_id,
        change_source="ai_edit",
    )
