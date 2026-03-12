#!/usr/bin/env python3
"""Migrate legacy chat S3 documents to canonical package/workspace records.

Legacy source path pattern:
  eagle/{tenant_id}/{user_id}/documents/{doc_type}_{YYYYMMDD_HHMMSS}.{ext}

Canonical package destination uses app.document_service.create_package_document_version():
  eagle/{tenant_id}/packages/{package_id}/{doc_type}/v{version}/{artifact}.{ext}

The script attempts to map each legacy object to a package by inspecting session
metadata (`active_package_id`) for sessions whose stored messages mention the
legacy object key. Unmapped records follow the configured orphan strategy.

Usage examples:
  python scripts/migrate-chat-s3-docs-to-package-records.py \
    --tenant-id dev-tenant --dry-run

  python scripts/migrate-chat-s3-docs-to-package-records.py \
    --tenant-id dev-tenant --orphan-strategy workdoc --limit 100
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import boto3
from boto3.dynamodb.conditions import Attr
from botocore.exceptions import BotoCoreError, ClientError


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(ROOT, "server")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from app.document_service import create_package_document_version  # noqa: E402


LEGACY_KEY_RE = re.compile(
    r"^eagle/(?P<tenant>[^/]+)/(?P<user>[^/]+)/documents/"
    r"(?P<doc_type>[a-z_]+)_(?P<timestamp>\d{8}_\d{6})\.(?P<ext>[a-z0-9]+)$"
)


@dataclass
class LegacyObject:
    key: str
    user_id: str
    doc_type: str
    timestamp: str
    ext: str


@dataclass
class MigrationStats:
    discovered: int = 0
    migrated_to_package: int = 0
    migrated_to_workdoc: int = 0
    skipped_orphans: int = 0
    failed: int = 0


class Migrator:
    def __init__(
        self,
        tenant_id: str,
        table_name: str,
        bucket: str,
        orphan_strategy: str,
        dry_run: bool,
        limit: Optional[int],
    ):
        self.tenant_id = tenant_id
        self.table_name = table_name
        self.bucket = bucket
        self.orphan_strategy = orphan_strategy
        self.dry_run = dry_run
        self.limit = limit

        region = os.getenv("AWS_REGION", "us-east-1")
        self.s3 = boto3.client("s3", region_name=region)
        self.ddb = boto3.resource("dynamodb", region_name=region)
        self.table = self.ddb.Table(table_name)

        self.stats = MigrationStats()

    def run(self) -> int:
        print(
            f"Starting migration tenant={self.tenant_id} bucket={self.bucket} "
            f"table={self.table_name} dry_run={self.dry_run} orphan={self.orphan_strategy}"
        )
        for obj in self._iter_legacy_objects():
            self.stats.discovered += 1
            try:
                self._migrate_one(obj)
            except Exception as exc:  # pragma: no cover - safety net
                self.stats.failed += 1
                self._write_audit(
                    entity_type="migration",
                    entity_name=obj.key,
                    event_type="failed",
                    metadata={"error": str(exc)},
                )
                print(f"[failed] key={obj.key} error={exc}")

            if self.limit and self.stats.discovered >= self.limit:
                break

        print("Migration complete")
        print(
            "Summary: "
            f"discovered={self.stats.discovered} "
            f"pkg={self.stats.migrated_to_package} "
            f"workdoc={self.stats.migrated_to_workdoc} "
            f"skipped={self.stats.skipped_orphans} "
            f"failed={self.stats.failed}"
        )
        return 0 if self.stats.failed == 0 else 1

    def _iter_legacy_objects(self):
        paginator = self.s3.get_paginator("list_objects_v2")
        prefix = f"eagle/{self.tenant_id}/"
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for item in page.get("Contents", []):
                key = item.get("Key", "")
                parsed = self._parse_legacy_key(key)
                if parsed:
                    yield parsed

    def _parse_legacy_key(self, key: str) -> Optional[LegacyObject]:
        match = LEGACY_KEY_RE.match(key)
        if not match:
            return None
        if match.group("tenant") != self.tenant_id:
            return None

        return LegacyObject(
            key=key,
            user_id=match.group("user"),
            doc_type=match.group("doc_type"),
            timestamp=match.group("timestamp"),
            ext=match.group("ext"),
        )

    def _migrate_one(self, obj: LegacyObject) -> None:
        package_id, reason = self._resolve_package_for_object(obj)
        if package_id:
            self._migrate_to_package(obj, package_id, reason)
            return

        self._handle_orphan(obj, reason or "no_package_association")

    def _resolve_package_for_object(self, obj: LegacyObject) -> tuple[Optional[str], str]:
        """Try resolving package from sessions mentioning this object key."""
        filename = obj.key.rsplit("/", 1)[-1]

        try:
            resp = self.table.scan(
                FilterExpression=Attr("PK").begins_with(f"SESSION#{self.tenant_id}#")
                & Attr("SK").begins_with("MSG#")
                & Attr("content").contains(filename),
                ProjectionExpression="PK,SK",
            )
        except (ClientError, BotoCoreError):
            return None, "message_scan_failed"

        for item in resp.get("Items", []):
            pk = item.get("PK", "")
            sk = item.get("SK", "")
            session_id = self._extract_session_id_from_msg_sk(sk)
            if not session_id:
                continue

            try:
                session_item = self.table.get_item(
                    Key={"PK": pk, "SK": f"SESSION#{session_id}"}
                ).get("Item")
            except (ClientError, BotoCoreError):
                session_item = None

            metadata = (session_item or {}).get("metadata", {})
            package_id = metadata.get("active_package_id")
            if package_id:
                return package_id, f"session:{session_id}"

        return None, "no_matching_session_metadata"

    @staticmethod
    def _extract_session_id_from_msg_sk(sk: str) -> Optional[str]:
        if not sk.startswith("MSG#"):
            return None
        parts = sk.split("#")
        if len(parts) < 3:
            return None
        return parts[1]

    def _migrate_to_package(self, obj: LegacyObject, package_id: str, reason: str) -> None:
        title = f"{obj.doc_type.replace('_', ' ').title()} Migrated {obj.timestamp}"

        if self.dry_run:
            self.stats.migrated_to_package += 1
            print(f"[dry-run][package] key={obj.key} package={package_id} reason={reason}")
            return

        payload = self.s3.get_object(Bucket=self.bucket, Key=obj.key)["Body"].read()

        result = create_package_document_version(
            tenant_id=self.tenant_id,
            package_id=package_id,
            doc_type=obj.doc_type,
            content=payload,
            title=title,
            file_type=obj.ext,
            created_by_user_id=obj.user_id,
            session_id=None,
            change_source="migration",
            template_id=None,
        )
        if not result.success:
            self.stats.failed += 1
            self._write_audit(
                entity_type="migration",
                entity_name=obj.key,
                event_type="failed",
                metadata={"target": "package", "package_id": package_id, "error": result.error},
            )
            print(f"[failed][package] key={obj.key} package={package_id} error={result.error}")
            return

        self.stats.migrated_to_package += 1
        self._write_audit(
            entity_type="migration",
            entity_name=obj.key,
            event_type="migrated_to_package",
            metadata={
                "package_id": package_id,
                "doc_type": obj.doc_type,
                "version": result.version,
                "reason": reason,
                "canonical_s3_key": result.s3_key,
            },
        )
        print(
            f"[ok][package] key={obj.key} package={package_id} "
            f"version={result.version} canonical={result.s3_key}"
        )

    def _handle_orphan(self, obj: LegacyObject, reason: str) -> None:
        if self.orphan_strategy == "skip":
            self.stats.skipped_orphans += 1
            if not self.dry_run:
                self._write_orphan_audit(obj, "skip", reason)
            print(f"[orphan][skip] key={obj.key} reason={reason}")
            return

        if self.orphan_strategy == "placeholder":
            placeholder_package_id = self._placeholder_package_id()
            self._migrate_to_package(obj, placeholder_package_id, f"orphan:{reason}")
            return

        # Default: workdoc
        self._migrate_to_workdoc(obj, reason)

    def _migrate_to_workdoc(self, obj: LegacyObject, reason: str) -> None:
        self.stats.migrated_to_workdoc += 1

        if self.dry_run:
            print(f"[dry-run][workdoc] key={obj.key} reason={reason}")
            return

        now = datetime.now(timezone.utc).isoformat()
        workdoc_id = str(uuid.uuid4())
        item = {
            "PK": f"WORKDOC#{self.tenant_id}",
            "SK": f"WORKDOC#{obj.user_id}#{obj.doc_type}#{obj.timestamp}",
            "workdoc_id": workdoc_id,
            "tenant_id": self.tenant_id,
            "user_id": obj.user_id,
            "doc_type": obj.doc_type,
            "status": "migrated",
            "source": "legacy_chat_s3",
            "source_s3_key": obj.key,
            "file_type": obj.ext,
            "created_at": now,
            "updated_at": now,
        }
        self.table.put_item(Item=item)
        self._write_orphan_audit(obj, "workdoc", reason)
        print(f"[ok][workdoc] key={obj.key} workdoc_id={workdoc_id}")

    def _write_orphan_audit(self, obj: LegacyObject, option: str, reason: str) -> None:
        self._write_audit(
            entity_type="orphan_classification",
            entity_name=obj.key,
            event_type="classified",
            metadata={
                "action": "orphan_classification",
                "option": option,
                "reason": reason,
                "doc_type": obj.doc_type,
                "original_s3_key": obj.key,
            },
        )

    def _write_audit(
        self,
        entity_type: str,
        entity_name: str,
        event_type: str,
        metadata: dict,
    ) -> None:
        if self.dry_run:
            return
        occurred_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        ttl = int((datetime.now(timezone.utc) + timedelta(days=365 * 7)).timestamp())
        audit_item = {
            "PK": f"AUDIT#{self.tenant_id}",
            "SK": f"AUDIT#{occurred_at}#{entity_type}#{entity_name}",
            "tenant_id": self.tenant_id,
            "event_type": event_type,
            "entity_type": entity_type,
            "entity_name": entity_name,
            "actor_user_id": "migration-script",
            "occurred_at": occurred_at,
            "metadata": metadata,
            "ttl": ttl,
        }
        self.table.put_item(Item=audit_item)

    @staticmethod
    def _placeholder_package_id() -> str:
        return f"PKG-MIGRATED-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", required=True, help="Tenant ID to migrate")
    parser.add_argument(
        "--table-name",
        default=os.getenv("EAGLE_SESSIONS_TABLE", "eagle"),
        help="DynamoDB single-table name",
    )
    parser.add_argument(
        "--bucket",
        default=os.getenv("S3_BUCKET", "eagle-documents-695681773636-dev"),
        help="S3 bucket containing legacy and canonical docs",
    )
    parser.add_argument(
        "--orphan-strategy",
        choices=["workdoc", "placeholder", "skip"],
        default="workdoc",
        help="Handling for docs that cannot be mapped to a package",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print actions only")
    parser.add_argument("--limit", type=int, default=None, help="Max docs to process")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    migrator = Migrator(
        tenant_id=args.tenant_id,
        table_name=args.table_name,
        bucket=args.bucket,
        orphan_strategy=args.orphan_strategy,
        dry_run=args.dry_run,
        limit=args.limit,
    )
    return migrator.run()


if __name__ == "__main__":
    raise SystemExit(main())
