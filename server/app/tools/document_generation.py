"""Active document generation boundary for ``create_document``.

This module owns the active create-document execution path. Shared document
generation helpers now live in ``create_document_support.py`` so active callers
do not import behavior from the deprecated ``agentic_service`` monolith.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from .create_document_support import (
    _apply_sow_clear_edits,
    _append_provenance_metadata,
    _augment_document_data_from_context,
    _default_output_format_for_doc_type,
    _generate_acquisition_plan,
    _generate_contract_type_justification,
    _generate_cor_certification,
    _generate_eval_criteria,
    _generate_igce,
    _generate_justification,
    _generate_market_research,
    _generate_section_508,
    _generate_security_checklist,
    _generate_sow,
    get_s3,
    _looks_like_unfilled_template_preview,
    _normalize_create_document_doc_type,
    _update_document_content,
    logger,
)
from ..session_scope import extract_user_id


def exec_create_document(params: dict[str, Any], tenant_id: str, session_id: str | None = None) -> dict:
    """Generate acquisition documents and save to S3.

    Uses official S3 templates when available (DOCX/XLSX), falling back to
    markdown generators when templates are unavailable or fail to load.

    If `update_existing_key` is provided, updates the existing document instead
    of creating a new one.
    """
    from app.template_service import TemplateService
    from app.template_registry import normalize_field_names

    update_key = params.get("update_existing_key")
    if update_key:
        return _update_document_content(
            tenant_id=tenant_id,
            doc_key=update_key,
            content=params.get("data", {}).get("content", ""),
            change_source="ai_edit",
            session_id=session_id,
        )

    title = params.get("title", "Untitled Acquisition")
    doc_type = _normalize_create_document_doc_type(params.get("doc_type"), title)
    raw_data = params.get("data", {})
    if isinstance(raw_data, str):
        try:
            raw_data = json.loads(raw_data)
        except (json.JSONDecodeError, TypeError):
            raw_data = {}
    data = raw_data if isinstance(raw_data, dict) else {}
    ai_content = params.get("content")
    package_id = params.get("package_id")
    output_format = params.get("output_format") or _default_output_format_for_doc_type(doc_type)
    timestamp = time.strftime("%Y%m%d_%H%M%S")

    data = _augment_document_data_from_context(doc_type, title, data, session_id)
    data = normalize_field_names(data, doc_type)

    inline_edited_content: str | None = None
    if doc_type == "sow":
        current_content = data.get("current_content")
        edit_request = str(data.get("edit_request", "") or "")
        if isinstance(current_content, str) and edit_request:
            inline_edited_content = _apply_sow_clear_edits(current_content, edit_request)

    valid_doc_types = {
        "sow", "igce", "market_research", "justification", "acquisition_plan",
        "eval_criteria", "security_checklist", "section_508", "cor_certification",
        "contract_type_justification",
    }
    if doc_type not in valid_doc_types:
        return {"error": f"Unknown document type: {doc_type}. Supported: {', '.join(sorted(valid_doc_types))}."}

    markdown_generators = {
        "sow": _generate_sow,
        "igce": _generate_igce,
        "market_research": _generate_market_research,
        "justification": _generate_justification,
        "acquisition_plan": _generate_acquisition_plan,
        "eval_criteria": _generate_eval_criteria,
        "security_checklist": _generate_security_checklist,
        "section_508": _generate_section_508,
        "cor_certification": _generate_cor_certification,
        "contract_type_justification": _generate_contract_type_justification,
    }

    user_id = extract_user_id(session_id)

    if inline_edited_content is not None:
        content = inline_edited_content
        file_type = "md"
        source = "inline_edit_clear_sections"
        template_path = None
        result = None
    elif ai_content and isinstance(ai_content, str) and ai_content.strip():
        content = ai_content.strip()
        file_type = "md"
        source = "ai_content"
        template_path = None
        result = None

        try:
            service = TemplateService(tenant_id, user_id, markdown_generators)
            template_result = service.generate_document(doc_type, title, data, output_format)
            if template_result.success:
                preview = template_result.preview or ""
                if not _looks_like_unfilled_template_preview(doc_type, preview):
                    file_type = template_result.file_type
                    source = "ai_content+s3_template"
                    template_path = template_result.template_path
                    result = template_result
                else:
                    logger.info(
                        "Template still unfilled after population for %s; using AI content",
                        doc_type,
                    )
        except Exception:
            logger.debug("Template population alongside AI content failed, using AI markdown")
    else:
        try:
            service = TemplateService(tenant_id, user_id, markdown_generators)
            result = service.generate_document(doc_type, title, data, output_format)

            if not result.success:
                generator = markdown_generators.get(doc_type)
                if generator:
                    content = generator(title, data)
                    file_type = "md"
                    source = "markdown_fallback"
                    template_path = None
                else:
                    return {"error": f"No generator available for {doc_type}: {result.error}"}
            else:
                file_type = result.file_type
                source = result.source
                template_path = result.template_path

                if _looks_like_unfilled_template_preview(doc_type, result.preview or ""):
                    generator = markdown_generators.get(doc_type)
                    if generator:
                        content = generator(title, data)
                        source = f"{source}+markdown_context_response"
                        file_type = "md"
                        result = None
                        logger.warning(
                            "Template preview unfilled for doc_type=%s; using markdown generator and saving markdown to S3",
                            doc_type,
                        )
                else:
                    generator = markdown_generators.get(doc_type)
                    if generator and file_type in ("docx", "xlsx"):
                        try:
                            content = generator(title, data)
                            logger.info(
                                "Using markdown generator for display content (%s); DOCX saved to S3",
                                doc_type,
                            )
                        except Exception:
                            content = result.preview or ""
                    else:
                        content = result.preview or ""

        except ImportError as exc:
            logger.warning("Template libraries unavailable: %s, using markdown fallback", exc)
            generator = markdown_generators.get(doc_type)
            if generator:
                content = generator(title, data)
                file_type = "md"
                source = "markdown_fallback"
                template_path = None
                result = None
            else:
                return {"error": f"No generator available for {doc_type}"}

    ext = file_type if file_type in ("docx", "xlsx") else "md"
    bucket = os.getenv("S3_BUCKET", "eagle-documents-695681773636-dev")
    content_to_store = (
        result.content if result and result.success and file_type in ("docx", "xlsx")
        else content
    )

    template_provenance = None
    effective_template_id = params.get("template_id") or template_path
    if effective_template_id:
        template_provenance = {
            "template_id": effective_template_id,
            "template_source": source,
            "template_version": 1,
            "template_name": title,
            "doc_type": doc_type,
        }
        if result and hasattr(result, "template_path") and result.template_path:
            template_provenance["template_id"] = result.template_path

    # Inject provenance metadata section into markdown content
    content = _append_provenance_metadata(
        content,
        template_provenance,
        source,
        datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    )
    # Update content_to_store for markdown files (DOCX/XLSX use result.content binary)
    if not (result and result.success and file_type in ("docx", "xlsx")):
        content_to_store = content

    if package_id:
        from app.document_service import create_package_document_version

        canonical = create_package_document_version(
            tenant_id=tenant_id,
            package_id=package_id,
            doc_type=doc_type,
            content=content_to_store,
            title=title,
            file_type=ext,
            created_by_user_id=user_id,
            session_id=session_id,
            change_source="agent_tool",
            template_id=effective_template_id,
            template_provenance=template_provenance,
        )
        if not canonical.success:
            return {"error": canonical.error or "Failed to create package document"}

        response = {
            "mode": "package",
            "package_id": package_id,
            "document_id": canonical.document_id,
            "doc_type": doc_type,
            "document_type": doc_type,
            "version": canonical.version,
            "status": canonical.status or "draft",
            "s3_key": canonical.s3_key,
            "s3_location": f"s3://{bucket}/{canonical.s3_key}",
            "file_type": ext,
            "source": source,
            "title": title,
            "content": content,
            "word_count": len(content.split()),
            "generated_at": datetime.utcnow().isoformat(),
            "note": "This is a draft document. Review and customize before official use.",
        }
        if template_path:
            response["template_path"] = template_path
        return response

    s3_key = f"eagle/{tenant_id}/{user_id}/documents/{doc_type}_{timestamp}.{ext}"

    try:
        s3 = get_s3()
        if isinstance(content_to_store, bytes):
            s3.put_object(
                Bucket=bucket,
                Key=s3_key,
                Body=content_to_store,
                ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                if file_type == "docx"
                else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            if content and isinstance(content, str):
                try:
                    s3.put_object(
                        Bucket=bucket,
                        Key=f"{s3_key}.content.md",
                        Body=content.encode("utf-8"),
                        ContentType="text/markdown",
                    )
                except Exception:
                    logger.debug("Failed to save markdown sidecar for %s", s3_key)
        else:
            s3.put_object(Bucket=bucket, Key=s3_key, Body=content_to_store.encode("utf-8"))
        save_status = "saved"
        save_location = f"s3://{bucket}/{s3_key}"
    except (ClientError, BotoCoreError) as exc:
        save_status = "generated_but_not_saved"
        save_location = f"S3 save failed: {str(exc)}"
        logger.warning("Failed to save document to S3: %s", exc)

    if save_status == "saved":
        try:
            from app.changelog_store import write_document_changelog_entry

            write_document_changelog_entry(
                tenant_id=tenant_id,
                document_key=s3_key,
                change_type="create",
                change_source="agent_tool",
                change_summary=f"Created {doc_type}: {title}",
                actor_user_id=user_id,
                doc_type=doc_type,
                session_id=session_id,
            )
        except Exception as exc:
            logger.warning("Failed to write changelog for document creation: %s", exc)

    response = {
        "document_type": doc_type,
        "title": title,
        "status": save_status,
        "s3_location": save_location,
        "s3_key": s3_key,
        "file_type": file_type,
        "source": source,
        "content": content,
        "word_count": len(content.split()),
        "generated_at": datetime.utcnow().isoformat(),
        "note": "This is a draft document. Review and customize before official use.",
    }

    if template_path:
        response["template_path"] = template_path

    return response
