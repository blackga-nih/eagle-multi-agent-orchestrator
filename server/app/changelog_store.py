"""
changelog_store.py — CHANGELOG# entity for document change tracking.

Entity layout:
    PK:  CHANGELOG#{tenant_id}
    SK:  CHANGELOG#{package_id}#{doc_type}#{ISO_timestamp}

TTL: 7 years from write time (epoch seconds stored in `ttl` attribute).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from boto3.dynamodb.conditions import Key
from botocore.exceptions import BotoCoreError, ClientError

from .db_client import get_table, now_iso, ttl_timestamp

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seven_year_ttl() -> int:
    """Return Unix epoch seconds 7 years from now."""
    return ttl_timestamp(days=365 * 7)


def _normalize_change_source(change_source: str) -> str:
    """Collapse legacy/internal source labels to the UI-facing values."""
    normalized = (change_source or "").strip().lower()
    if normalized in {"ai_edit", "agent_tool"}:
        return "agent_tool"
    return change_source


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def write_changelog_entry(
    tenant_id: str,
    package_id: str,
    doc_type: str,
    version: int,
    change_type: str,
    change_source: str,
    change_summary: str,
    actor_user_id: str,
    session_id: Optional[str] = None,
) -> dict:
    """Write a changelog entry for a document change.

    Parameters
    ----------
    tenant_id:     Tenant owning this document.
    package_id:    Package containing the document.
    doc_type:      Document type (sow, igce, etc.).
    version:       Document version number.
    change_type:   Type of change: 'create', 'update', 'finalize'.
    change_source: How the change was made: 'agent_tool', 'user_edit'.
    change_summary: Human-readable description of what changed.
    actor_user_id: User or system process that made the change.
    session_id:    Optional chat session that triggered the change.
    """
    created_at = now_iso()
    changelog_id = str(uuid.uuid4())

    pk = f"CHANGELOG#{tenant_id}"
    sk = f"CHANGELOG#{package_id}#{doc_type}#{created_at}"

    item: dict[str, Any] = {
        "PK": pk,
        "SK": sk,
        "changelog_id": changelog_id,
        "tenant_id": tenant_id,
        "package_id": package_id,
        "doc_type": doc_type,
        "version": version,
        "change_type": change_type,
        "change_source": _normalize_change_source(change_source),
        "change_summary": change_summary,
        "actor_user_id": actor_user_id,
        "created_at": created_at,
        "ttl": _seven_year_ttl(),
    }

    if session_id:
        item["session_id"] = session_id

    try:
        get_table().put_item(Item=item)
        logger.info(
            "changelog_store: wrote %s entry for %s/%s v%d (tenant=%s actor=%s)",
            change_type,
            package_id,
            doc_type,
            version,
            tenant_id,
            actor_user_id,
        )
    except (ClientError, BotoCoreError) as exc:
        logger.error("changelog_store: failed to write changelog entry: %s", exc)
        raise

    return item


def list_changelog_entries(
    tenant_id: str,
    package_id: str,
    doc_type: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """Query changelog entries for a document, newest first.

    Parameters
    ----------
    tenant_id:   Tenant whose changelog to read.
    package_id:  Package to filter by.
    doc_type:    If provided, filter to specific document type.
    limit:       Maximum number of items to return (default 50).
    """
    pk = f"CHANGELOG#{tenant_id}"

    # Build SK prefix based on whether doc_type is specified
    if doc_type:
        sk_prefix = f"CHANGELOG#{package_id}#{doc_type}#"
    else:
        sk_prefix = f"CHANGELOG#{package_id}#"

    query_kwargs: dict[str, Any] = {
        "KeyConditionExpression": Key("PK").eq(pk) & Key("SK").begins_with(sk_prefix),
        "ScanIndexForward": False,  # newest first
        "Limit": limit,
    }

    try:
        response = get_table().query(**query_kwargs)
        items: list[dict] = response.get("Items", [])
        logger.debug(
            "changelog_store: retrieved %d entries for tenant=%s package=%s doc_type=%s",
            len(items),
            tenant_id,
            package_id,
            doc_type,
        )
        return items
    except (ClientError, BotoCoreError) as exc:
        logger.error("changelog_store: failed to list changelog entries: %s", exc)
        raise


# ---------------------------------------------------------------------------
# Document-key-based changelog (for workspace/standalone documents)
# ---------------------------------------------------------------------------


def write_document_changelog_entry(
    tenant_id: str,
    document_key: str,
    change_type: str,
    change_source: str,
    change_summary: str,
    actor_user_id: str,
    doc_type: Optional[str] = None,
    version: int = 1,
    session_id: Optional[str] = None,
) -> dict:
    """Write a changelog entry keyed by document S3 key.

    Used for workspace documents that don't belong to a package.

    Parameters
    ----------
    tenant_id:     Tenant owning this document.
    document_key:  S3 key of the document.
    change_type:   Type of change: 'create', 'update', 'finalize'.
    change_source: How the change was made: 'agent_tool', 'user_edit'.
    change_summary: Human-readable description of what changed.
    actor_user_id: User or system process that made the change.
    doc_type:      Optional document type (sow, igce, etc.).
    version:       Version number (default 1 for workspace docs).
    session_id:    Optional chat session that triggered the change.
    """
    import hashlib

    created_at = now_iso()
    changelog_id = str(uuid.uuid4())

    # Use hash of document key for SK to keep it reasonable length
    key_hash = hashlib.sha256(document_key.encode()).hexdigest()[:16]

    pk = f"CHANGELOG#{tenant_id}"
    sk = f"DOCLOG#{key_hash}#{created_at}"

    item: dict[str, Any] = {
        "PK": pk,
        "SK": sk,
        "changelog_id": changelog_id,
        "tenant_id": tenant_id,
        "document_key": document_key,
        "doc_type": doc_type or _infer_doc_type(document_key),
        "version": version,
        "change_type": change_type,
        "change_source": _normalize_change_source(change_source),
        "change_summary": change_summary,
        "actor_user_id": actor_user_id,
        "created_at": created_at,
        "ttl": _seven_year_ttl(),
    }

    if session_id:
        item["session_id"] = session_id

    try:
        get_table().put_item(Item=item)
        logger.info(
            "changelog_store: wrote %s entry for doc_key=%s (tenant=%s actor=%s)",
            change_type,
            document_key[:50],
            tenant_id,
            actor_user_id,
        )
    except (ClientError, BotoCoreError) as exc:
        logger.error(
            "changelog_store: failed to write document changelog entry: %s", exc
        )
        raise

    return item


def list_document_changelog_entries(
    tenant_id: str,
    document_key: str,
    limit: int = 50,
) -> list[dict]:
    """Query changelog entries for a document by S3 key, newest first."""
    import hashlib

    pk = f"CHANGELOG#{tenant_id}"
    key_hash = hashlib.sha256(document_key.encode()).hexdigest()[:16]
    sk_prefix = f"DOCLOG#{key_hash}#"

    query_kwargs: dict[str, Any] = {
        "KeyConditionExpression": Key("PK").eq(pk) & Key("SK").begins_with(sk_prefix),
        "ScanIndexForward": False,  # newest first
        "Limit": limit,
    }

    try:
        response = get_table().query(**query_kwargs)
        items: list[dict] = response.get("Items", [])
        logger.debug(
            "changelog_store: retrieved %d entries for tenant=%s doc_key=%s",
            len(items),
            tenant_id,
            document_key[:50],
        )
        return items
    except (ClientError, BotoCoreError) as exc:
        logger.error(
            "changelog_store: failed to list document changelog entries: %s", exc
        )
        raise


def _infer_doc_type(document_key: str) -> str:
    """Infer document type from filename in S3 key."""
    filename = document_key.split("/")[-1]
    # Handle patterns like sow_20260310_151559.docx or sow_v1.md
    base = filename.split("_")[0] if "_" in filename else filename.rsplit(".", 1)[0]
    return base.lower()
