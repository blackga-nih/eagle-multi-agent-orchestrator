"""Skill Store -- DynamoDB-backed SKILL# entity CRUD with lifecycle management.

SKILL# items represent user-created custom skills with a draft->review->active lifecycle.
Tenants can define their own skills that integrate with the EAGLE supervisor routing.

Entity format:
    PK:  SKILL#{tenant_id}
    SK:  SKILL#{skill_id}

GSI2:
    GSI2PK:  SKILL_STATUS#{status}
    GSI2SK:  TENANT#{tenant_id}#{skill_id}

Status lifecycle:
    draft -> review -> active -> disabled
    draft or disabled -> (deleted)
"""
import os
import time
import uuid
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from boto3.dynamodb.conditions import Attr, Key

logger = logging.getLogger("eagle.skill_store")

# -- Configuration -----------------------------------------------------------
TABLE_NAME = os.getenv("EAGLE_SESSIONS_TABLE", "eagle")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# -- Allowed statuses --------------------------------------------------------
_VALID_STATUSES = {"draft", "review", "active", "disabled"}

# -- Fields callers may update via update_skill() ----------------------------
_UPDATABLE_FIELDS = {
    "name",
    "display_name",
    "description",
    "prompt_body",
    "triggers",
    "tools",
    "model",
    "visibility",
}

# -- DynamoDB singleton (lazy, same pattern as plugin_store.py) --------------
_dynamodb = None


def _get_dynamodb():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
    return _dynamodb


def _get_table():
    return _get_dynamodb().Table(TABLE_NAME)


# -- In-Process Cache (60-second TTL, keyed by "{tenant_id}#{skill_id}") -----
_skill_cache: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SECONDS = 60


def _cache_key(tenant_id: str, skill_id: str) -> str:
    return f"{tenant_id}#{skill_id}"


def _cache_get(tenant_id: str, skill_id: str) -> Optional[Dict[str, Any]]:
    """Return cached item if still within TTL, else None."""
    key = _cache_key(tenant_id, skill_id)
    entry = _skill_cache.get(key)
    if entry and time.time() < entry["ts"] + CACHE_TTL_SECONDS:
        return entry["item"]
    return None


def _cache_set(tenant_id: str, skill_id: str, item: Dict[str, Any]) -> None:
    key = _cache_key(tenant_id, skill_id)
    _skill_cache[key] = {"ts": time.time(), "item": item}


def _cache_invalidate(tenant_id: str, skill_id: str) -> None:
    _skill_cache.pop(_cache_key(tenant_id, skill_id), None)


