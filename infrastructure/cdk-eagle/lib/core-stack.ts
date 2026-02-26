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
      removalPolicy: cdk.RemovalPolicy.RETAIN,
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

    // DynamoDB: Full CRUD on eagle table
    this.appRole.addToPolicy(new iam.PolicyStatement({
      sid: 'DynamoDBAccess',
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

    // Document bucket: read access for ECS backend (static ARN avoids cross-stack token cycle)
    this.appRole.addToPolicy(new iam.PolicyStatement({
      sid: 'DocumentBucketRead',
      actions: ['s3:GetObject', 's3:ListBucket'],
      resources: [
        `arn:aws:s3:::${config.documentBucketName}`,
        `arn:aws:s3:::${config.documentBucketName}/*`,
      ],
    }));

    // Metadata DynamoDB: read access for ECS backend
    this.appRole.addToPolicy(new iam.PolicyStatement({
      sid: 'DocumentMetadataRead',
      actions: ['dynamodb:GetItem', 'dynamodb:Query', 'dynamodb:Scan'],
      resources: [
        `arn:aws:dynamodb:${config.region}:${this.account}:table/${config.documentMetadataTableName}`,
        `arn:aws:dynamodb:${config.region}:${this.account}:table/${config.documentMetadataTableName}/index/*`,
      ],
    }));

    // Bedrock: Invoke models — restricted to Haiku 4.5 only to prevent Opus/Sonnet charges.
    // To allow other models, add their ARNs here and re-deploy the core stack.
    this.appRole.addToPolicy(new iam.PolicyStatement({
      sid: 'BedrockInvoke',
      actions: [
        'bedrock:InvokeModel',
        'bedrock:InvokeModelWithResponseStream',
        'bedrock:InvokeAgent',
      ],
      resources: [
        // Haiku 4.5 foundation model (direct invocation)
        'arn:aws:bedrock:*::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0',
        // Haiku 4.5 cross-region inference profile (us.* prefix used by SDK)
        `arn:aws:bedrock:us-east-1:${this.account}:inference-profile/us.anthropic.claude-haiku-4-5-20251001-v1:0`,
        // Bedrock agents (routing, not model-specific)
        `arn:aws:bedrock:us-east-1:${this.account}:agent/*`,
      ],
    }));

    // CloudWatch: App + eval logging
    this.appRole.addToPolicy(new iam.PolicyStatement({
      sid: 'CloudWatchLogs',
      actions: [
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
      sid: 'CognitoUserManagement',
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
    new cdk.CfnOutput(this, 'EagleTableName', {
      value: eagleTable.tableName,
      exportName: `eagle-table-name-${config.env}`,
    });
  }
}
