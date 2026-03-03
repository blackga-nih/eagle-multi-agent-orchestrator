---
type: expert-file
parent: "[[aws/_index]]"
file-type: expertise
human_reviewed: false
tags: [expert-file, mental-model, aws, cdk, dynamodb, iam, s3]
last_updated: 2026-02-24T00:00:00
---

# AWS Expertise (Complete Mental Model)

> **Sources**: infrastructure/cdk-eagle/ (5 stacks — all in one project), deployment/docker/ Dockerfiles, .github/workflows/ (deploy + merge analysis), server/app/session_store.py, AWS CDK documentation, Next.js documentation. Verified: 2026-02-24.

---

## Part 1: Current Infrastructure

### Provisioning Model

S3 (`nci-documents`) is **NCI-managed** (manually provisioned, imported read-only). The `eagle` DynamoDB table is now **CDK-managed** (EagleCoreStack). All platform infrastructure lives in `infrastructure/cdk-eagle/` as **5 TypeScript CDK stacks** in a single project. The VPC is NCI-provisioned via Service Catalog (SCP blocks `ec2:CreateVpc`) and imported via lookup. The GitHub OIDC provider is pre-deployed by an NCI StackSet and imported via ARN (SCP blocks `iam:CreateOpenIDConnectProvider`).

```
Provisioning: Hybrid (NCI-provisioned + CDK-managed)
Region: us-east-1
Account: 695681773636 (NCI dev account)
IAM: NCIAWSPowerUserAccess policy (restricted -- see NCI SCP Constraints below)
CDK: infrastructure/cdk-eagle/ (TypeScript, 5 stacks: EagleCiCdStack, EagleCoreStack, EagleStorageStack, EagleComputeStack, EagleEvalStack)
CDK Entry: bin/eagle.ts (custom DefaultStackSynthesizer with power-user-cdk-* roles)
CDK Synthesizer Roles: power-user-cdk-deploy-{ACCOUNT}, power-user-cdk-file-pub-{ACCOUNT},
                       power-user-cdk-img-pub-{ACCOUNT}, power-user-cdk-cfn-exec-{ACCOUNT},
                       power-user-cdk-lookup-{ACCOUNT}
CDK Bootstrap SSM: /cdk-bootstrap/hnb659fds/version (generateBootstrapVersionRule: false)
CDK: infrastructure/cdk/ (Python, reference only -- not deployed)
CI/CD: GitHub Actions (deploy.yml: 4-job pipeline, claude-merge-analysis.yml: AI code review)
Docker: deployment/docker/Dockerfile.backend (python:3.11-slim, single-stage)
Docker: deployment/docker/Dockerfile.frontend (node:20-alpine, 3-stage: deps->builder->runner)
CDK lib: aws-cdk-lib ^2.196.0
```

### NCI SCP (Service Control Policy) Constraints

The NCI AWS account has SCPs that block certain IAM and networking actions:

| Blocked Action | Impact | Workaround |
|----------------|--------|------------|
| `ec2:CreateVpc` | Cannot create VPC via CDK | Import NCI-provisioned VPC via `Vpc.fromLookup({vpcId: '...'})` |
| `iam:CreateOpenIDConnectProvider` | Cannot create OIDC provider | Import pre-deployed provider via `fromOpenIdConnectProviderArn()` |
| `iam:PassRole` on EC2 | Cannot attach IAM roles to EC2 instances | EagleDevboxStack reverted (commit 911f4ef) |
| `iam:CreateRole` on arbitrary names | CDK bootstrap role naming restricted | Use `power-user-cdk-*` role names in DefaultStackSynthesizer |

NCI VPC: `C1-CWEB-EAGLE-DEV-VPC` (`vpc-09def43fcabfa4df6`), CIDR `10.209.140.192/26`
4 private subnets across 2 AZs; egress via Transit Gateway. **No public subnets.** All ALBs are internal.

GitHub OIDC Provider: Pre-deployed by `StackSet-StackSet-Github-OIDC-*`, imported via ARN in EagleCiCdStack.

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
| S3 bucket `nci-documents` | Yes | NCI-managed, imported read-only via `Bucket.fromBucketName` |
| S3 bucket `eagle-documents-695681773636-dev` | Yes | CDK-managed (EagleStorageStack), versioned |
| S3 bucket `eagle-eval-artifacts-695681773636-dev` | Yes | CDK-managed (EagleEvalStack) |
| DynamoDB table `eagle` | Yes | CDK-managed (EagleCoreStack), PK+SK, PAY_PER_REQUEST, TTL |
| DynamoDB table `eagle-document-metadata-dev` | Yes | CDK-managed (EagleStorageStack), 3 GSIs |
| CloudWatch log group `/eagle/test-runs` | Yes | Imported (auto-created by eval suite); EagleEvalStack |
| CloudWatch log group `/eagle/app` | Yes | CDK-managed (EagleCoreStack), 90-day retention |
| CloudWatch log group `/eagle/ecs/backend-dev` | Yes | CDK-managed (EagleComputeStack), 30-day, DESTROY |
| CloudWatch log group `/eagle/ecs/frontend-dev` | Yes | CDK-managed (EagleComputeStack), 30-day, DESTROY |
| CloudWatch log group `/eagle/lambda/metadata-extraction-dev` | Yes | CDK-managed (EagleStorageStack), 30-day, DESTROY |
| CloudWatch dashboard `EAGLE-Eval-Dashboard-dev` | Yes | CDK-managed (EagleEvalStack) -- 28 tests |
| SNS topic `eagle-eval-alerts-dev` | Yes | CDK-managed (EagleEvalStack) |
| Bedrock model access | Yes | Anthropic models (Claude) enabled in NCI account |
| CDK project (platform + eval) | Yes | `infrastructure/cdk-eagle/` -- all 5 stacks unified |
| CDK project (reference) | Yes | `infrastructure/cdk/` -- Python, not deployed |
| GitHub Actions | Yes | `deploy.yml`, `claude-merge-analysis.yml` |
| VPC `vpc-09def43fcabfa4df6` | Yes | NCI-provisioned C1-CWEB-EAGLE-DEV-VPC, imported |
| Cognito User Pool `eagle-users-dev` | Yes | CDK-managed (EagleCoreStack) |
| ECS Cluster `eagle-dev` | Yes | CDK-managed (EagleComputeStack), Container Insights V2 |
| ECR Repository `eagle-backend-dev` | Yes | CDK-managed (EagleComputeStack), RETAIN |
| ECR Repository `eagle-frontend-dev` | Yes | CDK-managed (EagleComputeStack), RETAIN |
| IAM OIDC Provider | Yes | NCI-pre-deployed, imported via ARN (EagleCiCdStack) |
| IAM Role `eagle-app-role-dev` | Yes | CDK-managed (EagleCoreStack), ECS task role |
| IAM Role `eagle-github-actions-dev` | Yes | CDK-managed (EagleCiCdStack), GitHub Actions deploy role |
| Lambda `eagle-metadata-extractor-dev` | Yes | CDK-managed (EagleStorageStack), Python 3.12, X-Ray |
| CloudFront distribution | No | Not used -- internal-only NCI VPC, no public subnets |
| Public ALB | No | All ALBs are internal (`publicLoadBalancer: false`) |

