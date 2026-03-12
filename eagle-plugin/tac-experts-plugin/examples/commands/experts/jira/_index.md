---
type: expert-file
file-type: index
domain: jira
tags: [expert, jira, sprint-planning, story-writer, commit-sync, nci-tracker, agile]
---

# Jira Expert

> Jira specialist for NCI tracker integration, story preparation from commits/PRs, sprint planning, commit-to-issue sync, and agile workflow automation.

## Domain Scope

This expert covers:
- **NCI Jira Setup** — tracker.nci.nih.gov, Bearer PAT auth, REST API v2, board 1767
- **Story Preparation** — Consolidating commits into cohesive stories with AC, expert domain labels, priority/effort
- **Commit-to-Issue Sync** — 3-phase matching (direct key, semantic, catch-all) via `jira-sync.md`
- **Sprint Planning** — Preparing story batches, priority ordering, effort estimation
- **Story Format** — Type, Epic, Summary, Status, Assignee, Expert Domain, PR links, Commit SHAs, Plan/Spec paths, Description, Acceptance Criteria
- **Scripts** — `jira_connect.py`, `jira_commits_sync.py`, `jira_scan_issues.py`, `create_git_stories.py`
- **Skills** — `jira-commit-matcher` (scoring rubric), `jira-story-writer` (story generation)

## Available Commands

| Command | Purpose |
|---------|---------|
| `/experts:jira:question` | Answer Jira questions without making changes |
| `/experts:jira:plan` | Plan Jira operations — story prep, sprint planning, sync runs |
| `/experts:jira:self-improve` | Update expertise after Jira sync runs or story batches |
| `/experts:jira:plan_build_improve` | Full ACT-LEARN-REUSE workflow for Jira tasks |
| `/experts:jira:maintenance` | Check Jira connectivity, validate PAT, list open issues |

## Key Files

| File | Purpose |
|------|---------|
| `expertise.md` | Complete mental model for Jira integration |
| `question.md` | Query command for read-only questions |
| `plan.md` | Planning command for Jira operations |
| `self-improve.md` | Expertise update command |
| `plan_build_improve.md` | Full workflow command |
| `maintenance.md` | Connectivity and health check command |

## Architecture

```
NCI Jira (tracker.nci.nih.gov)
  |
  |-- REST API v2 (Bearer PAT auth)
  |     |-- /rest/api/2/myself (connection test)
  |     |-- /rest/api/2/search (JQL queries)
  |     |-- /rest/api/2/issue/{key}/comment (add comments)
  |     |-- /rest/api/2/issue (create issues)
  |     |-- /rest/agile/1.0/board/{id}/issue (board issues)
  |
  |-- scripts/jira_connect.py
  |     |-- add_comment(), search_issues(), create_issue()
  |     |-- fetch_open_issues(), fetch_board_issues()
  |     |-- find_issue_by_summary(), test_connection()
  |
  |-- scripts/jira_commits_sync.py (Phase 1 — direct key matching)
  |-- scripts/jira_scan_issues.py (data collection for semantic matching)
  |-- scripts/create_git_stories.py (batch story creation)
  |
  |-- .claude/commands/jira-sync.md (3-mode agentic command)
  |     |-- dry-run: print match plan
  |     |-- live: post comments to Jira
  |     |-- prepare-stories: generate story markdown from commits
  |
  |-- .claude/skills/
        |-- jira-commit-matcher/SKILL.md (scoring rubric, matching rules)
        |-- jira-story-writer/SKILL.md (story generation from commits/PRs)
```

## Key Source Files

| File | Content |
|------|---------|
| `scripts/jira_connect.py` | Jira API client — PAT auth, CRUD operations |
| `scripts/jira_commits_sync.py` | Phase 1 direct key matching |
| `scripts/jira_scan_issues.py` | Data collection for semantic matching |
| `scripts/create_git_stories.py` | Batch story creation |
| `.claude/commands/jira-sync.md` | 3-mode agentic commit matcher |
| `.claude/skills/jira-commit-matcher/SKILL.md` | Semantic matching scoring rubric |
| `.claude/skills/jira-story-writer/SKILL.md` | Story generation skill |
| `docs/jira-new-items-*.md` | Story exemplars and sprint planning docs |

## ACT-LEARN-REUSE Pattern

```
ACT    ->  Prepare stories, sync commits, plan sprints using Jira patterns
LEARN  ->  Update expertise.md with Jira API behaviors, story patterns, sync results
REUSE  ->  Apply patterns to future story batches and sprint planning
```
