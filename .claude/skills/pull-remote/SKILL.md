# pull-remote Skill

Syncs `upstream` (`gblack686/sample-multi-tenant-agent-core-app`) into a `sync/upstream-YYYYMMDD`
branch and runs a protected-pattern scan before anything touches main.

## Invoke

```
/pull-remote
```

## What it does

1. `git fetch upstream` — pulls latest from `gblack686/sample-multi-tenant-agent-core-app`
2. Creates `sync/upstream-YYYYMMDD` off `origin/main`
3. `git merge --no-commit --no-ff` — stages changes without committing
4. Scans staged diff for NCI-specific values (account ID, VPC, subnets, IAM prefix, Cognito IDs)
5. Reports safe files vs. files needing manual review
6. Commits + pushes only if no protected patterns hit
7. Opens a GitHub PR against `main` with the scan results pre-filled

## Protected files (never auto-merged)

| File | Reason |
|------|--------|
| `infrastructure/cdk-eagle/config/environments.ts` | NCI account, VPC, subnet IDs |
| `infrastructure/cdk-eagle/bin/eagle.ts` | CDK synthesizer with power-user-cdk-* roles |
| `infrastructure/cdk-eagle/bootstrap-*.yaml` | Account-specific bootstrap (gitignored) |
| `client/.env.local` | Cognito client ID |
| `server/.env` | Runtime secrets |
| `.claude/settings.local.json` | Local Claude permissions |

## Protected pattern grep targets

| Pattern | Risk |
|---------|------|
| `695681773636` | AWS account number — breaks all ARNs |
| `vpc-09def43fcabfa4df6` | NCI VPC ID — ECS/ALB lose network |
| `subnet-0[a-f0-9]+` | Subnet IDs — Fargate placement fails |
| `power-user-` | IAM role prefix — CDK deploy role not found |
| `us-east-1_GqZzjtSu9` | Cognito user pool — auth breaks |
| `4cv12gt73qi3nct25vl6mno72a` | Cognito client ID — frontend login fails |

## Upstream remote

```
upstream → https://github.com/gblack686/sample-multi-tenant-agent-core-app.git
```

Full command spec: `.claude/commands/pull-remote.md`
