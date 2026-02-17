---
type: expert-file
file-type: index
domain: aws
tags: [expert, aws, cdk, dynamodb, s3, iam, cloudformation, infrastructure]
---

# AWS Expert

> AWS infrastructure specialist — CDK stack authoring, DynamoDB table design, IAM policy generation, S3 operations, CloudFormation, and AWS documentation lookup.

## Domain Scope

This expert covers:
- **CDK Stack Authoring** - Create, deploy, and manage AWS CDK stacks (TypeScript)
- **DynamoDB Design** - Table/GSI design, key schema patterns, access pattern mapping
- **IAM Policy Generation** - Least-privilege policies, OIDC trust, service roles
- **S3 Operations** - Bucket configuration, lifecycle rules, static hosting
- **CloudWatch** - Dashboards, alarms, metrics (cross-ref to cloudwatch expert)
- **CloudFormation** - Template analysis, resource import, drift detection
- **AWS Documentation** - Lookup CDK construct APIs and CloudFormation properties
- **Infrastructure Inventory** - Track all AWS resources used by the EAGLE platform

## Current State

**Hybrid provisioning** — Core resources (S3, DynamoDB, Bedrock) are manually provisioned. Platform infrastructure (`infrastructure/cdk-eagle/`) provides VPC, Cognito, ECS, ECR, and OIDC via 3 CDK stacks. Eval observability stack (`infrastructure/eval/`) is also CDK-managed.

| Resource | Name | Region | Provisioning |
|----------|------|--------|-------------|
| S3 Bucket | `nci-documents` | us-east-1 | Manual |
| S3 Bucket | `eagle-eval-artifacts` | us-east-1 | CDK (EagleEvalStack) |
| DynamoDB Table | `eagle` | us-east-1 | Manual |
| CloudWatch Log Group | `/eagle/test-runs` | us-east-1 | CDK (EagleEvalStack) |
| CloudWatch Dashboard | `EAGLE-Eval-Dashboard` | us-east-1 | CDK (EagleEvalStack) |
| SNS Topic | `eagle-eval-alerts` | us-east-1 | CDK (EagleEvalStack) |
| VPC | `eagle-vpc-dev` | us-east-1 | CDK (EagleCoreStack) |
| Cognito User Pool | `eagle-users-dev` | us-east-1 | CDK (EagleCoreStack) |
| IAM Role | `eagle-app-role-dev` | us-east-1 | CDK (EagleCoreStack) |
| ECS Cluster | `eagle-dev` | us-east-1 | CDK (EagleComputeStack) |
| ECR Repository | `eagle-backend-dev` | us-east-1 | CDK (EagleComputeStack) |
| ECR Repository | `eagle-frontend-dev` | us-east-1 | CDK (EagleComputeStack) |
| IAM OIDC Provider | GitHub Actions | us-east-1 | CDK (EagleCiCdStack) |
| IAM Role | `eagle-github-actions-dev` | us-east-1 | CDK (EagleCiCdStack) |
| Bedrock | Anthropic Haiku/Sonnet | us-east-1 | AWS Console |

## Available Commands

| Command | Purpose |
|---------|---------|
| `/experts:aws:question` | Answer AWS/CDK/infrastructure questions without coding |
| `/experts:aws:plan` | Plan infrastructure changes, CDK stacks, or resource modifications |
| `/experts:aws:self-improve` | Update expertise after infrastructure changes |
| `/experts:aws:plan_build_improve` | Full ACT-LEARN-REUSE workflow for infrastructure |
| `/experts:aws:maintenance` | Check AWS resource status and validate connectivity |
| `/experts:aws:cdk-scaffold` | Scaffold new CDK stacks from templates |

## Key Files

| File | Purpose |
|------|---------|
| `expertise.md` | Complete mental model for AWS domain |
| `question.md` | Query command for read-only questions |
| `plan.md` | Planning command for infrastructure changes |
| `self-improve.md` | Expertise update command |
| `plan_build_improve.md` | Full workflow command |
| `maintenance.md` | AWS status check and connectivity validation |
| `cdk-scaffold.md` | CDK stack scaffolding command |

## Architecture

```
AWS Resources (EAGLE Platform)
  |
  |-- S3
  |     |-- nci-documents (Manual) — eagle/{tenant}/{user}/documents/
  |     |-- eagle-eval-artifacts (CDK) — eval/results/, eval/videos/
  |
  |-- DynamoDB
  |     |-- eagle (Manual) — PK=INTAKE#{tenant}, SK=INTAKE#{item_id}
  |
  |-- CloudWatch
  |     |-- /eagle/test-runs (CDK) — Eval log streams
  |     |-- EAGLE/Eval namespace (CDK) — PassRate, TestStatus metrics
  |     |-- EAGLE-Eval-Dashboard (CDK) — Widgets for all metrics
  |
  |-- SNS
  |     |-- eagle-eval-alerts (CDK) — Alarm notifications
  |
  |-- Bedrock
  |     |-- Anthropic models (Console) — Haiku, Sonnet, Opus
  |
  |-- CDK Stacks
  |     |-- infrastructure/cdk-eagle/ (TypeScript) — 3 stacks:
  |     |     |-- EagleCoreStack (VPC, Cognito, IAM, storage imports)
  |     |     |-- EagleComputeStack (ECS Fargate, ECR, ALB)
  |     |     |-- EagleCiCdStack (OIDC provider, deploy role)
  |     |-- infrastructure/eval/ (TypeScript) — EagleEvalStack
  |     |-- infrastructure/cdk/ (Python) — Reference MultiTenantBedrockStack
  |
  |-- Credentials
        |-- ~/.aws/credentials (local profile)
```

## Cross-References

| Related Expert | When to Use |
|---------------|-------------|
| git | When CDK changes need CI/CD pipeline updates |
| cloudwatch | When adding CloudWatch dashboards, alarms, or metrics |
| eval | When updating the eval observability stack |
| deployment | Legacy alias — redirects here |

## ACT-LEARN-REUSE Pattern

```
ACT    ->  Provision resources, deploy CDK stacks, configure IAM
LEARN  ->  Update expertise.md with CDK patterns, issues, and solutions
REUSE  ->  Apply patterns to future stacks and resource configurations
```
