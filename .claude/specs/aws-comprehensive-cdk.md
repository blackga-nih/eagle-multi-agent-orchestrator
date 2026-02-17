# Comprehensive CDK Plan: Full AWS Resource Management

## Decisions Locked In

| Decision | Choice |
|----------|--------|
| Compute | **ECS Fargate** (scalable, production-ready) |
| Cognito | **New CDK-managed pool** (clean state, repeatable) |
| GitHub owner | **gblack686** |
| DynamoDB | **Option B** — Migrate all to unified `eagle` table, delete legacy tables |
| CDK Language | **TypeScript** (aligns with existing eval stack) |

---

## Overview

Two-part plan:
1. **Phase 0**: Migrate legacy DynamoDBStore → unified `eagle` table (Python backend refactor)
2. **Phases 1-5**: Build comprehensive CDK stacks (TypeScript infrastructure)

### Target Architecture

```
infrastructure/cdk-eagle/                # NEW unified CDK project
  bin/eagle.ts                           # CDK app entry — instantiates all stacks
  lib/
    core-stack.ts                        # Storage + Auth + IAM
    compute-stack.ts                     # ECS Fargate + ECR + ALB
    cicd-stack.ts                        # OIDC + GitHub Actions role
  config/
    environments.ts                      # Per-env config (dev, staging, prod)
  cdk.json
  tsconfig.json
  package.json

infrastructure/eval/                     # EXISTING — unchanged
  lib/eval-stack.ts                      # EagleEvalStack (S3, CloudWatch, SNS)
```

### Stack Dependency Graph

```
EagleCiCdStack (independent — deploy first)

EagleCoreStack (storage, auth, IAM)
    ↓
EagleComputeStack (depends on Core for IAM roles, Cognito, VPC)

EagleEvalStack (existing — unchanged)
```

---

## Phase 0: DynamoDB Migration (Backend Refactor)

### Problem

Two parallel session systems writing to 3 different DynamoDB tables:

| System | File | Tables | Status |
|--------|------|--------|--------|
| Legacy `DynamoDBStore` | `dynamodb_store.py` | `tenant-sessions`, `tenant-usage` | Partially dead code |
| New `session_store` | `session_store.py` | `eagle` (unified PK/SK) | Active, modern |

### Current DynamoDBStore Usage (Only Live Calls)

| Method | Caller | Sync/Async | Replacement |
|--------|--------|------------|-------------|
| `get_tenant_usage()` | `main.py` (2 endpoints) | Sync | `session_store.get_usage_summary()` |
| `get_tenant_sessions()` | `main.py` (1 endpoint) | Sync | `session_store.list_sessions()` |
| `get_tenant_usage_metrics()` | `admin_cost_service.py`, `cost_attribution.py` | Async | New `session_store.get_usage_metrics()` |
| `get_all_tenants()` | `cost_attribution.py` | Async | New `session_store.get_all_tenants()` |
| `get_tenants_by_tier()` | `cost_attribution.py` | Async | New `session_store.get_tenants_by_tier()` |
| `store_usage_metric()` | `cost_attribution.py` | Async | Extend `session_store.record_usage()` |

**Dead code** (never called externally): `create_session()`, `get_session()`, `update_session_activity()`, `record_usage_metric()`

**streaming_routes.py**: Receives `DynamoDBStore` as parameter but **never calls any method on it** — remove parameter entirely.

**subscription_service.py**: Bypasses DynamoDBStore, directly accesses `store.usage_table` attribute — refactor to use session_store.

### Migration Steps

#### Step 0.1: Add Missing Functions to `session_store.py`

New functions to add (all use the `eagle` table with PK/SK patterns):

