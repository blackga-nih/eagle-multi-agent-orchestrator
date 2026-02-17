---
type: expert-file
parent: "[[aws/_index]]"
file-type: expertise
human_reviewed: false
tags: [expert-file, mental-model, aws, cdk, dynamodb, iam, s3]
last_updated: 2026-02-11T00:00:00
---

# AWS Expertise (Complete Mental Model)

> **Sources**: AWS Console (manual resources), infrastructure/eval/ CDK stack, nci-oa-agent CDK patterns, AWS CDK documentation, Next.js documentation

---

## Part 1: Current Infrastructure

### Provisioning Model

Core AWS resources (S3, DynamoDB, Bedrock) are **manually provisioned**. Platform infrastructure (`infrastructure/cdk-eagle/`) provides VPC, Cognito, ECS, ECR, and OIDC via **3 TypeScript CDK stacks**. The eval observability stack (`infrastructure/eval/`) is also CDK-managed.

```
Provisioning: Hybrid (Manual + CDK)
Region: us-east-1
Account: Accessed via ~/.aws/credentials (local profile)
IAM: Developer credentials with broad permissions
CDK: infrastructure/cdk-eagle/ (TypeScript, 3 stacks: EagleCoreStack, EagleComputeStack, EagleCiCdStack)
CDK: infrastructure/eval/ (TypeScript, EagleEvalStack)
CI/CD: GitHub Actions (deploy.yml, claude-merge-analysis.yml)
Docker: ECS Fargate (backend + frontend containers)
```

### Credential Configuration

```
~/.aws/credentials
  |-- [default] or named profile
  |-- aws_access_key_id = AKIA...
  |-- aws_secret_access_key = ...
  |-- region = us-east-1

~/.aws/config
  |-- [default]
  |-- region = us-east-1
  |-- output = json
```

**Access pattern**: All code uses `boto3.client('service', region_name='us-east-1')` — hardcoded region, default credential chain.

### What Exists vs What Doesn't

| Component | Exists | Notes |
|-----------|--------|-------|
| S3 bucket (documents) | Yes | `nci-documents`, manually created |
| S3 bucket (eval) | Yes | `eagle-eval-artifacts`, CDK-managed |
| DynamoDB table | Yes | `eagle`, manually created |
| CloudWatch log group | Yes | `/eagle/test-runs`, CDK-managed |
| CloudWatch dashboard | Yes | `EAGLE-Eval-Dashboard`, CDK-managed |
| SNS topic | Yes | `eagle-eval-alerts`, CDK-managed |
| Bedrock model access | Yes | Anthropic models enabled in Console |
| CDK project (platform) | Yes | `infrastructure/cdk-eagle/` — EagleCoreStack, EagleComputeStack, EagleCiCdStack |
| CDK project (eval) | Yes | `infrastructure/eval/` — EagleEvalStack |
| CDK project (reference) | Yes | `infrastructure/cdk/` — Python, not deployed |
| GitHub Actions | Yes | `deploy.yml`, `claude-merge-analysis.yml` |
| VPC | Yes | `eagle-vpc-dev`, CDK-managed (EagleCoreStack) |
| Cognito User Pool | Yes | `eagle-users-dev`, CDK-managed (EagleCoreStack) |
| ECS Cluster | Yes | `eagle-dev`, CDK-managed (EagleComputeStack) |
| ECR Repository (backend) | Yes | `eagle-backend-dev`, CDK-managed (EagleComputeStack) |
| ECR Repository (frontend) | Yes | `eagle-frontend-dev`, CDK-managed (EagleComputeStack) |
| IAM OIDC Provider | Yes | GitHub Actions federation, CDK-managed (EagleCiCdStack) |
| CloudFront distribution | No | Frontend served via public ALB |

---

## Part 2: AWS Resources Inventory

### S3 Bucket: `nci-documents`

