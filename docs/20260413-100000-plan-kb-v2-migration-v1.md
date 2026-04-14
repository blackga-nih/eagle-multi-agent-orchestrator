# EAGLE Knowledge Base v2 Migration Plan

**Date**: 2026-04-13  
**Author**: Alvee Hoque  
**Purpose**: Migrate KB from v1 to v2 per Ryan Hash's April 6, 2026 email

---

## Overview

| Item | Count |
|------|-------|
| Files to remove | 14 |
| Files to rename | 2 |
| New agent files | 2 |
| New HHSAR files | 6 |

**Source**: `/Users/hoquemi/Desktop/KB/rh-eagle-2/`  
**Destination**: `s3://eagle-documents-695681773636-dev/eagle-knowledge-base/approved/`

---

## Prerequisites

### 1. Verify AWS CLI Access

```bash
aws sts get-caller-identity --profile eagle --region us-east-1
```

**Expected**: Returns your AWS account ID and ARN.

### 2. Verify Source Folder Exists

```bash
ls -la "/Users/hoquemi/Desktop/KB/rh-eagle-2/"
```

**Expected**: Shows `agents/`, `compliance-strategist/`, `financial-advisor/`, etc.

### 3. Verify S3 Bucket Access

```bash
MSYS_NO_PATHCONV=1 aws s3 ls "s3://eagle-documents-695681773636-dev/eagle-knowledge-base/approved/" --profile eagle --region us-east-1 | head -20
```

**Expected**: Lists current KB folders.

---

## Phase 1: Dry Run (Preview Changes)

Run this first to see what WILL change without actually changing anything:

```bash
MSYS_NO_PATHCONV=1 aws s3 sync \
  "/Users/hoquemi/Desktop/KB/rh-eagle-2/" \
  "s3://eagle-documents-695681773636-dev/eagle-knowledge-base/approved/" \
  --profile eagle --region us-east-1 \
  --exclude ".DS_Store" \
  --exclude "*.DS_Store" \
  --delete \
  --dryrun
```

### Expected Output

You should see approximately:
- **~16 deletes** (14 removed files + 2 old renamed files)
- **~8+ uploads** (2 new agents + 6 HHSAR files + renamed files)

Review the output carefully. If it looks correct, proceed to Phase 2.

---

## Phase 2: Execute S3 Sync

```bash
MSYS_NO_PATHCONV=1 aws s3 sync \
  "/Users/hoquemi/Desktop/KB/rh-eagle-2/" \
  "s3://eagle-documents-695681773636-dev/eagle-knowledge-base/approved/" \
  --profile eagle --region us-east-1 \
  --exclude ".DS_Store" \
  --exclude "*.DS_Store" \
  --delete
```

### Verify Upload Success

```bash
# Check new agent files exist
MSYS_NO_PATHCONV=1 aws s3 ls "s3://eagle-documents-695681773636-dev/eagle-knowledge-base/approved/agents/" --profile eagle --region us-east-1
```

**Expected**: Should show 10 agent files (00-supervisor through 09-FINANCIAL).

```bash
# Check a removed file is gone
MSYS_NO_PATHCONV=1 aws s3 ls "s3://eagle-documents-695681773636-dev/eagle-knowledge-base/approved/compliance-strategist/FAR-guidance/FAR_Part_19_Small_Business_Programs.txt" --profile eagle --region us-east-1
```

