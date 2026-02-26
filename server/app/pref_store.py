"""Pref Store — DynamoDB-backed PREF# user preferences CRUD.

Entity format:
    PK:  PREF#{tenant_id}
    SK:  PREF#{user_id}

Preferences persist indefinitely (no TTL).
No in-process cache — prefs are user-specific and low-volume.
"""
import os
import logging
from datetime import datetime
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger("eagle.pref_store")

# ── Configuration ─────────────────────────────────────────────────────
TABLE_NAME = os.getenv("EAGLE_SESSIONS_TABLE", "eagle")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# ── Default preferences ───────────────────────────────────────────────
DEFAULT_PREFS: Dict[str, Any] = {
    "default_model": "haiku",
    "default_doc_format": "docx",
    "preferred_vehicle": None,
    "ui_theme": "light",
    "notification_email": False,
    "show_far_citations": True,
    "default_template": {},
}

# Keys callers are allowed to modify via update_prefs()
_ALLOWED_KEYS = frozenset(DEFAULT_PREFS.keys())

# ── DynamoDB lazy singleton ───────────────────────────────────────────
_dynamodb = None


def _get_dynamodb():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
    return _dynamodb


def _get_table():
    return _get_dynamodb().Table(TABLE_NAME)


# ── Helpers ───────────────────────────────────────────────────────────

def _merge_with_defaults(item: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Return DEFAULT_PREFS merged with any values present in *item*.

    Fields absent in *item* fall back to their default values.
    The identity keys (tenant_id, user_id, updated_at) are included only
    when *item* supplies them.
    """
    merged: Dict[str, Any] = dict(DEFAULT_PREFS)
    if item:
        for key in DEFAULT_PREFS:
            if key in item:
                merged[key] = item[key]
        # Carry through identity / audit fields
        for key in ("tenant_id", "user_id", "updated_at"):
            if key in item:
                merged[key] = item[key]
    return merged


# ── Public API ────────────────────────────────────────────────────────

def get_prefs(tenant_id: str, user_id: str) -> Dict[str, Any]:
    """Fetch preferences for *user_id* within *tenant_id*.

    Merges the stored item with DEFAULT_PREFS so every key is always
    present in the returned dict.  Never returns None.
    """
    try:
        table = _get_table()
        response = table.get_item(
            Key={
                "PK": f"PREF#{tenant_id}",
                "SK": f"PREF#{user_id}",
            }
        )
        item = response.get("Item")
        return _merge_with_defaults(dict(item) if item else None)
    except (ClientError, BotoCoreError) as exc:
        logger.error(
            "pref_store.get_prefs failed [%s/%s]: %s",
            tenant_id,
            user_id,
            exc,
        )
        return dict(DEFAULT_PREFS)


def update_prefs(
    tenant_id: str,
    user_id: str,
    updates: Dict[str, Any],
) -> Dict[str, Any]:
    """Upsert preferences for *user_id* within *tenant_id*.

    Only keys present in *updates* that are also in _ALLOWED_KEYS are
    applied.  Unknown keys are silently ignored.  Returns the full merged
    prefs after the write.
    """
    # Strip unknown keys
    filtered = {k: v for k, v in updates.items() if k in _ALLOWED_KEYS}
    if not filtered:
        logger.debug("pref_store.update_prefs: no valid keys supplied — returning current prefs")
        return get_prefs(tenant_id, user_id)

    now = datetime.utcnow().isoformat()

    # Fetch current item to produce a full merged view for the return value
    current = get_prefs(tenant_id, user_id)
    merged = {**current, **filtered}

    item: Dict[str, Any] = {
        "PK": f"PREF#{tenant_id}",
        "SK": f"PREF#{user_id}",
        "tenant_id": tenant_id,
        "user_id": user_id,
        "updated_at": now,
        **{k: v for k, v in merged.items() if k in _ALLOWED_KEYS},
    }

    try:
        table = _get_table()
        table.put_item(Item=item)
        logger.debug(
            "pref_store.update_prefs: upserted prefs [%s/%s]",
            tenant_id,
            user_id,
        )
    except (ClientError, BotoCoreError) as exc:
        logger.error(
            "pref_store.update_prefs failed [%s/%s]: %s",
            tenant_id,
            user_id,
            exc,
        )

    merged["tenant_id"] = tenant_id
    merged["user_id"] = user_id
    merged["updated_at"] = now
    return merged


def reset_prefs(tenant_id: str, user_id: str) -> Dict[str, Any]:
    """Delete stored preferences for *user_id* within *tenant_id*.

    Returns DEFAULT_PREFS (a fresh copy) after deletion.
    """
    try:
        table = _get_table()
        table.delete_item(
            Key={
                "PK": f"PREF#{tenant_id}",
                "SK": f"PREF#{user_id}",
            }
        )
        logger.debug(
            "pref_store.reset_prefs: deleted prefs [%s/%s]",
            tenant_id,
            user_id,
        )
    except (ClientError, BotoCoreError) as exc:
        logger.error(
            "pref_store.reset_prefs failed [%s/%s]: %s",
            tenant_id,
            user_id,
            exc,
        )
    return dict(DEFAULT_PREFS)


def get_pref(
    tenant_id: str,
    user_id: str,
    key: str,
    default: Any = None,
) -> Any:
    """Convenience getter — return a single preference value by *key*.

    Falls back to *default* (not DEFAULT_PREFS) when the key is absent
    or DynamoDB is unreachable, so callers can supply their own sentinel.
    """
    prefs = get_prefs(tenant_id, user_id)
    return prefs.get(key, default)
