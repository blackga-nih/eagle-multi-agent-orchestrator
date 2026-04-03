"""Wipe all DOCUMENT#, DOC#, and PACKAGE# entities from DynamoDB + S3 documents.

Usage:
    python scripts/wipe_documents_and_packages.py              # Dry run (counts only)
    python scripts/wipe_documents_and_packages.py --confirm    # Actually delete
"""

import argparse
import boto3
from boto3.dynamodb.conditions import Attr

TABLE_NAME = "eagle"
DOCUMENT_BUCKET = "eagle-documents-695681773636-dev"
REGION = "us-east-1"

PK_PREFIXES = ["DOCUMENT#", "DOC#", "PACKAGE#"]


def scan_items(table, prefix: str) -> list[dict]:
    """Scan for all items whose PK starts with the given prefix."""
    items = []
    kwargs = {
        "FilterExpression": Attr("PK").begins_with(prefix),
        "ProjectionExpression": "PK, SK",
    }
    while True:
        response = table.scan(**kwargs)
        items.extend(response.get("Items", []))
        if "LastEvaluatedKey" not in response:
            break
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    return items


def delete_items(table, items: list[dict]) -> int:
    """Batch-delete items from DynamoDB."""
    deleted = 0
    with table.batch_writer() as batch:
        for item in items:
            batch.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})
            deleted += 1
    return deleted


def list_s3_objects(s3, bucket: str) -> list[str]:
    """List all object keys in the bucket."""
    keys = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    return keys


def delete_s3_objects(s3, bucket: str, keys: list[str]) -> int:
    """Batch-delete S3 objects (1000 per request)."""
    deleted = 0
    for i in range(0, len(keys), 1000):
        batch = keys[i : i + 1000]
        s3.delete_objects(
            Bucket=bucket,
            Delete={"Objects": [{"Key": k} for k in batch]},
        )
        deleted += len(batch)
    return deleted


def main():
    parser = argparse.ArgumentParser(description="Wipe documents and packages from DDB + S3")
    parser.add_argument("--confirm", action="store_true", help="Actually delete (default is dry run)")
    args = parser.parse_args()

    session = boto3.Session(region_name=REGION, profile_name="eagle")
    dynamodb = session.resource("dynamodb")
    table = dynamodb.Table(TABLE_NAME)
    s3 = session.client("s3")

    # -- DynamoDB --
    all_items: dict[str, list[dict]] = {}
    total_ddb = 0
    for prefix in PK_PREFIXES:
        items = scan_items(table, prefix)
        all_items[prefix] = items
        total_ddb += len(items)
        print(f"  {prefix}*  ->  {len(items)} items")

    print(f"\nTotal DynamoDB items to delete: {total_ddb}")

    # -- S3 --
    print(f"\nScanning S3 bucket: {DOCUMENT_BUCKET}")
    s3_keys = list_s3_objects(s3, DOCUMENT_BUCKET)
    print(f"  Total S3 objects: {len(s3_keys)}")

    if not args.confirm:
        print("\nWARNING:  DRY RUN — pass --confirm to actually delete")
        return

    # Delete DynamoDB
    print("\nDeleting DynamoDB items...")
    for prefix, items in all_items.items():
        if items:
            count = delete_items(table, items)
            print(f"  Deleted {count} {prefix}* items")

    # Delete S3
    if s3_keys:
        print(f"\nDeleting {len(s3_keys)} S3 objects...")
        count = delete_s3_objects(s3, DOCUMENT_BUCKET, s3_keys)
        print(f"  Deleted {count} S3 objects")

    print("\nDone.")


if __name__ == "__main__":
    main()
