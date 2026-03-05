---
description: "Scan recent changes, plan + add tests in parallel, run the suite, then self-improve expertise"
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, Agent
argument-hint: "[optional: space-separated feature areas or file paths to test]"
---

# Parallel Test Suite Update

> Detect what changed, spawn parallel agents to add tests, validate, then self-improve.

## Purpose

After a feature branch or commit lands, run this command to automatically:
1. Detect what source files changed
2. Group changes by test area
3. Launch parallel `add-test` agents (one per area)
4. Run the full suite to catch regressions
5. Self-improve the test expertise

This is the test expert's equivalent of `parallel_expert_self_improve` — but it **writes tests**, not just expertise.

## Variables

- `ARGS`: $ARGUMENTS (optional file paths or feature keywords)

---

## Workflow

### Phase 1: Detect Changes

If ARGS is provided, use those as the target areas. Otherwise, auto-detect:

1. **Recent commits** — identify changed source files:
   ```bash
   cd server && git diff HEAD~3 --name-only -- app/ | grep '\.py$'
   ```

2. **Unstaged changes** — catch work-in-progress:
   ```bash
   cd server && git diff --name-only -- app/ | grep '\.py$'
   ```

3. **Untracked files** — new modules without tests:
   ```bash
   cd server && git ls-files --others --exclude-standard -- app/ | grep '\.py$'
   ```

4. Merge all three lists into CHANGED_FILES (deduplicated).

5. If CHANGED_FILES is empty and no ARGS, STOP and report "No changes detected."

### Phase 2: Group by Test Area

Map each changed file to a test area:

| Source pattern | Test area | Target test file |
|---------------|-----------|-----------------|
| `app/feedback_store.py` | feedback-store | `test_feedback_store.py` |
| `app/main.py` (new endpoints) | endpoints | `test_chat_endpoints.py` |
| `app/session_store.py` | session-store | `test_session_store.py` |
| `app/strands_agentic_service.py` | strands | `test_strands_*.py` |
| `app/streaming_routes.py` | streaming | `test_streaming.py` |
| `app/*_store.py` | store-{name} | `test_{name}_store.py` |
| `app/document_export.py` | document | `test_document_pipeline.py` |
| Other `app/*.py` | {module} | `test_{module}.py` |

Produce a list of TEST_AREAS, each with:
- `area`: short name
- `source_files`: list of changed source files
- `target_test_file`: where tests should go
- `description`: what to test (derived from git diff summary)

### Phase 3: Read Expertise Context

```
Read .claude/commands/experts/test/expertise.md
```

Extract:
- Existing test inventory (Part 1) — avoid duplicating tests
- Test patterns (Part 2) — pass to agents
- Coverage gaps (Part 3) — prioritize these areas

### Phase 4: Run Baseline

Before adding tests, capture the current state:

```bash
cd server && python -m pytest tests/ -v --tb=short 2>&1 | tail -30
```

Record BASELINE_PASS_COUNT and BASELINE_FAIL_COUNT. If baseline has failures, note them so agents don't re-report known issues.

### Phase 5: Launch Parallel Add-Test Agents

For each TEST_AREA, launch an Agent (subagent_type: `general-purpose`) with a self-contained prompt:

```
You are the EAGLE test expert. Add tests for the {area} area.

## What changed
{git diff summary for source_files}

## Source code
Read these files: {source_files}

## Target test file
{target_test_file} — create if it doesn't exist, append if it does.

## Test patterns to follow
- Import from `app.*` inside test methods (avoids module-level AWS init)
- Mock all external dependencies (DDB, S3, Bedrock) with `unittest.mock.patch`
- Clear caches at end of cache tests: `_cache.clear()`
- Use Arrange/Act/Assert structure
- Class name: Test{FeatureName}, method: test_{behavior}
- For endpoint tests use `fastapi.testclient.TestClient`

## Existing tests to avoid duplicating
{list from expertise.md Part 1}

## Instructions
1. Read the source file(s) to understand what to test
2. Read the target test file (if it exists) to see existing tests
3. Write 2-5 focused test functions covering:
   - Happy path
   - Edge cases (empty input, missing fields)
   - Error handling (mock exceptions)
4. Run: `cd server && ruff check tests/{target_test_file}`
5. Run: `cd server && python -m pytest tests/{target_test_file} -v`
6. Fix any failures
7. Report what tests were added and their pass/fail status
```

**Launch all agents in parallel** using the Agent tool with multiple invocations in a single message.

### Phase 6: Collect Results

After all agents complete:

1. Gather each agent's report (tests added, pass/fail)
2. Build a combined test inventory

### Phase 7: Full Suite Validation

Run the complete suite to check for regressions:

```bash
cd server && python -m pytest tests/ -v --tb=short 2>&1
```

Compare to baseline:
- Same or more passes?
- No new failures?
- If regressions found, diagnose and fix inline.

### Phase 8: Self-Improve

Launch a final agent to update expertise:

```
Run the test expert self-improve workflow.

## What happened
- Areas tested: {TEST_AREAS}
- Tests added: {count}
- Pass/fail: {results}
- New patterns discovered: {any}

Update expertise.md with:
1. Part 1 (Test Inventory) — add new test files/classes
2. Part 3 (Coverage Gaps) — mark resolved gaps
3. Part 5 (Learnings) — record patterns that worked
4. Update last_updated timestamp
```

---

## Report Format

```markdown
## Parallel Test Suite Update

**Trigger**: {ARGS or "auto-detected from recent changes"}
**Date**: {timestamp}

### Changes Detected

| Source file | Test area |
|------------|-----------|
| {file} | {area} |

### Agents Launched: {N}

| Area | Agent | Tests Added | Status |
|------|-------|-------------|--------|
| {area} | {agent_id} | {N} | PASS/PARTIAL/FAIL |

### Suite Validation

| Metric | Baseline | After | Delta |
|--------|----------|-------|-------|
| Total | {N} | {N} | +{N} |
| Passed | {N} | {N} | +{N} |
| Failed | {N} | {N} | {N} |

### New Tests

| File | Class | Test | Status |
|------|-------|------|--------|
| {file} | {class} | {test} | PASS |

### Expertise Updated
- Sections modified: {list}
- Coverage gaps resolved: {list}
```

---

## Examples

```bash
# Auto-detect from recent commits
/experts:test:parallel_test_suite_update

# Target specific files
/experts:test:parallel_test_suite_update feedback_store.py main.py

# Target feature areas
/experts:test:parallel_test_suite_update feedback endpoints streaming
```

## Important Notes

- Each parallel agent is **self-contained** — provide full context in the prompt
- Agents write to **different test files** to avoid merge conflicts
- If two areas map to the same test file, merge them into one agent
- Maximum 5 parallel agents to avoid rate limits
- Always run full suite after all agents complete
- Self-improve runs last, after validation confirms everything passes
