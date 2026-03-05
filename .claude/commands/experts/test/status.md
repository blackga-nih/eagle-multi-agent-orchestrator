---
description: "Quick test inventory count — no execution, just file/test counts across pytest and Playwright"
allowed-tools: Bash, Glob, Grep
---

# Test Expert - Status Command

> Fast read-only inventory of all test files and test counts. No tests are executed.

## Usage

```
/experts:test:status
```

## Workflow

1. **Count pytest test files and test functions**:
   ```bash
   cd server && grep -r "def test_" tests/test_*.py | wc -l
   ```

2. **Count Playwright spec files and test blocks**:
   ```bash
   cd client && grep -r "test(" tests/*.spec.ts | wc -l
   ```

3. **List test files with modification dates** (most recently changed first)

## Report Format

```markdown
## Test Inventory Status

### Backend (pytest)
| File | Test Count | Last Modified |
|------|-----------|---------------|
| ... | ... | ... |
**Total**: {N} tests across {M} files

### Frontend (Playwright)
| File | Test Count | Last Modified |
|------|-----------|---------------|
| ... | ... | ... |
**Total**: {N} tests across {M} files

### Grand Total: {N} tests
```

## Instructions

1. **Never run tests** — this is inventory only
2. Count `def test_` for pytest, `test(` or `test.describe` for Playwright
3. Sort by last modified (most recent first)
4. Flag any empty test files (0 test functions)
