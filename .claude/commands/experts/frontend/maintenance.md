---
allowed-tools: Read, Write, Glob, Grep, Bash
description: "Check frontend builds, validate test result mappings, and verify consistency across frontends"
argument-hint: [--build | --mappings | --all | --html]
---

# Frontend Expert - Maintenance Command

Check frontend builds, validate test result mappings, and verify consistency.

## Purpose

Run build checks, verify mapping consistency between the Next.js app and the legacy HTML dashboard, and produce a structured report.

## Usage

```
/experts:frontend:maintenance --all
/experts:frontend:maintenance --build
/experts:frontend:maintenance --mappings
/experts:frontend:maintenance --html
```

## Presets

| Flag | Action | Description |
|------|--------|-------------|
| `--all` | Build + Mappings + HTML | Full frontend health check |
| `--build` | TypeScript + Next.js build | Check for compile errors |
| `--mappings` | Cross-file mapping check | Verify TEST_NAMES, TEST_DEFS, SKILL_TEST_MAP consistency |
| `--html` | HTML dashboard check | Verify TEST_DEFS, readiness panel, LATEST_RESULTS |

## Workflow

### Phase 1: Pre-Check

1. Verify project structure:
   ```bash
   ls client/package.json
   ls test_results_dashboard.html
   ```

2. Determine check type from arguments

### Phase 2: Build Check (if --build or --all)

1. TypeScript check:
   ```bash
   cd client && npx tsc --noEmit 2>&1
   ```

2. Full build (if TypeScript passes):
   ```bash
   cd client && npm run build 2>&1 | tail -40
   ```

3. Note any errors or warnings

### Phase 3: Mapping Check (if --mappings or --all)

1. Extract TEST_NAMES entries from Next.js:
   ```bash
   grep "^\s*'" client/app/admin/tests/page.tsx | head -30
   ```

2. Extract TEST_DEFS entries from HTML dashboard:
   ```bash
   grep "{ id:" test_results_dashboard.html
   ```

3. Extract SKILL_TEST_MAP entries from eval page:
   ```bash
   grep -A1 "^\s*[a-z]" client/app/admin/eval/page.tsx | grep -E "^\s*(intake|docgen|tech|compliance|supervisor|'[0-9]|s3_|dynamodb|cloudwatch|create_)"
   ```

4. Extract readiness panel entries:
   ```bash
   grep "label:" test_results_dashboard.html
   ```

5. Cross-reference:
   - Every test ID in TEST_DEFS should have a matching TEST_NAMES entry
   - Every readiness entry should map to a valid test ID
   - SKILL_TEST_MAP keys should reference valid test IDs
   - Count mismatches

### Phase 4: HTML Dashboard Check (if --html or --all)

1. Verify TEST_DEFS covers all test IDs (1 through N)
2. Verify LATEST_RESULTS has entries for all test IDs
3. Verify readiness panel has entries for all tests
4. Check that category tags are valid (core, traces, agents, tools, skills, workflow, aws)
5. Verify filter button "All" count matches TEST_DEFS length

### Phase 5: Report

Write results summary and respond to user.

## Report Format

```markdown
## Frontend Maintenance Report

**Date**: {timestamp}
**Checks Run**: {list}
**Status**: ALL PASS | ISSUES FOUND

### Build Status

| Check | Status | Notes |
|-------|--------|-------|
| TypeScript (tsc --noEmit) | PASS/FAIL | {error count} |
| Next.js Build | PASS/FAIL | {details} |

### Mapping Consistency

| Source | Count | Status |
|--------|-------|--------|
| TEST_NAMES (tests/page.tsx) | {N} entries | OK / MISMATCH |
| TEST_DEFS (dashboard.html) | {N} entries | OK / MISMATCH |
| SKILL_TEST_MAP (eval/page.tsx) | {N} keys | OK / MISMATCH |
| Readiness Panel (dashboard.html) | {N} entries | OK / MISMATCH |

### Missing Entries (if any)

| Test ID | Missing From |
|---------|-------------|
| {N} | TEST_NAMES |
| {N} | TEST_DEFS |

### HTML Dashboard Status

| Check | Status |
|-------|--------|
| TEST_DEFS complete (1-N) | OK / GAPS |
| LATEST_RESULTS complete | OK / GAPS |
| Readiness entries complete | OK / GAPS |
| Category tags valid | OK / INVALID |
| Filter count correct | OK / WRONG |

### Recommendations

- {actions to take}
```

## Quick Checks

If you just want to verify specific things without a full check:

```bash
# TypeScript only
cd client && npx tsc --noEmit 2>&1 | tail -5

# Count TEST_NAMES entries
grep -c "'" client/app/admin/tests/page.tsx

# Count TEST_DEFS entries
grep -c "{ id:" test_results_dashboard.html

# Verify both have same count
echo "TEST_NAMES:" && grep -c "'" client/app/admin/tests/page.tsx
echo "TEST_DEFS:" && grep -c "{ id:" test_results_dashboard.html
```

## Troubleshooting

### TypeScript Build Fails

```bash
# Show specific errors
cd client && npx tsc --noEmit 2>&1 | grep "error TS"
```

### Missing node_modules

```bash
cd client && npm install
```

### TEST_NAMES Count Mismatch

```bash
# Compare test IDs in both files
grep -oP "'(\d+)'" client/app/admin/tests/page.tsx | sort -n
grep -oP "id: (\d+)" test_results_dashboard.html | sort -n
```

### SKILL_TEST_MAP References Invalid Test

```bash
# List all test IDs referenced in SKILL_TEST_MAP
grep -oP '\[\d+' client/app/admin/eval/page.tsx | sort -n -u
```
