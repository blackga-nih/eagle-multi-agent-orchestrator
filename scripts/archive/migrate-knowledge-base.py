#!/usr/bin/env python3
"""Migrate knowledge base documents from rh-eagle-files to eagle-documents bucket.

This script copies all documents from the source bucket to the destination bucket,
preserving the folder structure under the eagle-knowledge-base/approved/ prefix.

Usage:
    python scripts/migrate-knowledge-base.py [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
import time

import boto3
from botocore.exceptions import ClientError

# Configuration
SOURCE_BUCKET = "rh-eagle-files"
DEST_BUCKET = "eagle-documents-695681773636-dev"
DEST_PREFIX = "eagle-knowledge-base/approved/"

# Rate limiting to avoid Lambda throttling
BATCH_SIZE = 10
BATCH_DELAY_SECONDS = 1


def get_source_objects(s3_client) -> list[dict]:
    """List all objects in the source bucket."""
    paginator = s3_client.get_paginator("list_objects_v2")
    objects = []

    for page in paginator.paginate(Bucket=SOURCE_BUCKET):
        for obj in page.get("Contents", []):
            objects.append({
                "key": obj["Key"],
                "size": obj["Size"],
                "last_modified": obj["LastModified"],
            })

    return objects


def copy_object(s3_client, source_key: str, dry_run: bool = False) -> bool:
    """Copy a single object from source to destination bucket."""
    dest_key = f"{DEST_PREFIX}{source_key}"

    if dry_run:
        print(f"  [DRY RUN] Would copy: {source_key} -> {dest_key}")
        return True

    try:
        s3_client.copy_object(
            CopySource={"Bucket": SOURCE_BUCKET, "Key": source_key},
            Bucket=DEST_BUCKET,
            Key=dest_key,
        )
        print(f"  Copied: {source_key} -> {dest_key}")
        return True
    except ClientError as e:
        print(f"  ERROR copying {source_key}: {e}")
        return False


def migrate_documents(dry_run: bool = False) -> dict:
    """Copy all documents from source to destination bucket."""
    s3 = boto3.client("s3")

    print(f"Source bucket: s3://{SOURCE_BUCKET}/")
    print(f"Destination:   s3://{DEST_BUCKET}/{DEST_PREFIX}")
    print()

    # Get list of objects to migrate
    print("Scanning source bucket...")
    objects = get_source_objects(s3)
    total = len(objects)
    print(f"Found {total} objects to migrate")
    print()

    if total == 0:
        print("No objects to migrate.")
        return {"total": 0, "copied": 0, "failed": 0}

    # Copy objects in batches
    copied = 0
    failed = 0

    for i, obj in enumerate(objects, 1):
        source_key = obj["key"]
        size_kb = obj["size"] / 1024

        print(f"[{i}/{total}] {source_key} ({size_kb:.1f} KB)")

        if copy_object(s3, source_key, dry_run):
            copied += 1
        else:
            failed += 1

        # Rate limiting
        if i % BATCH_SIZE == 0 and i < total:
            print(f"  ... pausing {BATCH_DELAY_SECONDS}s to avoid throttling ...")
            time.sleep(BATCH_DELAY_SECONDS)

    print()
    print("=" * 60)
    print(f"Migration complete!")
    print(f"  Total:  {total}")
    print(f"  Copied: {copied}")
    print(f"  Failed: {failed}")

    if dry_run:
        print()
        print("This was a DRY RUN. No files were actually copied.")
        print("Run without --dry-run to perform the migration.")

    return {"total": total, "copied": copied, "failed": failed}


def main():
    parser = argparse.ArgumentParser(
        description="Migrate knowledge base documents to eagle-documents bucket"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be copied without actually copying",
    )
    args = parser.parse_args()

    try:
        result = migrate_documents(dry_run=args.dry_run)
        sys.exit(0 if result["failed"] == 0 else 1)
    except ClientError as e:
        print(f"AWS Error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nMigration interrupted.")
        sys.exit(1)


if __name__ == "__main__":
    main()
