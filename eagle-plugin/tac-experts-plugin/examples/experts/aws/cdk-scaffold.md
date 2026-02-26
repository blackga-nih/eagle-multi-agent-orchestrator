---
description: Scaffold a new CDK stack from templates (5 stack types)
argument-hint: "<stack-type> <stack-name> — Types: core, compute, cicd, data, monitoring"
model: opus
allowed-tools: Read, Write, Glob, Grep, Bash(npx tsc:*), Bash(npx cdk:*)
---

# CDK Stack Scaffold

> Domain-specific expert extension. This file lives alongside the standard 7 expert files
> and adds a capability unique to the AWS domain.

## Purpose

Generate a production-ready CDK stack from templates. Each stack type includes IAM least-privilege,
tagging, environment configs, and cross-stack references.

## Stack Type: $ARGUMENTS

---

## Stack Templates

### Type: `core`
Foundation stack — VPC, security groups, shared resources.

```typescript
import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import { Construct } from 'constructs';

export interface CoreStackProps extends cdk.StackProps {
  readonly environment: string;
  readonly projectName: string;
}

export class CoreStack extends cdk.Stack {
  public readonly vpc: ec2.Vpc;

  constructor(scope: Construct, id: string, props: CoreStackProps) {
    super(scope, id, props);

    // VPC with private + public subnets
    this.vpc = new ec2.Vpc(this, 'Vpc', {
      maxAzs: 2,
      natGateways: props.environment === 'prod' ? 2 : 1,
      subnetConfiguration: [
        { name: 'Public', subnetType: ec2.SubnetType.PUBLIC, cidrMask: 24 },
        { name: 'Private', subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS, cidrMask: 24 },
        { name: 'Isolated', subnetType: ec2.SubnetType.PRIVATE_ISOLATED, cidrMask: 24 },
      ],
    });

    // Standard tags
    cdk.Tags.of(this).add('Project', props.projectName);
    cdk.Tags.of(this).add('Environment', props.environment);
    cdk.Tags.of(this).add('ManagedBy', 'cdk');
  }
}
```

### Type: `compute`
ECS Fargate services with ALB, auto-scaling, health checks.

```typescript
import * as cdk from 'aws-cdk-lib';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as ecr from 'aws-cdk-lib/aws-ecr';
import * as elbv2 from 'aws-cdk-lib/aws-elasticloadbalancingv2';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import { Construct } from 'constructs';

export interface ComputeStackProps extends cdk.StackProps {
  readonly vpc: ec2.Vpc;
  readonly environment: string;
  readonly cpu: number;      // 256, 512, 1024, 2048, 4096
  readonly memory: number;   // Must be compatible with CPU
}

export class ComputeStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: ComputeStackProps) {
    super(scope, id, props);

    const cluster = new ecs.Cluster(this, 'Cluster', { vpc: props.vpc });

    const repo = new ecr.Repository(this, 'Repo', {
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      lifecycleRules: [{ maxImageCount: 10 }],
    });

    const taskDef = new ecs.FargateTaskDefinition(this, 'TaskDef', {
      cpu: props.cpu,
      memoryLimitMiB: props.memory,
    });

    taskDef.addContainer('App', {
      image: ecs.ContainerImage.fromEcrRepository(repo),
      portMappings: [{ containerPort: 8000 }],
      logging: ecs.LogDrivers.awsLogs({ streamPrefix: 'app' }),
      healthCheck: {
        command: ['CMD-SHELL', 'curl -f http://localhost:8000/health || exit 1'],
        interval: cdk.Duration.seconds(30),
        retries: 3,
      },
    });

    const service = new ecs.FargateService(this, 'Service', {
      cluster,
      taskDefinition: taskDef,
      desiredCount: props.environment === 'prod' ? 2 : 1,
      assignPublicIp: false,
    });

    // ALB
    const alb = new elbv2.ApplicationLoadBalancer(this, 'ALB', {
      vpc: props.vpc,
      internetFacing: true,
    });

    const listener = alb.addListener('Listener', { port: 80 });
    listener.addTargets('Target', {
      port: 8000,
      targets: [service],
      healthCheck: { path: '/health', interval: cdk.Duration.seconds(30) },
    });

    // Auto-scaling
    const scaling = service.autoScaleTaskCount({
      minCapacity: props.environment === 'prod' ? 2 : 1,
      maxCapacity: props.environment === 'prod' ? 10 : 3,
    });
    scaling.scaleOnCpuUtilization('CpuScaling', { targetUtilizationPercent: 70 });
  }
}
```

### Type: `cicd`
GitHub Actions OIDC provider + deploy IAM role.

```typescript
import * as cdk from 'aws-cdk-lib';
import * as iam from 'aws-cdk-lib/aws-iam';
import { Construct } from 'constructs';

export interface CiCdStackProps extends cdk.StackProps {
  readonly githubOrg: string;
  readonly githubRepo: string;
  readonly ecrRepoArn: string;
  readonly ecsClusterArn: string;
  readonly ecsServiceArn: string;
}

export class CiCdStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: CiCdStackProps) {
    super(scope, id, props);

    // GitHub OIDC Provider (create once per account)
    const oidcProvider = new iam.OpenIdConnectProvider(this, 'GitHubOidc', {
      url: 'https://token.actions.githubusercontent.com',
      clientIds: ['sts.amazonaws.com'],
    });

    // Deploy role — GitHub Actions assumes this via OIDC
    const deployRole = new iam.Role(this, 'DeployRole', {
      assumedBy: new iam.WebIdentityPrincipal(
        oidcProvider.openIdConnectProviderArn,
        {
          StringEquals: {
            'token.actions.githubusercontent.com:aud': 'sts.amazonaws.com',
          },
          StringLike: {
            'token.actions.githubusercontent.com:sub':
              `repo:${props.githubOrg}/${props.githubRepo}:*`,
          },
        },
      ),
      description: 'GitHub Actions deploy role (OIDC)',
      maxSessionDuration: cdk.Duration.hours(1),
    });

    // Least-privilege: only ECR push + ECS deploy
    deployRole.addToPolicy(new iam.PolicyStatement({
      actions: [
        'ecr:GetAuthorizationToken',
        'ecr:BatchCheckLayerAvailability',
        'ecr:PutImage',
        'ecr:InitiateLayerUpload',
        'ecr:UploadLayerPart',
        'ecr:CompleteLayerUpload',
      ],
      resources: [props.ecrRepoArn],
    }));

    deployRole.addToPolicy(new iam.PolicyStatement({
      actions: ['ecs:UpdateService', 'ecs:DescribeServices'],
      resources: [props.ecsServiceArn],
    }));

    new cdk.CfnOutput(this, 'DeployRoleArn', { value: deployRole.roleArn });
  }
}
```

