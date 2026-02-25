"""Prompt Store — DynamoDB-backed PROMPT# tenant/admin prompt overrides with 60-second cache.

PROMPT# items are Layer 2 of the 4-layer resolution chain:
    WSPC#  (workspace overrides)   ← highest priority
    PROMPT# (tenant/admin prompts) ← this module
    PLUGIN# (bundled plugin files)
    hardcoded defaults             ← lowest priority

Entity format:
    PK:  PROMPT#{tenant_id}   (or PROMPT#global for system-wide overrides)
    SK:  PROMPT#{agent_name}

Attributes:
    agent_name  str     — agent directory name (e.g. "supervisor", "legal-counsel")
    tenant_id   str     — tenant identifier, or "global" for system-wide
    prompt_body str     — override prompt text (full replacement or append fragment)
    is_append   bool    — False → replace agent system prompt; True → append to it
    version     int     — monotonically incrementing on each put
    updated_at  str     — ISO-8601 UTC timestamp
    updated_by  str     — principal that wrote the record (e.g. "admin", "api-key-xyz")
    ttl         int     — optional Unix epoch expiry (DynamoDB TTL attribute)
"""
import os
import time
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger("eagle.prompt_store")

# ── Configuration ─────────────────────────────────────────────────────
TABLE_NAME = os.getenv("EAGLE_SESSIONS_TABLE", "eagle")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# ── DynamoDB lazy singleton ───────────────────────────────────────────
_dynamodb = None


def _get_dynamodb():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
    return _dynamodb


def _get_table():
    return _get_dynamodb().Table(TABLE_NAME)


# ── In-Process Cache (60-second TTL per tenant_id#agent_name) ─────────
# Keys: "{tenant_id}#{agent_name}" → {"ts": float, "item": dict | None}
_prompt_cache: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SECONDS = 60


def _cache_key(tenant_id: str, agent_name: str) -> str:
    return f"{tenant_id}#{agent_name}"


def _cache_get(tenant_id: str, agent_name: str) -> Optional[Dict]:
    """Return cached item (or None sentinel) if still fresh; else return sentinel
    indicating cache miss (distinguished from a cached None via key presence)."""
    key = _cache_key(tenant_id, agent_name)
    entry = _prompt_cache.get(key)
    if entry and time.time() < entry["ts"] + CACHE_TTL_SECONDS:
        return entry  # caller checks entry["item"] for actual value
    return None


def _cache_set(tenant_id: str, agent_name: str, item: Optional[Dict]) -> None:
    key = _cache_key(tenant_id, agent_name)
    _prompt_cache[key] = {"ts": time.time(), "item": item}


def _cache_invalidate(tenant_id: str, agent_name: str) -> None:
    key = _cache_key(tenant_id, agent_name)
    _prompt_cache.pop(key, None)


# ── CRUD ──────────────────────────────────────────────────────────────

def put_prompt(
    tenant_id: str,
    agent_name: str,
    prompt_body: str,
    is_append: bool = False,
    updated_by: str = "admin",
    ttl_epoch: Optional[int] = None,
) -> Dict[str, Any]:
    """Upsert a PROMPT# override for (tenant_id, agent_name).

    Increments version on each write.  Returns the written item dict.
    If ttl_epoch is provided it is stored as the DynamoDB TTL attribute ``ttl``.
    """
    now = datetime.utcnow().isoformat()

    existing = get_prompt(tenant_id, agent_name)
    version = (existing.get("version", 0) + 1) if existing else 1

    item: Dict[str, Any] = {
        "PK": f"PROMPT#{tenant_id}",
        "SK": f"PROMPT#{agent_name}",
        "tenant_id": tenant_id,
        "agent_name": agent_name,
        "prompt_body": prompt_body,
        "is_append": is_append,
        "version": version,
        "updated_at": now,
        "updated_by": updated_by,
    }

    if ttl_epoch is not None:
        item["ttl"] = ttl_epoch

    try:
        table = _get_table()
        table.put_item(Item=item)
        _cache_invalidate(tenant_id, agent_name)
        logger.debug(
            "prompt_store.put_prompt: [%s/%s] v%s is_append=%s",
            tenant_id,
            agent_name,
            version,
            is_append,
        )
    except (ClientError, BotoCoreError) as exc:
        logger.error(
            "prompt_store.put_prompt failed [%s/%s]: %s", tenant_id, agent_name, exc
        )

    return item


