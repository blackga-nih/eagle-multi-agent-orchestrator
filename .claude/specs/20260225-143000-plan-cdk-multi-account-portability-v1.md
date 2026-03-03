# Plan: CDK Multi-Account Portability
**File**: `20260225-143000-plan-cdk-multi-account-portability-v1.md`
**Type**: plan · **Dest**: `.claude/specs/` · **Version**: v1
**Date**: 2026-02-25

---

## Problem Statement

The current CDK is deployed exclusively against the NCI account (`695681773636`) with
four hard dependencies baked in:

1. VPC ID `vpc-09def43fcabfa4df6` hard-coded in `core-stack.ts`
2. NCI-patched CDK bootstrap role names (`power-user-cdk-*`) in `bin/eagle.ts`
3. GitHub OIDC provider imported-not-created in `cicd-stack.ts` (NCI StackSet pre-deployed it)
4. S3 bucket names containing the NCI account ID in `environments.ts`

Additionally, the ALBs are HTTP-only with no HTTPS/domain support, and `bin/eagle.ts`
hardcodes `DEV_CONFIG` with no environment-selection mechanism.

**Goal**: Make it possible to deploy an exact replica of the EAGLE stack into any AWS
account by changing a single config block — with zero code changes to stack files.

---

## Target Architecture

```
environments.ts
  └─ NCI_DEV_CONFIG      (existing — 695681773636, NCI SCP rules, VPC imported)
  └─ STANDARD_DEV_CONFIG (new account — standard bootstrap, VPC created by CDK)
  └─ STAGING_CONFIG      (inherits pattern)
  └─ PROD_CONFIG         (inherits pattern)

bin/eagle.ts
  └─ reads EAGLE_ENV env var → selects config → all stacks get the right values

core-stack.ts
  └─ if config.vpcId set → Vpc.fromLookup   (NCI path)
  └─ else               → new ec2.Vpc(...)  (standard path)

cicd-stack.ts
  └─ if config.existingOidcProviderArn set → fromOpenIdConnectProviderArn  (NCI path)
  └─ else                                  → new iam.OpenIdConnectProvider  (standard path)

bin/eagle.ts synthesizer
  └─ if config.cdkBootstrapQualifier set → DefaultStackSynthesizer with custom role names
  └─ else                                → DefaultStackSynthesizer defaults (cdk-hnb659fds-*)
```

---

## EagleConfig Changes

### New fields to add to the `EagleConfig` interface

```typescript
// ── Account topology ─────────────────────────────────────
account: string;           // AWS account ID (already present)
region: string;            // (already present)

// ── VPC ──────────────────────────────────────────────────
vpcId?: string;            // If set → import existing VPC (NCI path)
                           // If unset → CDK creates VPC
vpcCidr?: string;          // CIDR for CDK-created VPC (default '10.0.0.0/16')
vpcMaxAzs: number;         // (already present)
natGateways: number;       // (already present)

// ── CDK Bootstrap ─────────────────────────────────────────
// If set, synthesizer uses these role name patterns instead of cdk-hnb659fds-*
cdkBootstrapQualifier?: string;           // e.g. 'power-user-cdk'
cdkBootstrapRoleSuffix?: string;          // e.g. account ID appended to role names

// ── GitHub OIDC ───────────────────────────────────────────
existingOidcProviderArn?: string;         // If set → import; else → create
githubOwner: string;       // (already present)
githubRepo: string;        // (already present)

// ── Networking / ALB ─────────────────────────────────────
albInternetFacing?: boolean;              // default false (internal)
albCertificateArn?: string;              // If set → HTTPS listener on 443
domainName?: string;                     // e.g. 'eagle-dev.example.gov'
hostedZoneId?: string;                   // Route53 HZ for DNS record creation
```

---

## File-by-File Changes

### 1. `config/environments.ts`

**Add** to `EagleConfig` interface: all new optional fields above.

