# EAGLE Deployment Guide — Quick Reference Memo

**Date**: 2026-03-27
**From**: Greg
**Re**: How to deploy EAGLE (what's working)

---

## How We've Been Deploying (Verified from AWS)

**All recent deploys go through GitHub Actions** — not local `just deploy`. Evidence:
- Every ECR image is tagged with a git commit SHA (GitHub Actions injects `github.sha`)
- 20 deploy runs in the last 3 days (mix of `push` to main and `workflow_dispatch`)
- Last successful deploy: **today (Mar 27, 12:23 PM)** to both dev and QA
- No local-only `:latest` pushes in ECR history

**How it works:**

| Target | Trigger | How |
|--------|---------|-----|
| **Dev** | Automatic | Push/merge to `main` |
| **QA** | Manual only | `workflow_dispatch` — select `qa` environment, pick any branch |

There is **no automatic deploy to QA**. QA deploys are always manual — you choose the branch and trigger it via GitHub UI or `gh` CLI.

---

## Prerequisites

Before deploying, make sure you have:

1. **GitHub repo access** — push access to `CBIIT/sm_eagle` (for merge-to-main deploys)
2. **`gh` CLI installed** — for triggering workflow_dispatch from terminal (optional but recommended)
3. **AWS SSO configured** — profile `eagle` pointing to `NCIAWSPowerUserAccess` in account `695681773636` (for `just status` / `just logs` only)

## Deploying to Dev

### Merge to `main` (automatic — this is what we do)

Merge your PR to `main`. GitHub Actions automatically:
1. Detects which paths changed (server/, client/, infrastructure/)
2. Runs the validation ladder (lint, tests, CDK synth, integration, eval)
3. Builds Docker images and pushes to ECR (tagged with git SHA)
4. Updates ECS services with force-new-deployment
5. Waits for service stabilization
6. Sends a Teams notification with results

**Nothing to do manually** — just merge and watch the Actions tab.

### Workflow Dispatch to Dev (deploy any branch without merging)

```bash
# From CLI
gh workflow run deploy.yml -f environment=dev -f deploy_mode=mini

# Watch the run
gh run watch
```

Or: GitHub Actions tab > "Deploy EAGLE Platform" > "Run workflow" > select `dev`.

## Deploying to QA

**QA is manual only.** There is no automatic trigger — you must use workflow_dispatch.

### From the CLI (recommended)

```bash
# Deploy current branch to QA
gh workflow run deploy.yml --ref dev-greg-20260324 -f environment=qa

# Deploy main to QA
gh workflow run deploy.yml --ref main -f environment=qa

# Watch the run
gh run watch
```

### From GitHub UI

1. Go to **Actions** tab > **"Deploy EAGLE Platform"** workflow
2. Click **"Run workflow"**
3. Select the **branch** you want to deploy
4. Set **environment** = `qa`
5. Click **"Run workflow"**

### QA deploy behavior

- QA **always runs in mini mode** — lint only, skips unit tests, CDK synth, integration, and eval
- Assumption: code was already validated on dev before promoting to QA
- QA uses a separate VPC, ECS cluster (`eagle-qa`), ECR repos (`eagle-backend-qa`, `eagle-frontend-qa`), and ALB
- Concurrency group is scoped per-environment, so dev and QA deploys don't block each other

## Checking Status

```bash
# Dev environment
just status               # ECS service health + ALB URLs
just urls                 # Just the ALB DNS names
just logs                 # CloudWatch logs (backend, last 30 min)
just logs frontend        # Frontend logs

# QA environment
just status-qa            # QA service health
just urls-qa              # QA ALB URLs
just logs-qa              # QA backend logs
just logs-qa frontend     # QA frontend logs

# GitHub Actions
gh run list --workflow deploy.yml --limit 10   # Recent deploy runs
gh run view                                     # Details of latest run
```

## Local Deploy (available but not how we've been deploying)

The Justfile has local deploy commands that build Docker images and push directly to ECR. These work but we haven't been using them — all recent deploys go through GitHub Actions.

```bash
# Local deploy to dev (requires Docker Desktop + AWS SSO)
just deploy               # Full: build + ECR push + ECS update + wait
just deploy-backend       # Backend only
just deploy-frontend      # Frontend only

# Local deploy to QA
just deploy-qa            # Full QA deploy
just deploy-backend-qa    # Backend only to QA

# Full local pipeline
just ship                 # lint + cdk-synth + deploy + smoke-prod
```

What `just deploy` does under the hood:
1. `_ecr-login` — authenticates Docker to ECR using your AWS creds
2. `build-backend` — builds `deployment/docker/Dockerfile.backend` (linux/amd64)
3. `build-frontend` — fetches Cognito config from CloudFormation, builds frontend with those build args
4. `_push-backend` / `_push-frontend` — tags and pushes `:latest` to ECR
5. `_ecs-update-all` — calls `update_service(forceNewDeployment=True)`
6. `_ecs-wait-all` — waits for ECS services to stabilize
7. `status` — shows final running/desired counts and ALB URLs

Note: local deploys push `:latest` tag only (no SHA tag), unlike GitHub Actions which tags with the commit SHA.

## Common Problems & Fixes

| Symptom | Cause | Fix |
|---------|-------|-----|
| GH Actions deploy fails at lint | ruff or tsc error on `main` | Fix lint, push again |
| GH Actions deploy fails at L6 eval | Flaky eval test or Bedrock timeout | Re-run via workflow_dispatch with `deploy_mode=mini` |
| QA deploy not happening | No automatic trigger for QA | Must use workflow_dispatch manually |
| `just status` fails | AWS SSO expired | `just aws-login` |
| ECS task keeps restarting | App crash on startup | `just logs backend` — check for import errors or missing env vars |
| `services_stable` waiter times out | Task failing health checks | Check ALB target group health in AWS Console, or `just logs` |

## Architecture

```
Push to main ──► GitHub Actions (deploy.yml)
                   │
                   ├── Dev (automatic)
                   │     ├── L1 Lint (ruff + tsc)
                   │     ├── L2 Unit Tests (full mode)
                   │     ├── L4 CDK Synth (full mode)
                   │     ├── L5 Integration (full mode)
                   │     ├── L6 Eval Suite (full mode, 42 tests)
                   │     ├── CDK deploy (if infra changed)
                   │     ├── Backend: Docker → ECR → ECS (eagle-backend-dev)
                   │     ├── Frontend: Docker → ECR → ECS (eagle-frontend-dev)
                   │     └── Teams notification
                   │
workflow_dispatch ─┤
                   │
                   └── QA (manual only)
                         ├── L1 Lint only (mini mode always)
                         ├── CDK deploy (if infra changed)
                         ├── Backend: Docker → ECR → ECS (eagle-backend-qa)
                         ├── Frontend: Docker → ECR → ECS (eagle-frontend-qa)
                         └── Teams notification
```

## Key Files

| File | What it is |
|------|-----------|
| `.github/workflows/deploy.yml` | CI/CD pipeline (~780 lines) — the actual deploy mechanism |
| `Justfile` | Local commands — `just --list` to see everything |
| `deployment/docker/Dockerfile.backend` | Backend Docker image |
| `deployment/docker/Dockerfile.frontend` | Frontend Docker image (3-stage) |
| `infrastructure/cdk-eagle/config/environments.ts` | Environment configs (dev/qa/prod) |
| `infrastructure/cdk-eagle/bin/eagle.ts` | CDK app entry + stack wiring |

---

## Current Live State (verified 2026-03-27)

| Resource | Status | Last Updated |
|----------|--------|-------------|
| ECS `eagle-backend-dev` | 1/1 running (task def v112) | Mar 27 12:20 PM |
| ECS `eagle-frontend-dev` | 1/1 running (task def v15) | Mar 27 12:23 PM |
| ECS `eagle-backend-qa` | 1/1 running (task def v11) | Mar 27 12:17 AM |
| ECS `eagle-frontend-qa` | 1/1 running (task def v10) | Mar 27 12:19 AM |
| CDK stacks (6 + QA) | All `UPDATE_COMPLETE` | Mar 5 - Mar 24 |
| GitHub Actions | 18/20 recent runs succeeded | Mar 25-27 |

Latest deployed commit (dev): `b6c3ffd` — "Add triage diagnostic skill for session-level troubleshooting"
Latest deployed commit (QA): `5c7310f` — "Fix ZIP export: fetch document content from S3 before building archive"

---

**TL;DR**: Merge to `main` = auto-deploy to dev. QA = manual only via workflow_dispatch (GitHub UI or `gh workflow run deploy.yml -f environment=qa`). Check results with `just status` / `just status-qa` or `gh run watch`.
