---
description: "Update backend expertise with learnings from implementations, debugging, or architecture changes"
allowed-tools: Read, Write, Edit, Grep, Glob
argument-hint: [component] [outcome: success|failed|partial]
---

# Backend Expert - Self-Improve Mode

> Update expertise.md with learnings from backend development and debugging.

## Purpose

After implementing backend changes or debugging issues, run self-improve to:
- Record what worked (patterns_that_work)
- Record what to avoid (patterns_to_avoid)
- Document issues encountered (common_issues)
- Add tips for future backend development

This is the **LEARN** step in ACT-LEARN-REUSE.

## Usage

```
/experts:backend:self-improve tool-handler success
/experts:backend:self-improve document-generation failed
/experts:backend:self-improve tenant-scoping partial
```

## Variables

- `COMPONENT`: $1 (component or area changed)
- `OUTCOME`: $2 (success | failed | partial)

## Allowed Tools

`Read`, `Write`, `Edit`, `Grep`, `Glob`

---

## Workflow

### Phase 1: Gather Information

1. Read current `.claude/commands/experts/backend/expertise.md`
2. Read recent changes:
   - `server/app/agentic_service.py` — check modified sections
   - Git log for recent commits:
     ```bash
     git log --oneline -10
     git diff HEAD~3 --stat
     ```
3. Check for any test results in `trace_logs.json`

### Phase 2: Analyze Outcome

Based on OUTCOME:

**success**:
- What made the implementation successful?
- Any patterns worth recording?
- Were there any surprises with AWS APIs?
- Did tenant scoping work correctly?

**failed**:
- What caused the failure?
- AWS permissions? Missing resources? Type errors?
- What should be avoided next time?
- What needs to happen before retry?

**partial**:
- What worked vs. what didn't?
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

- **Part 3** (AWS Tool Handlers): If handler params or return shapes changed
- **Part 5** (Document Generation): If new doc types were added
- **Part 7** (Known Issues): If new issues or patterns were discovered
- **Line numbers**: If code changes shifted line numbers

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
- expertise.md -> {other sections if changed}
```

---

## Instructions

1. **Run after every significant backend change** - Even failed attempts have learnings
2. **Be specific** - Record concrete patterns, not vague observations
3. **Include context** - Date, component, and circumstances
4. **Keep it actionable** - Learnings should help future backend development
5. **Don't overwrite** - Append to existing learnings, don't replace
6. **Update line numbers** - If code shifts, update Part references in expertise.md

---

## Data Sources

| Source | Location | Content |
|--------|----------|---------|
| Backend code | `server/app/agentic_service.py` | Handler implementations, dispatch |
| Test results | `trace_logs.json` | Tool test pass/fail data |
| Git history | `git log` | Recent changes and context |
| Expertise | `.claude/commands/experts/backend/expertise.md` | Current mental model |
