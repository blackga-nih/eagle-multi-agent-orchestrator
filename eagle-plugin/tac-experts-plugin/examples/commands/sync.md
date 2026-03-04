# sync — Hub-and-Spoke Multi-Remote Sync

`blackga-nih/eagle-multi-agent-orchestrator` is the **hub**. It cherry-picks app logic
from two spokes and pushes app logic back — never crossing account-specific config.

```
gblack686/sample-multi-tenant-agent-core-app  (upstream dev)
              ↕ cherry-pick app logic
blackga-nih/eagle-multi-agent-orchestrator     ← HUB
              ↕ cherry-pick app logic
CBIIT/sm_eagle                                 (CBIIT production)
```

---

## Usage

Parse the user's command argument:

| Command | Action |
|---------|--------|
| `/sync status` | Show each remote ahead/behind count |
| `/sync pull gblack686` | Pull upstream dev → hub |
| `/sync pull sm_eagle` | Pull CBIIT → hub |
| `/sync push gblack686` | Push hub → upstream dev (opens PR in their repo) |
| `/sync push sm_eagle` | Push hub → CBIIT (opens PR in their repo) |

If no argument given, run `status` first and ask which operation to perform.

---

## Remote Profiles

### `upstream` → gblack686/sample-multi-tenant-agent-core-app

- GitHub: `https://github.com/gblack686/sample-multi-tenant-agent-core-app`
- Dev/sandbox account — no PermissionBoundary_PowerUser constraint
- Their account: `274487662938`, VPC: `vpc-0ede565d9119f98aa`
- **Pull ownership**: upstream leads on `server/app/*_store.py`, `main.py`, frontend features; hub owns infra/config/experts
- **Push ownership**: hub sends app logic; suppress NCI infra config

### `sm_eagle` → CBIIT/sm_eagle

- GitHub: `https://github.com/CBIIT/sm_eagle`
- CBIIT-managed production repo — may have stricter IAM/review requirements
- Their account: **`695681773636`** — same AWS account as hub (NCI account)
- VPC/subnets: identical to hub (`vpc-09def43fcabfa4df6`, same subnet IDs)
- Only material differences: `githubOwner: 'CBIIT'`, `githubRepo: 'sm_eagle'` in `environments.ts`
- **Pull ownership**: sm_eagle leads on compliance/policy features and CBIIT-specific integrations; hub owns NCI infra, `.claude/`, `eagle-plugin/`
- **Push ownership**: hub sends app logic and skill improvements; suppress NCI infra config

---

## Step 0 — status (always run first if direction unclear)

```bash
git fetch upstream
git fetch sm_eagle

echo "=== upstream (gblack686) ==="
UPSTREAM_AHEAD=$(git log origin/main..upstream/main --no-merges --oneline | wc -l)
HUB_AHEAD_UPSTREAM=$(git log upstream/main..origin/main --no-merges --oneline | wc -l)
echo "  upstream ahead of hub: $UPSTREAM_AHEAD non-merge commits"
echo "  hub ahead of upstream: $HUB_AHEAD_UPSTREAM non-merge commits"

echo "=== sm_eagle (CBIIT) ==="
SM_AHEAD=$(git log origin/main..sm_eagle/main --no-merges --oneline | wc -l)
HUB_AHEAD_SM=$(git log sm_eagle/main..origin/main --no-merges --oneline | wc -l)
echo "  sm_eagle ahead of hub: $SM_AHEAD non-merge commits"
echo "  hub ahead of sm_eagle: $HUB_AHEAD_SM non-merge commits"
```

Present as a summary table and suggest which operations make sense.

---

## PULL operations

### Pull from gblack686 (`/sync pull gblack686`)

1. `git fetch upstream`
2. List non-merge commits not in hub:
   ```bash
   git log origin/main..upstream/main --oneline --no-merges --reverse
   ```
3. Filter out commits touching gitignored/NCI-owned files:
   ```bash
   # For each SHA, check if it touches these paths — SKIP if so:
   SKIP_PATHS="contract-requirements-matrix|gb\.txt|aws/cloud_formation|testing\.txt|cursor-shortcuts|\.vtt|\.zip|tac-experts-plugin"
   ```
