---
description: "Plan {{DOMAIN}} changes using accumulated expertise"
allowed-tools: Read, Write, Glob, Grep, Bash
argument-hint: [feature or change to plan]
---

# {{DOMAIN_TITLE}} Expert - Plan Mode

> Create domain-aware plans for {{DOMAIN}} changes.

## Purpose

Generate a plan informed by accumulated {{DOMAIN}} expertise, current codebase state, and TAC principles.

## Usage

```
/experts:{{DOMAIN}}:plan [feature or change description]
```

## Variables

- `TASK`: $ARGUMENTS

## Allowed Tools

`Read`, `Write`, `Glob`, `Grep`, `Bash`

---

## Workflow

### Phase 1: Load Context

1. Read `.claude/commands/experts/{{DOMAIN}}/expertise.md` for:
   - Domain patterns and conventions
   - Known issues and workarounds
   - Architecture and key files

2. Scan current state:
   ```
   Glob: {{SOURCE_GLOB_PATTERN}}
   ```

### Phase 2: Analyze

1. Map TASK to domain patterns
2. Identify affected files
3. Check for known issues that might apply
4. Select validation strategy

### Phase 3: Generate Plan

```markdown
# Plan: {TASK}

## Analysis

| Dimension | Assessment |
|-----------|------------|
| Affected area | {area} |
| Complexity | {low/medium/high} |
| Key patterns | {patterns from expertise.md} |
| Risk factors | {known issues that apply} |

## Implementation Steps

### Step 1: {action}
- Details: {what to do}
- Validation: {how to verify}

### Step 2: {action}
...

## Files to Create/Modify

| File | Action | Notes |
|------|--------|-------|
| {path} | Create/Edit | {notes} |

## Validation Strategy

- [ ] {check 1}
- [ ] {check 2}
- [ ] {check 3}
```

### Phase 4: Save Plan

1. Write plan to `.claude/specs/{{DOMAIN}}-{feature}.md`
2. Report summary to user

---

## Instructions

1. **Always read expertise.md first** — contains domain patterns that inform the plan
2. **Reference known issues** — check Learnings section for gotchas
3. **Include validation** — every plan must have built-in checks
4. **Keep it actionable** — steps should be concrete enough for an agent to execute

---

## Output Location

Plans are saved to: `.claude/specs/{{DOMAIN}}-{feature}.md`
