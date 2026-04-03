---
description: "Regenerate KB index — purge orphaned metadata, validate checklists, deep compliance matrix analysis"
allowed-tools: Bash, Read, Grep, Glob
argument-hint: [--dry-run | --regenerate <s3-key> | --regenerate-all]
---

# /kb-regenerate

Maintain KB integrity and compliance matrix consistency. Runs up to 5 phases depending on flags.

## Arguments

Parse `$ARGUMENTS` for:
- `--dry-run` — scan and report only, no deletes
- `--regenerate <s3-key-or-prefix>` — invoke metadata extraction Lambda for a specific document
- `--regenerate-all` — invoke Lambda for all `eagle-knowledge-base/approved/` documents
- No flags — full run: purge orphans + validate checklists + matrix analysis

## Constants

```
METADATA_TABLE = eagle-document-metadata-dev
DOCUMENT_BUCKET = eagle-documents-695681773636-dev
LAMBDA_NAME = eagle-metadata-extractor-dev
KB_PREFIX = eagle-knowledge-base/approved/
AWS_PROFILE = eagle
AWS_REGION = us-east-1
```

**IMPORTANT**: Prefix ALL `aws` CLI commands with `MSYS_NO_PATHCONV=1` and append `--profile eagle --region us-east-1`. For boto3, use `boto3.Session(profile_name='eagle', region_name='us-east-1')`.

---

## Phase 1 — Orphan Purge

Scan every entry in the metadata table. For each, `head_object` the S3 key. If the object is missing, the entry is an orphan.

```bash
python -c "
import boto3, sys, json

session = boto3.Session(profile_name='eagle', region_name='us-east-1')
ddb = session.client('dynamodb')
s3 = session.client('s3')

TABLE = 'eagle-document-metadata-dev'
BUCKET = 'eagle-documents-695681773636-dev'
DRY_RUN = '--dry-run' in sys.argv

# 1. Full scan
print('Scanning metadata table...')
items = []
params = {'TableName': TABLE, 'Select': 'ALL_ATTRIBUTES'}
while True:
    resp = ddb.scan(**params)
    items.extend(resp.get('Items', []))
    if 'LastEvaluatedKey' not in resp:
        break
    params['ExclusiveStartKey'] = resp['LastEvaluatedKey']

print(f'Total metadata entries: {len(items)}')

# 2. Check each S3 key
orphans = []
valid = 0
no_key = 0
for item in items:
    doc_id_attr = item.get('document_id', {})
    doc_id = doc_id_attr.get('S', '')
    s3_key = item.get('s3_key', {}).get('S', '') or doc_id
    if not s3_key:
        no_key += 1
        continue
    try:
        s3.head_object(Bucket=BUCKET, Key=s3_key)
        valid += 1
    except s3.exceptions.ClientError as e:
        if e.response['Error']['Code'] == '404':
            orphans.append({'document_id': doc_id, 's3_key': s3_key})
        else:
            print(f'  WARN: error checking {s3_key}: {e}')
            valid += 1  # don't delete on non-404 errors

print(f'Valid: {valid} | Orphans: {len(orphans)} | No key: {no_key}')

# 3. Delete orphans
if orphans and not DRY_RUN:
    print(f'Deleting {len(orphans)} orphaned entries...')
    deleted = 0
    for i in range(0, len(orphans), 25):
        batch = orphans[i:i+25]
        requests = [{'DeleteRequest': {'Key': {'document_id': {'S': o['document_id']}}}} for o in batch]
        ddb.batch_write_item(RequestItems={TABLE: requests})
        deleted += len(batch)
        print(f'  Deleted batch: {deleted}/{len(orphans)}')
    print(f'Purged {deleted} orphaned metadata entries.')
elif orphans:
    print(f'[DRY RUN] Would delete {len(orphans)} orphans:')
    for o in orphans[:10]:
        print(f'  {o[\"document_id\"]} -> {o[\"s3_key\"]}')
    if len(orphans) > 10:
        print(f'  ... and {len(orphans) - 10} more')
else:
    print('No orphans found.')

# Output JSON summary for later
print('---PHASE1_JSON---')
print(json.dumps({'total': len(items), 'valid': valid, 'orphans': len(orphans), 'no_key': no_key, 'dry_run': DRY_RUN}))
" $ARGUMENTS
```

---

## Phase 2 — Checklist Validation

Validate that all 9 BUILTIN_KB_ENTRIES checklists exist in S3.

