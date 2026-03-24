---
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Agent
description: "Run ALL test suites (ruff, tsc, pytest, playwright, eval, cdk) in parallel, save each report to a timestamped folder"
argument-hint: [--skip-eval] [--skip-e2e] [--skip-cdk]
model: opus
---

# Test Expert - Run All Suites

> Execute every test suite, capture output, and save organized reports to a timestamped folder.

## Variables

- `SKIP_EVAL`: true if $ARGUMENTS contains "--skip-eval"
- `SKIP_E2E`: true if $ARGUMENTS contains "--skip-e2e"
- `SKIP_CDK`: true if $ARGUMENTS contains "--skip-cdk"

## Instructions

### Phase 0: Create Report Directory

```bash
RUN_ID=$(date +%Y%m%d-%H%M%S)
REPORT_DIR="test-reports/${RUN_ID}"
mkdir -p "${REPORT_DIR}"
```

### Phase 1: Run All Suites (parallel where possible)

Launch these in parallel using the Bash tool:

#### 1. Python Lint (ruff)
```bash
cd server && ruff check app/ 2>&1 | tee "../${REPORT_DIR}/01-ruff-lint.txt"
echo "EXIT_CODE: $?" >> "../${REPORT_DIR}/01-ruff-lint.txt"
```

#### 2. TypeScript Check (tsc)
```bash
cd client && npx tsc --noEmit 2>&1 | tee "../${REPORT_DIR}/02-tsc-typecheck.txt"
echo "EXIT_CODE: $?" >> "../${REPORT_DIR}/02-tsc-typecheck.txt"
```

#### 3. Python Unit Tests (pytest — exclude eval)
```bash
cd server && python -m pytest tests/ -v --ignore=tests/test_eagle_sdk_eval.py 2>&1 | tee "../${REPORT_DIR}/03-pytest-unit.txt"
echo "EXIT_CODE: $?" >> "../${REPORT_DIR}/03-pytest-unit.txt"
```

#### 4. Eval Suite (pytest — eval only) — skip if --skip-eval
```bash
cd server && python -m pytest tests/test_eagle_sdk_eval.py -v 2>&1 | tee "../${REPORT_DIR}/04-pytest-eval.txt"
echo "EXIT_CODE: $?" >> "../${REPORT_DIR}/04-pytest-eval.txt"
```

#### 5. Playwright E2E — skip if --skip-e2e
```bash
cd client && npx playwright test 2>&1 | tee "../${REPORT_DIR}/05-playwright-e2e.txt"
echo "EXIT_CODE: $?" >> "../${REPORT_DIR}/05-playwright-e2e.txt"
```

#### 6. CDK Synth — skip if --skip-cdk
```bash
cd infrastructure/cdk-eagle && npm run build 2>&1 && npx cdk synth --quiet 2>&1 | tee "../../${REPORT_DIR}/06-cdk-synth.txt"
echo "EXIT_CODE: $?" >> "../../${REPORT_DIR}/06-cdk-synth.txt"
```

### Phase 2: Parse Results

For each report file, extract the exit code and pass/fail counts:

```bash
for f in ${REPORT_DIR}/*.txt; do
  name=$(basename "$f" .txt)
  exit_code=$(grep "EXIT_CODE:" "$f" | tail -1 | cut -d: -f2 | tr -d ' ')
  if [ "$exit_code" = "0" ]; then
    status="PASS"
  else
    status="FAIL"
  fi
  echo "${name}|${status}|${exit_code}"
done
```

For pytest files, also extract:
- Total tests, passed, failed, errors, skipped
- Use: `grep -E "passed|failed|error" ${REPORT_DIR}/03-pytest-unit.txt | tail -1`

For ruff/tsc, extract error count:
- ruff: `grep -c "error" ${REPORT_DIR}/01-ruff-lint.txt` or "All checks passed"
- tsc: count lines with "error TS"

### Phase 3: Generate Summary Report

Write `${REPORT_DIR}/SUMMARY.md`:

```markdown
# EAGLE Test Suite Report

**Run ID**: {RUN_ID}
**Date**: {date}
**Branch**: {git branch}
**Commit**: {git rev-parse --short HEAD}

## Results

| # | Suite | Status | Duration | Details |
|---|-------|--------|----------|---------|
| 1 | Ruff (Python lint) | PASS/FAIL | Xs | {error count} |
| 2 | TSC (TypeScript) | PASS/FAIL | Xs | {error count} |
| 3 | Pytest (Unit) | PASS/FAIL | Xs | {passed}/{total} tests |
| 4 | Pytest (Eval) | PASS/FAIL/SKIPPED | Xs | {passed}/{total} tests |
| 5 | Playwright (E2E) | PASS/FAIL/SKIPPED | Xs | {passed}/{total} tests |
| 6 | CDK Synth | PASS/FAIL/SKIPPED | Xs | {stack count} stacks |

## Overall: {PASS if all passed, FAIL if any failed}

## Failures

{For each FAIL suite, include the last 20 lines of output}

## Report Files

| File | Size |
|------|------|
| 01-ruff-lint.txt | {size} |
| 02-tsc-typecheck.txt | {size} |
| ... | ... |
```

### Phase 4: Print Summary

Output the summary table to the console. If any suite failed, highlight which ones and show the first error from each.

## Output Structure

```
test-reports/
└── 20260309-141500/
    ├── SUMMARY.md
    ├── 01-ruff-lint.txt
    ├── 02-tsc-typecheck.txt
    ├── 03-pytest-unit.txt
    ├── 04-pytest-eval.txt        (if not skipped)
    ├── 05-playwright-e2e.txt     (if not skipped)
    └── 06-cdk-synth.txt          (if not skipped)
```

## Notes

- Always kill ghost sockets before starting tests that need servers
- Eval suite requires AWS SSO credentials (`aws sso login --profile eagle`)
- Playwright requires frontend + backend running
- CDK synth requires `npm install` in infrastructure/cdk-eagle/
- If a suite hangs for >5 minutes, kill it and record TIMEOUT
- Run ruff, tsc, and pytest-unit in parallel (they're independent)
- Run eval, playwright, and cdk sequentially if resources are constrained
