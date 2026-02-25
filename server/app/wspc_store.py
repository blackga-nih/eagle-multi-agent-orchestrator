"""WSPC Store — DynamoDB-backed WSPC# entity CRUD with 4-layer resolution chain.

WSPC# items are per-user, per-workspace overrides of any agent/skill/template/config.
Changes made in one user's workspace are completely invisible to all other users.

Entity format:
    PK:  WSPC#{tenant_id}#{user_id}#{workspace_id}
    SK:  {entity_type}#{name}

entity_type values: "AGENT" | "SKILL" | "TEMPLATE" | "CONFIG" | "REFDATA"

Resolution chain (highest → lowest priority):
  1. WSPC#{tenant}#{user}#{workspace} / {entity_type}#{name}   ← this file
  2. PROMPT#{tenant_id} / PROMPT#{agent_name}                   ← prompt_store (tenant admin)
  3. PROMPT#global / PROMPT#{agent_name}                        ← prompt_store (platform admin)
  4. PLUGIN#agents / PLUGIN#{name}                              ← plugin_store (canonical DynamoDB)
"""
import os
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError, BotoCoreError

from .plugin_store import get_agent_content, get_skill_content

logger = logging.getLogger("eagle.wspc_store")

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


# ── CRUD ─────────────────────────────────────────────────────────────

def put_override(
    tenant_id: str,
    user_id: str,
    workspace_id: str,
    entity_type: str,
    name: str,
    content: str,
    is_append: bool = False,
) -> Dict[str, Any]:
    """Write a user workspace override.

    entity_type must be one of: AGENT | SKILL | TEMPLATE | CONFIG | REFDATA

    If is_append=True the override text is appended to the base content;
    otherwise it fully replaces it.

    Returns the written item dict.
    """
    now = datetime.utcnow().isoformat()
    pk = f"WSPC#{tenant_id}#{user_id}#{workspace_id}"
    sk = f"{entity_type.upper()}#{name}"

    # Fetch existing to preserve version
    existing = get_override(tenant_id, user_id, workspace_id, entity_type, name)
    version = (existing.get("version", 0) + 1) if existing else 1
    created_at = existing.get("created_at", now) if existing else now

    item: Dict[str, Any] = {
        "PK": pk,
        "SK": sk,
        "entity_type": entity_type.upper(),
        "name": name,
        "content": content,
        "is_append": is_append,
        "version": version,
        "created_at": created_at,
        "updated_at": now,
    }

    try:
        _get_table().put_item(Item=item)
        logger.debug("wspc_store.put_override: [%s/%s/%s] %s#%s v%s", tenant_id, user_id, workspace_id, entity_type, name, version)

        # Keep workspace override_count accurate
        if not existing:
            from .workspace_store import increment_override_count
            increment_override_count(tenant_id, user_id, workspace_id, delta=1)

    except (ClientError, BotoCoreError) as e:
        logger.error("wspc_store.put_override failed [%s#%s]: %s", entity_type, name, e)

    return item


def get_override(
    tenant_id: str,
    user_id: str,
    workspace_id: str,
    entity_type: str,
    name: str,
) -> Optional[Dict[str, Any]]:
    """Fetch a single workspace override.  Returns None if not set."""
    try:
        resp = _get_table().get_item(
            Key={
                "PK": f"WSPC#{tenant_id}#{user_id}#{workspace_id}",
                "SK": f"{entity_type.upper()}#{name}",
            }
        )
        item = resp.get("Item")
        return dict(item) if item else None
    except (ClientError, BotoCoreError) as e:
        logger.error("wspc_store.get_override failed [%s#%s]: %s", entity_type, name, e)
        return None


