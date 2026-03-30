---
type: expert-file
file-type: index
domain: deployment
tags: [expert, deployment, aws, cdk, cicd, docker, ecs, fargate, justfile]
---

# Deployment Expert

> AWS infrastructure, CDK, CI/CD, Docker, ECS Fargate, and deployment specialist for the EAGLE multi-tenant agent platform.

## Domain Scope

This expert covers:
- **CDK Infrastructure** — 6 stacks: CiCd, Core, Storage, Compute, Eval, Backup
- **ECS Fargate Deploys** — Backend (Python/FastAPI) + Frontend (Next.js standalone) on Fargate
- **CI/CD Pipeline** — GitHub Actions with OIDC, 6-level validation ladder, Teams notifications
- **Docker Builds** — Multi-stage builds for backend (python:3.11-slim) and frontend (node:20-alpine)
- **Justfile Task Runner** — Local deploy, smoke tests, validation ladder, devbox operations
- **Devbox Deploy** — EC2 via SSM for VPC-internal testing
- **QA Environment** — Separate VPC, external ALB, mini-mode deploys
- **Troubleshooting** — CDK bootstrap, VPC lookup, ECS task failures, credential issues

## Current State

**CDK-managed + CI/CD automated** — 6 CDK stacks deployed, GitHub Actions OIDC pipeline active, Docker images in ECR, ECS Fargate running backend + frontend.

| Resource | Name | Managed By |
|----------|------|------------|
| VPC | `vpc-0ede565d9119f98aa` (2 AZs, 1 NAT) | CDK (EagleCoreStack) |
| Cognito User Pool | `us-east-1_fyy3Ko0tX` | CDK (EagleCoreStack) |
| IAM App Role | `eagle-app-role-dev` | CDK (EagleCoreStack) |
| S3 `nci-documents` | Document storage (legacy) | Manual (imported by CDK) |
| DynamoDB `eagle` | Single-table design | Manual (imported by CDK) |
| S3 `eagle-documents-dev` | Document storage (new) | CDK (EagleStorageStack) |
| DynamoDB `eagle-document-metadata-dev` | Document metadata (3 GSIs) | CDK (EagleStorageStack) |
| Lambda `eagle-metadata-extractor-dev` | S3 → Bedrock extraction | CDK (EagleStorageStack) |
| ECR `eagle-backend-dev` | Backend container registry | CDK (EagleComputeStack) |
| ECR `eagle-frontend-dev` | Frontend container registry | CDK (EagleComputeStack) |
| ECS cluster `eagle-dev` | Fargate cluster | CDK (EagleComputeStack) |
| ECS `eagle-backend-dev` | Backend service (512 CPU / 1024 MB) | CDK (EagleComputeStack) |
| ECS `eagle-frontend-dev` | Frontend service (256 CPU / 512 MB) | CDK (EagleComputeStack) |
| ALB (frontend) | Public-facing | CDK (EagleComputeStack) |
| ALB (backend) | Internal | CDK (EagleComputeStack) |
| S3 `eagle-eval-artifacts` | Eval results archive | CDK (EagleEvalStack) |
| CW Dashboard `EAGLE-Eval-Dashboard-dev` | Eval metrics | CDK (EagleEvalStack) |
| GitHub Actions OIDC | Federation provider | CDK (EagleCiCdStack) |
| IAM Deploy Role | `eagle-deploy-role-dev` | CDK (EagleCiCdStack) |
| Bedrock | Claude Sonnet 4.6 (deploy), Haiku (eval) | Manual (AWS Console) |

## Deployment Methods

### 1. GitHub Actions CI/CD (Primary — all recent deploys use this)

**Dev (automatic):** Push/merge to `main` triggers the full pipeline.
```
L1 Lint (ruff + tsc) → L2 Unit Tests → L4 CDK Synth → L5 Integration → L6 Eval → Deploy
```

**QA (manual only):** workflow_dispatch — select `qa` environment + branch. No automatic trigger.
```
L1 Lint only (mini mode always) → Deploy
```

- **auto mode**: detects changed paths, runs appropriate gates
- **full mode**: all 6 gates before deploy
- **mini mode**: lint only (QA always uses mini — assumes code validated on dev)
- **Teams notification** on completion
- **QA deploy CLI**: `gh workflow run deploy.yml --ref <branch> -f environment=qa`
- File: `.github/workflows/deploy.yml` (~780 lines)

