---
allowed-tools: Read, Write, Glob, Grep, Bash
description: "Check AWS resource status, validate connectivity, and report infrastructure health"
argument-hint: [--all | --quick | --resources | --credentials]
---

# Deployment Expert - Maintenance Command

Check AWS resource status, validate connectivity, and report infrastructure health.

## Purpose

Run comprehensive AWS connectivity and resource validation checks to confirm the EAGLE platform infrastructure is healthy. Uses inline boto3 calls (similar to `/check-aws` and `/check-envs` commands).

## Usage

```
/experts:deployment:maintenance --all
/experts:deployment:maintenance --quick
/experts:deployment:maintenance --resources
/experts:deployment:maintenance --credentials
```

## Presets

| Flag | Checks | Description |
|------|--------|-------------|
| `--all` | Everything | Full infrastructure health check |
| `--quick` | STS + S3 head | Fast connectivity smoke test |
| `--resources` | S3, DDB, CW, Bedrock | All AWS resource checks |
| `--credentials` | STS identity only | Credential validation |

## Workflow

### Phase 1: AWS Credentials Check

Validate AWS credentials and identity.

```bash
python -c "
import boto3, json

print('AWS Credentials Check')
print('=' * 55)

try:
    sts = boto3.client('sts', region_name='us-east-1')
    identity = sts.get_caller_identity()
    print(f'  Account:  {identity[\"Account\"]}')
    print(f'  ARN:      {identity[\"Arn\"]}')
    print(f'  Region:   us-east-1')
    print(f'  Status:   OK')
except Exception as e:
    print(f'  Status:   FAIL')
    print(f'  Error:    {e}')
    print()
    print('  Fix: Check ~/.aws/credentials or set AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY')
"
```

### Phase 2: S3 Bucket Check

Verify the `nci-documents` bucket exists and is accessible.

```bash
python -c "
import boto3

print()
print('S3 Bucket Check: nci-documents')
print('=' * 55)

try:
    s3 = boto3.client('s3', region_name='us-east-1')
    s3.head_bucket(Bucket='nci-documents')
    print(f'  Bucket:   nci-documents')
    print(f'  Status:   OK (accessible)')

    # Check for eagle/ prefix
    resp = s3.list_objects_v2(Bucket='nci-documents', Prefix='eagle/', MaxKeys=5)
    count = resp.get('KeyCount', 0)
    print(f'  Objects:  {count} objects under eagle/ prefix (showing up to 5)')
    for obj in resp.get('Contents', [])[:5]:
        print(f'    - {obj[\"Key\"]} ({obj[\"Size\"]} bytes)')

except Exception as e:
    print(f'  Status:   FAIL')
    print(f'  Error:    {e}')
    print()
    print('  Fix: Verify bucket exists in us-east-1')
    print('       aws s3 ls s3://nci-documents/ 2>&1 | head -5')
"
```

### Phase 3: DynamoDB Table Check

Verify the `eagle` table exists, is active, and has items.

```bash
python -c "
import boto3

print()
print('DynamoDB Table Check: eagle')
print('=' * 55)

try:
    ddb = boto3.client('dynamodb', region_name='us-east-1')
    resp = ddb.describe_table(TableName='eagle')
    table = resp['Table']
    print(f'  Table:    eagle')
    print(f'  Status:   {table[\"TableStatus\"]}')
    print(f'  Items:    {table.get(\"ItemCount\", \"unknown\")}')
    print(f'  Size:     {table.get(\"TableSizeBytes\", 0)} bytes')

    # Check key schema
    for key in table.get('KeySchema', []):
        print(f'  Key:      {key[\"AttributeName\"]} ({key[\"KeyType\"]})')

    # Check billing
    billing = table.get('BillingModeSummary', {}).get('BillingMode', 'PROVISIONED')
    print(f'  Billing:  {billing}')

except Exception as e:
    print(f'  Status:   FAIL')
    print(f'  Error:    {e}')
    print()
    print('  Fix: Verify table exists in us-east-1')
    print('       aws dynamodb describe-table --table-name eagle')
"
```

### Phase 4: CloudWatch Log Group Check

Verify `/eagle/test-runs` log group exists and has recent streams.

```bash
python -c "
import boto3
from datetime import datetime

print()
print('CloudWatch Log Group Check: /eagle/test-runs')
print('=' * 55)

try:
    logs = boto3.client('logs', region_name='us-east-1')

    # Check log group
    resp = logs.describe_log_groups(logGroupNamePrefix='/eagle/test-runs')
    groups = [g for g in resp.get('logGroups', []) if g['logGroupName'] == '/eagle/test-runs']

    if not groups:
        print(f'  Status:   NOT FOUND')
        print(f'  Note:     Log group is auto-created on first eval suite run')
    else:
        group = groups[0]
        stored = group.get('storedBytes', 0)
        retention = group.get('retentionInDays', 'Never expire')
        print(f'  Group:    /eagle/test-runs')
        print(f'  Status:   OK')
        print(f'  Stored:   {stored} bytes')
        print(f'  Retention: {retention}')

        # Check recent streams
        streams_resp = logs.describe_log_streams(
            logGroupName='/eagle/test-runs',
            orderBy='LastEventTime',
            descending=True,
            limit=3
        )
        streams = streams_resp.get('logStreams', [])
        print(f'  Streams:  {len(streams)} most recent:')
        for s in streams[:3]:
            ts = s.get('lastEventTimestamp', 0)
            if ts:
                dt = datetime.fromtimestamp(ts / 1000).strftime('%Y-%m-%d %H:%M:%S')
            else:
                dt = 'no events'
            print(f'    - {s[\"logStreamName\"]} (last event: {dt})')

except Exception as e:
    print(f'  Status:   FAIL')
    print(f'  Error:    {e}')
    print()
    print('  Fix: Run eval suite to auto-create log group')
    print('       python server/tests/test_eagle_sdk_eval.py --model haiku --tests 16')
"
```

