---
type: expert-file
file-type: expertise
domain: jira
last_updated: "2026-03-02"
tags: [jira, nci-tracker, story-writer, commit-sync, sprint-planning, agile, pat-auth]
---

# Jira Expertise

> Complete mental model for NCI Jira integration — API setup, story preparation patterns, commit-to-issue sync, and sprint planning workflows.

---

## Part 1: NCI Jira Setup

### Connection

- **Host**: `tracker.nci.nih.gov` (self-hosted Jira)
- **Auth**: Bearer PAT (Personal Access Token) — no email/password
- **API**: REST API v2 (`/rest/api/2/`) + Agile API (`/rest/agile/1.0/`)
- **Board**: 1767 (EAGLE project board)
- **Project Key**: `EAGLE`

### Environment Variables

| Var | Purpose | Source |
|-----|---------|--------|
| `JIRA_BASE_URL` | Base URL for Jira API | `.env` |
| `JIRA_API_TOKEN` | Personal Access Token | `.env` |
| `JIRA_WEEKLY_SUMMARY` | Catch-all issue for unmatched commits | `.env` (optional) |

### Auth Pattern

```python
headers = {
    "Authorization": f"Bearer {JIRA_API_TOKEN}",
    "Content-Type": "application/json",
}
```

### Key Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/rest/api/2/myself` | GET | Connection test |
| `/rest/api/2/search` | GET | JQL queries |
| `/rest/api/2/issue/{key}/comment` | POST | Add comment |
| `/rest/api/2/issue` | POST | Create issue |
| `/rest/agile/1.0/board/{id}/issue` | GET | Board issues |

---

## Part 2: Story Preparation Pattern

> Codified from the pattern established in `docs/jira-new-items-20260302.md`.

### Story Format

Each story entry contains these fields:

```markdown
### EAGLE-{N}: {Summary Title}
- **Type**: Story | Task | Bug | Epic
- **Epic**: {Parent epic name}
- **Summary**: {One-line summary}
- **Status**: Done | In Progress | To Do
- **Assignee**: `assignee:{name}`
- **Expert Domain**: `{domain1}`, `{domain2}`
- **PR**: [{repo}#{N}]({url}) (`{branch}`)
- **Commits**: `{sha1}`, `{sha2}`, ...
- **Plan**: `{path to spec/plan file}`
- **Architecture Report**: `{path to arch report}` (if applicable)
- **Description**: {Detailed narrative — what was done, how, why}
- **Acceptance Criteria**:
  - [x] Completed criterion
  - [ ] Open criterion
```

### Field Rules

| Field | Rule |
|-------|------|
| Type | Story for features, Task for ops, Bug for fixes |
| Epic | Group related stories under one epic |
| Expert Domain | Use labels from the 10 expert domains (frontend, backend, aws, strands-sdk, deployment, cloudwatch, eval, git, tac, jira) |
| PR | Link to GitHub PR with branch name |
| Commits | Short SHAs (7-10 chars), comma-separated |
| Plan | Path to `.claude/specs/` plan file |
| Description | Past tense for Done stories, future tense for To Do |
| AC | Checked `[x]` for Done, unchecked `[ ]` for To Do |

### Consolidation Rules

When grouping commits into stories:

1. **Related commits → 1-2 cohesive stories** — Don't create one story per commit
2. **Cite PR links** — Every story references its GitHub PR
3. **Cite spec paths** — Reference `.claude/specs/` plans and `docs/` reports
4. **Include checked/unchecked AC** — Done stories have `[x]`, new stories have `[ ]`
5. **Add expert domain labels** — Multiple domains per story when cross-cutting
6. **Assign priority** — P1 (blockers/bugs), P2 (features), P3 (improvements/spikes)
7. **Estimate effort** — S (< 1 day), M (1-2 days), L (3-5 days)

### Summary Tables

Every story batch document ends with two tables:

#### Completed Today Table

```markdown
| Key | Summary | Status | PR / Commits |
|-----|---------|--------|--------------|
| EAGLE-49 | Migration summary | Done | [PR #5](...) · `sha1` `sha2` |
```

#### Open Priority Table

```markdown
| Priority | Key | Summary | Effort |
|----------|-----|---------|--------|
| P1 | EAGLE-43 | Fix S3 bucket env | S |
| P2 | EAGLE-42 | Session persistence | L |
```

---

## Part 3: Commit-to-Issue Sync

### 3-Phase Matching (from `jira-sync.md`)

| Phase | Method | Tool |
|-------|--------|------|
| Phase 1 | Direct key matching (`EAGLE-XXX` in commit message) | `scripts/jira_commits_sync.py` |
| Phase 2 | Semantic matching (Claude analyzes commit vs issue meaning) | `jira-commit-matcher` skill |
| Phase 3 | Catch-all (unmatched → `JIRA_WEEKLY_SUMMARY` if set) | `scripts/jira_commits_sync.py` |

### Scoring Rubric (from `jira-commit-matcher/SKILL.md`)

#### Issue Complexity Score (1-4)

