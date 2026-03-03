# Plan: Wire ECS Fargate Services to Existing EAGLE-DEV-ALB

## Task Description

The NCI account has two pre-existing, NCI-provisioned Application Load Balancers:
- **EAGLE-DEV-ALB** — HTTPS/443, ACM cert `3a0e0451-68b2-464b-bfd2-1536dc57fb57`, VPC `vpc-09def43fcabfa4df6`, no active targets
- **EAGLE-QA-ALB** — same VPC, presumably for staging/QA environment

Our CDK `EagleComputeStack` currently creates **two new ALBs** (one for frontend, one for backend) on HTTP/80 in private subnets. These are unnecessary and create confusion — the NCI networking team has already provisioned EAGLE-DEV-ALB with the proper ACM certificate and DNS.

This plan replaces the CDK-managed ALBs with imports of the existing NCI ALBs and adds path-based routing (HTTPS) so both frontend and backend are served through the single canonical EAGLE-DEV-ALB.

## Objective

- Remove the two CDK-created ALBs from `EagleComputeStack`
- Import `EAGLE-DEV-ALB` into CDK using L1/L2 lookup constructs
- Create `ip`-type target groups for frontend (port 3000) and backend (port 8000)
- Add path-based listener rules on the HTTPS:443 listener: `/api/*` → backend, `/*` → frontend
- Register ECS Fargate services with the new target groups
- Update `FASTAPI_URL` in the frontend container to route through the same ALB
- Update `EagleConfig` with ALB lookup values so the pattern works for dev and QA/staging

## Problem Statement

The EAGLE-DEV-ALB was provisioned by NCI with a trusted ACM certificate, proper DNS, and VPC attachment. Our CDK stack created new HTTP-only ALBs that:
- Lack the ACM certificate (HTTP only, not HTTPS)
- Created duplicate load balancers in the account
- Are not the canonical DNS endpoints for the EAGLE application
- Are internal-only — inaccessible to users without VPN unless we add CloudFront on top

The existing EAGLE-DEV-ALB is the correct entry point and already has HTTPS configured.

## Solution Approach

1. Look up ALB ARN, listener ARN, and security group ID from AWS CLI (one-time discovery)
2. Add `albArn`, `albListenerArn`, `albSecurityGroupId` to `EagleConfig`
3. In `EagleComputeStack`, use `fromApplicationLoadBalancerAttributes()` to import the ALB
4. Use `fromApplicationListenerAttributes()` to import the HTTPS:443 listener
5. Create two new `ip`-type `ApplicationTargetGroup`s for backend and frontend
6. Add `ApplicationListenerRule`s with path-based priority routing
7. Update Fargate service `SecurityGroup`s to allow traffic from the ALB's security group
8. Remove all CDK-created `ApplicationLoadBalancer` constructs
9. Update `FASTAPI_URL` frontend env to point to the ALB DNS name
10. Update `CfnOutput`s to reflect the new HTTPS URLs

## Relevant Files

- `infrastructure/cdk-eagle/lib/compute-stack.ts` — primary target, all ALB/service code
- `infrastructure/cdk-eagle/config/environments.ts` — `EagleConfig` interface + per-env configs
- `infrastructure/cdk-eagle/bin/eagle.ts` — stack instantiation (passes config)
- `.github/workflows/deploy.yml` — `BackendUrl` / `FrontendUrl` outputs used in health check step

### New Files
None — all changes are to existing files.

## Implementation Phases

### Phase 1: Foundation — Discover and Configure

Gather ALB ARN, listener ARN, security group ID from AWS, then add to config.

### Phase 2: Core Implementation — Rewrite `compute-stack.ts`

Replace CDK-created ALBs with imported constructs; add path-based routing; update service SGs.

### Phase 3: Integration & Polish

Update deploy workflow health check URLs, validate CDK synth, deploy and smoke test.

## Step by Step Tasks

### 1. Discover ALB Details from AWS CLI ✅ COMPLETE

Discovery was run on 2026-02-25. All values confirmed:

| Field | Value |
|-------|-------|
| ALB ARN | `arn:aws:elasticloadbalancing:us-east-1:695681773636:loadbalancer/app/EAGLE-DEV-ALB/07cf21fc12866daa` |
| DNS Name | `internal-EAGLE-DEV-ALB-1571243620.us-east-1.elb.amazonaws.com` |
| Security Group | `sg-0f426290543115077` |
| HTTPS:443 Listener ARN | `arn:aws:elasticloadbalancing:us-east-1:695681773636:listener/app/EAGLE-DEV-ALB/07cf21fc12866daa/96eadc16864e583a` |
| HTTP:80 Listener | Redirects → HTTPS 301 (already configured correctly) |
| Existing TG | `EAGLE-DEV-TG` — `instance`-type, port 443, empty — **cannot be used for Fargate** |
| Existing HTTPS rules | Only a default rule → `EAGLE-DEV-TG`. No custom priority rules — clean slate. |

**ALB Security Group — RESOLVED**

The ALB SG initially only allowed inbound from itself (self-referencing). An HTTPS ingress rule was added on 2026-02-25:
- Rule ID: `sgr-0381d7d68481937f4`
- Inbound: TCP 443 from `10.209.140.192/26` (VPC CIDR)
- Outbound: all traffic to `0.0.0.0/0` (already present)

The ALB is now reachable from within the VPC (covers NCI VPN users and the EC2 runner).

### 2. Update `EagleConfig` in `environments.ts`

Add new fields to the `EagleConfig` interface and populate `DEV_CONFIG`:

```typescript
// Add to EagleConfig interface (after desiredCount/maxCount block):
albArn: string;
albHttpsListenerArn: string;
albSecurityGroupId: string;
albDnsName: string;

// Add to DEV_CONFIG (values from Step 1 discovery):
albArn: 'arn:aws:elasticloadbalancing:us-east-1:695681773636:loadbalancer/app/EAGLE-DEV-ALB/07cf21fc12866daa',
albHttpsListenerArn: 'arn:aws:elasticloadbalancing:us-east-1:695681773636:listener/app/EAGLE-DEV-ALB/07cf21fc12866daa/96eadc16864e583a',
albSecurityGroupId: 'sg-0f426290543115077',
albDnsName: 'internal-EAGLE-DEV-ALB-1571243620.us-east-1.elb.amazonaws.com',
```

For `STAGING_CONFIG`, populate with EAGLE-QA-ALB values once discovered.
For `PROD_CONFIG`, populate when prod ALB is provisioned.

### 3. Rewrite `EagleComputeStack` — Remove CDK ALBs, Import Existing

**Delete** the following constructs from `compute-stack.ts`:
- `backendLBSG` (SecurityGroup for CDK backend ALB)
- `backendAlb` (ApplicationLoadBalancer CDK-created)
- `backendTargetGroup` (the old TG)
- `backendAlb.addListener(...)` call
- `frontendLBSG` (SecurityGroup for CDK frontend ALB)
- `frontendAlb` (ApplicationLoadBalancer CDK-created)
- `frontendTargetGroup` (the old TG)
- `frontendAlb.addListener(...)` call

**Replace with imported constructs:**

```typescript
// Import existing EAGLE-DEV-ALB (NCI-provisioned)
const existingAlb = elbv2.ApplicationLoadBalancer.fromApplicationLoadBalancerAttributes(
  this, 'EagleDevAlb',
  {
    loadBalancerArn: config.albArn,
    securityGroupId: config.albSecurityGroupId,
    loadBalancerDnsName: config.albDnsName,
    loadBalancerCanonicalHostedZoneId: '',  // optional, not needed for routing
    vpc,
  }
);

// Import existing HTTPS:443 listener
const httpsListener = elbv2.ApplicationListener.fromApplicationListenerAttributes(
  this, 'EagleDevAlbHttpsListener',
  {
    listenerArn: config.albListenerArn,
    securityGroup: ec2.SecurityGroup.fromSecurityGroupId(
      this, 'AlbSG', config.albSecurityGroupId
    ),
  }
);
```

### 4. Create `ip`-Type Target Groups

Replace old target group definitions with `ip`-type TGs:

```typescript
// Backend target group — ip type required for Fargate
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

// Frontend target group — ip type required for Fargate
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
```

### 5. Add Path-Based Listener Rules

