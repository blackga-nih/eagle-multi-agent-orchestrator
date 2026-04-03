"""Package/document tool handlers.

Manages package validation, finalization, and document linkage operations.
"""

from __future__ import annotations

import logging
import os
from decimal import Decimal

from ..db_client import get_s3

logger = logging.getLogger("eagle.package_document_tools")


def exec_document_changelog_search(params: dict, tenant_id: str) -> dict:
    """Search changelog history for a document or package."""
    from app.changelog_store import list_changelog_entries

    package_id = params.get("package_id")
    if not package_id:
        return {"error": "package_id is required"}

    doc_type = params.get("doc_type")
    limit = params.get("limit", 20)

    entries = list_changelog_entries(tenant_id, package_id, doc_type, limit)

    return {
        "package_id": package_id,
        "doc_type": doc_type,
        "count": len(entries),
        "entries": [
            {
                "change_type": entry.get("change_type"),
                "change_source": entry.get("change_source"),
                "change_summary": entry.get("change_summary"),
                "doc_type": entry.get("doc_type"),
                "version": entry.get("version"),
                "actor_user_id": entry.get("actor_user_id"),
                "created_at": entry.get("created_at"),
            }
            for entry in entries
        ],
    }


def exec_get_latest_document(params: dict, tenant_id: str) -> dict:
    """Get latest document version with recent changelog entries."""
    from app.changelog_store import list_changelog_entries
    from app.package_document_store import get_document

    package_id = params.get("package_id")
    doc_type = params.get("doc_type")

    if not package_id or not doc_type:
        return {"error": "package_id and doc_type are required"}

    document = get_document(tenant_id, package_id, doc_type, version=None)
    if not document:
        return {"error": f"No {doc_type} document found for package {package_id}"}

    changelog = list_changelog_entries(tenant_id, package_id, doc_type, limit=5)

    return {
        "document": {
            "doc_type": document.get("doc_type"),
            "version": document.get("version"),
            "title": document.get("title"),
            "status": document.get("status"),
            "created_at": document.get("created_at"),
            "s3_key": document.get("s3_key"),
        },
        "recent_changes": [
            {
                "change_type": entry.get("change_type"),
                "change_summary": entry.get("change_summary"),
                "actor_user_id": entry.get("actor_user_id"),
                "created_at": entry.get("created_at"),
            }
            for entry in changelog
        ],
    }


def exec_finalize_package(params: dict, tenant_id: str) -> dict:
    """Validate acquisition package completeness and optionally submit."""
    from app.package_store import submit_package, validate_package_completeness

    package_id = params.get("package_id")
    if not package_id:
        return {"error": "package_id is required"}

    result = validate_package_completeness(tenant_id, package_id)
    if result.get("error"):
        return result

    auto_submit = params.get("auto_submit", False)
    if auto_submit and result.get("ready"):
        submitted = submit_package(tenant_id, package_id)
        if submitted:
            result["submitted"] = True
            result["status"] = "review"
        else:
            result["submitted"] = False
            result["submit_error"] = (
                "Package could not be submitted (may not be in drafting status)"
            )

    return result


def _backfill_completed_docs(
    package: dict, tenant_id: str, owner: str, session_id: str | None
) -> None:
    """Link pre-existing session documents to a newly created package.

    When a user generates documents (e.g. SOW) before creating a package,
    those docs live in S3 under the user prefix but aren't tracked in the
    package's ``completed_documents``. This scans the user's S3 documents
    prefix and registers any that match the package's required_documents.

    Only documents created within the last 15 minutes are eligible for
    backfill, preventing stale files from prior sessions from being linked.
    """
    try:
        pkg_id = package.get("package_id")
        required = set(package.get("required_documents", []))
        if not pkg_id or not required or not owner:
            return

        bucket = os.getenv("S3_BUCKET", "eagle-documents-695681773636-dev")
        prefix = f"eagle/{tenant_id}/{owner}/documents/"
        s3 = get_s3()
        resp = s3.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=200)
        contents = resp.get("Contents", [])

        # Only backfill recent files (created during the current session).
        # Stale files from prior sessions must not be auto-linked.
        from datetime import datetime, timedelta, timezone

        cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)

        # Parse doc_types from S3 keys: {prefix}{doc_type}_{timestamp}.{ext}
        found: dict[str, str] = {}  # doc_type → s3_key (latest)
        for obj in contents:
            last_modified = obj.get("LastModified")
            if last_modified and last_modified < cutoff:
                continue  # Skip stale files from prior sessions
            key = obj["Key"]
            filename = key[len(prefix) :]  # e.g. "sow_20260325_203000.md"
            parts = filename.split("_", 1)
            if parts:
                dt = parts[0].lower()
                if dt in required and dt not in found:
                    found[dt] = key

        skipped = len(contents) - sum(1 for o in contents if not o.get("LastModified") or o["LastModified"] >= cutoff)
        if skipped:
            logger.debug(
                "Backfill skipped %d stale S3 objects (older than 15 min) for %s",
                skipped,
                pkg_id,
            )

        if not found:
            return

        # Register each found doc as a package document
        from app.document_service import create_package_document_version
        from app.package_store import update_package

        completed = list(package.get("completed_documents", []))
        for doc_type, s3_key in found.items():
            if doc_type in completed:
                continue
            # Read content from S3 to link into package
            try:
                obj = s3.get_object(Bucket=bucket, Key=s3_key)
                content = obj["Body"].read()
                result = create_package_document_version(
                    tenant_id=tenant_id,
                    package_id=pkg_id,
                    doc_type=doc_type,
                    content=content,
                    title=f"{doc_type.replace('_', ' ').title()}",
                    file_type=s3_key.rsplit(".", 1)[-1] if "." in s3_key else "md",
                    created_by_user_id=owner,
                    session_id=session_id,
                    change_source="backfill",
                )
                if result.success:
                    completed.append(doc_type)
                    logger.info(
                        "Backfilled %s from %s into package %s",
                        doc_type,
                        s3_key,
                        pkg_id,
                    )
            except Exception:
                logger.debug(
                    "Backfill failed for %s: %s", doc_type, s3_key, exc_info=True
                )

        if completed != list(package.get("completed_documents", [])):
            update_package(tenant_id, pkg_id, {"completed_documents": completed})
    except Exception:
        logger.debug("_backfill_completed_docs failed (non-critical)", exc_info=True)


