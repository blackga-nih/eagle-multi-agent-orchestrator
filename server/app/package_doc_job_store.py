"""Package document generation jobs — DOCJOB# entity store.

Tracks asynchronous document-generation work submitted via the
``batch_generate_documents`` tool. Each job represents one
(package_id, doc_type) pair queued for generation. Status transitions
queued → running → done | failed; on done, ``document_id`` points at
the resulting DOCUMENT# record.

PR2.1 of the jolly-snacking-narwhal plan. The store is the data plane;
the SQS + worker pieces (PR2 follow-up) consume from it. For now,
``batch_generate_documents`` may run jobs synchronously in-process
while still going through this store so the API contract is stable.

PK:  JOB#{tenant_id}
SK:  DOCJOB#{package_id}#{job_id}
GSI1PK:  TENANT#{tenant_id}
GSI1SK:  DOCJOB#{status}#{created_at}#{job_id}

GSI1 lets the worker poll by status (e.g. queued) without scanning
across packages.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from boto3.dynamodb.conditions import Key
from botocore.exceptions import BotoCoreError, ClientError

from .db_client import get_table, item_to_dict, now_iso

logger = logging.getLogger("eagle.package_doc_job_store")


# Allowed status transitions. We don't enforce strictly — DDB writes are
# unconditional — but the dispatch layer should respect this graph.
_VALID_STATUSES = {"queued", "running", "done", "failed"}


def _pk(tenant_id: str) -> str:
    return f"JOB#{tenant_id}"


def _sk(package_id: str, job_id: str) -> str:
    return f"DOCJOB#{package_id}#{job_id}"


def _sk_package_prefix(package_id: str) -> str:
    return f"DOCJOB#{package_id}#"


def _gsi1pk(tenant_id: str) -> str:
    return f"TENANT#{tenant_id}"


def _gsi1sk(status: str, created_at: str, job_id: str) -> str:
    return f"DOCJOB#{status}#{created_at}#{job_id}"


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def create_job(
    tenant_id: str,
    package_id: str,
    doc_type: str,
    actor_user_id: str,
    session_id: Optional[str] = None,
    job_spec: Optional[dict[str, Any]] = None,
) -> dict:
    """Insert a new DOCJOB# record in the queued state. Returns the job dict.

    Raises BotoCoreError / ClientError on DDB failure.
    """
    job_id = str(uuid.uuid4())
    now = now_iso()
    item: dict[str, Any] = {
        "PK": _pk(tenant_id),
        "SK": _sk(package_id, job_id),
        "GSI1PK": _gsi1pk(tenant_id),
        "GSI1SK": _gsi1sk("queued", now, job_id),
        "job_id": job_id,
        "tenant_id": tenant_id,
        "package_id": package_id,
        "doc_type": doc_type,
        "status": "queued",
        "actor_user_id": actor_user_id,
        "created_at": now,
        "updated_at": now,
    }
    if session_id:
        item["session_id"] = session_id
    if job_spec:
        item["job_spec"] = job_spec

    try:
        get_table().put_item(Item=item)
    except (ClientError, BotoCoreError) as exc:
        logger.error(
            "create_job: put_item failed (tenant=%s, pkg=%s, doc_type=%s): %s",
            tenant_id,
            package_id,
            doc_type,
            exc,
        )
        raise

    return _serialize(item)


def get_job(tenant_id: str, package_id: str, job_id: str) -> Optional[dict]:
    """Return a single job by id, or None if missing."""
    try:
        response = get_table().get_item(
            Key={"PK": _pk(tenant_id), "SK": _sk(package_id, job_id)}
        )
    except (ClientError, BotoCoreError) as exc:
        logger.error("get_job: get_item failed: %s", exc)
        return None

    item = response.get("Item")
    return _serialize(item) if item else None


def update_job_status(
    tenant_id: str,
    package_id: str,
    job_id: str,
    status: str,
    document_id: Optional[str] = None,
    error_message: Optional[str] = None,
) -> Optional[dict]:
    """Transition a job's status. Returns the updated job dict, or None
    if the job doesn't exist.

    On status="done", ``document_id`` should be the DOCUMENT#'s id.
    On status="failed", ``error_message`` should explain the failure.
    Both fields are optional and only stored when present.

    The GSI1SK is rewritten so the status-keyed index reflects the
    new status — important so the worker can poll by status.
    """
    if status not in _VALID_STATUSES:
        raise ValueError(f"invalid status: {status} (allowed: {_VALID_STATUSES})")

    existing = get_job(tenant_id, package_id, job_id)
    if existing is None:
        logger.warning(
            "update_job_status: not found (tenant=%s, pkg=%s, job=%s)",
            tenant_id,
            package_id,
            job_id,
        )
        return None

    now = now_iso()
    update_parts = ["#status = :status", "updated_at = :now", "GSI1SK = :gsi1sk"]
    expr_attr_names = {"#status": "status"}
    expr_attr_values = {
        ":status": status,
        ":now": now,
        # Re-key the GSI by status; preserve the original created_at so
        # status-keyed queries are still time-ordered within a status.
        ":gsi1sk": _gsi1sk(status, existing["created_at"], job_id),
    }

    if status in {"done", "failed"}:
        update_parts.append("completed_at = :completed_at")
        expr_attr_values[":completed_at"] = now

    if document_id is not None:
        update_parts.append("document_id = :document_id")
        expr_attr_values[":document_id"] = document_id

    if error_message is not None:
        update_parts.append("error_message = :error_message")
        # Cap pathological error strings so a runaway stack trace
        # doesn't blow the 400KB DDB item limit.
        expr_attr_values[":error_message"] = error_message[:2000]

    try:
        response = get_table().update_item(
            Key={"PK": _pk(tenant_id), "SK": _sk(package_id, job_id)},
            UpdateExpression="SET " + ", ".join(update_parts),
            ExpressionAttributeNames=expr_attr_names,
            ExpressionAttributeValues=expr_attr_values,
            ReturnValues="ALL_NEW",
        )
    except (ClientError, BotoCoreError) as exc:
        logger.error("update_job_status: update_item failed: %s", exc)
        return None

    return _serialize(response.get("Attributes", {}))


def list_jobs_for_package(
    tenant_id: str, package_id: str, limit: int = 100
) -> list[dict]:
    """Return all jobs for a package in chronological order."""
    try:
        response = get_table().query(
            KeyConditionExpression=Key("PK").eq(_pk(tenant_id))
            & Key("SK").begins_with(_sk_package_prefix(package_id)),
            Limit=limit,
        )
    except (ClientError, BotoCoreError) as exc:
        logger.error("list_jobs_for_package: query failed: %s", exc)
        return []

    items = [_serialize(i) for i in response.get("Items", [])]
    items.sort(key=lambda j: j.get("created_at", ""))
    return items


def list_recently_completed(
    tenant_id: str,
    package_id: str,
    since_iso: str,
) -> list[dict]:
    """Return jobs in package whose ``completed_at`` is >= since_iso.

    Used by the supervisor's ``get_doc_jobs`` tool to surface freshly-
    completed jobs in the next response. since_iso is typically the
    timestamp of the previous user turn.
    """
    jobs = list_jobs_for_package(tenant_id, package_id)
    return [
        j
        for j in jobs
        if j.get("status") == "done"
        and j.get("completed_at")
        and j["completed_at"] >= since_iso
    ]


def list_pending_for_package(tenant_id: str, package_id: str) -> list[dict]:
    """Return queued + running jobs for a package — what's still in flight."""
    jobs = list_jobs_for_package(tenant_id, package_id)
    return [j for j in jobs if j.get("status") in {"queued", "running"}]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _serialize(item: dict) -> dict:
    """Convert a raw DDB item to a JSON-serialisable dict (Decimal → str)."""
    return item_to_dict(item)
