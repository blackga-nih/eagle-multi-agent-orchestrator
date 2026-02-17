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

export const STAGING_CONFIG: EagleConfig = {
  ...DEV_CONFIG,
  env: 'staging',
  natGateways: 2,
  desiredCount: 2,
  maxCount: 6,
};

export const PROD_CONFIG: EagleConfig = {
  ...DEV_CONFIG,
  env: 'prod',
  vpcMaxAzs: 3,
  natGateways: 3,
  backendCpu: 1024,
  backendMemory: 2048,
  frontendCpu: 512,
  frontendMemory: 1024,
  desiredCount: 2,
  maxCount: 10,
};
