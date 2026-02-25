"""Config Store - DynamoDB-backed CONFIG# global runtime feature flags.

CONFIG# items provide hot-reloadable runtime configuration for EAGLE.
Values are stored as JSON-encoded strings, allowing dicts, lists, and
scalars to round-trip cleanly. Typed accessors provide a safe API.

Entity format:
    PK:  CONFIG#global
    SK:  CONFIG#{key}

Known keys and defaults:
    "model"           -> "haiku"
    "tier_budgets"    -> {"basic": 0.10, "advanced": 0.25, "premium": 0.75}
    "tier_tools"      -> {"basic": [], "advanced": ["Read","Glob","Grep"],
                          "premium": ["Read","Glob","Grep","Bash"]}
    "rate_limits"     -> {"basic": 10, "advanced": 50, "premium": 200}
    "max_turns"       -> 15
    "skill_cache_ttl" -> 60
    "feature_flags"   -> {"streaming_v2": True, "user_skills": False, "mcp_enabled": False}
"""
import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict

import boto3
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger("eagle.config_store")

# -- Configuration ------------------------------------------------------
TABLE_NAME = os.getenv("EAGLE_SESSIONS_TABLE", "eagle")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# -- Known defaults -----------------------------------------------------
_DEFAULTS: Dict[str, Any] = {
    "model": "haiku",
    "tier_budgets": {"basic": 0.10, "advanced": 0.25, "premium": 0.75},
    "tier_tools": {
        "basic": [],
        "advanced": ["Read", "Glob", "Grep"],
        "premium": ["Read", "Glob", "Grep", "Bash"],
    },
    "rate_limits": {"basic": 10, "advanced": 50, "premium": 200},
    "max_turns": 15,
    "skill_cache_ttl": 60,
    "feature_flags": {"streaming_v2": True, "user_skills": False, "mcp_enabled": False},
}

_CONFIG_PK = "CONFIG#global"

_dynamodb = None


def _get_dynamodb():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
    return _dynamodb


def _get_table():
    return _get_dynamodb().Table(TABLE_NAME)


# -- In-Process Cache (60-second TTL per config key) --------------------
_config_cache: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SECONDS = 60

_MISS = object()


def _cache_get(key: str) -> Any:
    """Return cached value for key if still fresh, else _MISS sentinel."""
    entry = _config_cache.get(key)
    if entry and time.time() < entry["ts"] + CACHE_TTL_SECONDS:
        return entry["value"]
    return _MISS


def _cache_set(key: str, value: Any) -> None:
    _config_cache[key] = {"ts": time.time(), "value": value}


def _cache_invalidate(key: str) -> None:
    _config_cache.pop(key, None)


# -- Serialization helpers ----------------------------------------------


def _serialize(value: Any) -> str:
    """Serialize any Python value to a JSON string for DynamoDB storage."""
    return json.dumps(value)


def _deserialize(raw: str) -> Any:
    """Deserialize a stored string back to a Python value.

    Plain strings stored pre-JSON are returned as-is if json.loads fails.
    """
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw


# -- Core CRUD ----------------------------------------------------------


def get_config(key: str, default: Any = None) -> Any:
    """Return the runtime value for config key, falling back to default.

    Resolution order:
      1. In-process cache (60 s TTL)
      2. DynamoDB CONFIG#global / CONFIG#{key}
      3. Built-in _DEFAULTS dict
      4. Caller-supplied default argument
    """
    cached = _cache_get(key)
    if cached is not _MISS:
        return cached

    try:
        table = _get_table()
        response = table.get_item(
            Key={
                "PK": _CONFIG_PK,
                "SK": f"CONFIG#{key}",
            }
        )
        item = response.get("Item")
        if item:
            value = _deserialize(item["value"])
            _cache_set(key, value)
            return value
    except (ClientError, BotoCoreError) as exc:
        logger.error("config_store.get_config failed [%s]: %s", key, exc)

    fallback = _DEFAULTS.get(key, default)
    _cache_set(key, fallback)
    return fallback


