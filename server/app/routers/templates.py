"""
Templates API Router

Provides endpoints for document template management, S3 template utilities,
standardization, clause references, and compliance gap analysis.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from ..cognito_auth import UserContext
from ..db_client import get_s3
from ..template_store import (
    delete_template,
    list_tenant_templates,
    put_template,
    resolve_template,
)
from .dependencies import get_user_from_header

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/templates", tags=["templates"])
compat_router = APIRouter(tags=["templates"])


class StandardizeBatchRequest(BaseModel):
    """Request body for batch template standardization."""

    doc_types: Optional[List[str]] = None
    dry_run: bool = False
    write_to_plugin: bool = False


class StandardizeSingleRequest(BaseModel):
    """Request body for single template standardization."""

    s3_key: str


@router.get("")
async def list_templates_endpoint(
    doc_type: Optional[str] = None,
    user: UserContext = Depends(get_user_from_header),
):
    """List available templates for the current tenant."""
    return list_tenant_templates(user.tenant_id, doc_type)


# ── S3 Template Library ────────────────────────────────────────────
# NOTE: These must be declared before /{doc_type} to avoid
# FastAPI matching "s3" as a doc_type path parameter.


@router.get("/s3")
async def list_s3_templates_endpoint(
    phase: Optional[str] = None,
    refresh: bool = False,
    user: UserContext = Depends(get_user_from_header),
):
    """List all templates from S3 bucket with metadata.

    Query params:
        phase: Filter by acquisition phase (intake, planning, solicitation, etc.)
        refresh: Force cache refresh (default: false)
    """
    from ..template_registry import list_s3_templates, ACQUISITION_PHASES

    templates = list_s3_templates(refresh=refresh, phase_filter=phase)

    # Build phase counts for filter UI
    phase_counts: Dict[str, int] = {p: 0 for p in ACQUISITION_PHASES}
    all_templates = list_s3_templates(refresh=False) if phase else templates
    for t in all_templates:
        cat = t.get("category")
        if cat and cat.get("phase") in phase_counts:
            phase_counts[cat["phase"]] += 1

    return {
        "templates": templates,
        "total": len(templates),
        "phases": ACQUISITION_PHASES,
        "phase_counts": phase_counts,
    }


@router.get("/s3/preview")
async def preview_s3_template(
    s3_key: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Preview an S3 template."""
    from ..spreadsheet_edit_service import extract_xlsx_preview_payload
    from ..template_registry import (
        TEMPLATE_BUCKET,
        TEMPLATE_PREFIX,
        get_s3_template_by_key,
    )
    from ..template_service import DOCXPopulator

    if not s3_key:
        raise HTTPException(status_code=400, detail="s3_key is required")
    if not s3_key.startswith(TEMPLATE_PREFIX):
        raise HTTPException(
            status_code=403, detail="Access denied — invalid template key"
        )

    filename = s3_key.rsplit("/", 1)[-1] if "/" in s3_key else s3_key
    file_ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if file_ext == "pdf":
        s3 = get_s3()
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": TEMPLATE_BUCKET, "Key": s3_key},
            ExpiresIn=3600,
        )
        return {"type": "pdf", "url": url, "filename": filename}

    if file_ext in ("docx", "doc"):
        content_bytes = get_s3_template_by_key(s3_key)
        if not content_bytes:
            raise HTTPException(status_code=404, detail="Template not found in S3")
        markdown = DOCXPopulator.extract_text(content_bytes)
        return {"type": "markdown", "content": markdown, "filename": filename}

    if file_ext in ("xlsx", "xls"):
        content_bytes = get_s3_template_by_key(s3_key)
        if not content_bytes:
            raise HTTPException(status_code=404, detail="Template not found in S3")
        preview_data = extract_xlsx_preview_payload(content_bytes)
        return {
            "type": "xlsx",
            "content": preview_data.get("content", ""),
            "preview_mode": preview_data.get("preview_mode"),
            "preview_sheets": preview_data.get("preview_sheets", []),
            "filename": filename,
        }

    raise HTTPException(status_code=400, detail=f"Unsupported file type: {file_ext}")


