---
name: s3-knowledge-base-sync
description: Synchronize and regenerate the EAGLE application knowledge base from the upstream S3 bucket into the app's KB storage, metadata table, compliance matrix checks, and search indexes. Use when the user says an S3 knowledge base bucket was updated, asks to sync the KB, run or combine KB-regenerate, refresh KB metadata, purge orphan metadata, validate KB checklists/templates, migrate rh-eagle-files content, update eagle-knowledge-base/approved files, or rebuild the S3 vector index for the app.
---

# S3 Knowledge Base Sync

Synchronize the upstream RH knowledge base bucket into EAGLE's current application knowledge base, then run the KB regeneration workflow that keeps metadata and matrix-dependent behavior consistent.

## Constants

- Upstream source bucket: `rh-eagle-files`
- Common typo to check: `rh-equal-files` usually returns 404; confirm with the user before using it.
- App document bucket: `eagle-documents-695681773636-dev`
- App KB prefix: `eagle-knowledge-base/approved/`
- Metadata table: `eagle-document-metadata-dev`
- Metadata extraction Lambda: `eagle-metadata-extractor-dev`
- S3 vector bucket: `rh-eagle`
- S3 vector index: `eagle-kb-approved`
- Region: `us-east-1`
- AWS profile normally used by the existing Claude command: `eagle`
- Existing KB-regenerate command reference: `.claude/commands/kb-regenerate.md`

## Existing KB-Regenerate Coverage

The existing `/kb-regenerate` command covers these phases:

1. Orphan purge: scan `eagle-document-metadata-dev`, `head_object` each record's `s3_key`, and delete DynamoDB metadata records whose S3 object is 404. In dry-run mode, report only.
2. Checklist/template validation: verify the built-in checklist and template S3 keys exist under `eagle-knowledge-base/approved/`.
3. Compliance matrix analysis: run `python scripts/kb_matrix_analysis.py` to compare `eagle-plugin/data/matrix.json` against backend `server/app/compliance_matrix.py` and frontend `client/components/contract-matrix/matrix-data.ts`.
4. Metadata regeneration: invoke `eagle-metadata-extractor-dev` for one S3 key with `--regenerate <s3-key>` or every object under `eagle-knowledge-base/approved/` with `--regenerate-all`.
5. Summary report: consolidate orphan count, checklist/template status, matrix drift, and metadata regeneration status.

This skill adds a new pre-phase before that command: sync updated content from `rh-eagle-files` into `s3://eagle-documents-695681773636-dev/eagle-knowledge-base/approved/`.

## Combined Workflow

1. Confirm repository context.
   - Run from the repo root, typically `/Users/hoquemi/Desktop/sm_eagle`.
   - Check `git status --short` and do not touch unrelated user changes.

2. Verify AWS identity and bucket access.
   - Prefer the configured profile used by the existing KB command:
     ```bash
     aws sts get-caller-identity --profile eagle --region us-east-1
     ```
   - If the environment is already exporting credentials, the same commands may work without `--profile eagle`.
   - Run:
     ```bash
     aws s3api head-bucket --bucket rh-eagle-files --profile eagle --region us-east-1
     aws s3api head-bucket --bucket eagle-documents-695681773636-dev --profile eagle --region us-east-1
     ```
   - If the user specifically said `rh-equal-files`, also run:
     ```bash
     aws s3api head-bucket --bucket rh-equal-files --profile eagle --region us-east-1
     ```
     Treat a 404 as evidence the bucket name is wrong, not as an access denial.

3. Inspect current source and destination state.
   - Run:
     ```bash
     aws s3 ls s3://rh-eagle-files/ --recursive --summarize --profile eagle --region us-east-1
     aws s3 ls s3://eagle-documents-695681773636-dev/eagle-knowledge-base/approved/ --recursive --summarize --profile eagle --region us-east-1
     aws dynamodb scan --table-name eagle-document-metadata-dev --select COUNT --profile eagle --region us-east-1
     ```
   - Capture object counts, total sizes, and metadata count for the final report.

