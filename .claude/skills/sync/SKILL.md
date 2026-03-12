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

**CBIIT's `claude-code-assistant.yml` workflow has been manually disabled** (no ANTHROPIC_API_KEY secret). Disable via API before pushing:
```bash
gh api -X PUT repos/CBIIT/sm_eagle/actions/workflows/238385374/disable
```

Full command spec: `.claude/commands/sync.md`

---

## Learned Patterns (from sync sessions)

### filter-branch: always use `-f` when re-running on the same branch

Running `git filter-branch --msg-filter` a second time on the same branch fails with:

> Cannot create a new backup. A previous backup already exists in refs/original/

Always include the `-f` flag:
```bash
git filter-branch -f --msg-filter '...' {base}..HEAD
```

### Strip Co-Authored-By before pushing to spokes

Remove `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>` from commits being synced using filter-branch before force-pushing:
```bash
git filter-branch -f --msg-filter 'sed "/Co-Authored-By: Claude Sonnet 4\.6 <noreply@anthropic\.com>/d"' {base}..HEAD
```

### Disable GitHub workflow via API (no code commit required)

To disable a workflow on a remote repo without making a code commit:
```bash
gh api -X PUT repos/{owner}/{repo}/actions/workflows/{workflow_id}/disable
```
Get workflow IDs:
```bash
gh api repos/{owner}/{repo}/actions/workflows --jq '.workflows[] | "\(.id) \(.name)"'
```

### Cherry-pick: skip merge commits with `--skip`

When cherry-picking a range and hitting a merge commit, use `git cherry-pick --skip` (not `--continue`) to skip it — all individual commits from that merge are already applied.

### Python scripts: always use `encoding="utf-8"` for file opens

Any Python script that processes git output (commit messages, diffs) must open files with `encoding="utf-8"` to avoid `UnicodeDecodeError` on Windows:
```python
open(path, "r", encoding="utf-8")
```

### Windows: use `git cat-file -p` instead of `git show` for remote file content

On Windows (MINGW64), `git show remote/branch:path/to/file` may fail with "ambiguous argument". Use:
```bash
git cat-file -p remote/branch:path/to/file
```
Or confirm existence first with `git ls-tree remote/branch path/to/file`.

### Untracked large files block branch checkout

Move untracked large files (docx, images) to `/tmp` before switching branches to avoid "would be overwritten by checkout" errors.

### Protected scan: account-specific S3 bucket names

Always grep outbound commits for the pattern `eagle-documents-{account_id}-dev` (e.g. `eagle-documents-695681773636-dev`). Sanitize to `eagle-documents-dev` before pushing to any spoke. This is a HARD BLOCK pattern.
