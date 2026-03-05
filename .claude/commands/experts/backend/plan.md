---
description: "Plan backend changes — new tool handlers, prompt updates, AWS integrations — using expertise context"
allowed-tools: Read, Write, Glob, Grep, Bash
argument-hint: [feature description or change to plan]
---

# Backend Expert - Plan Mode

> Create detailed plans for backend changes informed by expertise.

## Purpose

Generate a plan for adding tool handlers, modifying existing handlers, updating the SYSTEM_PROMPT, or changing AWS integrations, using:
- Expertise from `.claude/commands/experts/backend/expertise.md`
- Current backend architecture and patterns
- AWS resource dependencies
- Validation-first methodology

## Usage

```
/experts:backend:plan [feature description or change]
```

## Variables

- `TASK`: $ARGUMENTS

## Allowed Tools

`Read`, `Write`, `Glob`, `Grep`, `Bash`

---

## Workflow

### Phase 1: Load Context

1. Read `.claude/commands/experts/backend/expertise.md` for:
   - Tool dispatch architecture
   - Existing handler patterns
   - Tenant scoping rules
   - Known issues and gotchas

2. Read `server/app/agentic_service.py` for:
   - Current TOOL_DISPATCH entries
   - EAGLE_TOOLS schema definitions
   - Handler implementations near the change area

3. Understand the TASK:
   - Is this a new tool handler?
   - Is this a modification to an existing handler?
   - Does it change SYSTEM_PROMPT?
   - Does it add AWS resource dependencies?

### Phase 2: Analyze Current State

1. Search for related code:
   ```
   grep "pattern" server/app/agentic_service.py
   ```

2. Check existing patterns:
   ```
   grep "def _exec_" server/app/agentic_service.py
   ```

3. Identify:
   - Files that need to change
   - Dependencies and prerequisites
   - Impact on existing tools
   - Impact on test suite

### Phase 3: Generate Plan

Create a plan document:

```markdown
# Backend Plan: {TASK}

## Overview
- Change Type: New Tool | Modify Handler | Update Prompt | AWS Integration
- Files Modified: {list}
- AWS Resources: {new or existing}
- Breaking Changes: Yes/No
- Test Impact: {which tests affected}

## Design

### Changes to server/app/agentic_service.py

| Location | Change |
|----------|--------|
| line ~{N} | {description} |

### New Handler (if applicable)

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| action | string | yes | Operation to perform |

### Return Shape

```json
{
  "field": "value"
}
```

## Registration Checklist

- [ ] Handler function `_exec_new_tool()` added
- [ ] `TOOL_DISPATCH` entry (line ~2167)
- [ ] `TOOLS_NEEDING_SESSION` updated if needed (line ~2178)
- [ ] `EAGLE_TOOLS` schema added (line ~173)
- [ ] `SYSTEM_PROMPT` updated if needed
- [ ] Syntax check passes

## Validation

1. `python -c "import py_compile; py_compile.compile('server/app/agentic_service.py', doraise=True)"`
2. Test via execute_tool() call
3. Check existing tests still pass
```

### Phase 4: Save Plan

1. Write plan to `.claude/specs/backend-{feature}.md`
2. Report plan summary to user

---

## Instructions

1. **Always read expertise.md first** - Contains patterns and conventions
2. **Follow handler patterns** - Match existing `_exec_*()` signatures and return shapes
3. **Include all registration points** - TOOL_DISPATCH, EAGLE_TOOLS, TOOLS_NEEDING_SESSION
4. **Consider tenant scoping** - Does the new tool need per-user isolation?
5. **Consider test impact** - Will eval tests need updates?
6. **Estimate scope** - Note how many lines change and where

---

## Output Location

Plans are saved to: `.claude/specs/backend-{feature}.md`
