"""Migration: Update owner_user_id on PACKAGE# items.

Scans PACKAGE# items for a tenant and updates owner_user_id from a source
value (default "dev-user") to a target value (default "blackga").

Usage:
    python -m scripts.migrate_package_owner --tenant dev-tenant --dry-run
    python -m scripts.migrate_package_owner --tenant dev-tenant --execute
    python -m scripts.migrate_package_owner --tenant dev-tenant --from-user dev-user --to-user blackga --execute
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

import boto3
from boto3.dynamodb.conditions import Attr, Key

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

TABLE_NAME = os.getenv("EAGLE_SESSIONS_TABLE", "eagle")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# Add app to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _get_table():
    dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
    return dynamodb.Table(TABLE_NAME)


def migrate(
    dry_run: bool = True,
    tenant_id: str | None = None,
    from_user: str = "dev-user",
    to_user: str = "blackga",
):
    """Run the migration."""
    table = _get_table()
    updated = 0
    skipped = 0
    errors = 0

    # Query PACKAGE# items
    if tenant_id:
        response = table.query(
            KeyConditionExpression=Key("PK").eq(f"PACKAGE#{tenant_id}"),
        )
    else:
        response = table.scan(
            FilterExpression=Attr("PK").begins_with("PACKAGE#") & Attr("SK").begins_with("PACKAGE#"),
        )

    items = response.get("Items", [])
    logger.info("Found %d PACKAGE# items total", len(items))

    # Filter to items with the source owner
    targets = [i for i in items if i.get("owner_user_id") == from_user]
    logger.info("%d items have owner_user_id=%r (will migrate to %r)", len(targets), from_user, to_user)

    if not targets:
        logger.info("Nothing to migrate.")
        return

    for item in targets:
        pk = item["PK"]
        sk = item["SK"]
        package_id = item.get("package_id", "")
        title = item.get("title", "")[:50]

        if dry_run:
            logger.info(
                "[DRY RUN] Would update %s (%s): owner_user_id %r -> %r",
                package_id, title, from_user, to_user,
            )
            updated += 1
            continue

        try:
            table.update_item(
                Key={"PK": pk, "SK": sk},
                UpdateExpression="SET owner_user_id = :new_owner",
                ConditionExpression=Attr("owner_user_id").eq(from_user),
                ExpressionAttributeValues={":new_owner": to_user},
            )
            updated += 1
            logger.info("Updated %s (%s): owner -> %r", package_id, title, to_user)
        except Exception as e:
            errors += 1
            logger.error("Failed to update %s: %s", package_id, e)

    # Also update items with empty owner
    empty_owners = [i for i in items if not i.get("owner_user_id")]
    if empty_owners:
        logger.info("%d items have empty owner_user_id", len(empty_owners))
        for item in empty_owners:
            pk = item["PK"]
            sk = item["SK"]
            package_id = item.get("package_id", "")
            title = item.get("title", "")[:50]

            if dry_run:
                logger.info(
                    "[DRY RUN] Would update %s (%s): owner_user_id '' -> %r",
                    package_id, title, to_user,
                )
                updated += 1
                continue

            try:
                table.update_item(
                    Key={"PK": pk, "SK": sk},
                    UpdateExpression="SET owner_user_id = :new_owner",
                    ExpressionAttributeValues={":new_owner": to_user},
                )
                updated += 1
                logger.info("Updated %s (%s): empty owner -> %r", package_id, title, to_user)
            except Exception as e:
                errors += 1
                logger.error("Failed to update %s: %s", package_id, e)

    logger.info("Migration complete: %d updated, %d skipped, %d errors", updated, skipped, errors)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Update owner_user_id on PACKAGE# items")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Preview changes without writing")
    parser.add_argument("--execute", action="store_true", help="Actually write changes")
    parser.add_argument("--tenant", type=str, help="Limit to a specific tenant_id")
    parser.add_argument("--from-user", type=str, default="dev-user", help="Source owner_user_id (default: dev-user)")
    parser.add_argument("--to-user", type=str, default="blackga", help="Target owner_user_id (default: blackga)")
    args = parser.parse_args()

    migrate(dry_run=not args.execute, tenant_id=args.tenant, from_user=args.from_user, to_user=args.to_user)
