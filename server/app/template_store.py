'''Template Store — DynamoDB-backed TEMPLATE# entity CRUD with 60-second in-process cache.

TEMPLATE# items hold tenant- and user-specific document template overrides.
When no tenant/user override exists the resolution chain falls back to
PLUGIN#templates, which holds the system-wide canonical templates.

Entity format:
    PK:  TEMPLATE#{tenant_id}   (use "global" as tenant_id for system defaults)
    SK:  TEMPLATE#{doc_type}#{user_id}

doc_type values: "sow" | "igce" | "acquisition-plan" | "market-research" | "justification"
user_id:         specific user ID  or  "shared" for tenant-wide defaults

GSI (for reverse lookups by tenant + doc_type + recency):
    GSI1PK = f"TENANT#{tenant_id}"
    GSI1SK = f"TEMPLATE#{doc_type}#{updated_at}"
'''
from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger("eagle.template_store")

# ── Configuration ─────────────────────────────────────────────────────
TABLE_NAME = os.getenv("EAGLE_SESSIONS_TABLE", "eagle")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

VALID_DOC_TYPES = frozenset(
    {"sow", "igce", "acquisition-plan", "market-research", "justification"}
)

# ── DynamoDB singleton (lazy, same pattern as plugin_store.py) ────
_dynamodb = None


def _get_dynamodb():
    global _dynamodb  # noqa: PLW0603
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
    return _dynamodb


def _get_table():
    return _get_dynamodb().Table(TABLE_NAME)


# ── In-Process Cache (60-second TTL) ─────────────────────
# Key format: f"{tenant_id}#{doc_type}#{user_id}"
# Value:       {"ts": float, "item": dict | None}
_template_cache: Dict[str, Dict] = {}
CACHE_TTL_SECONDS = 60

# Sentinel: distinguishes cached-None (item not found) from not-in-cache.
_MISS = object()


def _cache_key(tenant_id: str, doc_type: str, user_id: str) -> str:
    return f"{tenant_id}#{doc_type}#{user_id}"


def _cache_get(tenant_id: str, doc_type: str, user_id: str) -> object:
    '''Return cached item (possibly None) if still fresh; _MISS sentinel if stale/absent.'''
    entry = _template_cache.get(_cache_key(tenant_id, doc_type, user_id))
    if entry is not None and time.time() < entry["ts"] + CACHE_TTL_SECONDS:
        return entry["item"]  # may itself be None (cached miss)
    return _MISS


def _cache_set(tenant_id: str, doc_type: str, user_id: str, item: Optional[dict]) -> None:
    _template_cache[_cache_key(tenant_id, doc_type, user_id)] = {
        "ts": time.time(),
        "item": item,
    }


def _cache_invalidate(tenant_id: str, doc_type: str, user_id: str) -> None:
    _template_cache.pop(_cache_key(tenant_id, doc_type, user_id), None)


# ── Key Helpers ──────────────────────────────────────────────────────────

def _pk(tenant_id: str) -> str:
    return f"TEMPLATE#{tenant_id}"


def _sk(doc_type: str, user_id: str) -> str:
    return f"TEMPLATE#{doc_type}#{user_id}"


def _extract_variables(template_body: str) -> List[str]:
    '''Return unique {{VARIABLE}} placeholder names found in template_body, in order.'''
    seen: List[str] = []
    for name in re.findall(r'\{\{(\w+)\}\}', template_body):
        if name not in seen:
            seen.append(name)
    return seen


# ── CRUD ──────────────────────────────────────────────────────────────

def put_template(
    tenant_id: str,
    doc_type: str,
    user_id: str,
    template_body: str,
    display_name: str = "",
    is_default: bool = False,
    ttl: Optional[int] = None,
) -> dict:
    '''Upsert a TEMPLATE# item.

    Extracts {{VARIABLE}} placeholders from template_body and stores them in the
    ``variables`` attribute.  Version is auto-incremented on each update.

    Args:
        tenant_id:     Owning tenant (use "global" for system-wide defaults).
        doc_type:      One of VALID_DOC_TYPES.
        user_id:       Owner user ID or "shared" for a tenant-wide default.
        template_body: Raw template text containing {{VARIABLE}} placeholders.
        display_name:  Human-readable label (defaults to "{doc_type} template").
        is_default:    Whether this is the default template for the doc_type.
        ttl:           Optional Unix epoch for DynamoDB TTL-based expiry.

    Returns:
        The written item as a plain dict.
    '''
    now = datetime.utcnow().isoformat()

    existing = get_template(tenant_id, doc_type, user_id)
    version = (existing.get("version", 0) + 1) if existing else 1
    created_at = existing.get("created_at", now) if existing else now
    parent_version: Optional[str] = (
        str(existing.get("version")) if existing and existing.get("version") else None
    )

    variables = _extract_variables(template_body)

    item: dict = {
        "PK": _pk(tenant_id),
        "SK": _sk(doc_type, user_id),
        # GSI attributes
        "GSI1PK": f"TENANT#{tenant_id}",
        "GSI1SK": f"TEMPLATE#{doc_type}#{now}",
        # Domain attributes
        "doc_type": doc_type,
        "tenant_id": tenant_id,
        "owner_user_id": user_id,
        "template_body": template_body,
        "variables": variables,
        "display_name": display_name or f"{doc_type} template",
        "is_default": is_default,
        "version": version,
        "created_at": created_at,
        "updated_at": now,
    }
    if parent_version is not None:
        item["parent_version"] = parent_version
    if ttl is not None:
        item["ttl"] = ttl

    try:
        _get_table().put_item(Item=item)
        _cache_invalidate(tenant_id, doc_type, user_id)
        logger.debug(
            "template_store.put_template: [%s/%s/%s] v%s",
            tenant_id,
            doc_type,
            user_id,
            version,
        )
    except (ClientError, BotoCoreError) as exc:
        logger.error(
            "template_store.put_template failed [%s/%s/%s]: %s",
            tenant_id,
            doc_type,
            user_id,
            exc,
        )

    return item


