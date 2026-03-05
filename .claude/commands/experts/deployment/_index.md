---
type: expert-file
file-type: index
domain: deployment
tags: [expert, deployment, aws, cdk, cicd, docker, cloudfront, ecs]
---

# Deployment Expert

> AWS infrastructure, CDK, CI/CD, Docker, and deployment specialist for the EAGLE multi-tenant agent platform.

## Domain Scope

This expert covers:
- **Current Infrastructure** - Manually provisioned AWS resources (S3, DynamoDB, CloudWatch, Bedrock)
- **AWS Resources Inventory** - `nci-documents` bucket, `eagle` table, `/eagle/test-runs` log group, Bedrock Haiku
- **Next.js Deployment** - Static export (S3 + CloudFront) vs standalone (ECS Fargate)
- **CDK Patterns** - Infrastructure-as-code based on nci-oa-agent conventions
- **Docker Patterns** - Multi-stage builds for Next.js standalone mode
- **CI/CD Pipelines** - GitHub Actions with OIDC, deployment workflows
- **Troubleshooting** - CDK bootstrap, VPC lookup, HOSTNAME override, credential issues

## Current State

**Manual provisioning** — All AWS resources are created by hand via AWS Console or CLI. There is no CDK stack, no CI/CD pipeline, and no Docker configuration yet.

| Resource | Name | Region | Provisioning |
|----------|------|--------|-------------|
| S3 Bucket | `nci-documents` | us-east-1 | Manual |
| DynamoDB Table | `eagle` | us-east-1 | Manual |
| CloudWatch Log Group | `/eagle/test-runs` | us-east-1 | Auto-created by eval suite |
| Bedrock | Anthropic Haiku | us-east-1 | AWS Console model access |
| AWS Credentials | `~/.aws/credentials` | Local | Manual profile |

## Future State

**CDK + CI/CD** — Infrastructure-as-code with automated deployments:

| Component | Target | Status |
|-----------|--------|--------|
| CDK Stack | S3, DynamoDB, CloudWatch, IAM | Not started |
| CloudFront + S3 | Static Next.js export | Not started |
| ECS Fargate | Dynamic Next.js standalone | Not started |
| ECR | Container image registry | Not started |
| GitHub Actions | CI/CD with OIDC | Not started |
| Dockerfile | Multi-stage Next.js build | Not started |

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
Current State (Manual)
  |-- S3: nci-documents (us-east-1)
  |     |-- eagle/{tenant}/{user}/ prefix structure
  |     |-- Documents, generated artifacts
  |
  |-- DynamoDB: eagle (us-east-1)
  |     |-- PK=INTAKE#{tenant}, SK=INTAKE#{item_id}
  |     |-- Intake records, workflow state
  |
  |-- CloudWatch: /eagle/test-runs (us-east-1)
  |     |-- Per-run log streams
  |     |-- Structured JSON events
  |
  |-- Bedrock: Anthropic Haiku (us-east-1)
  |     |-- claude-agent-sdk query() calls
  |     |-- Model access via AWS Console
  |
  |-- Credentials: ~/.aws/credentials
        |-- Local profile (no OIDC, no role assumption)

Future State (CDK + CI/CD)
  |-- cdk/
  |     |-- Stack definitions (S3, DDB, CW, IAM, CloudFront, ECS)
  |     |-- Config system (dev/staging/prod)
  |
  |-- .github/workflows/
  |     |-- deploy.yml (OIDC + CDK deploy)
  |     |-- build-push.yml (Docker build + ECR push)
  |
  |-- Dockerfile
  |     |-- Multi-stage Next.js standalone build
  |     |-- HOSTNAME=0.0.0.0 for ECS
  |
  |-- client/
        |-- Static export OR standalone mode
        |-- CloudFront + S3 OR ECS Fargate
```

## Cross-References

| Related Expert | When to Use |
|---------------|-------------|
| aws | For CDK stack authoring, DynamoDB design, IAM policies — the AWS expert is the expanded successor to this deployment expert |
| git | For GitHub Actions workflows, CI/CD pipelines, release management |
| cloudwatch | For CloudWatch dashboards, alarms, and metrics configuration |
| eval | For eval suite infrastructure (eval CDK stack) |

> **Note**: The `aws` expert is the expanded version of this deployment expert, adding CDK authoring, DynamoDB design, and IAM policy generation. All deployment commands still work. For new AWS infrastructure work, prefer `/experts:aws:*` commands.

## ACT-LEARN-REUSE Pattern

```
ACT    ->  Provision infrastructure, deploy services, configure CI/CD
LEARN  ->  Update expertise.md with patterns, issues, and solutions
REUSE  ->  Apply patterns to future deployments and environment setups
```
