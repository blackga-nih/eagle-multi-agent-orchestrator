# EAGLE — Multi-Tenant Amazon Bedrock Agent Core Application

A multi-tenant AI platform demonstrating **Amazon Bedrock Agent Core Runtime**, **Cognito JWT authentication**, **DynamoDB session storage**, and **granular cost attribution**. Built for the NCI Office of Acquisitions, this application serves as a reference implementation for multi-tenant AI applications on AWS.

## Core Concept

This application demonstrates how to leverage **Amazon Bedrock Agent Core Runtime** to serve multiple tenants from a single agent deployment by passing **tenant IDs at runtime**:

1. **Dynamic Tenant Routing**: Pass tenant_id and subscription_tier to Bedrock Agent Core Runtime during each invocation
2. **Subscription-Based Access Control**: Control feature access based on subscription tier passed in session attributes
3. **Granular Cost Attribution**: Track and attribute costs per tenant and user
4. **Multi-Tenant Isolation**: Ensure complete data separation while sharing the same infrastructure

```
User Login -> JWT with tenant_id -> Session Attributes -> Bedrock Agent Core Runtime
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

## Project Structure

```
.
├── client/                  # Next.js 14+ frontend (App Router, TypeScript, Tailwind)
├── server/                  # FastAPI backend (Python 3.11+, Bedrock SDK)
│   ├── app/                 # Application modules
│   │   ├── main.py          # FastAPI entry point
│   │   ├── session_store.py # Unified DynamoDB access layer
│   │   ├── bedrock_service.py
│   │   ├── sdk_agentic_service.py  # Agent orchestration with EAGLE plugin
│   │   ├── cognito_auth.py
│   │   ├── streaming_routes.py
│   │   ├── cost_attribution.py
│   │   └── subscription_service.py
│   ├── tests/               # Eval suite (28 tests)
│   ├── config.py
│   ├── run.py
│   └── requirements.txt
├── eagle-plugin/            # EAGLE plugin (single source of truth)
│   ├── agents/              # 8 agent directories with YAML frontmatter
│   ├── skills/              # 5 skill directories with YAML frontmatter
│   ├── plugin.json          # Plugin manifest
│   └── diagrams/            # Architecture diagrams
├── infrastructure/
│   ├── cdk-eagle/           # Primary CDK stacks (TypeScript)
│   │   ├── lib/
│   │   │   ├── core-stack.ts      # VPC, Cognito, IAM, S3/DDB imports
│   │   │   ├── compute-stack.ts   # ECS Fargate, ECR, ALB
│   │   │   └── cicd-stack.ts      # OIDC + GitHub Actions role
│   │   ├── config/environments.ts # Per-env config (dev, staging, prod)
│   │   └── bin/eagle.ts           # CDK app entry point
│   ├── eval/                # Eval observability CDK stack
│   └── terraform/           # Legacy Terraform reference
├── deployment/
│   ├── docker/
│   │   ├── Dockerfile.backend     # Python backend container
│   │   └── Dockerfile.frontend    # Next.js standalone container
│   ├── docker-compose.dev.yml     # Local development
│   └── scripts/                   # Setup and deployment scripts
├── docs/                    # Architecture docs, diagrams, guides
├── .github/workflows/       # CI/CD (deploy.yml, tests)
└── .claude/                 # Claude IDE config, experts, specs
```

## Architecture Overview

![Architecture Diagram](data/media/architecuture.png)

> **Detailed interactive diagrams** available in [`excalidraw-diagrams/aws/`](excalidraw-diagrams/aws/) — open in [Excalidraw](https://excalidraw.com) or the Obsidian Excalidraw plugin:
> - [`eagle-aws-architecture.excalidraw.md`](excalidraw-diagrams/aws/eagle-aws-architecture.excalidraw.md) — Dark theme
> - [`eagle-aws-architecture-light.excalidraw.md`](excalidraw-diagrams/aws/eagle-aws-architecture-light.excalidraw.md) — Light theme
>
> These diagrams show the full request flow: **Users → ALB → Next.js Frontend (ECS Fargate) → Internal ALB → FastAPI Backend (ECS Fargate) → AWS Services** (DynamoDB, S3, Bedrock/Claude, CloudWatch, Cognito), including VPC boundaries, subnets, NAT Gateway, ECR repos, and the GitHub Actions CI/CD pipeline with OIDC.

### EAGLE Plugin Architecture

The **EAGLE plugin** (`eagle-plugin/`) defines a supervisor agent with 12 specialist subagents:

| Type | Agents |
|------|--------|
| **Supervisor** | Orchestrator — routes queries to appropriate specialists |
| **Specialist Agents** | legal-counsel, market-intelligence, tech-translator, public-interest, policy-supervisor, policy-librarian, policy-analyst |
| **Skills** | oa-intake, document-generator, compliance, knowledge-retrieval, tech-review |

Agent definitions use YAML frontmatter in `agent.md` / `SKILL.md` files, auto-discovered by `server/eagle_skill_constants.py` at runtime.

### AWS Infrastructure (CDK)

Three CDK stacks manage all AWS resources:

| Stack | Resources |
|-------|-----------|
| **EagleCoreStack** | VPC (2 AZ, NAT), Cognito User Pool, IAM app role, S3/DDB imports, CloudWatch |
| **EagleComputeStack** | ECR repos, ECS Fargate cluster, backend ALB (internal), frontend ALB (public), auto-scaling |
| **EagleCiCdStack** | GitHub OIDC provider, deploy role with scoped IAM policies |

### System Flow
```
JWT Token -> Tenant Context -> Session Attributes -> Bedrock Agent Core -> Supervisor -> Subagent
                                                          |
                                                   Observability Traces -> DynamoDB + CloudWatch
