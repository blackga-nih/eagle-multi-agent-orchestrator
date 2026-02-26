"""Plugin Store — DynamoDB-backed PLUGIN# entity CRUD with 60-second TTL cache.

PLUGIN# items are the authoritative runtime source of truth for agent/skill/template
content in EAGLE. The bundled eagle-plugin/ files are bootstrap seeds only; DynamoDB
is the live source after the first `ensure_plugin_seeded()` call.

Entity format:
    PK:  PLUGIN#{entity_type}
    SK:  PLUGIN#{name}

entity_type values: "agents" | "skills" | "templates" | "refdata" | "tools" | "manifest"
"""
import os
import time
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import ClientError, BotoCoreError

logger = logging.getLogger("eagle.plugin_store")

# ── Configuration ────────────────────────────────────────────────────
TABLE_NAME = os.getenv("EAGLE_SESSIONS_TABLE", "eagle")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# Version string representing the bundled plugin files.
# Increment this whenever eagle-plugin/ content changes to force a re-seed.
BUNDLED_PLUGIN_VERSION = "1"

# ── DynamoDB Client (lazy singleton — same pattern as session_store.py) ──
_dynamodb = None


def _get_dynamodb():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
    return _dynamodb


def _get_table():
    return _get_dynamodb().Table(TABLE_NAME)


# ── In-Process Cache (60-second TTL per entity_type) ─────────────────
# Keys: entity_type str → {"ts": float, "items": list[dict]}
_entity_cache: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SECONDS = 60


def _cache_get(entity_type: str) -> Optional[List[Dict]]:
    """Return cached items for entity_type if still fresh, else None."""
    entry = _entity_cache.get(entity_type)
    if entry and time.time() < entry["ts"] + CACHE_TTL_SECONDS:
        return entry["items"]
    return None


def _cache_set(entity_type: str, items: List[Dict]) -> None:
    _entity_cache[entity_type] = {"ts": time.time(), "items": items}


def _cache_invalidate(entity_type: str) -> None:
    _entity_cache.pop(entity_type, None)


# ── Low-Level CRUD ────────────────────────────────────────────────────

def get_plugin_item(entity_type: str, name: str) -> Optional[Dict[str, Any]]:
    """Fetch a single PLUGIN# item by entity_type and name.

    Returns the item dict or None if not found.
    """
    try:
        table = _get_table()
        response = table.get_item(
            Key={
                "PK": f"PLUGIN#{entity_type}",
                "SK": f"PLUGIN#{name}",
            }
        )
        item = response.get("Item")
        return dict(item) if item else None
    except (ClientError, BotoCoreError) as e:
        logger.error("plugin_store.get_plugin_item failed [%s/%s]: %s", entity_type, name, e)
        return None


def put_plugin_item(
    entity_type: str,
    name: str,
    content: str,
    metadata: Optional[Dict[str, Any]] = None,
    content_type: str = "markdown",
) -> Dict[str, Any]:
    """Upsert a PLUGIN# item.

    If the item already exists, version is incremented and updated_at is refreshed.
    Returns the written item dict.
    """
    now = datetime.utcnow().isoformat()

    # Fetch existing to preserve version and created_at
    existing = get_plugin_item(entity_type, name)
    version = (existing.get("version", 0) + 1) if existing else 1
    created_at = existing.get("created_at", now) if existing else now

    item: Dict[str, Any] = {
        "PK": f"PLUGIN#{entity_type}",
        "SK": f"PLUGIN#{name}",
        "entity_type": entity_type,
        "name": name,
        "content": content,
        "content_type": content_type,
        "metadata": metadata or {},
        "version": version,
        "is_active": True,
        "created_at": created_at,
        "updated_at": now,
    }

    try:
        table = _get_table()
        table.put_item(Item=item)
        _cache_invalidate(entity_type)
        logger.debug("plugin_store.put_plugin_item: [%s/%s] v%s", entity_type, name, version)
    except (ClientError, BotoCoreError) as e:
        logger.error("plugin_store.put_plugin_item failed [%s/%s]: %s", entity_type, name, e)

    return item


