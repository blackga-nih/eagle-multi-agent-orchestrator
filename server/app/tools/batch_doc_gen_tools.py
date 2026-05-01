"""Batch document generation tools — dispatch handlers.

PR2.2 of the jolly-snacking-narwhal plan. Two new tools that go through
the DOCJOB# data plane introduced in PR2.1:

* ``exec_batch_generate_documents(params, tenant, session_id)`` —
  enqueue + run generation for a list of doc_types in a single tool
  call. Today the implementation is a synchronous in-process loop;
  every job is recorded in DOCJOB# so the API contract matches the
  future SQS+worker swap without changing callers.

* ``exec_get_doc_jobs(params, tenant, session_id)`` — read-back tool
  the supervisor calls at the start of each turn to surface freshly
  completed jobs in its response.

Why ship the synchronous version first: the API surface (job_id ↔
document_id mapping, queued/running/done/failed transitions) is the
hard contract. The transport (in-process now, SQS later) is an
implementation detail that can flip without affecting callers.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .. import package_doc_job_store as docjob_store
from ..package_store import get_package
from .document_generation import exec_create_document

logger = logging.getLogger("eagle.tools.batch_doc_gen")


# Hard cap on doc_types per call so a misfiring agent can't enqueue
# 200 jobs in a single tool call. 25 is comfortably above the largest
# acquisition checklist.
_MAX_DOC_TYPES_PER_CALL = 25


def exec_batch_generate_documents(
    params: dict[str, Any],
    tenant_id: str,
    session_id: str | None = None,
) -> dict:
    """Generate documents for one or more doc_types under a single package.

    Params:
        package_id: required.
        doc_types:  required, list[str]. One job per element.
        actor_user_id: required for audit trail.
        title_overrides: optional, dict[str, str] — per-doc-type title
                         override. Useful when a slash-bypass call needs
                         specific titles per doc.
        data: optional, dict — passed through to create_document data.

    Returns ``{"jobs": [{job_id, doc_type, status, document_id?}, ...],
               "summary": {queued, running, done, failed}}``.

    The handler creates a DOCJOB# record per doc_type, transitions it
    through running → done|failed, and surfaces the final state in the
    response. Today every job runs synchronously in-process (the loop
    does NOT return early on failure — one bad doc_type does not abort
    the rest). The SQS+worker swap (PR2 follow-up) replaces the
    in-process call with a queue send and lets the worker drive the
    transitions on its own clock.
    """
    package_id = params.get("package_id")
    if not package_id:
        return {"error": "missing_package_id", "tool": "batch_generate_documents"}

    actor_user_id = params.get("actor_user_id")
    if not actor_user_id:
        return {
            "error": "missing_actor_user_id",
            "tool": "batch_generate_documents",
            "message": "actor_user_id is required for audit trail.",
        }

    doc_types = params.get("doc_types") or []
    if not isinstance(doc_types, list) or not doc_types:
        return {
            "error": "invalid_doc_types",
            "tool": "batch_generate_documents",
            "message": "doc_types must be a non-empty list of strings.",
        }
    if len(doc_types) > _MAX_DOC_TYPES_PER_CALL:
        return {
            "error": "too_many_doc_types",
            "tool": "batch_generate_documents",
            "message": (
                f"Cap is {_MAX_DOC_TYPES_PER_CALL} doc_types per call; got "
                f"{len(doc_types)}. Split into multiple calls."
            ),
        }

    pkg = get_package(tenant_id, package_id)
    if pkg is None:
        return {
            "error": "package_not_found",
            "tool": "batch_generate_documents",
            "package_id": package_id,
        }

    title_overrides = params.get("title_overrides") or {}
    base_data = params.get("data") or {}
    if not isinstance(title_overrides, dict):
        title_overrides = {}
    if not isinstance(base_data, dict):
        base_data = {}

    jobs: list[dict] = []
    for doc_type in doc_types:
        if not isinstance(doc_type, str) or not doc_type.strip():
            jobs.append(
                {
                    "doc_type": str(doc_type),
                    "status": "failed",
                    "error_message": "doc_type must be a non-empty string",
                }
            )
            continue

        try:
            job = docjob_store.create_job(
                tenant_id=tenant_id,
                package_id=package_id,
                doc_type=doc_type,
                actor_user_id=actor_user_id,
                session_id=session_id,
                job_spec={
                    "title": title_overrides.get(doc_type, ""),
                    "data": base_data,
                },
            )
        except Exception as exc:
            logger.exception(
                "batch_generate_documents: create_job failed for %s/%s",
                package_id,
                doc_type,
            )
            jobs.append(
                {
                    "doc_type": doc_type,
                    "status": "failed",
                    "error_message": f"job creation failed: {exc}",
                }
            )
            continue

        # Transition to running before kicking off the work so observers
        # see in-flight state. The future async path moves this into the
        # worker.
        docjob_store.update_job_status(
            tenant_id, package_id, job["job_id"], "running"
        )

        # Synchronous in-process generation (placeholder for SQS+worker).
        gen_params: dict[str, Any] = {
            "doc_type": doc_type,
            "package_id": package_id,
            "title": title_overrides.get(doc_type, ""),
            "data": base_data,
        }
        try:
            result = exec_create_document(gen_params, tenant_id, session_id)
        except Exception as exc:
            logger.exception(
                "batch_generate_documents: create_document raised for %s/%s",
                package_id,
                doc_type,
            )
            failed = docjob_store.update_job_status(
                tenant_id,
                package_id,
                job["job_id"],
                "failed",
                error_message=f"create_document raised: {exc}",
            )
            jobs.append(_summarize_job(failed or {"job_id": job["job_id"]}))
            continue

        # create_document returns a dict — error or success — never raises.
        if isinstance(result, dict) and result.get("error"):
            failed = docjob_store.update_job_status(
                tenant_id,
                package_id,
                job["job_id"],
                "failed",
                error_message=str(result.get("message") or result.get("error")),
            )
            jobs.append(_summarize_job(failed or {"job_id": job["job_id"]}))
            continue

        document_id = (
            (result or {}).get("document_id")
            or (result or {}).get("doc_id")
            or ""
        )
        done = docjob_store.update_job_status(
            tenant_id,
            package_id,
            job["job_id"],
            "done",
            document_id=document_id or None,
        )
        jobs.append(_summarize_job(done or {"job_id": job["job_id"]}))

    summary = _summary_counts(jobs)
    return {
        "tool": "batch_generate_documents",
        "package_id": package_id,
        "jobs": jobs,
        "summary": summary,
    }


def exec_get_doc_jobs(
    params: dict[str, Any],
    tenant_id: str,
    session_id: str | None = None,
) -> dict:
    """List doc-gen jobs for a package, optionally filtered.

    Params:
        package_id: required.
        since_iso:  optional ISO-8601 timestamp. When set, returns ONLY
                    jobs that completed (done) at or after that timestamp.
                    Use case: supervisor calls this at turn start to
                    surface freshly-completed jobs to the user.
        include_pending: optional, default true. When true, also returns
                    queued + running jobs in a separate ``pending`` list.
    """
    package_id = params.get("package_id")
    if not package_id:
        return {"error": "missing_package_id", "tool": "get_doc_jobs"}

    since_iso = params.get("since_iso")
    include_pending = bool(params.get("include_pending", True))

    if since_iso:
        recent = docjob_store.list_recently_completed(
            tenant_id, package_id, since_iso
        )
        result: dict[str, Any] = {
            "tool": "get_doc_jobs",
            "package_id": package_id,
            "since_iso": since_iso,
            "recently_completed": [_summarize_job(j) for j in recent],
        }
    else:
        all_jobs = docjob_store.list_jobs_for_package(tenant_id, package_id)
        result = {
            "tool": "get_doc_jobs",
            "package_id": package_id,
            "jobs": [_summarize_job(j) for j in all_jobs],
            "summary": _summary_counts(
                [_summarize_job(j) for j in all_jobs]
            ),
        }

    if include_pending:
        pending = docjob_store.list_pending_for_package(tenant_id, package_id)
        result["pending"] = [_summarize_job(j) for j in pending]

    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _summarize_job(job: dict) -> dict:
    """Trim a DOCJOB# record to the fields the agent (and frontend) care
    about. Drops PK/SK/GSI keys + the verbose job_spec."""
    keep = (
        "job_id",
        "package_id",
        "doc_type",
        "status",
        "created_at",
        "completed_at",
        "document_id",
        "error_message",
    )
    return {k: job[k] for k in keep if k in job}


def _summary_counts(jobs: list[dict]) -> dict:
    """Tally counts per status — handy for the agent's response to the
    user (e.g. "5 of 6 documents drafted, 1 failed")."""
    counts = {"queued": 0, "running": 0, "done": 0, "failed": 0}
    for j in jobs:
        status = j.get("status") or ""
        if status in counts:
            counts[status] += 1
    return counts


__all__ = [
    "exec_batch_generate_documents",
    "exec_get_doc_jobs",
]


# Silence unused import lint when _MAX_DOC_TYPES_PER_CALL is constant only.
_ = json