### Deployed Resource IDs (Account 695681773636, us-east-1, verified 2026-02-24)

| Resource | ID/ARN |
|----------|--------|
| VPC (NCI-provisioned) | `vpc-09def43fcabfa4df6` |
| VPC CIDR | `10.209.140.192/26` |
| Subnets | 4 private subnets across 2 AZs (NCI-managed) |
| App Role | `arn:aws:iam::695681773636:role/eagle-app-role-dev` |
| Deploy Role (GH Actions) | `arn:aws:iam::695681773636:role/eagle-github-actions-dev` |
| ECS Cluster | `eagle-dev` |
| Backend ECR | `695681773636.dkr.ecr.us-east-1.amazonaws.com/eagle-backend-dev` |
| Frontend ECR | `695681773636.dkr.ecr.us-east-1.amazonaws.com/eagle-frontend-dev` |
| CDK Deploy Role | `arn:aws:iam::695681773636:role/power-user-cdk-deploy-695681773636` |
| CDK CFN Exec Role | `arn:aws:iam::695681773636:role/power-user-cdk-cfn-exec-695681773636` |

Note: Cognito User Pool ID, ALB DNS names, and exact subnet IDs are CloudFormation outputs -- query via `aws cloudformation describe-stacks`.

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

### S3 Bucket: `eagle-documents-695681773636-dev` (CDK-managed, EagleStorageStack)

```
Bucket: eagle-documents-695681773636-dev
Region: us-east-1
Encryption: SSE-S3
Versioning: Yes
Public Access: Blocked
Removal Policy: RETAIN
Lifecycle: Noncurrent → IA after 90d, expire after 365d
CORS: GET + PUT from * (presigned uploads)

Key Structure:
  eagle/knowledge-base/{agent-name}/        # KB documents uploaded from rh-eagle.zip
  metadata/metadata-catalog.json            # Lambda-maintained catalog of all extracted metadata

S3 Event Notifications:
  .txt, .md, .pdf, .doc, .docx → eagle-metadata-extractor-dev Lambda
```

### DynamoDB Table: `eagle-document-metadata-dev` (CDK-managed, EagleStorageStack)

```
Table: eagle-document-metadata-dev
Region: us-east-1
Billing: On-demand (PAY_PER_REQUEST)
PITR: Enabled
Removal Policy: RETAIN
Key Schema:
  PK: document_id (String) — S3 key used as document ID

GSIs:
  primary_topic-index:   PK=primary_topic, SK=last_updated
  primary_agent-index:   PK=primary_agent, SK=last_updated
  document_type-index:   PK=document_type, SK=last_updated

Access Patterns:
  Get metadata by document ID (direct lookup)
  List by topic (primary_topic-index)
  List by agent affinity (primary_agent-index)
  List by document type (document_type-index)

Item Schema (from models.py — stdlib dataclasses, no pydantic):
  document_id, file_name, file_type, file_size_bytes, s3_bucket, s3_key
  title, summary, document_type, primary_topic, primary_agent
  keywords[], agencies[], far_references[]
  confidence_score (stored as String in DDB), upload_date, last_updated, extraction_model
```

### S3 Bucket: `eagle-eval-artifacts-695681773636-dev` (CDK-managed)

```
Bucket: eagle-eval-artifacts-695681773636-dev
Region: us-east-1
Encryption: SSE-S3
Public Access: Blocked
Lifecycle: 365-day expiration
Removal Policy: RETAIN
CDK Stack: EagleEvalStack (in infrastructure/cdk-eagle/)

Key Structure:
  eval/results/run-{ISO8601_timestamp}.json
  eval/videos/{run-ts}/{test_dir}/{file}
```

### DynamoDB Table: `eagle`

```
Table: eagle
Region: us-east-1
Billing: On-demand (PAY_PER_REQUEST)
Key Schema:
  PK (String) - Partition Key
  SK (String) - Sort Key

Access Patterns (from session_store.py):
  PK=SESSION#{tenant}#{user}, SK=SESSION#{session_id}  ->  Session record
  PK=SESSION#{tenant}#{user}, SK=MSG#{session_id}#{msg_id}  ->  Message
  PK=SESSION#{tenant}#{user}, SK begins_with SESSION#  ->  List user sessions
  PK=SESSION#{tenant}#{user}, SK begins_with MSG#{session_id}#  ->  List messages
  PK=USAGE#{tenant}, SK=USAGE#{date}#{session}#{ts}  ->  Usage record
  PK=INTAKE#{tenant}, SK=INTAKE#{id}  ->  Intake record
  PK=INTAKE#{tenant}, SK begins_with INTAKE#  ->  List intakes

GSI1 (confirmed in session_store.py):
  GSI1PK=TENANT#{tenant}, GSI1SK=SESSION#{timestamp}  ->  Cross-user session listing

TTL: ttl field (epoch seconds, 30-day default)
```