4. Cherry-pick the filtered list with `--no-commit`
5. Resolve NCI-owned file conflicts via `git checkout HEAD -- <file>`
6. Remove noise: `git rm --cached upstream-changes.patch upstream-changes-summary.md client/playwright-report/ client/test-results/ 2>/dev/null || true`
7. Run protected-pattern scan (see Scan section)
8. If clean: commit + push `sync/upstream-YYYYMMDD` + open PR via `gh api`

### Pull from sm_eagle (`/sync pull sm_eagle`)

1. `git fetch sm_eagle`
2. List non-merge commits not in hub:
   ```bash
   git log origin/main..sm_eagle/main --oneline --no-merges --reverse
   ```
3. Filter out commits touching CBIIT-specific infra/config paths:
   ```bash
   SKIP_PATHS="infrastructure/cdk-eagle/config|infrastructure/cdk-eagle/bin|\.env|settings\.local"
   ```
4. Cherry-pick filtered list with `--no-commit`
5. Resolve hub-owned file conflicts via `git checkout HEAD -- <file>`
6. Run protected-pattern scan
7. If clean: commit + push `sync/sm-eagle-YYYYMMDD` + open PR via `gh api`

---

## PUSH operations

### Push to gblack686 (`/sync push gblack686`)

Hub pushes its commits to upstream. They get app logic; their infra config is untouched.

1. `git fetch upstream`
2. Find hub commits upstream doesn't have:
   ```bash
   git log upstream/main..origin/main --oneline --no-merges --reverse
   ```
3. Filter out hub-specific commits that shouldn't go upstream (infra, NCI config):
   ```bash
   # SKIP commits touching:
   SKIP_PATHS="infrastructure/cdk-eagle/config|infrastructure/cdk-eagle/bin|\
   eagle-plugin|\.claude/commands/experts|\.gitignore|client/\.env|server/\.env|\
   bootstrap-|pull-remote|sync\.md|\.warp"
   ```
4. If 0 commits remain after filtering: "Nothing new to push to gblack686."
5. Clone or create a branch on the hub that's based off `upstream/main`:
   ```bash
   BRANCH="hub-sync-$(date +%Y%m%d)"
   git checkout -b "$BRANCH" upstream/main
   ```
6. Cherry-pick the filtered hub commits with `--no-commit`
7. Run protected-pattern scan IN REVERSE — look for NCI values that shouldn't go to gblack686:
   ```bash
   git diff --cached | grep -En "695681773636|vpc-09def43fcabfa4df6|subnet-0acfc5795a31620c4|\
   subnet-06c0f502dc9c178ae|subnet-0b13e7a760e1606f3|subnet-0a1bbbd502dc187e0|\
   us-east-1_GqZzjtSu9|4cv12gt73qi3nct25vl6mno72a|power-user-cdk-"
   ```
   If hits: show the file:line to the user; do NOT commit until resolved.
8. Commit + push branch to `upstream`:
   ```bash
   git push upstream "$BRANCH"
   ```
9. Open PR **in their repo** via `gh api`:
   ```bash
   gh api repos/gblack686/sample-multi-tenant-agent-core-app/pulls \
     --method POST \
     --field title="feat(hub): hub sync $(date +%Y-%m-%d) from blackga-nih" \
     --field head="blackga-nih:$BRANCH" \
     --field base="main" \
     --field body="Hub-to-spoke sync from blackga-nih/eagle-multi-agent-orchestrator. App logic only — NCI infra config excluded." \
     --jq '.html_url'
   ```
10. Return the PR URL. Go back to hub's `main`.

### Push to sm_eagle (`/sync push sm_eagle`)

Hub pushes its commits to CBIIT. Same pattern as gblack686 push.

1. `git fetch sm_eagle`
2. Find hub commits sm_eagle doesn't have:
   ```bash
   git log sm_eagle/main..origin/main --oneline --no-merges --reverse
   ```
3. Filter — same SKIP_PATHS as gblack686 push
4. Branch off `sm_eagle/main`:
   ```bash
   BRANCH="hub-sync-$(date +%Y%m%d)"
   git checkout -b "$BRANCH" sm_eagle/main
   ```
5. Cherry-pick filtered commits with `--no-commit`
6. Reverse protected-pattern scan (NCI values must not appear)
7. Commit + push branch to `sm_eagle`:
   ```bash
   git push sm_eagle "$BRANCH"
   ```
