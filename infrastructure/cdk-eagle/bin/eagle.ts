#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { EagleCoreStack } from '../lib/core-stack';
import { EagleComputeStack } from '../lib/compute-stack';
import { EagleCiCdStack } from '../lib/cicd-stack';
import { DEV_CONFIG } from '../config/environments';

const app = new cdk.App();
const env = { account: DEV_CONFIG.account, region: DEV_CONFIG.region };

// CI/CD stack is independent — deploy first
const cicd = new EagleCiCdStack(app, 'EagleCiCdStack', {
  env,
  config: DEV_CONFIG,
  description: 'EAGLE CI/CD — GitHub Actions OIDC federation and deploy role',
});

// Core stack: VPC, Cognito, IAM, imports existing S3/DDB
const core = new EagleCoreStack(app, 'EagleCoreStack', {
  env,
  config: DEV_CONFIG,
  description: 'EAGLE Core — VPC, Cognito, IAM, storage imports',
});

// Compute stack depends on Core for VPC, IAM role, Cognito IDs
const compute = new EagleComputeStack(app, 'EagleComputeStack', {
  env,
  config: DEV_CONFIG,
  vpc: core.vpc,
  appRole: core.appRole,
  userPoolId: core.userPool.userPoolId,
  userPoolClientId: core.userPoolClient.userPoolClientId,
  description: 'EAGLE Compute — ECS Fargate, ECR, ALB',
});
compute.addDependency(core);

// Tag all stacks
for (const stack of [cicd, core, compute]) {
  cdk.Tags.of(stack).add('Project', 'eagle');
  cdk.Tags.of(stack).add('ManagedBy', 'cdk');
  cdk.Tags.of(stack).add('Environment', DEV_CONFIG.env);
}

app.synth();