### Phase 5: Bedrock Model Access Check

Verify Anthropic models are available via Bedrock.

```bash
python -c "
import boto3

print()
print('Bedrock Model Access Check: Anthropic')
print('=' * 55)

try:
    bedrock = boto3.client('bedrock', region_name='us-east-1')
    resp = bedrock.list_foundation_models(byProvider='Anthropic')
    models = resp.get('modelSummaries', [])
    haiku_models = [m for m in models if 'haiku' in m['modelId'].lower()]
    sonnet_models = [m for m in models if 'sonnet' in m['modelId'].lower()]
    opus_models = [m for m in models if 'opus' in m['modelId'].lower()]

    print(f'  Provider: Anthropic')
    print(f'  Status:   OK ({len(models)} models total)')
    print(f'  Haiku:    {len(haiku_models)} models')
    for m in haiku_models[:3]:
        print(f'    - {m[\"modelId\"]}')
    print(f'  Sonnet:   {len(sonnet_models)} models')
    print(f'  Opus:     {len(opus_models)} models')

except Exception as e:
    print(f'  Status:   FAIL')
    print(f'  Error:    {e}')
    print()
    print('  Fix: Enable Anthropic model access in AWS Console')
    print('       Bedrock > Model Access > Request access to Anthropic models')
"
```

### Phase 6: Infrastructure Files Check

Check if CDK, Docker, or CI/CD files exist in the project.

```bash
python -c "
import os

print()
print('Infrastructure Files Check')
print('=' * 55)

checks = [
    ('CDK project',       'cdk/cdk.json'),
    ('CDK stacks',        'cdk/lib/'),
    ('Dockerfile',        'Dockerfile'),
    ('Docker Compose',    'docker-compose.yml'),
    ('GitHub Actions',    '.github/workflows/'),
    ('Next.js config',    'client/next.config.ts'),
    ('Next.js package',   'client/package.json'),
    ('.env file',         '.env'),
    ('.env.local',        'client/.env.local'),
]

for label, path in checks:
    exists = os.path.exists(path)
    status = 'EXISTS' if exists else 'MISSING'
    print(f'  {label:25s} {status:8s} {path}')

print()
print('  Note: MISSING items for CDK/Docker/CI are expected')
print('        (project uses manual provisioning currently)')
"
```

### Phase 7: Summary Report

Compile all results into a status report.

## Report Format

```markdown
## Deployment Maintenance Report

**Date**: {timestamp}
**Account**: {account_id}
**Region**: us-east-1

### Resource Status

| Resource | Status | Details |
|----------|--------|---------|
| AWS Credentials | OK/FAIL | Account: {id} |
| S3 (nci-documents) | OK/FAIL | {object count} objects |
| DynamoDB (eagle) | OK/FAIL | {status}, {item count} items |
| CloudWatch (/eagle/test-runs) | OK/FAIL/MISSING | {stream count} streams |
| Bedrock (Anthropic) | OK/FAIL | {model count} models |

### Infrastructure Files

| Component | Status |
|-----------|--------|
| CDK | Not configured |
| Docker | Not configured |
| GitHub Actions | Not configured |
| Next.js | Configured (local dev) |

### Summary

- {N}/{total} AWS services healthy
- Infrastructure provisioning: Manual
- Recommended next step: {suggestion}

### Issues Found

{List any FAIL or MISSING items with suggested fixes}
```

## Quick Check

For fast connectivity validation (credentials + S3 only):

```bash
python -c "
import boto3
print('Quick Check...')
try:
    sts = boto3.client('sts', region_name='us-east-1')
    identity = sts.get_caller_identity()
    print(f'  AWS: OK (Account: {identity[\"Account\"]})')
except Exception as e:
    print(f'  AWS: FAIL ({e})')
try:
    s3 = boto3.client('s3', region_name='us-east-1')
    s3.head_bucket(Bucket='nci-documents')
    print(f'  S3:  OK (nci-documents accessible)')
except Exception as e:
    print(f'  S3:  FAIL ({e})')
print('Done.')
"
```

## Troubleshooting

### All Checks Fail

```bash
# Verify credentials file exists
ls ~/.aws/credentials 2>/dev/null && echo "File exists" || echo "No credentials file"

# Check environment variables
python -c "import os; print('AWS_ACCESS_KEY_ID:', 'SET' if os.environ.get('AWS_ACCESS_KEY_ID') else 'NOT SET')"

# Try explicit profile
aws sts get-caller-identity --profile default
```

### S3 Only Fails

```bash
# Check if bucket exists (may be in different account)
aws s3api head-bucket --bucket nci-documents 2>&1

# Check bucket location
aws s3api get-bucket-location --bucket nci-documents
```

### DynamoDB Only Fails

```bash
# List tables in region
aws dynamodb list-tables --region us-east-1

# Check table exists
aws dynamodb describe-table --table-name eagle --region us-east-1 2>&1 | head -10
```

### Bedrock Only Fails

```bash
# Check if Bedrock is available in region
aws bedrock list-foundation-models --region us-east-1 --query 'modelSummaries[?contains(modelId, `anthropic`)].modelId' 2>&1 | head -10
```
