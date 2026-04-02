export interface EagleConfig {
  env: string;
  account: string;
  region: string;

  // Networking (import existing VPC)
  vpcId: string;

  // External ALB (pre-provisioned, e.g. QA ALB in a different VPC)
  externalAlbSecurityGroupId?: string;

  // Explicit subnet IDs (when VPC has mixed subnet types CDK can't distinguish)
  privateSubnetIds?: string[];

  // Storage (import existing)
  eagleTableName: string;

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

  // Langfuse observability
  langfusePublicKey: string;
  langfuseSecretKey: string;
  langfuseHost: string;
  langfuseProjectId: string;

  // JIRA + feedback triage
  jiraBaseUrl?: string;
  feedbackActionSecret?: string;

  // CI/CD
  githubOwner: string;
  githubRepo: string;
}

const ACCOUNT = process.env.CDK_DEFAULT_ACCOUNT || process.env.AWS_ACCOUNT_ID || '';
const REGION = process.env.CDK_DEFAULT_REGION || 'us-east-1';

export const DEV_CONFIG: EagleConfig = {
  env: 'dev',
  account: ACCOUNT,
  region: REGION,

  vpcId: process.env.CDK_VPC_ID || 'vpc-0ede565d9119f98aa',

  eagleTableName: 'eagle',
  evalBucketName: `eagle-eval-artifacts-${ACCOUNT}-dev`,

  documentBucketName: `eagle-documents-${ACCOUNT}-dev`,
  documentMetadataTableName: 'eagle-document-metadata-dev',
  bedrockMetadataModelId: 'us.anthropic.claude-sonnet-4-6',
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

  langfusePublicKey: 'pk-lf-47021a72-2b4e-4c38-8421-6ab06aef0f5c',
  langfuseSecretKey: 'sk-lf-dbad2023-eede-420c-82e6-2ddec00fb7bb',
  langfuseHost: 'https://us.cloud.langfuse.com',
  langfuseProjectId: 'cmmsqvi2406aead071t0zhl7f',

  jiraBaseUrl: 'https://tracker.nci.nih.gov',
  feedbackActionSecret: process.env.FEEDBACK_ACTION_SECRET || 'eagle-feedback-action-key',

  githubOwner: 'CBIIT',
  githubRepo: 'sm_eagle',

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

export const QA_CONFIG: EagleConfig = {
  ...DEV_CONFIG,
  env: 'qa',
  vpcId: 'vpc-0a3010977e2bca965',
  externalAlbSecurityGroupId: 'sg-02970d6bd45fe8bd4',
  privateSubnetIds: ['subnet-00efa33c26f620963', 'subnet-0c37ceaa073beb491'],
  desiredCount: 1,
  maxCount: 2,
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
