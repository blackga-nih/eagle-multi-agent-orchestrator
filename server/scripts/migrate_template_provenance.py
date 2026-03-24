"""Migration: Backfill template_provenance on existing DOCUMENT# items.

Scans all DOCUMENT# items where template_id exists but template_provenance does not.
Reconstructs provenance from the template_id string and backfills system/far tags.

Usage:
    python -m scripts.migrate_template_provenance [--dry-run] [--tenant TENANT_ID]
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


def _get_table():
    dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
    return dynamodb.Table(TABLE_NAME)


def _reconstruct_provenance(item: dict) -> dict:
    """Reconstruct template_provenance from a legacy template_id string."""
    template_id = item.get("template_id", "")
    doc_type = item.get("doc_type", "")

    # Determine source type from template_id format
    if "/" in template_id:
        # Looks like an S3 key
        source = "s3_template"
    elif template_id:
        source = "plugin"
    else:
        source = "markdown_fallback"

    return {
        "template_id": template_id,
        "template_source": source,
        "template_version": 1,
        "template_name": doc_type.replace("_", " ").replace("-", " ").title(),
        "doc_type": doc_type,
    }


def _compute_tags_for_document(item: dict) -> dict:
    """Compute system_tags and far_tags for a document."""
    doc_type = item.get("doc_type", "")
    tags = {
        "system_tags": [f"doc_type:{doc_type}", f"status:{item.get('status', 'draft')}"],
        "far_tags": [],
    }

    # Try to compute far_tags from template clause references
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
        from tag_computation import compute_far_tags_from_template
        tags["far_tags"] = compute_far_tags_from_template(doc_type)
    except Exception:
        pass

    return tags


def migrate(dry_run: bool = True, tenant_id: str | None = None):
    """Run the migration."""
    table = _get_table()
    updated = 0
    skipped = 0
    errors = 0

    # Scan DOCUMENT# items
    scan_kwargs = {
        "FilterExpression": (
            Attr("template_id").exists()
            & Attr("template_provenance").not_exists()
            & Key("PK").begins_with("DOCUMENT#")
        ),
    }

    if tenant_id:
        scan_kwargs["FilterExpression"] = (
            Attr("template_id").exists()
            & Attr("template_provenance").not_exists()
        )
        scan_kwargs["KeyConditionExpression"] = Key("PK").eq(f"DOCUMENT#{tenant_id}")
        response = table.query(**scan_kwargs)
    else:
        response = table.scan(**scan_kwargs)

    items = response.get("Items", [])
    logger.info("Found %d DOCUMENT# items to migrate", len(items))

    for item in items:
        pk = item["PK"]
        sk = item["SK"]
        doc_type = item.get("doc_type", "")

        provenance = _reconstruct_provenance(item)
        tags = _compute_tags_for_document(item)

        if dry_run:
            logger.info("[DRY RUN] Would update %s / %s (doc_type=%s) → provenance=%s", pk, sk, doc_type, provenance)
            updated += 1
            continue

        try:
            update_expr = "SET template_provenance = :prov, system_tags = :st"
            expr_values = {
                ":prov": provenance,
                ":st": tags["system_tags"],
            }
            if tags["far_tags"]:
                update_expr += ", far_tags = :ft"
                expr_values[":ft"] = tags["far_tags"]

            table.update_item(
                Key={"PK": pk, "SK": sk},
                UpdateExpression=update_expr,
                ExpressionAttributeValues=expr_values,
            )
            updated += 1
            logger.info("Updated %s / %s (doc_type=%s)", pk, sk, doc_type)
        except Exception as e:
            errors += 1
            logger.error("Failed to update %s / %s: %s", pk, sk, e)

    logger.info(
        "Migration complete: %d updated, %d skipped, %d errors",
        updated, skipped, errors,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill template_provenance on DOCUMENT# items")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Preview changes without writing")
    parser.add_argument("--execute", action="store_true", help="Actually write changes")
    parser.add_argument("--tenant", type=str, help="Limit to a specific tenant_id")
    args = parser.parse_args()

    migrate(dry_run=not args.execute, tenant_id=args.tenant)