```bash
python -c "
import boto3, json

session = boto3.Session(profile_name='eagle', region_name='us-east-1')
s3 = session.client('s3')
BUCKET = 'eagle-documents-695681773636-dev'

CHECKLISTS = [
    {'id': 'checklist-acquisition-package', 'title': 'Acquisition Package Checklist', 's3_key': 'eagle-knowledge-base/approved/supervisor-core/checklists/HHS_PMR_Common_Requirements.txt'},
    {'id': 'checklist-frc', 'title': 'NIH File Reviewers Checklist (FRC)', 's3_key': 'eagle-knowledge-base/approved/supervisor-core/checklists/File_Reviewers_Checklist_FRC.txt'},
    {'id': 'checklist-nih-acq-files', 'title': 'NIH Acquisition File Checklists (OAG-FY25-01)', 's3_key': 'eagle-knowledge-base/approved/supervisor-core/checklists/OAG_FY25_01_NIH_Acquisition_File_Checklists_MERGED_CORRECTED.txt'},
    {'id': 'checklist-pmr-common', 'title': 'HHS PMR Common Requirements', 's3_key': 'eagle-knowledge-base/approved/supervisor-core/checklists/HHS_PMR_Common_Requirements.txt'},
    {'id': 'checklist-pmr-sap', 'title': 'HHS PMR SAP Checklist', 's3_key': 'eagle-knowledge-base/approved/compliance-strategist/PMR-checklists/HHS_PMR_SAP_Checklist.txt'},
    {'id': 'checklist-pmr-fss', 'title': 'HHS PMR FSS Checklist', 's3_key': 'eagle-knowledge-base/approved/compliance-strategist/PMR-checklists/HHS_PMR_FSS_Checklist.txt'},
    {'id': 'checklist-pmr-bpa', 'title': 'HHS PMR BPA Checklist', 's3_key': 'eagle-knowledge-base/approved/compliance-strategist/PMR-checklists/HHS_PMR_BPA_Checklist.txt'},
    {'id': 'checklist-pmr-idiq', 'title': 'HHS PMR IDIQ Checklist', 's3_key': 'eagle-knowledge-base/approved/compliance-strategist/PMR-checklists/HHS_PMR_IDIQ_Checklist.txt'},
    {'id': 'checklist-pmr-thresholds', 'title': 'HHS PMR Threshold Matrix', 's3_key': 'eagle-knowledge-base/approved/compliance-strategist/PMR-checklists/HHS_PMR_Threshold_Matrix.txt'},
]

TEMPLATES = [
    {'id': 'tmpl-sow', 'title': 'SOW Template', 's3_key': 'eagle-knowledge-base/approved/supervisor-core/essential-templates/statement-of-work-template-eagle-v2.docx'},
    {'id': 'tmpl-igce', 'title': 'IGCE Template', 's3_key': 'eagle-knowledge-base/approved/supervisor-core/essential-templates/01.D_IGCE_for_Commercial_Organizations.xlsx'},
    {'id': 'tmpl-market-research', 'title': 'Market Research Template', 's3_key': 'eagle-knowledge-base/approved/supervisor-core/essential-templates/HHS_Streamlined_Market_Research_Template_FY26.docx'},
    {'id': 'tmpl-justification', 'title': 'J&A Template (>350K)', 's3_key': 'eagle-knowledge-base/approved/supervisor-core/essential-templates/Justification_and_Approval_Over_350K_Template.docx'},
    {'id': 'tmpl-acquisition-plan', 'title': 'Acquisition Plan Template', 's3_key': 'eagle-knowledge-base/approved/supervisor-core/essential-templates/HHS Streamlined Acquisition Plan Template.docx'},
    {'id': 'tmpl-cor-certification', 'title': 'COR Appointment Memo', 's3_key': 'eagle-knowledge-base/approved/supervisor-core/essential-templates/NIH COR Appointment Memorandum.docx'},
    {'id': 'tmpl-son-products', 'title': 'SON Products', 's3_key': 'eagle-knowledge-base/approved/supervisor-core/essential-templates/3.a. SON - Products (including Equipment and Supplies).docx'},
    {'id': 'tmpl-son-services', 'title': 'SON Services', 's3_key': 'eagle-knowledge-base/approved/supervisor-core/essential-templates/3.b. SON - Services based on Catalog Pricing.docx'},
    {'id': 'tmpl-buy-american', 'title': 'Buy American Form', 's3_key': 'eagle-knowledge-base/approved/supervisor-core/essential-templates/DF_Buy_American_Non_Availability_Template.docx'},
    {'id': 'tmpl-subk-plan', 'title': 'SubK Plan Template', 's3_key': 'eagle-knowledge-base/approved/supervisor-core/essential-templates/HHS SubK Plan Template - updated March 2022.doc'},
    {'id': 'tmpl-j-and-a-under-sat', 'title': 'J&A Template (<350K)', 's3_key': 'eagle-knowledge-base/approved/supervisor-core/essential-templates/Justification_and_Approval_Under_350K_Template.docx'},
]

results = {'checklists': [], 'templates': []}

print('=== Checklist S3 Validation ===')
for cl in CHECKLISTS:
    try:
        resp = s3.head_object(Bucket=BUCKET, Key=cl['s3_key'])
        size = resp['ContentLength']
        status = f'OK ({size:,} bytes)'
        results['checklists'].append({'id': cl['id'], 'status': 'OK', 'size': size})
    except Exception as e:
        code = getattr(e, 'response', {}).get('Error', {}).get('Code', str(e))
        status = f'MISSING ({code})'
        results['checklists'].append({'id': cl['id'], 'status': 'MISSING'})
    print(f'  {cl[\"id\"]:<35} {status}')

print()
print('=== Template S3 Validation ===')
for tmpl in TEMPLATES:
    try:
        resp = s3.head_object(Bucket=BUCKET, Key=tmpl['s3_key'])
        size = resp['ContentLength']
        status = f'OK ({size:,} bytes)'
        results['templates'].append({'id': tmpl['id'], 'status': 'OK', 'size': size})
    except Exception as e:
        code = getattr(e, 'response', {}).get('Error', {}).get('Code', str(e))
        status = f'MISSING ({code})'
        results['templates'].append({'id': tmpl['id'], 'status': 'MISSING'})
    print(f'  {tmpl[\"id\"]:<35} {status}')

cl_ok = sum(1 for r in results['checklists'] if r['status'] == 'OK')
cl_fail = len(results['checklists']) - cl_ok
tmpl_ok = sum(1 for r in results['templates'] if r['status'] == 'OK')
tmpl_fail = len(results['templates']) - tmpl_ok

print()
print(f'Checklists: {cl_ok}/{len(results[\"checklists\"])} OK' + (f' ({cl_fail} MISSING)' if cl_fail else ''))
print(f'Templates:  {tmpl_ok}/{len(results[\"templates\"])} OK' + (f' ({tmpl_fail} MISSING)' if tmpl_fail else ''))

print('---PHASE2_JSON---')
print(json.dumps({'checklists_ok': cl_ok, 'checklists_fail': cl_fail, 'templates_ok': tmpl_ok, 'templates_fail': tmpl_fail}))
"
```

