import * as cdk from 'aws-cdk-lib';
import * as iam from 'aws-cdk-lib/aws-iam';
import { Construct } from 'constructs';
import { EagleConfig } from '../config/environments';

export interface EagleCiCdStackProps extends cdk.StackProps {
  config: EagleConfig;
}

export class EagleCiCdStack extends cdk.Stack {
  public readonly deployRole: iam.Role;

  constructor(scope: Construct, id: string, props: EagleCiCdStackProps) {
    super(scope, id, props);
    const { config } = props;

    // ── GitHub Actions OIDC Provider ─────────────────────────
    const githubProvider = new iam.OpenIdConnectProvider(this, 'GitHubOIDC', {
      url: 'https://token.actions.githubusercontent.com',
      clientIds: ['sts.amazonaws.com'],
      thumbprints: ['6938fd4d98bab03faadb97b34396831e3780aea1'],
    });

    // ── Deploy Role ──────────────────────────────────────────
    // Trusted by GitHub Actions from the specific repo/branch
    this.deployRole = new iam.Role(this, 'GitHubActionsRole', {
      roleName: `eagle-github-actions-${config.env}`,
      maxSessionDuration: cdk.Duration.hours(1),
      assumedBy: new iam.OpenIdConnectPrincipal(githubProvider, {
        StringEquals: {
          'token.actions.githubusercontent.com:aud': 'sts.amazonaws.com',
        },
        StringLike: {
          'token.actions.githubusercontent.com:sub':
            `repo:${config.githubOwner}/${config.githubRepo}:*`,
        },
      }),
    });

    // CDK deploy permissions (CloudFormation + SSM + STS for CDK)
    this.deployRole.addToPolicy(new iam.PolicyStatement({
      sid: 'CDKDeploy',
      actions: [
        'cloudformation:DescribeStacks',
        'cloudformation:DescribeStackEvents',
        'cloudformation:GetTemplate',
        'cloudformation:CreateStack',
        'cloudformation:UpdateStack',
        'cloudformation:DeleteStack',
        'cloudformation:CreateChangeSet',
        'cloudformation:DescribeChangeSet',
        'cloudformation:ExecuteChangeSet',
        'cloudformation:DeleteChangeSet',
        'cloudformation:GetTemplateSummary',
        'ssm:GetParameter',
        'sts:AssumeRole',
      ],
      resources: ['*'],
    }));

    // S3: CDK assets bucket + deploy artifacts
    this.deployRole.addToPolicy(new iam.PolicyStatement({
      sid: 'S3CDKAssets',
      actions: [
        's3:GetObject',
        's3:PutObject',
        's3:ListBucket',
        's3:GetBucketLocation',
        's3:CreateBucket',
      ],
      resources: [
        'arn:aws:s3:::cdk-*',
        'arn:aws:s3:::cdk-*/*',
      ],
    }));

    // ECR: Push container images
    this.deployRole.addToPolicy(new iam.PolicyStatement({
      sid: 'ECRPush',
      actions: [
        'ecr:GetAuthorizationToken',
        'ecr:BatchCheckLayerAvailability',
        'ecr:GetDownloadUrlForLayer',
        'ecr:PutImage',
        'ecr:InitiateLayerUpload',
        'ecr:UploadLayerPart',
        'ecr:CompleteLayerUpload',
        'ecr:BatchGetImage',
      ],
      resources: ['*'],
    }));

    // ECS: Update services
    this.deployRole.addToPolicy(new iam.PolicyStatement({
      sid: 'ECSDeploy',
      actions: [
        'ecs:UpdateService',
        'ecs:DescribeServices',
        'ecs:DescribeTaskDefinition',
        'ecs:RegisterTaskDefinition',
        'ecs:DeregisterTaskDefinition',
        'ecs:ListTasks',
        'ecs:DescribeTasks',
        'iam:PassRole',
      ],
      resources: ['*'],
    }));

    // IAM: CDK bootstrap role lookups
    this.deployRole.addToPolicy(new iam.PolicyStatement({
      sid: 'IAMCDKBootstrap',
      actions: [
        'iam:GetRole',
        'iam:CreateRole',
        'iam:AttachRolePolicy',
        'iam:PutRolePolicy',
      ],
      resources: [
        `arn:aws:iam::${this.account}:role/cdk-*`,
      ],
    }));

    // ── Outputs ──────────────────────────────────────────────
    new cdk.CfnOutput(this, 'DeployRoleArn', {
      value: this.deployRole.roleArn,
      exportName: `eagle-deploy-role-arn-${config.env}`,
      description: 'ARN for GitHub Actions to assume via OIDC',
    });
    new cdk.CfnOutput(this, 'OIDCProviderArn', {
      value: githubProvider.openIdConnectProviderArn,
    });
  }
}
