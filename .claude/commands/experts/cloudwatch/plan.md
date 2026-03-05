---
description: "Plan changes to CloudWatch telemetry, emission pipeline, event schemas, or log queries"
allowed-tools: Read, Write, Glob, Grep, Bash
argument-hint: [description of CloudWatch change]
---

# CloudWatch Expert - Plan Mode

> Create detailed plans for CloudWatch telemetry changes informed by expertise.

## Purpose

Generate a plan for modifying the CloudWatch emission pipeline, adding new event schemas, changing query patterns, or updating the CloudWatch Logs tool, using:
- Expertise from `.claude/commands/experts/cloudwatch/expertise.md`
- Current emission and query implementations
- boto3 API constraints
- Known issues and gotchas

## Usage

```
/experts:cloudwatch:plan [description of CloudWatch change]
```

## Variables

- `TASK`: $ARGUMENTS

## Allowed Tools

`Read`, `Write`, `Glob`, `Grep`, `Bash`

---

## Workflow

### Phase 1: Load Context

1. Read `.claude/commands/experts/cloudwatch/expertise.md` for:
   - Log group structure and stream naming
   - Event schemas (test_result, run_summary)
   - Emission pipeline details
   - CloudWatch tool operations
   - boto3 API patterns
   - Known issues

2. Read source files as needed:
   - `server/tests/test_eagle_sdk_eval.py` (~line 2222-2311) for emission implementation
   - `server/app/agentic_service.py` (~line 589-705) for CloudWatch tool

3. Understand the TASK:
   - Is this a schema change? New event type?
   - Is this an emission change? New pipeline step?
   - Is this a query change? New operation?
   - What boto3 APIs are involved?

### Phase 2: Analyze Impact

1. Identify affected components:
   - `emit_to_cloudwatch()` in server/tests/test_eagle_sdk_eval.py
   - `_exec_cloudwatch_logs()` in agentic_service.py
   - Test 18 (cloudwatch_logs_ops)
   - Test 20 (cloudwatch_e2e_verification)
   - `trace_logs.json` local output

2. Check for conflicts:
   - Does the change break the run_summary invariant?
   - Does it affect event ordering?
   - Does it exceed message size limits?
   - Does it interact with tenant scoping?

3. Identify risks:
   - Eventual consistency implications
   - Backward compatibility with existing streams
   - Error handling coverage

### Phase 3: Generate Plan

Create a plan document:

```markdown
# CloudWatch Plan: {TASK}

## Overview
- Change Type: Schema | Emission | Query | Tool | Infrastructure
- Files Modified: {list}
- boto3 APIs Affected: {list}
- Breaking Changes: Yes/No

## Design

### Current State
{How it works now}

### Proposed Change
{What will change}

### Event Schema Changes (if any)

| Field | Type | Before | After |
|-------|------|--------|-------|
| {field} | {type} | {old} | {new} |

## Implementation Steps

| # | File | Change | Line |
|---|------|--------|------|
| 1 | {file} | {description} | ~{line} |

## Impact Analysis

### Affected Tests
- Test 18: {impact}
- Test 20: {impact}

### Backward Compatibility
{Can old streams coexist with new streams?}

### Error Handling
{What new failure modes are introduced?}

## Verification

1. Run test 18: `python server/tests/test_eagle_sdk_eval.py --model haiku --tests 18`
2. Run test 20: `python server/tests/test_eagle_sdk_eval.py --model haiku --tests 20`
3. Check CloudWatch: `aws logs describe-log-streams --log-group-name /eagle/test-runs --limit 1`
4. Verify event structure: {specific check}

## Rollback
{How to revert if something goes wrong}
```

### Phase 4: Save Plan

1. Write plan to `.claude/specs/cloudwatch-{feature}.md`
2. Report plan summary to user

---

## Instructions

1. **Always read expertise.md first** - Contains architecture, schemas, and known issues
2. **Check event schema invariants** - passed + skipped + failed == total_tests
3. **Consider eventual consistency** - Reads may lag writes
4. **Preserve non-fatal behavior** - Emission must never crash the test suite
5. **Sort events by timestamp** - CloudWatch requires ascending order
6. **Account for tenant scoping** - The search operation adds tenant_id to filter patterns
7. **Test with both 18 and 20** - Test 18 validates the tool; test 20 validates emission

---

## Output Location

Plans are saved to: `.claude/specs/cloudwatch-{feature}.md`