def put_config(key: str, value: Any, updated_by: str = "admin") -> dict:
    """Upsert a config key/value pair in DynamoDB and invalidate the cache.

    value is serialized to a JSON string before storage.
    Returns the written item dict.
    """
    now = datetime.utcnow().isoformat()
    serialized = _serialize(value)

    item: Dict[str, Any] = {
        "PK": _CONFIG_PK,
        "SK": f"CONFIG#{key}",
        "key": key,
        "value": serialized,
        "updated_at": now,
        "updated_by": updated_by,
    }

    try:
        table = _get_table()
        table.put_item(Item=item)
        _cache_invalidate(key)
        _cache_invalidate("__all__")
        logger.debug("config_store.put_config: [%s] updated by %s", key, updated_by)
    except (ClientError, BotoCoreError) as exc:
        logger.error("config_store.put_config failed [%s]: %s", key, exc)

    return item


def delete_config(key: str) -> bool:
    """Delete a config item from DynamoDB and invalidate the cache.

    Returns True on success, False if an error occurred.
    """
    try:
        table = _get_table()
        table.delete_item(
            Key={
                "PK": _CONFIG_PK,
                "SK": f"CONFIG#{key}",
            }
        )
        _cache_invalidate(key)
        _cache_invalidate("__all__")
        logger.debug("config_store.delete_config: [%s] deleted", key)
        return True
    except (ClientError, BotoCoreError) as exc:
        logger.error("config_store.delete_config failed [%s]: %s", key, exc)
        return False


def list_config() -> Dict[str, Any]:
    """Return all CONFIG#global items as a deserialized {key: value} dict.

    Uses a short-lived cache entry keyed __all__ to avoid repeated scans.
    Falls back to built-in _DEFAULTS if DynamoDB is unreachable.
    """
    cached = _cache_get("__all__")
    if cached is not _MISS:
        return cached  # type: ignore[return-value]

    try:
        table = _get_table()
        response = table.query(
            KeyConditionExpression="PK = :pk AND begins_with(SK, :sk_prefix)",
            ExpressionAttributeValues={
                ":pk": _CONFIG_PK,
                ":sk_prefix": "CONFIG#",
            },
        )
        result: Dict[str, Any] = {}
        for raw_item in response.get("Items", []):
            k = raw_item.get("key") or raw_item["SK"].removeprefix("CONFIG#")
            result[k] = _deserialize(raw_item["value"])
        _cache_set("__all__", result)
        return result
    except (ClientError, BotoCoreError) as exc:
        logger.error("config_store.list_config failed: %s", exc)
        return dict(_DEFAULTS)


# -- Typed Accessors ----------------------------------------------------


def get_model() -> str:
    """Return the active model identifier (e.g. haiku, sonnet)."""
    value = get_config("model", _DEFAULTS["model"])
    return str(value)


def get_tier_budgets() -> Dict[str, float]:
    """Return per-tier cost budget ceilings in USD."""
    value = get_config("tier_budgets", _DEFAULTS["tier_budgets"])
    if isinstance(value, dict):
        return value
    logger.warning(
        "config_store.get_tier_budgets: unexpected type %s - using default", type(value)
    )
    return dict(_DEFAULTS["tier_budgets"])


def get_max_turns() -> int:
    """Return the maximum number of agentic turns per session."""
    value = get_config("max_turns", _DEFAULTS["max_turns"])
    try:
        return int(value)
    except (TypeError, ValueError):
        logger.warning(
            "config_store.get_max_turns: cannot coerce %r to int - using default", value
        )
        return int(_DEFAULTS["max_turns"])


def get_feature_flags() -> Dict[str, bool]:
    """Return the feature flags dict (streaming_v2, user_skills, mcp_enabled)."""
    value = get_config("feature_flags", _DEFAULTS["feature_flags"])
    if isinstance(value, dict):
        return value
    logger.warning(
        "config_store.get_feature_flags: unexpected type %s - using default", type(value)
    )
    return dict(_DEFAULTS["feature_flags"])
