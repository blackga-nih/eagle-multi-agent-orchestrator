---
description: "Plan infrastructure changes, new deployments, or CDK stack additions using expertise context"
allowed-tools: Read, Write, Glob, Grep, Bash
argument-hint: [infrastructure change or deployment target]
---

# Deployment Expert - Plan Mode

> Create detailed plans for infrastructure changes, new deployments, or CDK stack additions informed by expertise.

## Purpose

Generate a plan for deploying services, adding CDK stacks, configuring CI/CD, or migrating existing resources, using:
- Expertise from `.claude/commands/experts/deployment/expertise.md`
- Current AWS resource inventory
- CDK and Docker patterns
- Known issues and workarounds

## Usage

```
/experts:deployment:plan add CDK stack for existing S3 and DynamoDB
/experts:deployment:plan deploy Next.js frontend to CloudFront
/experts:deployment:plan set up GitHub Actions CI/CD with OIDC
/experts:deployment:plan containerize Next.js for ECS Fargate
```

## Variables

- `TASK`: $ARGUMENTS

## Allowed Tools

`Read`, `Write`, `Glob`, `Grep`, `Bash`

---

## Workflow

### Phase 1: Load Context

1. Read `.claude/commands/experts/deployment/expertise.md` for:
   - Current infrastructure state
   - AWS resources inventory
   - CDK patterns and naming conventions
   - Known issues and gotchas

2. Read relevant project files:
   - `client/next.config.ts` — Current Next.js configuration
   - `client/package.json` — Dependencies and scripts
   - `server/app/agentic_service.py` — AWS resource references (bucket names, table names)

3. Understand the TASK:
   - What is being deployed or changed?
   - Which AWS services are involved?
   - Does it involve existing resources (import) or new resources (create)?
   - What environments are needed (dev/staging/prod)?

### Phase 2: Analyze Current State

1. Check what infrastructure files exist:
   ```bash
   # CDK project
   ls cdk/ 2>/dev/null || echo "No CDK project"

   # Docker files
   ls Dockerfile docker-compose.yml 2>/dev/null || echo "No Docker files"

   # GitHub Actions
   ls .github/workflows/ 2>/dev/null || echo "No GitHub Actions"
   ```

2. Run connectivity check:
   ```bash
   python -c "
   import boto3
   sts = boto3.client('sts', region_name='us-east-1')
   identity = sts.get_caller_identity()
   print(f'Account: {identity[\"Account\"]}')
   print(f'Region: us-east-1')
   "
   ```

3. Identify:
   - Resources that need to be imported vs created
   - Dependencies between components
   - Potential conflicts with existing resources

### Phase 3: Generate Plan

Create a plan document:

```markdown
# Deployment Plan: {TASK}

## Overview
- Target: {what is being deployed}
- AWS Services: {list}
- New Resources: {list of resources to create}
- Imported Resources: {list of existing resources to reference}
- Environments: {dev/staging/prod}

## Prerequisites

| Prerequisite | Status | Action |
|-------------|--------|--------|
| AWS credentials | Check | Run /experts:deployment:maintenance |
| CDK bootstrap | Needed/Done | npx cdk bootstrap |
| Docker installed | Needed/N/A | Install Docker Desktop |
| Node.js 20+ | Check | node --version |

## Architecture

{ASCII diagram of the target architecture}

## Implementation Steps

### Step 1: {description}
- Files to create/modify: {list}
- Commands: {list}
- Verification: {how to confirm success}

### Step 2: {description}
...

## Resource Definitions

| Resource | Type | Name | Notes |
|----------|------|------|-------|
| S3 Bucket | Import | nci-documents | Existing, reference only |
| CloudFront | Create | eagle-cdn-{env} | New distribution |

## IAM Permissions Required

| Principal | Service | Actions | Resource |
|-----------|---------|---------|----------|
| Deploy Role | S3 | s3:PutObject, s3:DeleteObject | arn:aws:s3:::eagle-frontend-* |

## Rollback Plan

{How to undo the changes if something goes wrong}

## Cost Estimate

| Resource | Monthly Cost (dev) | Monthly Cost (prod) |
|----------|-------------------|---------------------|
| S3 | ~$1 | ~$5 |
| CloudFront | ~$1 | ~$10 |

## Verification

1. {How to verify the deployment succeeded}
2. {Health check or smoke test}
3. {CloudWatch metrics to watch}
```

### Phase 4: Save Plan

1. Write plan to `.claude/specs/deployment-{feature}.md`
2. Report plan summary to user

---

## Plan Templates

### Template: CDK Stack for Existing Resources

When the task involves wrapping existing manual resources in CDK:
1. Use `fromBucketName()` / `fromTableName()` for existing resources
2. Add new resources with environment-specific names
3. Tag everything with Project=eagle, ManagedBy=cdk
4. Include CDK bootstrap as prerequisite

### Template: Static Frontend Deployment

When the task involves deploying Next.js as a static site:
1. Configure `output: 'export'` in next.config
2. Create S3 bucket for static files
3. Create CloudFront distribution with error page routing
4. Set up S3 sync deployment script

### Template: ECS Fargate Deployment

When the task involves deploying Next.js as a container:
1. Create Dockerfile with multi-stage build
2. Configure `output: 'standalone'` in next.config
3. Set HOSTNAME=0.0.0.0 in container environment
4. Create ECR repository, ECS cluster, Fargate service, ALB

### Template: CI/CD Pipeline

When the task involves setting up GitHub Actions:
1. Create IAM OIDC provider for GitHub
2. Create deployment IAM role with trust policy
3. Create workflow YAML with OIDC auth
4. Add deployment steps (build, push, deploy)

---

## Instructions

1. **Always read expertise.md first** - Contains all patterns and known issues
2. **Check current state** - Don't assume what exists; verify
3. **Import existing resources** - Never recreate what already exists
4. **Include rollback plan** - Every deployment plan needs a way to undo
5. **Estimate costs** - Note expected monthly costs for new resources
6. **Tag everything** - Project=eagle, Environment={env}, ManagedBy=cdk

---

## Output Location

Plans are saved to: `.claude/specs/deployment-{feature}.md`