---

## Phase 3 — Compliance Matrix Deep Analysis

Cross-reference `matrix.json` (source of truth) against backend `compliance_matrix.py` and frontend `matrix-data.ts`.

Run the analysis script from the repo root:

```bash
python scripts/kb_matrix_analysis.py
```

This script validates 3 layers:
- **Layer A** — `matrix.json` internal consistency (ascending thresholds, valid triggers, doc_rules refs, approval chains)
- **Layer B** — Backend `compliance_matrix.py` sync (all `_threshold()` calls resolve, METHODS/TYPES match)
- **Layer C** — Frontend `matrix-data.ts` sync (METHODS, TYPES, THRESHOLDS match matrix.json)

Reports issues (must fix) and warnings (review) with a PASS/WARN/FAIL verdict.

### Key files checked
| File | What |
|---|---|
| `eagle-plugin/data/matrix.json` | Source of truth — thresholds, doc_rules, approval_chains |
| `server/app/compliance_matrix.py:43-141` | METHODS, TYPES, THRESHOLD_TIERS, 12 derived constants |
| `client/components/contract-matrix/matrix-data.ts:26-68` | Frontend METHODS, TYPES, THRESHOLDS (Ctrl+M modal) |

---

## Phase 4 — Metadata Regeneration

**Only run when `--regenerate` or `--regenerate-all` is in `$ARGUMENTS`.**

Skip this phase entirely if neither flag is present.

### Single document: `--regenerate <s3-key>`

