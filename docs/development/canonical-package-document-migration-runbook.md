# Canonical Package Document Migration Runbook

## Purpose

Backfill legacy chat-generated S3 documents (`eagle/{tenant}/{user}/documents/...`) into the canonical package/workspace model used by `DOCUMENT#` + deterministic package S3 keys.

## Script

- Path: `scripts/migrate-chat-s3-docs-to-package-records.py`

## What the Script Does

1. Discovers legacy S3 keys for a tenant.
2. Infers `doc_type` and timestamp from filename.
3. Attempts package mapping by checking session metadata (`active_package_id`) for sessions whose messages reference the legacy filename.
4. If mapped, writes a canonical package document version via `document_service.create_package_document_version(...)`.
5. If unmapped, applies orphan strategy:
- `workdoc` (default): writes `WORKDOC#` record and audit entry.
- `placeholder`: assigns to placeholder package ID `PKG-MIGRATED-{timestamp}`.
- `skip`: no migration write; logs audit classification.
6. Writes `AUDIT#` migration/orphan events (unless `--dry-run`).

## Preconditions

1. DynamoDB table and S3 bucket exist and are reachable with current AWS credentials.
2. Backend code with canonical services is deployed.
3. Tenant package data already exists for expected associations.
4. Run first in `--dry-run` mode.

## Dry Run

```bash
python scripts/migrate-chat-s3-docs-to-package-records.py \
  --tenant-id <tenant-id> \
  --dry-run
```

## Execute Migration

```bash
python scripts/migrate-chat-s3-docs-to-package-records.py \
  --tenant-id <tenant-id> \
  --orphan-strategy workdoc
```

Optional controls:

```bash
# process only N keys
python scripts/migrate-chat-s3-docs-to-package-records.py --tenant-id <tenant-id> --limit 100

# skip orphans
python scripts/migrate-chat-s3-docs-to-package-records.py --tenant-id <tenant-id> --orphan-strategy skip
```

## Validation Checklist

1. Query `DOCUMENT#{tenant}` records and confirm migrated versions and canonical `s3_key` format.
2. Spot check package checklist state for required documents.
3. Verify `AUDIT#{tenant}` entries exist for migration actions.
4. Review `WORKDOC#` records for orphaned items needing manual reassignment.

## Rollback Notes

There is no automatic rollback. To reverse a migration batch:

1. Identify created `DOCUMENT#` versions and `WORKDOC#` entries from `AUDIT#` events.
2. Delete affected records manually.
3. Optionally remove canonical S3 objects if business-approved.

## Safety Notes

1. `--dry-run` does not write DynamoDB or S3.
2. Idempotency for package docs is handled by `content_hash` in `document_service`.
3. Script is tenant-scoped; run one tenant at a time.
