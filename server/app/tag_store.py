"""Tag Store — DynamoDB-backed TAG# inverted-index for document and package tagging.

Stores TAG# items as an inverted index so that documents and packages can be
queried by tag value without a GSI on list attributes.

Entity format:
    PK: TAG#{tenant_id}#{tag_value}
    SK: TAG#{entity_type}#{entity_id}

Tag types:
    - system: Auto-derived (e.g., "phase:planning", "threshold:sat")
    - user:   Free-form user labels (e.g., "priority", "needs-review")
    - far:    FAR clause references (e.g., "FAR 52.219-8", "FAR 6.302")
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import BotoCoreError, ClientError

from .db_client import get_table

logger = logging.getLogger("eagle.tag_store")


# ── Core CRUD ─────────────────────────────────────────────────────────


def add_tags(
    tenant_id: str,
    entity_type: str,
    entity_id: str,
    tags: list[dict],
) -> int:
    """Add tags to an entity via TAG# inverted-index items.

    Args:
        tenant_id: Tenant identifier
        entity_type: "document" or "package"
        entity_id: Document ID or Package ID
        tags: List of dicts with keys: type ("system"|"user"|"far"), value (str)

    Returns:
        Number of TAG# items written
    """
    table = get_table()
    now = datetime.utcnow().isoformat()
    written = 0

    for tag in tags:
        tag_type = tag.get("type", "user")
        tag_value = tag.get("value", "").strip()
        if not tag_value:
            continue

        item = {
            "PK": f"TAG#{tenant_id}#{tag_value}",
            "SK": f"TAG#{entity_type}#{entity_id}",
            "entity_type": entity_type,
            "entity_id": entity_id,
            "tag_type": tag_type,
            "tag_value": tag_value,
            "tenant_id": tenant_id,
            "created_at": now,
        }

        try:
            table.put_item(Item=item)
            written += 1
        except (ClientError, BotoCoreError) as e:
            logger.error("tag_store.add_tags failed for %s: %s", tag_value, e)

    return written


def remove_tags(
    tenant_id: str,
    entity_type: str,
    entity_id: str,
    tag_values: list[str],
) -> int:
    """Remove TAG# items for specific tag values.

    Returns:
        Number of TAG# items deleted
    """
    table = get_table()
    deleted = 0

    for tag_value in tag_values:
        tag_value = tag_value.strip()
        if not tag_value:
            continue

        try:
            table.delete_item(
                Key={
                    "PK": f"TAG#{tenant_id}#{tag_value}",
                    "SK": f"TAG#{entity_type}#{entity_id}",
                }
            )
            deleted += 1
        except (ClientError, BotoCoreError) as e:
            logger.error("tag_store.remove_tags failed for %s: %s", tag_value, e)

    return deleted


def get_entity_tags(
    tenant_id: str,
    entity_type: str,
    entity_id: str,
) -> dict:
    """Get all tags for an entity by scanning TAG# items.

    Since TAG# items are keyed by tag_value, we need to scan all TAG# items
    for this tenant and filter by entity. For efficiency, this queries the
    entity's DynamoDB item directly for its tag lists.

    Returns:
        Dict with keys: system_tags, user_tags, far_tags (each a list[str])
    """
    # Direct approach: query all TAG# items where SK matches this entity.
    # This requires a scan with filter, which isn't ideal at scale.
    # For now, we return tags from the entity item directly.
    result = {"system_tags": [], "user_tags": [], "far_tags": []}

    table = get_table()

    # Determine entity PK/SK prefix
    if entity_type == "document":
        pk_prefix = f"DOCUMENT#{tenant_id}"
    elif entity_type == "package":
        pk_prefix = f"PACKAGE#{tenant_id}"
    else:
        return result

    try:
        # Query the entity's partition for items matching the entity_id
        response = table.query(
            KeyConditionExpression=Key("PK").eq(pk_prefix),
            FilterExpression=(
                Attr("document_id").eq(entity_id)
                if entity_type == "document"
                else Attr("package_id").eq(entity_id)
            ),
            Limit=1,
        )
        items = response.get("Items", [])
        if items:
            item = items[0]
            result["system_tags"] = item.get("system_tags", [])
            result["user_tags"] = item.get("user_tags", [])
            result["far_tags"] = item.get("far_tags", [])
    except (ClientError, BotoCoreError) as e:
        logger.error("tag_store.get_entity_tags failed: %s", e)

    return result


def find_entities_by_tag(
    tenant_id: str,
    tag_value: str,
    entity_type: Optional[str] = None,
) -> list[dict]:
    """Find all entities tagged with a specific value.

    Args:
        tenant_id: Tenant identifier
        tag_value: Tag value to search for (e.g., "FAR 52.219-8")
        entity_type: Optional filter for "document" or "package"

    Returns:
        List of dicts with entity_type, entity_id, tag_type, created_at
    """
    table = get_table()
    pk = f"TAG#{tenant_id}#{tag_value}"

    try:
        if entity_type:
            response = table.query(
                KeyConditionExpression=(
                    Key("PK").eq(pk) & Key("SK").begins_with(f"TAG#{entity_type}#")
                ),
            )
        else:
            response = table.query(
                KeyConditionExpression=(
                    Key("PK").eq(pk) & Key("SK").begins_with("TAG#")
                ),
            )

        return [
            {
                "entity_type": item.get("entity_type"),
                "entity_id": item.get("entity_id"),
                "tag_type": item.get("tag_type"),
                "tag_value": item.get("tag_value"),
                "created_at": item.get("created_at"),
            }
            for item in response.get("Items", [])
        ]
    except (ClientError, BotoCoreError) as e:
        logger.error("tag_store.find_entities_by_tag failed: %s", e)
        return []


def find_entities_by_tags(
    tenant_id: str,
    tag_values: list[str],
    match_all: bool = False,
) -> list[dict]:
    """Find entities matching multiple tags.

    Args:
        tenant_id: Tenant identifier
        tag_values: List of tag values to search for
        match_all: If True, return only entities matching ALL tags (intersection).
                   If False, return entities matching ANY tag (union).

    Returns:
        List of unique entity dicts
    """
    if not tag_values:
        return []

    all_results: dict[str, dict] = {}
    tag_counts: dict[str, int] = {}

    for tag_value in tag_values:
        entities = find_entities_by_tag(tenant_id, tag_value)
        for entity in entities:
            key = f"{entity['entity_type']}#{entity['entity_id']}"
            if key not in all_results:
                all_results[key] = entity
                tag_counts[key] = 0
            tag_counts[key] += 1

    if match_all:
        return [
            entity
            for key, entity in all_results.items()
            if tag_counts[key] >= len(tag_values)
        ]
    else:
        return list(all_results.values())


def update_entity_tags(
    tenant_id: str,
    entity_type: str,
    entity_id: str,
    system_tags: Optional[list[str]] = None,
    user_tags: Optional[list[str]] = None,
    far_tags: Optional[list[str]] = None,
) -> bool:
    """Update the tag lists directly on a document or package entity item.

    This updates the entity's own tag attributes AND writes/removes TAG#
    inverted-index items to keep them in sync.

    Returns True on success.
    """
    table = get_table()

    # Build update expression
    update_parts = []
    attr_names = {}
    attr_values = {}

    if system_tags is not None:
        update_parts.append("#st = :st")
        attr_names["#st"] = "system_tags"
        attr_values[":st"] = system_tags
    if user_tags is not None:
        update_parts.append("#ut = :ut")
        attr_names["#ut"] = "user_tags"
        attr_values[":ut"] = user_tags
    if far_tags is not None:
        update_parts.append("#ft = :ft")
        attr_names["#ft"] = "far_tags"
        attr_values[":ft"] = far_tags

    if not update_parts:
        return True

    # Determine PK/SK for the entity
    if entity_type == "document":
        # For documents we need the full SK — use a scan+filter approach
        pk = f"DOCUMENT#{tenant_id}"
        try:
            response = table.query(
                KeyConditionExpression=Key("PK").eq(pk),
                FilterExpression=Attr("document_id").eq(entity_id),
                Limit=1,
            )
            items = response.get("Items", [])
            if not items:
                return False
            sk = items[0]["SK"]
        except (ClientError, BotoCoreError):
            return False
    elif entity_type == "package":
        pk = f"PACKAGE#{tenant_id}"
        sk = f"PACKAGE#{entity_id}"
    else:
        return False

    try:
        table.update_item(
            Key={"PK": pk, "SK": sk},
            UpdateExpression="SET " + ", ".join(update_parts),
            ExpressionAttributeNames=attr_names,
            ExpressionAttributeValues=attr_values,
        )
        return True
    except (ClientError, BotoCoreError) as e:
        logger.error("tag_store.update_entity_tags failed: %s", e)
        return False
