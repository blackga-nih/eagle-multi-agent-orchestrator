---
description: "Update frontend expertise with learnings from development, build results, or discovered issues"
allowed-tools: Read, Edit, Glob, Grep, Bash
argument-hint: [component] [outcome: success|failed|partial]
---

# Frontend Expert - Self-Improve Mode

> Update expertise.md with learnings from frontend development and maintenance.

## Purpose

After making frontend changes, running builds, or discovering issues, run self-improve to:
- Record what worked (patterns_that_work)
- Record what to avoid (patterns_to_avoid)
- Document issues encountered (common_issues)
- Add tips for future development

This is the **LEARN** step in ACT-LEARN-REUSE.

## Usage

```
/experts:frontend:self-improve chat-interface success
/experts:frontend:self-improve test-mappings failed
/experts:frontend:self-improve eval-page partial
```

## Variables

- `COMPONENT`: $1 (component or area)
- `OUTCOME`: $2 (success | failed | partial)

## Allowed Tools

`Read`, `Edit`, `Glob`, `Grep`, `Bash`

---

## Workflow

### Phase 1: Gather Information

1. Read current `.claude/commands/experts/frontend/expertise.md`
2. Check build status:
   ```bash
   cd client && npm run build 2>&1 | tail -20
   ```
3. Read git log for recent changes:
   ```bash
   git log --oneline -10
   git diff HEAD~3 --stat -- client/ test_results_dashboard.html
   ```
4. Check for mapping consistency (if applicable)

### Phase 2: Analyze Outcome

Based on OUTCOME:

**success**:
- What pattern made this successful?
- Any new components or interfaces worth documenting?
- Were there any surprises?

**failed**:
- What caused the failure?
- TypeScript error? Build failure? Missing mapping?
- What should be avoided next time?
- What needs to happen before retry?

**partial**:
- What worked vs what didn't?
- What remains to be done?
- What blockers were encountered?

### Phase 3: Update expertise.md

#### Update `Learnings` section:

Add entries to the appropriate subsection:

```markdown
### patterns_that_work
- {what worked} (discovered: {date}, component: {COMPONENT})

### patterns_to_avoid
- {what to avoid} (reason: {why})

### common_issues
- {issue}: {solution} (component: {COMPONENT})

### tips
- {useful tip learned}
```

#### Update other sections if needed:

- Part 1: New routes or components added
- Part 4/5: New test mappings registered
- Part 7: New styling patterns
- Part 8: New known issues

### Phase 4: Update timestamp

Update the `last_updated` field in the frontmatter.

---

## Report Format

```markdown
## Self-Improve Report: {COMPONENT}

### Outcome: {OUTCOME}

### Learnings Recorded

**Patterns that work:**
- {pattern 1}

**Patterns to avoid:**
- {pattern 1}

**Issues documented:**
- {issue 1}

**Tips added:**
- {tip 1}

### Expertise Updated

- expertise.md -> Learnings section
- expertise.md -> last_updated timestamp
- expertise.md -> {other sections if updated}
```

---

## Instructions

1. **Run after every significant frontend change** - Even failed builds have learnings
2. **Be specific** - Record concrete patterns, not vague observations
3. **Include context** - Date, component, and circumstances
4. **Keep it actionable** - Learnings should help future development
5. **Don't overwrite** - Append to existing learnings, don't replace

---

## Data Sources

| Source | Location | Content |
|--------|----------|---------|
| Build output | `npm run build` | TypeScript errors, warnings |
| Git history | `git log` | Recent changes and context |
| Browser DevTools | Manual | Runtime errors, layout issues |
| Mapping check | grep across files | TEST_NAMES, TEST_DEFS, SKILL_TEST_MAP consistency |
