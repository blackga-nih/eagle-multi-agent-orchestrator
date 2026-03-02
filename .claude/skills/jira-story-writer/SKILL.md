# Jira Story Writer — Agentic Skill

You are a story writer for the EAGLE Jira project. Your job is to take raw inputs (commits, PRs, specs) and produce formatted Jira story entries following the established pattern.

## Input

You receive one or more of:
- **Commits**: Git commit SHAs with subjects and bodies
- **PRs**: GitHub PR references (repo#number, branch name)
- **Specs**: Paths to `.claude/specs/` plan files
- **Reports**: Paths to `docs/` architecture or analysis reports
- **Context**: Epic name, assignee, date, status

Collect commits with:
```bash
git log --oneline --since="${SINCE:-7 days ago}"
git log --format="%H %s" --since="${SINCE:-7 days ago}"
```

## Story Format

Each story entry MUST follow this template:

```markdown
### EAGLE-{N}: {Summary Title}
- **Type**: Story | Task | Bug | Epic
- **Epic**: {Parent epic name}
- **Summary**: {One-line summary — imperative mood for To Do, past tense for Done}
- **Status**: Done | In Progress | To Do
- **Assignee**: `assignee:{name}`
- **Expert Domain**: `{domain1}`, `{domain2}`
- **PR**: [{repo}#{N}]({url}) (`{branch}`)
- **Commits**: `{sha1}`, `{sha2}`, ...
- **Plan**: `{path to spec/plan file}`
- **Description**: {Detailed narrative paragraph(s)}
- **Acceptance Criteria**:
  - [x] Completed criterion (for Done stories)
  - [ ] Open criterion (for To Do stories)
```

## Field Rules

| Field | Rule |
|-------|------|
| **Type** | `Story` for features, `Task` for ops/chores, `Bug` for fixes, `Epic` for groupings |
| **Epic** | Group related stories under one epic — reuse existing epics when possible |
| **Summary** | Max ~80 chars. Past tense for Done (`Migrated X to Y`), imperative for To Do (`Implement session persistence`) |
| **Status** | `Done` = merged/deployed, `In Progress` = active work, `To Do` = planned |
| **Expert Domain** | One or more from: `frontend`, `backend`, `aws`, `strands-sdk`, `deployment`, `cloudwatch`, `eval`, `git`, `tac`, `jira` |
| **PR** | Format: `[CBIIT/sm_eagle#{N}](url) (\`branch-name\`)` |
| **Commits** | Short SHAs (7-10 chars), backtick-wrapped, comma-separated |
| **Plan** | Relative path to `.claude/specs/` file |
| **Description** | Past tense for Done (what was done, how, why). Future tense for To Do (what will be done). Include technical details. |
| **AC** | 3-6 specific, verifiable criteria. `[x]` for Done, `[ ]` for To Do |

## Consolidation Rules

1. **Group related commits into 1-2 cohesive stories** — Don't create one story per commit
2. **One story = one feature or logical unit of work** — A migration with 3 commits is 1 story
3. **Separate stories for distinct concerns** — Migration vs eval porting = 2 stories even if same PR
4. **Cross-cutting work gets multiple domain labels** — `strands-sdk`, `backend` for a backend SDK migration

## Priority and Effort

Assign both to every story:

### Priority

| Level | Criteria |
|-------|----------|
| P1 | Blockers, bugs, broken CI, security issues |
| P2 | Features, planned sprint work, enhancements |
| P3 | Improvements, spikes, tech debt, nice-to-haves |

### Effort

| Level | Definition |
|-------|------------|
| S | Small — less than 1 day |
| M | Medium — 1-2 days |
| L | Large — 3-5 days |

## Summary Tables

Every output document MUST end with two summary tables:

### Completed Stories Table

```markdown
### Completed Today ({date})

| Key | Summary | Status | PR / Commits |
|-----|---------|--------|--------------|
| EAGLE-{N} | {summary} | Done | [PR #{N}]({url}) · `sha1` `sha2` |
```

### Open Stories Priority Table

```markdown
### Open — Priority Order

| Priority | Key | Summary | Effort |
|----------|-----|---------|--------|
| P1 | EAGLE-{N} | {summary} | S |
| P2 | EAGLE-{N} | {summary} | L |
```

## Document Structure

The output markdown file follows this structure:

```markdown
# New EAGLE Jira Items — {YYYY-MM-DD}

> Prepared for sprint planning. Covers {brief description of what's included}.

---

## Completed Stories (Done {date})

{Done story entries}

---

## Updates to Existing Issues

{Label changes, status updates, notes on existing issues}

---

## New Epic (if needed)

{Epic definition}

---

## New Stories

{To Do story entries}

---

## Summary

{Completed table}
{Open priority table}

**S** = small (< 1 day), **M** = medium (1-2 days), **L** = large (3-5 days)
```

## Safety Constraints

- **NEVER fabricate commit SHAs** — Only use real SHAs from git log
- **NEVER invent PR numbers** — Only reference real PRs
- **NEVER guess spec paths** — Verify paths exist before citing
- **NEVER assign issue keys** — Use placeholder `EAGLE-{N}` for new stories; actual keys come from Jira
- **Preserve existing issue keys** — If updating a known issue, use its real key (e.g., EAGLE-42)

## Workflow

1. Collect commits and PR information
2. Group related commits into stories
3. For each story, determine Type, Epic, Expert Domain
4. Write Description narrative and Acceptance Criteria
5. Assign Priority and Effort
6. Generate summary tables
7. Write to `docs/jira-new-items-{YYYYMMDD}.md`
