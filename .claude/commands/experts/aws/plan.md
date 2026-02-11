---
description: "Plan infrastructure changes, CDK stacks, DynamoDB tables, or IAM policies using expertise context"
allowed-tools: Read, Write, Glob, Grep, Bash
argument-hint: [infrastructure change or resource to create]
---

# AWS Expert - Plan Mode

> Create detailed plans for AWS infrastructure changes informed by expertise.

## Purpose

Generate a plan for CDK stacks, DynamoDB tables, IAM policies, S3 buckets, or any AWS resource change, using:
- Expertise from `.claude/commands/experts/aws/expertise.md`
- Current AWS resource inventory
- CDK patterns and naming conventions
- Known issues and workarounds

## Usage

```
/experts:aws:plan add CDK stack for existing S3 and DynamoDB
/experts:aws:plan design DynamoDB GSI for document queries
/experts:aws:plan create IAM deployment role with OIDC trust
/experts:aws:plan deploy Next.js frontend to CloudFront
```

## Variables

- `TASK`: $ARGUMENTS

## Allowed Tools

`Read`, `Write`, `Glob`, `Grep`, `Bash`

---

## Workflow

### Phase 1: Load Context

1. Read `.claude/commands/experts/aws/expertise.md`
2. Read relevant project files based on TASK
3. Understand: What is being changed? Which AWS services? Import vs create?

### Phase 2: Analyze Current State

1. Check what infrastructure files exist
2. Run connectivity check if relevant
3. Identify resources to import vs create, dependencies, potential conflicts

### Phase 3: Generate Plan

Write plan to `.claude/specs/aws-{feature}.md` with:
- Overview and target architecture
- Prerequisites checklist
- Implementation steps with verification
- Resource definitions table
- IAM permissions required
- Rollback plan
- Cost estimate
- Verification steps

### Phase 4: Report

Present plan summary to user.

---

## Plan Templates

### CDK Stack for Existing Resources
1. Use `fromBucketName()` / `fromTableName()` for existing resources
2. Add new resources with environment-specific names
3. Tag everything with Project=eagle, ManagedBy=cdk

### DynamoDB Table Design
1. Define access patterns first
2. Map to PK/SK schema
3. Design GSIs for cross-partition queries
4. Choose capacity mode

### IAM Policy
1. Identify required actions per service
2. Scope to specific resources (not `*`)
3. Add conditions where possible
4. Test with IAM policy simulator

---

## Instructions

1. **Always read expertise.md first**
2. **Check current state** - Don't assume what exists
3. **Import existing resources** - Never recreate what already exists
4. **Include rollback plan**
5. **Estimate costs**
6. **Tag everything** - Project=eagle, Environment={env}, ManagedBy=cdk

## Output Location

Plans are saved to: `.claude/specs/aws-{feature}.md`
