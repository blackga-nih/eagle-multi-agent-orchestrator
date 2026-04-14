"""Active document generation boundary for ``create_document``.

This module owns the active create-document execution path. Shared document
generation helpers live in ``create_document_support.py``.
"""

from __future__ import annotations

import json
import os
import re
import time
import hashlib
from datetime import datetime
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from .create_document_support import (
    _DOC_TYPE_LABELS,
    _apply_sow_clear_edits,
    _augment_document_data_from_context,
    _default_output_format_for_doc_type,
    _generate_acquisition_plan,
    _generate_buy_american,
    _generate_contract_type_justification,
    _generate_cor_certification,
    _generate_eval_criteria,
    _generate_igce,
    _generate_justification,
    _generate_market_research,
    _generate_price_reasonableness,
    _generate_purchase_request,
    _generate_pws,
    _generate_required_sources,
    _generate_section_508,
    _generate_security_checklist,
    _generate_son_products,
    _generate_son_services,
    _generate_sow,
    _generate_subk_plan,
    _generate_subk_review,
    get_s3,
    _looks_like_unfilled_template_preview,
    _update_document_content,
    logger,
)
from ..session_scope import extract_user_id
from ..ai_document_schema import (
    normalize_and_validate_document_payload,
    get_create_document_types,
    normalize_doc_type,
)


_LOW_SIGNAL_TITLE_CONTEXT_RE = re.compile(
    r"\b(attached|uploaded|using|use|take a look|review|see)\b.*\b(document|file|attachment)\b"
    r"|\b(this|that)\s+(document|file|attachment)\b"
    r"|\bgenerate\b.*\busing that document\b",
    re.IGNORECASE,
)


def _is_low_signal_title_context(text: str) -> bool:
    cleaned = (text or "").strip()
    if not cleaned:
        return True
    if len(cleaned) < 8:
        return True
    return bool(_LOW_SIGNAL_TITLE_CONTEXT_RE.search(cleaned))


def _title_from_context(title: str, doc_type: str, data: dict) -> str:
    """Enrich a fallback title using session context from enriched data.

    Replaces bare fallback titles (doc-type label + package ID or date) with
    a descriptive title derived from session context when available. Leaves
    agent-generated titles untouched.
    """
    base_label = _DOC_TYPE_LABELS.get(doc_type, "")
    if not base_label:
        return title

    # Only override fallback titles, which start with the full doc-type label.
    # LLM-generated titles like "SOW - Cloud Hosting Services" won't match.
    if not title.startswith(base_label):
        return title

    # If the title already has a meaningful descriptive suffix (>10 chars),
    # keep it. Only enrich bare labels or short suffixes.
    after_label = title[len(base_label):].strip()
    if after_label.startswith("- "):
        existing_suffix = after_label[2:].strip()
        if len(existing_suffix) > 10:
            return title
    elif after_label:
        return title

    # Pull the best available context string from enriched session data
    context = ""
    for key in ("description", "requirement", "objective"):
        candidate = str(data.get(key, "")).strip()
        if candidate and len(candidate) > 8:
            context = candidate
            break

    if not context or _is_low_signal_title_context(context):
        return title

    # Trim to the first sentence
    for stop_char in (".", "\n", ";"):
        pos = context.find(stop_char)
        if 0 < pos < 100:
            context = context[:pos]
            break
    context = context[:80].strip().rstrip(",").strip()

    if len(context) <= 5:
        return title

    return f"{base_label} - {context}"


# Polite-phrase prefix is REQUIRED — without it, legitimate titles whose
# descriptive suffix happens to start with a "verb" word (e.g. "Statement of
# Work - Draft for NIH Cloud Hosting") were being wrongly stripped to just
# "Statement of Work". Requiring a polite phrase (can you / please / help me /
# i need to / i want to / i'd like to) means only actual prompt fragments
# match.
_PROMPT_FRAGMENT_TITLE_RE = re.compile(
    r"^(.*?)\s*-\s*"
    r"(?:can you |could you |please |help me |i need(?: you)? to |i want to |i'd like to )"
    r"(?:help\s+(?:me\s+)?)?(?:create|generate|draft|write|produce|make|build|prepare)"
    r"\b.*$",
    re.IGNORECASE,
)


def _sanitize_title(title: str, doc_type: str) -> str:
    """Strip raw user prompt fragments from document titles.

    Catches titles like "Statement of Work - can you help me create an sow"
    and returns just "Statement of Work".  Leaves meaningful titles like
    "Statement of Work - Cloud Hosting Services" or "Statement of Work -
    Draft for NIH" untouched (the polite-phrase prefix on the regex is
    what distinguishes prompt fragments from real descriptive suffixes).
    """
    if not title:
        return title
    m = _PROMPT_FRAGMENT_TITLE_RE.match(title)
    if m:
        base = m.group(1).strip()
        return base or _DOC_TYPE_LABELS.get(doc_type, doc_type.replace("_", " ").title())
    return title