**Expected**: No output (file doesn't exist).

```bash
# Check renamed file exists with new name
MSYS_NO_PATHCONV=1 aws s3 ls "s3://eagle-documents-695681773636-dev/eagle-knowledge-base/approved/supervisor-core/core-procedures/EAGLE_Acquisition_Plan_Guide_FAR_7105.txt" --profile eagle --region us-east-1
```

**Expected**: Shows the file with size and date.

---

## Phase 3: Wait for Lambda Processing

The metadata extraction Lambda fires automatically on S3 ObjectCreated events.

**Wait time**: 2-3 minutes

### Monitor Lambda (Optional)

Check CloudWatch logs for processing:

```bash
MSYS_NO_PATHCONV=1 aws logs tail "/eagle/lambda/metadata-extraction-dev" \
  --profile eagle --region us-east-1 \
  --since 5m \
  --follow
```

Press `Ctrl+C` to stop following.

### Verify New Metadata Created

```bash
MSYS_NO_PATHCONV=1 aws dynamodb get-item \
  --table-name eagle-document-metadata-dev \
  --key '{"document_id":{"S":"eagle-knowledge-base/approved/agents/08-COMPLIANCE.txt"}}' \
  --profile eagle --region us-east-1
```

**Expected**: Returns metadata JSON with title, summary, keywords, etc.

---

## Phase 4: Clean Up Orphaned Metadata

The 14 deleted files + 2 renamed files left orphaned records in DynamoDB.

### Option A: Using Claude Code Skill

In Claude Code, run:

```
/kb-regenerate
```

This will:
1. Scan all metadata entries
2. Check each against S3
3. Delete entries where S3 file is missing
4. Validate checklists and templates
5. Print summary report

### Option B: Manual Orphan Purge

If not using Claude Code:

```bash
python -c "
import boto3

session = boto3.Session(profile_name='eagle', region_name='us-east-1')
ddb = session.client('dynamodb')
s3 = session.client('s3')

TABLE = 'eagle-document-metadata-dev'
BUCKET = 'eagle-documents-695681773636-dev'

# 1. Scan all metadata
print('Scanning metadata table...')
items = []
params = {'TableName': TABLE, 'Select': 'ALL_ATTRIBUTES'}
while True:
    resp = ddb.scan(**params)
    items.extend(resp.get('Items', []))
    if 'LastEvaluatedKey' not in resp:
        break
    params['ExclusiveStartKey'] = resp['LastEvaluatedKey']

print(f'Total entries: {len(items)}')

# 2. Find orphans
orphans = []
for item in items:
    doc_id = item.get('document_id', {}).get('S', '')
    s3_key = item.get('s3_key', {}).get('S', '') or doc_id
    if not s3_key:
        continue
    try:
        s3.head_object(Bucket=BUCKET, Key=s3_key)
    except s3.exceptions.ClientError as e:
        if e.response['Error']['Code'] == '404':
            orphans.append(doc_id)

print(f'Found {len(orphans)} orphans')

# 3. Delete orphans
if orphans:
    for doc_id in orphans:
        print(f'  Deleting: {doc_id}')
        ddb.delete_item(TableName=TABLE, Key={'document_id': {'S': doc_id}})
    print(f'Purged {len(orphans)} orphaned entries.')
else:
    print('No orphans found.')
"
```

---

## Phase 5: Final Validation

### 1. Count Total KB Documents

```bash
MSYS_NO_PATHCONV=1 aws s3 ls "s3://eagle-documents-695681773636-dev/eagle-knowledge-base/approved/" \
  --profile eagle --region us-east-1 \
  --recursive | wc -l
```

### 2. Count Metadata Entries

```bash
MSYS_NO_PATHCONV=1 aws dynamodb scan \
  --table-name eagle-document-metadata-dev \
  --select COUNT \
  --profile eagle --region us-east-1
```

### 3. Spot Check Key Files

| File | Check Command |
|------|---------------|
| New agent 08 | `aws dynamodb get-item --table-name eagle-document-metadata-dev --key '{"document_id":{"S":"eagle-knowledge-base/approved/agents/08-COMPLIANCE.txt"}}' --profile eagle --region us-east-1` |
| New agent 09 | `aws dynamodb get-item --table-name eagle-document-metadata-dev --key '{"document_id":{"S":"eagle-knowledge-base/approved/agents/09-FINANCIAL.txt"}}' --profile eagle --region us-east-1` |
| Renamed file | `aws dynamodb get-item --table-name eagle-document-metadata-dev --key '{"document_id":{"S":"eagle-knowledge-base/approved/shared/EAGLE_Clause_Quick_Reference_FAR_52.txt"}}' --profile eagle --region us-east-1` |

---

## Rollback Plan (If Needed)

If something goes wrong, restore from KB v1:

```bash
MSYS_NO_PATHCONV=1 aws s3 sync \
  "/Users/hoquemi/Desktop/KB/rh-eagle-1/" \
  "s3://eagle-documents-695681773636-dev/eagle-knowledge-base/approved/" \
  --profile eagle --region us-east-1 \
  --exclude ".DS_Store" \
  --delete
```

Then run `/kb-regenerate` again to clean up metadata.

---

## Summary Checklist

| # | Step | Command | Status |
|---|------|---------|--------|
| 1 | Verify AWS access | `aws sts get-caller-identity` | ☐ |
| 2 | Dry run sync | `aws s3 sync ... --dryrun` | ☐ |
| 3 | Review dry run output | (manual review) | ☐ |
| 4 | Execute sync | `aws s3 sync ... --delete` | ☐ |
| 5 | Verify new files in S3 | `aws s3 ls ...` | ☐ |
| 6 | Wait for Lambda | 2-3 minutes | ☐ |
| 7 | Verify new metadata | `aws dynamodb get-item ...` | ☐ |
| 8 | Clean up orphans | `/kb-regenerate` | ☐ |
| 9 | Final validation | Count S3 vs DynamoDB | ☐ |

---

## Appendix: Files Changed

### Removed (14 files)

| Path |
|------|
| `compliance-strategist/FAR-guidance/FAR_Part_19_Small_Business_Programs.txt` |
| `compliance-strategist/FAR-guidance/FC_5_Publicizing_Guidance.txt` |
| `compliance-strategist/FAR-guidance/FC_6_Competition_JOFOC_Guidance.txt` |
| `compliance-strategist/FAR-guidance/FC_9_Contractor_Qualifications.txt` |
| `compliance-strategist/FAR-guidance/FC_15_Negotiation_Source_Selection.txt` |
| `compliance-strategist/FAR-guidance/FC_16_Contract_Types_Guidance.txt` |
| `compliance-strategist/FAR-guidance/FC_17_Special_Contracting_Methods.txt` |
| `compliance-strategist/FAR-guidance/FAR_Part_13_Simplified_Acquisition_Procedures.txt` |
| `compliance-strategist/FAR-guidance/FAR_Parts_6_8_10_17_32_Competition_Sources_Options_Financing..txt` |
| `compliance-strategist/FAR-guidance/FAR_Part_17_Options_and_Special_Methods.txt` |
| `financial-advisor/contract-financing/FC_32_Contract_Financing.txt` |
| `supervisor-core/core-procedures/FC_7_Acquisition_Planning_Complete.txt` |
| `supervisor-core/core-procedures/FC_42_Contract_Administration.txt` |
| `market-intelligence/small-business/FC_19_Small_Business_Programs.txt` |

### Renamed (2 files)

| Old Name | New Name |
|----------|----------|
| `supervisor-core/core-procedures/FAR_Part_7_Acquisition_Planning_Guide.txt` | `supervisor-core/core-procedures/EAGLE_Acquisition_Plan_Guide_FAR_7105.txt` |
| `shared/FAR_Part_52_Essential_Clauses_Reference.txt` | `shared/EAGLE_Clause_Quick_Reference_FAR_52.txt` |

### Added (8+ files)

| Path |
|------|
| `agents/08-COMPLIANCE.txt` |
| `agents/09-FINANCIAL.txt` |
| `compliance-strategist/HHSAR-guidance/HHS_OCIO_OIS_2021_03_001_Appendix_D_Summary.txt` |
| `compliance-strategist/HHSAR-guidance/HHSAM_317_Interagency_Acquisitions_Guidance.txt` |
| `compliance-strategist/HHSAR-guidance/HHSAR_CD_2024_01_OAMS_Security_Checklist_Guide.txt` |
| `compliance-strategist/HHSAR-guidance/HHSAR_Class_Deviation_2026-02_Amendment_1.txt` |
| `compliance-strategist/HHSAR-guidance/HHSAR_Class_Deviation_2026-06.txt` |
| `supervisor-core/essential-templates/HHSAR_CD_2024_01_OAMS_Security_Checklist_Template.txt` |

---

## Change Log

| Date | Change | By |
|------|--------|-----|
| 2026-04-13 | Initial plan created | Alvee |
