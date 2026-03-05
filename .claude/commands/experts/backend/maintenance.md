---
allowed-tools: Bash, Read, Grep, Glob
description: "Run backend checks, validate tool dispatch, and report health status"
argument-hint: [--syntax | --dispatch | --tools | --full]
---

# Backend Expert - Maintenance Command

Execute backend health checks and report status.

## Purpose

Validate the EAGLE Agentic Service backend — syntax, imports, tool dispatch integrity, handler registrations, and optionally run AWS tool tests.

## Usage

```
/experts:backend:maintenance --syntax
/experts:backend:maintenance --dispatch
/experts:backend:maintenance --tools
/experts:backend:maintenance --full
```

## Presets

| Flag | Checks | Description | AWS Required |
|------|--------|-------------|-------------|
| `--syntax` | Syntax only | Python compile check | No |
| `--dispatch` | Syntax + dispatch | Verify TOOL_DISPATCH and EAGLE_TOOLS alignment | No |
| `--tools` | Dispatch + tool tests | Run eval tests 16-20 | Yes |
| `--full` | Everything | All checks + tool tests | Yes |

## Workflow

### Phase 1: Syntax Check

Always run first, regardless of preset:

```bash
# Python syntax validation
python -c "import py_compile; py_compile.compile('server/app/agentic_service.py', doraise=True)"
```

If this fails, report the error and stop.

### Phase 2: Import and Dispatch Check (--dispatch, --tools, --full)

```bash
# Verify imports and dispatch table
python -c "
import sys
sys.path.insert(0, 'app')
from agentic_service import (
    TOOL_DISPATCH, TOOLS_NEEDING_SESSION, EAGLE_TOOLS,
    execute_tool, SYSTEM_PROMPT, MODEL
)
print(f'Model: {MODEL}')
print(f'SYSTEM_PROMPT length: {len(SYSTEM_PROMPT)} chars')
print(f'TOOL_DISPATCH entries: {len(TOOL_DISPATCH)}')
print(f'  Tools: {list(TOOL_DISPATCH.keys())}')
print(f'TOOLS_NEEDING_SESSION: {TOOLS_NEEDING_SESSION}')
print(f'EAGLE_TOOLS schemas: {len(EAGLE_TOOLS)}')
print(f'  Tool names: {[t[\"name\"] for t in EAGLE_TOOLS]}')

# Check alignment: every dispatched tool should have a schema
dispatch_names = set(TOOL_DISPATCH.keys())
schema_names = {t['name'] for t in EAGLE_TOOLS}
missing_schema = dispatch_names - schema_names
missing_dispatch = schema_names - dispatch_names
if missing_schema:
    print(f'WARNING: Tools in DISPATCH but not EAGLE_TOOLS: {missing_schema}')
if missing_dispatch:
    print(f'WARNING: Tools in EAGLE_TOOLS but not DISPATCH: {missing_dispatch}')
if not missing_schema and not missing_dispatch:
    print('Dispatch/Schema alignment: OK')
"
```

### Phase 3: Handler Signature Check (--dispatch, --tools, --full)

```bash
# Verify session-scoped tools have correct handler signatures
python -c "
import sys, inspect
sys.path.insert(0, 'app')
from agentic_service import TOOL_DISPATCH, TOOLS_NEEDING_SESSION

for name, handler in TOOL_DISPATCH.items():
    sig = inspect.signature(handler)
    params = list(sig.parameters.keys())
    needs_session = name in TOOLS_NEEDING_SESSION
    has_session = 'session_id' in params
    status = 'OK' if needs_session == has_session else 'MISMATCH'
    print(f'  {name}: params={params}, needs_session={needs_session}, has_session={has_session} -> {status}')
"
```

### Phase 4: AWS Tool Tests (--tools, --full)

```bash
# Check AWS credentials first
python -c "import boto3; ident = boto3.client('sts').get_caller_identity(); print(f'AWS Account: {ident[\"Account\"]}, ARN: {ident[\"Arn\"]}')" 2>&1

# Run eval suite AWS tool tests (16-20)
python server/tests/test_eagle_sdk_eval.py --model haiku --tests 16,17,18,19,20
```

### Phase 5: Analyze and Report

1. Read `trace_logs.json` for test results (if tool tests were run)
2. Compile all check results
3. Report to user

## Report Format

```markdown
## Backend Maintenance Report

**Date**: {timestamp}
**Preset**: {--syntax | --dispatch | --tools | --full}
**Status**: HEALTHY | DEGRADED | FAILED

### Syntax Check

- server/app/agentic_service.py: PASS | FAIL ({error})

### Dispatch Integrity (if checked)

| Metric | Value |
|--------|-------|
| TOOL_DISPATCH entries | {N} |
| EAGLE_TOOLS schemas | {N} |
| Alignment | OK | MISMATCH |
| TOOLS_NEEDING_SESSION | {set} |

### Handler Signatures (if checked)

| Tool | Params | Session Scoped | Status |
|------|--------|---------------|--------|
| s3_document_ops | params, tenant_id, session_id | Yes | OK |
| dynamodb_intake | params, tenant_id | No | OK |
| ... | ... | ... | ... |

### AWS Tool Tests (if run)

| # | Test Name | Status |
|---|-----------|--------|
| 16 | S3 Document Ops | PASS |
| 17 | DynamoDB Intake | PASS |
| 18 | CloudWatch Logs | PASS |
| 19 | Document Generation | PASS |
| 20 | CloudWatch E2E | PASS |

### Issues Found

- {issue description and recommended fix}

### Next Steps

- {recommended actions}
```

## Quick Checks

If you just want to verify the backend is healthy without a full run:

```bash
# Syntax only (fastest)
python -c "import py_compile; py_compile.compile('server/app/agentic_service.py', doraise=True)"

# Import check (no AWS needed)
python -c "import sys; sys.path.insert(0, 'app'); from agentic_service import execute_tool; print('OK')"

# Tool count check
python -c "import sys; sys.path.insert(0, 'app'); from agentic_service import TOOL_DISPATCH; print(f'{len(TOOL_DISPATCH)} tools loaded')"

# Test FAR search (no AWS dependency)
python -c "
import sys, json
sys.path.insert(0, 'app')
from agentic_service import execute_tool
result = execute_tool('search_far', {'query': 'sole source'}, None)
print(json.loads(result).get('matches', [])[:2])
"
```

## Troubleshooting

### Syntax Error
```bash
# Get detailed error
python -c "import py_compile; py_compile.compile('server/app/agentic_service.py', doraise=True)" 2>&1
```

### Import Error
```bash
# Check if app/ directory has __init__.py issues
python -c "import sys; sys.path.insert(0, '.'); from app.agentic_service import execute_tool; print('OK')"
```

### Dispatch/Schema Mismatch
- Tool in TOOL_DISPATCH but not EAGLE_TOOLS: Claude will never call it
- Tool in EAGLE_TOOLS but not TOOL_DISPATCH: execute_tool() returns "Unknown tool" error
- Fix: Add the missing entry to align both sides

### AWS Credential Error
```bash
aws sts get-caller-identity
echo $AWS_REGION
```

### S3 Bucket Not Found
```bash
aws s3 ls s3://nci-documents/ 2>&1 | head -5
```

### DynamoDB Table Not Found
```bash
aws dynamodb describe-table --table-name eagle 2>&1 | head -5
```

### CloudWatch Log Group Missing
```bash
aws logs describe-log-groups --log-group-name-prefix /eagle
# Create if missing:
aws logs create-log-group --log-group-name /eagle/test-runs
```
