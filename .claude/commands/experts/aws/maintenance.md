---
allowed-tools: Read, Write, Glob, Grep, Bash
description: "Check AWS resource status, validate connectivity, and report infrastructure health"
argument-hint: [--all | --quick | --resources | --credentials]
---

# AWS Expert - Maintenance Command

Check AWS resource status, validate connectivity, and report infrastructure health.

## Usage

```
/experts:aws:maintenance --all
/experts:aws:maintenance --quick
/experts:aws:maintenance --resources
/experts:aws:maintenance --credentials
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

```bash
python -c "
import boto3
print('AWS Credentials Check')
print('=' * 55)
try:
    sts = boto3.client('sts', region_name='us-east-1')
    identity = sts.get_caller_identity()
    print(f'  Account:  {identity[\"Account\"]}')
    print(f'  ARN:      {identity[\"Arn\"]}')
    print(f'  Status:   OK')
except Exception as e:
    print(f'  Status:   FAIL')
    print(f'  Error:    {e}')
"
```

### Phase 2: S3 Bucket Check

```bash
python -c "
import boto3
print()
print('S3 Bucket Check')
print('=' * 55)
for bucket in ['nci-documents', 'eagle-eval-artifacts']:
    try:
        s3 = boto3.client('s3', region_name='us-east-1')
        s3.head_bucket(Bucket=bucket)
        print(f'  {bucket:30s} OK')
    except Exception as e:
        print(f'  {bucket:30s} FAIL ({str(e)[:40]})')
"
```

### Phase 3: DynamoDB Table Check

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
    print(f'  Status:   {table[\"TableStatus\"]}')
    print(f'  Items:    {table.get(\"ItemCount\", \"unknown\")}')
    for key in table.get('KeySchema', []):
        print(f'  Key:      {key[\"AttributeName\"]} ({key[\"KeyType\"]})')
except Exception as e:
    print(f'  Status:   FAIL ({e})')
"
```

### Phase 4: CloudWatch Check

```bash
python -c "
import boto3
from datetime import datetime
print()
print('CloudWatch Check')
print('=' * 55)
try:
    logs = boto3.client('logs', region_name='us-east-1')
    resp = logs.describe_log_groups(logGroupNamePrefix='/eagle/test-runs')
    groups = [g for g in resp.get('logGroups', []) if g['logGroupName'] == '/eagle/test-runs']
    if groups:
        print(f'  /eagle/test-runs: OK ({groups[0].get(\"storedBytes\", 0)} bytes)')
        streams = logs.describe_log_streams(logGroupName='/eagle/test-runs', orderBy='LastEventTime', descending=True, limit=3)
        for s in streams.get('logStreams', [])[:3]:
            ts = s.get('lastEventTimestamp', 0)
            dt = datetime.fromtimestamp(ts / 1000).strftime('%Y-%m-%d %H:%M') if ts else 'no events'
            print(f'    Stream: {s[\"logStreamName\"]} ({dt})')
    else:
        print(f'  /eagle/test-runs: NOT FOUND')
except Exception as e:
    print(f'  Status:   FAIL ({e})')
"
```

### Phase 5: Bedrock Check

```bash
python -c "
import boto3
print()
print('Bedrock Model Access Check')
print('=' * 55)
try:
    bedrock = boto3.client('bedrock', region_name='us-east-1')
    resp = bedrock.list_foundation_models(byProvider='Anthropic')
    models = resp.get('modelSummaries', [])
    print(f'  Anthropic models: {len(models)} available')
except Exception as e:
    print(f'  Status:   FAIL ({e})')
"
```

### Phase 6: CDK Stack Check

```bash
python -c "
import os
print()
print('Infrastructure Files Check')
print('=' * 55)
checks = [
    ('CDK eval stack',     'infra/eval/cdk.json'),
    ('CDK ref stack',      'infra/cdk/cdk.json'),
    ('Dockerfile',         'Dockerfile'),
    ('GitHub Actions',     '.github/workflows/deploy.yml'),
    ('Claude Actions',     '.github/workflows/claude-merge-analysis.yml'),
]
for label, path in checks:
    exists = os.path.exists(path)
    print(f'  {label:25s} {\"EXISTS\" if exists else \"MISSING\":8s} {path}')
"
```

## Quick Check

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
    print(f'  S3:  OK (nci-documents)')
except Exception as e:
    print(f'  S3:  FAIL ({e})')
print('Done.')
"
```
