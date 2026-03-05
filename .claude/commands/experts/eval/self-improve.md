---
description: "Update eval expertise with learnings from test runs, new patterns, or discovered issues"
allowed-tools: Read, Edit, Glob, Grep, Bash
argument-hint: [component] [outcome: success|failed|partial]
---

# Eval Expert - Self-Improve Mode

> Update expertise.md with learnings from eval suite runs and test development.

## Purpose

After running the eval suite or adding new tests, run self-improve to:
- Record what worked (patterns_that_work)
- Record what to avoid (patterns_to_avoid)
- Document issues encountered (common_issues)
- Add tips for future test development

This is the **LEARN** step in ACT-LEARN-REUSE.

## Usage

```
/experts:eval:self-improve aws-tool-tests success
/experts:eval:self-improve test-17-dynamodb failed
/experts:eval:self-improve cloudwatch-telemetry partial
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
2. Read test results:
   - `trace_logs.json` — per-test logs and pass/fail
   - CloudWatch `/eagle/test-runs` — structured events
3. Read git log for recent changes:
   ```bash
   git log --oneline -10
   git diff HEAD~3 --stat
   ```
4. Check test output if available

### Phase 2: Analyze Outcome

Based on OUTCOME:

**success**:
- What made the test(s) successful?
- Any patterns worth recording?
- Were there any surprises?
- Which AWS APIs worked well?

**failed**:
- What caused the failure?
- AWS permissions issue? Missing resources?
- What should be avoided next time?
- What needs to happen before retry?

**partial**:
- Which tests passed vs failed?
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
```

---

## Instructions

1. **Run after every significant test session** - Even failed runs have learnings
2. **Be specific** - Record concrete patterns, not vague observations
3. **Include context** - Date, component, and circumstances
4. **Keep it actionable** - Learnings should help future test development
5. **Don't overwrite** - Append to existing learnings, don't replace

---

## Data Sources

| Source | Location | Content |
|--------|----------|---------|
| Local logs | `trace_logs.json` | Per-test pass/fail + captured stdout |
| CloudWatch | `/eagle/test-runs` | Structured events per run |
| Git history | `git log` | Recent changes and context |
| Test output | stdout | Live test execution output |
