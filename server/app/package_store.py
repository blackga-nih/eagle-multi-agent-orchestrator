"""
Package Store -- Acquisition Lifecycle CRUD
Manages PACKAGE# entities in the eagle DynamoDB single-table.

PK:  PACKAGE#{tenant_id}
SK:  PACKAGE#{package_id}
GSI: GSI1PK = TENANT#{tenant_id}, GSI1SK = PACKAGE#{status}#{created_at}
"""
import os
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import boto3
from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger("eagle.packages")

# -- Configuration ----------------------------------------------------------
TABLE_NAME = os.getenv("EAGLE_SESSIONS_TABLE", "eagle")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

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

# -- Valid updatable fields --------------------------------------------------
_UPDATABLE_FIELDS = {
    "title",
    "requirement_type",
    "estimated_value",
    "acquisition_pathway",
    "contract_vehicle",
    "status",
    "notes",
    "completed_documents",
    "far_citations",
}

# -- DynamoDB singleton ------------------------------------------------------
_dynamodb = None


def _get_dynamodb():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
    return _dynamodb


def _get_table():
    return _get_dynamodb().Table(TABLE_NAME)


# -- Internal helpers -------------------------------------------------------


def _now_iso() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


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


def _next_package_id(tenant_id: str) -> str:
    """Generate the next sequential package ID in PKG-{YYYY}-{NNNN} format.

    Queries all existing PACKAGE# items for this tenant and increments the
    highest sequence number found.  If no packages exist, starts at 0001.
    """
    year = datetime.now(timezone.utc).strftime("%Y")
    table = _get_table()

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
) -> dict:
    """Create a new acquisition package and persist it to DynamoDB.

    Automatically determines acquisition_pathway and required_documents from
    estimated_value using FAR thresholds.

    Returns the newly created package as a serialised dict.
    Raises ClientError / BotoCoreError on DynamoDB failure.
    """
    package_id = _next_package_id(tenant_id)
    pathway = _pathway_from_value(estimated_value)
    required_docs = _required_docs_for(pathway)
    now = _now_iso()

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

    _get_table().put_item(Item=item)
    logger.info("Created package %s for tenant %s", package_id, tenant_id)
    return _serialize(item)


def get_package(tenant_id: str, package_id: str) -> Optional[dict]:
    """Fetch a single package by tenant + package ID.

    Returns the serialised package dict, or None if not found.
    """
    try:
        response = _get_table().get_item(
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

    # Recalculate pathway / required_docs when estimated_value changes
    if "estimated_value" in allowed:
        new_value = Decimal(str(allowed["estimated_value"]))
        allowed["estimated_value"] = new_value

        explicit_pathway = allowed.get("acquisition_pathway")
        if explicit_pathway == "sole_source":
            new_pathway = "sole_source"
        else:
            new_pathway = _pathway_from_value(new_value)
            allowed["acquisition_pathway"] = new_pathway

        if "required_documents" not in updates:
            allowed["required_documents"] = _required_docs_for(new_pathway)

    now = _now_iso()
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
        response = _get_table().update_item(
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
    table = _get_table()

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
        {"status": "approved", "approved_at": _now_iso()},
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