```

## Prerequisites

### AWS Account Requirements
1. **AWS Account** with appropriate permissions
2. **AWS CLI** installed and configured (`aws configure`)
3. **AWS CDK CLI** installed (`npm install -g aws-cdk`)
4. **Bedrock Model Access**: Request access to foundation models in AWS Console
5. **Bedrock Agent Core Runtime**: Ensure Bedrock Agent features are enabled in your region

### Required AWS Services
- **Amazon Bedrock**: Agent Core Runtime with foundation model access
- **Amazon Cognito**: User Pool with custom attributes (`tenant_id`, `subscription_tier`)
- **Amazon DynamoDB**: Unified `eagle` table (single-table design)
- **Amazon ECS Fargate**: Container compute for backend and frontend
- **Amazon ECR**: Container image registries
- **Amazon S3**: Document storage (`nci-documents` bucket)
- **AWS IAM**: OIDC federation for GitHub Actions CI/CD

### Development Tools
- **Node.js 20+** (frontend, CDK)
- **Python 3.11+** (backend)
- **Docker** (container builds)
- **Git**

## Deployment Guide

### Option A: CDK Infrastructure Deployment (Recommended)

#### Step 1: Bootstrap CDK
```bash
cd infrastructure/cdk-eagle
npm ci
npx cdk bootstrap aws://ACCOUNT_ID/us-east-1
```

#### Step 2: Deploy All Stacks
```bash
npx cdk deploy --all --outputs-file outputs.json
```

This creates:
- VPC with public and private subnets
- Cognito User Pool (`eagle-users-dev`) with custom attributes
- ECS Fargate cluster with backend and frontend services
- ECR repositories for container images
- Internal ALB (backend) and public ALB (frontend)
- GitHub Actions OIDC federation for CI/CD
- IAM roles with least-privilege policies

#### Step 3: Build and Push Container Images
```bash
# Login to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com

# Build and push backend
docker build -f deployment/docker/Dockerfile.backend -t ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/eagle-backend-dev:latest .
docker push ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/eagle-backend-dev:latest

# Build and push frontend
docker build -f deployment/docker/Dockerfile.frontend \
  --build-arg NEXT_PUBLIC_COGNITO_USER_POOL_ID=<from-outputs> \
  --build-arg NEXT_PUBLIC_COGNITO_CLIENT_ID=<from-outputs> \
  -t ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/eagle-frontend-dev:latest .
docker push ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/eagle-frontend-dev:latest
```

#### Step 4: Force New ECS Deployment
```bash
aws ecs update-service --cluster eagle-dev --service eagle-backend-dev --force-new-deployment
aws ecs update-service --cluster eagle-dev --service eagle-frontend-dev --force-new-deployment
```

After the first manual deploy, subsequent pushes to `main` trigger the GitHub Actions pipeline automatically.

#### Step 5: Set GitHub Secret
Add the `DEPLOY_ROLE_ARN` output from the CiCd stack as a GitHub repository secret for CI/CD.

### Option B: Local Development

```bash
# Backend
cd server
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Create .env
cat > .env << EOF
COGNITO_USER_POOL_ID=<your-pool-id>
COGNITO_CLIENT_ID=<your-client-id>
EAGLE_SESSIONS_TABLE=eagle
AWS_REGION=us-east-1
DEV_MODE=true
EOF

python run.py
# Backend available at http://localhost:8000

