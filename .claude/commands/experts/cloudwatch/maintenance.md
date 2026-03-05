---
allowed-tools: Read, Write, Glob, Grep, Bash
description: "Check CloudWatch connectivity, query recent runs, validate telemetry pipeline"
argument-hint: [--connectivity | --recent | --validate | --failures | --history]
---

# CloudWatch Expert - Maintenance Command

Check CloudWatch connectivity, query recent eval runs, and validate the telemetry pipeline.

## Purpose

Perform CloudWatch health checks and telemetry validation:
- Verify AWS credentials and CloudWatch access
- Query recent eval run results from `/eagle/test-runs`
- Validate the emission pipeline end-to-end
- Find failures across recent runs
- Review pass rate history

## Usage

```
/experts:cloudwatch:maintenance --connectivity
/experts:cloudwatch:maintenance --recent
/experts:cloudwatch:maintenance --validate
/experts:cloudwatch:maintenance --failures
/experts:cloudwatch:maintenance --history
```

## Presets

| Flag | Description | AWS Cost |
|------|-------------|----------|
| `--connectivity` | Check AWS credentials and CloudWatch access | Free |
| `--recent` | Query the most recent eval run from CloudWatch | Free |
| `--validate` | Run tests 18,20 and verify emission end-to-end | Free (no LLM) |
| `--failures` | Find all failures in the last 24 hours | Free |
| `--history` | Show pass rates from the last 10 runs | Free |

---

## Workflow

### Preset: --connectivity

Verify AWS credentials and CloudWatch Logs access.

```bash
# Step 1: Check AWS credentials
python -c "import boto3; sts = boto3.client('sts'); print(sts.get_caller_identity())" 2>&1

# Step 2: Check CloudWatch Logs access
python -c "
import boto3
logs = boto3.client('logs', region_name='us-east-1')
resp = logs.describe_log_groups(logGroupNamePrefix='/eagle')
groups = [g['logGroupName'] for g in resp.get('logGroups', [])]
print(f'Log groups found: {groups}')
" 2>&1

# Step 3: Check test-runs log group specifically
python -c "
import boto3
logs = boto3.client('logs', region_name='us-east-1')
resp = logs.describe_log_streams(
    logGroupName='/eagle/test-runs',
    orderBy='LastEventTime',
    descending=True,
    limit=3,
)
streams = [s['logStreamName'] for s in resp.get('logStreams', [])]
print(f'Recent streams: {streams}')
" 2>&1
```

**Report**:
```markdown
## CloudWatch Connectivity Report

| Check | Status | Detail |
|-------|--------|--------|
| AWS Credentials | PASS/FAIL | {identity or error} |
| Log Groups | PASS/FAIL | {groups found or error} |
| /eagle/test-runs | PASS/FAIL | {stream count or error} |
```

---

### Preset: --recent

Query the most recent eval run and display results.

```bash
python -c "
import boto3, json
logs = boto3.client('logs', region_name='us-east-1')

# Find latest stream
resp = logs.describe_log_streams(
    logGroupName='/eagle/test-runs',
    orderBy='LastEventTime',
    descending=True,
    limit=1,
)
if not resp.get('logStreams'):
    print('No streams found in /eagle/test-runs')
    exit()

stream = resp['logStreams'][0]['logStreamName']
print(f'Latest stream: {stream}')

# Read events
resp = logs.get_log_events(
    logGroupName='/eagle/test-runs',
    logStreamName=stream,
    startFromHead=True,
)
for event in resp.get('events', []):
    data = json.loads(event['message'])
    if data['type'] == 'test_result':
        print(f'  Test {data[\"test_id\"]:2d}: {data[\"status\"]:4s}  {data[\"test_name\"]}')
    elif data['type'] == 'run_summary':
        print(f'  Summary: {data[\"passed\"]}P {data[\"failed\"]}F {data[\"skipped\"]}S  ({data[\"pass_rate\"]}%)')
" 2>&1
```

**Report**:
```markdown
## Most Recent Run

**Stream**: {stream_name}
**Timestamp**: {run_timestamp}

| # | Test Name | Status |
|---|-----------|--------|
| 1 | session_creation | PASS |
| ... | ... | ... |

### Summary

| Metric | Value |
|--------|-------|
| Passed | {N} |
| Failed | {N} |
| Skipped | {N} |
| Pass Rate | {N}% |
```

---

### Preset: --validate

Run CloudWatch-related tests and verify the emission pipeline end-to-end.

```bash
# Step 1: Syntax check
python -c "import py_compile; py_compile.compile('server/tests/test_eagle_sdk_eval.py', doraise=True)"

# Step 2: Run CloudWatch tests (test 18 = tool, test 20 = E2E)
python server/tests/test_eagle_sdk_eval.py --model haiku --tests 18,20

# Step 3: Check trace_logs.json for results
python -c "
import json
d = json.load(open('trace_logs.json'))
for key in ['18_cloudwatch_logs_ops', '20_cloudwatch_e2e_verification']:
    status = d.get('results', {}).get(key, {}).get('status', 'missing')
    print(f'  {key}: {status}')
print(f'CloudWatch emission: {\"emitted\" if d.get(\"cloudwatch_emitted\") else \"check stdout\"} ')
" 2>&1

# Step 4: Verify latest stream in CloudWatch
python -c "
import boto3
logs = boto3.client('logs', region_name='us-east-1')
resp = logs.describe_log_streams(
    logGroupName='/eagle/test-runs',
    orderBy='LastEventTime',
    descending=True,
    limit=1,
)
if resp.get('logStreams'):
    stream = resp['logStreams'][0]
    print(f'Latest stream: {stream[\"logStreamName\"]}')
    print(f'Last event: {stream.get(\"lastEventTimestamp\", \"unknown\")}')
else:
    print('No streams found')
" 2>&1
```

