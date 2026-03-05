import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as ecr from 'aws-cdk-lib/aws-ecr';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as elbv2 from 'aws-cdk-lib/aws-elasticloadbalancingv2';
import * as logs from 'aws-cdk-lib/aws-logs';
import { Construct } from 'constructs';
import { EagleConfig } from '../config/environments';

export interface EagleComputeStackProps extends cdk.StackProps {
  config: EagleConfig;
  vpc: ec2.IVpc;
  appRole: iam.Role;
  userPoolId: string;
  userPoolClientId: string;
  documentBucketName: string;
  metadataTableName: string;
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
        S3_BUCKET: props.documentBucketName,
        S3_PREFIX: 'eagle/',
        AWS_REGION: config.region,
        USE_BEDROCK: 'true',
        REQUIRE_AUTH: 'true',
        USE_PERSISTENT_SESSIONS: 'true',
        DEV_MODE: 'true',
        COGNITO_USER_POOL_ID: props.userPoolId,
        COGNITO_CLIENT_ID: props.userPoolClientId,
        DOCUMENT_BUCKET: props.documentBucketName,
        METADATA_TABLE: props.metadataTableName,
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

    // backendAlb is referenced in frontend env — declared below but used here via DNS reference
    // We use a placeholder; the real value comes from the Cfn output or a token.
    // Solution: create ALBs before task definitions to allow token reference.
    // Refactored: ALB creation moved before frontend task definition (see below).

    // ── Backend ALB & Service ────────────────────────────────
    // NCI VPC: Private subnets tagged aws-cdk:subnet-type=Private, one per AZ.
    // Using PRIVATE_WITH_EGRESS to select exactly those 2 subnets for both ALB and tasks.

    const backendLBSG = new ec2.SecurityGroup(this, 'BackendLBSG', {
      vpc,
      description: 'eagle-backend ALB security group',
    });
    // Allow HTTP from entire VPC CIDR (NCI private-only VPC)
    backendLBSG.addIngressRule(ec2.Peer.ipv4(vpc.vpcCidrBlock), ec2.Port.tcp(80));

    const backendAlb = new elbv2.ApplicationLoadBalancer(this, 'BackendALB', {
      vpc,
      internetFacing: false,
      securityGroup: backendLBSG,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
    });

    const backendTargetGroup = new elbv2.ApplicationTargetGroup(this, 'BackendTargetGroup', {
      vpc,
      port: 8000,
      protocol: elbv2.ApplicationProtocol.HTTP,
      targetType: elbv2.TargetType.IP,
      healthCheck: {
        path: '/api/health',
        healthyThresholdCount: 2,
        unhealthyThresholdCount: 3,
        interval: cdk.Duration.seconds(30),
      },
      deregistrationDelay: cdk.Duration.seconds(30),
    });

    backendAlb.addListener('BackendListener', {
      port: 80,
      defaultTargetGroups: [backendTargetGroup],
      open: false,
    });

    const backendServiceSG = new ec2.SecurityGroup(this, 'BackendServiceSG', {
      vpc,
      description: 'eagle-backend ECS task security group',
    });
    backendServiceSG.addIngressRule(backendLBSG, ec2.Port.tcp(8000), 'from backend ALB');

    const backendService = new ecs.FargateService(this, 'BackendService', {
      cluster: this.cluster,
      serviceName: `eagle-backend-${config.env}`,
      taskDefinition: backendTaskDef,
      desiredCount: config.desiredCount,
      securityGroups: [backendServiceSG],
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
      assignPublicIp: false,
    });

    backendService.attachToApplicationTargetGroup(backendTargetGroup);

    // ── Frontend Task Definition ─────────────────────────────
    // Backend ALB DNS is now available as a token after backendAlb is created.
    frontendTaskDef.addContainer('frontend', {
      containerName: 'eagle-frontend',
      image: ecs.ContainerImage.fromEcrRepository(this.frontendRepo),
      portMappings: [{ containerPort: 3000 }],
      environment: {
        FASTAPI_URL: `http://${backendAlb.loadBalancerDnsName}`,
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

    // ── Frontend ALB & Service ───────────────────────────────
    const frontendLBSG = new ec2.SecurityGroup(this, 'FrontendLBSG', {
      vpc,
      description: 'eagle-frontend ALB security group',
    });
    frontendLBSG.addIngressRule(ec2.Peer.ipv4(vpc.vpcCidrBlock), ec2.Port.tcp(80));

    const frontendAlb = new elbv2.ApplicationLoadBalancer(this, 'FrontendALB', {
      vpc,
      internetFacing: false,
      securityGroup: frontendLBSG,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
    });

    const frontendTargetGroup = new elbv2.ApplicationTargetGroup(this, 'FrontendTargetGroup', {
      vpc,
      port: 3000,
      protocol: elbv2.ApplicationProtocol.HTTP,
      targetType: elbv2.TargetType.IP,
      healthCheck: {
        path: '/',
        healthyThresholdCount: 2,
        unhealthyThresholdCount: 3,
        interval: cdk.Duration.seconds(30),
      },
      deregistrationDelay: cdk.Duration.seconds(30),
    });

    frontendAlb.addListener('FrontendListener', {
      port: 80,
      defaultTargetGroups: [frontendTargetGroup],
      open: false,
    });

    const frontendServiceSG = new ec2.SecurityGroup(this, 'FrontendServiceSG', {
      vpc,
      description: 'eagle-frontend ECS task security group',
    });
    frontendServiceSG.addIngressRule(frontendLBSG, ec2.Port.tcp(3000), 'from frontend ALB');

    const frontendService = new ecs.FargateService(this, 'FrontendService', {
      cluster: this.cluster,
      serviceName: `eagle-frontend-${config.env}`,
      taskDefinition: frontendTaskDef,
      desiredCount: config.desiredCount,
      securityGroups: [frontendServiceSG],
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
      assignPublicIp: false,
    });

    frontendService.attachToApplicationTargetGroup(frontendTargetGroup);

    // ── Auto-Scaling ─────────────────────────────────────────
    const backendScaling = backendService.autoScaleTaskCount({
      minCapacity: 0,
      maxCapacity: config.maxCount,
    });
    backendScaling.scaleOnCpuUtilization('BackendCpuScaling', {
      targetUtilizationPercent: 70,
      scaleInCooldown: cdk.Duration.seconds(60),
      scaleOutCooldown: cdk.Duration.seconds(60),
    });

    const frontendScaling = frontendService.autoScaleTaskCount({
      minCapacity: 0,
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
      value: `http://${frontendAlb.loadBalancerDnsName}`,
      description: 'Internal URL for the EAGLE frontend',
    });
    new cdk.CfnOutput(this, 'BackendUrl', {
      value: `http://${backendAlb.loadBalancerDnsName}`,
      description: 'Internal URL for the EAGLE backend',
    });
  }
}
