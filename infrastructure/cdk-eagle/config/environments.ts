export interface EagleConfig {
  env: string;
  account: string;
  region: string;

  // Networking (import existing VPC)
  vpcId: string;

  // External ALB (CBIIT-managed, HTTPS, pre-provisioned).
  // CDK does not own the ALB but:
  //   - opens the frontend task SG to the ALB's SG (via externalAlbSecurityGroupId)
  //   - registers the frontend ECS service with the ALB's target group so
  //     ECS auto-syncs task IPs on every deploy (fixes the stale-IP-target
  //     problem the previous manual-pinning setup had).
  //   - exposes the public hostname so backend can build absolute URLs
  //     (FRONTEND_BASE_URL, ENTRA_REDIRECT_URI).
  externalAlbSecurityGroupId?: string;
  externalFrontendTargetGroupArn?: string;
  externalFrontendHostname?: string;

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

  // Knowledge Base — S3 Vectors store (semantic search lane).
  // Created out-of-band via AWS CLI; CDK only owns IAM grants.
  vectorsBucketName: string;
  vectorsIndexName: string;

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
  jiraApiToken?: string;
  feedbackActionSecret?: string;
  ghDispatchToken?: string;
  teamsTriageWebhookUrl?: string;

  // CI/CD
  githubOwner: string;
  githubRepo: string;

  // Microsoft Entra OIDC (replaces Cognito).
  // App registration is per-environment; secrets live in AWS Secrets Manager
  // under entraClientSecretArn / jwtSigningKeySecretArn.
  entraTenantId: string;
  entraClientId: string;
  entraRedirectUri: string;
  entraPostLoginPath: string;
  /** Secrets Manager secret holding the Entra app reg client_secret (string). */
  entraClientSecretArn: string;
  /** Secrets Manager secret holding the HS256 signing key for local session JWTs. */
  jwtSigningKeySecretArn: string;
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

  // Per-env S3 Vectors bucket. Each env points to its own bucket + index;
  // re-indexing is performed out-of-band by an offline embed job. The legacy
  // `rh-eagle` bucket (Ryan Hash's original index) is being decommissioned —
  // do NOT default back to it. Bucket itself is provisioned via:
  //   aws s3vectors create-vector-bucket --vector-bucket-name <name>
  //   aws s3vectors create-index --vector-bucket-name <name> \
  //     --index-name eagle-kb-approved --data-type float32 \
  //     --dimension 1024 --distance-metric cosine
  vectorsBucketName: process.env.S3_VECTORS_BUCKET || `eagle-kb-vectors-${ACCOUNT}-dev`,
  vectorsIndexName: process.env.S3_VECTORS_INDEX || 'eagle-kb-approved',

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
  jiraApiToken: process.env.JIRA_API_TOKEN || '',
  feedbackActionSecret: process.env.FEEDBACK_ACTION_SECRET || 'eagle-feedback-action-key',
  ghDispatchToken: process.env.GH_DISPATCH_TOKEN || '',
  teamsTriageWebhookUrl: process.env.TEAMS_TRIAGE_WEBHOOK_URL || '',

  githubOwner: 'CBIIT',
  githubRepo: 'sm_eagle',

  // Microsoft Entra (NIH tenant) — populate via env vars at synth time.
  // Per-env app registrations and Secrets Manager entries are provisioned
  // out-of-band (the EAGLE Entra app reg is already created).
  entraTenantId: process.env.EAGLE_ENTRA_TENANT_ID || '',
  entraClientId: process.env.EAGLE_ENTRA_CLIENT_ID || '',
  entraRedirectUri: process.env.EAGLE_ENTRA_REDIRECT_URI || '',
  entraPostLoginPath: '/chat',
  // Complete ARN (with 6-char Secrets Manager suffix) is REQUIRED — see
  // `core-stack.ts` (the partial-ARN form leaks an IAM/task-def mismatch
  // that fails the ECS task with AccessDenied at startup, observed
  // 2026-05-13 in run 25825912427).
  entraClientSecretArn:
    process.env.EAGLE_ENTRA_CLIENT_SECRET_ARN ||
    `arn:aws:secretsmanager:${REGION}:${ACCOUNT}:secret:eagle/dev/entra-client-secret-sJv2P4`,
  jwtSigningKeySecretArn:
    process.env.EAGLE_JWT_SIGNING_KEY_ARN ||
    `arn:aws:secretsmanager:${REGION}:${ACCOUNT}:secret:eagle/dev/jwt-signing-key-8xvoN8`,

  // CBIIT-managed external front-door — EAGLE-DEV-ALB (HTTPS, *.cancer.gov cert).
  // SG already permits the frontend task SG on :3000 (verified out-of-band).
  externalAlbSecurityGroupId: 'sg-0f426290543115077',
  externalFrontendTargetGroupArn:
    'arn:aws:elasticloadbalancing:us-east-1:695681773636:targetgroup/EAGLE-DEV-FRONTEND-IP/0e76ba2b0ab49d0c',
  externalFrontendHostname: process.env.EAGLE_EXTERNAL_HOSTNAME_DEV || '',
};

export const STAGING_CONFIG: EagleConfig = {
  ...DEV_CONFIG,
  env: 'staging',
  evalBucketName: 'eagle-eval-artifacts-staging',
  documentBucketName: 'eagle-documents-staging',
  documentMetadataTableName: 'eagle-document-metadata-staging',
  vectorsBucketName: 'eagle-kb-vectors-staging',
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
  // Per-env resource names — must override DEV_CONFIG so QA does not point at
  // dev buckets/tables. Same class of bug as the vectors-bucket fix in
  // ff8654f, which only patched vectorsBucketName.
  documentBucketName: `eagle-documents-${ACCOUNT}-qa`,
  documentMetadataTableName: 'eagle-document-metadata-qa',
  evalBucketName: `eagle-eval-artifacts-${ACCOUNT}-qa`,
  vectorsBucketName: `eagle-kb-vectors-${ACCOUNT}-qa`,
  desiredCount: 1,
  maxCount: 2,
  entraClientSecretArn:
    process.env.EAGLE_ENTRA_CLIENT_SECRET_ARN_QA ||
    `arn:aws:secretsmanager:${REGION}:${ACCOUNT}:secret:eagle/qa/entra-client-secret`,
  jwtSigningKeySecretArn:
    process.env.EAGLE_JWT_SIGNING_KEY_ARN_QA ||
    `arn:aws:secretsmanager:${REGION}:${ACCOUNT}:secret:eagle/qa/jwt-signing-key`,

  // CBIIT-managed external front-door — EAGLE-QA-ALB (HTTPS, *.cancer.gov cert).
  externalFrontendTargetGroupArn:
    'arn:aws:elasticloadbalancing:us-east-1:695681773636:targetgroup/EAGLE-QA-FRONTEND-IP/152273fb8d5cd028',
  externalFrontendHostname: process.env.EAGLE_EXTERNAL_HOSTNAME_QA || '',

  // QA redirect URI overrides the DEV inherited value so each env points
  // Entra back at its own ALB after sign-in.
  entraRedirectUri: process.env.EAGLE_ENTRA_REDIRECT_URI_QA || '',
};

export const PROD_CONFIG: EagleConfig = {
  ...DEV_CONFIG,
  env: 'prod',
  evalBucketName: 'eagle-eval-artifacts-prod',
  documentBucketName: 'eagle-documents-prod',
  documentMetadataTableName: 'eagle-document-metadata-prod',
  vectorsBucketName: 'eagle-kb-vectors-prod',
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
