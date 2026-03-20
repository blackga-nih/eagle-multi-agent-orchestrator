---
description: "Pre-flight, push, trigger CI pipeline, monitor GH Actions run, Jira sync, and report — the single command to ship"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Agent, Skill
argument-hint: "--full | --mini [--skip-jira] [--dry-run]"
---

# /ship — Deploy Orchestrator

Pre-flight locally, push, trigger the CI pipeline, monitor the GH Actions run, sync Jira, and report. This is the single command to go from local changes to deployed.

**Architecture**: `/ship` is the trigger + monitor. `deploy.yml` is the executor. No duplicate validation — CI is the source of truth for the full ladder (L1-L6) + deploy + Teams notification.

## Variables

- `FLAGS`: $ARGUMENTS
- `TIMESTAMP`: current datetime (run `date +"%Y-%m-%d_%H-%M-%S"`)
- `COMMIT_SHA`: current HEAD SHA

## Instructions

You are a deploy orchestrator. Parse flags, run a fast local pre-flight, push to trigger CI, monitor the GH Actions run, sync Jira, and give the user a final report. You do NOT write application code.

Parse `FLAGS` to determine mode and options:

| Flag | Effect |
|------|--------|
| (empty) or `--full` | **Full mode** — CI runs L1-L6 + deploy |
| `--mini` | **Mini mode** — CI runs L1 lint only + deploy |
| `--skip-jira` | Skip Jira analysis and sync |
| `--dry-run` | Local pre-flight only — no push, no CI trigger, no Jira |

---

## Workflow

### Step 0: Setup + Detect Changes

1. Get timestamp and commit SHA
2. Run `git status` and `git diff --name-only` to classify changes:
   - **Backend**: `server/app/**`, `server/tests/**`, `eagle-plugin/**`
   - **Frontend**: `client/components/**`, `client/hooks/**`, `client/lib/**`, `client/app/api/**`
   - **Infra**: `infrastructure/**`, `deployment/**`
   - **Docs/Config**: `docs/**`, `*.md`, `.claude/**`, `*.yml`
3. Determine deploy mode from flags (default: `--full`)
4. Show the user what changed and what mode will be used

### Step 1: Local Pre-flight (fast gate)

Run lint locally as a fast sanity check before pushing. This catches obvious errors before consuming CI minutes:

```
/test --lint
```

If lint FAILS, **STOP** and report — do not push broken code. Help the user fix the issues first.

### Step 2: Jira Analysis (unless --skip-jira)

Invoke the **jira-commit-matcher** skill to match recent commits to open Jira issues:

```
/jira-commit-matcher
```

Also run the review analysis for transition suggestions:

```bash
python scripts/jira_review_analysis.py --since "7 days ago" --json 2>&1
```

- Parse the JSON output for issue matches and suggested transitions
- Present suggestions to the user and **wait for approval** before applying any transitions
- Collect the Jira summary (issue keys + actions) for the PR body
- If Jira env vars are not set, skip gracefully and note in report

### Step 3: Commit + Push

If there are uncommitted changes:

1. Stage relevant files (not `.env`, credentials, or large binaries)
2. Commit with a descriptive message including `Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>`

Then push:

```bash
git push -u origin $(git rev-parse --abbrev-ref HEAD)
```

### Step 4: Create PR with Report Card Stub

Create a PR that will be updated with CI results:

```bash
gh pr create --title "chore(ship): deploy {TIMESTAMP}" --body "$(cat <<'EOF'
## Deploy Report Card — {FULL|MINI}
**Commit**: {SHA} | **Branch**: {branch} | **Date**: {TIMESTAMP}

### Pre-flight
- L1 Lint: PASS (local)

### CI Pipeline
Waiting for GH Actions run...

### Jira Issues
| Key | Action |
|-----|--------|
{jira results from Step 2, or "No Jira issues matched"}

### Changes
{git diff --stat output}
EOF
)"
```

