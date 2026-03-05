---
description: "Update CloudWatch expertise with learnings from telemetry work, pipeline changes, or discovered issues"
allowed-tools: Read, Edit, Glob, Grep, Bash
argument-hint: [component] [outcome: success|failed|partial]
---

# CloudWatch Expert - Self-Improve Mode

> Update expertise.md with learnings from CloudWatch telemetry work and pipeline changes.

## Purpose

After modifying the emission pipeline, adding event schemas, updating queries, or debugging CloudWatch issues, run self-improve to:
- Record what worked (patterns_that_work)
- Record what to avoid (patterns_to_avoid)
- Document issues encountered (common_issues)
- Add tips for future CloudWatch development

This is the **LEARN** step in ACT-LEARN-REUSE.

## Usage

```
/experts:cloudwatch:self-improve emission-pipeline success
/experts:cloudwatch:self-improve event-schema-change failed
/experts:cloudwatch:self-improve query-optimization partial
```

## Variables

- `COMPONENT`: $1 (component or area)
- `OUTCOME`: $2 (success | failed | partial)

## Allowed Tools

`Read`, `Edit`, `Glob`, `Grep`, `Bash`

---

## Workflow

### Phase 1: Gather Information

1. Read current `.claude/commands/experts/cloudwatch/expertise.md`
2. Read telemetry results:
   - `trace_logs.json` -- local per-test logs and pass/fail
   - CloudWatch `/eagle/test-runs` -- structured events from recent runs
3. Read git log for recent changes:
   ```bash
   git log --oneline -10
   git diff HEAD~3 --stat
   ```
4. Check test output for CloudWatch-related tests (18, 20)

### Phase 2: Analyze Outcome

Based on OUTCOME:

**success**:
- What made the CloudWatch change successful?
- Any boto3 API patterns worth recording?
- Were there any surprises with eventual consistency?
- Did the emission pipeline handle errors correctly?

**failed**:
- What caused the failure?
- AWS permissions issue? API limits? Schema error?
- What should be avoided next time?
- What needs to happen before retry?

**partial**:
- Which parts worked vs failed?
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

- **Part 2 (Event Schemas)**: If schema fields were added or changed
- **Part 3 (Emission Pipeline)**: If pipeline steps were modified
- **Part 4 (CloudWatch Logs Tool)**: If tool operations were added
- **Part 7 (Known Issues)**: If new issues were discovered

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
- expertise.md -> {other sections if updated}
- expertise.md -> last_updated timestamp
```

---

## Instructions

1. **Run after every significant CloudWatch change** - Even failed attempts have learnings
2. **Be specific** - Record concrete patterns, not vague observations
3. **Include context** - Date, component, and circumstances
4. **Keep it actionable** - Learnings should help future CloudWatch development
5. **Don't overwrite** - Append to existing learnings, don't replace

---

## Data Sources

| Source | Location | Content |
|--------|----------|---------|
| Local logs | `trace_logs.json` | Per-test pass/fail + captured stdout |
| CloudWatch | `/eagle/test-runs` | Structured events per run |
| Git history | `git log` | Recent changes and context |
| Test output | stdout | Live test execution output (tests 18, 20) |
| Expertise | `.claude/commands/experts/cloudwatch/expertise.md` | Current mental model |