```python
# --- Tenant-level queries (for admin/cost services) ---

def get_usage_metrics(
    tenant_id: str,
    start_date: datetime,
    end_date: datetime
) -> List[Dict[str, Any]]:
    """Query USAGE# records for a tenant within a date range."""
    table = _get_table()
    response = table.query(
        KeyConditionExpression="PK = :pk AND SK BETWEEN :start AND :end",
        ExpressionAttributeValues={
            ":pk": f"USAGE#{tenant_id}",
            ":start": f"USAGE#{start_date.strftime('%Y-%m-%d')}",
            ":end": f"USAGE#{end_date.strftime('%Y-%m-%d')}~",  # ~ sorts after all dates
        }
    )
    return [_serialize_item(i) for i in response.get("Items", [])]


def get_all_tenants() -> List[Dict[str, str]]:
    """Scan for unique tenant IDs across all SESSION# records."""
    table = _get_table()
    response = table.scan(
        FilterExpression="begins_with(PK, :prefix)",
        ExpressionAttributeValues={":prefix": "SESSION#"},
        ProjectionExpression="PK"
    )
    tenant_ids = set()
    for item in response.get("Items", []):
        parts = item["PK"].split("#")
        if len(parts) >= 2:
            tenant_ids.add(parts[1])
    return [{"tenant_id": tid} for tid in tenant_ids]


def get_tenants_by_tier(tier: str) -> List[Dict[str, str]]:
    """Scan sessions filtered by subscription tier metadata."""
    table = _get_table()
    response = table.scan(
        FilterExpression="begins_with(SK, :prefix) AND metadata.subscription_tier = :tier",
        ExpressionAttributeValues={
            ":prefix": "SESSION#",
            ":tier": tier,
        },
        ProjectionExpression="PK"
    )
    tenant_ids = set()
    for item in response.get("Items", []):
        parts = item["PK"].split("#")
        if len(parts) >= 2:
            tenant_ids.add(parts[1])
    return [{"tenant_id": tid} for tid in tenant_ids]


def store_cost_metric(
    tenant_id: str,
    user_id: str,
    session_id: str,
    metric_type: str,
    value: float,
    **metadata
) -> None:
    """Store a cost/usage metric in the eagle table."""
    now = datetime.utcnow()
    item = {
        "PK": f"COST#{tenant_id}",
        "SK": f"COST#{now.strftime('%Y-%m-%d')}#{int(now.timestamp() * 1000)}",
        "tenant_id": tenant_id,
        "user_id": user_id,
        "session_id": session_id,
        "metric_type": metric_type,
        "value": Decimal(str(value)),
        "created_at": now.isoformat(),
        **{k: v for k, v in metadata.items()},
    }
    table = _get_table()
    table.put_item(Item=item)
```

#### Step 0.2: Update Consumers

| File | Change |
|------|--------|
| `main.py` | Replace `store = DynamoDBStore()` with imports from `session_store`. Update 3 legacy endpoints to call `session_store.get_usage_summary()` and `session_store.list_sessions()`. |
| `streaming_routes.py` | Remove `store: DynamoDBStore` parameter from `create_streaming_router()`. Remove from `stream_generator()`. |
| `admin_cost_service.py` | Replace `self.dynamodb_store = DynamoDBStore()` with `from app import session_store`. Call `session_store.get_usage_metrics()`. |
| `cost_attribution.py` | Replace `self.dynamodb_store = DynamoDBStore()` with `from app import session_store`. Call `session_store.get_all_tenants()`, `session_store.get_tenants_by_tier()`, `session_store.store_cost_metric()`. |
| `subscription_service.py` | Replace `self.store = dynamodb_store` + direct table access with `session_store.record_usage()` calls. |
| `config.py` | Remove `SESSIONS_TABLE` and `USAGE_TABLE` (keep `EAGLE_SESSIONS_TABLE`). |

#### Step 0.3: Delete Legacy Code

- Delete `server/app/dynamodb_store.py`
- Remove all `from .dynamodb_store import DynamoDBStore` imports
- Remove `SESSIONS_TABLE` and `USAGE_TABLE` from `.env.example`

#### Step 0.4: Verify

- Run existing eval suite: `cd server && python -m pytest tests/test_eagle_sdk_eval.py`
- Test legacy endpoints still work with new session_store backend
- Confirm no references to `tenant-sessions` or `tenant-usage` remain

---

## Phase 1: CDK Project Setup (30 min)

### Create Project

```bash
mkdir -p infrastructure/cdk-eagle
cd infrastructure/cdk-eagle
npx cdk init app --language typescript
```

### Dependencies

```json
{
  "dependencies": {
    "aws-cdk-lib": "^2.196.0",
    "constructs": "^10.0.0"
  }
}
```