```typescript
// Rule 1 (priority 10): /api/* → backend
new elbv2.ApplicationListenerRule(this, 'BackendListenerRule', {
  listener: httpsListener,
  priority: 10,
  conditions: [elbv2.ListenerCondition.pathPatterns(['/api/*'])],
  targetGroups: [backendTargetGroup],
});

// Rule 2 (priority 20): /* → frontend (catch-all)
new elbv2.ApplicationListenerRule(this, 'FrontendListenerRule', {
  listener: httpsListener,
  priority: 20,
  conditions: [elbv2.ListenerCondition.pathPatterns(['/*'])],
  targetGroups: [frontendTargetGroup],
});
```

> **Note**: If EAGLE-DEV-ALB already has a default action (e.g., fixed 404 response), these priority rules will override it for `/api/*` and `/*`. If the listener already has a default target group, we may need to use `addTargetGroups()` on the imported listener instead. Verify with `aws elbv2 describe-rules --listener-arn <ARN>` before deploying.

### 6. Update Fargate Service Security Groups

Replace `backendServiceSG` and `frontendServiceSG` to allow traffic from the ALB's security group:

```typescript
// Reference ALB security group (already created above as existingAlb's SG)
const albSG = ec2.SecurityGroup.fromSecurityGroupId(
  this, 'AlbSGRef', config.albSecurityGroupId
);

const backendServiceSG = new ec2.SecurityGroup(this, 'BackendServiceSG', {
  vpc,
  description: 'eagle-backend ECS task security group',
});
backendServiceSG.addIngressRule(albSG, ec2.Port.tcp(8000), 'from EAGLE-DEV-ALB');

const frontendServiceSG = new ec2.SecurityGroup(this, 'FrontendServiceSG', {
  vpc,
  description: 'eagle-frontend ECS task security group',
});
frontendServiceSG.addIngressRule(albSG, ec2.Port.tcp(3000), 'from EAGLE-DEV-ALB');
```

### 7. Update Frontend Container Environment

The `FASTAPI_URL` (used by Next.js server-side to call the backend) should now go through the ALB:

```typescript
environment: {
  FASTAPI_URL: `https://${config.albDnsName}`,  // changed from backendAlb.loadBalancerDnsName
  // ...rest unchanged
}
```

This means the frontend → backend call is: frontend container → EAGLE-DEV-ALB:443 → backend TG (via `/api/*` rule).

> **Alternative (lower latency)**: Keep `FASTAPI_URL` pointing directly to the backend container's internal DNS or a VPC-internal Service Connect endpoint. This avoids the round-trip through the ALB for server-to-server calls. Recommend starting with the ALB route for simplicity, then optimize if needed.

### 8. Update `CfnOutput`s

Replace old ALB DNS outputs with the imported ALB HTTPS URL:

```typescript
new cdk.CfnOutput(this, 'AppUrl', {
  value: `https://${config.albDnsName}`,
  description: 'EAGLE application URL (HTTPS via EAGLE-DEV-ALB)',
});
// Remove old BackendUrl and FrontendUrl outputs or update them:
new cdk.CfnOutput(this, 'BackendUrl', {
  value: `https://${config.albDnsName}/api`,
  description: 'Internal URL for the EAGLE backend API',
});
new cdk.CfnOutput(this, 'FrontendUrl', {
  value: `https://${config.albDnsName}`,
  description: 'Internal URL for the EAGLE frontend',
});
```

### 9. Update `.github/workflows/deploy.yml` Health Check

The `verify` job does a curl health check. Update to use HTTPS:

```yaml
- name: Health check
  run: |
    BACKEND_URL="${{ needs.deploy-infra.outputs.backend-url }}"
    # Use -k flag if the ALB cert is internal; or ensure runner can reach it
    curl -sf "${BACKEND_URL}/api/health" | jq . || echo "Backend health check failed"
```

> **Note**: GitHub Actions runners are on the public internet and cannot reach the NCI private ALB directly. The health check step will always fail unless a VPC-connected runner is used (the EC2 runner). Consider making the `verify` job conditional on running from the EC2 runner, or removing the external health check and replacing it with a CloudWatch alarm check instead.

### 10. Validate and Deploy

```bash
# Step 1: Install dependencies
cd infrastructure/cdk-eagle && npm install

# Step 2: Build TypeScript
npm run build

# Step 3: Synth to verify no errors
npx cdk synth --quiet

# Step 4: Diff to see what changes
AWS_PROFILE=eagle npx cdk diff EagleComputeStack

# Step 5: Deploy (only compute stack changes)
AWS_PROFILE=eagle npx cdk deploy EagleComputeStack --require-approval never

# Step 6: Verify ECS tasks registered in target groups
aws elbv2 describe-target-health \
  --profile eagle --region us-east-1 \
  --target-group-arn <BACKEND_TG_ARN>

aws elbv2 describe-target-health \
  --profile eagle --region us-east-1 \
  --target-group-arn <FRONTEND_TG_ARN>

# Step 7: Test endpoints (from EC2 runner or VPN)
curl -k https://<ALB_DNS>/api/health
curl -k https://<ALB_DNS>/
```

## Testing Strategy

**Pre-deploy validation:**
- `npm run build` — TypeScript compiles without errors
- `npx cdk synth --quiet` — CloudFormation template generates without errors
- `npx cdk diff EagleComputeStack` — review changes (should show TG additions, SG changes, old ALB removal)

**Post-deploy validation:**
- Target groups show healthy tasks: `describe-target-health` returns `healthy` for both TGs
- Backend: `curl https://<ALB_DNS>/api/health` returns `{"status": "ok"}`
- Frontend: `curl -I https://<ALB_DNS>/` returns `HTTP/2 200`
- Chat flow: log into EAGLE via browser, send a message, verify response
- Path routing: `curl https://<ALB_DNS>/api/sessions` requires auth and returns 401/403 (not 404)

## Acceptance Criteria

- [ ] `EagleComputeStack` contains no `elbv2.ApplicationLoadBalancer` constructs that create NEW ALBs
- [ ] `EAGLE-DEV-ALB` is imported via `fromApplicationLoadBalancerAttributes()` or equivalent
- [ ] Backend Fargate service is registered as a healthy target in a new `ip`-type target group
- [ ] Frontend Fargate service is registered as a healthy target in a new `ip`-type target group
- [ ] Path-based rules exist: `/api/*` → backend TG (priority 10), `/*` → frontend TG (priority 20)
- [ ] `FrontendUrl` CloudFormation output is `https://<EAGLE-DEV-ALB-DNS>`
- [ ] `BackendUrl` CloudFormation output is `https://<EAGLE-DEV-ALB-DNS>/api`
- [ ] CDK-created ALB SGs (`BackendLBSG`, `FrontendLBSG`) are removed from the stack
- [ ] `cdk synth --quiet` exits 0
- [ ] EC2 runner smoke test: `/api/health` returns 200

## Validation Commands

```bash
# TypeScript build
cd infrastructure/cdk-eagle && npm run build

# CDK synth
npx cdk synth --quiet

# CDK diff (review before deploy)
AWS_PROFILE=eagle npx cdk diff EagleComputeStack

# Deploy
AWS_PROFILE=eagle npx cdk deploy EagleComputeStack --require-approval never

# Smoke test (from EC2 runner)
curl -sf https://<ALB_DNS>/api/health | python3 -m json.tool
curl -sI https://<ALB_DNS>/ | head -5
```

## Notes

### Existing Listener Rules — CONFIRMED CLEAN
HTTPS:443 listener has only a default rule → `EAGLE-DEV-TG` (instance-type, empty). No custom priority rules exist. Priorities 10 and 20 are safe to use.

### ALB Security Group — RESOLVED
SG `sg-0f426290543115077` had only a self-referencing inbound rule (no external access). On 2026-02-25, an HTTPS inbound rule was added (`sgr-0381d7d68481937f4`) allowing TCP 443 from `10.209.140.192/26`. Outbound is unrestricted. No further SG changes needed.

### EAGLE-QA-ALB (Staging)
Once `STAGING_CONFIG` is populated with QA ALB values, the same compute-stack code will automatically use `EAGLE-QA-ALB` for the staging environment deploy.

### CloudFront Alternative
If path-based routing conflicts with existing ALB rules, an alternative is to put CloudFront in front:
- CloudFront origin 1: `/api/*` → backend internal ALB (via VPC Origin)
- CloudFront origin 2: `/*` → frontend internal ALB (via VPC Origin)
This adds HTTPS termination at CloudFront and avoids modifying the existing ALB listener.