**Update** `DEV_CONFIG` (NCI account — no changes to deployed behavior):
```typescript
export const DEV_CONFIG: EagleConfig = {
  // ... existing fields unchanged ...
  vpcId: 'vpc-09def43fcabfa4df6',           // NCI: import existing
  cdkBootstrapQualifier: 'power-user-cdk',
  cdkBootstrapRoleSuffix: '695681773636',
  existingOidcProviderArn:
    'arn:aws:iam::695681773636:oidc-provider/token.actions.githubusercontent.com',
  albInternetFacing: false,
};
```

**Add** new `STANDARD_DEV_CONFIG` (template for new accounts):
```typescript
export const STANDARD_DEV_CONFIG: EagleConfig = {
  env: 'dev',
  account: 'REPLACE_ME',          // new account ID
  region: 'us-east-1',
  eagleTableName: 'eagle',
  evalBucketName: `eagle-eval-artifacts-REPLACE_ME-dev`,
  documentBucketName: `eagle-documents-REPLACE_ME-dev`,
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
  githubOwner: 'REPLACE_ME',
  githubRepo: 'REPLACE_ME',
  albInternetFacing: false,
  // vpcId: omitted → CDK creates VPC
  // existingOidcProviderArn: omitted → CDK creates OIDC provider
  // cdkBootstrapQualifier: omitted → standard cdk-hnb659fds-* roles
  // albCertificateArn: omitted → HTTP only
};
```

> S3 bucket names use `REPLACE_ME` placeholder. Before deploying to a new account,
> set `account` to the real account ID and update bucket names accordingly.
> Alternatively, make them dynamic: `` `eagle-documents-${account}-${env}` ``

**Better long-term**: make bucket names derived automatically:
```typescript
// Helper — avoids account ID duplication:
function makeBucketName(base: string, account: string, env: string) {
  return `${base}-${account}-${env}`;
}
```

---

### 2. `bin/eagle.ts`

**Environment selection** via `EAGLE_ENV` env var:
```typescript
import { DEV_CONFIG, STANDARD_DEV_CONFIG, STAGING_CONFIG, PROD_CONFIG } from '../config/environments';

const ENV = process.env.EAGLE_ENV ?? 'dev';
const ACCOUNT_TYPE = process.env.EAGLE_ACCOUNT_TYPE ?? 'nci'; // 'nci' | 'standard'

const configMap: Record<string, EagleConfig> = {
  'nci-dev': DEV_CONFIG,
  'standard-dev': STANDARD_DEV_CONFIG,
  'staging': STAGING_CONFIG,
  'prod': PROD_CONFIG,
};
const config = configMap[`${ACCOUNT_TYPE}-${ENV}`] ?? DEV_CONFIG;
```

**Synthesizer — conditional on config**:
```typescript
function makeSynthesizer(config: EagleConfig): cdk.IStackSynthesizer {
  if (config.cdkBootstrapQualifier && config.cdkBootstrapRoleSuffix) {
    // NCI-patched bootstrap path
    const Q = config.cdkBootstrapQualifier;
    const S = config.cdkBootstrapRoleSuffix;
    return new cdk.DefaultStackSynthesizer({
      deployRoleArn:               `arn:aws:iam::${config.account}:role/${Q}-deploy-${S}`,
      fileAssetPublishingRoleArn:  `arn:aws:iam::${config.account}:role/${Q}-file-pub-${S}`,
      imageAssetPublishingRoleArn: `arn:aws:iam::${config.account}:role/${Q}-img-pub-${S}`,
      cloudFormationExecutionRole: `arn:aws:iam::${config.account}:role/${Q}-cfn-exec-${S}`,
      lookupRoleArn:               `arn:aws:iam::${config.account}:role/${Q}-lookup-${S}`,
      bootstrapStackVersionSsmParameter: '/cdk-bootstrap/hnb659fds/version',
      generateBootstrapVersionRule: false,
    });
  }
  // Standard CDK bootstrap (cdk-hnb659fds-* roles)
  return new cdk.DefaultStackSynthesizer();
}

const synthesizer = makeSynthesizer(config);
```

---

### 3. `lib/core-stack.ts`