4. Dry-run the upstream source-to-app KB sync.
   - First determine the desired mode:
     - Copy-only mode: add/update objects from upstream, leave destination-only objects in place.
     - Mirror mode: make app KB match upstream, including deleting destination-only objects. This is the normal choice when upstream is canonical and files may have been removed or renamed.
   - Copy-only dry-run using the repo script:
     ```bash
     python3 scripts/migrate-knowledge-base.py --dry-run
     ```
     This copies each source key to:
     `s3://eagle-documents-695681773636-dev/eagle-knowledge-base/approved/<source-key>`
   - Mirror-mode dry-run using AWS CLI:
     ```bash
     aws s3 sync \
       s3://rh-eagle-files/ \
       s3://eagle-documents-695681773636-dev/eagle-knowledge-base/approved/ \
       --dryrun \
       --delete \
       --profile eagle \
       --region us-east-1
     ```

5. Sync S3 only after explicit user approval.
   - Copy-only mode:
     ```bash
     python3 scripts/migrate-knowledge-base.py
     ```
   - The script copies/overwrites changed source objects into the app KB prefix. It does not delete destination-only stale objects.
   - Mirror mode:
     ```bash
     aws s3 sync \
       s3://rh-eagle-files/ \
       s3://eagle-documents-695681773636-dev/eagle-knowledge-base/approved/ \
       --delete \
       --profile eagle \
       --region us-east-1
     ```
   - Mirror mode is destructive for destination-only objects. Use it only after reviewing dry-run output with the user.

6. Wait for automatic metadata extraction if S3 notifications are expected to fire.
   - The document bucket has ObjectCreated notifications to `eagle-metadata-extractor-dev` for supported file suffixes.
   - After a real S3 sync, wait 2-3 minutes before judging metadata completeness.
   - Then spot-check at least one newly copied key:
     ```bash
     aws dynamodb get-item \
       --table-name eagle-document-metadata-dev \
       --key '{"document_id":{"S":"<s3-key>"}}' \
       --profile eagle \
       --region us-east-1
     ```

7. Run KB-regenerate dry checks.
   - If Claude command execution is available, run `/kb-regenerate --dry-run`.
   - If working directly from the shell, use the existing command file as the source of truth:
     `.claude/commands/kb-regenerate.md`.
   - At minimum, run:
     ```bash
     python scripts/kb_matrix_analysis.py
     ```
   - For orphan purge and checklist/template validation, follow the Phase 1 and Phase 2 snippets in `.claude/commands/kb-regenerate.md`. Keep `--dry-run` unless the user approved deleting orphan metadata.

8. Refresh DynamoDB metadata after S3 sync.
   - Existing command route:
     ```text
     /kb-regenerate --regenerate-all
     ```
   - Script route:
     ```bash
     python3 scripts/backfill-metadata.py --dry-run --limit 5
     ```
   - Then trigger extraction for all app KB documents:
     ```bash
     python3 scripts/backfill-metadata.py
     ```
   - Lambda invocations are asynchronous. After triggering, verify with:
     ```bash
     aws dynamodb scan --table-name eagle-document-metadata-dev --select COUNT
     ```
   - For a single changed object, prefer the targeted existing flow:
     ```text
     /kb-regenerate --regenerate <s3-key>
     ```
     or invoke the Lambda with the Phase 4 single-document snippet in `.claude/commands/kb-regenerate.md`.
   - If records exist but have empty summaries, run the summary-specific backfill:
     ```bash
     python3 scripts/backfill-summaries.py --dry-run --limit 5
     python3 scripts/backfill-summaries.py --limit 50
     ```
     Increase the limit only after reviewing cost/runtime.