@router.get("/s3/download-url")
async def get_s3_template_download_url(
    s3_key: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Return a presigned download URL for an S3 template."""
    from ..template_registry import TEMPLATE_BUCKET, TEMPLATE_PREFIX

    if not s3_key:
        raise HTTPException(status_code=400, detail="s3_key is required")
    if not s3_key.startswith(TEMPLATE_PREFIX):
        raise HTTPException(
            status_code=403, detail="Access denied — invalid template key"
        )

    filename = s3_key.rsplit("/", 1)[-1] if "/" in s3_key else s3_key
    s3 = get_s3()
    url = s3.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": TEMPLATE_BUCKET,
            "Key": s3_key,
            "ResponseContentDisposition": f'attachment; filename="{filename}"',
        },
        ExpiresIn=3600,
    )
    return {"download_url": url, "filename": filename, "expires_in": 3600}


@router.post("/s3/copy")
async def copy_s3_template_to_package(
    body: Dict[str, Any],
    user: UserContext = Depends(get_user_from_header),
):
    """Copy an S3 template into an acquisition package.

    Body:
        s3_key: Full S3 key of the template
        package_id: Target package ID

    Returns:
        Created document entry with document_id
    """
    from ..template_registry import (
        get_s3_template_by_key,
        _infer_doc_type_from_filename,
    )
    from ..package_document_store import create_document_from_s3

    s3_key = body.get("s3_key")
    package_id = body.get("package_id")

    if not s3_key or not package_id:
        raise HTTPException(
            status_code=400, detail="s3_key and package_id are required"
        )

    # Fetch template content from S3
    content = get_s3_template_by_key(s3_key)
    if content is None:
        raise HTTPException(status_code=404, detail="Template not found in S3")

    # Extract filename and doc_type
    filename = s3_key.rsplit("/", 1)[-1] if "/" in s3_key else s3_key
    file_type = filename.rsplit(".", 1)[-1].lower() if "." in filename else "unknown"

    # Infer doc_type from filename
    doc_type = _infer_doc_type_from_filename(filename) or "custom"

    # Create document entry in package
    document = create_document_from_s3(
        tenant_id=user.tenant_id,
        package_id=package_id,
        doc_type=doc_type,
        filename=filename,
        file_type=file_type,
        content=content,
        source_s3_key=s3_key,
        created_by=user.user_id,
    )

    return {
        "document_id": document.get("document_id"),
        "doc_type": doc_type,
        "filename": filename,
        "package_id": package_id,
        "source": "s3_template",
    }


@router.post("/standardize")
async def batch_standardize_templates(
    body: StandardizeBatchRequest,
    background_tasks: BackgroundTasks,
    user: UserContext = Depends(get_user_from_header),
):
    """Batch standardize S3 templates to gold-standard markdown."""
    from ..template_registry import (
        TEMPLATE_BUCKET,
        get_s3_template_by_key,
        list_s3_templates,
    )
    from ..template_standardizer import (
        BatchJobResult,
        create_batch_job,
        standardize_template as run_standardize,
        update_batch_job,
    )

    templates = list_s3_templates(refresh=True)
    templates = [
        template
        for template in templates
        if template.get("file_type") not in ("xlsx", "xls")
    ]
    if body.doc_types:
        templates = [
            template
            for template in templates
            if template.get("doc_type") in body.doc_types
        ]

    if not templates:
        return {
            "job_id": None,
            "status": "complete",
            "message": "No templates to process",
        }

    job_id = create_batch_job(len(templates))

    async def _run_batch():
        import asyncio

        s3 = get_s3()
        for template in templates:
            try:
                s3_key = template["s3_key"]
                filename = template["filename"]
                file_type = template.get("file_type", "docx")
                doc_type = template.get("doc_type") or "unknown"
                template_bytes = get_s3_template_by_key(s3_key)
                if template_bytes is None:
                    update_batch_job(
                        job_id,
                        BatchJobResult(
                            filename=filename,
                            doc_type=doc_type,
                            quality_score=0,
                            success=False,
                            issues=["Template not found in S3"],
                        ),
                    )
                    continue

                content_type_map = {
                    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "doc": "application/msword",
                    "pdf": "application/pdf",
                    "txt": "text/plain",
                    "md": "text/markdown",
                }
                content_type = content_type_map.get(
                    file_type, "application/octet-stream"
                )
                result = await asyncio.to_thread(
                    run_standardize, template_bytes, filename, content_type, doc_type
                )

                if result.success and not body.dry_run:
                    md_key = s3_key.rsplit(".", 1)[0] + ".standardized.md"
                    try:
                        s3.put_object(
                            Bucket=TEMPLATE_BUCKET,
                            Key=md_key,
                            Body=result.markdown.encode("utf-8"),
                            ContentType="text/markdown",
                        )
                    except Exception as exc:
                        logger.warning("Failed to write standardized md to S3: %s", exc)

                update_batch_job(
                    job_id,
                    BatchJobResult(
                        filename=filename,
                        doc_type=doc_type,
                        quality_score=result.quality_score,
                        success=result.success,
                        issues=result.issues,
                        placeholders_found=result.placeholders_found,
                        sections_found=result.sections_found,
                    ),
                )
            except Exception as exc:
                logger.error(
                    "Batch standardization error for %s: %s",
                    template.get("filename"),
                    exc,
                )
                update_batch_job(
                    job_id,
                    BatchJobResult(
                        filename=template.get("filename", "unknown"),
                        doc_type=template.get("doc_type", "unknown"),
                        quality_score=0,
                        success=False,
                        issues=[str(exc)],
                    ),
                )

    background_tasks.add_task(_run_batch)
    return {"job_id": job_id, "status": "processing", "total": len(templates)}


@router.get("/standardize/{job_id}")
async def get_standardization_status(
    job_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Poll batch standardization job status."""
    from ..template_standardizer import get_batch_job

    job = get_batch_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "progress": {"completed": job["completed"], "total": job["total"]},
        "results": job["results"],
        "summary": job.get("summary"),
        "error": job.get("error"),
    }


