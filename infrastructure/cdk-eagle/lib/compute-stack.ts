import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as ecr from 'aws-cdk-lib/aws-ecr';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as ecs_patterns from 'aws-cdk-lib/aws-ecs-patterns';
import * as logs from 'aws-cdk-lib/aws-logs';
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
  public readonly backendRepo: ecr.Repository;
  public readonly frontendRepo: ecr.Repository;
  public readonly cluster: ecs.Cluster;

  constructor(scope: Construct, id: string, props: EagleComputeStackProps) {
    super(scope, id, props);
    const { config, vpc, appRole } = props;

    // ── ECR Repositories ─────────────────────────────────────
    this.backendRepo = new ecr.Repository(this, 'BackendRepo', {
      repositoryName: `eagle-backend-${config.env}`,
      lifecycleRules: [{ maxImageCount: 10 }],
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });

    this.frontendRepo = new ecr.Repository(this, 'FrontendRepo', {
      repositoryName: `eagle-frontend-${config.env}`,
      lifecycleRules: [{ maxImageCount: 10 }],
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });

    // ── ECS Cluster ──────────────────────────────────────────
    this.cluster = new ecs.Cluster(this, 'Cluster', {
      clusterName: `eagle-${config.env}`,
      vpc,
      containerInsightsV2: ecs.ContainerInsights.ENABLED,
    });

    // ── Backend Task Definition ──────────────────────────────
    const backendTaskDef = new ecs.FargateTaskDefinition(this, 'BackendTaskDef', {
      family: `eagle-backend-${config.env}`,
      cpu: config.backendCpu,
      memoryLimitMiB: config.backendMemory,
      taskRole: appRole,
    });

    const backendLogGroup = new logs.LogGroup(this, 'BackendLogGroup', {
      logGroupName: `/eagle/ecs/backend-${config.env}`,
      retention: logs.RetentionDays.ONE_MONTH,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    backendTaskDef.addContainer('backend', {
      containerName: 'eagle-backend',
      image: ecs.ContainerImage.fromEcrRepository(this.backendRepo),
      portMappings: [{ containerPort: 8000 }],
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
        APP_HOST: '0.0.0.0',
        APP_PORT: '8000',
      },
      logging: ecs.LogDrivers.awsLogs({
        logGroup: backendLogGroup,
        streamPrefix: 'backend',
      }),
      healthCheck: {
        command: ['CMD-SHELL', 'curl -f http://localhost:8000/api/health || exit 1'],
        interval: cdk.Duration.seconds(30),
        timeout: cdk.Duration.seconds(5),
        retries: 3,
        startPeriod: cdk.Duration.seconds(60),
      },
    });

    // ── Backend Fargate Service (internal ALB) ───────────────
    const backendService = new ecs_patterns.ApplicationLoadBalancedFargateService(
      this, 'BackendService', {
        cluster: this.cluster,
        serviceName: `eagle-backend-${config.env}`,
        taskDefinition: backendTaskDef,
        desiredCount: config.desiredCount,
        publicLoadBalancer: false,
        listenerPort: 80,
        minHealthyPercent: 100,
      },
    );

    backendService.targetGroup.configureHealthCheck({
      path: '/api/health',
      healthyThresholdCount: 2,
      unhealthyThresholdCount: 3,
      interval: cdk.Duration.seconds(30),
    });

    // ── Frontend Task Definition ─────────────────────────────
    const frontendTaskDef = new ecs.FargateTaskDefinition(this, 'FrontendTaskDef', {
      family: `eagle-frontend-${config.env}`,
      cpu: config.frontendCpu,
      memoryLimitMiB: config.frontendMemory,
    });

    const frontendLogGroup = new logs.LogGroup(this, 'FrontendLogGroup', {
      logGroupName: `/eagle/ecs/frontend-${config.env}`,
      retention: logs.RetentionDays.ONE_MONTH,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    frontendTaskDef.addContainer('frontend', {
      containerName: 'eagle-frontend',
      image: ecs.ContainerImage.fromEcrRepository(this.frontendRepo),
      portMappings: [{ containerPort: 3000 }],
      environment: {
        FASTAPI_URL: `http://${backendService.loadBalancer.loadBalancerDnsName}`,
        HOSTNAME: '0.0.0.0',
        PORT: '3000',
        NODE_ENV: 'production',
        NEXT_PUBLIC_COGNITO_USER_POOL_ID: props.userPoolId,
        NEXT_PUBLIC_COGNITO_CLIENT_ID: props.userPoolClientId,
        NEXT_PUBLIC_COGNITO_REGION: config.region,
      },
      logging: ecs.LogDrivers.awsLogs({
        logGroup: frontendLogGroup,
        streamPrefix: 'frontend',
      }),
      healthCheck: {
        command: ['CMD-SHELL', 'curl -f http://localhost:3000/ || exit 1'],
        interval: cdk.Duration.seconds(30),
        timeout: cdk.Duration.seconds(5),
        retries: 3,
        startPeriod: cdk.Duration.seconds(60),
      },
    });

    // ── Frontend Fargate Service (public ALB) ────────────────
    const frontendService = new ecs_patterns.ApplicationLoadBalancedFargateService(
      this, 'FrontendService', {
        cluster: this.cluster,
        serviceName: `eagle-frontend-${config.env}`,
        taskDefinition: frontendTaskDef,
        desiredCount: config.desiredCount,
        publicLoadBalancer: true,
        listenerPort: 80,
        minHealthyPercent: 100,
      },
    );

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
      scaleInCooldown: cdk.Duration.seconds(60),
      scaleOutCooldown: cdk.Duration.seconds(60),
    });

    const frontendScaling = frontendService.service.autoScaleTaskCount({
      minCapacity: config.desiredCount,
      maxCapacity: config.maxCount,
    });
    frontendScaling.scaleOnCpuUtilization('FrontendCpuScaling', {
      targetUtilizationPercent: 70,
      scaleInCooldown: cdk.Duration.seconds(60),
      scaleOutCooldown: cdk.Duration.seconds(60),
    });

    // ── Outputs ──────────────────────────────────────────────
    new cdk.CfnOutput(this, 'BackendRepoUri', {
      value: this.backendRepo.repositoryUri,
      exportName: `eagle-backend-repo-uri-${config.env}`,
    });
    new cdk.CfnOutput(this, 'FrontendRepoUri', {
      value: this.frontendRepo.repositoryUri,
      exportName: `eagle-frontend-repo-uri-${config.env}`,
    });
    new cdk.CfnOutput(this, 'ClusterName', {
      value: this.cluster.clusterName,
      exportName: `eagle-cluster-name-${config.env}`,
    });
    new cdk.CfnOutput(this, 'FrontendUrl', {
      value: `http://${frontendService.loadBalancer.loadBalancerDnsName}`,
      description: 'Public URL for the EAGLE frontend',
    });
    new cdk.CfnOutput(this, 'BackendUrl', {
      value: `http://${backendService.loadBalancer.loadBalancerDnsName}`,
      description: 'Internal URL for the EAGLE backend',
    });
  }
}
