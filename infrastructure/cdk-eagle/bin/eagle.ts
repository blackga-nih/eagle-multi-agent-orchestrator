#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { EagleCoreStack } from '../lib/core-stack';
import { EagleComputeStack } from '../lib/compute-stack';
import { EagleStorageStack } from '../lib/storage-stack';
import { EagleCiCdStack } from '../lib/cicd-stack';
import { EagleEvalStack } from '../lib/eval-stack';
import { EagleBackupStack } from '../lib/backup-stack';
import { EagleCostStack } from '../lib/cost-stack';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import { DEV_CONFIG, QA_CONFIG } from '../config/environments';

const app = new cdk.App();
const env = { account: DEV_CONFIG.account, region: DEV_CONFIG.region };

// DefaultStackSynthesizer with NCI-compliant power-user-cdk-* role names.
// CDKToolkit bootstrap was deployed with these renamed roles (power-user-cdk-*)
// so that NCIAWSPowerUserAccess (restricted to iam:CreateRole on power-user* only)
// could self-service bootstrap without admin help.
const ACCOUNT = DEV_CONFIG.account;
const synthesizer = new cdk.DefaultStackSynthesizer({
  deployRoleArn:                  `arn:aws:iam::${ACCOUNT}:role/power-user-cdk-deploy-${ACCOUNT}`,
  fileAssetPublishingRoleArn:     `arn:aws:iam::${ACCOUNT}:role/power-user-cdk-file-pub-${ACCOUNT}`,
  imageAssetPublishingRoleArn:    `arn:aws:iam::${ACCOUNT}:role/power-user-cdk-img-pub-${ACCOUNT}`,
  cloudFormationExecutionRole:    `arn:aws:iam::${ACCOUNT}:role/power-user-cdk-cfn-exec-${ACCOUNT}`,
  lookupRoleArn:                  `arn:aws:iam::${ACCOUNT}:role/power-user-cdk-lookup-${ACCOUNT}`,
  bootstrapStackVersionSsmParameter: '/cdk-bootstrap/hnb659fds/version',
  generateBootstrapVersionRule: false,
});

// CI/CD stack is independent — deploy first
const cicd = new EagleCiCdStack(app, 'EagleCiCdStack', {
  env,
  synthesizer,
  config: DEV_CONFIG,
  description: 'EAGLE CI/CD — GitHub Actions OIDC federation and deploy role',
});

// Core stack: VPC, Cognito, IAM, imports existing S3/DDB
const core = new EagleCoreStack(app, 'EagleCoreStack', {
  env,
  synthesizer,
  config: DEV_CONFIG,
  description: 'EAGLE Core — VPC, Cognito, IAM, storage imports',
});

// Storage stack depends on Core for appRole
const storage = new EagleStorageStack(app, 'EagleStorageStack', {
  env,
  synthesizer,
  config: DEV_CONFIG,
  appRole: core.appRole,
  description: 'EAGLE Storage — Document bucket, metadata DynamoDB, extraction Lambda',
});
storage.addDependency(core);

// Compute stack depends on Core for VPC, IAM role, Cognito IDs + Storage for bucket/table names
const compute = new EagleComputeStack(app, 'EagleComputeStack', {
  env,
  synthesizer,
  config: DEV_CONFIG,
  vpc: core.vpc,
  appRole: core.appRole,
  userPoolId: core.userPool.userPoolId,
  userPoolClientId: core.userPoolClient.userPoolClientId,
  documentBucketName: storage.documentBucket.bucketName,
  metadataTableName: storage.metadataTable.tableName,
  description: 'EAGLE Compute — ECS Fargate, ECR, ALB',
});
compute.addDependency(core);
compute.addDependency(storage);

// Eval stack is independent — no cross-stack dependencies
const evalStack = new EagleEvalStack(app, 'EagleEvalStack', {
  env,
  synthesizer,
  config: DEV_CONFIG,
  description: 'EAGLE Eval — S3 artifacts, CloudWatch dashboard, SNS alerts',
});

// Backup stack is independent — targets resources by ARN from config
const backup = new EagleBackupStack(app, 'EagleBackupStack', {
  env,
  synthesizer,
  config: DEV_CONFIG,
  description: 'EAGLE Backup — hourly DynamoDB snapshots + daily S3, 7/30-day retention',
});

// Cost stack is independent — AWS Budgets alerts for Bedrock daily spend
const cost = new EagleCostStack(app, 'EagleCostStack', {
  env,
  synthesizer,
  config: DEV_CONFIG,
  alertEmails: ['blackga@nih.gov', 'hoquemi@nih.gov'],
  bedrockDailyLimitUsd: 20,
  description: 'EAGLE Cost — AWS Budgets alerts (daily Bedrock spend > $20)',
});

// ── QA Compute Stack (separate VPC, shared Cognito/IAM/Storage) ──
// VPC lookup needs a Stack scope — use a dedicated lightweight stack
const qaLookup = new cdk.Stack(app, 'EagleQaLookup', { env, synthesizer });
const qaVpc = ec2.Vpc.fromLookup(qaLookup, 'QaVpc', { vpcId: QA_CONFIG.vpcId });

const qaCompute = new EagleComputeStack(app, 'EagleComputeStackQA', {
  env,
  synthesizer,
  config: QA_CONFIG,
  vpc: qaVpc,
  appRole: core.appRole,
  userPoolId: core.userPool.userPoolId,
  userPoolClientId: core.userPoolClient.userPoolClientId,
  documentBucketName: storage.documentBucket.bucketName,
  metadataTableName: storage.metadataTable.tableName,
  description: 'EAGLE QA Compute — ECS Fargate in QA VPC',
});
qaCompute.addDependency(core);
qaCompute.addDependency(storage);

// Tag all stacks
for (const stack of [cicd, core, storage, compute, evalStack, backup, cost]) {
  cdk.Tags.of(stack).add('Project', 'eagle');
  cdk.Tags.of(stack).add('ManagedBy', 'cdk');
  cdk.Tags.of(stack).add('Environment', DEV_CONFIG.env);
}

cdk.Tags.of(qaCompute).add('Project', 'eagle');
cdk.Tags.of(qaCompute).add('ManagedBy', 'cdk');
cdk.Tags.of(qaCompute).add('Environment', 'qa');

app.synth();