@router.post("/standardize-single")
async def standardize_single_template(
    body: StandardizeSingleRequest,
    user: UserContext = Depends(get_user_from_header),
):
    """Standardize a single S3 template."""
    from ..template_registry import (
        _infer_doc_type_from_filename,
        get_s3_template_by_key,
    )
    from ..template_standardizer import standardize_template as run_standardize

    s3_key = body.s3_key
    template_bytes = get_s3_template_by_key(s3_key)
    if template_bytes is None:
        raise HTTPException(status_code=404, detail="Template not found in S3")

    filename = s3_key.rsplit("/", 1)[-1] if "/" in s3_key else s3_key
    file_type = filename.rsplit(".", 1)[-1].lower() if "." in filename else "unknown"
    doc_type = _infer_doc_type_from_filename(filename) or "unknown"
    content_type_map = {
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "doc": "application/msword",
        "pdf": "application/pdf",
        "txt": "text/plain",
        "md": "text/markdown",
    }
    content_type = content_type_map.get(file_type, "application/octet-stream")
    result = run_standardize(template_bytes, filename, content_type, doc_type)
    return {
        "result": result.to_dict(),
        "preview": result.markdown[:1000] if result.markdown else "",
    }


@router.get("/quality-report")
async def get_templates_quality_report(
    user: UserContext = Depends(get_user_from_header),
):
    """Get quality assessment for all S3 templates."""
    from ..document_markdown_service import convert_to_markdown
    from ..template_registry import get_s3_template_by_key, list_s3_templates
    from ..template_standardizer import assess_quality

    templates = list_s3_templates(refresh=True)
    templates = [
        template
        for template in templates
        if template.get("file_type") not in ("xlsx", "xls")
    ]

    results = []
    for template in templates:
        filename = template["filename"]
        doc_type = template.get("doc_type") or "unknown"
        file_type = template.get("file_type", "unknown")
        try:
            template_bytes = get_s3_template_by_key(template["s3_key"])
            if template_bytes is None:
                results.append(
                    {
                        "filename": filename,
                        "doc_type": doc_type,
                        "quality": {"score": 0, "issues": ["Template not found"]},
                    }
                )
                continue

            content_type_map = {
                "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "doc": "application/msword",
                "pdf": "application/pdf",
                "txt": "text/plain",
                "md": "text/markdown",
            }
            content_type = content_type_map.get(file_type, "application/octet-stream")
            markdown = convert_to_markdown(template_bytes, content_type, filename)
            quality = assess_quality(markdown or "", doc_type)
            results.append(
                {
                    "filename": filename,
                    "doc_type": doc_type,
                    "display_name": template.get("display_name", filename),
                    "file_type": file_type,
                    "quality": quality.to_dict(),
                }
            )
        except Exception as exc:
            results.append(
                {
                    "filename": filename,
                    "doc_type": doc_type,
                    "quality": {"score": 0, "issues": [str(exc)]},
                }
            )

    results.sort(key=lambda item: item.get("quality", {}).get("score", 0))
    total = len(results)
    avg_score = (
        sum(item.get("quality", {}).get("score", 0) for item in results) / total
        if total
        else 0
    )
    return {
        "total": total,
        "avg_quality_score": round(avg_score, 1),
        "templates": results,
    }


# ── Template CRUD (Dynamic Routes) ─────────────────────────────────