def exec_manage_package(
    params: dict, tenant_id: str, session_id: str | None = None
) -> dict:
    """Create, read, update, list, or get checklist for acquisition packages."""
    from app.package_store import (
        clone_package,
        create_package,
        delete_package,
        get_package,
        get_package_checklist,
        list_packages,
        update_package,
    )

    operation = params.get("operation", "").strip().lower()

    if operation == "create":
        title = params.get("title") or "Acquisition Package"
        requirement_type = params.get("requirement_type") or "services"
        estimated_value = Decimal(str(params.get("estimated_value", 0)))
        owner = _extract_owner_user_id(session_id)
        result = create_package(
            tenant_id=tenant_id,
            owner_user_id=owner,
            title=title,
            requirement_type=requirement_type,
            estimated_value=estimated_value,
            session_id=session_id,
            notes=params.get("notes", ""),
            contract_vehicle=params.get("contract_vehicle") or None,
            acquisition_method=params.get("acquisition_method") or None,
            contract_type=params.get("contract_type") or None,
        )
        # Backfill: link pre-existing session documents to the new package
        _backfill_completed_docs(result, tenant_id, owner, session_id)
        return result

    if operation == "get":
        package_id = params.get("package_id")
        if not package_id:
            return {"error": "package_id is required for get operation"}
        result = get_package(tenant_id, package_id)
        if result is None:
            return {"error": f"Package {package_id} not found"}
        return result

    if operation == "update":
        package_id = params.get("package_id")
        if not package_id:
            return {"error": "package_id is required for update operation"}
        updates = params.get("updates", {})
        for field in (
            "title",
            "requirement_type",
            "estimated_value",
            "acquisition_method",
            "contract_type",
            "contract_vehicle",
            "notes",
            "status",
        ):
            value = params.get(field)
            if value and field not in updates:
                updates[field] = value
        if not updates:
            return {"error": "No update fields provided"}
        result = update_package(tenant_id, package_id, updates)
        if result is None:
            return {"error": f"Package {package_id} not found"}
        return result

    if operation == "list":
        status_filter = params.get("status") or None
        packages = list_packages(tenant_id, status=status_filter)
        return {"packages": packages, "count": len(packages)}

    if operation == "checklist":
        package_id = params.get("package_id")
        if not package_id:
            return {"error": "package_id is required for checklist operation"}
        checklist = get_package_checklist(tenant_id, package_id)
        checklist["package_id"] = package_id
        return checklist

    if operation == "delete":
        package_id = params.get("package_id")
        if not package_id:
            return {"error": "package_id is required for delete operation"}
        result = delete_package(tenant_id, package_id)
        if result is None:
            return {
                "error": (
                    f"Package {package_id} not found or cannot"
                    " be deleted (only intake/drafting)"
                ),
            }
        return {"deleted": True, "package_id": package_id, "title": result.get("title")}

    if operation == "clone":
        package_id = params.get("package_id")
        if not package_id:
            return {"error": "package_id is required for clone operation"}
        new_title = params.get("title") or None
        owner = _extract_owner_user_id(session_id)
        result = clone_package(
            tenant_id, package_id, new_title,
            owner_user_id=owner or None,
        )
        if result is None:
            return {"error": f"Source package {package_id} not found"}
        return result

    if operation == "exports":
        from app.export_store import list_exports

        package_id = params.get("package_id")
        if not package_id:
            return {"error": "package_id is required for exports operation"}
        exports = list_exports(tenant_id, package_id=package_id)
        return {"exports": exports, "count": len(exports)}

    return {
        "error": (
            f"Unknown operation: {operation}. Use create, get,"
            " update, delete, list, checklist, clone, or exports."
        )
    }


def _extract_owner_user_id(session_id: str | None) -> str:
    """Extract owner user id from scoped session id format tenant#tier#user#session."""
    if session_id and "#" in session_id:
        parts = session_id.split("#")
        if len(parts) >= 3:
            return parts[2]
    return ""