```
Bucket: nci-documents
Region: us-east-1
Versioning: Unknown (likely disabled)
Encryption: Unknown (likely SSE-S3 default)
Public Access: Likely blocked (default)

Key Structure:
  eagle/{tenant_id}/{user_id}/                    # User workspace root
  eagle/{tenant_id}/{user_id}/documents/           # Generated documents
  eagle/{tenant_id}/{user_id}/documents/{type}_{timestamp}.md
```

**Used by**:
- `server/app/agentic_service.py` — `_exec_s3_document_ops()` for read/write/list/delete
- `server/tests/test_eagle_sdk_eval.py` — Tests 16 and 19 (with cleanup)

### S3 Bucket: `eagle-eval-artifacts` (CDK-managed)

```
Bucket: eagle-eval-artifacts
Region: us-east-1
Encryption: SSE-S3
Public Access: Blocked
Lifecycle: 365-day expiration
Removal Policy: RETAIN
CDK Stack: EagleEvalStack

Key Structure:
  eval/results/run-{ISO8601_timestamp}.json
  eval/videos/{run-ts}/{test_dir}/{file}
```

### DynamoDB Table: `eagle`

```
Table: eagle
Region: us-east-1
Billing: Unknown (likely on-demand)
Key Schema:
  PK (String) - Partition Key
  SK (String) - Sort Key

Access Patterns:
  PK=INTAKE#{tenant_id}, SK=INTAKE#{item_id}  ->  Intake records
  PK=INTAKE#{tenant_id}, SK begins_with INTAKE#  ->  List by tenant

GSI: Unknown (may not have any)
```

**Used by**:
- `server/app/agentic_service.py` — `_exec_dynamodb_intake()` for create/read/update/list/delete
- `server/tests/test_eagle_sdk_eval.py` — Test 17 (with cleanup)

### CloudWatch Resources (CDK-managed)

```
Log Group: /eagle/test-runs (90-day retention)
Dashboard: EAGLE-Eval-Dashboard
Alarm: EvalPassRate (< 80% -> SNS)
Namespace: EAGLE/Eval
SNS Topic: eagle-eval-alerts
```

### Bedrock: Anthropic Models

```
Service: Amazon Bedrock
Region: us-east-1
Provider: Anthropic
Models: Claude Haiku, Sonnet, Opus
Auth: Same AWS credentials as other services
```

---

## Part 3: CDK Patterns

### Active CDK Stacks

#### `infrastructure/cdk-eagle/` — Platform Infrastructure (3 Stacks)

```
infrastructure/cdk-eagle/
  |-- bin/eagle.ts                    # CDK app entry point
  |-- lib/core-stack.ts              # EagleCoreStack
  |-- lib/compute-stack.ts           # EagleComputeStack
  |-- lib/cicd-stack.ts              # EagleCiCdStack
  |-- config/environments.ts         # EagleConfig (dev, staging, prod)
  |-- cdk.json                       # app: npx ts-node --prefer-ts-exts bin/eagle.ts
  |-- tsconfig.json
  |-- package.json

EagleCoreStack:
  - VPC: eagle-vpc-dev (2 AZ, 1 NAT, public + private subnets)
  - Cognito User Pool: eagle-users-dev (email sign-in, tenant_id custom attr)
  - Cognito App Client: eagle-app-client-dev
  - IAM Role: eagle-app-role-dev (S3, DynamoDB, Bedrock, CW, Cognito)
  - CW Log Group: /eagle/app (90-day retention)
  - Imports: nci-documents (S3), eagle (DynamoDB)

EagleComputeStack (depends on EagleCoreStack):
  - ECS Cluster: eagle-dev (Fargate, Container Insights)
  - ECR: eagle-backend-dev, eagle-frontend-dev (10-image lifecycle)
  - Backend Fargate Service: internal ALB, port 8000, auto-scale 1-4
  - Frontend Fargate Service: public ALB, port 3000, auto-scale 1-4
  - CW Log Groups: /eagle/ecs/backend-dev, /eagle/ecs/frontend-dev

EagleCiCdStack (independent):
  - IAM OIDC Provider: token.actions.githubusercontent.com
  - IAM Role: eagle-github-actions-dev (CDK deploy, ECR push, ECS update)

Deploy: cd infrastructure/cdk-eagle && npx cdk deploy --all
Synth:  cd infrastructure/cdk-eagle && npx cdk synth
```

