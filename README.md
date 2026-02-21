# EAGLE — Multi-Tenant AI Acquisition Assistant

A multi-tenant AI platform built for the **NCI Office of Acquisitions**, using the **Anthropic Python SDK** (routed through **Amazon Bedrock** for model inference), **Cognito JWT authentication**, **DynamoDB session storage**, and **granular cost attribution**. This application serves as a reference implementation for multi-tenant AI applications on AWS.

## Core Concept

EAGLE (Enhanced Acquisition Guidance & Lifecycle Engine) uses a **supervisor + subagent architecture** to guide contracting officers through the federal acquisition lifecycle. The backend has two orchestration modes:

1. **Anthropic SDK** (`agentic_service.py`): Single system prompt with all skills injected — currently active in `main.py`
2. **Claude Agent SDK** (`sdk_agentic_service.py`): Supervisor delegates to skill subagents via the `Task` tool, each with a fresh context window — the target architecture

Both modes use **Claude on Amazon Bedrock** for model inference (not Amazon Bedrock AgentCore).

```
User Login -> JWT with tenant_id -> Session Attributes -> Anthropic SDK (via Bedrock)
                                                               |
                                    Tenant-specific response + cost tracking
```

## Important Disclaimers

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

---

## Quick Start

### Prerequisites

- **Python 3.11+**, **Node.js 20+**, **Docker**, **AWS CLI** configured
- **[just](https://github.com/casey/just)** task runner (`cargo install just` or `brew install just`)
- AWS account with Bedrock model access enabled (Claude 3.5 Haiku / Sonnet)

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
just smoke          # base: nav + home page (10 tests, headless, ~14s)
just smoke mid      # all pages: nav, home, admin, documents, workflows (27 tests, ~22s)
just smoke full     # all pages + basic agent response (31 tests, ~27s)
just smoke-ui       # same as smoke base, headed (visible browser)

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
just cdk-synth      # Compile CDK stacks
just cdk-diff       # Preview changes
just cdk-deploy     # Deploy all stacks

# Operations
just status         # ECS health + live URLs
just urls           # Print frontend/backend URLs
just check-aws      # Verify AWS connectivity (all 8 resources)
just logs           # Tail backend ECS logs
just logs frontend  # Tail frontend ECS logs

# Composite
just ci             # lint → test → eval-aws
just ship           # lint → deploy
```

---

## Architecture

![Architecture Diagram](data/media/architecuture.png)

> **Interactive diagrams** in [`excalidraw-diagrams/aws/`](excalidraw-diagrams/aws/) — open in [Excalidraw](https://excalidraw.com) or Obsidian:
> - [`eagle-aws-architecture.excalidraw.md`](excalidraw-diagrams/aws/eagle-aws-architecture.excalidraw.md) (dark)
> - [`eagle-aws-architecture-light.excalidraw.md`](excalidraw-diagrams/aws/eagle-aws-architecture-light.excalidraw.md) (light)

### System Flow

```
JWT Token -> Tenant Context -> Session Attributes -> Anthropic SDK (Bedrock) -> Supervisor -> Subagent
                                                          |
                                                   Observability Traces -> DynamoDB + CloudWatch
```

### EAGLE Plugin

The **EAGLE plugin** (`eagle-plugin/`) is the single source of truth for all agent and skill definitions. Agents use YAML frontmatter in markdown files, auto-discovered by `server/eagle_skill_constants.py` at runtime.

| Type | Count | Names |
|------|-------|-------|
| **Supervisor** | 1 | Orchestrator — routes to specialists |
| **Specialist Agents** | 7 | legal-counsel, market-intelligence, tech-translator, public-interest, policy-supervisor, policy-librarian, policy-analyst |
| **Skills** | 5 | oa-intake, document-generator, compliance, knowledge-retrieval, tech-review |

### AI Orchestration

The backend uses the **Anthropic Python SDK** (`anthropic>=0.40.0`) for all LLM interactions. When deployed on AWS, requests route through **Amazon Bedrock** via `USE_BEDROCK=true` — this uses Bedrock's model access, not a separate agent service.

The advanced path (`sdk_agentic_service.py`) uses the **Claude Agent SDK** to implement a supervisor/subagent pattern where each skill gets its own context window, enabling better separation of concerns for complex multi-step acquisition workflows.

### AWS Infrastructure (5 CDK Stacks)

All stacks in `infrastructure/cdk-eagle/`:

| Stack | Resources |
|-------|-----------|
| **EagleCiCdStack** | GitHub OIDC provider, deploy role |
| **EagleCoreStack** | VPC (2 AZ, 1 NAT), Cognito User Pool, IAM app role, imports `nci-documents` S3 + `eagle` DDB |
| **EagleStorageStack** | `eagle-documents-{env}` S3 (versioned), `eagle-document-metadata-{env}` DDB, metadata extraction Lambda (Claude 3.5 Haiku via Bedrock) |
| **EagleComputeStack** | ECR repos, ECS Fargate cluster, backend ALB (internal), frontend ALB (public), auto-scaling |
| **EagleEvalStack** | `eagle-eval-artifacts` S3, CloudWatch dashboards + alarms, SNS alerts |

### Environment Tiers

| Setting | Dev | Staging | Prod |
|---------|-----|---------|------|
| Backend CPU/Memory | 512 / 1024 MiB | 512 / 1024 MiB | 1024 / 2048 MiB |
| Frontend CPU/Memory | 256 / 512 MiB | 256 / 512 MiB | 512 / 1024 MiB |
| Desired / Max Tasks | 1 / 4 | 2 / 6 | 2 / 10 |
| AZs / NAT Gateways | 2 / 1 | 2 / 2 | 3 / 3 |

---

## Project Structure

```
.
├── client/                  # Next.js 14+ frontend (App Router, TypeScript, Tailwind)
├── server/                  # FastAPI backend (Python 3.11+, Anthropic SDK)
│   ├── app/
│   │   ├── main.py          # FastAPI entry point
│   │   ├── agentic_service.py      # Anthropic SDK orchestration (active)
│   │   ├── sdk_agentic_service.py  # Claude Agent SDK orchestration (target)
│   │   ├── session_store.py # Unified DynamoDB access layer
│   │   ├── cognito_auth.py
│   │   ├── streaming_routes.py
│   │   └── cost_attribution.py
│   └── tests/               # Eval suite (28 tests)
├── eagle-plugin/            # Agent/skill source of truth
│   ├── plugin.json          # Manifest
│   ├── agents/              # 8 agents (supervisor + 7 specialists)
│   └── skills/              # 5 skills with YAML frontmatter
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

Two paths depending on your goal. Start with **Checklist A** to validate the stack locally, then run **Checklist B** to deploy to AWS.

---

## Checklist A: Local Development

Run the full stack on your laptop using Docker Compose. No cloud account required for the app itself — you only need AWS credentials for DynamoDB session storage and optionally Bedrock.

### A0 — Prerequisites

- [ ] **Docker Desktop** installed and running
- [ ] **Python 3.11+** and **Node.js 20+**
- [ ] **`just`** task runner: `cargo install just` or `brew install just` or `winget install just`
- [ ] **Playwright Chromium**: `cd client && npx playwright install chromium`

### A1 — Configure Environment

```bash
cp .env.example .env
```

Minimum settings for local dev (edit `.env`):

```bash
ANTHROPIC_API_KEY=sk-ant-...       # Direct Anthropic API (no Bedrock needed)
USE_BEDROCK=false
DEV_MODE=true                       # Skips Cognito auth — use for local only
REQUIRE_AUTH=false
EAGLE_SESSIONS_TABLE=eagle          # Still needs AWS credentials for DynamoDB
AWS_DEFAULT_REGION=us-east-1
```

> **DynamoDB note**: Session storage still uses the real `eagle` DynamoDB table.
> Set `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` in `.env`, or configure `aws configure`.

### A2 — Start the Stack

```bash
just dev-up
```

This builds both containers, starts them detached, then polls `localhost:8000/health` until the backend is ready (up to 60s). You should see:

```
Backend ready (HTTP 200)
```

### A3 — Open in Browser

Open **http://localhost:3000** — you should see the EAGLE landing page with a green **"Connected"** indicator in the top-right header. That indicator only appears when the frontend successfully called the backend on startup.

### A4 — Run Tests

Start with smoke, then use case workflows:

```bash
# Smoke — pages load and backend is reachable (headless, fast)
just smoke          # nav + home page (~14s)
just smoke mid      # all pages including admin, documents, workflows (~22s)
just smoke full     # all pages + basic agent response check (~27s)

# E2E Use Cases — complete acquisition workflows (headed, visible browser)
just e2e intake     # describe acquisition → agent returns pathway + document list
just e2e doc        # request SOW → agent generates document structure
just e2e far        # ask FAR question → agent returns regulation reference
just e2e full       # all three workflows in sequence
```

`just e2e full` opens a Chromium window and walks through three real acquisition scenarios end-to-end — proof the AI pipeline, agent routing, and domain knowledge are all working.

### A5 — Tear Down

```bash
just dev-down
```

---

## Checklist B: Cloud Deployment (AWS)

Deploys all 5 CDK stacks to AWS and runs EAGLE on ECS Fargate with Cognito auth, Bedrock, and full observability.

### B0 — Prerequisites

- [ ] **AWS CLI** configured with admin credentials:
  ```bash
  aws configure
  # Region: us-east-1
  aws sts get-caller-identity   # verify
  ```
- [ ] **Docker Desktop** installed and running
- [ ] **Node.js 20+**, **Python 3.11+**, **`just`**

### B1 — Configure Account-Specific Names *(new accounts only)*

S3 bucket names are **globally unique**. If this isn't your first deploy, update `infrastructure/cdk-eagle/config/environments.ts`:

```typescript
documentBucketName: 'eagle-documents-dev-yourname',  // must be globally unique
githubOwner: 'your-github-username',
githubRepo:  'your-repo-name',
```

### B2 — Enable Bedrock Model Access *(manual, one-time)*

1. Open **AWS Console → Amazon Bedrock → Model access**
2. Click **Manage model access** → enable **Anthropic Claude 3.5 Haiku** and **Claude 3.5 Sonnet**
3. Wait for **"Access granted"** before continuing

> The metadata Lambda uses the cross-region inference profile `us.anthropic.claude-3-5-haiku-20241022-v1:0` — no separate profile step needed once standard access is granted.

### B3 — Create Pre-requisite S3 Bucket

The `nci-documents` bucket is **imported** by CDK (not created). It must exist first:

```bash
aws s3 mb s3://nci-documents --region us-east-1
```

### B4 — Deploy CDK (all 5 stacks)

```bash
just cdk-install   # npm ci in infrastructure/cdk-eagle/

# Bootstrap CDK once per account/region
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
npx cdk bootstrap aws://$ACCOUNT_ID/us-east-1 --app "npx ts-node infrastructure/cdk-eagle/bin/eagle.ts"

# Deploy all stacks
just cdk-deploy
```

Or one command if this is your first time:

```bash
just setup   # S3 bucket → CDK bootstrap → CDK deploy → containers → users → verify
```

### B5 — Upload Knowledge Base Documents *(optional)*

After `EagleStorageStack` deploys, upload documents. S3 event notifications auto-trigger the metadata extraction Lambda:

```bash
aws s3 sync path/to/knowledge-base/ s3://eagle-documents-dev/eagle/knowledge-base/ \
  --region us-east-1

# Confirm Lambda ran
aws logs filter-log-events \
  --log-group-name /eagle/lambda/metadata-extraction-dev \
  --start-time $(python -c "import time; print(int((time.time()-300)*1000))") \
  --query 'events[].message' --output text | head -20
```

### B6 — Build and Deploy Containers

```bash
just deploy
```

This logs into ECR, builds both images, pushes them, triggers ECS rolling updates, and waits for services to stabilize.

### B7 — Create Cognito Users

```bash
just create-users
```

| User | Email | Password | Tenant | Tier |
|------|-------|----------|--------|------|
| Test | testuser@example.com | EagleTest2024! | nci | basic |
| Admin | admin@example.com | EagleAdmin2024! | nci | premium |

<details>
<summary>Manual user creation</summary>

```bash
USER_POOL_ID=$(aws cloudformation describe-stacks --stack-name EagleCoreStack \
  --query "Stacks[0].Outputs[?OutputKey=='UserPoolId'].OutputValue" --output text)

aws cognito-idp admin-create-user \
  --user-pool-id $USER_POOL_ID \
  --username testuser@example.com \
  --user-attributes \
    Name=email,Value=testuser@example.com \
    Name=email_verified,Value=true \
    Name=given_name,Value=Test \
    Name=family_name,Value=User \
    Name=custom:tenant_id,Value=nci \
    Name=custom:subscription_tier,Value=basic \
  --temporary-password 'TempPass123!' \
  --message-action SUPPRESS

aws cognito-idp admin-set-user-password \
  --user-pool-id $USER_POOL_ID \
  --username testuser@example.com \
  --password 'EagleTest2024!' \
  --permanent
```

</details>

### B8 — Set GitHub Secret *(for CI/CD)*

```bash
aws cloudformation describe-stacks --stack-name EagleCiCdStack \
  --query "Stacks[0].Outputs[?OutputKey=='DeployRoleArn'].OutputValue" --output text
```

Add the output as `DEPLOY_ROLE_ARN` in **GitHub → Settings → Secrets and variables → Actions**.

### B9 — Verify and Open in Browser

```bash
just check-aws   # verifies all 8 resources (S3×2, DDB×2, Lambda, ECS×2, Identity)
just status      # ECS running counts
just urls        # prints frontend + backend URLs
```

**Open the frontend URL in your browser** — log in with `testuser@example.com / EagleTest2024!` and confirm the intake form loads and responds.

```bash
# Or run E2E tests with a visible browser window against Fargate:
just test-e2e-ui

# Headless:
just test-e2e
```

---

## CI/CD Pipeline

The GitHub Actions workflow (`.github/workflows/deploy.yml`) runs on push to `main`:

1. **deploy-infra** — OIDC auth → `cdk deploy --all` → extract outputs
2. **deploy-backend** — Docker build+push → ECS rolling update → wait for stable
3. **deploy-frontend** — Docker build+push (with Cognito build-args) → ECS rolling update
4. **verify** — Health checks on `/api/health` and `/`

Authentication uses GitHub OIDC federation — no static IAM keys.

---

## Authentication & Multi-Tenancy

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

- **Session IDs**: `{tenant_id}-{subscription_tier}-{user_id}-{session_id}`
- **DynamoDB Partitioning**: All data partitioned by `tenant_id` via PK/SK patterns
- **Runtime Context**: Tenant information passed as session attributes to the Anthropic SDK
- **Admin Access**: Cognito Groups for tenant-specific admin privileges

---

## Data Model

### DynamoDB Single-Table Design (`eagle`)

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

![Demo](data/media/Demo.gif)

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