### 2. Justfile Local Deploy (Available but not actively used)
```bash
just deploy              # Build + ECR push (:latest only) + ECS update + wait
just deploy-backend      # Backend only
just deploy-frontend     # Frontend only (fetches Cognito from CF)
just deploy-qa-ci [branch]  # Trigger QA deploy via GitHub Actions (recommended)
just deploy-qa           # Local QA deploy (EAGLE_ENV=qa)
just ship                # lint + cdk-synth + deploy + smoke-prod
```

### 3. Devbox Deploy (EC2/VPC testing)
```bash
just devbox-deploy [branch]   # Git sync → docker-compose up via SSM
just devbox-ship [branch]     # Deploy + tunnel + smoke
just devbox-tunnel             # Port-forward 3000/8000
```

## Available Commands

| Command | Purpose |
|---------|---------|
| `/experts:deployment:question` | Answer deployment and infrastructure questions without coding |
| `/experts:deployment:plan` | Plan infrastructure changes or new deployment targets |
| `/experts:deployment:self-improve` | Update expertise after deployments or infrastructure changes |
| `/experts:deployment:plan_build_improve` | Full ACT-LEARN-REUSE workflow for infrastructure |
| `/experts:deployment:maintenance` | Check AWS resource status and validate connectivity |

## Key Files

| File | Purpose |
|------|---------|
| `expertise.md` | Complete mental model for deployment domain |
| `question.md` | Query command for read-only questions |
| `plan.md` | Planning command for infrastructure changes |
| `self-improve.md` | Expertise update command |
| `plan_build_improve.md` | Full workflow command |
| `maintenance.md` | AWS status check and connectivity validation |

## Architecture

```
Push to main ──► GitHub Actions (deploy.yml) ──► Dev (automatic)
                   │
                   ├── L1 Lint (ruff + tsc)                    — always
                   ├── L2 Unit Tests (pytest)                  — full mode
                   ├── L4 CDK Synth                            — full mode
                   ├── L5 Integration (uvicorn health check)   — full mode
                   ├── L6 Eval Suite (34 + 8 tests, Haiku)     — full mode
                   │
                   ├── Deploy CDK (if infra changed)
                   │     ├── EagleCiCdStack     (OIDC + deploy role)
                   │     ├── EagleCoreStack     (VPC, Cognito, IAM)
                   │     ├── EagleStorageStack  (S3, DynamoDB, Lambda)
                   │     ├── EagleComputeStack  (ECR, ECS, ALB)
                   │     ├── EagleEvalStack     (eval artifacts, dashboard)
                   │     └── EagleBackupStack   (backup policies)
                   │
                   ├── Deploy Backend (Docker → ECR → ECS eagle-backend-dev)
                   ├── Deploy Frontend (Docker → ECR → ECS eagle-frontend-dev)
                   └── Report (Teams Adaptive Card)

workflow_dispatch ──► GitHub Actions (deploy.yml) ──► QA (manual only)
                   │
                   ├── L1 Lint only (mini mode — always for QA)
                   ├── Deploy Backend (Docker → ECR → ECS eagle-backend-qa)
                   ├── Deploy Frontend (Docker → ECR → ECS eagle-frontend-qa)
                   └── Report (Teams Adaptive Card)
                   │
                   └── CLI: gh workflow run deploy.yml --ref <branch> -f environment=qa

Local Deploy (Justfile — available but not actively used)
  ├── just deploy          → _ecr-login → build → push (:latest) → ECS update → wait → status
  ├── just deploy-backend  → backend only
  ├── just deploy-frontend → frontend only (fetches Cognito from CloudFormation)
  ├── just deploy-qa-ci    → triggers QA deploy via GitHub Actions (recommended)
  └── just ship            → lint → cdk-synth → deploy → smoke-prod

Devbox Deploy (EC2 via SSM)
  ├── just devbox-deploy   → git sync → docker-compose up
  ├── just devbox-ship     → deploy → tunnel → smoke
  └── just devbox-tunnel   → SSM port-forward 3000 + 8000
```

## Cross-References

| Related Expert | When to Use |
|---------------|-------------|
| aws | CDK stack authoring, DynamoDB design, IAM policies, S3 configuration |
| git | GitHub Actions workflows, CI/CD pipelines, branch/PR management |
| cloudwatch | CloudWatch dashboards, alarms, log queries, and metrics |
| eval | Eval suite infrastructure (EagleEvalStack), test execution |
| backend | FastAPI service, tool dispatch, Strands SDK, session management |
| frontend | Next.js app, Cognito auth flow, Playwright E2E tests |

## ACT-LEARN-REUSE Pattern

```
ACT    ->  Deploy infrastructure, push containers, update ECS services, run CI/CD
LEARN  ->  Update expertise.md with patterns, failures, and solutions discovered
REUSE  ->  Apply patterns to future deployments and environment setups
```
