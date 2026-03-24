"""Migration: Backfill system_tags, threshold_tier, approval_level on existing PACKAGE# items.

Scans all PACKAGE# items and computes tags from existing metadata using the
tag_computation module.

Usage:
    python -m scripts.migrate_package_tags [--dry-run] [--tenant TENANT_ID]
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


def migrate(dry_run: bool = True, tenant_id: str | None = None):
    """Run the migration."""
    table = _get_table()
    updated = 0
    errors = 0

    # Scan PACKAGE# items
    if tenant_id:
        response = table.query(
            KeyConditionExpression=Key("PK").eq(f"PACKAGE#{tenant_id}"),
        )
    else:
        response = table.scan(
            FilterExpression=Attr("PK").begins_with("PACKAGE#") & Attr("SK").begins_with("PACKAGE#"),
        )

    items = response.get("Items", [])
    logger.info("Found %d PACKAGE# items to migrate", len(items))

    for item in items:
        pk = item["PK"]
        sk = item["SK"]
        package_id = item.get("package_id", "")

        try:
            from app.tag_computation import (
                compute_package_tags,
                compute_threshold_tier,
                compute_approval_level,
            )

            system_tags = compute_package_tags(item)
            estimated_value = float(item.get("estimated_value", 0))
            threshold_tier = compute_threshold_tier(estimated_value)
            approval_level = compute_approval_level(
                estimated_value,
                item.get("acquisition_method", ""),
                item.get("contract_type", ""),
            )
        except Exception as e:
            logger.warning("Tag computation failed for %s: %s", package_id, e)
            system_tags = []
            threshold_tier = ""
            approval_level = ""

        if dry_run:
            logger.info(
                "[DRY RUN] Would update %s: system_tags=%s, threshold=%s, approval=%s",
                package_id, system_tags[:3], threshold_tier, approval_level,
            )
            updated += 1
            continue

        try:
            table.update_item(
                Key={"PK": pk, "SK": sk},
                UpdateExpression=(
                    "SET system_tags = :st, threshold_tier = :tt, approval_level = :al"
                ),
                ExpressionAttributeValues={
                    ":st": system_tags,
                    ":tt": threshold_tier,
                    ":al": approval_level,
                },
            )
            updated += 1
            logger.info("Updated package %s", package_id)
        except Exception as e:
            errors += 1
            logger.error("Failed to update %s: %s", package_id, e)

    logger.info("Migration complete: %d updated, %d errors", updated, errors)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill tags on PACKAGE# items")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Preview changes without writing")
    parser.add_argument("--execute", action="store_true", help="Actually write changes")
    parser.add_argument("--tenant", type=str, help="Limit to a specific tenant_id")
    args = parser.parse_args()

    migrate(dry_run=not args.execute, tenant_id=args.tenant)