def exec_create_document(
    params: dict[str, Any], tenant_id: str, session_id: str | None = None
) -> dict:
    """Generate acquisition documents and save to S3.

    Uses official S3 templates when available (DOCX/XLSX), falling back to
    markdown generators when templates are unavailable or fail to load.

    If `update_existing_key` is provided, updates the existing document instead
    of creating a new one.
    """
    from app.template_service import TemplateService

    update_key = params.get("update_existing_key")
    if update_key:
        return _update_document_content(
            tenant_id=tenant_id,
            doc_key=update_key,
            content=params.get("content") or params.get("data", {}).get("content", ""),
            change_source="ai_edit",
            session_id=session_id,
        )

    title = params.get("title") or ""
    # Initial doc_type normalization (canonical schema handles full validation later)
    doc_type = normalize_doc_type(params.get("doc_type") or "")
    raw_data = params.get("data", {})
    if isinstance(raw_data, str):
        try:
            raw_data = json.loads(raw_data)
        except (json.JSONDecodeError, TypeError):
            raw_data = {}
    data = raw_data if isinstance(raw_data, dict) else {}
    ai_content = params.get("content")
    package_id = params.get("package_id")
    output_format = params.get("output_format") or _default_output_format_for_doc_type(
        doc_type
    )
    timestamp = time.strftime("%Y%m%d_%H%M%S")

    # Augment data from session context
    data = _augment_document_data_from_context(doc_type, title, data, session_id)

    # Canonical schema validation and normalization (Phase 1 of schema propagation)
    canonical_payload = normalize_and_validate_document_payload(
        raw_doc_type=doc_type,
        title=title,
        data=data,
    )
    doc_type = canonical_payload.doc_type
    data = canonical_payload.data

    # Code-level checklist guardrail. The supervisor prompt tells the agent to
    # consult the PMR checklist before calling create_document, but a pure
    # prompt-level rule is easy to ignore. Check here too so the system fails
    # fast with a structured error if a non-required doc_type is requested,
    # or warns if the doc is already completed (agent should use update_existing_key
    # for revisions instead of creating a duplicate). Only runs when package_id
    # is provided — session-mode documents (no package) are unaffected.
    if package_id:
        try:
            from app.package_store import get_package_checklist

            checklist = get_package_checklist(tenant_id, package_id)
            required = set(checklist.get("required", []) or [])
            completed_set = set(checklist.get("completed", []) or [])

            # Requirements-document companion pairs: PWS and SOW serve the same
            # checklist role (both are the "requirements document" — one
            # performance-based, the other task-based). If the checklist lists
            # one and the user explicitly asks for the other, treat the request
            # as satisfying the requirement so the guardrail does not hard-block.
            # The supervisor prompt has a separate rule telling the agent to
            # pick whichever the user explicitly asked for.
            _DOC_TYPE_COMPANIONS: dict[str, str] = {"pws": "sow", "sow": "pws"}
            companion = _DOC_TYPE_COMPANIONS.get(doc_type)
            companion_satisfies_required = bool(
                companion and companion in required
            )
            companion_in_completed = bool(
                companion and companion in completed_set
            )

            # Not on the required checklist → hard error with list to guide the agent.
            if (
                required
                and doc_type not in required
                and doc_type not in completed_set
                and not companion_satisfies_required
                and not companion_in_completed
            ):
                logger.info(
                    "Checklist guardrail blocked %s for package %s — not in required list",
                    doc_type,
                    package_id,
                )
                return {
                    "error": (
                        f"doc_type '{doc_type}' is not in the required checklist "
                        f"for package {package_id}. Call manage_package("
                        f"operation='checklist', package_id='{package_id}') to see "
                        "the required documents, then only generate documents "
                        "on that list."
                    ),
                    "required": sorted(required),
                    "completed": sorted(completed_set),
                }

            # Already completed → warn and point the agent at update_existing_key.
            # Does not block — lets the agent proceed if the user explicitly
            # asked to regenerate (agent will see the warning in its tool result
            # and should surface it to the user before redoing the work).
            if doc_type in completed_set:
                existing_key: str | None = None
                try:
                    from app.package_document_store import get_document as _get_doc

                    existing = _get_doc(tenant_id, package_id, doc_type, version=None)
                    if existing:
                        existing_key = existing.get("s3_key")
                except Exception:
                    existing_key = None
                logger.info(
                    "Checklist guardrail: %s already completed for package %s (existing=%s)",
                    doc_type,
                    package_id,
                    existing_key,
                )
                data["_checklist_warning"] = (
                    f"'{doc_type}' is already marked complete in the checklist. "
                    "If the user wants to revise the existing document, call "
                    "create_document again with update_existing_key set to the "
                    "existing s3_key instead of creating a duplicate."
                )
                if existing_key:
                    data["_existing_s3_key"] = existing_key
        except Exception:
            logger.debug("Checklist guardrail check failed (non-fatal)", exc_info=True)

    # Log and emit telemetry for schema normalization (Phase 6 observability)
    if canonical_payload.warnings:
        logger.warning(
            "Document payload warnings: %s", canonical_payload.warnings
        )
    if canonical_payload.normalized_aliases:
        logger.info(
            "Document payload normalized: %s", canonical_payload.normalized_aliases
        )

    # Emit telemetry for schema drift analysis
    if canonical_payload.normalized_aliases or canonical_payload.warnings or canonical_payload.unknown_fields:
        try:
            from app.telemetry.cloudwatch_emitter import emit_telemetry_event
            emit_telemetry_event(
                event_type="schema.normalized",
                tenant_id=tenant_id,
                session_id=session_id,
                data={
                    "doc_type": doc_type,
                    "original_doc_type": params.get("doc_type"),
                    "normalized_aliases": canonical_payload.normalized_aliases,
                    "warnings": canonical_payload.warnings,
                    "unknown_fields": canonical_payload.unknown_fields,
                    "alias_count": len(canonical_payload.normalized_aliases),
                    "warning_count": len(canonical_payload.warnings),
                    "unknown_field_count": len(canonical_payload.unknown_fields),
                },
            )
        except Exception as e:
            logger.debug("Schema telemetry emission failed: %s", e)

    # For IGCE XLSX, extract structured workbook data (line items, goods, etc.)
    if doc_type == "igce" and output_format == "xlsx":
        from app.igce_generation_extractor import extract_igce_generation_data
        data = extract_igce_generation_data(data, session_id)

    # Extract template_hint before passing data to template service — the
    # compliance matrix injects this for value-aware template selection
    # (e.g. simplified J&A under SAT vs full J&A over SAT).
    template_hint = data.pop("template_hint", None)

    # If session context provided a richer description than the prompt-derived
    # title, rebuild the title from it.  Before the fast-path was introduced
    # (commit b654a49), the LLM generated titles using the full conversation
    # context.  This restores that behaviour for the fast-path.
    title = _title_from_context(title, doc_type, data)
    title = _sanitize_title(title, doc_type)
    if not title:
        title = _DOC_TYPE_LABELS.get(doc_type, "") or doc_type.replace("_", " ").title() or "Acquisition Document"

    inline_edited_content: str | None = None
    if doc_type == "sow":
        current_content = data.get("current_content")
        edit_request = str(data.get("edit_request", "") or "")
        if isinstance(current_content, str) and edit_request:
            inline_edited_content = _apply_sow_clear_edits(
                current_content, edit_request
            )

    # Use canonical schema for valid doc_types (Phase 1 of schema propagation)
    valid_doc_types = get_create_document_types()
    if doc_type not in valid_doc_types:
        return {
            "error": f"Unknown document type: {doc_type}. Supported: {', '.join(sorted(valid_doc_types))}."
        }

    markdown_generators = {
        "sow": _generate_sow,
        "pws": _generate_pws,
        "igce": _generate_igce,
        "market_research": _generate_market_research,
        "justification": _generate_justification,
        "acquisition_plan": _generate_acquisition_plan,
        "eval_criteria": _generate_eval_criteria,
        "security_checklist": _generate_security_checklist,
        "section_508": _generate_section_508,
        "cor_certification": _generate_cor_certification,
        "contract_type_justification": _generate_contract_type_justification,
        "son_products": _generate_son_products,
        "son_services": _generate_son_services,
        "purchase_request": _generate_purchase_request,
        "price_reasonableness": _generate_price_reasonableness,
        "required_sources": _generate_required_sources,
        "subk_plan": _generate_subk_plan,
        "subk_review": _generate_subk_review,
        "buy_american": _generate_buy_american,
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
            template_result = service.generate_document(
                doc_type, title, data, output_format, template_hint=template_hint
            )
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
            logger.debug(
                "Template population alongside AI content failed, using AI markdown"
            )
    else:
        try:
            service = TemplateService(tenant_id, user_id, markdown_generators)
            result = service.generate_document(doc_type, title, data, output_format, template_hint=template_hint)

            if not result.success:
                generator = markdown_generators.get(doc_type)
                if generator:
                    content = generator(title, data)
                    file_type = "md"
                    source = "markdown_fallback"
                    template_path = None
                else:
                    return {
                        "error": f"No generator available for {doc_type}: {result.error}"
                    }
            else:
                file_type = result.file_type
                source = result.source
                template_path = result.template_path

                if _looks_like_unfilled_template_preview(
                    doc_type, result.preview or ""
                ):
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
            logger.warning(
                "Template libraries unavailable: %s, using markdown fallback", exc
            )
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
        result.content
        if result and result.success and file_type in ("docx", "xlsx")
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

    # Provenance footer is injected one layer down inside
    # create_package_document_version() so every DOCUMENT# write — chat,
    # POST route, AI edit — gets the same guarantee. Don't double-inject
    # here; the helper has a guard but the placement also matters for
    # content-hash idempotency.
    if not (result and result.success and file_type in ("docx", "xlsx")):
        content_to_store = content

    # Build origin context for IGCE XLSX generation (Phase 4)
    source_context_type = None
    source_data_summary = None
    source_data = None
    if doc_type == "igce" and output_format == "xlsx":
        source_context_type = "igce_xlsx_generation"
        # Build compact summary
        line_items = data.get("line_items", [])
        goods_items = data.get("goods_items", [])
        summary_parts = []
        if line_items:
            summary_parts.append(f"{len(line_items)} labor items")
        if goods_items:
            summary_parts.append(f"{len(goods_items)} goods items")
        if data.get("contract_type"):
            summary_parts.append(f"contract: {data.get('contract_type')}")
        if data.get("period_months"):
            summary_parts.append(f"period: {data.get('period_months')} months")
        source_data_summary = ", ".join(summary_parts) if summary_parts else "IGCE from context"
        # Store compact source data (limited to key fields, ~10KB max)
        source_data = {
            "line_items": line_items[:12] if line_items else [],  # Max 12 labor slots
            "goods_items": goods_items[:8] if goods_items else [],  # Max 8 goods slots
            "contract_type": data.get("contract_type"),
            "period_months": data.get("period_months"),
            "period_of_performance": data.get("period_of_performance"),
            "delivery_date": data.get("delivery_date"),
            "estimated_value": data.get("estimated_value"),
            "description": data.get("description"),
        }

    if package_id:
        from app.document_service import create_package_document_version

        # Pass the markdown content as sidecar when storing binary files
        # so the viewer and ZIP export can render human-readable previews.
        _md_content = content if ext in ("docx", "xlsx") and isinstance(content, str) else None

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
            markdown_content=_md_content,
            source_context_type=source_context_type,
            source_data_summary=source_data_summary,
            source_data=source_data,
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
            s3.put_object(
                Bucket=bucket, Key=s3_key, Body=content_to_store.encode("utf-8")
            )
        save_status = "saved"
        save_location = f"s3://{bucket}/{s3_key}"
    except (ClientError, BotoCoreError) as exc:
        save_status = "generated_but_not_saved"
        save_location = f"S3 save failed: {str(exc)}"
        logger.warning("Failed to save document to S3: %s", exc)

    if save_status == "saved":
        try:
            document_id = None
            markdown_s3_key = f"{s3_key}.content.md" if content and isinstance(content, str) else None

            from app.user_document_store import create_document as create_unified_document

            stored_doc = create_unified_document(
                tenant_id=tenant_id,
                user_id=user_id,
                s3_bucket=bucket,
                s3_key=s3_key,
                filename=s3_key.rsplit("/", 1)[-1],
                original_filename=s3_key.rsplit("/", 1)[-1],
                content_type=(
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    if file_type == "docx"
                    else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    if file_type == "xlsx"
                    else "text/markdown"
                ),
                size_bytes=(
                    len(content_to_store)
                    if isinstance(content_to_store, bytes)
                    else len(content_to_store.encode("utf-8"))
                ),
                doc_type=doc_type,
                title=title,
                file_type=ext,
                markdown_s3_key=markdown_s3_key,
                content_hash=hashlib.sha256(
                    content_to_store if isinstance(content_to_store, bytes) else content_to_store.encode("utf-8")
                ).hexdigest(),
                package_id=None,
                is_deliverable=True,
                session_id=session_id,
                template_id=effective_template_id,
                template_provenance=template_provenance,
                source_context_type=source_context_type,
                source_data_summary=source_data_summary,
                source_data=source_data,
            )
            document_id = stored_doc.get("document_id")
        except Exception as exc:
            document_id = None
            logger.warning("Failed to create unified document metadata for %s: %s", s3_key, exc)

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
        "document_id": document_id if save_status == "saved" else None,
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
