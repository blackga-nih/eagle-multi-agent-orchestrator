---
description: "Plan Jira operations — story preparation, sprint planning, sync runs, batch creation"
allowed-tools: Read, Write, Glob, Grep, Bash
argument-hint: [operation description or Jira task to plan]
---

# Jira Expert - Plan Mode

> Create detailed plans for Jira operations informed by expertise.

## Purpose

Generate a plan for preparing stories, planning sprints, running commit syncs, or batch-creating issues, using:
- Expertise from `.claude/commands/experts/jira/expertise.md`
- Story patterns from `docs/jira-new-items-*.md`
- Current git history and branch state
- Scoring rubric from `jira-commit-matcher` skill

## Usage

```
/experts:jira:plan [operation description]
```

## Variables

- `TASK`: $ARGUMENTS

## Allowed Tools

`Read`, `Write`, `Glob`, `Grep`, `Bash`

---

## Workflow

### Phase 1: Load Context

1. Read `.claude/commands/experts/jira/expertise.md` for:
   - NCI Jira setup (Part 1)
   - Story preparation pattern (Part 2)
   - Commit-to-issue sync (Part 3)
   - Scripts reference (Part 4)
   - Sync modes (Part 5)
   - Learnings (Part 6)

2. Gather current state:
   ```bash
   git log --oneline -20
   git branch --show-current
   git log --oneline --since="7 days ago"
   ```

3. Check for existing story docs:
   ```bash
   ls -la docs/jira-new-items-*.md 2>/dev/null
   ```

4. Understand the TASK:
   - Is this story preparation from commits?
   - Is it a commit sync run?
   - Is it sprint planning?
   - Is it batch issue creation?

### Phase 2: Analyze Current State

1. For story preparation:
   - Identify commits to consolidate
   - Find related PRs and branches
   - Locate spec/plan files to cite
   - Determine expert domain labels

2. For commit sync:
   - Count unsynced commits
   - Check which have `EAGLE-XXX` keys
   - Identify semantic matching candidates

3. For sprint planning:
   - List open issues and their priorities
   - Estimate effort for each
   - Group by epic

### Phase 3: Generate Plan

Create a plan document:

```markdown
# Jira Operation Plan: {TASK}

## Overview
- Operation Type: Story Prep | Commit Sync | Sprint Plan | Batch Create
- Commits: {count} commits since {date}
- Stories: {count} stories to prepare
- Mode: dry-run | live | prepare-stories

## Stories to Prepare

| # | Summary | Type | Expert Domain | Priority | Effort |
|---|---------|------|---------------|----------|--------|
| 1 | {summary} | Story | {domains} | P{N} | {S/M/L} |

## Commits Covered

| SHA | Subject | Story # |
|-----|---------|---------|
| {sha} | {subject} | {story number} |

## Specs/Plans Referenced

| Path | Content |
|------|---------|
| {path} | {description} |

## Output

- File: `docs/jira-new-items-{YYYYMMDD}.md`
- Format: Standard story template from expertise.md Part 2
- Includes: Summary tables (completed + open)

## Validation

1. All commits accounted for (grouped or explicitly skipped)
2. Every story has Type, Epic, Summary, Expert Domain, AC
3. Summary tables are complete
4. No orphaned commits
```

### Phase 4: Save Plan

1. Write plan to `.claude/specs/` following naming convention
2. Report plan summary to user

---

## Instructions

1. **Always read expertise.md first** — Contains all story patterns and conventions
2. **Consolidate commits** — Group related commits into 1-2 stories, not one-per-commit
3. **Cite references** — Every story should link to PRs, specs, and reports
4. **Include AC** — Checked for Done stories, unchecked for To Do
5. **Assign domains** — Use the 10 expert domain labels
6. **Estimate effort** — S/M/L based on scope, not duration

---

## Output Location

Plans are saved to: `.claude/specs/jira-{operation}.md`