**Used by**:
- `server/app/session_store.py` — All session/message/usage CRUD (unified access layer)
- `server/app/agentic_service.py` — `_exec_dynamodb_intake()` for create/read/update/list/delete
- `server/tests/test_eagle_sdk_eval.py` — Test 17 (with cleanup)

**Caching**: In-memory write-through cache in session_store.py (5-min TTL, per session_id)

### CloudWatch Resources (CDK-managed)

```
Log Group: /eagle/app             (EagleCoreStack, 90-day retention, RETAIN)
Log Group: /eagle/ecs/backend-dev (EagleComputeStack, 30-day retention, DESTROY)
Log Group: /eagle/ecs/frontend-dev (EagleComputeStack, 30-day retention, DESTROY)
Log Group: /eagle/lambda/metadata-extraction-dev (EagleStorageStack, 30-day, DESTROY)
Log Group: /eagle/test-runs       (EagleEvalStack, IMPORTED — not managed by CDK)

Dashboard: EAGLE-Eval-Dashboard-dev (EagleEvalStack, 28 tests)
Alarm: eagle-eval-pass-rate-dev (< 80% -> SNS, EagleEvalStack)
Alarm: eagle-metadata-extractor-errors-dev (>= 3 errors in 5min, EagleStorageStack)
Alarm: eagle-metadata-extractor-duration-dev (p99 >= 80% of timeout, EagleStorageStack)
Alarm: eagle-metadata-extractor-throttles-dev (>= 1 throttle in 5min, EagleStorageStack)
Namespace: EAGLE/Eval
SNS Topic: eagle-eval-alerts-dev (EagleEvalStack)
```

### Bedrock: Anthropic Models

```
Service: Amazon Bedrock
Region: us-east-1
Provider: Anthropic
Models: Claude Haiku, Sonnet, Opus
Auth: Same AWS credentials as other services

On-Demand Invocation (Claude 3.5+):
  Use cross-region inference profiles — direct model IDs require provisioned throughput:
  CORRECT:   us.anthropic.claude-3-5-haiku-20241022-v1:0   ← note "us." prefix
  INCORRECT: anthropic.claude-3-5-haiku-20241022-v1:0      ← ValidationException

IAM Resources needed for inference profiles:
  arn:aws:bedrock:{region}:{account}:inference-profile/us.anthropic.*   ← profile
  arn:aws:bedrock:*::foundation-model/anthropic.*                        ← underlying model

Used by:
  - ECS app role (eagle-app-role-dev) — InvokeModel + InvokeModelWithResponseStream
  - Lambda (eagle-metadata-extractor-dev) — InvokeModel via inference profile
```

---

## Part 3: CDK Patterns

### Active CDK Stacks

#### `infrastructure/cdk-eagle/` — Platform Infrastructure (5 Stacks)

```
infrastructure/cdk-eagle/
  |-- bin/eagle.ts                    # CDK app entry point (5 stacks)
  |-- lib/core-stack.ts              # EagleCoreStack
  |-- lib/compute-stack.ts           # EagleComputeStack
  |-- lib/cicd-stack.ts              # EagleCiCdStack
  |-- lib/storage-stack.ts           # EagleStorageStack
  |-- lib/eval-stack.ts              # EagleEvalStack
  |-- config/environments.ts         # EagleConfig (dev, staging, prod)
  |-- cdk.json                       # app: npx ts-node bin/eagle.ts
  |-- tsconfig.json
  |-- package.json

Stack dependency order: EagleCiCdStack (independent) → EagleCoreStack → EagleStorageStack
                        → EagleComputeStack; EagleEvalStack (independent)

EagleCoreStack:
  - VPC: vpc-09def43fcabfa4df6 (NCI C1-CWEB-EAGLE-DEV-VPC, IMPORTED via Vpc.fromLookup)
    - 4 private subnets across 2 AZs, CIDR 10.209.140.192/26, egress via Transit Gateway
    - NO public subnets — SCP blocks ec2:CreateVpc, VPC provisioned by NCI Service Catalog
  - DynamoDB Table: eagle (CDK-MANAGED, PK+SK, PAY_PER_REQUEST, TTL=ttl, RETAIN)
  - Cognito User Pool: eagle-users-dev (email sign-in, tenant_id + subscription_tier custom attrs)
  - Cognito App Client: eagle-app-client-dev (userPassword + SRP + adminUserPassword flows)
  - Token validity: access/id 1hr, refresh 30d
  - IAM Role: eagle-app-role-dev (assumed by ecs-tasks.amazonaws.com)
    - S3: GetObject, PutObject, DeleteObject, ListBucket on nci-documents/eagle/*
    - S3: GetObject, GetBucketLocation, ListBucket on eagle-documents-695681773636-dev (read-only)
    - DynamoDB: GetItem, PutItem, UpdateItem, DeleteItem, Query, Scan, BatchWriteItem on eagle + /index/*
    - DynamoDB: GetItem, Query, Scan, BatchGetItem on eagle-document-metadata-dev + /index/*
    - Bedrock: InvokeModel, InvokeModelWithResponseStream, InvokeAgent (anthropic.* + agents)
      - Resources: inference-profile/us.anthropic.* + foundation-model/anthropic.* + agent/*
    - CW: CreateLogStream, PutLogEvents, GetLogEvents, DescribeLogStreams, FilterLogEvents on /eagle/*
    - Cognito: GetUser, AdminGetUser, CreateGroup, AdminAddUserToGroup, ListUsers
  - CW Log Group: /eagle/app (90-day retention, RETAIN)
  - Imports (read-only refs): nci-documents (S3 via fromBucketName)
  - Outputs: VpcId, UserPoolId, UserPoolClientId, AppRoleArn, AppLogGroupName, EagleTableName

EagleComputeStack (depends on EagleCoreStack + EagleStorageStack):
  - ECS Cluster: eagle-dev (Fargate, Container Insights V2)
  - ECR: eagle-backend-dev, eagle-frontend-dev (10-image lifecycle, RETAIN)
  - Backend Fargate Service:
    - Internal ALB (publicLoadBalancer: false), port 8000, 512 CPU / 1024 MiB, auto-scale 1-4 (70% CPU)
    - Health check: /api/health (curl), 30s interval, 3 retries, 60s start period
    - Env: EAGLE_SESSIONS_TABLE, S3_BUCKET, USE_BEDROCK=true, REQUIRE_AUTH=true,
           COGNITO_USER_POOL_ID, COGNITO_CLIENT_ID, DOCUMENT_BUCKET, METADATA_TABLE
  - Frontend Fargate Service:
    - Internal ALB (publicLoadBalancer: false), port 3000, 256 CPU / 512 MiB, auto-scale 1-4 (70% CPU)
    - Health check: / (curl), HOSTNAME=0.0.0.0
    - Env: FASTAPI_URL=http://{backend-alb-dns}, NEXT_PUBLIC_COGNITO_*
  - CW Log Groups: /eagle/ecs/backend-dev, /eagle/ecs/frontend-dev (30-day, DESTROY)
  - Outputs: BackendRepoUri, FrontendRepoUri, ClusterName, FrontendUrl, BackendUrl
  NOTE: Both ALBs are INTERNAL (NCI VPC has no public subnets). Access via VPN/bastion only.

EagleCiCdStack (independent):
  - IAM OIDC Provider: token.actions.githubusercontent.com
  - IAM Role: eagle-github-actions-dev (1hr max session)
    - Trust: repo:gblack686/sample-multi-tenant-agent-core-app:* (wildcard branch)
    - Permissions: CloudFormation (full stack ops), SSM GetParameter, STS AssumeRole
    - S3: CDK asset buckets (cdk-*), ECR: full push cycle, ECS: update/describe/register
    - IAM: CDK bootstrap role ops (cdk-* roles)
  - Outputs: DeployRoleArn, OIDCProviderArn

Environment Configs (config/environments.ts):
  - DEV:     2 AZ, 1 NAT, 512/1024 backend, 256/512 frontend, scale 1-4
  - STAGING: 2 AZ, 2 NAT, same CPU/mem, scale 2-6
  - PROD:    3 AZ, 3 NAT, 1024/2048 backend, 512/1024 frontend, scale 2-10

cdk.json: app: npx ts-node bin/eagle.ts (no --prefer-ts-exts)
tsconfig: ES2020, commonjs, no explicit moduleResolution
Tags: Project=eagle, ManagedBy=cdk, Environment={env} (applied to all stacks in eagle.ts)

Deploy: cd infrastructure/cdk-eagle && npx cdk deploy --all
Synth:  cd infrastructure/cdk-eagle && npx cdk synth
```