#### `infrastructure/eval/` — EagleEvalStack (Eval Observability)

```
infrastructure/eval/
  |-- bin/eval.ts                    # CDK app entry point
  |-- lib/eval-stack.ts              # EvalObservabilityStack
  |-- cdk.json                       # app: npx ts-node --prefer-ts-exts bin/eval.ts
  |-- tsconfig.json                  # ES2022, commonjs, strict
  |-- package.json                   # aws-cdk-lib 2.196.0

Resources:
  - S3 Bucket: eagle-eval-artifacts (365-day lifecycle, SSE-S3)
  - CW Log Group: /eagle/test-runs (90-day retention)
  - SNS Topic: eagle-eval-alerts
  - CW Alarm: EvalPassRate (< 80% -> SNS)
  - CW Dashboard: EAGLE-Eval-Dashboard

Deploy: cd infrastructure/eval && npx cdk deploy
Synth:  cd infrastructure/eval && npx cdk synth
```

#### `infrastructure/cdk/` — MultiTenantBedrockStack (Reference, Python)

```
infrastructure/cdk/
  |-- app.py                         # Python CDK entry point
  |-- bedrock_agents.py              # Bedrock agent construct
  |-- lambda_deployment.py           # Lambda + API Gateway construct
  |-- requirements.txt               # aws-cdk-lib 2.100.0
  |-- cdk.json                       # app: python app.py

Status: Reference implementation, not actively deployed
```

### Naming Conventions

```typescript
// Stack names: eagle-{component}-{env}
const stackName = `eagle-storage-${env}`;

// Resource names: eagle-{resource}-{env}
const bucketName = `eagle-documents-${env}`;
const tableName = `eagle-table-${env}`;

// Tags: applied to all resources
Tags.of(this).add('Project', 'eagle');
Tags.of(this).add('Environment', env);
Tags.of(this).add('ManagedBy', 'cdk');
```

### Importing Existing Resources

```typescript
// Import existing S3 bucket (read-only reference, CDK won't manage it)
const existingBucket = s3.Bucket.fromBucketName(this, 'ExistingBucket', 'nci-documents');

// Import existing DynamoDB table
const existingTable = dynamodb.Table.fromTableName(this, 'ExistingTable', 'eagle');
```

### CDK Bootstrap

```bash
# Required once per account/region before first deploy
npx cdk bootstrap aws://{ACCOUNT_ID}/us-east-1
```

---

## Part 4: DynamoDB Table Design

### Key Schema Patterns

```
Single-Table Design:
  PK = {ENTITY_TYPE}#{identifier}
  SK = {SUB_TYPE}#{sub_identifier}

Examples (EAGLE table):
  PK=INTAKE#demo-tenant    SK=INTAKE#abc123        -> Intake record
  PK=INTAKE#demo-tenant    SK=INTAKE#              -> List all intakes for tenant
  PK=USER#demo-user        SK=PROFILE#             -> User profile
  PK=DOC#tenant            SK=DOC#sow_20260210     -> Document metadata
```

### GSI Design Patterns

```typescript
// GSI for querying across partitions
const table = new dynamodb.Table(this, 'Table', {
  tableName: `eagle-${env}`,
  partitionKey: { name: 'PK', type: dynamodb.AttributeType.STRING },
  sortKey: { name: 'SK', type: dynamodb.AttributeType.STRING },
  billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
  removalPolicy: cdk.RemovalPolicy.RETAIN,
});

// GSI1: Query by entity type across tenants
table.addGlobalSecondaryIndex({
  indexName: 'GSI1',
  partitionKey: { name: 'GSI1PK', type: dynamodb.AttributeType.STRING },
  sortKey: { name: 'GSI1SK', type: dynamodb.AttributeType.STRING },
});
```

