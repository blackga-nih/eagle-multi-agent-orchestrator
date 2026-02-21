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

  // Eval
  evalBucketName: string;

  // Storage stack
  documentBucketName: string;
  documentMetadataTableName: string;
  bedrockMetadataModelId: string;
  metadataLambdaMemory: number;
  metadataLambdaTimeout: number;

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
  evalBucketName: 'eagle-eval-artifacts',

  documentBucketName: 'eagle-documents-dev',
  documentMetadataTableName: 'eagle-document-metadata-dev',
  bedrockMetadataModelId: 'us.anthropic.claude-3-5-haiku-20241022-v1:0',
  metadataLambdaMemory: 512,
  metadataLambdaTimeout: 120,

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
  evalBucketName: 'eagle-eval-artifacts-staging',
  documentBucketName: 'eagle-documents-staging',
  documentMetadataTableName: 'eagle-document-metadata-staging',
  natGateways: 2,
  desiredCount: 2,
  maxCount: 6,
};

export const PROD_CONFIG: EagleConfig = {
  ...DEV_CONFIG,
  env: 'prod',
  evalBucketName: 'eagle-eval-artifacts-prod',
  documentBucketName: 'eagle-documents-prod',
  documentMetadataTableName: 'eagle-document-metadata-prod',
  metadataLambdaMemory: 1024,
  vpcMaxAzs: 3,
  natGateways: 3,
  backendCpu: 1024,
  backendMemory: 2048,
  frontendCpu: 512,
  frontendMemory: 1024,
  desiredCount: 2,
  maxCount: 10,
};
