# Checklist B: EC2 Runner Deployment (Standard)

> **This is the recommended deploy path for NCI.** No local Docker required — all builds happen on the EC2 runner inside the VPC using its instance-role credentials.

## B0 — Prerequisites

- [ ] **AWS CLI** with SSO profile `eagle` configured
- [ ] SSM Session Manager plugin installed: `aws ssm install-plugin`
- [ ] EC2 runner `i-0390c06d166d18926` in account `695681773636`

## B1 — Open SSM Session

```bash
aws sso login --profile eagle
AWS_PROFILE=eagle aws ssm start-session \
  --target i-0390c06d166d18926 \
  --region us-east-1
```

No SSH keys, no bastion host — SSM handles authentication via IAM.

## B2 — Switch to Eagle User and Pull Latest Code

```bash
su -s /bin/bash eagle
cd /home/eagle/eagle

# Pull latest from your branch
git pull origin dev/greg   # or main for production
```

> **Updating from Windows**: If git pull fails (no direct GitHub access from EC2), use the bundle method:
> ```bash
> # On Windows: create and upload bundle
> git bundle create /tmp/bundle.bundle dev/greg
> aws s3 cp /tmp/bundle.bundle s3://eagle-eval-artifacts-695681773636-dev/deploy/
>
> # On EC2: download and apply
> aws s3 cp s3://eagle-eval-artifacts-695681773636-dev/deploy/bundle.bundle /tmp/
> git -C /home/eagle/eagle pull /tmp/bundle.bundle dev/greg
> ```

## B3 — Deploy

```bash
# Full deploy: ECR login → build backend → build frontend → push → ECS rolling update
just deploy

# Or separately:
just deploy-backend
just deploy-frontend
```

`just deploy` automatically:
1. Logs into ECR using instance role credentials
2. Reads Cognito config from CloudFormation outputs (no manual env vars)
3. Builds both Docker images (Linux, matching container OS)
4. Pushes to ECR with `latest` and `$COMMIT_SHA` tags
5. Triggers ECS rolling updates and waits for `services-stable`

## B4 — Verify

```bash
just check-aws   # 7/7 OK: Identity, S3, DDB×2, Lambda, ECS×2
just status      # ECS running counts
just urls        # frontend + backend ALB URLs
```

## B5 — Access the App

The ALBs are **VPC-internal** — not reachable from the public internet. Access requires being on the NCI network (VPN or SSM port-forward).

**Get the frontend URL:**
```bash
AWS_PROFILE=eagle aws cloudformation describe-stacks --stack-name EagleComputeStack \
  --query "Stacks[0].Outputs[?contains(OutputKey,'FrontendUrl')].OutputValue" \
  --output text --region us-east-1
```

**Login credentials** (created by `just create-users`):

| Role | Email | Password |
|------|-------|----------|
| Standard user | testuser@example.com | EagleTest2024! |
| Admin | admin@example.com | EagleAdmin2024! |

> **First login note**: Cognito may prompt for a password change. Enter `EagleTest2024!` as both old and new password to clear the prompt.

## B6 — Run Smoke Tests from EC2

The EC2 runner also supports running the full smoke + eval suite:

```bash
# Eval suite (28 tests against Bedrock/haiku)
just eval

# Smoke tests (Playwright against local Docker stack)
just smoke mid
```

> Playwright and Chromium are pre-installed on the runner. Browsers are in `/home/eagle/.cache/ms-playwright`.