### Config: `config/environments.ts`

```typescript
export interface EagleConfig {
  env: string;
  account: string;
  region: string;

  // Storage (import existing)
  eagleTableName: string;
  docsBucketName: string;

  // Compute
  vpcMaxAzs: number;
  natGateways: number;
  backendCpu: number;
  backendMemory: number;
  frontendCpu: number;
  frontendMemory: number;
  desiredCount: number;
  maxCount: number;

  // CI/CD
  githubOwner: string;
  githubRepo: string;
}

export const DEV_CONFIG: EagleConfig = {
  env: 'dev',
  account: process.env.CDK_DEFAULT_ACCOUNT!,
  region: 'us-east-1',

  eagleTableName: 'eagle',
  docsBucketName: 'nci-documents',

  vpcMaxAzs: 2,
  natGateways: 1,
  backendCpu: 512,
  backendMemory: 1024,
  frontendCpu: 256,
  frontendMemory: 512,
  desiredCount: 1,
  maxCount: 4,

  githubOwner: 'gblack686',
  githubRepo: 'sample-multi-tenant-agent-core-app',
};
```

### CDK App: `bin/eagle.ts`

```typescript
import * as cdk from 'aws-cdk-lib';
import { EagleCoreStack } from '../lib/core-stack';
import { EagleComputeStack } from '../lib/compute-stack';
import { EagleCiCdStack } from '../lib/cicd-stack';
import { DEV_CONFIG } from '../config/environments';

const app = new cdk.App();
const env = { account: DEV_CONFIG.account, region: DEV_CONFIG.region };

const cicd = new EagleCiCdStack(app, 'EagleCiCdStack', {
  env, config: DEV_CONFIG,
});

const core = new EagleCoreStack(app, 'EagleCoreStack', {
  env, config: DEV_CONFIG,
});

const compute = new EagleComputeStack(app, 'EagleComputeStack', {
  env, config: DEV_CONFIG,
  vpc: core.vpc,
  appRole: core.appRole,
  userPoolId: core.userPool.userPoolId,
  userPoolClientId: core.userPoolClient.userPoolClientId,
});
compute.addDependency(core);

app.synth();
```

---

## Phase 2: EagleCoreStack (1-2 hours)

### Resources

| Resource | Action | Name |
|----------|--------|------|
| S3 Bucket | **Import** | `nci-documents` |
| DynamoDB Table | **Import** | `eagle` |
| Cognito User Pool | **Create** | `eagle-users-{env}` |
| Cognito Client | **Create** | `eagle-app-client-{env}` |
| CloudWatch Log Group | **Create** | `/eagle/app` |
| IAM Role | **Create** | `eagle-app-role-{env}` |
| VPC | **Create** | `eagle-vpc-{env}` |

### Implementation: `lib/core-stack.ts`

