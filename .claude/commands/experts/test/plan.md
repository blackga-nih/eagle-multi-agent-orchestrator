---
description: "Plan new tests, smoke tests, regression tests, or coverage improvements using expertise context"
allowed-tools: Read, Write, Glob, Grep, Bash
argument-hint: [test description or feature to test]
---

# Test Expert - Plan Mode

> Create detailed plans for new tests or test suite changes informed by expertise.

## Purpose

Generate a plan for adding tests, improving coverage, or building smoke/regression test suites, using:
- Expertise from `expertise.md`
- Current test suite patterns
- Coverage gap analysis
- Validation-first methodology

## Usage

```
/experts:test:plan [test description or feature]
```

## Variables

- `TASK`: $ARGUMENTS

## Allowed Tools

`Read`, `Write`, `Glob`, `Grep`, `Bash`

---

## Workflow

### Phase 1: Load Context

1. Read `expertise.md` for:
   - Test inventory and patterns
   - Coverage gaps
   - Known issues and learnings

2. Understand the TASK:
   - What feature/behavior is being tested?
   - Unit test (mocked) or integration (real AWS)?
   - Which source files are involved?

3. Search for related existing tests:
   ```
   Grep pattern="relevant_pattern" path="server/tests/"
   ```

### Phase 2: Analyze Current Coverage

1. Identify what's already tested:
   ```
   Grep pattern="class Test|def test_" path="server/tests/" glob="test_*.py"
   ```

2. Identify source code paths needing coverage:
   ```
   Grep pattern="def function_name" path="server/app/"
   ```

3. Classify gaps by priority (HIGH/MEDIUM/LOW)

### Phase 3: Design Tests

For each test, specify:

| Field | Value |
|-------|-------|
| File | New or existing test file |
| Class | `TestClassName` |
| Method | `test_descriptive_name` |
| Type | Unit (mocked) / Integration / Smoke / E2E |
| Mocks | What to mock and how |
| Assertions | What to verify |
| Cleanup | Cache clears, artifact deletion |

### Phase 4: Generate Plan

```markdown
# Test Plan: {TASK}

## Overview
- New tests: {N}
- Modified tests: {N}
- Test file(s): {list}
- Type: Unit / Integration / Smoke / E2E
- AWS required: Yes / No
- LLM cost: $0 / ${amount}

## Tests

### Test 1: {descriptive name}

| Step | Action | Assert |
|------|--------|--------|
| 1 | {setup} | {precondition} |
| 2 | {call} | {expected result} |
| 3 | {cleanup} | {clean state} |

Mock setup:
- `mock.patch("app.module.dependency")`

### Test 2: ...

## Files Modified

| File | Change |
|------|--------|
| `server/tests/test_*.py` | Add/modify test class |

## Verification

1. `ruff check app/` — lint passes
2. `python -m pytest tests/{file} -v` — all tests pass
3. `python -m pytest tests/ -v` — no regressions
```

### Phase 5: Save Plan

1. Write plan to `.claude/specs/test-{feature}.md`
2. Report plan summary to user

---

## Test Type Decision Tree

```mermaid
flowchart TD
    A[What to test?] --> B{Needs real AWS?}
    B -->|No| C{Needs real LLM?}
    B -->|Yes| D[Integration Test]
    C -->|No| E[Unit Test - mocked]
    C -->|Yes| F[Integration Test]
    E --> G{Testing cache/perf?}
    G -->|Yes| H[Add to test_perf_simple_message.py]
    G -->|No| I{Testing endpoint?}
    I -->|Yes| J[Add to test_chat_endpoints.py or new file]
    I -->|No| K[New test file: test_{feature}.py]
    D --> L{Testing Strands Agent?}
    L -->|Yes| M[Add to test_strands_*.py]
    L -->|No| N{Testing document pipeline?}
    N -->|Yes| O[Add to test_document_pipeline.py]
    N -->|No| P[New test file]
```

---

## Instructions

1. **Always read expertise.md first** - Contains patterns and known gaps
2. **Follow existing patterns** - Use Pattern 1-7 from expertise.md Part 2
3. **Include cleanup** - Cache clears, artifact deletion
4. **Keep tests fast** - Mock AWS/Bedrock for unit tests
5. **Estimate costs** - Note if test requires LLM calls
6. **Include verification commands** - Exact pytest commands to validate