def list_overrides(
    tenant_id: str,
    user_id: str,
    workspace_id: str,
    entity_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return all overrides in a workspace.

    If entity_type is given, only returns overrides of that type.
    All overrides live in one partition key — cheap, single-query.
    """
    try:
        pk = f"WSPC#{tenant_id}#{user_id}#{workspace_id}"
        if entity_type:
            resp = _get_table().query(
                KeyConditionExpression=(
                    Key("PK").eq(pk) & Key("SK").begins_with(f"{entity_type.upper()}#")
                )
            )
        else:
            resp = _get_table().query(
                KeyConditionExpression=Key("PK").eq(pk)
            )
        return [dict(i) for i in resp.get("Items", [])]
    except (ClientError, BotoCoreError) as e:
        logger.error("wspc_store.list_overrides failed [%s/%s/%s]: %s", tenant_id, user_id, workspace_id, e)
        return []


def delete_override(
    tenant_id: str,
    user_id: str,
    workspace_id: str,
    entity_type: str,
    name: str,
) -> bool:
    """Delete a single override (reset this entity to default for the user)."""
    existing = get_override(tenant_id, user_id, workspace_id, entity_type, name)
    if not existing:
        return False

    try:
        _get_table().delete_item(
            Key={
                "PK": f"WSPC#{tenant_id}#{user_id}#{workspace_id}",
                "SK": f"{entity_type.upper()}#{name}",
            }
        )
        from .workspace_store import increment_override_count
        increment_override_count(tenant_id, user_id, workspace_id, delta=-1)
        logger.debug("wspc_store.delete_override: [%s#%s] — reset to default", entity_type, name)
        return True
    except (ClientError, BotoCoreError) as e:
        logger.error("wspc_store.delete_override failed [%s#%s]: %s", entity_type, name, e)
        return False


def delete_all_overrides(
    tenant_id: str,
    user_id: str,
    workspace_id: str,
) -> int:
    """Delete all overrides in a workspace (reset everything to defaults).

    Returns the count of deleted items.
    """
    overrides = list_overrides(tenant_id, user_id, workspace_id)
    table = _get_table()
    deleted = 0
    pk = f"WSPC#{tenant_id}#{user_id}#{workspace_id}"

    with table.batch_writer() as batch:
        for item in overrides:
            batch.delete_item(Key={"PK": pk, "SK": item["SK"]})
            deleted += 1

    if deleted:
        from .workspace_store import update_workspace
        update_workspace(tenant_id, user_id, workspace_id, {"override_count": 0})
        logger.info("wspc_store.delete_all_overrides: cleared %d overrides for [%s/%s/%s]", deleted, tenant_id, user_id, workspace_id)

    return deleted


# ── Resolution Chain ─────────────────────────────────────────────────

def resolve_agent(
    tenant_id: str,
    user_id: str,
    workspace_id: str,
    agent_name: str,
) -> Tuple[str, str]:
    """Resolve the effective agent prompt using the 4-layer fallback chain.

    Returns (content, source) where source describes which layer resolved:
      "wspc"    — user workspace override
      "plugin"  — canonical DynamoDB PLUGIN# (authoritative default)
      "missing" — not found in any layer
    """
    # Layer 1: User workspace override
    override = get_override(tenant_id, user_id, workspace_id, "AGENT", agent_name)
    if override:
        content = override.get("content", "")
        if override.get("is_append"):
            # Append mode: fetch base and append override
            base = get_agent_content(agent_name) or ""
            return base + "\n\n" + content, "wspc+plugin"
        return content, "wspc"

    # Layers 2 & 3: Tenant/global PROMPT# overrides
    # These are resolved in prompt_store (imported lazily to avoid circular imports).
    # If prompt_store is not yet implemented, fall through to PLUGIN#.
    try:
        from .prompt_store import resolve_prompt  # type: ignore[import]
        prompt_content = resolve_prompt(tenant_id, agent_name)
        if prompt_content:
            return prompt_content, "prompt"
    except ImportError:
        pass  # prompt_store not yet implemented — skip to PLUGIN#

    # Layer 4: Canonical PLUGIN# in DynamoDB
    plugin_content = get_agent_content(agent_name)
    if plugin_content:
        return plugin_content, "plugin"

    return "", "missing"


def resolve_skill(
    tenant_id: str,
    user_id: str,
    workspace_id: str,
    skill_name: str,
) -> Tuple[str, str]:
    """Resolve the effective skill prompt using the 4-layer fallback chain.

    Returns (content, source).
    """
    # Layer 1: User workspace override
    override = get_override(tenant_id, user_id, workspace_id, "SKILL", skill_name)
    if override:
        content = override.get("content", "")
        if override.get("is_append"):
            base = get_skill_content(skill_name) or ""
            return base + "\n\n" + content, "wspc+plugin"
        return content, "wspc"

    # Layer 4: Canonical PLUGIN#
    plugin_content = get_skill_content(skill_name)
    if plugin_content:
        return plugin_content, "plugin"

    return "", "missing"


def resolve_config(
    tenant_id: str,
    user_id: str,
    workspace_id: str,
    key: str,
    default: Any = None,
) -> Any:
    """Resolve a user-level config value from workspace overrides.

    Falls through to global CONFIG# (config_store) if no workspace override.
    """
    # Layer 1: User workspace override
    override = get_override(tenant_id, user_id, workspace_id, "CONFIG", key)
    if override:
        import json
        content = override.get("content", "")
        try:
            return json.loads(content)
        except (ValueError, TypeError):
            return content

    # Fall through to config_store (imported lazily)
    try:
        from .config_store import get_config  # type: ignore[import]
        val = get_config(key)
        if val is not None:
            return val
    except ImportError:
        pass

    return default


def load_workspace_overrides(
    tenant_id: str,
    user_id: str,
    workspace_id: str,
) -> Dict[str, Dict[str, str]]:
    """Bulk-load all overrides for a workspace into a nested dict.

    Returns:
        {
          "AGENT": {"supervisor": "<content>", ...},
          "SKILL": {"oa-intake": "<content>", ...},
          "CONFIG": {"model": "sonnet", ...},
          ...
        }

    This is the efficient path for session start — fetch all overrides
    in one DynamoDB query, then resolve everything from the in-memory dict.
    """
    overrides = list_overrides(tenant_id, user_id, workspace_id)
    result: Dict[str, Dict[str, str]] = {}
    for item in overrides:
        etype = item.get("entity_type", "")
        name = item.get("name", "")
        content = item.get("content", "")
        if etype not in result:
            result[etype] = {}
        result[etype][name] = content
    return result
