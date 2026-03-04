---
description: "Update test expertise with learnings from test runs, new patterns, or discovered issues"
allowed-tools: Read, Edit, Glob, Grep, Bash
argument-hint: [component] [outcome: success|failed|partial]
---

# Test Expert - Self-Improve Mode

> Update expertise.md with learnings from test runs and test development.

## Purpose

After running tests, adding new tests, or diagnosing failures, run self-improve to:
- Record what worked (patterns_that_work)
- Record what to avoid (patterns_to_avoid)
- Document issues encountered (common_issues)
- Add tips for future test development
- Update coverage gap analysis

This is the **LEARN** step in ACT-LEARN-REUSE.

## Usage

```
/experts:test:self-improve fast-path-tests success
/experts:test:self-improve cache-invalidation failed
/experts:test:self-improve smoke-tests partial
```

## Variables

- `COMPONENT`: $1 (component or test area)
- `OUTCOME`: $2 (success | failed | partial)

## Allowed Tools

`Read`, `Edit`, `Glob`, `Grep`, `Bash`

---

## Workflow

### Phase 1: Gather Information

1. Read current `expertise.md`
2. Read recent test results (if available):
   ```bash
   # Last pytest output
   cd server && python -m pytest tests/test_perf_simple_message.py -v --tb=short 2>&1 | tail -20
   ```
3. Read git log for recent test changes:
   ```bash
   git log --oneline -10 -- server/tests/
   git diff HEAD~3 --stat -- server/tests/
   ```

### Phase 2: Analyze Outcome

Based on OUTCOME:

**success**:
- What patterns made tests reliable?
- Any new mock patterns worth documenting?
- Were there surprises?
- What should be replicated?

**failed**:
- What caused failures?
- Missing mocks? Wrong assertions? Import issues?
- What should be avoided?
- What needs to happen before retry?

**partial**:
- Which tests passed vs failed?
- What remains to be done?
- What blockers were encountered?

### Phase 3: Update expertise.md

Update the appropriate sections:

1. **Part 1 (Test Inventory)** — Add new test files/classes
2. **Part 2 (Test Patterns)** — Add new patterns discovered
3. **Part 3 (Coverage Gaps)** — Mark gaps as resolved or add new ones
4. **Part 5 (Learnings)** — Append to appropriate subsection:

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

### Phase 4: Update Timestamp

Update the `last_updated` field in the frontmatter.

---

## Report Format

```markdown
## Self-Improve Report: {COMPONENT}

### Outcome: {OUTCOME}

### Changes to Expertise

**Test Inventory Updated:**
- {added/modified test file}

**Coverage Gaps Updated:**
- {gap resolved or new gap added}

**Learnings Recorded:**

- Pattern: {what worked}
- Avoid: {what to avoid}
- Issue: {problem and fix}
- Tip: {useful observation}

### Expertise Updated

- expertise.md -> {sections modified}
- expertise.md -> last_updated: {new timestamp}
```

---

## Instructions

1. **Run after every significant test session** - Even failed runs have learnings
2. **Be specific** - Record concrete patterns, not vague observations
3. **Include context** - Date, component, and circumstances
4. **Keep it actionable** - Learnings should help future test development
5. **Don't overwrite** - Append to existing learnings, don't replace
6. **Update coverage gaps** - Remove resolved gaps, add new ones discovered