9. Refresh S3 Vectors after metadata is reasonably complete.
   - Dry-run first:
     ```bash
     python3 server/scripts/backfill_s3_vectors.py \
       --bucket eagle-documents-695681773636-dev \
       --prefix eagle-knowledge-base/approved/ \
       --vector-bucket rh-eagle \
       --index eagle-kb-approved \
       --dry-run
     ```
   - Then rebuild/upsert vectors:
     ```bash
     python3 server/scripts/backfill_s3_vectors.py \
       --bucket eagle-documents-695681773636-dev \
       --prefix eagle-knowledge-base/approved/ \
       --vector-bucket rh-eagle \
       --index eagle-kb-approved
     ```
   - The vector script is idempotent for existing vector keys; it upserts chunks.

10. Run final backfill and integrity tasks.
   - Required after a real source sync:
     - Run orphan purge in dry-run mode, then delete orphans only with approval.
     - Run checklist/template validation.
     - Run compliance matrix analysis.
     - Run metadata regeneration for changed or all KB objects.
     - Run S3 vector backfill after metadata is refreshed.
   - Conditional:
     - Run `scripts/backfill-summaries.py` when metadata records have blank or low-quality summaries.
     - Run `scripts/extract_template_metadata.py` when templates changed under `supervisor-core/essential-templates`.
     - Run local/backend KB endpoint smoke checks only when the app is running.

11. Validate the app KB can see the refreshed documents.
   - Query the metadata-backed endpoint if the backend is running:
     ```bash
     curl -sS "http://127.0.0.1:8000/api/knowledge-base/stats"
     curl -sS "http://127.0.0.1:8000/api/knowledge-base?limit=5"
     ```
   - If the local backend is not running, validate directly through S3 and DynamoDB counts.

## Completion Criteria

A KB sync is not complete when S3 copy finishes. Treat it as complete only after:

- Source bucket access and destination bucket access were verified.
- Upstream objects were copied into `eagle-knowledge-base/approved/`, or dry-run output was reviewed and the user declined execution.
- New/changed KB objects have DynamoDB metadata or regeneration was triggered.
- Orphan metadata was checked; approved deletions were applied or explicitly skipped.
- Required checklists/templates were validated.
- Matrix drift analysis was run and issues were reported.
- S3 vector index was dry-run or refreshed after metadata regeneration.
- Final S3 object count, metadata count, and notable failures were reported.

## Useful Scripts

- `scripts/migrate-knowledge-base.py`: copy upstream `rh-eagle-files` into the app KB S3 prefix.
- `scripts/backfill-metadata.py`: invoke the metadata extraction Lambda for existing app KB documents.
- `scripts/backfill-summaries.py`: use Bedrock to fill missing DynamoDB summaries for supported documents.
- `scripts/extract_template_metadata.py`: inspect template metadata from the S3 template prefix.
- `scripts/kb_matrix_analysis.py`: validate matrix/frontend/backend consistency for `/kb-regenerate` Phase 3.
- `server/scripts/backfill_s3_vectors.py`: chunk KB documents, embed with Titan, and upsert to S3 Vectors.

## Sandbox And Approval Handling

- AWS SSO-backed boto3 commands may fail in the sandbox with an OIDC endpoint connection error. If that happens, rerun the same command with escalated permissions.
- Do not request approval for all write commands at once. Run read-only checks and dry-runs first, summarize what will change, then ask for approval before write steps.
- Never use `--delete`, `rm`, S3 delete APIs, or DynamoDB deletes unless the user explicitly asks to remove stale objects or records.
- `/kb-regenerate` Phase 1 can delete orphaned DynamoDB metadata records when not in dry-run mode. Treat that as a write operation requiring explicit approval.
- Metadata regeneration and vector backfill can invoke AWS Lambda, Bedrock, DynamoDB, and S3 Vectors. Call out cost/runtime risk before running full regeneration.

## Final Report

Report:

- Confirmed AWS identity/account.
- Which source bucket was used.
- Source and destination object counts before sync.
- Whether the migration script copied successfully.
- Orphan purge dry-run or delete count.
- Checklist/template validation pass/fail counts.
- Compliance matrix analysis pass/warn/fail summary.
- Metadata backfill trigger count and any failures.
- Vector backfill indexed document/chunk counts.
- Any commands that were skipped because approval was not granted.
