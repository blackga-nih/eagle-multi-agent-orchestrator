---
allowed-tools: Read, Write, Glob, Grep, Bash
description: "Run eval suite, analyze results, and report status"
argument-hint: [--all | --aws | --sdk | --skills | --tests 1,2,3]
---

# Eval Expert - Maintenance Command

Execute the eval suite and report results.

## Purpose

Run the EAGLE SDK Evaluation Suite (or a subset), analyze pass/fail results, and produce a structured report.

## Usage

```
/experts:eval:maintenance --all
/experts:eval:maintenance --aws
/experts:eval:maintenance --sdk
/experts:eval:maintenance --skills
/experts:eval:maintenance --tests 16,17,18
```

## Presets

| Flag | Tests | Description | LLM Cost |
|------|-------|-------------|----------|
| `--all` | 1-20 | Full suite | ~$0.50 |
| `--aws` | 16-20 | AWS tool integration only | $0 |
| `--sdk` | 1-6 | SDK patterns only | ~$0.30 |
| `--skills` | 7-15 | Skill validation only | ~$0.30 |
| `--tests N,N` | Specific | Custom selection | Varies |

## Workflow

### Phase 1: Pre-Run Check

1. Verify prerequisites:
   ```bash
   # Check Python syntax
   python -c "import py_compile; py_compile.compile('server/tests/test_eagle_sdk_eval.py', doraise=True)"

   # Check AWS credentials
   python -c "import boto3; boto3.client('sts').get_caller_identity()" 2>&1
   ```

2. Determine test selection from arguments

### Phase 2: Execute Tests

Based on the preset:

```bash
# AWS tool tests (free, fast)
python server/tests/test_eagle_sdk_eval.py --model haiku --tests 16,17,18,19,20

# Full suite
python server/tests/test_eagle_sdk_eval.py --model haiku

# Specific tests
python server/tests/test_eagle_sdk_eval.py --model haiku --tests {N,N,N}
```

### Phase 3: Analyze Results

1. Read `trace_logs.json` for structured results
2. Parse pass/fail/skip counts
3. Identify failures and their causes
4. Check CloudWatch emission status

### Phase 4: Report

Write results summary and respond to user.

## Report Format

```markdown
## Eval Maintenance Report

**Date**: {timestamp}
**Tests Run**: {list}
**Status**: ALL PASS | PARTIAL | FAILED

### Results

| # | Test Name | Status | Notes |
|---|-----------|--------|-------|
| 1 | session_creation | PASS | |
| 2 | session_resume | PASS | |
| ... | ... | ... | ... |

### Summary

| Metric | Value |
|--------|-------|
| Total | {N} |
| Passed | {N} |
| Failed | {N} |
| Skipped | {N} |
| Pass Rate | {N}% |

### SDK Patterns (1-6)
{pass/fail breakdown}

### Skill Validation (7-15)
{pass/fail breakdown}

### AWS Tool Integration (16-20)
{pass/fail breakdown}

### CloudWatch Telemetry
- Log group: /eagle/test-runs
- Stream: {run stream name}
- Events emitted: {count}

### Failures (if any)

#### Test {N}: {name}
- **Error**: {error message}
- **Likely cause**: {diagnosis}
- **Fix**: {suggested action}

### Next Steps
- {recommended actions}
```

## Quick Checks

If you just want to verify the suite is healthy without a full run:

```bash
# Syntax only
python -c "import py_compile; py_compile.compile('server/tests/test_eagle_sdk_eval.py', doraise=True)"

# AWS connectivity only (test 16 is fastest)
python server/tests/test_eagle_sdk_eval.py --model haiku --tests 16

# Last run results
python -c "import json; d=json.load(open('trace_logs.json')); print(f'Last run: {d[\"passed\"]}P {d[\"failed\"]}F {d[\"skipped\"]}S')"
```

## Troubleshooting

### All AWS Tests Fail
```bash
# Check AWS credentials
aws sts get-caller-identity
# Check region
echo $AWS_REGION
```

### Import Error on execute_tool
```bash
# Verify app/ is in the path
python -c "import sys; sys.path.insert(0, 'app'); from agentic_service import execute_tool; print('OK')"
```

### CloudWatch Emission Fails
```bash
# Check log group exists
aws logs describe-log-groups --log-group-name-prefix /eagle
# Create if missing
aws logs create-log-group --log-group-name /eagle/test-runs
```

### S3 Bucket Not Found
```bash
aws s3 ls s3://nci-documents/ 2>&1 | head -5
```

### DynamoDB Table Not Found
```bash
aws dynamodb describe-table --table-name eagle 2>&1 | head -5
```