**Report**:
```markdown
## Telemetry Validation Report

| Check | Status | Detail |
|-------|--------|--------|
| Syntax | PASS/FAIL | {detail} |
| Test 18 (CW Tool) | PASS/FAIL | {detail} |
| Test 20 (CW E2E) | PASS/FAIL | {detail} |
| Emission | PASS/FAIL | {stream name or error} |
| trace_logs.json | PASS/FAIL | {detail} |
```

---

### Preset: --failures

Find all test failures in CloudWatch from the last 24 hours.

```bash
python -c "
import boto3, json
from datetime import datetime, timezone, timedelta
logs = boto3.client('logs', region_name='us-east-1')

now = datetime.now(timezone.utc)
start = int((now - timedelta(hours=24)).timestamp() * 1000)
end = int(now.timestamp() * 1000)

resp = logs.filter_log_events(
    logGroupName='/eagle/test-runs',
    filterPattern='\"fail\"',
    startTime=start,
    endTime=end,
    limit=100,
)

failures = []
for event in resp.get('events', []):
    data = json.loads(event['message'])
    if data.get('type') == 'test_result' and data.get('status') == 'fail':
        failures.append({
            'stream': event.get('logStreamName', ''),
            'test_id': data['test_id'],
            'test_name': data['test_name'],
        })

if failures:
    print(f'Found {len(failures)} failure(s) in last 24 hours:')
    for f in failures:
        print(f'  Test {f[\"test_id\"]}: {f[\"test_name\"]} (stream: {f[\"stream\"]})')
else:
    print('No failures found in the last 24 hours.')
" 2>&1
```

**Report**:
```markdown
## Failure Report (Last 24 Hours)

**Total failures**: {N}

| Stream | Test ID | Test Name |
|--------|---------|-----------|
| {stream} | {id} | {name} |

### Recommendations
- {suggested actions based on failure patterns}
```

---

### Preset: --history

Show pass rates from the last 10 eval runs.

```bash
python -c "
import boto3, json
logs = boto3.client('logs', region_name='us-east-1')

# Get last 10 streams
resp = logs.describe_log_streams(
    logGroupName='/eagle/test-runs',
    orderBy='LastEventTime',
    descending=True,
    limit=10,
)

print(f'Pass Rate History (last {len(resp.get(\"logStreams\", []))} runs):')
print(f'{\"Stream\":<50s} {\"Pass Rate\":>10s} {\"P\":>4s} {\"F\":>4s} {\"S\":>4s}')
print('-' * 75)

for stream in resp.get('logStreams', []):
    events_resp = logs.get_log_events(
        logGroupName='/eagle/test-runs',
        logStreamName=stream['logStreamName'],
        startFromHead=True,
    )
    for event in events_resp.get('events', []):
        data = json.loads(event['message'])
        if data.get('type') == 'run_summary':
            name = stream['logStreamName']
            if len(name) > 48:
                name = name[:48] + '..'
            print(f'{name:<50s} {data[\"pass_rate\"]:>9.1f}% {data[\"passed\"]:>4d} {data[\"failed\"]:>4d} {data[\"skipped\"]:>4d}')
            break
" 2>&1
```

**Report**:
```markdown
## Pass Rate History

| # | Stream | Pass Rate | Passed | Failed | Skipped |
|---|--------|-----------|--------|--------|---------|
| 1 | {stream} | {rate}% | {P} | {F} | {S} |

### Trend
- {trend analysis: improving, stable, declining}
- {notable patterns}
```

---

## Quick Checks

If you just want fast answers without a full workflow:

```bash
# Is CloudWatch reachable?
python -c "import boto3; boto3.client('logs', region_name='us-east-1').describe_log_groups(logGroupNamePrefix='/eagle'); print('OK')" 2>&1

# How many streams exist?
python -c "
import boto3
logs = boto3.client('logs', region_name='us-east-1')
resp = logs.describe_log_streams(logGroupName='/eagle/test-runs', limit=50)
print(f'Streams: {len(resp.get(\"logStreams\", []))}')
" 2>&1

# Last run pass rate?
python -c "
import json
d = json.load(open('trace_logs.json'))
total = d.get('passed', 0) + d.get('failed', 0) + d.get('skipped', 0)
rate = round(d.get('passed', 0) / max(total, 1) * 100, 1)
print(f'Last local run: {d.get(\"passed\", 0)}P {d.get(\"failed\", 0)}F {d.get(\"skipped\", 0)}S ({rate}%)')
" 2>&1
```

## Troubleshooting

### NoCredentialsError
```bash
# Check AWS config
aws sts get-caller-identity
# If not configured:
aws configure
```

### Log Group Not Found
```bash
# Create the log group
aws logs create-log-group --log-group-name /eagle/test-runs
```

### No Streams Found
This is normal for a fresh setup. Run the eval suite once to create the first stream:
```bash
python server/tests/test_eagle_sdk_eval.py --model haiku --tests 16,17,18,19,20
```

### Emission Says "non-fatal" in Output
Check the specific error printed:
- `NoCredentialsError` -> Configure AWS credentials
- `AccessDenied` -> IAM policy needs `logs:CreateLogGroup`, `logs:CreateLogStream`, `logs:PutLogEvents`
- `EndpointConnectionError` -> Network issue or wrong region
- `InvalidSequenceTokenException` -> Stream was reused (should not happen)

### Test 20 Fails But Run Looks Good
Test 20 validates the **previous** run's data due to eventual consistency. Run the suite again after a few seconds:
```bash
# Wait and re-run
sleep 10
python server/tests/test_eagle_sdk_eval.py --model haiku --tests 20
```
