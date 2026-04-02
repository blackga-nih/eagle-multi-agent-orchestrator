import * as cdk from 'aws-cdk-lib';
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
  public readonly vpc: ec2.IVpc;
  public readonly appRole: iam.Role;
  public readonly userPool: cognito.UserPool;
  public readonly userPoolClient: cognito.UserPoolClient;

  constructor(scope: Construct, id: string, props: EagleCoreStackProps) {
    super(scope, id, props);
    const { config } = props;

    // ── DynamoDB: Eagle single-table ─────────────────────────
    const eagleTable = new dynamodb.Table(this, 'EagleTable', {
      tableName: config.eagleTableName,
      partitionKey: { name: 'PK', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'SK', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      timeToLiveAttribute: 'ttl',
      pointInTimeRecoverySpecification: { pointInTimeRecoveryEnabled: true },
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });

    // GSI1: Tenant-level session and workspace listing
    // PK=TENANT#{tenant_id}, SK=SESSION#{created_at}#{session_id}
    // Eliminates table.scan() for list_tenant_sessions() and get_tenant_usage_overview()
    eagleTable.addGlobalSecondaryIndex({
      indexName: 'GSI1',
      partitionKey: { name: 'GSI1PK', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'GSI1SK', type: dynamodb.AttributeType.STRING },
      projectionType: dynamodb.ProjectionType.ALL,
    });

    // GSI2: Tier queries and skill listing by status
    // PK=TIER#{tier} or SKILL#STATUS#{status}, SK varies by entity
    // Eliminates table.scan() for get_tenants_by_tier() and future skill queries
    eagleTable.addGlobalSecondaryIndex({
      indexName: 'GSI2',
      partitionKey: { name: 'GSI2PK', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'GSI2SK', type: dynamodb.AttributeType.STRING },
      projectionType: dynamodb.ProjectionType.ALL,
    });

    // ── VPC ──────────────────────────────────────────────────
    // Import the existing NCI EAGLE DEV VPC — SCP blocks ec2:CreateVpc directly;
    // VPCs are provisioned by the NCI networking team via Service Catalog.
    // VPC: C1-CWEB-EAGLE-DEV-VPC (vpc-09def43fcabfa4df6), CIDR 10.209.140.192/26
    // 4 private subnets across 2 AZs; egress via Transit Gateway. No public subnets.
    this.vpc = ec2.Vpc.fromLookup(this, 'Vpc', {
      vpcId: 'vpc-09def43fcabfa4df6',
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
        tenant_id: new cognito.StringAttribute({
          minLen: 1,
          maxLen: 50,
          mutable: true,
        }),
        subscription_tier: new cognito.StringAttribute({
          minLen: 1,
          maxLen: 20,
          mutable: true,
        }),
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

    // ── CloudWatch Log Groups ────────────────────────────────
    const appLogGroup = new logs.LogGroup(this, 'AppLogGroup', {
      logGroupName: '/eagle/app',
      retention: logs.RetentionDays.THREE_MONTHS,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });

    // Bedrock model invocation logs — captures per-call latency, input/output
    // tokens, model ID, and error codes for every converse() call.
    const bedrockInvocationLogGroup = new logs.LogGroup(this, 'BedrockInvocationLogGroup', {
      logGroupName: '/aws/bedrock/modelinvocations',
      retention: logs.RetentionDays.TWO_WEEKS,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // Role assumed by Bedrock service to write invocation logs.
    // NCI SCP requires power-user-* prefix + PermissionBoundary_PowerUser.
    const bedrockLoggingRole = new iam.Role(this, 'BedrockLoggingRole', {
      roleName: `power-user-eagle-bedrock-logging-${config.env}`,
      assumedBy: new iam.ServicePrincipal('bedrock.amazonaws.com'),
      permissionsBoundary: iam.ManagedPolicy.fromManagedPolicyName(
        this, 'PowerUserBoundary', 'PermissionBoundary_PowerUser',
      ),
    });

    bedrockLoggingRole.addToPolicy(new iam.PolicyStatement({
      actions: [
        'logs:CreateLogStream',
        'logs:PutLogEvents',
      ],
      resources: [
        `${bedrockInvocationLogGroup.logGroupArn}:*`,
      ],
    }));

    // ── IAM App Execution Role ───────────────────────────────
    this.appRole = new iam.Role(this, 'AppRole', {
      roleName: `eagle-app-role-${config.env}`,
      assumedBy: new iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
    });

    // DynamoDB: Full CRUD on eagle table
    this.appRole.addToPolicy(new iam.PolicyStatement({
      actions: [
        'dynamodb:GetItem',
        'dynamodb:PutItem',
        'dynamodb:UpdateItem',
        'dynamodb:DeleteItem',
        'dynamodb:Query',
        'dynamodb:Scan',
        'dynamodb:BatchWriteItem',
      ],
      resources: [
        eagleTable.tableArn,
        `${eagleTable.tableArn}/index/*`,
      ],
    }));

    // Document bucket + metadata table: permissions granted by StorageStack
    // via appRole.addToPolicy() (Sids: DocumentBucketReadWrite, MetadataTableRead)

    // Bedrock: Invoke models — Sonnet 4.6 (chat) + Haiku 4.5 (title generation).
    // To allow other models, add their ARNs here and re-deploy the core stack.
    this.appRole.addToPolicy(new iam.PolicyStatement({
      actions: [
        'bedrock:InvokeModel',
        'bedrock:InvokeModelWithResponseStream',
        'bedrock:InvokeAgent',
      ],
      resources: [
        // Sonnet 4.6 foundation model (direct invocation)
        'arn:aws:bedrock:*::foundation-model/anthropic.claude-sonnet-4-6',
        // Sonnet 4.6 cross-region inference profile (us.* prefix used by SDK)
        `arn:aws:bedrock:us-east-1:${this.account}:inference-profile/us.anthropic.claude-sonnet-4-6`,
        // Sonnet 4.5 foundation model (circuit breaker fallback)
        'arn:aws:bedrock:*::foundation-model/anthropic.claude-sonnet-4-5-20250929-v1:0',
        // Sonnet 4.5 cross-region inference profile
        `arn:aws:bedrock:us-east-1:${this.account}:inference-profile/us.anthropic.claude-sonnet-4-5-20250929-v1:0`,
        // Haiku 4.5 foundation model (last-resort fallback + title generation)
        'arn:aws:bedrock:*::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0',
        // Haiku 4.5 cross-region inference profile
        `arn:aws:bedrock:us-east-1:${this.account}:inference-profile/us.anthropic.claude-haiku-4-5-20251001-v1:0`,
        // Bedrock agents (routing, not model-specific)
        `arn:aws:bedrock:us-east-1:${this.account}:agent/*`,
      ],
    }));

    // Nova Web Grounding: web search via nova_grounding systemTool
    // Requires both InvokeModel (for the Nova model) and InvokeTool (for the system tool)
    // See: https://docs.aws.amazon.com/nova/latest/nova2-userguide/web-grounding.html
    this.appRole.addToPolicy(new iam.PolicyStatement({
      actions: ['bedrock:InvokeModel'],
      resources: [
        // Nova 2 Lite foundation model (for web grounding searches)
        'arn:aws:bedrock:*::foundation-model/amazon.nova-2-lite-v1:0',
        // Nova 2 Lite cross-region inference profile
        `arn:aws:bedrock:us-east-1:${this.account}:inference-profile/us.amazon.nova-2-lite-v1:0`,
      ],
    }));
    // nova_grounding system tool — separate permission per AWS docs
    this.appRole.addToPolicy(new iam.PolicyStatement({
      actions: ['bedrock:InvokeTool'],
      resources: [
        `arn:aws:bedrock::${this.account}:system-tool/amazon.nova_grounding`,
      ],
    }));

    // CloudWatch: App + eval logging
    this.appRole.addToPolicy(new iam.PolicyStatement({
      actions: [
        'logs:CreateLogGroup',
        'logs:CreateLogStream',
        'logs:PutLogEvents',
        'logs:GetLogEvents',
        'logs:DescribeLogStreams',
        'logs:FilterLogEvents',
      ],
      resources: [
        `arn:aws:logs:us-east-1:${this.account}:log-group:/eagle/*`,
      ],
    }));

    // Cognito: User management
    this.appRole.addToPolicy(new iam.PolicyStatement({
      actions: [
        'cognito-idp:GetUser',
        'cognito-idp:AdminGetUser',
        'cognito-idp:CreateGroup',
        'cognito-idp:AdminAddUserToGroup',
        'cognito-idp:ListUsers',
      ],
      resources: [this.userPool.userPoolArn],
    }));

    // ── Outputs ──────────────────────────────────────────────
    new cdk.CfnOutput(this, 'VpcId', {
      value: this.vpc.vpcId,
      description: 'EAGLE DEV VPC (imported)',
      exportName: `eagle-vpc-id-${config.env}`,
    });
    new cdk.CfnOutput(this, 'UserPoolId', {
      value: this.userPool.userPoolId,
      exportName: `eagle-user-pool-id-${config.env}`,
    });
    new cdk.CfnOutput(this, 'UserPoolClientId', {
      value: this.userPoolClient.userPoolClientId,
      exportName: `eagle-user-pool-client-id-${config.env}`,
    });
    new cdk.CfnOutput(this, 'AppRoleArn', {
      value: this.appRole.roleArn,
      exportName: `eagle-app-role-arn-${config.env}`,
    });
    new cdk.CfnOutput(this, 'AppLogGroupName', {
      value: appLogGroup.logGroupName,
    });
    new cdk.CfnOutput(this, 'BedrockLoggingRoleArn', {
      value: bedrockLoggingRole.roleArn,
      description: 'Role ARN for Bedrock model invocation logging',
      exportName: `eagle-bedrock-logging-role-arn-${config.env}`,
    });
    new cdk.CfnOutput(this, 'EagleTableName', {
      value: eagleTable.tableName,
      exportName: `eagle-table-name-${config.env}`,
    });
  }
}
