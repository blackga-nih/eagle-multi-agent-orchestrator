---
description: "Are we on track? Comprehensive project health check — scans Jira, git history, branch status against MVP milestones. Trigger keywords: on track, project status, MVP gap, health check."
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Agent
argument-hint: [full|light] (default: light)
model: opus
---

# On-Track — Project Health Check

> Scan Jira, meeting transcripts, git history, and branch status. Compare against MVP milestones. Produce a gap analysis with prioritized actions.

## Variables

- `MODE`: $1 (full | light — default: light)
- `JIRA_BASE_URL`: from `.env` or `https://tracker.nci.nih.gov`
- `JIRA_API_TOKEN`: from `.env` or from `C:/Users/blackga/Desktop/eagle/eagle-multi-agent-orchestrator/.env`
- `REPORT_DIR`: `docs/development/`
- `TRANSCRIPT_DIR`: `docs/development/meeting-transcripts/`

## MVP Milestone Definitions

### MVP-0 (Foundation) — COMPLETE
- AWS account, CDK stacks deployed (Core, Compute, Storage, CiCd)
- ECS Fargate backend running FastAPI
- Next.js frontend on localhost
- Cognito auth (dev mode bypass)
- Basic chat with Bedrock model
- DynamoDB single-table for sessions

### MVP-1 (Acquisition Package Core) — CURRENT TARGET
- **Working agent chat** hitting Knowledge Base consistently
- **Decision tree / compliance matrix** for acquisition routing
- **Document generation**: SOW, IGCE, AP (from templates)
- **Template-faithful export** (Word .docx matching NCI forms)
- **User confirmation checkpoint** before doc generation
- **"Three walls of the box"**: budget ceiling, timeline, must-haves captured before generation
- **Specialist routing**: correct agents invoked per acquisition type
- **Session persistence**: multi-turn context preserved
- **Feedback capture**: in-app feedback with chat snapshot
- **Stage environment**: KB access working

### MVP-2 (Workflow & Handoff) — FUTURE
- Acquisition package lifecycle (Draft → Submitted → Accepted → Returned)
- CO session handoff (fork/transfer)
- Acquisition list UI with status indicators
- Per-acquisition cost tracking
- Risk-trigger-based agent routing
- Teams integration for CO notification

---

## Workflow

### Phase 1: Data Collection

Launch these in parallel:

#### 1a. Jira Board Scan
```bash
JIRA_BASE_URL=https://tracker.nci.nih.gov \
JIRA_API_TOKEN=$(grep JIRA_API_TOKEN C:/Users/blackga/Desktop/eagle/eagle-multi-agent-orchestrator/.env | cut -d= -f2) \
python scripts/jira_scan_issues.py --dry-run --project EAGLE --assignees "" --since "30 days ago"
```
Also fetch all open issues:
```python
from scripts.jira_connect import fetch_open_issues
issues = fetch_open_issues('EAGLE')
```
Categorize each issue by MVP tier (0/1/2) based on description and labels.

#### 1b. Meeting Transcript Scan
- Glob `docs/development/meeting-transcripts/*/summaries/SUMMARY-*.md`
- Read the 3 most recent summaries
- Extract: action items, decisions, risks, MVP scope discussions

#### 1c. Git Status
- `git log --oneline --all --since="14 days ago" --format="%h %an %ad %s" --date=short`
- `git branch -a --sort=-committerdate | head -10`
- `git diff --stat main...HEAD` (current branch divergence)
- Count: commits this week, PRs merged, branches active

#### 1d. Branch Divergence (FULL mode only)
- For each active branch: `git diff --stat main...{branch}`
- Identify overlap/conflict zones
- Map branch changes to Jira issues

#### 1e. Backend Health Check
```bash
curl -s http://localhost:8000/api/health | python -m json.tool
```
Check: model, services connected, tools available, KB accessible.

#### 1f. Frontend Page Inventory (FULL mode only)
- Count pages, API routes
- Check if chat page loads
- Verify tool cards render

---

### Phase 2: Analysis

#### 2a. MVP-1 Gap Analysis
For each MVP-1 requirement, determine status:
- **DONE**: Merged to main, tested, working
- **IN PROGRESS**: On a branch, partially working
- **BLOCKED**: Dependencies or issues preventing progress
- **NOT STARTED**: No commits or branches touch this

Cross-reference against:
- Jira issues (which ones map to MVP-1?)
- Meeting action items (what was promised?)
- Git commits (what was actually built?)

#### 2b. Drift Detection
- What work was done that ISN'T on the MVP-1 list? (scope creep)
- What MVP-1 items have zero commits? (neglected)
- Are meeting action items being completed?

#### 2c. Risk Assessment
- Stale branches (>7 days without commit)
- Merge conflicts brewing (overlap matrix)
- AWS credential/infrastructure issues
- Missing test coverage for new features

---

### Phase 3: Report Generation

#### LIGHT mode output
Print directly to console — no file written:
```
## EAGLE Project Health Check — {date}

### MVP-1 Status: {X}/{total} requirements met

| # | MVP-1 Requirement | Status | Evidence |
|---|-------------------|--------|----------|
| 1 | Working agent chat + KB | DONE/IN PROGRESS/BLOCKED | commit/branch/issue |
...

### Top 5 Priorities
1. {highest priority item}
...

### Drift Alert
- {items worked on outside MVP-1 scope}

### Blockers
- {active blockers}
```

#### FULL mode output
Write a formal report to `docs/development/YYYYMMDD-HHMMSS-report-on-track-v1.md`:

```markdown
# EAGLE Project Health Check

**Date**: {date}
**Mode**: Full
**Branch**: {current branch}
**Sprint**: MVP-1

## Executive Summary
{2-3 sentences: are we on track? what's the biggest gap?}

## MVP-1 Scorecard
| # | Requirement | Status | Jira | Branch | Last Activity |
...

## Jira Board Status
| Key | Summary | Status | MVP Tier | Mapped Commits |
...

## Meeting Action Items Tracker
| Action Item | Owner | Meeting Date | Status | Evidence |
...

## Git Activity (Last 14 Days)
| Date | Author | Commits | Areas |
...

## Branch Divergence
{overlap matrix from divergence audit}

## Drift Analysis
{work done outside MVP-1 scope}

## Risk Register
| Risk | Severity | Mitigation |
...

## Recommended Priority Stack
1. {P0 — must do this week}
2. {P1 — should do this week}
3. {P2 — next week}
...

## Action Plan
- [ ] {specific next steps with owners}
```

---

## Instructions

1. **Always run Jira scan** — even if token fails, report what we know from git
2. **Cross-reference everything** — a Jira issue with no commits = gap; a commit with no issue = drift
3. **Be honest about status** — don't mark DONE unless it's merged and tested
4. **Prioritize MVP-1** — anything outside MVP-1 scope is drift (not necessarily bad, but flag it)
5. **LIGHT mode is fast** — no file writes, no subagents, just console output (~30 seconds)
6. **FULL mode is thorough** — subagents for parallel data collection, formal report (~3 minutes)