def get_template(tenant_id: str, doc_type: str, user_id: str) -> Optional[dict]:
    '''Fetch a single TEMPLATE# item by (tenant_id, doc_type, user_id).

    Returns the item dict or None if not found.  Results are served from the
    60-second in-process cache when fresh.
    '''
    cached = _cache_get(tenant_id, doc_type, user_id)
    if cached is not _MISS:
        return cached  # type: ignore[return-value]

    try:
        response = _get_table().get_item(
            Key={"PK": _pk(tenant_id), "SK": _sk(doc_type, user_id)}
        )
        item = response.get("Item")
        result = dict(item) if item else None
        _cache_set(tenant_id, doc_type, user_id, result)
        return result
    except (ClientError, BotoCoreError) as exc:
        logger.error(
            "template_store.get_template failed [%s/%s/%s]: %s",
            tenant_id,
            doc_type,
            user_id,
            exc,
        )
        return None


def delete_template(tenant_id: str, doc_type: str, user_id: str) -> bool:
    '''Delete a TEMPLATE# item.  Returns True on success, False on error.'''
    try:
        _get_table().delete_item(
            Key={"PK": _pk(tenant_id), "SK": _sk(doc_type, user_id)}
        )
        _cache_invalidate(tenant_id, doc_type, user_id)
        logger.debug(
            "template_store.delete_template: [%s/%s/%s]",
            tenant_id,
            doc_type,
            user_id,
        )
        return True
    except (ClientError, BotoCoreError) as exc:
        logger.error(
            "template_store.delete_template failed [%s/%s/%s]: %s",
            tenant_id,
            doc_type,
            user_id,
            exc,
        )
        return False


def list_tenant_templates(
    tenant_id: str,
    doc_type: Optional[str] = None,
) -> List[dict]:
    '''List all TEMPLATE# items for a tenant, optionally filtered by doc_type.

    Queries by PK = TEMPLATE#{tenant_id}.  When doc_type is supplied the SK
    begins_with filter restricts results to that doc_type only.

    Args:
        tenant_id: Tenant to query.
        doc_type:  Optional doc_type filter (e.g. "sow").

    Returns:
        List of item dicts, possibly empty.
    '''
    pk_val = _pk(tenant_id)

    try:
        table = _get_table()

        if doc_type:
            sk_prefix = f"TEMPLATE#{doc_type}#"
            response = table.query(
                KeyConditionExpression=(
                    Key("PK").eq(pk_val) & Key("SK").begins_with(sk_prefix)
                )
            )
        else:
            response = table.query(
                KeyConditionExpression=(
                    Key("PK").eq(pk_val) & Key("SK").begins_with("TEMPLATE#")
                )
            )

        return [dict(i) for i in response.get("Items", [])]
    except (ClientError, BotoCoreError) as exc:
        logger.error(
            "template_store.list_tenant_templates failed [%s/%s]: %s",
            tenant_id,
            doc_type,
            exc,
        )
        return []


# ── Resolution ────────────────────────────────────────────────────────

def resolve_template(
    tenant_id: str,
    user_id: str,
    doc_type: str,
) -> Tuple[str, str]:
    '''Resolve the best available template body for a given (tenant, user, doc_type).

    Fallback chain — first non-empty match wins:
        1. TEMPLATE#{tenant_id}  /  {doc_type}#{user_id}   — user personal override
        2. TEMPLATE#{tenant_id}  /  {doc_type}#shared      — tenant-wide default
        3. TEMPLATE#global       /  {doc_type}#shared      — system-wide global default
        4. PLUGIN#templates      /  {doc_type}              — canonical plugin template

    Args:
        tenant_id: The calling tenant identifier.
        user_id:   The calling user identifier.
        doc_type:  Document type (e.g. "sow").

    Returns:
        Tuple of (template_body, source) where source is one of:
            "user"    — personal override
            "tenant"  — tenant shared default
            "global"  — system-wide global default
            "plugin"  — canonical PLUGIN#templates entry
            "missing" — no template found anywhere
    '''
    # 1. User personal override
    user_item = get_template(tenant_id, doc_type, user_id)
    if user_item and user_item.get("template_body"):
        return user_item["template_body"], "user"

    # 2. Tenant shared default
    shared_item = get_template(tenant_id, doc_type, "shared")
    if shared_item and shared_item.get("template_body"):
        return shared_item["template_body"], "tenant"

    # 3. Global system default
    global_item = get_template("global", doc_type, "shared")
    if global_item and global_item.get("template_body"):
        return global_item["template_body"], "global"

    # 4. PLUGIN#templates canonical fallback
    try:
        from plugin_store import get_plugin_item  # type: ignore[import]

        plugin_item = get_plugin_item("templates", doc_type)
        if plugin_item and plugin_item.get("content"):
            return plugin_item["content"], "plugin"
    except ImportError:
        logger.warning(
            "template_store.resolve_template: plugin_store not importable; "
            "skipping PLUGIN# fallback for [%s/%s]",
            tenant_id,
            doc_type,
        )
    except (ClientError, BotoCoreError) as exc:
        logger.error(
            "template_store.resolve_template: plugin_store lookup failed [%s/%s]: %s",
            tenant_id,
            doc_type,
            exc,
        )

    return "", "missing"