#### EagleStorageStack (in `infrastructure/cdk-eagle/lib/storage-stack.ts`)

```
Resources:
  - S3 Bucket: eagle-documents-695681773636-dev (versioned, SSE-S3, BLOCK_ALL, RETAIN)
    - Lifecycle: noncurrent versions → IA after 90d, expire after 365d
    - CORS: GET + PUT allowed from * (for presigned URL uploads)
    - S3 event notifications → Lambda on .txt, .md, .pdf, .doc, .docx uploads
  - DynamoDB Table: eagle-document-metadata-dev (PAY_PER_REQUEST, PITR, RETAIN)
    - PK: document_id (String) — S3 key used as document ID
    - GSI: primary_topic-index (PK=primary_topic, SK=last_updated)
    - GSI: primary_agent-index (PK=primary_agent, SK=last_updated)
    - GSI: document_type-index (PK=document_type, SK=last_updated)
  - Lambda: eagle-metadata-extractor-dev (Python 3.12, 512 MiB, 120s timeout, X-Ray active tracing)
    - Reads S3 object → extracts text → Claude via Bedrock → writes DynamoDB + S3 catalog
    - Model: us.anthropic.claude-3-5-haiku-20241022-v1:0 (cross-region inference profile)
    - Env: DOCUMENT_BUCKET, METADATA_TABLE, BEDROCK_MODEL_ID, CATALOG_KEY=metadata/metadata-catalog.json
    - IAM: S3 read/put on eagle-documents-695681773636-dev, DynamoDB write on metadata table,
           Bedrock InvokeModel on inference-profile/us.anthropic.* + foundation-model/anthropic.*
    - Bundler: infrastructure/cdk-eagle/scripts/bundle-lambda.py (manylinux2014_x86_64 on Windows)
    - Log Group: /eagle/lambda/metadata-extraction-dev (30-day retention)
  - CW Alarms: errors >= 3 in 5min, duration p99 >= 80% of timeout, throttles >= 1

Deploy: cd infrastructure/cdk-eagle && npx cdk deploy EagleStorageStack
Lambda bundler script: infrastructure/cdk-eagle/scripts/bundle-lambda.py
```

---

#### EagleEvalStack (in `infrastructure/cdk-eagle/lib/eval-stack.ts`)