```typescript
import * as cdk from 'aws-cdk-lib';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as cognito from 'aws-cdk-lib/aws-cognito';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import { Construct } from 'constructs';
import { EagleConfig } from '../config/environments';

export interface EagleCoreStackProps extends cdk.StackProps {
  config: EagleConfig;
}

export class EagleCoreStack extends cdk.Stack {
  public readonly vpc: ec2.Vpc;
  public readonly appRole: iam.Role;
  public readonly userPool: cognito.UserPool;
  public readonly userPoolClient: cognito.UserPoolClient;

  constructor(scope: Construct, id: string, props: EagleCoreStackProps) {
    super(scope, id, props);
    const { config } = props;

    // ── Import existing resources ────────────────────────────
    const docsBucket = s3.Bucket.fromBucketName(
      this, 'DocsBucket', config.docsBucketName
    );
    const eagleTable = dynamodb.Table.fromTableName(
      this, 'EagleTable', config.eagleTableName
    );

    // ── VPC ──────────────────────────────────────────────────
    this.vpc = new ec2.Vpc(this, 'Vpc', {
      vpcName: `eagle-vpc-${config.env}`,
      maxAzs: config.vpcMaxAzs,
      natGateways: config.natGateways,
    });

    // ── Cognito User Pool ────────────────────────────────────
    this.userPool = new cognito.UserPool(this, 'UserPool', {
      userPoolName: `eagle-users-${config.env}`,
      signInAliases: { email: true },
      autoVerify: { email: true },
      selfSignUpEnabled: true,
      standardAttributes: {
        email: { required: true, mutable: true },
        givenName: { required: true, mutable: true },
        familyName: { required: true, mutable: true },
      },
      customAttributes: {
        tenant_id: new cognito.StringAttribute({ minLen: 1, maxLen: 50, mutable: true }),
        subscription_tier: new cognito.StringAttribute({ minLen: 1, maxLen: 20, mutable: true }),
      },
      passwordPolicy: {
        minLength: 8,
        requireLowercase: true,
        requireUppercase: true,
        requireDigits: true,
        requireSymbols: false,
      },
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });

    this.userPoolClient = this.userPool.addClient('AppClient', {
      userPoolClientName: `eagle-app-client-${config.env}`,
      authFlows: {
        userPassword: true,
        userSrp: true,
        adminUserPassword: true,
      },
      generateSecret: false,
      accessTokenValidity: cdk.Duration.hours(1),
      idTokenValidity: cdk.Duration.hours(1),
      refreshTokenValidity: cdk.Duration.days(30),
    });

    // ── CloudWatch Log Group ─────────────────────────────────
    const appLogGroup = new logs.LogGroup(this, 'AppLogGroup', {
      logGroupName: '/eagle/app',
      retention: logs.RetentionDays.THREE_MONTHS,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });

    // ── IAM App Execution Role ───────────────────────────────
    this.appRole = new iam.Role(this, 'AppRole', {
      roleName: `eagle-app-role-${config.env}`,
      assumedBy: new iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
    });

    // S3: Document operations scoped to eagle/ prefix
    this.appRole.addToPolicy(new iam.PolicyStatement({
      actions: ['s3:GetObject', 's3:PutObject', 's3:DeleteObject', 's3:ListBucket'],
      resources: [
        docsBucket.bucketArn,
        `${docsBucket.bucketArn}/eagle/*`,
      ],
    }));

    // DynamoDB: Full CRUD on eagle table
    this.appRole.addToPolicy(new iam.PolicyStatement({
      actions: [
        'dynamodb:GetItem', 'dynamodb:PutItem', 'dynamodb:UpdateItem',
        'dynamodb:DeleteItem', 'dynamodb:Query', 'dynamodb:Scan',
        'dynamodb:BatchWriteItem',
      ],
      resources: [eagleTable.tableArn],
    }));

    // Bedrock: Invoke models
    this.appRole.addToPolicy(new iam.PolicyStatement({
      actions: [
        'bedrock:InvokeModel', 'bedrock:InvokeModelWithResponseStream',
        'bedrock:InvokeAgent',
      ],
      resources: [
        'arn:aws:bedrock:us-east-1::foundation-model/anthropic.*',
        `arn:aws:bedrock:us-east-1:${this.account}:agent/*`,
      ],
    }));

    // CloudWatch: App + eval logging
    this.appRole.addToPolicy(new iam.PolicyStatement({
      actions: [
        'logs:CreateLogStream', 'logs:PutLogEvents',
        'logs:GetLogEvents', 'logs:DescribeLogStreams',
        'logs:FilterLogEvents',
      ],
      resources: [`arn:aws:logs:us-east-1:${this.account}:log-group:/eagle/*`],
    }));

    // Cognito: User management
    this.appRole.addToPolicy(new iam.PolicyStatement({
      actions: [
        'cognito-idp:GetUser', 'cognito-idp:AdminGetUser',
        'cognito-idp:CreateGroup', 'cognito-idp:AdminAddUserToGroup',
      ],
      resources: [this.userPool.userPoolArn],
    }));

    // ── Outputs ──────────────────────────────────────────────
    new cdk.CfnOutput(this, 'VpcId', { value: this.vpc.vpcId });
    new cdk.CfnOutput(this, 'UserPoolId', { value: this.userPool.userPoolId });
    new cdk.CfnOutput(this, 'UserPoolClientId', { value: this.userPoolClient.userPoolClientId });
    new cdk.CfnOutput(this, 'AppRoleArn', { value: this.appRole.roleArn });
    new cdk.CfnOutput(this, 'AppLogGroupName', { value: appLogGroup.logGroupName });
  }
}
```

---

## Phase 3: EagleCiCdStack (1 hour)

### Resources

| Resource | Name |
|----------|------|
| OIDC Provider | `token.actions.githubusercontent.com` |
| IAM Role | `eagle-github-actions-{env}` |

### Implementation: `lib/cicd-stack.ts`

```typescript
import * as cdk from 'aws-cdk-lib';
import * as iam from 'aws-cdk-lib/aws-iam';
import { Construct } from 'constructs';
import { EagleConfig } from '../config/environments';

export interface EagleCiCdStackProps extends cdk.StackProps {
  config: EagleConfig;
}

export class EagleCiCdStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: EagleCiCdStackProps) {
    super(scope, id, props);
    const { config } = props;

    const githubProvider = new iam.OpenIdConnectProvider(this, 'GitHubOIDC', {
      url: 'https://token.actions.githubusercontent.com',
      clientIds: ['sts.amazonaws.com'],
    });

    const deployRole = new iam.Role(this, 'GitHubActionsRole', {
      roleName: `eagle-github-actions-${config.env}`,
      assumedBy: new iam.OpenIdConnectPrincipal(githubProvider, {
        StringEquals: {
          'token.actions.githubusercontent.com:aud': 'sts.amazonaws.com',
        },
        StringLike: {
          'token.actions.githubusercontent.com:sub':
            `repo:${config.githubOwner}/${config.githubRepo}:ref:refs/heads/main`,
        },
      }),
    });

    // CDK deploy permissions
    deployRole.addToPolicy(new iam.PolicyStatement({
      actions: [
        'cloudformation:*', 'ssm:GetParameter', 'sts:AssumeRole',
        's3:*',  // CDK assets bucket
      ],
      resources: ['*'],
    }));

    // ECR push
    deployRole.addToPolicy(new iam.PolicyStatement({
      actions: [
        'ecr:GetAuthorizationToken', 'ecr:BatchCheckLayerAvailability',
        'ecr:GetDownloadUrlForLayer', 'ecr:PutImage',
        'ecr:InitiateLayerUpload', 'ecr:UploadLayerPart',
        'ecr:CompleteLayerUpload', 'ecr:BatchGetImage',
      ],
      resources: ['*'],
    }));

    // ECS deploy
    deployRole.addToPolicy(new iam.PolicyStatement({
      actions: [
        'ecs:UpdateService', 'ecs:DescribeServices',
        'ecs:DescribeTaskDefinition', 'ecs:RegisterTaskDefinition',
        'iam:PassRole',
      ],
      resources: ['*'],
    }));

    new cdk.CfnOutput(this, 'DeployRoleArn', { value: deployRole.roleArn });
  }
}
```

### GitHub Actions Update

Replace in `.github/workflows/deploy.yml`:
```yaml
- uses: aws-actions/configure-aws-credentials@v4
  with:
    role-to-assume: arn:aws:iam::{ACCOUNT_ID}:role/eagle-github-actions-dev
    aws-region: us-east-1
    # Remove: aws-access-key-id, aws-secret-access-key
```

---

## Phase 4: EagleComputeStack — ECS Fargate (2-3 hours)

### Resources

| Resource | Name |
|----------|------|
| ECR Repository (backend) | `eagle-backend-{env}` |
| ECR Repository (frontend) | `eagle-frontend-{env}` |
| ECS Cluster | `eagle-{env}` |
| Backend Fargate Service | `eagle-backend-{env}` |
| Frontend Fargate Service | `eagle-frontend-{env}` |
| ALB (public) | Auto-created by pattern |

### Implementation: `lib/compute-stack.ts`

```typescript
import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as ecr from 'aws-cdk-lib/aws-ecr';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as ecs_patterns from 'aws-cdk-lib/aws-ecs-patterns';
import { Construct } from 'constructs';
import { EagleConfig } from '../config/environments';

export interface EagleComputeStackProps extends cdk.StackProps {
  config: EagleConfig;
  vpc: ec2.Vpc;
  appRole: iam.Role;
  userPoolId: string;
  userPoolClientId: string;
}

export class EagleComputeStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: EagleComputeStackProps) {
    super(scope, id, props);
    const { config, vpc, appRole } = props;

    // ── ECR Repositories ─────────────────────────────────────
    const backendRepo = new ecr.Repository(this, 'BackendRepo', {
      repositoryName: `eagle-backend-${config.env}`,
      lifecycleRules: [{ maxImageCount: 10 }],
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });

    const frontendRepo = new ecr.Repository(this, 'FrontendRepo', {
      repositoryName: `eagle-frontend-${config.env}`,
      lifecycleRules: [{ maxImageCount: 10 }],
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });

    // ── ECS Cluster ──────────────────────────────────────────
    const cluster = new ecs.Cluster(this, 'Cluster', {
      clusterName: `eagle-${config.env}`,
      vpc,
      containerInsights: true,
    });

    // ── Backend Fargate Service ──────────────────────────────
    const backendService = new ecs_patterns.ApplicationLoadBalancedFargateService(
      this, 'BackendService', {
        cluster,
        serviceName: `eagle-backend-${config.env}`,
        cpu: config.backendCpu,
        memoryLimitMiB: config.backendMemory,
        desiredCount: config.desiredCount,
        taskImageOptions: {
          image: ecs.ContainerImage.fromEcrRepository(backendRepo),
          containerPort: 8000,
          environment: {
            EAGLE_SESSIONS_TABLE: config.eagleTableName,
            S3_BUCKET: config.docsBucketName,
            S3_PREFIX: 'eagle/',
            AWS_REGION: config.region,
            USE_BEDROCK: 'true',
            REQUIRE_AUTH: 'true',
            USE_PERSISTENT_SESSIONS: 'true',
            DEV_MODE: 'false',
            COGNITO_USER_POOL_ID: props.userPoolId,
            COGNITO_CLIENT_ID: props.userPoolClientId,
          },
          taskRole: appRole,
        },
        publicLoadBalancer: false,  // Internal — frontend proxies
      },
    );

    // Backend health check
    backendService.targetGroup.configureHealthCheck({
      path: '/api/health',
      healthyThresholdCount: 2,
      unhealthyThresholdCount: 3,
      interval: cdk.Duration.seconds(30),
    });

    // ── Frontend Fargate Service ─────────────────────────────
    const frontendService = new ecs_patterns.ApplicationLoadBalancedFargateService(
      this, 'FrontendService', {
        cluster,
        serviceName: `eagle-frontend-${config.env}`,
        cpu: config.frontendCpu,
        memoryLimitMiB: config.frontendMemory,
        desiredCount: config.desiredCount,
        taskImageOptions: {
          image: ecs.ContainerImage.fromEcrRepository(frontendRepo),
          containerPort: 3000,
          environment: {
            FASTAPI_URL: `http://${backendService.loadBalancer.loadBalancerDnsName}`,
            HOSTNAME: '0.0.0.0',
            NODE_ENV: 'production',
            NEXT_PUBLIC_COGNITO_USER_POOL_ID: props.userPoolId,
            NEXT_PUBLIC_COGNITO_CLIENT_ID: props.userPoolClientId,
            NEXT_PUBLIC_COGNITO_REGION: config.region,
          },
        },
        publicLoadBalancer: true,   // Public-facing
      },
    );

    // Frontend health check
    frontendService.targetGroup.configureHealthCheck({
      path: '/',
      healthyThresholdCount: 2,
      unhealthyThresholdCount: 3,
      interval: cdk.Duration.seconds(30),
    });

    // ── Auto-Scaling ─────────────────────────────────────────
    const backendScaling = backendService.service.autoScaleTaskCount({
      minCapacity: config.desiredCount,
      maxCapacity: config.maxCount,
    });
    backendScaling.scaleOnCpuUtilization('BackendCpuScaling', {
      targetUtilizationPercent: 70,
    });

    const frontendScaling = frontendService.service.autoScaleTaskCount({
      minCapacity: config.desiredCount,
      maxCapacity: config.maxCount,
    });
    frontendScaling.scaleOnCpuUtilization('FrontendCpuScaling', {
      targetUtilizationPercent: 70,
    });

    // ── Outputs ──────────────────────────────────────────────
    new cdk.CfnOutput(this, 'BackendRepoUri', { value: backendRepo.repositoryUri });
    new cdk.CfnOutput(this, 'FrontendRepoUri', { value: frontendRepo.repositoryUri });
    new cdk.CfnOutput(this, 'ClusterName', { value: cluster.clusterName });
    new cdk.CfnOutput(this, 'FrontendUrl', {
      value: `http://${frontendService.loadBalancer.loadBalancerDnsName}`,
    });
    new cdk.CfnOutput(this, 'BackendUrl', {
      value: `http://${backendService.loadBalancer.loadBalancerDnsName}`,
    });
  }
}
```

---

## Phase 5: Integration + Cleanup (1 hour)

1. Update `deploy.yml` to use OIDC + ECR push + ECS deploy
2. Update `deployment/docker/Dockerfile.backend` for ECS (no changes needed — same image)
3. Add `output: 'standalone'` to `client/next.config.mjs` for Fargate
4. Update Dockerfile for frontend (multi-stage standalone build)
5. Deprecate `infrastructure/cdk/` (stale Python reference stack)
6. Delete legacy tables `tenant-sessions` and `tenant-usage` from AWS Console (after migration verified)
7. Remove `SESSIONS_TABLE`, `USAGE_TABLE` from all env files
8. Update `docs/codebase-structure.md`
9. Run `/experts:aws:maintenance` to verify

---

## Implementation Order Summary

| Phase | What | Effort | Prereqs |
|-------|------|--------|---------|
| **0** | DynamoDB migration — refactor `DynamoDBStore` → `session_store` | 2-3 hours | None |
| **1** | CDK project setup (`infrastructure/cdk-eagle/`) | 30 min | Phase 0 done |
| **2** | EagleCoreStack (VPC, Cognito, IAM, imports) | 1-2 hours | Phase 1 |
| **3** | EagleCiCdStack (OIDC, GitHub Actions role) | 1 hour | Phase 1 |
| **4** | EagleComputeStack (ECR, ECS Fargate, ALB) | 2-3 hours | Phase 2 |
| **5** | Integration, cleanup, deploy.yml update | 1 hour | Phases 2-4 |

**Total: ~8-11 hours**

---

## Cost Estimate (Dev)

| Resource | Monthly Cost |
|----------|-------------|
| S3 (nci-documents) | ~$0.50 |
| S3 (eval-artifacts) | ~$0.50 |
| DynamoDB (eagle, on-demand) | ~$1-5 |
| CloudWatch Logs | ~$0.50 |
| CloudWatch Dashboard | $3.00 |
| Cognito | Free (< 50k MAU) |
| Bedrock (Haiku/Sonnet) | ~$5-20 |
| **VPC + NAT Gateway** | **~$32** |
| **ECS Fargate (backend 512/1024)** | **~$18** |
| **ECS Fargate (frontend 256/512)** | **~$9** |
| **ALB** | **~$16** |
| OIDC Provider | Free |
| ECR | ~$1 |
| **Total** | **~$87-106/mo** |

---

## Rollback Plan

1. **CDK RETAIN policies** — S3, DynamoDB, Cognito persist if stacks deleted
2. **Lightsail still works** — `deployment/scripts/deploy-lightsail.sh` unchanged
3. **DynamoDB migration reversible** — legacy tables can be re-imported until deleted
4. **Git revert** — all CDK code is version-controlled

---

## What Gets Deleted/Deprecated

| Item | Action |
|------|--------|
| `server/app/dynamodb_store.py` | **Delete** (replaced by session_store.py) |
| `infrastructure/cdk/` (Python) | **Deprecate** (keep as reference, not deployed) |
| DynamoDB `tenant-sessions` | **Delete from AWS** (after Phase 0 verified) |
| DynamoDB `tenant-usage` | **Delete from AWS** (after Phase 0 verified) |
| Static IAM keys in GitHub | **Remove** (replaced by OIDC) |
| `SESSIONS_TABLE` env var | **Remove** |
| `USAGE_TABLE` env var | **Remove** |
| `deploy-lightsail.sh` | **Keep** (fallback) |