# -- Internal helpers --------------------------------------------------------


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _build_item(
    tenant_id: str,
    skill_id: str,
    owner_user_id: str,
    name: str,
    display_name: str,
    description: str,
    prompt_body: str,
    triggers: Optional[List[str]],
    tools: Optional[List[str]],
    model: Optional[str],
    status: str,
    visibility: str,
    version: int,
    created_at: str,
    updated_at: str,
    published_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Assemble a full DynamoDB item dict including GSI2 keys."""
    item: Dict[str, Any] = {
        "PK": f"SKILL#{tenant_id}",
        "SK": f"SKILL#{skill_id}",
        "skill_id": skill_id,
        "tenant_id": tenant_id,
        "owner_user_id": owner_user_id,
        "name": name,
        "display_name": display_name,
        "description": description,
        "prompt_body": prompt_body,
        "triggers": triggers or [],
        "tools": tools or [],
        "status": status,
        "visibility": visibility,
        "version": version,
        "created_at": created_at,
        "updated_at": updated_at,
        # GSI2 keys for status-based queries
        "GSI2PK": f"SKILL_STATUS#{status}",
        "GSI2SK": f"TENANT#{tenant_id}#{skill_id}",
    }
    if model is not None:
        item["model"] = model
    if published_at is not None:
        item["published_at"] = published_at
    return item


# -- Public API --------------------------------------------------------------


def create_skill(
    tenant_id: str,
    owner_user_id: str,
    name: str,
    display_name: str,
    description: str,
    prompt_body: str,
    triggers: Optional[List[str]] = None,
    tools: Optional[List[str]] = None,
    model: Optional[str] = None,
    visibility: str = "private",
) -> Dict[str, Any]:
    """Create a new custom skill in draft status.

    Generates a uuid4 skill_id, sets status="draft" and version=1.
    Returns the persisted item dict.
    """
    skill_id = str(uuid.uuid4())
    now = _now_iso()

    item = _build_item(
        tenant_id=tenant_id,
        skill_id=skill_id,
        owner_user_id=owner_user_id,
        name=name,
        display_name=display_name,
        description=description,
        prompt_body=prompt_body,
        triggers=triggers,
        tools=tools,
        model=model,
        status="draft",
        visibility=visibility,
        version=1,
        created_at=now,
        updated_at=now,
    )

    try:
        _get_table().put_item(Item=item)
        _cache_set(tenant_id, skill_id, item)
        logger.debug("skill_store.create_skill: [%s/%s] created", tenant_id, skill_id)
    except (ClientError, BotoCoreError) as exc:
        logger.error("skill_store.create_skill failed [%s]: %s", tenant_id, exc)
        raise

    return item


def get_skill(tenant_id: str, skill_id: str) -> Optional[Dict[str, Any]]:
    """Fetch a single skill by tenant and skill_id.

    Returns the item dict or None if not found.
    Serves from 60-second cache when fresh.
    """
    cached = _cache_get(tenant_id, skill_id)
    if cached is not None:
        return cached

    try:
        response = _get_table().get_item(
            Key={
                "PK": f"SKILL#{tenant_id}",
                "SK": f"SKILL#{skill_id}",
            }
        )
        item = response.get("Item")
        if item:
            item = dict(item)
            _cache_set(tenant_id, skill_id, item)
            return item
        return None
    except (ClientError, BotoCoreError) as exc:
        logger.error("skill_store.get_skill failed [%s/%s]: %s", tenant_id, skill_id, exc)
        return None


def update_skill(
    tenant_id: str,
    skill_id: str,
    updates: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Apply a partial update to a skill's mutable fields.

    Only fields in _UPDATABLE_FIELDS are applied; all others are silently ignored.
    Increments version and refreshes updated_at.
    Returns the updated item dict, or None if the skill does not exist.
    """
    existing = get_skill(tenant_id, skill_id)
    if existing is None:
        logger.warning("skill_store.update_skill: skill not found [%s/%s]", tenant_id, skill_id)
        return None

    # Merge only allowed fields
    allowed_updates = {k: v for k, v in updates.items() if k in _UPDATABLE_FIELDS}
    if not allowed_updates:
        logger.debug(
            "skill_store.update_skill: no updatable fields supplied for [%s/%s]",
            tenant_id,
            skill_id,
        )
        return existing

    updated = dict(existing)
    updated.update(allowed_updates)
    updated["version"] = existing.get("version", 1) + 1
    updated["updated_at"] = _now_iso()

    # Rebuild GSI2 keys -- status is unchanged here but keep consistent
    updated["GSI2PK"] = f"SKILL_STATUS#{updated['status']}"
    updated["GSI2SK"] = f"TENANT#{tenant_id}#{skill_id}"

    try:
        _get_table().put_item(Item=updated)
        _cache_set(tenant_id, skill_id, updated)
        logger.debug(
            "skill_store.update_skill: [%s/%s] v%s", tenant_id, skill_id, updated["version"]
        )
    except (ClientError, BotoCoreError) as exc:
        logger.error("skill_store.update_skill failed [%s/%s]: %s", tenant_id, skill_id, exc)
        return None

    return updated


def _transition_status(
    tenant_id: str,
    skill_id: str,
    from_status: str,
    to_status: str,
    set_published_at: bool = False,
) -> Optional[Dict[str, Any]]:
    """Internal helper: transition skill status if current status matches from_status."""
    existing = get_skill(tenant_id, skill_id)
    if existing is None:
        logger.warning(
            "skill_store._transition_status: skill not found [%s/%s]", tenant_id, skill_id
        )
        return None

    current = existing.get("status")
    if current != from_status:
        logger.warning(
            "skill_store._transition_status: expected status=%s but got %s [%s/%s]",
            from_status,
            current,
            tenant_id,
            skill_id,
        )
        return None

    updated = dict(existing)
    updated["status"] = to_status
    updated["version"] = existing.get("version", 1) + 1
    updated["updated_at"] = _now_iso()
    updated["GSI2PK"] = f"SKILL_STATUS#{to_status}"
    updated["GSI2SK"] = f"TENANT#{tenant_id}#{skill_id}"

    if set_published_at:
        updated["published_at"] = updated["updated_at"]

    try:
        _get_table().put_item(Item=updated)
        _cache_invalidate(tenant_id, skill_id)
        _cache_set(tenant_id, skill_id, updated)
        logger.debug(
            "skill_store: status %s->%s [%s/%s]", from_status, to_status, tenant_id, skill_id
        )
    except (ClientError, BotoCoreError) as exc:
        logger.error(
            "skill_store._transition_status failed [%s/%s]: %s", tenant_id, skill_id, exc
        )
        return None

    return updated


def submit_for_review(tenant_id: str, skill_id: str) -> Optional[Dict[str, Any]]:
    """Transition skill from draft -> review.

    Returns the updated item or None if the skill does not exist or is not in draft status.
    """
    return _transition_status(tenant_id, skill_id, from_status="draft", to_status="review")


def publish_skill(tenant_id: str, skill_id: str) -> Optional[Dict[str, Any]]:
    """Transition skill from review -> active and record published_at.

    Returns the updated item or None if the skill does not exist or is not in review status.
    """
    return _transition_status(
        tenant_id, skill_id, from_status="review", to_status="active", set_published_at=True
    )


def disable_skill(tenant_id: str, skill_id: str) -> Optional[Dict[str, Any]]:
    """Transition skill from active -> disabled.

    Returns the updated item or None if the skill does not exist or is not in active status.
    """
    return _transition_status(tenant_id, skill_id, from_status="active", to_status="disabled")


def delete_skill(tenant_id: str, skill_id: str) -> bool:
    """Permanently delete a skill. Only permitted when status is draft or disabled.

    Returns True on success, False if the skill does not exist or its status prevents deletion.
    """
    existing = get_skill(tenant_id, skill_id)
    if existing is None:
        logger.warning("skill_store.delete_skill: skill not found [%s/%s]", tenant_id, skill_id)
        return False

    current_status = existing.get("status")
    if current_status not in {"draft", "disabled"}:
        logger.warning(
            "skill_store.delete_skill: cannot delete skill with status=%s [%s/%s]",
            current_status,
            tenant_id,
            skill_id,
        )
        return False

    try:
        _get_table().delete_item(
            Key={
                "PK": f"SKILL#{tenant_id}",
                "SK": f"SKILL#{skill_id}",
            }
        )
        _cache_invalidate(tenant_id, skill_id)
        logger.debug("skill_store.delete_skill: deleted [%s/%s]", tenant_id, skill_id)
        return True
    except (ClientError, BotoCoreError) as exc:
        logger.error("skill_store.delete_skill failed [%s/%s]: %s", tenant_id, skill_id, exc)
        return False


def list_skills(
    tenant_id: str,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return all skills for a tenant, with optional status filter.

    Queries DynamoDB by PK = SKILL#{tenant_id} and applies an optional
    filter-expression status filter.
    """
    try:
        table = _get_table()
        if status is not None:
            response = table.query(
                KeyConditionExpression=(
                    Key("PK").eq(f"SKILL#{tenant_id}")
                    & Key("SK").begins_with("SKILL#")
                ),
                FilterExpression=Attr("status").eq(status),
            )
        else:
            response = table.query(
                KeyConditionExpression=(
                    Key("PK").eq(f"SKILL#{tenant_id}")
                    & Key("SK").begins_with("SKILL#")
                ),
            )
        return [dict(item) for item in response.get("Items", [])]
    except (ClientError, BotoCoreError) as exc:
        logger.error("skill_store.list_skills failed [%s]: %s", tenant_id, exc)
        return []


def list_active_skills(tenant_id: str) -> List[Dict[str, Any]]:
    """Return only active skills for a tenant.

    Attempts a GSI2 query on GSI2PK = SKILL_STATUS#active filtered by tenant prefix.
    Falls back to a full tenant query with status filter if the GSI is unavailable.
    """
    try:
        table = _get_table()
        response = table.query(
            IndexName="GSI2",
            KeyConditionExpression=(
                Key("GSI2PK").eq("SKILL_STATUS#active")
                & Key("GSI2SK").begins_with(f"TENANT#{tenant_id}#")
            ),
        )
        return [dict(item) for item in response.get("Items", [])]
    except (ClientError, BotoCoreError) as exc:
        # GSI may not exist in all environments -- fall back gracefully
        logger.warning(
            "skill_store.list_active_skills: GSI2 query failed (%s), falling back to filter",
            exc,
        )
        return list_skills(tenant_id, status="active")
