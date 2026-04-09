# EAGLE — Multi-Tenant AI Acquisition Assistant

![CI](https://github.com/CBIIT/sm_eagle/actions/workflows/deploy.yml/badge.svg)
![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)
![Next.js 15](https://img.shields.io/badge/Next.js-15-black.svg)
![Strands Agents SDK](https://img.shields.io/badge/Strands_Agents-SDK-orange.svg)
![License: NCI Internal](https://img.shields.io/badge/license-NCI_Internal-lightgrey.svg)

A multi-tenant AI platform built for the **NCI Office of Acquisitions**, using the **Strands Agents SDK** (with **Amazon Bedrock** inference via boto3-native `BedrockModel`), **Cognito JWT authentication**, **DynamoDB session storage**, and **granular cost attribution**. This application serves as a reference implementation for multi-tenant AI applications on AWS.

## Table of Contents

- [Core Concept](#core-concept)
- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Setup Guides](#setup-guides)
- [Common Commands](#common-commands)
- [Validation Ladder](#validation-ladder)
- [CI/CD Pipeline](#cicd-pipeline)
- [API Reference](#api-reference)
- [Authentication & Multi-Tenancy](#authentication--multi-tenancy)
- [Data Model](#data-model)
- [Contributing](#contributing)

## Core Concept

EAGLE (Enhanced Acquisition Guidance & Lifecycle Engine) uses a **supervisor + subagent architecture** to guide contracting officers through the federal acquisition lifecycle. The backend has two orchestration modes:

1. **Strands Agents SDK** (`strands_agentic_service.py`): Supervisor delegates to specialist subagents with fresh per-call context windows — **active** in `main.py` and `streaming_routes.py`
2. **Anthropic SDK** (`agentic_service.py`): Single system prompt with all skills injected — deprecated, kept for reference

Both modes use **Claude on Amazon Bedrock** for model inference (not Amazon Bedrock AgentCore).

```
User Login -> JWT with tenant_id -> Session Attributes -> Strands Agents SDK (via Bedrock)
                                                               |
                                    Tenant-specific response + cost tracking
```

<details>
<summary><strong>Important Disclaimers</strong></summary>

**This is a code sample for demonstration purposes only.** Do not use in production environments without:
- Comprehensive security review and penetration testing
- Proper error handling and input validation
- Rate limiting and DDoS protection
- Encryption at rest and in transit
- Compliance review (GDPR, HIPAA, etc.)
- Load testing and performance optimization
- Monitoring, alerting, and incident response procedures

**Responsible AI**: This system includes automated AWS operations capabilities. Users are responsible for ensuring appropriate safeguards, monitoring, and human oversight when deploying AI-driven infrastructure management tools. Learn more about [AWS Responsible AI practices](https://docs.aws.amazon.com/wellarchitected/latest/generative-ai-lens/responsible-ai.html).

**Guardrails for Foundation Models**: When deploying this application in production, implement [Amazon Bedrock Guardrails](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails.html) for content filtering, denied topics, word filters, PII redaction, contextual grounding, and safety thresholds.
</details>

---

## Deployment Methods

GitHub Actions is the standard deployment path for EAGLE. Local `just` commands and the EC2 runner remain supported as manual/operator workflows.

| | Local Development | GitHub Actions (Standard) | Manual Operator Deploy |
|---|---|---|---|
| **Use when** | Iterating locally, UI changes | Normal dev and QA releases | Need a direct/manual deploy path |
| **Primary command** | `just dev` | merge to `main` or `gh workflow run deploy.yml ...` | `just deploy` or EC2 runner + `just deploy` |
| **AWS creds** | Optional for some local-only work, required for AWS-backed flows | OIDC in GitHub Actions | SSO, access keys, or instance role |
| **Audit trail** | Local only | Workflow runs + commit SHA | Operator-managed |
| **Build location** | Your machine | GitHub-hosted runner | Your machine or EC2 runner |

---

## Quick Start

### Prerequisites

- **Python 3.11+**, **Node.js 20+**, **Docker**, **AWS CLI** configured
- **[just](https://github.com/casey/just)** task runner (`cargo install just` or `brew install just`)
- For AWS-backed development or deployment: AWS account access with Bedrock model access enabled

### Standard Deployment (GitHub Actions)

```bash
# Deploy main to dev
gh workflow run deploy.yml --ref main -f environment=dev

# Deploy a branch to QA
gh workflow run deploy.yml --ref <branch> -f environment=qa

# Watch the latest run
gh run watch
```

See [docs/development/ci-cd.md](docs/development/ci-cd.md) for the full pipeline, deploy modes, and manual QA flow.

### Manual Deployment Options

```bash
# Option A: local/operator deploy
just deploy

# Option B: open SSM session to the EC2 runner and deploy there
AWS_PROFILE=eagle aws ssm start-session \
  --target i-0390c06d166d18926 \
  --region us-east-1

su -s /bin/bash eagle
cd /home/eagle/eagle
just deploy
```

### Local Development

```bash
# Option A: Docker Compose (recommended)
just dev

# Option B: Run services individually
just dev-backend    # FastAPI at http://localhost:8000
just dev-frontend   # Next.js at http://localhost:3000
```

### Common Commands

```bash
just --list         # See all available commands

# Development
just lint           # Ruff (Python) + tsc (TypeScript)
just test           # Backend pytest

# Smoke Tests — verify pages load and backend is reachable (stack must be running)
just smoke          # base: nav + home page (~10 tests, headless, ~14s)
just smoke mid      # all pages: nav, home, admin, documents, workflows (~27 tests, ~22s)
just smoke full     # all pages + basic agent response (~31 tests, ~27s)
just smoke-ui       # same as smoke base, headed (visible browser)

# Smoke against deployed Fargate (requires AWS creds)
just smoke-prod        # mid-level smoke against Fargate ALB (auto-discovers URL)
just smoke-prod full   # full smoke + chat against Fargate


# E2E Use Case Tests — complete acquisition workflows through the UI (headed)
just e2e intake     # OA Intake: describe need → agent returns pathway + document list
just e2e doc        # Document Gen: request SOW → agent returns document structure
just e2e far        # FAR Search: ask regulation question → agent returns FAR citation
just e2e full       # all three use case workflows in sequence

# Cloud E2E Testing (against Fargate)
just test-e2e       # Playwright against Fargate (headless)
just test-e2e-ui    # Playwright against Fargate (headed)

# Eval Suite
just eval           # Full 28-test eval suite (haiku)
just eval-quick 1,2 # Run specific tests
just eval-aws       # AWS tool tests only (16-20)

# Deploy
just deploy         # Full: build → ECR push → ECS update → wait
just deploy-backend # Backend only
just deploy-frontend # Frontend only

# Infrastructure
just cdk-synth      # Compile CDK stacks (L4 gate)
just cdk-diff       # Preview changes
just cdk-deploy     # Deploy all stacks

# Operations
just status         # ECS health + live URLs
just urls           # Print frontend/backend URLs
just check-aws      # Verify AWS connectivity (7 core resources)
just logs           # Tail backend ECS logs
just logs frontend  # Tail frontend ECS logs

# Validation Ladder
just validate       # L1-L5: lint → unit → CDK synth → docker stack → smoke mid (auto-teardown)
just validate-full  # L1-L6: validate + eval suite (requires AWS creds)

# Composite
just ci             # L1 lint + L2 unit + L4 CDK synth + L6 eval-aws
just ship           # lint + CDK synth gate + deploy + smoke-prod verify
```

---

## Architecture

```
┌──────────────────────────────────────────── AWS Cloud ────────────────────────────────────────────┐
│                                                                                                     │
│   ┌──────────┐          ┌───────────────────────────────────────────────────────────────────────┐  │
│   │  Users   │─ HTTPS ─▶│                           ECS Fargate                                 │  │
│   └────┬─────┘          │                                                                        │  │
│        │                │  ┌────────────────────┐   SSE / REST   ┌────────────────────────────┐ │  │
│        │ JWT auth        │  │  Next.js Frontend   │◀─────────────▶│      FastAPI Backend        │ │  │
│        └───────────────▶│  │  App Router · TS    │               │  streaming_routes.py        │ │  │
│                          │  └────────────────────┘               │  strands_agentic_service.py │ │  │
│   ┌────────────────┐     │                                        └─────────────┬──────────────┘ │  │
│   │    Cognito     │     └──────────────────────────────────────────────────────┼────────────────┘  │
│   │  tenant_id     │                                                             │                   │
│   │  user_id       │                                              Strands Agents SDK                 │
│   │  tier (JWT)    │                                                             │                   │
│   └────────────────┘                                                             ▼                   │
│                                                              ┌───────────────────────────────────┐   │
│                                                              │         Supervisor Agent           │   │
│                                                              │   routes request to subagents      │   │
│                                                              └─────────────────┬─────────────────┘   │
│                                                                                │                      │
│                                      ┌──────────┬───────────┬─────────────────┼──────────┬─────────┐ │
│                                      ▼          ▼           ▼                 ▼          ▼         ▼ │
│                                  legal-      market-     policy-*          oa-intake  document-  comp │
│                                  counsel  intelligence  (supervisor,        skill      generator  liance│
│                                                         librarian,                               skill │
│                                                         analyst)                                       │
│                                                                                                        │
│                                                    ▼  Amazon Bedrock                                  │
│                                             Claude Sonnet 4.6 / Haiku 4.5                             │
│                                                                                                        │
│   ┌───────────────────────────────────┐       ┌────────────────────────────────────────────────────┐ │
│   │            DynamoDB               │       │                        S3                           │ │
│   │  SESSION# · MSG# · USAGE#         │       │  eagle-documents · nci-documents                   │ │
│   │  COST#    · SUB#                  │       │  metadata Lambda (triggered on upload)              │ │
│   └───────────────────────────────────┘       └────────────────────────────────────────────────────┘ │
│                                                                                                        │
│   CloudWatch  ·  EagleEvalStack dashboards + alarms  ·  SNS alerts                                   │
│   GitHub Actions  ──▶  ECR (backend + frontend images)  ──▶  ECS rolling deploy                      │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

> **Interactive diagrams** in [`docs/architecture/diagrams/excalidraw/`](docs/architecture/diagrams/excalidraw/) — open in [Excalidraw](https://excalidraw.com) or Obsidian:
> - [`20260220-175116-arch-aws-architecture-v1.excalidraw.md`](docs/architecture/diagrams/excalidraw/20260220-175116-arch-aws-architecture-v1.excalidraw.md) (dark)
> - [`20260220-175116-arch-aws-architecture-light-v1.excalidraw.md`](docs/architecture/diagrams/excalidraw/20260220-175116-arch-aws-architecture-light-v1.excalidraw.md) (light)

### System Flow

```
User ──▶ Cognito (JWT: tenant_id · user_id · tier)
     ──▶ Next.js Frontend
     ──▶ FastAPI Backend (ECS Fargate)
    ──▶ Strands Agents SDK ──▶ Supervisor Agent
                          ──▶ Skill Subagents (each with fresh context window)
             ──▶ Amazon Bedrock (Claude Sonnet 4.6 / Haiku 4.5)
                          ──▶ DynamoDB (session · usage · cost)  +  CloudWatch
```

### EAGLE Plugin

The **EAGLE plugin** (`eagle-plugin/`) is the single source of truth for all agent and skill definitions. Agents use YAML frontmatter in markdown files, auto-discovered by `server/eagle_skill_constants.py` at runtime.

| Type | Count | Names |
|------|-------|-------|
| **Supervisor** | 1 | Orchestrator — routes to specialists |
| **Specialist Agents** | 7 | legal-counsel, market-intelligence, tech-translator, public-interest, policy-supervisor, policy-librarian, policy-analyst |
| **Skills** | 7 | oa-intake, document-generator, compliance, knowledge-retrieval, tech-review, ingest-document, admin-manager |

### AI Orchestration

The backend uses the **Strands Agents SDK** with boto3-native **`BedrockModel`** for supervisor/subagent orchestration and model inference through **Amazon Bedrock**.

The active path (`strands_agentic_service.py`) implements the supervisor/subagent pattern where each skill gets its own context window, enabling better separation of concerns for complex multi-step acquisition workflows. A legacy Anthropic path remains for compatibility/reference.

### AWS Infrastructure (6 Primary Stacks + QA Compute Stack)

All stacks in `infrastructure/cdk-eagle/`:

| Stack | Resources |
|-------|-----------|
| **EagleCiCdStack** | GitHub OIDC provider, deploy role |
| **EagleCoreStack** | VPC (2 AZ, 1 NAT), Cognito User Pool, IAM app role, imports `nci-documents` S3 + `eagle` DDB |
| **EagleStorageStack** | `eagle-documents-{env}` S3 (versioned), `eagle-document-metadata-{env}` DDB, metadata extraction Lambda (Claude via Bedrock) |
| **EagleComputeStack** | ECR repos, ECS Fargate cluster, backend ALB (internal), frontend ALB (internal), auto-scaling |
| **EagleEvalStack** | `eagle-eval-artifacts` S3, CloudWatch dashboards + alarms, SNS alerts |
| **EagleBackupStack** | Backup policies and retention for core resources |
| **EagleComputeStackQA** | Separate QA compute plane in the QA VPC |

### Environment Tiers

| Setting | Dev | QA | Prod |
|---------|-----|----|------|
| Backend CPU/Memory | 512 / 1024 MiB | 512 / 1024 MiB | 1024 / 2048 MiB |
| Frontend CPU/Memory | 256 / 512 MiB | 256 / 512 MiB | 512 / 1024 MiB |
| Desired / Max Tasks | 1 / 4 | 1 / 2 | 2 / 10 |
| Deploy path in workflow | automatic/manual | manual only | not wired into default workflow |

`staging` and `prod` config shapes exist in `infrastructure/cdk-eagle/config/environments.ts`, but the default GitHub deploy workflow currently targets `dev` and `qa`.

---

## Project Structure

```
.
├── client/                  # Next.js 14+ frontend (App Router, TypeScript, Tailwind)
├── server/                  # FastAPI backend (Python 3.11+, Strands + Bedrock)
│   ├── app/
│   │   ├── main.py          # FastAPI entry point
│   │   ├── strands_agentic_service.py  # Strands orchestration (active)
│   │   ├── sdk_agentic_service.py      # legacy compatibility layer
│   │   ├── agentic_service.py      # Anthropic SDK orchestration (deprecated)
│   │   ├── session_store.py # Unified DynamoDB access layer
│   │   ├── cognito_auth.py
│   │   ├── streaming_routes.py
│   │   └── cost_attribution.py
│   └── tests/               # Eval suite (28 tests)
├── eagle-plugin/            # Agent/skill source of truth
│   ├── plugin.json          # Manifest
│   ├── agents/              # 8 agents (supervisor + 7 specialists)
│   └── skills/              # 7 skills with YAML frontmatter
├── infrastructure/
│   └── cdk-eagle/           # CDK stacks (TypeScript)
│       ├── lib/             # core, storage, compute, cicd, eval stacks
│       ├── config/environments.ts
│       ├── scripts/         # bundle-lambda.py (cross-platform bundler)
│       └── bin/eagle.ts
├── deployment/
│   ├── docker/              # Dockerfile.backend + Dockerfile.frontend
│   └── docker-compose.dev.yml
├── scripts/                 # check_aws.py, create_users.py, setup scripts
├── docs/                    # Architecture docs, diagrams, guides
├── .github/workflows/       # CI/CD (deploy.yml, claude-code-assistant.yml)
├── Justfile                 # Unified task runner
└── .claude/                 # Expert system, specs, commands
```

---

## Setup Guides

| Guide | When to Use | Link |
|-------|------------|------|
| **Local Development** | Iterating on UI/backend, running tests locally | [docs/setup/local-development.md](docs/setup/local-development.md) |
| **CI/CD and Deployment** | Standard release path, deploy modes, QA promotion | [docs/development/ci-cd.md](docs/development/ci-cd.md) |
| **EC2 Runner Manual Deploy** | Manual in-VPC deployment and troubleshooting | [docs/setup/ec2-runner-deployment.md](docs/setup/ec2-runner-deployment.md) |
| **CDK Bootstrap** | First-time AWS account setup | [docs/setup/cdk-bootstrap.md](docs/setup/cdk-bootstrap.md) |

**Quick start (local):**
```bash
cp .env.example .env     # configure credentials
just dev                 # start full stack via Docker Compose
# → http://localhost:3000
```

---

## Validation Ladder

The local validation ladder is driven by `just`. GitHub Actions uses related but not identical gates in `.github/workflows/deploy.yml`.

| Level | Gate | Command | When |
|-------|------|---------|------|
| **L1 — Lint** | `ruff check` + `tsc --noEmit` | `just lint` | Every change |
| **L2 — Unit** | `pytest tests/` | `just test` | Backend logic changes |
| **L3 — Smoke / UI** | Playwright smoke (local stack) | `just smoke mid` | Frontend/UI changes |
| **L4 — Infra** | `cdk synth --quiet` | `just cdk-synth` | CDK changes |
| **L5 — Integration** | Docker Compose + smoke | `just validate` | Before any PR |
| **L6 — Eval** | AWS-backed eval suite | `just validate-full` | Before high-risk merges or manual release checks |

```bash
just validate       # L1-L5: full local gate — lint, unit, CDK synth, docker stack, smoke
just validate-full  # L1-L6: adds eval suite (requires AWS creds)
just ship           # deploy gate: lint + CDK synth + deploy + smoke-prod verify
```

| Change Type | Minimum Level |
|-------------|---------------|
| Typo / copy | L1 |
| Backend logic | L1 + L2 |
| Frontend UI | L1 + L3 |
| CDK change | L1 + L4 |
| Cross-stack feature | L1–L5 (`just validate`) |
| High-risk release candidate | L1–L6 (`just validate-full`) |

---


## CI/CD Pipeline

The standard deployment pipeline is the GitHub Actions workflow [`deploy.yml`](.github/workflows/deploy.yml). It deploys automatically to `dev` on push to `main`, and supports manual `workflow_dispatch` runs for both `dev` and `qa`.

| Stage | What Happens |
|------|---------------|
| **setup + changes** | resolve environment, detect changed paths, pick `mini` vs `full` deploy mode |
| **lint** | run Ruff and TypeScript checks |
| **full-mode gates** | run unit tests, CDK synth, integration health check, and optional eval |
| **deploy-infra** | run CDK deploy when infra changes are present or manually requested |
| **deploy-backend** | build and push backend image, pin ECS task definition to commit SHA |
| **deploy-frontend** | build and push frontend image, update ECS service, sync ALB target |
| **report** | send Teams notification with job results |

Authentication uses **GitHub OIDC federation** — no static IAM keys stored in secrets.

Required secrets:
- `DEPLOY_ROLE_ARN`
- `TEAMS_WEBHOOK_URL`
- optional eval and observability secrets used by downstream jobs

```bash
# Manual dev deploy
gh workflow run deploy.yml --ref main -f environment=dev

# Manual QA deploy
gh workflow run deploy.yml --ref <branch> -f environment=qa

# Watch the run
gh run watch
```

Important behavior:

- `qa` always resolves to `mini` mode in the workflow
- eval is optional and only runs when explicitly requested
- local `just deploy` remains available, but it is a manual/operator path rather than the standard release flow

For the full deployment runbook, see [docs/development/ci-cd.md](docs/development/ci-cd.md).

Related manual commands:

```bash
just deploy-ci main        # trigger deploy workflow for dev
just deploy-qa-ci <branch> # trigger deploy workflow for QA
just deploy                # manual operator deploy
just ship                  # local gate + manual deploy + smoke-prod
```


---

## Authentication & Multi-Tenancy

Cognito JWT tokens carry `tenant_id`, `user_id`, and `subscription_tier`. Session IDs encode tenant context: `{tenant_id}-{tier}-{user_id}-{session_id}`. All DynamoDB data is partitioned by tenant.

<details>
<summary>JWT structure and tenant isolation details</summary>

### JWT Token Structure

```json
{
  "sub": "user-uuid",
  "email": "user@company.com",
  "custom:tenant_id": "acme-corp",
  "custom:subscription_tier": "premium",
  "cognito:groups": ["acme-corp-admins"]
}
```

### Tenant Isolation

- **DynamoDB Partitioning**: All data partitioned by `tenant_id` via PK/SK patterns
- **Runtime Context**: Tenant information passed as session attributes to the Strands SDK
- **Admin Access**: Cognito Groups for tenant-specific admin privileges

</details>

---

## Data Model

DynamoDB single-table design (`eagle`) with 5 entity types. Subscription tiers (`basic` / `advanced` / `premium`) gate message limits, concurrent sessions, and session duration.

<details>
<summary>DynamoDB key patterns and tier limits</summary>

### DynamoDB Single-Table Design

| Entity | PK Pattern | SK Pattern |
|--------|-----------|------------|
| Session | `SESSION#{tenant}#{user}` | `SESSION#{session_id}` |
| Message | `SESSION#{tenant}#{user}` | `MSG#{session_id}#{timestamp}` |
| Usage | `USAGE#{tenant}` | `USAGE#{date}#{session}#{timestamp}` |
| Cost | `COST#{tenant}` | `COST#{date}#{timestamp}` |
| Subscription | `SUB#{tenant}` | `SUB#{tier}#current` |

### Subscription Tiers

| Feature | Basic | Advanced | Premium |
|---------|-------|----------|---------|
| Daily Messages | 50 | 200 | 1,000 |
| Monthly Messages | 1,000 | 5,000 | 25,000 |
| Concurrent Sessions | 1 | 3 | 10 |
| Session Duration | 30 min | 60 min | 240 min |

</details>

---

## API Reference

### Core

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/chat` | Chat with agent (REST) |
| POST | `/api/chat/stream` | Chat with agent (SSE streaming) |
| GET | `/api/health` | Health check |
| GET | `/api/tools` | List available tools |

### Sessions

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/sessions` | List sessions |
| POST | `/api/sessions` | Create session |
| GET | `/api/sessions/{id}` | Get session |
| DELETE | `/api/sessions/{id}` | Delete session |
| GET | `/api/sessions/{id}/messages` | Get messages |

### Admin

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/admin/dashboard` | Dashboard data |
| GET | `/api/admin/users` | List users |
| GET | `/api/admin/cost-report` | Cost report |
| GET | `/api/admin/tenants/{id}/comprehensive-report` | Full tenant report |
| POST | `/api/admin/add-to-group` | Add user to Cognito group |

---

## Demo

![Demo](docs/media/Demo.gif)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, branch naming, validation requirements, and code style guidelines.

## Cleanup

```bash
cd infrastructure/cdk-eagle
npx cdk destroy --all

# ECR repos have RETAIN policy — delete manually if needed
aws ecr delete-repository --repository-name eagle-backend-dev --force
aws ecr delete-repository --repository-name eagle-frontend-dev --force
```

## Cost Notes

| Service | Billing |
|---------|---------|
| Bedrock | Per-token ([pricing](https://aws.amazon.com/bedrock/pricing/)) |
| DynamoDB | On-demand (pay per request) |
| ECS Fargate | Per vCPU + memory per second |
| Cognito | Free for first 50K MAU |
| S3 | Standard storage + requests |
| Lambda | First 1M requests/month free |
