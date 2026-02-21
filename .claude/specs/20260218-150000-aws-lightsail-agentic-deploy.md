# Plan: Zero-Touch Agentic EAGLE Deployment via Lightsail

## Summary

Fully automated deployment of the EAGLE platform from a Lightsail instance. Two approaches:
- **Option A**: Deterministic script (`just setup`) — no AI needed, fastest
- **Option B**: Claude Code agent — handles errors, adapts, verifies, can troubleshoot

Both require a single manual prerequisite: **Bedrock model access** (no CLI/API exists — [AWS CLI #9691](https://github.com/aws/aws-cli/issues/9691)).

## Can It Be Fully Zero-Touch?

| Step | Automatable? | How |
|------|-------------|-----|
| Provision Lightsail instance | Yes | `aws lightsail create-instances` or boto3 |
| Install deps (Docker, Node, Python, just) | Yes | User-data (cloud-init) script |
| Clone repo | Yes | `git clone` in user-data |
| Configure AWS credentials | Yes | `.env` file injected via user-data |
| Create S3 bucket | Yes | `just setup` → `_create-bucket` |
| CDK bootstrap + deploy | Yes | `just setup` → `cdk-install` + `_cdk-bootstrap` + `cdk-deploy` |
| Build + push containers | Yes | `just setup` → `deploy` |
| Create Cognito users | Yes | `just setup` → `create-users` |
| **Enable Bedrock model access** | **NO** | **AWS Console only** — must be done before deploy |
| Verify deployment | Yes | `just check-aws` + `just status` |

**Answer: 99% automated. One manual click (Bedrock) per AWS account, one time.**

## Required `.env` Variables

```bash
# === Target AWS Account ===
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
AWS_DEFAULT_REGION=us-east-1

# === Git ===
GIT_REPO=https://github.com/gblack686/sample-multi-tenant-agent-core-app.git
GIT_BRANCH=main

# === Claude Code (Option B only) ===
ANTHROPIC_API_KEY=sk-ant-...
```

### IAM Permissions Required

The AWS credentials need these permissions (admin is simplest, or scoped):

```
cloudformation:*          # CDK stacks
ec2:*                     # VPC, subnets, NAT, security groups
ecs:*                     # Fargate cluster, services, tasks
ecr:*                     # Container registry
elasticloadbalancing:*    # ALBs
cognito-idp:*             # User pool, users, groups
dynamodb:*                # Eagle table
s3:*                      # nci-documents bucket, CDK assets
iam:*                     # Roles, policies, OIDC provider
logs:*                    # CloudWatch log groups
sts:GetCallerIdentity     # CDK bootstrap
ssm:GetParameter          # CDK
bedrock:InvokeModel*      # Runtime (after model access enabled)
```

## Option A: Deterministic Script (Recommended)

No Claude Code needed. A bash user-data script runs `just setup` directly.

### Architecture

```
Local machine (or CI)
  │
  ├── aws lightsail create-instances --user-data bootstrap.sh
  │
  └── Lightsail Instance (Ubuntu 22.04)
        │
        ├── cloud-init installs: Docker, Node 20, Python 3.11, just, git
        ├── git clone $GIT_REPO
        ├── writes .env from injected variables
        ├── just setup  (S3 → CDK → containers → users → verify)
        │
        └── EAGLE running on ECS Fargate
              ├── Frontend ALB (public)
              └── Backend ALB (internal)
```

### Implementation: `scripts/bootstrap-lightsail.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

# --- Configuration (injected via user-data or .env) ---
: "${AWS_ACCESS_KEY_ID:?Required}"
: "${AWS_SECRET_ACCESS_KEY:?Required}"
: "${AWS_DEFAULT_REGION:=us-east-1}"
: "${GIT_REPO:=https://github.com/gblack686/sample-multi-tenant-agent-core-app.git}"
: "${GIT_BRANCH:=main}"

LOG=/var/log/eagle-bootstrap.log
exec &> >(tee -a "$LOG")
echo "=== EAGLE Bootstrap $(date -Iseconds) ==="

# --- Install dependencies ---
apt-get update && apt-get install -y \
  docker.io docker-compose-plugin python3 python3-pip python3-venv \
  nodejs npm git curl unzip

# Install just
curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to /usr/local/bin

# Install Node 20 via nvm
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt-get install -y nodejs

# Start Docker
systemctl enable docker && systemctl start docker

# --- Configure AWS ---
mkdir -p ~/.aws
cat > ~/.aws/credentials << CREDS
[default]
aws_access_key_id = $AWS_ACCESS_KEY_ID
aws_secret_access_key = $AWS_SECRET_ACCESS_KEY
CREDS
cat > ~/.aws/config << CONF
[default]
region = $AWS_DEFAULT_REGION
output = json
CONF

# --- Clone and deploy ---
cd /opt
git clone --branch "$GIT_BRANCH" "$GIT_REPO" eagle
cd eagle

# Install Python deps for boto3 (used by Justfile)
pip3 install boto3

# Run full setup
just setup

echo "=== EAGLE Bootstrap COMPLETE $(date -Iseconds) ==="
echo "Run 'just urls' to see application URLs"
```

### Justfile Recipe: `just provision`

```just
# Provision a Lightsail instance and auto-deploy EAGLE
provision:
    python scripts/provision_lightsail.py
```

### `scripts/provision_lightsail.py`

```python
#!/usr/bin/env python3
"""Provision a Lightsail instance with EAGLE auto-deploy."""
import boto3
import os
import sys
from pathlib import Path

REGION = "us-east-1"
INSTANCE_NAME = "eagle-deployer"
BLUEPRINT = "ubuntu_22_04"
BUNDLE = "medium_3_0"  # 2 vCPU, 4 GB RAM, $40/mo

def main():
    # Read bootstrap script
    script_path = Path(__file__).parent / "bootstrap-lightsail.sh"
    if not script_path.exists():
        print("Error: scripts/bootstrap-lightsail.sh not found", file=sys.stderr)
        sys.exit(1)

    user_data = script_path.read_text()

    # Inject env vars into the script header
    env_block = "\n".join([
        f'export AWS_ACCESS_KEY_ID="{os.environ["AWS_ACCESS_KEY_ID"]}"',
        f'export AWS_SECRET_ACCESS_KEY="{os.environ["AWS_SECRET_ACCESS_KEY"]}"',
        f'export AWS_DEFAULT_REGION="{os.environ.get("AWS_DEFAULT_REGION", REGION)}"',
        f'export GIT_REPO="{os.environ.get("GIT_REPO", "https://github.com/gblack686/sample-multi-tenant-agent-core-app.git")}"',
        f'export GIT_BRANCH="{os.environ.get("GIT_BRANCH", "main")}"',
    ])
    user_data = f"#!/usr/bin/env bash\n{env_block}\n{user_data}"

    ls = boto3.client("lightsail", region_name=REGION)

    print(f"Creating Lightsail instance: {INSTANCE_NAME}")
    ls.create_instances(
        instanceNames=[INSTANCE_NAME],
        availabilityZone=f"{REGION}a",
        blueprintId=BLUEPRINT,
        bundleId=BUNDLE,
        userData=user_data,
        tags=[
            {"key": "Project", "value": "eagle"},
            {"key": "ManagedBy", "value": "just-provision"},
        ],
    )

    print(f"Instance '{INSTANCE_NAME}' launching...")
    print("Monitor bootstrap: ssh ubuntu@<ip> 'tail -f /var/log/eagle-bootstrap.log'")
    print("Once complete: ssh ubuntu@<ip> 'cd /opt/eagle && just urls'")


if __name__ == "__main__":
    main()
```

## Option B: Claude Code Agent

Same Lightsail instance, but Claude Code runs the deployment interactively. Adds error handling, verification, and troubleshooting that a static script can't do.

### Additional `.env`

```bash
ANTHROPIC_API_KEY=sk-ant-...  # For Claude Code itself
```

### Bootstrap Addition (after deps install)

```bash
# Install Claude Code
npm install -g @anthropic-ai/claude-code

# Run Claude Code with a deployment prompt
claude --print --dangerously-skip-permissions \
  "You are deploying the EAGLE platform to AWS. Steps:
   1. Run 'just setup' and monitor for errors
   2. If any step fails, diagnose and fix the issue
   3. Run 'just check-aws' to verify all services
   4. Run 'just urls' and report the live URLs
   5. Run 'just create-users' if users weren't created
   The AWS credentials are already configured. Bedrock model access is already enabled.
   Do NOT ask questions — just execute and report results."
```

### When Option B Makes Sense

| Scenario | Option A | Option B |
|----------|----------|----------|
| Happy path (everything works) | 15-20 min | 20-30 min |
| CDK bootstrap issue | Fails, needs manual fix | Claude Code diagnoses + fixes |
| Docker build failure | Fails | Claude Code reads logs, adjusts |
| ECR first-deploy chicken-and-egg | Needs placeholder images | Claude Code handles it |
| Network/timeout issues | Fails | Claude Code retries with backoff |
| Unknown errors | Fails | Claude Code reads error, searches codebase, adapts |

## Pre-Flight Checklist (Before Triggering)

- [ ] AWS credentials with admin access (or scoped per IAM list above)
- [ ] **Bedrock model access enabled** in target account (Console → Bedrock → Model Access → Anthropic Claude) — THIS IS THE ONE MANUAL STEP
- [ ] `.env` file with required variables
- [ ] (Option B only) Anthropic API key for Claude Code

## Estimated Timeline

| Phase | Duration |
|-------|----------|
| Lightsail instance boot | 1-2 min |
| Dependency install | 3-5 min |
| CDK bootstrap + deploy (4 stacks) | 10-15 min |
| Docker build + ECR push | 5-8 min |
| ECS service stabilization | 3-5 min |
| User creation + verification | 1 min |
| **Total** | **~25-35 min** |

## Cost Impact

| Resource | Monthly Cost |
|----------|-------------|
| Lightsail instance (medium) | $40 (can terminate after deploy) |
| ECS Fargate (dev tier) | ~$35-50 |
| NAT Gateway (1) | ~$32 |
| ALB (2) | ~$32 |
| DynamoDB (on-demand) | ~$1-5 |
| S3 | < $1 |
| **Total platform** | **~$100-120/mo** |
| Lightsail deployer (if kept) | +$40/mo |

## Rollback

```bash
# Terminate deployer instance
aws lightsail delete-instance --instance-name eagle-deployer

# Destroy EAGLE platform (if needed)
cd infrastructure/cdk-eagle && npx cdk destroy --all
aws ecr delete-repository --repository-name eagle-backend-dev --force
aws ecr delete-repository --repository-name eagle-frontend-dev --force
aws s3 rb s3://nci-documents --force
```

## Recommendation

**Start with Option A** (deterministic script). It's simpler, faster, and `just setup` already handles the full chain. Add Option B only if you need:
- Multi-account rollout where each account may have different issues
- Self-healing deployment that can troubleshoot novel errors
- A demo of agentic infrastructure management
