---
description: "Scaffold new CDK stacks from templates — storage, compute, network, monitoring, pipeline"
allowed-tools: Read, Write, Edit, Glob, Grep, Bash
argument-hint: [storage | compute | network | monitoring | pipeline]
---

# AWS Expert - CDK Scaffold Command

> Scaffold new CDK stacks from templates.

## Purpose

Generate CDK stack boilerplate for common infrastructure patterns, pre-configured with EAGLE project conventions (naming, tagging, region).

## Usage

```
/experts:aws:cdk-scaffold storage     → S3 + DynamoDB stack
/experts:aws:cdk-scaffold compute     → ECS Fargate + ECR stack
/experts:aws:cdk-scaffold network     → VPC + ALB + CloudFront stack
/experts:aws:cdk-scaffold monitoring  → CloudWatch dashboard + alarms stack
/experts:aws:cdk-scaffold pipeline    → CodePipeline + CodeBuild stack
```

## Variables

- `STACK_TYPE`: $ARGUMENTS

## Allowed Tools

`Read`, `Write`, `Edit`, `Glob`, `Grep`, `Bash`

---

## Workflow

### Phase 1: Load Context

1. Read `.claude/commands/experts/aws/expertise.md` -> Parts 3-5
2. Check existing CDK stacks: `ls infra/*/cdk.json`
3. Determine target directory (default: `infra/{stack_type}/`)

### Phase 2: Scaffold Files

Create the following structure:

```
infra/{stack_type}/
  bin/{stack_type}.ts          # CDK app entry point
  lib/{stack_type}-stack.ts    # Main stack definition
  cdk.json                     # CDK configuration
  tsconfig.json                # TypeScript config (commonjs + node)
  package.json                 # Dependencies
  .gitignore                   # *.js, *.d.ts, node_modules, cdk.out
```

### Phase 3: Apply Conventions

- Stack name: `eagle-{stack_type}-${env}`
- Resource names: `eagle-{resource}-${env}`
- Tags: `Project=eagle`, `Environment=${env}`, `ManagedBy=cdk`
- Import existing resources where applicable
- `removalPolicy: RETAIN` for stateful resources

### Phase 4: Validate

```bash
cd infra/{stack_type} && npm install && npx cdk synth
```

---

## Stack Templates

### storage

```typescript
// S3 bucket + DynamoDB table
// Imports existing nci-documents and eagle table
// Creates new environment-specific resources
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
```

### compute

```typescript
// ECS Fargate service + ECR repository
// Includes task definition with HOSTNAME=0.0.0.0
// Health check configuration
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as ecr from 'aws-cdk-lib/aws-ecr';
```

### network

```typescript
// VPC + ALB + CloudFront
// CloudFront error responses for SPA routing
// ACM certificate integration
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as elbv2 from 'aws-cdk-lib/aws-elasticloadbalancingv2';
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
```

### monitoring

```typescript
// CloudWatch dashboard + alarms + SNS
// Pattern from existing infra/eval/ stack
import * as cloudwatch from 'aws-cdk-lib/aws-cloudwatch';
import * as sns from 'aws-cdk-lib/aws-sns';
```

### pipeline

```typescript
// CodePipeline + CodeBuild
// GitHub source + CDK deploy stages
import * as codepipeline from 'aws-cdk-lib/aws-codepipeline';
import * as codebuild from 'aws-cdk-lib/aws-codebuild';
```

---

## tsconfig.json Template

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "commonjs",
    "moduleResolution": "node",
    "lib": ["es2022"],
    "declaration": true,
    "strict": true,
    "noImplicitAny": true,
    "strictNullChecks": true,
    "noImplicitThis": true,
    "alwaysStrict": true,
    "outDir": "cdk.out",
    "skipLibCheck": true,
    "esModuleInterop": true,
    "resolveJsonModule": true
  },
  "exclude": ["node_modules", "cdk.out"]
}
```

**Critical**: Use `commonjs` module + `node` moduleResolution. Do NOT use `NodeNext` with ts-node.

---

## Instructions

1. **Check existing stacks first** - Don't create duplicates
2. **Follow naming conventions** - `eagle-{component}-{env}`
3. **Import existing resources** - Never recreate nci-documents or eagle table
4. **Tag everything** - Project, Environment, ManagedBy
5. **Use commonjs/node** - For ts-node compatibility
6. **Validate with synth** - Always run `npx cdk synth` after scaffolding