@router.get("/{doc_type}")
async def get_active_template(
    doc_type: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Return the resolved template for this user (4-layer fallback)."""
    resolved = resolve_template(user.tenant_id, user.user_id, doc_type)
    if len(resolved) == 3:
        body, source, metadata = resolved
    else:
        body, source = resolved
        metadata = None
    return {
        "doc_type": doc_type,
        "template_body": body,
        "source": source,
        "metadata": metadata,
    }


@router.post("/{doc_type}")
async def create_template_endpoint(
    doc_type: str,
    body: Dict[str, Any],
    user: UserContext = Depends(get_user_from_header),
):
    """Create or update a user/tenant template override."""
    return put_template(
        tenant_id=user.tenant_id,
        doc_type=doc_type,
        user_id=body.get("user_id", user.user_id),
        template_body=body.get("template_body", ""),
        display_name=body.get("display_name", ""),
        is_default=body.get("is_default", False),
    )


@router.delete("/{doc_type}")
async def delete_template_endpoint(
    doc_type: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Delete the current user's template override for a doc type."""
    ok = delete_template(user.tenant_id, doc_type, user.user_id)
    return {"deleted": ok}


@router.get("/{doc_type}/clauses")
async def get_template_clauses(
    doc_type: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Return aggregated clause references for a doc_type."""
    try:
        from ..template_schema import load_clause_references_by_category

        refs = load_clause_references_by_category(doc_type)
        all_clauses: dict[str, dict[str, Any]] = {}
        for ref_data in refs:
            for sec_data in ref_data.get("section_clause_map", {}).values():
                for clause in sec_data.get("clauses", []):
                    clause_number = clause.get("clause_number", "")
                    if clause_number and clause_number not in all_clauses:
                        all_clauses[clause_number] = clause
            for clause in ref_data.get("template_level_clauses", []):
                clause_number = clause.get("clause_number", "")
                if clause_number and clause_number not in all_clauses:
                    all_clauses[clause_number] = clause
        return {
            "doc_type": doc_type,
            "clauses": list(all_clauses.values()),
            "total": len(all_clauses),
            "variants": len(refs),
        }
    except Exception as exc:
        return {"doc_type": doc_type, "clauses": [], "total": 0, "error": str(exc)}


@router.get("/clauses/summary")
async def get_all_clause_summary(
    user: UserContext = Depends(get_user_from_header),
):
    """Return clause counts and FAR parts covered for all templates."""
    try:
        from ..template_schema import load_all_clause_references

        all_refs = load_all_clause_references()
        summary = []
        for filename, ref_data in all_refs.items():
            summary.append(
                {
                    "template_filename": ref_data.get("template_filename", filename),
                    "category": ref_data.get("category", ""),
                    "total_clauses": ref_data.get("total_clauses", 0),
                    "far_parts_covered": ref_data.get("far_parts_covered", []),
                }
            )
        return {"templates": summary, "total": len(summary)}
    except Exception as exc:
        return {"templates": [], "total": 0, "error": str(exc)}


@router.get("/clause-search")
async def search_templates_by_clause(
    clause: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Find all templates that reference a specific FAR clause."""
    try:
        from ..template_schema import load_all_clause_references

        all_refs = load_all_clause_references()
        matches = []
        clause_lower = clause.lower()
        for filename, ref_data in all_refs.items():
            found_in = []
            for sec_num, sec_data in ref_data.get("section_clause_map", {}).items():
                for ref_clause in sec_data.get("clauses", []):
                    if clause_lower in ref_clause.get("clause_number", "").lower():
                        found_in.append(
                            {
                                "section": sec_num,
                                "section_title": sec_data.get("section_title", ""),
                            }
                        )
            for ref_clause in ref_data.get("template_level_clauses", []):
                if clause_lower in ref_clause.get("clause_number", "").lower():
                    found_in.append(
                        {"section": "template_level", "section_title": "Template-level"}
                    )
            if found_in:
                matches.append(
                    {
                        "template_filename": ref_data.get(
                            "template_filename", filename
                        ),
                        "category": ref_data.get("category", ""),
                        "sections": found_in,
                    }
                )
        return {"clause": clause, "matches": matches, "total": len(matches)}
    except Exception as exc:
        return {"clause": clause, "matches": [], "total": 0, "error": str(exc)}


@compat_router.get("/api/compliance/gap-analysis")
async def compliance_gap_analysis(
    value: float,
    method: str,
    type: str,
    is_it: bool = False,
    is_services: bool = True,
    is_small_business: bool = False,
    user: UserContext = Depends(get_user_from_header),
):
    """Analyze compliance gaps across templates for given package parameters."""
    try:
        from ..compliance_gap_service import analyze_compliance_gaps

        flags = {
            "is_it": is_it,
            "is_services": is_services,
            "is_small_business": is_small_business,
        }
        return analyze_compliance_gaps(value, method, type, flags)
    except Exception as exc:
        return {
            "error": str(exc),
            "covered": [],
            "gaps": [],
            "partial": [],
            "coverage_pct": 0,
        }
