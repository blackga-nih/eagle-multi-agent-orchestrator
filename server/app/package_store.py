"""
Package Store -- Acquisition Lifecycle CRUD
Manages PACKAGE# entities in the eagle DynamoDB single-table.

PK:  PACKAGE#{tenant_id}
SK:  PACKAGE#{package_id}
GSI: GSI1PK = TENANT#{tenant_id}, GSI1SK = PACKAGE#{status}#{created_at}
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import BotoCoreError, ClientError

from .db_client import get_table, now_iso

logger = logging.getLogger("eagle.packages")

# -- FAR Thresholds ---------------------------------------------------------
_MICRO_PURCHASE_THRESHOLD = Decimal("10000")
_SIMPLIFIED_THRESHOLD = Decimal("250000")

# -- Required documents by acquisition pathway ------------------------------
_REQUIRED_DOCS: dict[str, list[str]] = {
    "micro_purchase": [],
    "simplified": ["igce"],
    "full_competition": ["sow", "igce", "market-research", "acquisition-plan"],
    "sole_source": ["sow", "igce", "justification"],
}

# -- Compliance matrix document name → package slug -------------------------
_COMPLIANCE_DOC_TO_SLUG: dict[str, str] = {
    "SOW / PWS": "sow",
    "Statement of Need (SON)": "sow",
    "IGCE": "igce",
    "Market Research Report": "market-research",
    "Market Research": "market-research",
    "Acquisition Plan": "acquisition-plan",
    "J&A / Justification": "justification",
    "D&F (Determination & Findings)": "d-f",
    "Source Selection Plan": "source-selection-plan",
    "Subcontracting Plan": "subcontracting-plan",
    "QASP": "qasp",
    "HHS-653 Small Business Review": "sb-review",
    "Purchase Request": "purchase-request",
    "IT Security & Privacy Certification": "security-checklist",
    "Section 508 ICT Evaluation": "section-508",
    "Human Subjects Provisions": "human-subjects",
}

# -- Valid updatable fields --------------------------------------------------
_UPDATABLE_FIELDS = {
    "title",
    "requirement_type",
    "estimated_value",
    "acquisition_pathway",
    "acquisition_method",
    "contract_type",
    "flags",
    "contract_vehicle",
    "status",
    "notes",
    "completed_documents",
    "far_citations",
}

# -- Internal helpers -------------------------------------------------------


def _pathway_from_value(estimated_value: Decimal) -> str:
    """Determine acquisition pathway from FAR dollar thresholds.

    sole_source is never auto-determined; it must be set explicitly by the
    caller via an update_package call.
    """
    if estimated_value < _MICRO_PURCHASE_THRESHOLD:
        return "micro_purchase"
    if estimated_value < _SIMPLIFIED_THRESHOLD:
        return "simplified"
    return "full_competition"


def _required_docs_for(pathway: str) -> list[str]:
    """Return list of required document types for the given pathway."""
    return list(_REQUIRED_DOCS.get(pathway, []))


def compute_required_docs(
    estimated_value: float,
    acquisition_method: str,
    contract_type: str,
    flags: dict | None = None,
) -> list[str]:
    """Compute required document slugs via the compliance matrix.

    Calls ``compliance_matrix.get_requirements()`` and maps the resulting
    ``documents_required`` entries (where ``required=True``) to package slugs.
    Falls back to the static ``_required_docs_for()`` on any error.
    """
    try:
        from .compliance_matrix import get_requirements

        result = get_requirements(
            contract_value=estimated_value,
            acquisition_method=acquisition_method,
            contract_type=contract_type,
            flags=flags,
        )

        if result.get("errors"):
            # Compliance matrix returned validation errors — fall back
            pathway = _pathway_from_value(Decimal(str(estimated_value)))
            return _required_docs_for(pathway)

        slugs: list[str] = []
        seen: set[str] = set()
        for doc in result.get("documents_required", []):
            if not doc.get("required"):
                continue
            slug = _COMPLIANCE_DOC_TO_SLUG.get(doc["name"])
            if slug and slug not in seen:
                slugs.append(slug)
                seen.add(slug)

        return slugs
    except Exception:
        logger.exception("compute_required_docs failed, falling back to static")
        pathway = _pathway_from_value(Decimal(str(estimated_value)))
        return _required_docs_for(pathway)


def _generate_descriptive_title(
    title: str,
    requirement_type: str | None = None,
    estimated_value: Decimal | None = None,
    contract_vehicle: str | None = None,
) -> str:
    """Build a descriptive package title from metadata.

    Only replaces generic titles (< 30 chars or exactly "Acquisition Package").
    Preserves user-provided specific titles.  Stores the original as
    ``original_title`` on the item (handled by the caller).
    """
    if len(title) >= 30 and title != "Acquisition Package":
        return title

    parts: list[str] = []

    # Type label
    label = (requirement_type or "Acquisition").replace("_", " ").title()
    parts.append(label)

    # Formatted value
    if estimated_value is not None:
        val = float(estimated_value)
        if val >= 1_000_000:
            parts.append(f"${val / 1_000_000:.1f}M")
        elif val >= 1_000:
            parts.append(f"${val / 1_000:.0f}K")
        elif val > 0:
            parts.append(f"${val:,.0f}")

    desc = " — ".join(parts)
    if contract_vehicle:
        desc += f" [{contract_vehicle}]"

    return desc


def _has_unfilled_markers(content: str) -> list[str]:
    """Return list of unfilled ``{{PLACEHOLDER}}`` markers found in content."""
    if not content:
        return []
    return re.findall(r"\{\{[A-Z_]{3,}\}\}", content)


def _next_package_id(tenant_id: str) -> str:
    """Generate the next sequential package ID in PKG-{YYYY}-{NNNN} format.

    Queries all existing PACKAGE# items for this tenant and increments the
    highest sequence number found.  If no packages exist, starts at 0001.
    """
    year = datetime.now(timezone.utc).strftime("%Y")
    table = get_table()

    try:
        response = table.query(
            KeyConditionExpression=Key("PK").eq(f"PACKAGE#{tenant_id}")
            & Key("SK").begins_with("PACKAGE#PKG-"),
        )
    except (ClientError, BotoCoreError):
        logger.exception(
            "Failed to list packages for ID generation (tenant=%s)", tenant_id
        )
        response = {"Items": []}

    max_seq = 0
    prefix = f"PKG-{year}-"
    for item in response.get("Items", []):
        pkg_id: str = item.get("package_id", "")
        if pkg_id.startswith(prefix):
            try:
                seq = int(pkg_id[len(prefix):])
                if seq > max_seq:
                    max_seq = seq
            except ValueError:
                pass

    return f"PKG-{year}-{max_seq + 1:04d}"


def _serialize(item: dict) -> dict:
    """Return a plain dict safe for JSON serialisation (Decimal -> str)."""
    out: dict = {}
    for k, v in item.items():
        if isinstance(v, Decimal):
            out[k] = str(v)
        elif isinstance(v, list):
            out[k] = v
        else:
            out[k] = v
    return out


# -- Public CRUD ------------------------------------------------------------


def create_package(
    tenant_id: str,
    owner_user_id: str,
    title: str,
    requirement_type: str,
    estimated_value: Decimal,
    session_id: Optional[str] = None,
    notes: str = "",
    contract_vehicle: Optional[str] = None,
    acquisition_method: Optional[str] = None,
    contract_type: Optional[str] = None,
    flags: Optional[dict] = None,
) -> dict:
    """Create a new acquisition package and persist it to DynamoDB.

    When ``acquisition_method`` and ``contract_type`` are provided, uses the
    compliance matrix to compute dynamic required documents.  Otherwise
    falls back to the static FAR-threshold-based pathway.

    Returns the newly created package as a serialised dict.
    Raises ClientError / BotoCoreError on DynamoDB failure.
    """
    package_id = _next_package_id(tenant_id)
    pathway = _pathway_from_value(estimated_value)

    # Dynamic docs via compliance matrix when method+type available
    if acquisition_method and contract_type:
        required_docs = compute_required_docs(
            float(estimated_value), acquisition_method, contract_type, flags
        )
    else:
        required_docs = _required_docs_for(pathway)

    # Descriptive title
    original_title = title
    title = _generate_descriptive_title(
        title, requirement_type, estimated_value, contract_vehicle
    )

    now = now_iso()

    item: dict = {
        "PK": f"PACKAGE#{tenant_id}",
        "SK": f"PACKAGE#{package_id}",
        # GSI attributes
        "GSI1PK": f"TENANT#{tenant_id}",
        "GSI1SK": f"PACKAGE#intake#{now}",
        # Entity attributes
        "package_id": package_id,
        "tenant_id": tenant_id,
        "owner_user_id": owner_user_id,
        "title": title,
        "original_title": original_title,
        "requirement_type": requirement_type,
        "estimated_value": estimated_value,
        "acquisition_pathway": pathway,
        "status": "intake",
        "required_documents": required_docs,
        "completed_documents": [],
        "far_citations": [],
        "notes": notes,
        "created_at": now,
        "updated_at": now,
    }

    if contract_vehicle is not None:
        item["contract_vehicle"] = contract_vehicle
    if session_id is not None:
        item["session_id"] = session_id
    if acquisition_method is not None:
        item["acquisition_method"] = acquisition_method
    if contract_type is not None:
        item["contract_type"] = contract_type
    if flags is not None:
        item["flags"] = flags

    get_table().put_item(Item=item)
    logger.info("Created package %s for tenant %s", package_id, tenant_id)
    return _serialize(item)


def get_package(tenant_id: str, package_id: str) -> Optional[dict]:
    """Fetch a single package by tenant + package ID.

    Returns the serialised package dict, or None if not found.
    """
    try:
        response = get_table().get_item(
            Key={
                "PK": f"PACKAGE#{tenant_id}",
                "SK": f"PACKAGE#{package_id}",
            }
        )
    except (ClientError, BotoCoreError):
        logger.exception(
            "get_package failed (tenant=%s, pkg=%s)", tenant_id, package_id
        )
        return None

    item = response.get("Item")
    if not item:
        return None
    return _serialize(item)


def update_package(
    tenant_id: str, package_id: str, updates: dict
) -> Optional[dict]:
    """Apply a partial update to an existing package.

    Only fields in _UPDATABLE_FIELDS are accepted; others are silently
    ignored.  When estimated_value is updated, acquisition_pathway and
    required_documents are recalculated unless the caller explicitly sets
    acquisition_pathway to sole_source.

    Returns the updated package dict, or None if the item does not exist.
    Raises ClientError / BotoCoreError on unexpected DynamoDB errors.
    """
    existing = get_package(tenant_id, package_id)
    if existing is None:
        return None

    allowed = {k: v for k, v in updates.items() if k in _UPDATABLE_FIELDS}
    if not allowed:
        logger.debug(
            "update_package: no updatable fields supplied; returning existing item"
        )
        return existing

    # Recalculate pathway / required_docs when key fields change
    recalc_triggers = {"estimated_value", "acquisition_method", "contract_type"}
    if recalc_triggers & allowed.keys():
        if "estimated_value" in allowed:
            new_value = Decimal(str(allowed["estimated_value"]))
            allowed["estimated_value"] = new_value
        else:
            new_value = Decimal(str(existing.get("estimated_value", 0)))

        explicit_pathway = allowed.get("acquisition_pathway")
        if explicit_pathway == "sole_source":
            new_pathway = "sole_source"
        else:
            new_pathway = _pathway_from_value(new_value)
            allowed["acquisition_pathway"] = new_pathway

        if "required_documents" not in updates:
            # Prefer dynamic calculation when method+type are available
            method = allowed.get("acquisition_method") or existing.get("acquisition_method")
            ctype = allowed.get("contract_type") or existing.get("contract_type")
            flags = allowed.get("flags") or existing.get("flags")
            if method and ctype:
                allowed["required_documents"] = compute_required_docs(
                    float(new_value), method, ctype, flags
                )
            else:
                allowed["required_documents"] = _required_docs_for(new_pathway)

    now = now_iso()
    allowed["updated_at"] = now

    # Keep GSI1SK consistent with current (or new) status
    target_status = allowed.get("status", existing.get("status", "intake"))
    created_at = existing.get("created_at", now)
    allowed["GSI1SK"] = f"PACKAGE#{target_status}#{created_at}"

    # Propagate approved_at if the caller included it
    if "approved_at" in updates:
        allowed["approved_at"] = updates["approved_at"]

    # Build UpdateExpression dynamically
    expr_parts: list[str] = []
    expr_names: dict[str, str] = {}
    expr_values: dict[str, object] = {}

    for i, (field, value) in enumerate(allowed.items()):
        name_ph = f"#f{i}"
        val_ph = f":v{i}"
        expr_names[name_ph] = field
        expr_values[val_ph] = value
        expr_parts.append(f"{name_ph} = {val_ph}")

    update_expression = "SET " + ", ".join(expr_parts)

    try:
        response = get_table().update_item(
            Key={
                "PK": f"PACKAGE#{tenant_id}",
                "SK": f"PACKAGE#{package_id}",
            },
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expr_names,
            ExpressionAttributeValues=expr_values,
            ConditionExpression=Attr("PK").exists(),
            ReturnValues="ALL_NEW",
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            logger.warning(
                "update_package: item not found (tenant=%s, pkg=%s)",
                tenant_id,
                package_id,
            )
            return None
        logger.exception(
            "update_package failed (tenant=%s, pkg=%s)", tenant_id, package_id
        )
        raise
    except BotoCoreError:
        logger.exception(
            "update_package boto core error (tenant=%s, pkg=%s)",
            tenant_id,
            package_id,
        )
        raise

    return _serialize(response["Attributes"])


def list_packages(
    tenant_id: str,
    status: Optional[str] = None,
    owner_user_id: Optional[str] = None,
) -> list[dict]:
    """List acquisition packages for a tenant.

    Uses GSI1 (TENANT# PK) for efficient tenant-scoped queries.
    When status is provided the GSI1SK begins_with filter narrows the result
    set before any Python-side owner filter is applied.

    Returns a list of serialised package dicts (may be empty).
    """
    table = get_table()

    try:
        if status:
            response = table.query(
                IndexName="GSI1",
                KeyConditionExpression=Key("GSI1PK").eq(f"TENANT#{tenant_id}")
                & Key("GSI1SK").begins_with(f"PACKAGE#{status}#"),
            )
        else:
            response = table.query(
                IndexName="GSI1",
                KeyConditionExpression=Key("GSI1PK").eq(f"TENANT#{tenant_id}")
                & Key("GSI1SK").begins_with("PACKAGE#"),
            )
    except (ClientError, BotoCoreError):
        logger.exception("list_packages failed (tenant=%s)", tenant_id)
        return []

    items = response.get("Items", [])

    if owner_user_id:
        items = [i for i in items if i.get("owner_user_id") == owner_user_id]

    return [_serialize(i) for i in items]


def get_package_checklist(tenant_id: str, package_id: str) -> dict:
    """Return a checklist showing required, completed, and missing documents.

    Returns:
        {
            "required":  list[str],
            "completed": list[str],
            "missing":   list[str],
            "complete":  bool,
        }

    If the package is not found, returns an empty checklist with complete=False.
    """
    pkg = get_package(tenant_id, package_id)
    if pkg is None:
        logger.warning(
            "get_package_checklist: package not found (tenant=%s, pkg=%s)",
            tenant_id,
            package_id,
        )
        return {"required": [], "completed": [], "missing": [], "complete": False}

    required: list[str] = pkg.get("required_documents") or []
    completed: list[str] = pkg.get("completed_documents") or []
    completed_set = set(completed)
    missing = [doc for doc in required if doc not in completed_set]

    return {
        "required": required,
        "completed": completed,
        "missing": missing,
        "complete": len(missing) == 0,
    }


def submit_package(tenant_id: str, package_id: str) -> Optional[dict]:
    """Advance package status from drafting to review.

    Returns the updated package dict, or None if not found or in an
    incompatible state.
    """
    pkg = get_package(tenant_id, package_id)
    if pkg is None:
        logger.warning(
            "submit_package: not found (tenant=%s, pkg=%s)", tenant_id, package_id
        )
        return None

    if pkg.get("status") != "drafting":
        logger.warning(
            "submit_package: invalid transition from %r (tenant=%s, pkg=%s)",
            pkg.get("status"),
            tenant_id,
            package_id,
        )
        return None

    return update_package(tenant_id, package_id, {"status": "review"})


def approve_package(tenant_id: str, package_id: str) -> Optional[dict]:
    """Advance package status from review to approved and stamp approved_at.

    Returns the updated package dict, or None if not found or in an
    incompatible state.
    """
    pkg = get_package(tenant_id, package_id)
    if pkg is None:
        logger.warning(
            "approve_package: not found (tenant=%s, pkg=%s)", tenant_id, package_id
        )
        return None

    if pkg.get("status") != "review":
        logger.warning(
            "approve_package: invalid transition from %r (tenant=%s, pkg=%s)",
            pkg.get("status"),
            tenant_id,
            package_id,
        )
        return None

    return update_package(
        tenant_id,
        package_id,
        {"status": "approved", "approved_at": now_iso()},
    )


def close_package(tenant_id: str, package_id: str) -> Optional[dict]:
    """Advance package status from awarded to closed.

    Returns the updated package dict, or None if not found or in an
    incompatible state.
    """
    pkg = get_package(tenant_id, package_id)
    if pkg is None:
        logger.warning(
            "close_package: not found (tenant=%s, pkg=%s)", tenant_id, package_id
        )
        return None

    if pkg.get("status") != "awarded":
        logger.warning(
            "close_package: invalid transition from %r (tenant=%s, pkg=%s)",
            pkg.get("status"),
            tenant_id,
            package_id,
        )
        return None

    return update_package(tenant_id, package_id, {"status": "closed"})


def validate_package_completeness(tenant_id: str, package_id: str) -> dict:
    """AI-powered completeness check for an acquisition package.

    Returns a validation report with readiness status, missing documents,
    draft documents, unfilled template markers, and compliance warnings.
    """
    from .document_store import list_package_documents

    pkg = get_package(tenant_id, package_id)
    if pkg is None:
        return {"error": "Package not found", "ready": False}

    # Fetch documents
    docs = list_package_documents(tenant_id, package_id)
    doc_map: dict[str, dict] = {d.get("doc_type", ""): d for d in docs}

    required: list[str] = pkg.get("required_documents") or []
    completed: list[str] = pkg.get("completed_documents") or []
    completed_set = set(completed)

    # 1. Missing documents — required but not present
    missing_documents = [r for r in required if r not in completed_set]

    # 2. Draft documents — present but not finalized
    draft_documents: list[str] = []
    for doc_type in required:
        doc = doc_map.get(doc_type)
        if doc and doc.get("status") not in ("final", "approved"):
            draft_documents.append(doc_type)

    # 3. Unfilled template markers
    unfilled_templates: list[dict] = []
    for doc_type, doc in doc_map.items():
        content = doc.get("content") or doc.get("preview") or ""
        markers = _has_unfilled_markers(content)
        if markers:
            unfilled_templates.append({
                "doc_type": doc_type,
                "markers": markers[:10],  # cap at 10
            })

    # 4. Compliance warnings via compliance matrix
    compliance_warnings: list[str] = []
    method = pkg.get("acquisition_method")
    ctype = pkg.get("contract_type")
    if method and ctype:
        try:
            from .compliance_matrix import get_requirements

            result = get_requirements(
                contract_value=float(pkg.get("estimated_value", 0)),
                acquisition_method=method,
                contract_type=ctype,
                flags=pkg.get("flags"),
            )
            compliance_warnings = result.get("warnings", [])
        except Exception:
            logger.debug("Could not run compliance check for validation")

    total_required = len(required)
    total_completed = len(completed_set & set(required))
    ready = (
        len(missing_documents) == 0
        and len(draft_documents) == 0
        and len(unfilled_templates) == 0
    )

    recommendation = "Package is complete and ready for submission." if ready else (
        "Package has outstanding items. "
        + (f"{len(missing_documents)} missing document(s). " if missing_documents else "")
        + (f"{len(draft_documents)} document(s) still in draft. " if draft_documents else "")
        + (f"{len(unfilled_templates)} document(s) with unfilled placeholders." if unfilled_templates else "")
    ).strip()

    return {
        "ready": ready,
        "missing_documents": missing_documents,
        "draft_documents": draft_documents,
        "unfilled_templates": unfilled_templates,
        "compliance_warnings": compliance_warnings,
        "recommendation": recommendation,
        "total_required": total_required,
        "total_completed": total_completed,
    }

