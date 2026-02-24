#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { EagleCoreStack } from '../lib/core-stack';
import { EagleComputeStack } from '../lib/compute-stack';
import { EagleStorageStack } from '../lib/storage-stack';
import { EagleCiCdStack } from '../lib/cicd-stack';
import { EagleEvalStack } from '../lib/eval-stack';
import { DEV_CONFIG } from '../config/environments';

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

// Tag all stacks
for (const stack of [cicd, core, storage, compute, evalStack]) {
  cdk.Tags.of(stack).add('Project', 'eagle');
  cdk.Tags.of(stack).add('ManagedBy', 'cdk');
  cdk.Tags.of(stack).add('Environment', DEV_CONFIG.env);
}

app.synth();
