---
description: "Update Jira expertise with learnings from sync runs, story batches, or sprint planning"
allowed-tools: Read, Write, Edit, Grep, Glob
argument-hint: [component] [outcome: success|failed|partial]
---

# Jira Expert - Self-Improve Mode

> Update expertise.md with learnings from Jira operations and debugging.

## Purpose

After running Jira syncs, preparing story batches, or planning sprints, run self-improve to:
- Record what worked (patterns_that_work)
- Record what to avoid (patterns_to_avoid)
- Document issues encountered (common_issues)
- Add tips for future Jira work

This is the **LEARN** step in ACT-LEARN-REUSE.

## Usage

```
/experts:jira:self-improve story-preparation success
/experts:jira:self-improve commit-sync failed
/experts:jira:self-improve sprint-planning partial
```

## Variables

- `COMPONENT`: $1 (component or area changed)
- `OUTCOME`: $2 (success | failed | partial)

## Allowed Tools

`Read`, `Write`, `Edit`, `Grep`, `Glob`

---

## Workflow

### Phase 1: Gather Information

1. Read current `.claude/commands/experts/jira/expertise.md`
2. Read recent changes:
   - Check for new story documents:
     ```bash
     ls -la docs/jira-new-items-*.md
     ```
   - Git log for recent commits:
     ```bash
     git log --oneline -10
     git diff HEAD~3 --stat
     ```
3. Check for any sync run outputs or error logs

### Phase 2: Analyze Outcome

Based on OUTCOME:

**success**:
- What Jira pattern made the operation successful?
- Any new API behaviors discovered?
- Did story consolidation work well?
- Were effort estimates accurate?

**failed**:
- What caused the failure?
- PAT expired? API rate limit? JQL error?
- What should be avoided next time?
- What needs to happen before retry?

**partial**:
- What worked vs. what didn't?
- Were some stories well-formed but others missing fields?
- Are there API limitations encountered?
- Were commits hard to consolidate into stories?

### Phase 3: Update expertise.md

#### Update `Learnings` section (Part 6):

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

- **Part 1** (Setup): If API behaviors were clarified
- **Part 2** (Story Pattern): If format was refined
- **Part 3** (Commit Sync): If matching rules were improved
- **Part 4** (Scripts): If script behaviors were documented
- **Part 5** (Sync Modes): If mode behavior was clarified

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

- expertise.md → Learnings section (Part 6)
- expertise.md → last_updated timestamp
- expertise.md → {other sections if changed}
```

---

## Instructions

1. **Run after every significant Jira operation** — Even failed syncs have learnings
2. **Be specific** — Record concrete API behaviors, not vague observations
3. **Include context** — Date, component, and circumstances
4. **Keep it actionable** — Learnings should help future Jira work
5. **Don't overwrite** — Append to existing learnings, don't replace
6. **Track API quirks** — NCI Jira may behave differently from cloud Jira

---

## Data Sources

| Source | Location | Content |
|--------|----------|---------|
| Expertise | `.claude/commands/experts/jira/expertise.md` | Current mental model |
| Story exemplar | `docs/jira-new-items-*.md` | Past story batches |
| Commit matcher | `.claude/skills/jira-commit-matcher/SKILL.md` | Scoring rubric |
| Story writer | `.claude/skills/jira-story-writer/SKILL.md` | Story generation |
| Scripts | `scripts/jira_*.py` | API client and sync tools |
| Git history | `git log` | Recent changes and context |
