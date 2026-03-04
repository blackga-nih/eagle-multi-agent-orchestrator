"""Workspace Store — DynamoDB-backed WORKSPACE# entity CRUD with auto-provisioning.

WORKSPACE# items represent named, isolated prompt environments per user.
Every user has at least one workspace (the Default workspace, auto-provisioned
on first use). Only one workspace is active at a time per user.

Entity format:
    PK:  WORKSPACE#{tenant_id}#{user_id}
    SK:  WORKSPACE#{workspace_id}

GSI1 projection:
    GSI1PK: TENANT#{tenant_id}
    GSI1SK: WORKSPACE#{user_id}#{workspace_id}
"""
import os
import time
import uuid
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError, BotoCoreError

logger = logging.getLogger("eagle.workspace_store")

# ── Configuration ─────────────────────────────────────────────────────
TABLE_NAME = os.getenv("EAGLE_SESSIONS_TABLE", "eagle")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# ── DynamoDB Client (lazy singleton) ─────────────────────────────────
_dynamodb = None


def _get_dynamodb():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
    return _dynamodb


def _get_table():
    return _get_dynamodb().Table(TABLE_NAME)


# ── Workspace Cache (60s TTL) ────────────────────────────────────────
_workspace_cache: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SECONDS = 60


def _ws_cache_key(tenant_id: str, user_id: str) -> str:
    return f"{tenant_id}#{user_id}"


