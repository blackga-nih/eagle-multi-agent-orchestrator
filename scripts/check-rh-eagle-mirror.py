#!/usr/bin/env python3
"""Check whether rh-eagle and rh-eagle-files contain the same objects.

This is a read-only drift check for the cross-account RH EAGLE mirror:

    source:      ro profile,    s3://rh-eagle/
    destination: eagle profile, s3://rh-eagle-files/

It compares file objects by S3 key, size, and ETag. Directory marker objects
ending in "/" are ignored.

Usage:
    python3 scripts/check-rh-eagle-mirror.py
    python3 scripts/check-rh-eagle-mirror.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass

import boto3
from botocore.exceptions import BotoCoreError, ClientError, ProfileNotFound


DEFAULT_SOURCE_PROFILE = "ro"
DEFAULT_DEST_PROFILE = "eagle"
DEFAULT_SOURCE_BUCKET = "rh-eagle"
DEFAULT_DEST_BUCKET = "rh-eagle-files"
DEFAULT_REGION = "us-east-1"


@dataclass(frozen=True)
class ObjectInfo:
    key: str
    size: int
    etag: str
    last_modified: str


@dataclass(frozen=True)
class ChangedObject:
    key: str
    source: ObjectInfo
    destination: ObjectInfo


def s3_client(profile: str, region: str):
    session = boto3.Session(profile_name=profile, region_name=region)
    return session.client("s3", region_name=region)


def list_objects(client, bucket: str, prefix: str = "") -> dict[str, ObjectInfo]:
    paginator = client.get_paginator("list_objects_v2")
    objects: dict[str, ObjectInfo] = {}

    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith("/"):
                continue
            objects[key] = ObjectInfo(
                key=key,
                size=int(obj["Size"]),
                etag=str(obj.get("ETag", "")),
                last_modified=obj["LastModified"].isoformat(),
            )

    return objects


def compare(
    source: dict[str, ObjectInfo],
    destination: dict[str, ObjectInfo],
) -> tuple[list[ObjectInfo], list[ChangedObject], list[ObjectInfo]]:
    missing_in_destination: list[ObjectInfo] = []
    changed: list[ChangedObject] = []
    destination_only: list[ObjectInfo] = []

    for key, src in sorted(source.items()):
        dest = destination.get(key)
        if dest is None:
            missing_in_destination.append(src)
        elif src.size != dest.size or src.etag != dest.etag:
            changed.append(ChangedObject(key=key, source=src, destination=dest))

    for key, dest in sorted(destination.items()):
        if key not in source:
            destination_only.append(dest)

    return missing_in_destination, changed, destination_only


def print_text_report(
    source_bucket: str,
    dest_bucket: str,
    source_count: int,
    dest_count: int,
    missing: list[ObjectInfo],
    changed: list[ChangedObject],
    dest_only: list[ObjectInfo],
    limit: int,
) -> None:
    drift_count = len(missing) + len(changed) + len(dest_only)
    status = "MATCH" if drift_count == 0 else "DRIFT"

    print(f"Source:      s3://{source_bucket}/ ({source_count} files)")
    print(f"Destination: s3://{dest_bucket}/ ({dest_count} files)")
    print(f"Status:      {status}")
    print()
    print(f"missing_in_destination={len(missing)}")
    print(f"changed_same_key={len(changed)}")
    print(f"destination_only={len(dest_only)}")

    def truncated(items):
        return items if limit <= 0 else items[:limit]

    if missing:
        print("\nMISSING_IN_DESTINATION")
        for obj in truncated(missing):
            print(f"{obj.size}\t{obj.etag}\t{obj.key}")
        if limit > 0 and len(missing) > limit:
            print(f"... {len(missing) - limit} more")

    if changed:
        print("\nCHANGED_SAME_KEY")
        for obj in truncated(changed):
            print(
                f"{obj.key}\n"
                f"  source:      size={obj.source.size} etag={obj.source.etag}\n"
                f"  destination: size={obj.destination.size} etag={obj.destination.etag}"
            )
        if limit > 0 and len(changed) > limit:
            print(f"... {len(changed) - limit} more")

    if dest_only:
        print("\nDESTINATION_ONLY")
        for obj in truncated(dest_only):
            print(f"{obj.size}\t{obj.etag}\t{obj.key}")
        if limit > 0 and len(dest_only) > limit:
            print(f"... {len(dest_only) - limit} more")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only drift check for rh-eagle -> rh-eagle-files.",
    )
    parser.add_argument("--source-profile", default=DEFAULT_SOURCE_PROFILE)
    parser.add_argument("--dest-profile", default=DEFAULT_DEST_PROFILE)
    parser.add_argument("--source-bucket", default=DEFAULT_SOURCE_BUCKET)
    parser.add_argument("--dest-bucket", default=DEFAULT_DEST_BUCKET)
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--prefix", default="", help="Optional common prefix to compare")
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum rows per drift section in text output; use 0 for no limit",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args()

    try:
        source_client = s3_client(args.source_profile, args.region)
        dest_client = s3_client(args.dest_profile, args.region)
        source = list_objects(source_client, args.source_bucket, args.prefix)
        destination = list_objects(dest_client, args.dest_bucket, args.prefix)
    except ProfileNotFound as exc:
        print(f"ERROR: AWS profile not found: {exc}", file=sys.stderr)
        return 2
    except (BotoCoreError, ClientError) as exc:
        print(f"ERROR: AWS inventory failed: {exc}", file=sys.stderr)
        return 2

    missing, changed, dest_only = compare(source, destination)
    drift_count = len(missing) + len(changed) + len(dest_only)

    if args.json:
        print(json.dumps(
            {
                "source_bucket": args.source_bucket,
                "destination_bucket": args.dest_bucket,
                "source_profile": args.source_profile,
                "destination_profile": args.dest_profile,
                "region": args.region,
                "prefix": args.prefix,
                "source_files": len(source),
                "destination_files": len(destination),
                "missing_in_destination": [asdict(obj) for obj in missing],
                "changed_same_key": [asdict(obj) for obj in changed],
                "destination_only": [asdict(obj) for obj in dest_only],
                "drift_count": drift_count,
                "matched": drift_count == 0,
            },
            indent=2,
        ))
    else:
        print_text_report(
            args.source_bucket,
            args.dest_bucket,
            len(source),
            len(destination),
            missing,
            changed,
            dest_only,
            args.limit,
        )

    return 0 if drift_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