**VPC — import or create**:
```typescript
if (config.vpcId) {
  // NCI path: import existing (SCP blocks ec2:CreateVpc)
  this.vpc = ec2.Vpc.fromLookup(this, 'Vpc', { vpcId: config.vpcId });
} else {
  // Standard path: CDK creates VPC with public + private subnets
  this.vpc = new ec2.Vpc(this, 'Vpc', {
    maxAzs: config.vpcMaxAzs,
    natGateways: config.natGateways,
    cidr: config.vpcCidr ?? '10.0.0.0/16',
    subnetConfiguration: [
      { name: 'Public',  subnetType: ec2.SubnetType.PUBLIC,              cidrMask: 24 },
      { name: 'Private', subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS, cidrMask: 24 },
    ],
  });
}
```

**No other changes to `core-stack.ts`** — Cognito, DynamoDB, IAM roles are already clean.

---

### 4. `lib/cicd-stack.ts`

**OIDC provider — import or create**:
```typescript
let githubProvider: iam.IOpenIdConnectProvider;

if (config.existingOidcProviderArn) {
  // NCI path: provider pre-deployed by StackSet; SCP blocks iam:CreateOpenIDConnectProvider
  githubProvider = iam.OpenIdConnectProvider.fromOpenIdConnectProviderArn(
    this, 'GitHubOIDC', config.existingOidcProviderArn,
  );
} else {
  // Standard path: create the OIDC provider
  githubProvider = new iam.OpenIdConnectProvider(this, 'GitHubOIDC', {
    url: 'https://token.actions.githubusercontent.com',
    clientIds: ['sts.amazonaws.com'],
    thumbprints: ['6938fd4d98bab03faadb97b34396831e3780aea1'],
  });
}
```

**No other changes to `cicd-stack.ts`**.

---

### 5. `lib/compute-stack.ts`

**ALB internet-facing and HTTPS** — add to `EagleComputeStackProps`:
```typescript
albInternetFacing?: boolean;
albCertificateArn?: string;
domainName?: string;
```

**Backend ALB**:
```typescript
const backendAlb = new elbv2.ApplicationLoadBalancer(this, 'BackendALB', {
  vpc,
  internetFacing: props.albInternetFacing ?? false,
  securityGroup: backendLBSG,
  vpcSubnets: props.albInternetFacing
    ? { subnetType: ec2.SubnetType.PUBLIC }
    : { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
});

// Add HTTPS listener if cert provided, else HTTP
if (props.albCertificateArn) {
  const cert = acm.Certificate.fromCertificateArn(this, 'BackendCert', props.albCertificateArn);
  backendAlb.addListener('BackendHttps', {
    port: 443,
    certificates: [cert],
    defaultTargetGroups: [backendTargetGroup],
    open: props.albInternetFacing ?? false,
  });
  // HTTP → HTTPS redirect
  backendAlb.addListener('BackendHttpRedirect', {
    port: 80,
    defaultAction: elbv2.ListenerAction.redirect({ protocol: 'HTTPS', port: '443' }),
    open: false,
  });
} else {
  backendAlb.addListener('BackendHttp', {
    port: 80,
    defaultTargetGroups: [backendTargetGroup],
    open: false,
  });
}
```

Apply the same pattern to the frontend ALB.

**Security group ingress** — when internet-facing, allow `0.0.0.0/0` instead of VPC CIDR:
```typescript
if (props.albInternetFacing) {
  backendLBSG.addIngressRule(ec2.Peer.anyIpv4(), ec2.Port.tcp(443));
} else {
  backendLBSG.addIngressRule(ec2.Peer.ipv4(vpc.vpcCidrBlock), ec2.Port.tcp(80));
}
```

**Pass new props from `bin/eagle.ts`**:
```typescript
new EagleComputeStack(app, 'EagleComputeStack', {
  ...existingProps,
  albInternetFacing: config.albInternetFacing,
  albCertificateArn: config.albCertificateArn,
});
```

---

## Deployment Checklist for a New Account

Before running `cdk bootstrap` + `cdk deploy` in a new account:

```
[ ] 1. Copy STANDARD_DEV_CONFIG in environments.ts
[ ] 2. Set account ID, region
[ ] 3. Update S3 bucket names with new account ID
[ ] 4. Set githubOwner / githubRepo to the correct fork
[ ] 5. Set albCertificateArn if HTTPS required (request ACM cert first)
[ ] 6. Set vpcId if importing existing VPC; otherwise leave unset
[ ] 7. Set existingOidcProviderArn if OIDC pre-deployed; otherwise leave unset
[ ] 8. Run standard cdk bootstrap: npx cdk bootstrap aws://ACCOUNT/REGION
[ ] 9. Set EAGLE_ACCOUNT_TYPE=standard EAGLE_ENV=dev npx cdk deploy --all
[ ] 10. Push first Docker images to ECR, then update ECS desired count to 1
[ ] 11. Request Bedrock model access in the new account (Claude Haiku, Sonnet)
```

---

## NCI Account — Zero Behavior Change

The NCI `DEV_CONFIG` now explicitly carries all the NCI-specific values
(`vpcId`, `cdkBootstrapQualifier`, `existingOidcProviderArn`) that previously
were hardcoded in stack files. Deploying with `EAGLE_ACCOUNT_TYPE=nci EAGLE_ENV=dev`
(or no env vars, since NCI/dev is the default) produces identical CloudFormation
as today.

---

## What Is NOT Changed

| Concern | Status |
|---------|--------|
| DynamoDB table schema / entity prefixes | Unchanged |
| ECS task definitions, env vars | Unchanged |
| Cognito user pool config | Unchanged (always created fresh) |
| Lambda metadata extractor | Unchanged |
| CloudWatch / eval stack | Unchanged |
| GitHub Actions workflow YAML | Unchanged (reads role ARN from CF output) |
| eagle-plugin/ agent/skill definitions | Unchanged |

---

## Implementation Order

| # | File | Change |
|---|------|--------|
| 1 | `config/environments.ts` | Add new interface fields; update DEV_CONFIG with NCI-explicit values; add STANDARD_DEV_CONFIG; add bucket name helper |
| 2 | `bin/eagle.ts` | Add env-var config selection; extract `makeSynthesizer()` |
| 3 | `lib/core-stack.ts` | VPC: import-or-create branch |
| 4 | `lib/cicd-stack.ts` | OIDC: import-or-create branch |
| 5 | `lib/compute-stack.ts` | ALB: internet-facing toggle; HTTPS listener; security group rules |
| 6 | Validate NCI path | `EAGLE_ACCOUNT_TYPE=nci npx cdk synth EagleCoreStack --quiet` |
| 7 | Validate standard path | `EAGLE_ACCOUNT_TYPE=standard npx cdk synth EagleCoreStack --quiet` |

---

## Validation Commands

```bash
cd infrastructure/cdk-eagle
npm run build

# NCI path — must produce identical template to current deployed
EAGLE_ACCOUNT_TYPE=nci EAGLE_ENV=dev npx cdk synth --quiet

# Standard path — must synthesize without errors
EAGLE_ACCOUNT_TYPE=standard EAGLE_ENV=dev npx cdk synth --quiet

# Diff NCI vs current deployed (should be empty after this change)
EAGLE_ACCOUNT_TYPE=nci EAGLE_ENV=dev npx cdk diff EagleCoreStack
```

---

## Open Questions for New Account

1. **SCP restrictions?** — If the new account has similar SCPs to NCI (blocking `ec2:CreateVpc`,
   `iam:CreateOpenIDConnectProvider`), use the `vpcId` + `existingOidcProviderArn` paths.
2. **Public or internal ALBs?** — Set `albInternetFacing: true` + provide `albCertificateArn`
   if end-users access from outside the VPC/organization network.
3. **Bedrock model access** — Must be requested separately in each AWS account; not transferred.
4. **Same GitHub repo or fork?** — Update `githubOwner` / `githubRepo` in the config if the
   deployment pipeline runs from a different repo.
5. **Cognito domain** — Cognito user pools are account-scoped; a new pool will be created with
   a new pool ID. Existing users do not transfer.
