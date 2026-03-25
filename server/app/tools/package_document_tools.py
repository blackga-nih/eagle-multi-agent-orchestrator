"""Active package/document tool handlers.

This module owns the package/document management handlers that were previously
hosted inside ``agentic_service``. Active runtimes should use these functions
through the compatibility dispatch layer while the broader migration continues.
"""

from __future__ import annotations

from decimal import Decimal


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
    from app.document_store import get_document

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
            result["submit_error"] = "Package could not be submitted (may not be in drafting status)"

    return result


def exec_manage_package(params: dict, tenant_id: str, session_id: str | None = None) -> dict:
    """Create, read, update, list, or get checklist for acquisition packages."""
    from app.package_store import (
        create_package,
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
        return create_package(
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

    return {"error": f"Unknown operation: {operation}. Use create, get, update, list, or checklist."}


def _extract_owner_user_id(session_id: str | None) -> str:
    """Extract owner user id from scoped session id format tenant#tier#user#session."""
    if session_id and "#" in session_id:
        parts = session_id.split("#")
        if len(parts) >= 3:
            return parts[2]
    return ""
