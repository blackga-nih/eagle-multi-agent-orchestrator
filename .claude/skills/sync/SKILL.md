# sync — Hub-and-Spoke Multi-Remote Sync

Manages `blackga-nih/eagle-multi-agent-orchestrator` as the **hub** between two spokes.
Cherry-picks app logic in both directions. Account-specific config never crosses boundaries.

## Invoke

```
/sync status              # See what each remote is ahead/behind by
/sync pull gblack686      # Pull upstream dev commits into hub
/sync pull sm_eagle       # Pull CBIIT commits into hub
/sync push gblack686      # Push hub commits to upstream dev (PR in their repo)
/sync push sm_eagle       # Push hub commits to CBIIT (PR in their repo)
```

## Hub-and-Spoke Model

```
gblack686/sample-multi-tenant-agent-core-app   (dev sandbox, account 274487662938)
              ↕  cherry-pick app logic only
blackga-nih/eagle-multi-agent-orchestrator      ← HUB (account 695681773636)
              ↕  cherry-pick app logic only
CBIIT/sm_eagle                                  (CBIIT production, account TBD)
```

## Remotes

| Remote name | Repo | Direction |
|-------------|------|-----------|
| `upstream` | `gblack686/sample-multi-tenant-agent-core-app` | Pull & Push |
| `sm_eagle` | `CBIIT/sm_eagle` | Pull & Push |
| `origin` | `blackga-nih/eagle-multi-agent-orchestrator` | Hub |

## Ownership Model

| Layer | Hub owns | Spokes own |
|-------|----------|------------|
| `infrastructure/cdk-eagle/config/` | ✅ Never overwrite | Their own account config |
| `infrastructure/cdk-eagle/bin/eagle.ts` | ✅ Never overwrite | Their synthesizer setup |
| `eagle-plugin/` | ✅ NCI content | Their plugin variants |
| `.claude/commands/experts/` | ✅ Hub expertise | — |
| `.gitignore` | ✅ Hub leads | — |
| `server/app/*_store.py` | — | Upstream leads (cherry-pick in) |
| `server/app/main.py` | — | Upstream leads, hub patches |
| `client/` features | Shared | Shared |
| `Justfile`, `scripts/` | Shared | Shared |

## What Never Crosses

**Hub → Spoke (push):** Never send `environments.ts`, `eagle.ts`, `eagle-plugin/`, `.claude/commands/experts/*/expertise.md`, `.gitignore`, `.env*`, `power-user-*` IAM values, NCI account/VPC/subnet/Cognito IDs.

**Spoke → Hub (pull):** Never let spoke's account ID, VPC, subnets, IAM prefix, or Cognito values overwrite hub's. Always `git checkout HEAD` on conflict for hub-owned files.

## PR Strategy

- **Pull**: creates `sync/{remote}-YYYYMMDD` branch on hub → PR into hub's `main`
- **Push**: creates `hub-sync-YYYYMMDD` branch based off spoke's `main` → PR into spoke's `main`
- Always uses `gh api repos/{owner}/{repo}/pulls` (not `gh pr create`) to avoid the untracked-files bug

## Protected-Pattern Scan

Run after every cherry-pick, before every commit.

**Inbound (pull):** Grep staged diff for NCI values being removed/replaced.
**Outbound (push):** Grep staged diff for NCI values leaking into spoke.

Doc-only hits (`.md`, `.claude/specs/`) → flag, don't block.
Infra/config hits → HARD BLOCK.

## sm_eagle Profile

| Value | Detail |
|-------|--------|
| AWS Account | `695681773636` (NIH.NCI.CBIIT.EAGLE.NONPROD) |
| Region | `us-east-1` |
| VPC | `vpc-09def43fcabfa4df6` (`10.209.140.192/26`) — NIH Network Automation managed |
| Cognito User Pool | `us-east-1_ChGLHtmmp` |
| Cognito Client | `4c2k2efviegphkr8bea99382jr` |
| DynamoDB Table | `eagle` |
| S3 Bucket | `eagle-documents-695681773636-dev` |
| ECR Backend | `695681773636.dkr.ecr.us-east-1.amazonaws.com/eagle-backend-dev` |
| ECR Frontend | `695681773636.dkr.ecr.us-east-1.amazonaws.com/eagle-frontend-dev` |
| ECS Cluster | `eagle-dev` |

**Protected patterns for sm_eagle:** `695681773636`, `vpc-09def43fcabfa4df6`, `us-east-1_ChGLHtmmp`, `4c2k2efviegphkr8bea99382jr`, `10.209.140`, `CBIIT`, `NCI-RITM`

Full command spec: `.claude/commands/sync.md`