| Points | Level | Examples |
|--------|-------|---------|
| 1 | Simple | Config change, single-file fix |
| 2 | Moderate | New component, API endpoint |
| 3 | Complex | Multi-file feature, cross-layer change |
| 4 | Major | Architecture refactor, new infrastructure |

#### Commit Scope Score (1-4)

| Points | Level | Examples |
|--------|-------|---------|
| 1 | Trivial | Typo fix, version bump |
| 2 | Small | Single function change, bug fix |
| 3 | Medium | New feature file, refactor module |
| 4 | Large | Multi-file refactor, new system |

### Safety Constraints

- **NEVER create new Jira issues** during sync — only comment on existing ones
- **NEVER touch issues not assigned** to the target user
- **NEVER modify issue status, assignee, or fields** — comments only
- **Read-only in dry-run mode**
- **Strip `Co-Authored-By:` lines** from commit bodies before posting
- **Short SHA only** (first 10 chars) — no full commit URLs

### Jira Comment Format

```
**Commit Linked** (Scope: {score}/4 — {level})
Commit: {short_sha}

{commit_subject}

{commit_body — stripped of Co-Authored-By lines}

*Issue Complexity: {issue_score}/4 — {level}*
*Matched by: Claude semantic analysis — {one-sentence reason}*
```

---

## Part 4: Scripts Reference

### `scripts/jira_connect.py` — API Client

Core CRUD operations for NCI Jira:

| Function | Purpose | Returns |
|----------|---------|---------|
| `test_connection()` | Validate PAT auth | User dict or None |
| `get_projects()` | List accessible projects | List of projects |
| `search_issues(jql)` | JQL search | Search results |
| `add_comment(key, body)` | Add comment to issue | bool |
| `create_issue(project, summary, type, desc)` | Create new issue | Issue key or None |
| `find_issue_by_summary(project, summary)` | Find issue by exact summary match | Issue key or None |
| `fetch_open_issues(project, assignees)` | Fetch non-Done issues | List of dicts |
| `fetch_board_issues(board_id)` | Fetch board issues (Agile API) | List of dicts |
| `dry_run()` | Validate env vars without HTTP | bool |

### `scripts/jira_commits_sync.py` — Phase 1 Direct Matching

- Scans git log for commits with `EAGLE-XXX` keys
- Posts comments to matched issues
- Flags: `--since`, `--project`, `--author`, `--dry-run`, `--weekly-summary`

### `scripts/jira_scan_issues.py` — Data Collection

- Fetches open issues and unmatched commits
- Outputs JSON: `{issues: [...], unmatched_commits: [...]}`
- Flags: `--project`, `--board-id`, `--since`, `--author`

### `scripts/create_git_stories.py` — Batch Story Creation

- Creates stories in Jira from batch definitions
- Uses `create_issue()` and `find_issue_by_summary()` for dedup

---

## Part 5: Jira Sync Modes

The `jira-sync.md` command supports 3 modes:

| Mode | Behavior |
|------|----------|
| `dry-run` | Print match plan — no Jira API writes |
| `live` | Execute for real — post comments to Jira |
| `prepare-stories` | Generate story markdown from commits/PRs |

### `prepare-stories` Mode Workflow

1. Collect commits since SINCE
2. Group by feature/PR branch
3. Use `jira-story-writer` skill to produce formatted story entries
4. Write output to `docs/jira-new-items-{YYYYMMDD}.md`
5. Include both completed (Done) and proposed (new) stories

---

## Part 6: Learnings

### patterns_that_work

- Consolidating 3-4 related commits into 1 cohesive story captures the narrative better than per-commit stories (discovered: 2026-03-02, component: story-preparation)
- Including both checked and unchecked AC in the same document gives sprint planning full context (discovered: 2026-03-02, component: story-format)
- Expert domain labels enable filtering stories by expert area for targeted reviews (discovered: 2026-03-02, component: labeling)
- Priority (P1-P3) + Effort (S/M/L) matrix gives enough granularity for sprint commitment without over-estimating (discovered: 2026-03-02, component: estimation)
- Citing spec paths in stories creates traceability from Jira → plan → implementation (discovered: 2026-03-02, component: traceability)

### patterns_to_avoid

- One story per commit: creates noise, fragments the narrative (reason: commits are incremental, stories are features)
- Missing PR links: makes code review disconnected from sprint tracking (reason: PR is the review artifact)
- Hardcoded issue numbers in story templates: they change per sprint (reason: use `EAGLE-{N}` placeholder)
- Posting commit bodies with `Co-Authored-By:` lines: clutters Jira comments (reason: Jira doesn't need git attribution metadata)

### common_issues

- NCI Jira PAT tokens expire periodically — run `/experts:jira:maintenance` to verify
- `fetch_board_issues` uses Agile API which has different pagination than REST v2 search
- JQL `summary ~ "text"` is a contains operator, not exact match — `find_issue_by_summary()` does client-side exact match after

### tips

- Always strip `Co-Authored-By:` from commit bodies before posting to Jira
- Use short SHA (10 chars) — Jira doesn't render full commit URLs
- Board ID 1767 is the EAGLE board — use `fetch_board_issues(1767)` for board-scoped queries
- Bearer PAT auth requires no email — just the token in `Authorization: Bearer {token}`