```
Part of the unified infrastructure/cdk-eagle/ project (NOT a separate CDK app).
Independent stack — no cross-stack dependencies. Deployed alongside other stacks.

Resources:
  - S3 Bucket: eagle-eval-artifacts-695681773636-dev (365-day lifecycle, SSE-S3, BLOCK_ALL, RETAIN)
  - CW Log Group: /eagle/test-runs (IMPORTED — auto-created by eval suite on first run)
  - SNS Topic: eagle-eval-alerts-dev (display: "EAGLE Eval Alerts")
  - CW Alarm: eagle-eval-pass-rate-dev (< 80% -> SNS, TREAT_MISSING_DATA: NOT_BREACHING)
  - CW Dashboard: EAGLE-Eval-Dashboard-dev
    - Row 1: PassRate (%) graph + Test Counts (stacked: Passed/Failed/Skipped)
    - Rows 2-6: 28 per-test SingleValueWidgets (TestStatus, 24hr max, 6 per row)
    - Row 7: Total Cost (USD) graph
  - Namespace: EAGLE/Eval
  - Metrics: PassRate(Avg), TestsPassed(Sum), TestsFailed(Sum), TestsSkipped(Sum), TotalCost(Avg), TestStatus(Max per test)

Dashboard tracks 28 tests (1_session_creation through 28_sdk_skill_subagent_orchestration)
  Tests 21-28 are use-case tests: uc02_micro_purchase, uc03_option_exercise, uc04_contract_modification,
  uc05_co_package_review, uc07_contract_closeout, uc08_shutdown_notification,
  uc09_score_consolidation, sdk_skill_subagent_orchestration

Deploy: cd infrastructure/cdk-eagle && npx cdk deploy EagleEvalStack
Synth:  cd infrastructure/cdk-eagle && npx cdk synth EagleEvalStack
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

### Access Pattern → Key Schema Mapping (from session_store.py + agentic_service.py)

| Access Pattern | PK | SK | Index |
|---------------|----|----|-------|
| Get session | `SESSION#{tenant}#{user}` | `SESSION#{session_id}` | Table |
| List user sessions | `SESSION#{tenant}#{user}` | begins_with `SESSION#` | Table |
| Get message | `SESSION#{tenant}#{user}` | `MSG#{session_id}#{msg_id}` | Table |
| List messages for session | `SESSION#{tenant}#{user}` | begins_with `MSG#{session_id}#` | Table |
| Record usage | `USAGE#{tenant}` | `USAGE#{date}#{session}#{ts}` | Table |
| List usage by date | `USAGE#{tenant}` | `>=` `USAGE#{start_date}` | Table |
| Get intake by ID | `INTAKE#{tenant}` | `INTAKE#{id}` | Table |
| List intakes for tenant | `INTAKE#{tenant}` | begins_with `INTAKE#` | Table |
| List sessions by tenant | `TENANT#{tenant}` | `SESSION#{timestamp}` | GSI1 |

### Capacity Modes

| Mode | When to Use | Cost Model |
|------|-------------|------------|
| On-Demand | Dev, unpredictable traffic | Per-request pricing |
| Provisioned | Prod, predictable traffic | Per-hour capacity units |
| Provisioned + Auto Scaling | Prod, variable but bounded | Base capacity + auto scale |

---

## Part 5: IAM Policy Patterns

