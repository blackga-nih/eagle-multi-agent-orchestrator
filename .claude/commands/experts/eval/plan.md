---
description: "Plan new eval tests, test modifications, or coverage improvements using expertise context"
allowed-tools: Read, Write, Glob, Grep, Bash
argument-hint: [test description or feature to test]
---

# Eval Expert - Plan Mode

> Create detailed plans for new tests or eval suite changes informed by expertise.

## Purpose

Generate a plan for adding tests, modifying existing tests, or improving coverage, using:
- Expertise from `expertise.md`
- Current test suite patterns
- AWS tool implementations
- Validation-first methodology

## Usage

```
/experts:eval:plan [test description or feature]
```

## Variables

- `TASK`: $ARGUMENTS

## Allowed Tools

`Read`, `Write`, `Glob`, `Grep`, `Bash`

---

## Workflow

### Phase 1: Load Context

1. Read `expertise.md` for:
   - Test architecture and tiers
   - Existing test patterns
   - AWS tool interfaces
   - Known issues and gotchas

2. Read `server/tests/test_eagle_sdk_eval.py` for:
   - Current test count and registry
   - Existing test implementations
   - Helper functions available

3. Understand the TASK:
   - What feature/tool is being tested?
   - Which tier does it belong to? (SDK, Skill, AWS Tool)
   - What AWS services are involved?

### Phase 2: Analyze Current State

1. Search for related tests:
   ```
   grep "test_pattern" server/tests/test_eagle_sdk_eval.py
   ```

2. Check tool implementations:
   ```
   grep "def _exec_" server/app/agentic_service.py
   ```

3. Identify:
   - Next available test number
   - Files that need to change
   - Dependencies and prerequisites

### Phase 3: Generate Plan

Create a plan document:

```markdown
# Eval Plan: {TASK}

## Overview
- Test Number(s): {N}
- Tier: SDK Pattern | Skill Validation | AWS Tool Integration
- AWS Services: {list}
- LLM Required: Yes/No
- Estimated Cost: ${amount per run}

## Test Design

### Test {N}: {Name}

| Step | Action | Verify |
|------|--------|--------|
| 1 | {operation} | {assertion} |
| 2 | {operation} | {assertion} |
| 3 | boto3 confirm | {independent check} |
| 4 | cleanup | {delete artifacts} |

Pass criteria: {conditions}

## Files Modified

| File | Change |
|------|--------|
| `server/tests/test_eagle_sdk_eval.py` | Add test function, update registry |

## Registration Checklist

- [ ] `async def test_N_name()` function
- [ ] `TEST_REGISTRY` entry in `_run_test()`
- [ ] `test_names` entry in `emit_to_cloudwatch()`
- [ ] `result_key` mapping in `main()` trace output
- [ ] Summary printout section in `main()`
- [ ] Default range updated if needed
- [ ] Docstring updated if test count changes

## Cleanup Strategy

{How test artifacts are cleaned up}

## Verification

1. `python server/tests/test_eagle_sdk_eval.py --tests {N}` — passes
2. CloudWatch: event emitted for test {N}
3. No artifacts left behind
```

### Phase 4: Save Plan

1. Write plan to `.claude/specs/eval-{feature}.md`
2. Report plan summary to user

---

## Instructions

1. **Always read expertise.md first** - Contains patterns and conventions
2. **Follow naming conventions** - `test_{N}_{snake_case}`, `{N}_{snake_case}`
3. **Include cleanup** - Every test that creates resources must clean up
4. **Include boto3 confirmation** - AWS tool tests need independent verification
5. **Keep tests idempotent** - Safe to run repeatedly
6. **Estimate costs** - Note if test requires LLM calls (Bedrock cost)

---

## Output Location

Plans are saved to: `.claude/specs/eval-{feature}.md`