def _ws_cache_get(tenant_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    key = _ws_cache_key(tenant_id, user_id)
    entry = _workspace_cache.get(key)
    if entry and time.time() < entry["ts"] + CACHE_TTL_SECONDS:
        return entry["item"]
    return None


def _ws_cache_set(tenant_id: str, user_id: str, item: Dict[str, Any]) -> None:
    _workspace_cache[_ws_cache_key(tenant_id, user_id)] = {"ts": time.time(), "item": item}


def _ws_cache_invalidate(tenant_id: str, user_id: str) -> None:
    _workspace_cache.pop(_ws_cache_key(tenant_id, user_id), None)


# ── CRUD ─────────────────────────────────────────────────────────────

def create_workspace(
    tenant_id: str,
    user_id: str,
    name: str = "Default",
    description: str = "",
    is_default: bool = False,
    is_active: bool = True,
    base_workspace_id: Optional[str] = None,
    visibility: str = "private",
    workspace_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new workspace for a user.

    Returns the workspace item dict.  Automatically deactivates all other
    workspaces for this user when ``is_active=True``.
    """
    wid = workspace_id or str(uuid.uuid4())
    now = datetime.utcnow().isoformat()

    if is_active:
        _deactivate_all(tenant_id, user_id)
        _ws_cache_invalidate(tenant_id, user_id)

    item: Dict[str, Any] = {
        "PK": f"WORKSPACE#{tenant_id}#{user_id}",
        "SK": f"WORKSPACE#{wid}",
        "workspace_id": wid,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "name": name,
        "description": description,
        "is_active": is_active,
        "is_default": is_default,
        "visibility": visibility,
        "override_count": 0,
        "created_at": now,
        "updated_at": now,
        # GSI1: list workspaces per tenant (all users)
        "GSI1PK": f"TENANT#{tenant_id}",
        "GSI1SK": f"WORKSPACE#{user_id}#{wid}",
    }
    if base_workspace_id:
        item["base_workspace_id"] = base_workspace_id

    try:
        _get_table().put_item(Item=item)
        logger.debug("workspace_store.create: [%s/%s] %s", tenant_id, user_id, name)
    except (ClientError, BotoCoreError) as e:
        logger.error("workspace_store.create failed [%s/%s]: %s", tenant_id, user_id, e)

    return item


def get_workspace(
    tenant_id: str,
    user_id: str,
    workspace_id: str,
) -> Optional[Dict[str, Any]]:
    """Fetch a workspace by ID.  Returns None if not found."""
    try:
        resp = _get_table().get_item(
            Key={
                "PK": f"WORKSPACE#{tenant_id}#{user_id}",
                "SK": f"WORKSPACE#{workspace_id}",
            }
        )
        item = resp.get("Item")
        return dict(item) if item else None
    except (ClientError, BotoCoreError) as e:
        logger.error("workspace_store.get failed [%s]: %s", workspace_id, e)
        return None


def list_workspaces(tenant_id: str, user_id: str) -> List[Dict[str, Any]]:
    """Return all workspaces for a user, sorted by updated_at descending."""
    try:
        resp = _get_table().query(
            KeyConditionExpression=Key("PK").eq(f"WORKSPACE#{tenant_id}#{user_id}"),
        )
        items = [dict(i) for i in resp.get("Items", [])]
        items.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return items
    except (ClientError, BotoCoreError) as e:
        logger.error("workspace_store.list failed [%s/%s]: %s", tenant_id, user_id, e)
        return []


def get_active_workspace(tenant_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    """Return the currently active workspace for a user, or None."""
    workspaces = list_workspaces(tenant_id, user_id)
    for ws in workspaces:
        if ws.get("is_active"):
            return ws
    return None


def activate_workspace(
    tenant_id: str,
    user_id: str,
    workspace_id: str,
) -> Optional[Dict[str, Any]]:
    """Switch active workspace.  Deactivates all others first."""
    _deactivate_all(tenant_id, user_id)
    _ws_cache_invalidate(tenant_id, user_id)
    now = datetime.utcnow().isoformat()
    try:
        _get_table().update_item(
            Key={
                "PK": f"WORKSPACE#{tenant_id}#{user_id}",
                "SK": f"WORKSPACE#{workspace_id}",
            },
            UpdateExpression="SET is_active = :t, updated_at = :now",
            ExpressionAttributeValues={":t": True, ":now": now},
        )
        return get_workspace(tenant_id, user_id, workspace_id)
    except (ClientError, BotoCoreError) as e:
        logger.error("workspace_store.activate failed [%s]: %s", workspace_id, e)
        return None


def update_workspace(
    tenant_id: str,
    user_id: str,
    workspace_id: str,
    updates: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Update mutable workspace fields (name, description, visibility)."""
    _MUTABLE = {"name", "description", "visibility", "override_count"}
    safe = {k: v for k, v in updates.items() if k in _MUTABLE}
    if not safe:
        return get_workspace(tenant_id, user_id, workspace_id)

    now = datetime.utcnow().isoformat()
    safe["updated_at"] = now

    parts = [f"#{i} = :{i}" for i in safe]
    expr = "SET " + ", ".join(parts)
    names = {f"#{k}": k for k in safe}
    values = {f":{k}": v for k, v in safe.items()}

    try:
        _get_table().update_item(
            Key={
                "PK": f"WORKSPACE#{tenant_id}#{user_id}",
                "SK": f"WORKSPACE#{workspace_id}",
            },
            UpdateExpression=expr,
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
        )
        return get_workspace(tenant_id, user_id, workspace_id)
    except (ClientError, BotoCoreError) as e:
        logger.error("workspace_store.update failed [%s]: %s", workspace_id, e)
        return None


def delete_workspace(
    tenant_id: str,
    user_id: str,
    workspace_id: str,
) -> bool:
    """Delete a non-default workspace.

    Returns False if the workspace is the default (cannot be deleted).
    """
    ws = get_workspace(tenant_id, user_id, workspace_id)
    if not ws:
        return False
    if ws.get("is_default"):
        logger.warning("workspace_store.delete: refused to delete default workspace [%s]", workspace_id)
        return False

    try:
        _get_table().delete_item(
            Key={
                "PK": f"WORKSPACE#{tenant_id}#{user_id}",
                "SK": f"WORKSPACE#{workspace_id}",
            }
        )
        logger.debug("workspace_store.delete: [%s]", workspace_id)
        return True
    except (ClientError, BotoCoreError) as e:
        logger.error("workspace_store.delete failed [%s]: %s", workspace_id, e)
        return False


# ── Auto-Provisioning ─────────────────────────────────────────────────

def get_or_create_default(tenant_id: str, user_id: str) -> Dict[str, Any]:
    """Return the active workspace for the user, creating a Default if none exists.

    This is the primary entry point for per-request workspace resolution.
    Uses a 60s TTL in-process cache to avoid repeated DynamoDB queries.
    """
    # Check cache first
    cached = _ws_cache_get(tenant_id, user_id)
    if cached:
        return cached

    existing = get_active_workspace(tenant_id, user_id)
    if existing:
        _ws_cache_set(tenant_id, user_id, existing)
        return existing

    # Check if any workspaces exist but none is active (shouldn't happen, but guard)
    all_ws = list_workspaces(tenant_id, user_id)
    if all_ws:
        # Activate the default one (or first if no default)
        default = next((w for w in all_ws if w.get("is_default")), all_ws[0])
        activated = activate_workspace(tenant_id, user_id, default["workspace_id"])
        result = activated or default
        _ws_cache_set(tenant_id, user_id, result)
        return result

    # No workspaces at all — provision the Default workspace
    logger.info("workspace_store: auto-provisioning Default workspace for [%s/%s]", tenant_id, user_id)
    result = create_workspace(
        tenant_id=tenant_id,
        user_id=user_id,
        name="Default",
        description="Auto-provisioned default workspace",
        is_default=True,
        is_active=True,
    )
    _ws_cache_set(tenant_id, user_id, result)
    return result


# ── Internal Helpers ─────────────────────────────────────────────────

def _deactivate_all(tenant_id: str, user_id: str) -> None:
    """Set is_active=False on every workspace for this user."""
    workspaces = list_workspaces(tenant_id, user_id)
    table = _get_table()
    now = datetime.utcnow().isoformat()
    for ws in workspaces:
        if ws.get("is_active"):
            try:
                table.update_item(
                    Key={
                        "PK": f"WORKSPACE#{tenant_id}#{user_id}",
                        "SK": f"WORKSPACE#{ws['workspace_id']}",
                    },
                    UpdateExpression="SET is_active = :f, updated_at = :now",
                    ExpressionAttributeValues={":f": False, ":now": now},
                )
            except (ClientError, BotoCoreError) as e:
                logger.warning("workspace_store._deactivate_all failed for [%s]: %s", ws["workspace_id"], e)


def increment_override_count(tenant_id: str, user_id: str, workspace_id: str, delta: int = 1) -> None:
    """Increment (or decrement) the override_count on a workspace record."""
    try:
        _get_table().update_item(
            Key={
                "PK": f"WORKSPACE#{tenant_id}#{user_id}",
                "SK": f"WORKSPACE#{workspace_id}",
            },
            UpdateExpression="SET override_count = if_not_exists(override_count, :zero) + :delta, updated_at = :now",
            ExpressionAttributeValues={
                ":delta": delta,
                ":zero": 0,
                ":now": datetime.utcnow().isoformat(),
            },
        )
    except (ClientError, BotoCoreError) as e:
        logger.warning("workspace_store.increment_override_count failed: %s", e)