### Type: `data`
DynamoDB single-table + S3 bucket with lifecycle rules.

```typescript
import * as cdk from 'aws-cdk-lib';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as s3 from 'aws-cdk-lib/aws-s3';
import { Construct } from 'constructs';

export interface DataStackProps extends cdk.StackProps {
  readonly tableName: string;
  readonly bucketName: string;
  readonly environment: string;
}

export class DataStack extends cdk.Stack {
  public readonly table: dynamodb.Table;
  public readonly bucket: s3.Bucket;

  constructor(scope: Construct, id: string, props: DataStackProps) {
    super(scope, id, props);

    // Single-table design with PK/SK
    this.table = new dynamodb.Table(this, 'Table', {
      tableName: props.tableName,
      partitionKey: { name: 'PK', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'SK', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      pointInTimeRecovery: props.environment === 'prod',
      removalPolicy: props.environment === 'prod'
        ? cdk.RemovalPolicy.RETAIN
        : cdk.RemovalPolicy.DESTROY,
    });

    // GSI for queries by type
    this.table.addGlobalSecondaryIndex({
      indexName: 'GSI1',
      partitionKey: { name: 'GSI1PK', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'GSI1SK', type: dynamodb.AttributeType.STRING },
    });

    // S3 bucket with lifecycle
    this.bucket = new s3.Bucket(this, 'Bucket', {
      bucketName: props.bucketName,
      versioned: true,
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      lifecycleRules: [
        { transition: [{ storageClass: s3.StorageClass.INFREQUENT_ACCESS, transitionAfter: cdk.Duration.days(90) }] },
        { noncurrentVersionExpiration: cdk.Duration.days(30) },
      ],
      removalPolicy: props.environment === 'prod'
        ? cdk.RemovalPolicy.RETAIN
        : cdk.RemovalPolicy.DESTROY,
    });
  }
}
```

### Type: `monitoring`
CloudWatch dashboards + alarms + SNS alerts.

```typescript
import * as cdk from 'aws-cdk-lib';
import * as cloudwatch from 'aws-cdk-lib/aws-cloudwatch';
import * as sns from 'aws-cdk-lib/aws-sns';
import * as sns_subs from 'aws-cdk-lib/aws-sns-subscriptions';
import * as cw_actions from 'aws-cdk-lib/aws-cloudwatch-actions';
import { Construct } from 'constructs';

export interface MonitoringStackProps extends cdk.StackProps {
  readonly serviceName: string;
  readonly alertEmail: string;
  readonly logGroupName: string;
}

export class MonitoringStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: MonitoringStackProps) {
    super(scope, id, props);

    // SNS topic for alerts
    const alertTopic = new sns.Topic(this, 'Alerts', {
      displayName: `${props.serviceName} Alerts`,
    });
    alertTopic.addSubscription(new sns_subs.EmailSubscription(props.alertEmail));

    // Error rate alarm
    const errorMetric = new cloudwatch.Metric({
      namespace: props.serviceName,
      metricName: 'ErrorCount',
      statistic: 'Sum',
      period: cdk.Duration.minutes(5),
    });

    const errorAlarm = new cloudwatch.Alarm(this, 'ErrorAlarm', {
      metric: errorMetric,
      threshold: 10,
      evaluationPeriods: 2,
      comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
      alarmDescription: `${props.serviceName}: >10 errors in 5 minutes`,
    });
    errorAlarm.addAlarmAction(new cw_actions.SnsAction(alertTopic));

    // Dashboard
    new cloudwatch.Dashboard(this, 'Dashboard', {
      dashboardName: `${props.serviceName}-dashboard`,
      widgets: [
        [
          new cloudwatch.GraphWidget({
            title: 'Error Rate',
            left: [errorMetric],
            width: 12,
          }),
          new cloudwatch.LogQueryWidget({
            title: 'Recent Errors',
            logGroupNames: [props.logGroupName],
            queryLines: [
              'fields @timestamp, @message',
              'filter @message like /ERROR/',
              'sort @timestamp desc',
              'limit 20',
            ],
            width: 12,
          }),
        ],
      ],
    });
  }
}
```

---

## Scaffold Workflow

1. **Read $ARGUMENTS** to determine stack type and name
2. **Read** `infrastructure/cdk-eagle/config/environments.ts` for env settings
3. **Read** existing stacks for cross-reference patterns
4. **Generate** the new stack file from the template above
5. **Register** the stack in `bin/cdk-eagle.ts`
6. **Validate**: `npx tsc --noEmit && npx cdk synth --quiet`

## Validation

After scaffolding, verify:
```bash
npx tsc --noEmit          # TypeScript compiles
npx cdk synth --quiet     # CDK synthesizes
npx cdk diff              # Show what would be deployed
```
