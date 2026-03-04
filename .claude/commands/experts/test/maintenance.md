---
allowed-tools: Read, Write, Glob, Grep, Bash
description: "Run test suites, analyze results, report coverage status, and identify failures"
argument-hint: [--unit | --perf | --smoke | --all | --e2e | --eval | --file test_name.py]
---

# Test Expert - Maintenance Command

Execute test suites and report results.

## Purpose

Run the EAGLE test suite (or a subset), analyze pass/fail results, identify regressions, and produce a structured report.

## Usage

```
/experts:test:maintenance --unit
/experts:test:maintenance --perf
/experts:test:maintenance --all
/experts:test:maintenance --e2e
/experts:test:maintenance --eval --tests 16,17,18
/experts:test:maintenance --file test_fast_path.py
```

## Presets

| Flag | Scope | Speed | Cost |
|------|-------|-------|------|
| `--unit` | Mocked unit tests only | <10s | $0 |
| `--perf` | `test_perf_simple_message.py` | <10s | $0 |
| `--smoke` | Fast-path, cache, endpoint health | <30s | $0 |
| `--all` | All pytest tests in `server/tests/` | 1-5min | $0-0.50 |
| `--e2e` | Playwright specs in `client/tests/` | 3-10min | $0.10+ |
| `--eval` | Strands eval suite (custom CLI) | 5-15min | ~$0.50 |
| `--file` | Specific test file | Varies | Varies |

## Workflow

### Phase 1: Pre-Run Check

1. Verify prerequisites:
   ```bash
   # Python syntax check
   cd server && ruff check app/ 2>&1 | tail -1

   # Check test file exists
   ls server/tests/test_*.py | wc -l
   ```

2. Determine test selection from arguments

### Phase 2: Execute Tests

Based on the preset:

```bash
# Unit tests (fast, no AWS)
cd server && python -m pytest tests/test_perf_simple_message.py tests/test_chat_endpoints.py -v

# Performance tests
cd server && python -m pytest tests/test_perf_simple_message.py -v

# All pytest tests
cd server && python -m pytest tests/ -v --timeout=120

# Playwright E2E
cd client && npx playwright test --reporter=list

# Eval suite (specific tests)
python server/tests/test_strands_eval.py --model haiku --tests 16,17,18,19,20

# Specific file
cd server && python -m pytest tests/{filename} -v
```

### Phase 3: Analyze Results

1. Parse pass/fail/skip/error counts
2. Identify failures and their causes
3. Check for regressions (compare to known passing tests)
4. Note timing for performance tests

### Phase 4: Report

```markdown
## Test Maintenance Report

**Date**: {timestamp}
**Preset**: {preset}
**Status**: ALL PASS | PARTIAL | FAILED

### Results

| File | Tests | Passed | Failed | Skipped |
|------|-------|--------|--------|---------|
| test_perf_simple_message.py | 10 | 10 | 0 | 0 |
| test_chat_endpoints.py | 15 | 15 | 0 | 0 |
| ... | ... | ... | ... | ... |

### Summary

| Metric | Value |
|--------|-------|
| Total | {N} |
| Passed | {N} |
| Failed | {N} |
| Skipped | {N} |
| Pass Rate | {N}% |
| Duration | {N}s |

### Failures (if any)

#### {test_name}
- **Error**: {error message}
- **File**: {file}:{line}
- **Likely cause**: {diagnosis}
- **Fix**: {suggested action}

### Coverage Gaps Identified

- {gap 1}
- {gap 2}

### Next Steps

- {recommended actions}
```

## Quick Checks

```bash
# Syntax only (fastest)
cd server && ruff check app/ && echo "LINT OK"

# Just performance tests (fast)
cd server && python -m pytest tests/test_perf_simple_message.py -v

# Just cache-related tests
cd server && python -m pytest tests/test_perf_simple_message.py -k "cache" -v

# Just prompt tests
cd server && python -m pytest tests/test_perf_simple_message.py -k "supervisor" -v
```

## Troubleshooting

### Import Errors
```bash
# Check module path
cd server && python -c "from app.main import app; print('OK')"
```

### All Tests Fail with ModuleNotFoundError
```bash
# Ensure you're in server/ directory
cd server && python -m pytest tests/ -v
```

### Stale Bytecache
```bash
cd server && python -c "import shutil, pathlib; [shutil.rmtree(p) for p in pathlib.Path('.').rglob('__pycache__')]"
```

### Port Already Bound (for integration tests)
```bash
netstat -ano | grep ":8000" | grep LISTEN
# Use alternate port for testing
```