8. Open PR **in their repo** via `gh api`:
   ```bash
   gh api repos/CBIIT/sm_eagle/pulls \
     --method POST \
     --field title="feat(hub): hub sync $(date +%Y-%m-%d) from blackga-nih" \
     --field head="blackga-nih:$BRANCH" \
     --field base="main" \
     --field body="Hub-to-spoke sync from blackga-nih/eagle-multi-agent-orchestrator. App logic only — NCI infra config excluded." \
     --jq '.html_url'
   ```
9. Return PR URL. Go back to hub's `main`.

---

## Protected-Pattern Scan

Run after every cherry-pick, before every commit.

### Inbound scan (pull) — look for spoke's account values overwriting hub's

```bash
# NCI values that must NOT be replaced by upstream values
git diff --cached | grep -En \
  "695681773636|vpc-09def43fcabfa4df6|subnet-0acfc5795a31620c4|subnet-06c0f502dc9c178ae|\
subnet-0b13e7a760e1606f3|subnet-0a1bbbd502dc187e0|us-east-1_GqZzjtSu9|4cv12gt73qi3nct25vl6mno72a|\
power-user-"

# Protected files touched
git diff --cached --name-only | grep -E \
  "infrastructure/cdk-eagle/config/environments\.ts|infrastructure/cdk-eagle/bin/eagle\.ts|\
\.env|settings\.local\.json|bootstrap-"
```

### Outbound scan (push) — look for NCI values leaking into spoke

```bash
git diff --cached | grep -En \
  "695681773636|vpc-09def43fcabfa4df6|subnet-0acfc5795a31620c4|subnet-06c0f502dc9c178ae|\
power-user-cdk-|us-east-1_GqZzjtSu9|4cv12gt73qi3nct25vl6mno72a"
```

**Doc-only hits** (in `.md`, `.claude/specs/`) — flag but do not block.
**Infra/config hits** — HARD BLOCK. Explain to user what must be removed.

---

## Conflict Resolution Rules

| File category | Pull conflict resolution | Push conflict resolution |
|---------------|--------------------------|--------------------------|
| `infrastructure/cdk-eagle/config/` | `git checkout HEAD -- <file>` (keep hub) | Skip entirely (don't cherry-pick) |
| `infrastructure/cdk-eagle/bin/eagle.ts` | `git checkout HEAD -- <file>` | Skip |
| `eagle-plugin/` | `git checkout HEAD -- <file>` | Skip |
| `.claude/commands/experts/*/expertise.md` | `git checkout HEAD -- <file>` | Skip |
| `server/app/*.py` (app logic) | Take incoming (upstream leads) | Cherry-pick in |
| `client/` (frontend) | Resolve manually — report to user | Cherry-pick in |
| `Justfile`, `scripts/` | Take incoming | Cherry-pick in |
| `gitignored files` | `git rm --cached` (keep our delete) | Skip |

---

## NCI Hub Protected Values

| Key | NCI Value |
|-----|-----------|
| AWS Account | `695681773636` |
| VPC | `vpc-09def43fcabfa4df6` |
| PrivateSubnet-01 | `subnet-0acfc5795a31620c4` |
| PrivateSubnet-02 | `subnet-06c0f502dc9c178ae` |
| EdgeSubnet-01 | `subnet-0b13e7a760e1606f3` |
| EdgeSubnet-02 | `subnet-0a1bbbd502dc187e0` |
| IAM prefix | `power-user-` |
| Cognito pool | `us-east-1_GqZzjtSu9` |
| Cognito client | `4cv12gt73qi3nct25vl6mno72a` |
| S3 bucket | `eagle-documents-695681773636-dev` |

## gblack686 Spoke Values (for reverse scan)

| Key | Their Value |
|-----|-------------|
| AWS Account | `274487662938` |
| VPC | `vpc-0ede565d9119f98aa` |
| PublicSubnet-01 | `subnet-0dafab85c993a5dd8` |
| PublicSubnet-02 | `subnet-07e67841820650b5d` |

## sm_eagle Spoke Values

sm_eagle uses the **same NCI account** (`695681773636`) as hub. Outbound scan uses identical
protected-pattern list as the inbound scan — no separate values to track.

| Key | sm_eagle Value |
|-----|----------------|
| AWS Account | `695681773636` (same as hub) |
| VPC | `vpc-09def43fcabfa4df6` (same as hub) |
| Subnets | Identical to hub NCI subnets |
| GitHub owner | `CBIIT` |
| GitHub repo | `sm_eagle` |