# Frontend (separate terminal)
cd client
npm install
npm run dev
# Frontend available at http://localhost:3000
```

### Option C: Docker Compose (Local)

```bash
cd deployment
docker compose -f docker-compose.dev.yml up
# Backend: http://localhost:8000
# Frontend: http://localhost:3000
```

## CDK Environment Configuration

Environments are defined in `infrastructure/cdk-eagle/config/environments.ts`:

| Setting | Dev | Staging | Prod |
|---------|-----|---------|------|
| Backend CPU/Memory | 512 / 1024 MiB | 512 / 1024 MiB | 1024 / 2048 MiB |
| Frontend CPU/Memory | 256 / 512 MiB | 256 / 512 MiB | 512 / 1024 MiB |
| Desired Count | 1 | 2 | 2 |
| Max Count | 4 | 6 | 10 |
| AZs / NAT Gateways | 2 / 1 | 2 / 2 | 3 / 3 |

## CI/CD Pipeline

The GitHub Actions workflow (`.github/workflows/deploy.yml`) runs on push to `main`:

1. **deploy-infra** — OIDC auth, `cdk deploy --all`, extract outputs
2. **deploy-backend** — ECR login, Docker build+push, ECS update-service
3. **deploy-frontend** — ECR login, Docker build+push with Cognito build-args, ECS update-service
4. **verify** — Health checks on backend (`/api/health`) and frontend (`/`)

Authentication uses GitHub OIDC federation (no static IAM keys).

## Authentication & Multi-Tenancy

### JWT Token Structure
```json
{
  "sub": "user-uuid",
  "email": "user@company.com",
  "custom:tenant_id": "acme-corp",
  "custom:subscription_tier": "premium",
  "cognito:groups": ["acme-corp-admins"],
  "exp": 1703123456
}
```

### Tenant Isolation
- **Session IDs**: `{tenant_id}-{subscription_tier}-{user_id}-{session_id}`
- **DynamoDB Partitioning**: All data partitioned by tenant_id via PK/SK patterns
- **Bedrock Agent Core Context**: Tenant information passed in session attributes
- **Admin Access**: Cognito Groups for tenant-specific admin privileges

## Data Storage

### DynamoDB Single-Table Design

All data stored in the unified `eagle` table using PK/SK composite keys:

| Entity | PK Pattern | SK Pattern |
|--------|-----------|------------|
| Session | `SESSION#{tenant}#{user}` | `SESSION#{session_id}` |
| Message | `SESSION#{tenant}#{user}` | `MSG#{session_id}#{timestamp}` |
| Usage | `USAGE#{tenant}` | `USAGE#{date}#{session}#{timestamp}` |
| Cost Metric | `COST#{tenant}` | `COST#{type}#{timestamp}` |
| Subscription | `SUB#{tenant}` | `SUB#{tier}#current` |

## Subscription Tiers

| Feature | Basic (Free) | Advanced ($29/mo) | Premium ($99/mo) |
|---------|--------------|-------------------|------------------|
| Daily Messages | 50 | 200 | 1,000 |
| Monthly Messages | 1,000 | 5,000 | 25,000 |
| Concurrent Sessions | 1 | 3 | 10 |
| Weather Tools | No | Basic | Full |
| Cost Reports | No | No | Admin |
| Session Duration | 30 min | 60 min | 240 min |

## API Endpoints

### Authentication Required
```
POST /api/chat                                    # Chat with Bedrock Agent Core
POST /api/sessions                                # Create session
GET  /api/tenants/{tenant_id}/sessions            # List sessions
GET  /api/tenants/{tenant_id}/usage               # Usage metrics
GET  /api/tenants/{tenant_id}/subscription        # Subscription info
GET  /api/tenants/{tenant_id}/costs               # Cost reports
GET  /api/health                                  # Health check
```

### Admin-Only
```
GET  /api/admin/tenants/{tenant_id}/overall-cost
GET  /api/admin/tenants/{tenant_id}/per-user-cost
GET  /api/admin/tenants/{tenant_id}/service-wise-cost
GET  /api/admin/tenants/{tenant_id}/comprehensive-report
GET  /api/admin/my-tenants
POST /api/admin/add-to-group
```

## Demo

![Demo](data/media/Demo.gif)

## Cleanup

### Remove CDK Infrastructure
```bash
cd infrastructure/cdk-eagle
npx cdk destroy --all
```

**Note**: ECR repositories have `RETAIN` removal policy. Delete manually if needed:
```bash
aws ecr delete-repository --repository-name eagle-backend-dev --force
aws ecr delete-repository --repository-name eagle-frontend-dev --force
```

### Remove Legacy Terraform Resources (if deployed)
```bash
cd infrastructure/terraform
terraform destroy
```

## Notes

- **Bedrock Pricing**: Varies by model (check [AWS Bedrock pricing](https://aws.amazon.com/bedrock/pricing/))
- **DynamoDB**: On-demand billing (pay per request)
- **ECS Fargate**: Billed per vCPU and memory per second
- **Cognito**: Free for first 50,000 monthly active users
- **EAGLE Plugin**: Agent/skill definitions in `eagle-plugin/` are the single source of truth
- **CDK Stacks**: Deploy via `infrastructure/cdk-eagle/` — the old Python CDK (`infrastructure/cdk/`) is deprecated