```bash
python -c "
import boto3, json, sys

session = boto3.Session(profile_name='eagle', region_name='us-east-1')
lambda_client = session.client('lambda')
s3 = session.client('s3')

BUCKET = 'eagle-documents-695681773636-dev'
LAMBDA_NAME = 'eagle-metadata-extractor-dev'

# Parse the key from arguments — it follows --regenerate
args = sys.argv[1:]
key = None
for i, arg in enumerate(args):
    if arg == '--regenerate' and i + 1 < len(args):
        key = args[i + 1]
        break

if not key:
    print('ERROR: --regenerate requires an S3 key argument')
    sys.exit(1)

# Verify object exists
try:
    resp = s3.head_object(Bucket=BUCKET, Key=key)
    size = resp['ContentLength']
    print(f'Found: {key} ({size:,} bytes)')
except Exception as e:
    print(f'ERROR: Object not found: {key}')
    print(f'  {e}')
    sys.exit(1)

# Invoke Lambda with synthetic S3 event
event = {'Records': [{'s3': {'bucket': {'name': BUCKET}, 'object': {'key': key, 'size': size}}}]}
response = lambda_client.invoke(
    FunctionName=LAMBDA_NAME,
    InvocationType='Event',
    Payload=json.dumps(event),
)
status = response.get('StatusCode', 0)
if status == 202:
    print(f'Lambda invoked (async). Check CloudWatch for results.')
    print(f'  Verify: aws dynamodb get-item --table-name eagle-document-metadata-dev --key \'{{\"document_id\":{{\"S\":\"{key}\"}}}}\' --profile eagle --region us-east-1')
else:
    print(f'WARNING: Unexpected status {status}')
" $ARGUMENTS
```

### All documents: `--regenerate-all`

```bash
python -c "
import boto3, json, time, sys

session = boto3.Session(profile_name='eagle', region_name='us-east-1')
s3 = session.client('s3')
lambda_client = session.client('lambda')

BUCKET = 'eagle-documents-695681773636-dev'
PREFIX = 'eagle-knowledge-base/approved/'
LAMBDA_NAME = 'eagle-metadata-extractor-dev'
BATCH_SIZE = 5
BATCH_DELAY = 2

DRY_RUN = '--dry-run' in sys.argv

# List all objects
print(f'Scanning s3://{BUCKET}/{PREFIX} ...')
paginator = s3.get_paginator('list_objects_v2')
documents = []
for page in paginator.paginate(Bucket=BUCKET, Prefix=PREFIX):
    for obj in page.get('Contents', []):
        key = obj['Key']
        if not key.endswith('/'):
            documents.append({'key': key, 'size': obj['Size']})

print(f'Found {len(documents)} documents')

if not documents:
    sys.exit(0)

triggered = 0
failed = 0

for i, doc in enumerate(documents, 1):
    key = doc['key']
    size = doc['size']

    if DRY_RUN:
        print(f'  [{i}/{len(documents)}] [DRY RUN] {key}')
        triggered += 1
        continue

    event = {'Records': [{'s3': {'bucket': {'name': BUCKET}, 'object': {'key': key, 'size': size}}}]}
    try:
        resp = lambda_client.invoke(FunctionName=LAMBDA_NAME, InvocationType='Event', Payload=json.dumps(event))
        if resp.get('StatusCode') == 202:
            print(f'  [{i}/{len(documents)}] Triggered: {key}')
            triggered += 1
        else:
            print(f'  [{i}/{len(documents)}] WARN status {resp.get(\"StatusCode\")}: {key}')
            failed += 1
    except Exception as e:
        print(f'  [{i}/{len(documents)}] ERROR: {key} - {e}')
        failed += 1

    if i % BATCH_SIZE == 0 and i < len(documents):
        time.sleep(BATCH_DELAY)

print()
print(f'Total: {len(documents)} | Triggered: {triggered} | Failed: {failed}')
if DRY_RUN:
    print('[DRY RUN] No Lambdas were actually invoked.')
print()
print('Lambda invocations are async. Verify with:')
print(f'  aws dynamodb scan --table-name eagle-document-metadata-dev --select COUNT --profile eagle --region us-east-1')
" $ARGUMENTS
```

---

## Phase 5 — Summary Report

After all phases complete, print a consolidated report:

```
KB Regenerate Report — $(date +%Y-%m-%d)
+----------------------------+----------+--------+
| Check                      | Result   | Detail |
+----------------------------+----------+--------+
| Phase 1: Orphan Purge      | PASS/FAIL| N purged / M total |
| Phase 2: Checklists        | PASS/FAIL| N/9 OK |
| Phase 2: Templates         | PASS/FAIL| N/11 OK |
| Phase 3A: matrix.json      | PASS/FAIL| Internal consistency |
| Phase 3B: Backend sync     | PASS/FAIL| _threshold() calls |
| Phase 3C: Frontend sync    | PASS/FAIL| N discrepancies |
| Phase 4: Metadata Regen    | SKIP/PASS| N triggered |
+----------------------------+----------+--------+
```

If any phase returned FAIL, list the actionable items at the bottom.