### Access Pattern → Key Schema Mapping

| Access Pattern | PK | SK | Index |
|---------------|----|----|-------|
| Get intake by tenant + ID | `INTAKE#{tenant}` | `INTAKE#{id}` | Table |
| List intakes for tenant | `INTAKE#{tenant}` | begins_with `INTAKE#` | Table |
| Get document by tenant | `DOC#{tenant}` | `DOC#{type}_{ts}` | Table |
| List all intakes (admin) | `INTAKE` | - | GSI1 |

### Capacity Modes

| Mode | When to Use | Cost Model |
|------|-------------|------------|
| On-Demand | Dev, unpredictable traffic | Per-request pricing |
| Provisioned | Prod, predictable traffic | Per-hour capacity units |
| Provisioned + Auto Scaling | Prod, variable but bounded | Base capacity + auto scale |

---

## Part 5: IAM Policy Patterns

### Least-Privilege Service Policies

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "S3DocumentAccess",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::nci-documents",
        "arn:aws:s3:::nci-documents/eagle/*"
      ]
    },
    {
      "Sid": "DynamoDBAccess",
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:DeleteItem",
        "dynamodb:Query"
      ],
      "Resource": "arn:aws:dynamodb:us-east-1:*:table/eagle"
    },
    {
      "Sid": "CloudWatchLogsAccess",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "logs:GetLogEvents",
        "logs:DescribeLogStreams"
      ],
      "Resource": "arn:aws:logs:us-east-1:*:log-group:/eagle/*"
    },
    {
      "Sid": "BedrockAccess",
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream"
      ],
      "Resource": "arn:aws:bedrock:us-east-1::foundation-model/anthropic.*"
    }
  ]
}
```

### OIDC Trust Policy for GitHub Actions

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::{ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:{OWNER}/{REPO}:ref:refs/heads/main"
        }
      }
    }
  ]
}
```

---

## Part 6: Next.js Deployment Options

### Option A: Static Export (S3 + CloudFront)

```
Build: next build (with output: 'export' in next.config.js)
Host: S3 bucket (static website hosting)
CDN: CloudFront distribution
Pros: Cheapest, no server, global CDN
Cons: No API routes, no SSR/ISR
```

### Option B: Standalone (ECS Fargate)

```
Build: next build (with output: 'standalone')
Host: ECS Fargate task
Registry: ECR
Pros: Full Next.js features, scalable
Cons: More complex, requires Docker, VPC
Critical: Set HOSTNAME=0.0.0.0 for ECS
```

### Current Assessment

The `client/` directory uses API routes (`app/api/prompts/`, `app/api/trace-logs/`) — needs a server. **Recommendation**: ECS Fargate or hybrid (static + API Gateway).

---

## Part 7: Docker Patterns

### Multi-Stage Build for Next.js Standalone

```dockerfile
FROM node:20-alpine AS deps
WORKDIR /app
COPY client/package.json client/package-lock.json ./
RUN npm ci --only=production

FROM node:20-alpine AS builder
WORKDIR /app
COPY client/ .
COPY --from=deps /app/node_modules ./node_modules
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV HOSTNAME=0.0.0.0
ENV PORT=3000
RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
```

---

## Part 8: CI/CD Patterns (GitHub Actions)

### Existing Workflows

| Workflow | File | Trigger | Purpose |
|----------|------|---------|---------|
| Deploy | `.github/workflows/deploy.yml` | push to main | CDK deploy + frontend setup |
| Claude Merge Analysis | `.github/workflows/claude-merge-analysis.yml` | PR events | AI-powered code review |

