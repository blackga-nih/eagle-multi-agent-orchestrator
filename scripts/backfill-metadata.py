#!/usr/bin/env python3
"""Trigger metadata extraction Lambda for existing documents in S3.

This script invokes the metadata extraction Lambda for each document
in the knowledge base to populate the DynamoDB metadata table.

Usage:
    python scripts/backfill-metadata.py [--dry-run] [--limit N]
"""

from __future__ import annotations

import argparse
import json
import sys
import time

import boto3
from botocore.exceptions import ClientError

# Configuration
BUCKET = "eagle-documents-695681773636-dev"
PREFIX = "eagle-knowledge-base/approved/"
LAMBDA_NAME = "eagle-metadata-extractor-dev"

# Rate limiting to avoid Lambda throttling
BATCH_SIZE = 5
BATCH_DELAY_SECONDS = 2  # Give Lambda time to process


def get_documents(s3_client, prefix: str = PREFIX) -> list[dict]:
    """List all documents in the knowledge base prefix."""
    paginator = s3_client.get_paginator("list_objects_v2")
    documents = []

    for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            # Skip directory markers
            if key.endswith("/"):
                continue
            documents.append({
                "key": key,
                "size": obj["Size"],
            })

    return documents


def invoke_lambda(lambda_client, key: str, size: int, dry_run: bool = False) -> bool:
    """Invoke the metadata extraction Lambda for a single document."""
    # Simulate S3 event structure
    event = {
        "Records": [{
            "s3": {
                "bucket": {"name": BUCKET},
                "object": {"key": key, "size": size}
            }
        }]
    }

    if dry_run:
        print(f"  [DRY RUN] Would invoke Lambda for: {key}")
        return True

    try:
        response = lambda_client.invoke(
            FunctionName=LAMBDA_NAME,
            InvocationType="Event",  # Async invocation
            Payload=json.dumps(event),
        )
        status = response.get("StatusCode", 0)
        if status == 202:  # Accepted for async
            print(f"  Triggered: {key}")
            return True
        else:
            print(f"  WARNING: Unexpected status {status} for {key}")
            return False
    except ClientError as e:
        print(f"  ERROR invoking Lambda for {key}: {e}")
        return False


def backfill_metadata(dry_run: bool = False, limit: int = 0) -> dict:
    """Trigger Lambda for all documents to extract metadata."""
    s3 = boto3.client("s3")
    lambda_client = boto3.client("lambda")

    print(f"Bucket: s3://{BUCKET}/{PREFIX}")
    print(f"Lambda: {LAMBDA_NAME}")
    print()

    # Get list of documents
    print("Scanning for documents...")
    documents = get_documents(s3)
    total = len(documents)
    print(f"Found {total} documents")

    if limit > 0:
        documents = documents[:limit]
        print(f"Limiting to first {limit} documents")

    print()

    if not documents:
        print("No documents to process.")
        return {"total": 0, "triggered": 0, "failed": 0}

    # Trigger Lambda for each document
    triggered = 0
    failed = 0
    to_process = len(documents)

    for i, doc in enumerate(documents, 1):
        key = doc["key"]
        size = doc["size"]
        size_kb = size / 1024

        print(f"[{i}/{to_process}] {key} ({size_kb:.1f} KB)")

        if invoke_lambda(lambda_client, key, size, dry_run):
            triggered += 1
        else:
            failed += 1

        # Rate limiting
        if i % BATCH_SIZE == 0 and i < to_process:
            print(f"  ... pausing {BATCH_DELAY_SECONDS}s for Lambda processing ...")
            time.sleep(BATCH_DELAY_SECONDS)

    print()
    print("=" * 60)
    print("Backfill triggered!")
    print(f"  Total documents: {total}")
    print(f"  Processed:       {to_process}")
    print(f"  Triggered:       {triggered}")
    print(f"  Failed:          {failed}")

    if dry_run:
        print()
        print("This was a DRY RUN. No Lambdas were actually invoked.")
        print("Run without --dry-run to trigger metadata extraction.")

    print()
    print("Note: Lambda invocations are async. Check CloudWatch Logs for progress.")
    print("Verify results with:")
    print(f"  aws dynamodb scan --table-name eagle-document-metadata-dev --select COUNT")

    return {"total": total, "triggered": triggered, "failed": failed}


def main():
    parser = argparse.ArgumentParser(
        description="Trigger metadata extraction for existing documents"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be triggered without actually invoking Lambda",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit to first N documents (0 = no limit)",
    )
    args = parser.parse_args()

    try:
        result = backfill_metadata(dry_run=args.dry_run, limit=args.limit)
        sys.exit(0 if result["failed"] == 0 else 1)
    except ClientError as e:
        print(f"AWS Error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nBackfill interrupted.")
        sys.exit(1)


if __name__ == "__main__":
    main()
