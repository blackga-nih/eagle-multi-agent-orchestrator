---
description: "Scaffold a new pytest test file or add tests to an existing file, validate, and run"
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
argument-hint: [test description, target file, and what to validate]
model: opus
---

# Test Expert - Add New Test

> Scaffold new test functions, add them to the correct file, and validate.

## Purpose

Automate the full workflow for adding new tests to the EAGLE test suite. Handles test scaffolding, mock setup, assertion design, and validation.

## Variables

- `TASK`: $ARGUMENTS

## Instructions

- **CRITICAL**: You ARE writing code. Implement the full test(s).
- If no `TASK` is provided, STOP and ask the user what to test.
- Read `expertise.md` Part 2 (Test Patterns) for templates.
- Read `expertise.md` Part 3 (Coverage Gaps) for what needs testing.
- Follow naming conventions: `TestClassName`, `test_descriptive_name`.
- Always include cleanup for cache tests.
- Mock all external dependencies (DDB, S3, Bedrock) for unit tests.

---

## Workflow

### Phase 1: Determine Target

1. Read expertise context:
   ```
   Read .claude/commands/experts/test/expertise.md
   ```

2. Determine where the test belongs:

   | Feature area | Target file | Pattern |
   |-------------|-------------|---------|
   | Cache behavior | `test_perf_simple_message.py` | Pattern 2 |
   | Fast-path / regex | `test_fast_path.py` (new) | Pattern 5 |
   | Fire-and-forget | `test_fire_and_forget.py` (new) | Pattern 6 |
   | Endpoint schema | `test_chat_endpoints.py` | Pattern 7 |
   | Prompt behavior | `test_prompt_behavioral.py` (new) | Pattern 3 |
   | Document pipeline | `test_document_pipeline.py` | Existing |
   | Strands integration | `test_strands_*.py` | Existing |

3. If creating a new file, use this template:

   ```python
   """Description of what this test file validates.

   All tests are fast (mocked, no AWS) unless noted otherwise.
   """
   import time
   from unittest import mock

   import pytest


   # ---------------------------------------------------------------------------
   # Helpers
   # ---------------------------------------------------------------------------

   TENANT = "test-tenant"
   USER = "test-user"
   WORKSPACE_ID = "ws-001"
   TIER = "advanced"


   # ---------------------------------------------------------------------------
   # Test Class
   # ---------------------------------------------------------------------------

   class TestFeatureName:
       """Verify feature behavior."""

       def test_expected_behavior(self):
           """Description of what this validates."""
           # Arrange
           # Act
           # Assert
   ```

### Phase 2: Write Tests

Follow the appropriate pattern from expertise.md Part 2:

**For cache tests (Pattern 2):**
```python
def test_cache_behavior(self):
    from app.module import _cache, _cache_set, function
    _cache_set(key, value)
    with mock.patch("app.module.dependency") as m:
        result = function(key)
    assert result == value
    m.assert_not_called()
    _cache.clear()
```

**For regex tests (Pattern 5):**
```python
def test_pattern_matches(self):
    from app.main import _TRIVIAL_RE
    assert _TRIVIAL_RE.match("hi")
    assert not _TRIVIAL_RE.match("What is FAR?")
```

**For async resilience tests (Pattern 6):**
```python
@pytest.mark.asyncio
async def test_failure_doesnt_propagate(self):
    import asyncio
    loop = asyncio.get_event_loop()
    def failing(): raise Exception("boom")
    loop.run_in_executor(None, failing)
    await asyncio.sleep(0.1)
    # Pass = no exception propagated
```

**For endpoint tests (Pattern 7):**
```python
def test_endpoint_returns_200(self):
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
```

### Phase 3: Validate

Run in sequence:

1. **Lint check**:
   ```bash
   cd server && ruff check tests/{test_file}.py
   ```

2. **Run new tests**:
   ```bash
   python -m pytest tests/{test_file}.py -v
   ```

3. **Run related tests for regressions**:
   ```bash
   python -m pytest tests/test_perf_simple_message.py tests/test_chat_endpoints.py -v
   ```

4. **Count pass/fail**:
   - All new tests pass?
   - No regressions in existing tests?

### Phase 4: Report

```
Tests Added

  File:     server/tests/{test_file}.py
  Class:    {TestClassName}
  Tests:    {N} new tests

  Results:
    [x] {test_name_1} — PASS
    [x] {test_name_2} — PASS
    ...

  Lint:     PASS
  Regressions: None
```

---

## Important Notes

- **Import inside test methods** — avoids module-level AWS client initialization
- **Always clear caches** — `_cache.clear()` at end of cache tests
- **Mock at the right level** — `mock.patch("app.module.dependency")` not `mock.patch("dependency")`
- **Account for _compliance_matrix_tool** — `build_skill_tools()` always appends it
- **Use `time.perf_counter()`** for latency assertions, not `time.time()`
- **Keep tests independent** — no test should depend on another test's state
