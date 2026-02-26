# pull-remote Skill

Syncs `upstream` (`gblack686/sample-multi-tenant-agent-core-app`) into a `sync/upstream-YYYYMMDD`
branch using **cherry-pick** (not merge) so history stays linear and GitHub PRs diff cleanly.

## Invoke

```
/pull-remote
```

## What it does

1. `git fetch upstream` — pulls latest from `gblack686/sample-multi-tenant-agent-core-app`
2. Lists non-merge upstream commits not yet in `origin/main` (`--no-merges`)
3. Creates `sync/upstream-YYYYMMDD` off `origin/main`
4. `git cherry-pick $COMMITS --no-commit` — stages all changes without committing
5. Resolves NCI-owned file conflicts via `git checkout HEAD` (ownership model)
6. Removes upstream noise (scratch files, test artifacts)
7. Scans staged diff for NCI-specific values (account ID, VPC, subnets, IAM prefix, Cognito IDs)
8. Commits + pushes + opens GitHub PR if no hard blocks

## Why cherry-pick, not merge

Upstream has `Merge remote-tracking branch 'blackga-nih/main'` commits pointing back at our repo.
A `git merge upstream/main` makes the merge base = our current HEAD → GitHub sees "zero new commits"
and refuses to create the PR. Cherry-pick `--no-merges` skips those back-merges entirely.

## Ownership model

| Layer | Owner | Rule |
|-------|-------|------|
| `infrastructure/cdk-eagle/config/` | **NCI** | Never overwrite — `git checkout HEAD` on conflict |
| `infrastructure/cdk-eagle/bin/` | **NCI** | Never overwrite |
| `eagle-plugin/` | **NCI** | Domain content lives here |
| `.claude/commands/experts/` | **NCI** | NCI expertise is more current |
| `.gitignore`, repo hygiene | **NCI** | NCI leads |
| `server/app/*_store.py` | **Upstream leads** | New modules cherry-picked in |
| `server/app/main.py` | **Upstream leads, NCI patches** | Cherry-pick, watch for conflicts |
| `client/` features | Shared | Cherry-pick, review per commit |

## Protected files (never cherry-pick over)

| File | Reason |
|------|--------|
| `infrastructure/cdk-eagle/config/environments.ts` | NCI account, VPC, subnet IDs |
| `infrastructure/cdk-eagle/bin/eagle.ts` | CDK synthesizer with power-user-cdk-* roles |
| `eagle-plugin/` | Agent/skill domain content |
| `.claude/commands/experts/*/expertise.md` | NCI deployment expertise |
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
