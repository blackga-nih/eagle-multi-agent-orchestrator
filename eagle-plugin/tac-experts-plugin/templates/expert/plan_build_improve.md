---
description: "Full ACT-LEARN-REUSE workflow: plan {{DOMAIN}} changes, implement them, validate, and update expertise"
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
argument-hint: [feature or change description]
---

# {{DOMAIN_TITLE}} Expert - Plan Build Improve Workflow

> Full ACT-LEARN-REUSE workflow for {{DOMAIN}} development.

## Purpose

Execute the complete development workflow:
1. **PLAN** — Design using domain expertise
2. **VALIDATE (baseline)** — Check current state
3. **BUILD** — Implement the plan
4. **VALIDATE (post)** — Verify implementation
5. **REVIEW** — Check quality and compliance
6. **IMPROVE** — Update expertise with learnings

## Usage

```
/experts:{{DOMAIN}}:plan_build_improve [feature or change]
```

## Variables

- `TASK`: $ARGUMENTS

## Allowed Tools

`Read`, `Write`, `Edit`, `Bash`, `Grep`, `Glob`

---

## Workflow

### Step 1: PLAN

1. Read `.claude/commands/experts/{{DOMAIN}}/expertise.md`
2. Analyze TASK against domain patterns
3. Create implementation plan
4. Write to `.claude/specs/{{DOMAIN}}-{feature}.md`

### Step 2: VALIDATE (Baseline)

1. Run pre-change validation:
   ```bash
   {{BASELINE_VALIDATION_COMMAND}}
   ```
2. Note baseline state for comparison
3. **STOP if baseline is broken** — fix existing issues first

### Step 3: BUILD

1. Follow the plan from Step 1
2. Use existing patterns from expertise.md as reference
3. Keep changes atomic

### Step 4: VALIDATE (Post-Implementation)

1. Run post-change validation:
   ```bash
   {{POST_VALIDATION_COMMAND}}
   ```
2. Compare to baseline — all existing tests still pass?
3. If validation fails: fix and re-validate

### Step 5: REVIEW

1. Review changes against domain patterns
2. Check for anti-patterns from expertise.md Learnings section
3. Verify consistency with existing code style

### Step 6: IMPROVE (Self-Improve)

1. Determine outcome: success / partial / failed
2. Update `.claude/commands/experts/{{DOMAIN}}/expertise.md`:
   - Add to `patterns_that_work`
   - Add to `patterns_to_avoid`
   - Document any `common_issues`
   - Add helpful `tips`
3. Update `last_updated` timestamp

---

## Report Format

```markdown
## {{DOMAIN_TITLE}} Development Complete: {TASK}

### Summary

| Phase | Status | Notes |
|-------|--------|-------|
| Plan | DONE | {plan summary} |
| Baseline | PASS | {baseline state} |
| Build | DONE | {files created/modified} |
| Validation | PASS | {validation results} |
| Review | PASS | {review notes} |
| Improve | DONE | Expertise updated |

### Files Created/Modified

| File | Action | Notes |
|------|--------|-------|
| {path} | Created/Modified | {notes} |

### Learnings Captured

- Pattern: {what worked}
- Tip: {useful observation}
```

---

## Instructions

1. **Follow the workflow order** — don't skip validation steps
2. **Stop on failures** — fix before proceeding
3. **Keep atomic** — one feature per workflow
4. **Always improve** — even failed attempts have learnings