### Step 5: Trigger CI Pipeline

If the push to main already triggered `deploy.yml`, find the run. Otherwise trigger via `workflow_dispatch`:

```bash
# Check if a run was already triggered by the push
gh run list --workflow=deploy.yml --limit=1 --json databaseId,status,headSha

# If no run for this SHA, trigger manually with the deploy mode
gh workflow run deploy.yml -f deploy_mode={full|mini} -f deploy_infra=true -f deploy_app=true
```

Capture the **run ID** for monitoring.

### Step 6: Monitor CI Run

Poll the GH Actions run until it completes. Report progress at each major milestone:

```bash
gh run view {RUN_ID} --json status,conclusion,jobs
```

Print status updates as jobs complete:
```
CI Pipeline — {RUN_URL}
  changes:       done (2s)
  lint:          done (45s) — PASS
  unit-tests:    running...
  cdk-synth:     running...
  integration:   pending
  eval:          pending
  deploy-infra:  pending
  deploy-backend: pending
  deploy-frontend: pending
  report:        pending
```

Use `gh run watch {RUN_ID}` if available, or poll with `gh run view` every 30 seconds.

### Step 7: Update PR with CI Results

Once the CI run completes, fetch the results and update the PR body:

```bash
# Get job results
gh run view {RUN_ID} --json jobs --jq '.jobs[] | {name, conclusion}'
```

Update the PR body with the full report card:

```bash
gh pr edit {PR_NUMBER} --body "$(cat <<'EOF'
## Deploy Report Card — {FULL|MINI}
**Commit**: {SHA} | **Branch**: {branch} | **Date**: {TIMESTAMP}
**CI Run**: {RUN_URL}

### Validation Ladder
| Level | Check | Status | Detail |
|-------|-------|--------|--------|
| L1 | Lint | {from CI} | {from CI} |
| L2 | Unit Tests | {from CI} | {from CI} |
| L4 | CDK Synth | {from CI} | |
| L5 | Integration | {from CI} | |
| L6 | Eval | {from CI} | {from CI} |

### Deploy
| Component | Status |
|-----------|--------|
| Infrastructure | {from CI} |
| Backend | {from CI} |
| Frontend | {from CI} |

### Jira Issues
{from Step 2}

### Changes
{git diff --stat}
EOF
)"
```

### Step 8: Jira Sync (unless --skip-jira)

After the CI run succeeds, sync commits to Jira:

```
/jira-sync
```

### Step 9: Print Summary

```
Ship Complete
=============
Mode:       {full|mini}
Commit:     {SHA}
Branch:     {branch}

Pre-flight: L1 Lint PASS (local)

CI Pipeline: {RUN_URL}
  L1 Lint:       {result}
  L2 Tests:      {result}
  L4 CDK:        {result}
  L5 Integration:{result}
  L6 Eval:       {result}
  Deploy Infra:  {result}
  Deploy Backend:{result}
  Deploy Frontend:{result}
  Teams Report:  {result}

PR:         {PR_URL}
Jira:       {N} issues updated
```

If any CI job failed, highlight the failure and suggest next steps (e.g., "L2 unit tests failed — run `/test --full` locally to debug").

---

## Dry Run Mode

When `--dry-run` is set:
- Run local pre-flight (lint) — still validates
- Run Jira analysis (read-only, no transitions)
- Print what WOULD be pushed, PR'd, and triggered
- Do NOT push, create PR, trigger CI, or sync Jira

---

## Examples

```bash
/ship                        # Full: pre-flight → push → CI (L1-L6+deploy) → Jira → report
/ship --mini                 # Mini: pre-flight → push → CI (L1+deploy) → Jira → report
/ship --skip-jira            # Skip Jira analysis and sync
/ship --dry-run              # Local lint + Jira analysis, no push or CI
/ship --mini --dry-run       # Quick lint check, no side effects
```