def get_prompt(tenant_id: str, agent_name: str) -> Optional[Dict[str, Any]]:
    """Fetch a single PROMPT# item for (tenant_id, agent_name).

    Serves from 60-second in-process cache when fresh.
    Returns the item dict or None if not found.
    """
    cached = _cache_get(tenant_id, agent_name)
    if cached is not None:
        return cached["item"]

    try:
        table = _get_table()
        response = table.get_item(
            Key={
                "PK": f"PROMPT#{tenant_id}",
                "SK": f"PROMPT#{agent_name}",
            }
        )
        item = response.get("Item")
        result = dict(item) if item else None
        _cache_set(tenant_id, agent_name, result)
        return result
    except (ClientError, BotoCoreError) as exc:
        logger.error(
            "prompt_store.get_prompt failed [%s/%s]: %s", tenant_id, agent_name, exc
        )
        return None


def resolve_prompt(tenant_id: str, agent_name: str) -> Optional[str]:
    """Resolve the effective prompt body for (tenant_id, agent_name).

    Resolution order (highest → lowest priority):
        1. PROMPT#{tenant_id} / PROMPT#{agent_name}  — tenant-level override
        2. PROMPT#global      / PROMPT#{agent_name}  — system-wide override

    Returns the ``prompt_body`` string of the first match, or None if neither
    exists.  Callers should apply is_append logic themselves when composing the
    final system prompt.
    """
    # 1. Tenant-level override
    tenant_item = get_prompt(tenant_id, agent_name)
    if tenant_item:
        return tenant_item.get("prompt_body")

    # 2. Global override (skip redundant lookup when tenant_id IS "global")
    if tenant_id != "global":
        global_item = get_prompt("global", agent_name)
        if global_item:
            return global_item.get("prompt_body")

    return None


def delete_prompt(tenant_id: str, agent_name: str) -> bool:
    """Delete a PROMPT# item.  Returns True on success, False on error."""
    try:
        table = _get_table()
        table.delete_item(
            Key={
                "PK": f"PROMPT#{tenant_id}",
                "SK": f"PROMPT#{agent_name}",
            }
        )
        _cache_invalidate(tenant_id, agent_name)
        logger.debug(
            "prompt_store.delete_prompt: [%s/%s] deleted", tenant_id, agent_name
        )
        return True
    except (ClientError, BotoCoreError) as exc:
        logger.error(
            "prompt_store.delete_prompt failed [%s/%s]: %s", tenant_id, agent_name, exc
        )
        return False


def list_tenant_prompts(tenant_id: str) -> List[Dict[str, Any]]:
    """Return all PROMPT# items for tenant_id (DynamoDB query, no cache aggregation).

    Each item includes all stored attributes (tenant_id, agent_name, prompt_body,
    is_append, version, updated_at, updated_by, and optionally ttl).
    """
    try:
        table = _get_table()
        response = table.query(
            KeyConditionExpression=(
                "PK = :pk AND begins_with(SK, :sk_prefix)"
            ),
            ExpressionAttributeValues={
                ":pk": f"PROMPT#{tenant_id}",
                ":sk_prefix": "PROMPT#",
            },
        )
        return [dict(i) for i in response.get("Items", [])]
    except (ClientError, BotoCoreError) as exc:
        logger.error(
            "prompt_store.list_tenant_prompts failed [%s]: %s", tenant_id, exc
        )
        return []