def list_plugin_entities(entity_type: str) -> List[Dict[str, Any]]:
    """Return all PLUGIN# items for the given entity_type.

    Results are served from the 60-second in-process cache when fresh.
    """
    cached = _cache_get(entity_type)
    if cached is not None:
        return cached

    try:
        table = _get_table()
        response = table.query(
            KeyConditionExpression="PK = :pk AND begins_with(SK, :sk_prefix)",
            ExpressionAttributeValues={
                ":pk": f"PLUGIN#{entity_type}",
                ":sk_prefix": "PLUGIN#",
            },
        )
        items = [dict(i) for i in response.get("Items", [])]
        _cache_set(entity_type, items)
        return items
    except (ClientError, BotoCoreError) as e:
        logger.error("plugin_store.list_plugin_entities failed [%s]: %s", entity_type, e)
        return []


# ── Resolution Helpers ────────────────────────────────────────────────

def get_agent_content(name: str) -> Optional[str]:
    """Return the body/content string for an agent by directory name.

    Returns None if not found in DynamoDB.
    """
    # Try cache first via list
    cached = _cache_get("agents")
    if cached is not None:
        for item in cached:
            if item.get("name") == name:
                return item.get("content")

    item = get_plugin_item("agents", name)
    return item.get("content") if item else None


def get_skill_content(name: str) -> Optional[str]:
    """Return the body/content string for a skill by directory name.

    Returns None if not found in DynamoDB.
    """
    cached = _cache_get("skills")
    if cached is not None:
        for item in cached:
            if item.get("name") == name:
                return item.get("content")

    item = get_plugin_item("skills", name)
    return item.get("content") if item else None


def get_plugin_manifest() -> Dict[str, Any]:
    """Return the PLUGIN#manifest item content as a dict.

    Returns an empty dict with empty agents/skills lists if not found.
    """
    item = get_plugin_item("manifest", "manifest")
    if item:
        content = item.get("content", "{}")
        try:
            return json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return {}
    return {"agents": [], "skills": []}


# ── Bootstrap Seeder ─────────────────────────────────────────────────

def ensure_plugin_seeded() -> None:
    """Seed the eagle DynamoDB table from bundled plugin files if not already seeded.

    Checks whether PLUGIN#manifest exists and whether its version matches
    BUNDLED_PLUGIN_VERSION. If the manifest is absent or stale, seeds all
    agents, skills, and templates from PLUGIN_CONTENTS (eagle_skill_constants.py)
    then writes a fresh manifest record.

    This function is intentionally idempotent — safe to call on every startup.
    """
    # Check manifest version first to skip seeding on hot restarts
    existing_manifest = get_plugin_item("manifest", "manifest")
    if existing_manifest:
        try:
            content = json.loads(existing_manifest.get("content", "{}"))
            if content.get("version") == BUNDLED_PLUGIN_VERSION:
                logger.debug("plugin_store: DynamoDB already seeded at version %s — skipping", BUNDLED_PLUGIN_VERSION)
                return
        except (json.JSONDecodeError, TypeError):
            pass  # Corrupt manifest — re-seed

    logger.info("plugin_store: seeding DynamoDB from bundled eagle-plugin/ files (version %s)", BUNDLED_PLUGIN_VERSION)

    # Import here to avoid circular imports — eagle_skill_constants imports plugin_store
    # at its tail end, so by the time ensure_plugin_seeded() runs, AGENTS/SKILLS are loaded.
    from eagle_skill_constants import AGENTS, SKILLS  # type: ignore[import]

    seeded_agents = 0
    seeded_skills = 0

    for agent_name, entry in AGENTS.items():
        try:
            put_plugin_item(
                entity_type="agents",
                name=agent_name,
                content=entry.get("body", ""),
                metadata=entry.get("meta", {}),
                content_type="markdown",
            )
            seeded_agents += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("plugin_store: failed to seed agent [%s]: %s", agent_name, exc)

    for skill_name, entry in SKILLS.items():
        try:
            put_plugin_item(
                entity_type="skills",
                name=skill_name,
                content=entry.get("body", ""),
                metadata=entry.get("meta", {}),
                content_type="markdown",
            )
            seeded_skills += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("plugin_store: failed to seed skill [%s]: %s", skill_name, exc)

    # Write manifest last — marks seeding as complete
    manifest_content = json.dumps({
        "version": BUNDLED_PLUGIN_VERSION,
        "seeded_at": datetime.utcnow().isoformat(),
        "agent_count": seeded_agents,
        "skill_count": seeded_skills,
    })
    put_plugin_item(
        entity_type="manifest",
        name="manifest",
        content=manifest_content,
        metadata={"version": BUNDLED_PLUGIN_VERSION},
        content_type="json",
    )

    logger.info(
        "plugin_store: seeding complete — %d agents, %d skills",
        seeded_agents,
        seeded_skills,
    )