### App Role Policies (from core-stack.ts — eagle-app-role-dev)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "S3DocumentAccess",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"],
      "Resource": ["arn:aws:s3:::nci-documents", "arn:aws:s3:::nci-documents/eagle/*"]
    },
    {
      "Sid": "DynamoDBAccess",
      "Effect": "Allow",
      "Action": ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem",
                 "dynamodb:DeleteItem", "dynamodb:Query", "dynamodb:Scan", "dynamodb:BatchWriteItem"],
      "Resource": ["arn:aws:dynamodb:us-east-1:*:table/eagle",
                   "arn:aws:dynamodb:us-east-1:*:table/eagle/index/*"]
    },
    {
      "Sid": "BedrockInvoke",
      "Effect": "Allow",
      "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream", "bedrock:InvokeAgent"],
      "Resource": ["arn:aws:bedrock:us-east-1::foundation-model/anthropic.*",
                   "arn:aws:bedrock:us-east-1:{ACCOUNT}:agent/*"]
    },
    {
      "Sid": "CloudWatchLogs",
      "Effect": "Allow",
      "Action": ["logs:CreateLogStream", "logs:PutLogEvents", "logs:GetLogEvents",
                 "logs:DescribeLogStreams", "logs:FilterLogEvents"],
      "Resource": "arn:aws:logs:us-east-1:{ACCOUNT}:log-group:/eagle/*"
    },
    {
      "Sid": "CognitoUserManagement",
      "Effect": "Allow",
      "Action": ["cognito-idp:GetUser", "cognito-idp:AdminGetUser", "cognito-idp:CreateGroup",
                 "cognito-idp:AdminAddUserToGroup", "cognito-idp:ListUsers"],
      "Resource": "{userPoolArn}"
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

### Backend Dockerfile (deployment/docker/Dockerfile.backend)

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server/app/ app/
COPY server/run.py .
COPY server/config.py .
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Frontend Dockerfile (deployment/docker/Dockerfile.frontend)

```dockerfile
# 3-stage: deps → builder → runner
FROM node:20-alpine AS deps     # npm ci --production=false (dev deps needed for build)
FROM node:20-alpine AS builder  # npm run build with NEXT_PUBLIC_COGNITO_* build-args
FROM node:20-alpine AS runner   # Non-root user (nextjs:1001), HOSTNAME=0.0.0.0
```

Key details:
- Build-args: `NEXT_PUBLIC_COGNITO_USER_POOL_ID`, `NEXT_PUBLIC_COGNITO_CLIENT_ID`, `NEXT_PUBLIC_COGNITO_REGION`
- Standalone output: `.next/standalone` + `.next/static` + `public/`
- Non-root: `nodejs:1001` group, `nextjs:1001` user
- Docker context: repo root (both Dockerfiles use paths like `server/` and `client/`)

---

## Part 8: CI/CD Patterns (GitHub Actions)

### Existing Workflows

| Workflow | File | Trigger | Purpose |
|----------|------|---------|---------|
| Deploy | `.github/workflows/deploy.yml` | push to main, workflow_dispatch | Full CDK + container pipeline |
| Claude Merge Analysis | `.github/workflows/claude-merge-analysis.yml` | PR, issue_comment, issues | AI-powered code review + auto-branch |

### Deploy Pipeline (deploy.yml — 4 Jobs)

```
deploy-infra (CDK deploy --all → outputs.json)
  ├── deploy-backend (parallel: build→push→update ECS)
  └── deploy-frontend (parallel: build→push→update ECS)
        └── verify (health checks: /api/health + /)
```

Key patterns:
- **Pinned action SHAs** (not tags) for security
- **OIDC auth** via `aws-actions/configure-aws-credentials` with `secrets.DEPLOY_ROLE_ARN`
- **workflow_dispatch** inputs: `deploy_infra` (bool) + `deploy_app` (bool)
- **CDK outputs extraction**: `--outputs-file outputs.json` → jq to GITHUB_OUTPUT
- **Docker builds**: `deployment/docker/Dockerfile.backend` + `Dockerfile.frontend`
- **Frontend build-args**: NEXT_PUBLIC_COGNITO_* baked at build time from CDK outputs
- **ECS deploy**: `aws ecs update-service --force-new-deployment` + `wait services-stable`
- **Tags**: `${{ github.sha }}` + `latest`

### Claude Merge Analysis (claude-merge-analysis.yml — 2 Jobs)

```
merge-analysis (claude-code-action@v1, claude-opus-4-6)
  └── create-feature-branch (if has_changes=true)
```

Key patterns:
- **anthropics/claude-code-action@v1** with structured JSON output
- **Triggers**: PR events, `@claude` in issue comments, `claude-analyze` label
- **Model**: claude-opus-4-6, temp 0.2 (analysis) / 0.1 (implementation)
- **Auto-PR creation** from analysis recommendations

### OIDC Authentication Pattern

```yaml
permissions:
  id-token: write
  contents: read

steps:
  - uses: aws-actions/configure-aws-credentials@e3dd6a429d7300a6a4c196c26e071d42e0343502  # v4.0.2
    with:
      role-to-assume: ${{ secrets.DEPLOY_ROLE_ARN }}
      aws-region: us-east-1
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

### ECS First Deploy Chicken-and-Egg (ECR Empty)

**Issue**: `ApplicationLoadBalancedFargateService` requires `desiredCount >= 1`. On first deploy, ECR repos are empty — ECS tries to launch tasks, can't pull images, CloudFormation waits ~30+ min for service stabilization then FAILS and ROLLS BACK the entire stack.
**Root Cause**: CDK's `ecs_patterns.ApplicationLoadBalancedFargateService` validates `desiredCount > 0` at synth time. Setting `desiredCount: 0` throws `ValidationError: You must specify a desiredCount greater than 0`.
**Fix**: Push placeholder images to ECR BEFORE first `cdk deploy`. Minimal images that pass container health checks:
- Backend: python:3.11-slim + fastapi + uvicorn + curl, responds to `GET /api/health`
- Frontend: node:20-alpine + express + curl, responds to `GET /` and `GET /api/health`
**Time cost**: ~60 min wasted on first attempt (30 min waiting + 30 min rollback + troubleshooting)

### ECR RETAIN Policy Blocks Re-Create

**Issue**: ECR repos with `removalPolicy: RETAIN` survive stack deletion. Re-deploying the same stack fails: `Resource of type 'AWS::ECR::Repository' with identifier 'eagle-backend-dev' already exists`.
**Fix**: Use `npx cdk deploy --import-existing-resources` to adopt the existing repos into the new stack.

### ECS Image Caching After ECR Push

**Issue**: After pushing a new image with the same `latest` tag, running ECS tasks continue using the OLD cached image digest. New tasks launched by service cycling may also get cached images.
**Fix**: Run `aws ecs update-service --cluster {cluster} --service {service} --force-new-deployment` to force Fargate to pull fresh images.

### Container Health Check vs ALB Health Check

**Issue**: ECS has TWO separate health checks: (1) Container-level `healthCheck` in task definition (uses `CMD-SHELL curl ...` inside the container), and (2) ALB target group health check (HTTP from ALB to container). Both must pass for service stabilization. The container health check requires `curl` to be installed IN the Docker image.
**Symptom**: CloudWatch logs show 200 OK (ALB health check passing), but ECS events show "failed container health checks" (curl not installed in image).
**Fix**: Always include `curl` in Docker images when using `CMD-SHELL curl` health checks:
- Debian/Ubuntu: `RUN apt-get update && apt-get install -y --no-install-recommends curl`
- Alpine: `RUN apk add --no-cache curl`

### Lambda Native Extension Fails on Linux (Windows Dev)

**Issue**: CDK `local.tryBundle()` runs pip on Windows → installs Windows binary wheels (`.pyd`, `.dll`). Lambda runs Linux x86_64. Native C extensions (`lxml`, `pydantic_core`, `numpy`, `cryptography`, etc.) fail at import: `Unable to import module 'handler': No module named 'xxx._xxx'`
**Root Cause**: pip installs wheels for the current OS by default. Windows wheels are incompatible with Lambda's Linux runtime.
**Fix (preferred)**: Use `infrastructure/cdk-eagle/scripts/bundle-lambda.py` as the CDK local bundler. It detects Windows and runs `pip install --platform manylinux2014_x86_64 --implementation cp --python-version 312 --only-binary :all:` to download Linux-compatible binary wheels from PyPI.
**Fix (fallback)**: Remove native extension dependencies — replace pydantic v2 with stdlib dataclasses, etc.
**FORCE_LINUX_BUNDLE=1**: Set this env var on macOS ARM CI/CD to force Linux-targeted bundling.
**Sign of correct bundling**: Lambda code size increases (Linux manylinux binaries are often larger than Windows counterparts).

### Bedrock Model IDs and Inference Profiles

**Issue 1**: `google.gemini-1-5-flash-v1` → `ValidationException: The provided model identifier is invalid`
**Root Cause**: Google Gemini is not a standard Bedrock foundation model. Requires explicit Marketplace subscription. Also, Gemini API format (`{"contents": [...]}`) is incompatible with Claude Messages API format.

**Issue 2**: `anthropic.claude-3-5-haiku-20241022-v1:0` → `ValidationException: Invocation of model ID ... with on-demand throughput isn't supported. Retry your request with the ID or ARN of an inference profile that contains this model.`
**Root Cause**: Claude 3.5+ models (Haiku, Sonnet) require **cross-region inference profiles** for on-demand invocation in Bedrock. Direct model IDs only work with provisioned throughput.

**Fix**: Use the cross-region inference profile ID: `us.anthropic.claude-3-5-haiku-20241022-v1:0` (note `us.` prefix). For Claude 3.5 Sonnet: `us.anthropic.claude-3-5-sonnet-20241022-v2:0`.

**IAM**: Lambda role needs BOTH resources in the Bedrock policy:
```
arn:aws:bedrock:{region}:{account}:inference-profile/us.anthropic.*   ← inference profile
arn:aws:bedrock:*::foundation-model/anthropic.*                        ← underlying model
```

**Claude Messages API body format** (for use with `bedrock:invoke_model`):
```python
body = json.dumps({
    "anthropic_version": "bedrock-2023-05-31",
    "max_tokens": 2048,
    "temperature": 0.1,
    "messages": [{"role": "user", "content": prompt}],
})
# Response: result["content"][0]["text"]
```

### Git Bash Path Conversion (Windows/MSYS)

**Issue**: On Windows Git Bash, AWS CLI args starting with `/` get converted to Windows paths: `/eagle/ecs/backend-dev` → `C:/Program Files/Git/eagle/ecs/backend-dev`. Causes `InvalidParameterException` for CloudWatch log group names, S3 paths, etc.
**Fix**: Prefix commands with `MSYS_NO_PATHCONV=1`:
```bash
MSYS_NO_PATHCONV=1 aws logs describe-log-streams --log-group-name "/eagle/ecs/backend-dev"
```

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
- 3-stack CDK split (Core/Compute/CiCd) with explicit dependencies keeps stacks independent and deployable (discovered: 2026-02-16, component: cdk-eagle)
- `fromBucketName`/`fromTableName` for importing manually-created resources into CDK without conflict (discovered: 2026-02-16, component: core-stack)
- Pinned GitHub Action SHAs (not tags) for security in deploy.yml (discovered: 2026-02-16, component: deploy.yml)
- `--outputs-file outputs.json` with jq extraction cleanly pipes CDK outputs to downstream jobs (discovered: 2026-02-16, component: deploy.yml)
- Write-through in-memory cache (5-min TTL) in session_store.py avoids repeated DynamoDB reads (discovered: 2026-02-16, component: session_store)
- ECS `minHealthyPercent: 100` ensures zero-downtime rolling updates (discovered: 2026-02-16, component: compute-stack)
- Container Insights V2 via `containerInsightsV2: ecs.ContainerInsights.ENABLED` (discovered: 2026-02-16, component: compute-stack)
- Push placeholder images to ECR BEFORE first `cdk deploy` of ECS stacks — avoids 60+ min failed stabilization cycle (discovered: 2026-02-17, component: compute-stack)
- `--import-existing-resources` flag when redeploying after stack deletion with RETAIN resources (discovered: 2026-02-17, component: compute-stack)
- `aws ecs update-service --force-new-deployment` to force fresh image pulls after ECR push with same tag (discovered: 2026-02-17, component: ecs)
- `MSYS_NO_PATHCONV=1` prefix on Windows Git Bash for AWS CLI commands with `/` paths (discovered: 2026-02-17, component: tooling)

- `pip install --platform manylinux2014_x86_64 --implementation cp --python-version 312 --only-binary :all:` installs Linux Lambda-compatible binary wheels on any OS (discovered: 2026-02-20, component: lambda-bundler)
- `bundle-lambda.py` script at `infrastructure/cdk-eagle/scripts/` is the canonical CDK local bundler — detects Windows and uses --platform flag automatically (discovered: 2026-02-20)
- Lambda code size increase after platform-targeted bundling is expected and correct (Linux manylinux binaries larger than Windows counterparts) (discovered: 2026-02-20)
- `LogType='Tail'` in Lambda invoke returns base64-encoded log tail inline — far faster than polling CloudWatch for debugging (discovered: 2026-02-20)
- Cross-region inference profiles (`us.anthropic.claude-3-5-haiku-20241022-v1:0`) enable on-demand Claude 3.5+ invocation in Bedrock — direct model IDs only work with provisioned throughput (discovered: 2026-02-20)
- Bedrock inference profile IAM: need both `inference-profile/us.anthropic.*` AND `foundation-model/anthropic.*` resources (discovered: 2026-02-20)

### patterns_to_avoid
- Don't create new CDK resources that conflict with existing manual resources
- Don't use `Vpc.fromLookup()` in CI/CD pipelines
- Don't forget HOSTNAME=0.0.0.0 for containerized Next.js
- Don't use `NodeNext` module/moduleResolution in tsconfig with ts-node
- Don't append `.js` extension to TypeScript imports in CDK projects using commonjs
- Don't use static IAM keys in GitHub Actions when OIDC is available
- Don't run `pip install` directly in CDK `local.tryBundle()` on Windows — always use `bundle-lambda.py` which handles platform targeting (discovered: 2026-02-20, component: lambda-bundler)
- Don't use Bedrock model IDs from other cloud providers (Google, etc.) without verifying they're subscribed in Bedrock Marketplace — use `bedrock:ListFoundationModels` to check what's available (discovered: 2026-02-20)
- Don't use direct Anthropic model IDs (`anthropic.claude-3-5-haiku-20241022-v1:0`) for Claude 3.5+ on-demand — use the cross-region inference profile (`us.anthropic.claude-3-5-haiku-20241022-v1:0`) (discovered: 2026-02-20)
- Don't use `--only-binary :all:` without `--platform` — it restricts to wheels for the current host OS, which still misses cross-platform (discovered: 2026-02-20)
- Don't use `removalPolicy: DESTROY` on stateful resources (S3, DDB, Cognito) — only safe for log groups (discovered: 2026-02-16)
- Don't use `containerInsights` (v1) — use `containerInsightsV2` for ECS clusters (discovered: 2026-02-16)
- cdk-eagle tsconfig omits explicit moduleResolution — add `"moduleResolution": "node"` to match eval stack for consistency (discovered: 2026-02-16)
- Don't deploy ECS Fargate services with `desiredCount >= 1` before pushing images to ECR — causes 30+ min CloudFormation timeout then full stack rollback (discovered: 2026-02-17, component: compute-stack)
- Don't delete a CloudFormation stack with RETAIN ECR repos then re-create without `--import-existing-resources` — will fail on repo name conflict (discovered: 2026-02-17)
- Don't rely on ECS pulling updated `latest` tag from ECR for already-running tasks — Fargate caches images per task launch, use `--force-new-deployment` (discovered: 2026-02-17)
- Don't use `CMD-SHELL curl` in container health checks without installing curl in the image — ALB health checks may pass while container health checks fail, causing infinite task cycling (discovered: 2026-02-17)

### common_issues
- AWS credentials expire or are not configured -> all services fail
- S3 bucket name globally unique constraint -> can't reuse names across accounts
- CDK bootstrap missing -> deploy fails with cryptic asset error
- `Cannot find module '../lib/eval-stack.js'`: use commonjs module, remove .js extension
- CloudWatch log group may already exist when CDK tries to create it: use RETAIN
- CDK account comes from `CDK_DEFAULT_ACCOUNT` env var or CLI profile — must be set for `cdk synth` (discovered: 2026-02-16)
- `aws-cdk` CLI version (2.1016.1 in eval) vs library version (2.196.0) can diverge — watch for compatibility (discovered: 2026-02-16)
- cdk-eagle and eval have different CDK context flags — merging stacks would require reconciling these (discovered: 2026-02-16)
- ECS first deploy with empty ECR repos: `ApplicationLoadBalancedFargateService` requires desiredCount>=1, tasks can't pull images, CloudFormation waits 30+ min then rolls back entire stack. Fix: push placeholder images to ECR first (discovered: 2026-02-17, component: compute-stack)
- ECR repos with RETAIN survive stack deletion — re-creating stack fails with "already exists". Fix: use `cdk deploy --import-existing-resources` (discovered: 2026-02-17)
- ECS tasks use cached image digest even after pushing new `latest` tag to ECR. Fix: `aws ecs update-service --force-new-deployment` (discovered: 2026-02-17)
- Container health check (`CMD-SHELL curl`) fails silently if curl not in image, while ALB health check passes — causes infinite task cycling with no obvious error (discovered: 2026-02-17)
- Windows Git Bash converts `/eagle/ecs/...` paths to `C:/Program Files/Git/eagle/ecs/...` — use `MSYS_NO_PATHCONV=1` prefix (discovered: 2026-02-17)

### tips
- Run `/experts:aws:maintenance` before any deployment to verify connectivity
- Start with static export (simpler) and migrate to ECS only if API routes are needed
- Tag all CDK resources with Project=eagle and ManagedBy=cdk for cost tracking
- Use OIDC for GitHub Actions instead of static IAM keys
- Run `npx cdk synth` before `cdk deploy` to verify template generates correctly
- The eval CDK stack lives at `infrastructure/eval/` — run `cd infrastructure/eval && npx cdk deploy`
- `put_metric_data` supports up to 1000 metrics per call
- Environment configs (DEV/STAGING/PROD) in `config/environments.ts` use spread to inherit defaults — override only what changes (discovered: 2026-02-16)
- Frontend NEXT_PUBLIC_* env vars must be set as Docker build-args (baked at build time), not runtime env vars (discovered: 2026-02-16)
- The CiCd stack OIDC trust uses wildcard branch (`repo:gblack686/sample-multi-tenant-agent-core-app:*`) — allows deploys from any branch (discovered: 2026-02-16)
- EagleEvalStack is part of `infrastructure/cdk-eagle/` (NOT a separate project) — deploy with `cd infrastructure/cdk-eagle && npx cdk deploy EagleEvalStack` (verified: 2026-02-24)
- Eval dashboard now tracks 28 tests — test_28 (28_sdk_skill_subagent_orchestration) IS in eval-stack.ts TEST_NAMES (verified: 2026-02-24)
- Both frontend and backend ALBs are INTERNAL (publicLoadBalancer: false) — NCI VPC has no public subnets; access only via VPN/bastion (verified: 2026-02-24)
- **ECS First Deploy Checklist**: (1) Push placeholder images to ECR, (2) `cdk deploy --all`, (3) Verify health checks pass, (4) Push real images, (5) `aws ecs update-service --force-new-deployment` (discovered: 2026-02-17)
- Placeholder images only need to pass health checks: backend → FastAPI with `GET /api/health` + curl installed; frontend → Express with `GET /` + curl installed (discovered: 2026-02-17)
- When redeploying after deleting a stack with RETAIN ECR repos, always use `npx cdk deploy --import-existing-resources` (discovered: 2026-02-17)
- On Windows Git Bash, always prefix AWS CLI commands that have `/path` args with `MSYS_NO_PATHCONV=1` (discovered: 2026-02-17)
- When adding new Lambda to CDK, always wire local bundler to `bundle-lambda.py` — never use raw `pip install` in tryBundle on Windows dev machines (discovered: 2026-02-20)
- Use `LogType='Tail'` in `lambda.invoke()` to get execution logs inline — no CloudWatch polling needed for debugging (discovered: 2026-02-20)
- Before using a Bedrock model ID, verify with `bedrock.list_foundation_models()` or in the Bedrock Console — avoid assuming model IDs from other cloud providers translate to Bedrock (discovered: 2026-02-20)
- EagleEvalStack is unified into `infrastructure/cdk-eagle/` (not a separate project) — all 5 stacks deploy from one `npx cdk deploy --all` (verified: 2026-02-24, component: eval-stack)
- S3 bucket names include account ID: `eagle-documents-695681773636-dev`, `eagle-eval-artifacts-695681773636-dev` — config uses full names with account ID suffix (verified: 2026-02-24, component: environments.ts)
- VPC is fully NCI-managed and IMPORTED — CDK does not create any VPC; no public subnets exist; all ALBs are internal (verified: 2026-02-24, component: core-stack)
- Both ECS ALBs (frontend + backend) are internal (`publicLoadBalancer: false`) — NCI VPC is private-only; access requires VPN/bastion (verified: 2026-02-24, component: compute-stack)
- Eval dashboard now has 28 tests including test_28 (28_sdk_skill_subagent_orchestration) — confirmed in eval-stack.ts TEST_NAMES (verified: 2026-02-24)
