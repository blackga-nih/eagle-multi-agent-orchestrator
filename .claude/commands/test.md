---
description: "Run tests — infers the right modules from changed files, or use --full for everything"
allowed-tools: Read, Bash, Grep, Glob
argument-hint: [--full | --file test_name.py | --perf | --lint | (empty = auto-infer)]
---

# /test — Smart Test Runner

Run the correct tests based on what changed. No arguments = auto-infer from `git diff`. Flags override inference.

## Variables

- `FLAGS`: $ARGUMENTS

## Instructions

You are a test runner. Your job is to determine WHICH tests to run, run them, and report results. You do NOT write code — you only read files and execute commands.

Parse `FLAGS` to determine mode:

| Flag | Mode | What runs |
|------|------|-----------|
| (empty) | **Auto-infer** | Detect changed files, map to test modules |
| `--full` | **Full suite** | All pytest + lint |
| `--file <name>` | **Specific file** | Run just that test file |
| `--perf` | **Performance** | `test_perf_simple_message.py` only |
| `--lint` | **Lint only** | `ruff check app/` only |
| `--smoke` | **Smoke tests** | Perf + chat endpoints + lint |
| `--e2e` | **Playwright E2E** | `npx playwright test` (client/) |
| `--eval [N,N]` | **Eval suite** | `test_strands_eval.py` with optional test IDs |

---

## Workflow

### Step 1: Determine Mode

Parse `FLAGS`. If empty or unrecognized, use **auto-infer** mode.

### Step 2: Auto-Infer (when no flags)

Run this to get changed files:

```bash
cd server && git diff --name-only HEAD 2>/dev/null; git diff --name-only --cached 2>/dev/null; git diff --name-only HEAD~1 HEAD 2>/dev/null
```

Also check for unstaged changes:
```bash
cd server && git diff --name-only 2>/dev/null
```

Deduplicate the file list. Then apply the mapping table below to determine which test files to run.

#### Source-to-Test Mapping

| Changed file (in `server/app/`) | Test file(s) to run |
|--------------------------------|---------------------|
| `main.py` | `test_perf_simple_message.py`, `test_chat_endpoints.py`, `test_document_pipeline.py` |
| `strands_agentic_service.py` | `test_perf_simple_message.py`, `test_strands_service_integration.py` |
| `workspace_store.py` | `test_perf_simple_message.py` |
| `agentic_service.py` | `test_document_pipeline.py` |
| `session_store.py` | `test_chat_endpoints.py` |
| `streaming_routes.py` | `test_chat_endpoints.py` |
| `stream_protocol.py` | `test_document_pipeline.py` |
| `document_store.py` | `test_document_pipeline.py` |
| `document_export.py` | `test_document_pipeline.py` |
| `skill_store.py` | `test_perf_simple_message.py` |
| `plugin_store.py` | `test_perf_simple_message.py` |
| `wspc_store.py` | `test_perf_simple_message.py` |
| `cost_attribution.py` | `test_chat_endpoints.py` |
| `auth.py` or `admin_auth.py` | `test_chat_endpoints.py` |

| Changed file (in `server/`) | Test file(s) to run |
|-----------------------------|---------------------|
| `eagle_skill_constants.py` | `test_perf_simple_message.py`, `test_strands_service_integration.py` |
| Any `tests/test_*.py` | That test file itself |

| Changed file (in `client/`) | What to run |
|-----------------------------|-------------|
| Any `*.tsx`, `*.ts` | `npx playwright test` (suggest, don't auto-run — slow) |

| Changed file (in `eagle-plugin/`) | Test file(s) to run |
|-----------------------------------|---------------------|
| Any `agent.md` or `SKILL.md` | `test_perf_simple_message.py`, `test_strands_service_integration.py` |

If NO changed files map to any test, print:
```
No testable changes detected. Use --full to run everything.
```

### Step 3: Always Lint First

Before running any tests, always lint:

```bash
cd server && ruff check app/ 2>&1 | tail -5
```

Report lint status. If there are errors, still proceed to tests (lint errors are informational, not blocking for test runs).

### Step 4: Run Tests

Build the pytest command from the inferred (or explicit) test files:

```bash
cd server && python -m pytest tests/{file1}.py tests/{file2}.py -v --tb=short 2>&1
```

For `--full` mode:
```bash
cd server && python -m pytest tests/ -v --tb=short --timeout=120 2>&1
```

For `--e2e` mode:
```bash
cd client && npx playwright test --reporter=list 2>&1
```

For `--eval` mode:
```bash
python server/tests/test_strands_eval.py --model haiku --tests {N,N,N} 2>&1
# Or without --tests for full eval:
python server/tests/test_strands_eval.py --model haiku 2>&1
```

### Step 5: Report

Print a structured report:

```
Test Run Report
===============

Mode:     {auto-infer | --full | --file | ...}
Trigger:  {list of changed source files that triggered test selection}

Lint:     {PASS | N errors (non-blocking)}

Tests Run:
  {test_file_1.py}  {N passed} / {N failed} / {N skipped}
  {test_file_2.py}  {N passed} / {N failed} / {N skipped}

Total:    {N passed}, {N failed}, {N skipped} in {N.N}s
Status:   ALL PASS | FAILURES DETECTED
```

If there are failures, list each failed test with its error message (first 3 lines of traceback).

---

## Examples

### `/test` (auto-infer from git diff)
```
Changed: app/workspace_store.py, app/strands_agentic_service.py
 -> Running: test_perf_simple_message.py, test_strands_service_integration.py
```

### `/test --full`
```
Running all tests in server/tests/
```

### `/test --file test_fast_path.py`
```
Running: test_fast_path.py
```

### `/test --perf`
```
Running: test_perf_simple_message.py
```

### `/test --smoke`
```
Running: lint + test_perf_simple_message.py + test_chat_endpoints.py
```

### `/test --eval 16,17,18`
```
Running: test_strands_eval.py --tests 16,17,18
```