### OIDC Authentication (Recommended)

```yaml
permissions:
  id-token: write
  contents: read

steps:
  - uses: aws-actions/configure-aws-credentials@v4
    with:
      role-to-assume: arn:aws:iam::{ACCOUNT_ID}:role/github-actions-deploy
      aws-region: us-east-1
```

### CDK Deploy Workflow

```yaml
steps:
  - name: CDK Diff
    run: cd infrastructure/eval && npx cdk diff
  - name: CDK Deploy
    run: cd infrastructure/eval && npx cdk deploy --require-approval never
```

---

## Part 9: Known Issues and Troubleshooting

### CDK Bootstrap Required

**Issue**: `cdk deploy` fails with "This stack uses assets, so the toolkit stack must be deployed"
**Fix**: `npx cdk bootstrap aws://{ACCOUNT_ID}/us-east-1`

### VPC Lookup Fails in CI/CD

**Issue**: `Vpc.fromLookup()` fails in GitHub Actions (synthesis-time API call)
**Fix**: Use explicit VPC ID in config, not `Vpc.fromLookup()`

### HOSTNAME Override for ECS

**Issue**: Next.js standalone binds to `localhost`, unreachable from ALB health checks
**Fix**: `ENV HOSTNAME=0.0.0.0` in Dockerfile

### Existing Resource Conflict

**Issue**: CDK tries to create resource that already exists
**Fix**: Use `fromBucketName()` / `fromTableName()` to import existing resources

### CloudWatch Log Group Already Exists

**Issue**: CDK creates log group that eval suite already auto-created
**Fix**: Use `removalPolicy: RETAIN` or import via `fromLogGroupName()`

### TypeScript CDK tsconfig

**Issue**: `Cannot find module '../lib/eval-stack.js'` with NodeNext moduleResolution
**Fix**: Use `commonjs` module + `node` moduleResolution with ts-node

---

## Learnings

### patterns_that_work
- Manual provisioning works for dev/prototyping but doesn't scale
- boto3 inline checks give instant connectivity feedback
- Hardcoded region `us-east-1` avoids misconfiguration across tools
- TypeScript CDK with `commonjs` module + `node` moduleResolution works reliably with ts-node
- Single-stack pattern for eval observability keeps related resources together
- Python publisher with lazy-loaded boto3 clients makes AWS integration non-fatal
- Import-guard pattern (`try: import ... except ImportError`) keeps optional AWS modules zero-impact
- CDK context flags copied from existing cdk.json ensure consistent behavior

### patterns_to_avoid
- Don't create new CDK resources that conflict with existing manual resources
- Don't use `Vpc.fromLookup()` in CI/CD pipelines
- Don't forget HOSTNAME=0.0.0.0 for containerized Next.js
- Don't use `NodeNext` module/moduleResolution in tsconfig with ts-node
- Don't append `.js` extension to TypeScript imports in CDK projects using commonjs
- Don't use static IAM keys in GitHub Actions when OIDC is available

### common_issues
- AWS credentials expire or are not configured -> all services fail
- S3 bucket name globally unique constraint -> can't reuse names across accounts
- CDK bootstrap missing -> deploy fails with cryptic asset error
- `Cannot find module '../lib/eval-stack.js'`: use commonjs module, remove .js extension
- CloudWatch log group may already exist when CDK tries to create it: use RETAIN

### tips
- Run `/experts:aws:maintenance` before any deployment to verify connectivity
- Start with static export (simpler) and migrate to ECS only if API routes are needed
- Tag all CDK resources with Project=eagle and ManagedBy=cdk for cost tracking
- Use OIDC for GitHub Actions instead of static IAM keys
- Run `npx cdk synth` before `cdk deploy` to verify template generates correctly
- The eval CDK stack lives at `infrastructure/eval/` — run `cd infrastructure/eval && npx cdk deploy`
- `put_metric_data` supports up to 1000 metrics per call
