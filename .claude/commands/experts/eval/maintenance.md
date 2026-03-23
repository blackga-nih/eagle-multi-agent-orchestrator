---
allowed-tools: Read, Write, Glob, Grep, Bash, Agent
description: "Run eval suite, analyze results, and report status"
argument-hint: [--all | --aws | --sdk | --skills | --uc | --matrix | --langfuse | --context | --handoff | --state | --tests 1,2,3]
---

# Eval Expert - Maintenance Command

Execute the eval suite (or a subset), analyze pass/fail results, and produce a structured report.

## Usage

```
/experts:eval:maintenance --all
/experts:eval:maintenance --aws
/experts:eval:maintenance --sdk
/experts:eval:maintenance --skills
/experts:eval:maintenance --uc
/experts:eval:maintenance --matrix
/experts:eval:maintenance --langfuse
/experts:eval:maintenance --context
/experts:eval:maintenance --handoff
/experts:eval:maintenance --state
/experts:eval:maintenance --tests 16,17,18
```

## Presets

| Flag | Tests | Description | LLM Cost |
|------|-------|-------------|----------|
| `--all` | 1-98 | Full 98-test suite | ~$2-5 |
| `--sdk` | 1-8 | SDK patterns (sessions, traces, subagents) | ~$0.30 |
| `--skills` | 9-15 | Skill validation (7 specialists) | ~$0.40 |
| `--aws` | 16-20 | AWS tool integration only | $0 |
| `--uc` | 21-27 | UC workflow queries | ~$0.50 |
| `--arch` | 28-34 | SDK architecture (admin, workspace, CRUD) | ~$0.30 |
| `--matrix` | 35-48 | Compliance matrix + FAR + tool chains | ~$0.80 |
| `--langfuse` | 49-55 | Langfuse traces + CloudWatch events | ~$0.20 |
| `--kb` | 56-60 | KB integration (FAR search, web search) | ~$0.30 |
| `--e2e` | 61-72 | MVP1 UC E2E workflows | ~$1.50 |
| `--docgen` | 73-76 | Document generation (SOW, IGCE, AP, MR) | ~$0.60 |
| `--context` | 77-82 | Context loss detection | ~$0.30 |
| `--handoff` | 83-87 | Cross-agent handoff validation | ~$0.40 |
| `--state` | 88-94 | State persistence | ~$0.30 |
| `--budget` | 95-98 | Context budget checks | ~$0.10 |
| `--tests N,N` | Specific | Custom selection | Varies |

## Workflow

### Phase 1: Pre-Run Check

1. Verify prerequisites:
   ```bash
   # Check Python syntax
   cd server && python -c "import py_compile; py_compile.compile('tests/test_strands_eval.py', doraise=True)"

   # Check AWS credentials
   aws sts get-caller-identity --profile eagle 2>&1
   ```

2. Determine test selection from arguments

### Phase 2: Execute Tests

```bash
cd server

# AWS tool tests (free, fast)
python tests/test_strands_eval.py --model us.anthropic.claude-3-5-haiku-20241022-v1:0 --tests 16,17,18,19,20

# Full suite (98 tests)
python tests/test_strands_eval.py --model us.anthropic.claude-3-5-haiku-20241022-v1:0

# Specific tests
python tests/test_strands_eval.py --model us.anthropic.claude-3-5-haiku-20241022-v1:0 --tests {N,N,N}

# With trace validation and CloudWatch emission
python tests/test_strands_eval.py --model us.anthropic.claude-3-5-haiku-20241022-v1:0 --validate-traces --emit-cloudwatch
```

### Phase 3: Analyze Results

1. Read `data/eval/results/latest.json` for structured results
2. Parse pass/fail/skip counts per category
3. Identify failures and their causes
4. Check CloudWatch emission status
5. If Langfuse is configured, query recent traces

### Phase 4: Report

## Report Format

```markdown
## Eval Maintenance Report

**Date**: {timestamp}
**Model**: {model}
**Tests Run**: {count}
**Status**: ALL PASS | PARTIAL | FAILED

### Results by Category

| Category | Tests | Passed | Failed | Skipped |
|----------|-------|--------|--------|---------|
| SDK Patterns (1-8) | 8 | N | N | N |
| Skill Validation (9-15) | 7 | N | N | N |
| AWS Tools (16-20) | 5 | N | N | N |
| UC Workflows (21-27) | 7 | N | N | N |
| SDK Architecture (28-34) | 7 | N | N | N |
| Compliance Matrix (35-48) | 14 | N | N | N |
| Langfuse + CW (49-55) | 7 | N | N | N |
| KB Integration (56-60) | 5 | N | N | N |
| UC E2E (61-72) | 12 | N | N | N |
| Doc Generation (73-76) | 4 | N | N | N |
| Context Loss (77-82) | 6 | N | N | N |
| Handoff (83-87) | 5 | N | N | N |
| State Persistence (88-94) | 7 | N | N | N |
| Context Budget (95-98) | 4 | N | N | N |
| **Total** | **98** | **N** | **N** | **N** |

### Pass Rate: {N}%

### Failures

#### Test {N}: {name}
- **Error**: {error message}
- **Root Cause**: {ROUTING | PROMPT | TOOL | TRUNCATION | DATA | BUDGET}
- **Fix**: {suggested action}

### CloudWatch Telemetry
- Log group: /eagle/test-runs
- Stream: {run stream name}
- Events emitted: {count}
- Custom metrics published: {count}

### Langfuse Traces (if available)
- Traces found: {N}
- Total tokens: {in} in / {out} out
- Est. cost: ${N.NN}

### Next Steps
- {recommended actions}
- If failures > 5: consider running `/experts:eval:self-improve --diagnose`
```

## Quick Checks

```bash
# Syntax only
cd server && python -c "import py_compile; py_compile.compile('tests/test_strands_eval.py', doraise=True)"

# AWS connectivity only (test 16 is fastest)
cd server && python tests/test_strands_eval.py --model us.anthropic.claude-3-5-haiku-20241022-v1:0 --tests 16

# Last run results
python -c "import json; d=json.load(open('data/eval/results/latest.json')); print(f'Last run: {d[\"passed\"]}P {d[\"failed\"]}F {d[\"skipped\"]}S')"
```

## Troubleshooting

### All AWS Tests Fail
```bash
aws sts get-caller-identity --profile eagle
echo $AWS_REGION
```

### Import Error on sdk_query
```bash
cd server && python -c "import sys; sys.path.insert(0, 'app'); from strands_agentic_service import sdk_query; print('OK')"
```

### CloudWatch Emission Fails
```bash
aws logs describe-log-groups --log-group-name-prefix /eagle --profile eagle
aws logs create-log-group --log-group-name /eagle/test-runs --profile eagle
```

### UnicodeEncodeError on Windows
The eval suite uses ASCII-only output (no arrows, em-dashes, or special chars). If you see encoding errors, check for non-ASCII characters in print statements and replace with ASCII equivalents.
