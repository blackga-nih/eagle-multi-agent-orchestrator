# pull-remote — Upstream Sync with NCI Guardrails

Sync `upstream` (`gblack686/sample-multi-tenant-agent-core-app`) into a review branch
using **cherry-pick** (not merge), so the PR history stays linear and GitHub can diff it cleanly.

## Ownership model

| Layer | Owner | Rule |
|-------|-------|------|
| `infrastructure/cdk-eagle/config/` | **NCI** | Never overwrite |
| `infrastructure/cdk-eagle/bin/` | **NCI** | Never overwrite |
| `eagle-plugin/` (agents, skills) | **NCI** | Never overwrite |
| `.claude/commands/experts/` | **NCI** | NCI expertise is more current |
| `.gitignore`, repo hygiene | **NCI** | NCI leads |
| `server/app/*_store.py` (new modules) | **Upstream leads** | Cherry-pick in |
| `server/app/main.py` | **Upstream leads, NCI patches** | Cherry-pick, watch for conflicts |
| `client/` (frontend features) | Shared — review per commit | Cherry-pick |
| `Justfile`, `scripts/`, `deployment/` | Shared — review per commit | Cherry-pick |

---

## Step 1 — Fetch upstream

```bash
git fetch upstream
```

Show what's new — **non-merge commits only** (skip upstream's merge-of-NCI commits):

```bash
git log origin/main..upstream/main --oneline --no-merges --reverse
```

If there are 0 new commits, stop: "Already in sync."

Save the list:

```bash
COMMITS=$(git log origin/main..upstream/main --no-merges --reverse --format="%H")
COUNT=$(echo "$COMMITS" | grep -c .)
echo "$COUNT new commits to cherry-pick"
```

---

## Step 2 — Create a dated sync branch

```bash
BRANCH="sync/upstream-$(date +%Y%m%d)"
git checkout -b "$BRANCH" origin/main
```

---

## Step 3 — Cherry-pick upstream commits (no auto-commit)

Apply all non-merge upstream commits as a single staged diff, without committing:

```bash
git cherry-pick $COMMITS --no-commit 2>&1
```

If cherry-pick reports conflicts:

```bash
git diff --name-only --diff-filter=U
```

For each conflicted file, apply the **ownership rule** from the table above:
- **NCI-owned files** → `git checkout HEAD -- <file>` (keep ours, discard upstream)
- **Upstream-owned or shared files** → resolve manually, keeping NCI-specific values

Do NOT auto-resolve shared files. Report the conflict list to the user.

---

## Step 4 — Exclude noise files

Always unstage these regardless of what upstream committed:

```bash
# Upstream scratch files
git rm --cached upstream-changes.patch upstream-changes-summary.md 2>/dev/null || true

# Test artifacts
git rm --cached -r client/playwright-report/ client/test-results/ 2>/dev/null || true
```

---

## Step 5 — Scan the staged diff for protected patterns

```bash
# Account number
git diff --cached | grep -n "695681773636"

# VPC / subnet IDs
git diff --cached | grep -En "vpc-09def43fcabfa4df6|subnet-0[a-f0-9]+"

# IAM power-user roles
git diff --cached | grep -n "power-user-"

# Cognito pool / client
git diff --cached | grep -En "us-east-1_GqZzjtSu9|4cv12gt73qi3nct25vl6mno72a"

# Protected file paths touched
git diff --cached --name-only | grep -E \
  "infrastructure/cdk-eagle/config/environments\.ts|\
infrastructure/cdk-eagle/bin/eagle\.ts|\
\.env|settings\.local\.json|bootstrap-"
```

A hit in a **spec/doc file** (`.claude/specs/`, `.md` docs) is informational — flag it but do not block.
A hit in **any other file** is a hard block — do not commit, explain what needs fixing.

---

## Step 6 — Categorize and report

Present a summary table:

| Category | Files | Action |
|----------|-------|--------|
| **Safe** — no pattern hits, NCI-owned files untouched | list | Auto-staged |
| **NCI-owned file conflict** | file list | Already resolved via `git checkout HEAD` |
| **Protected pattern hit (doc only)** | file:line | Flagged, not blocked |
| **Protected pattern hit (infra/config)** | file:line | BLOCKED — fix before commit |
| **Unresolved conflicts** | file list | BLOCKED — must resolve manually |

---

## Step 7 — Commit and push

If no hard blocks:

```bash
git commit -m "chore(sync): cherry-pick upstream $(date +%Y-%m-%d) — $COUNT commits

Non-merge upstream commits cherry-picked from gblack686/sample-multi-tenant-agent-core-app.
NCI-specific config (environments.ts, eagle.ts, VPC, IAM, Cognito) unchanged.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"

git push origin "$BRANCH"
```

---

## Step 8 — Open PR

```bash
gh pr create \
  --base main \
  --head "$BRANCH" \
  --title "chore(sync): upstream cherry-pick $(date +%Y-%m-%d)" \
  --body "$(cat <<'EOF'
## Upstream Sync — Cherry-Pick

Cherry-picked $COUNT non-merge commits from \`gblack686/sample-multi-tenant-agent-core-app\`.
Uses cherry-pick (not merge) to keep history linear and PRs diffable.

## Ownership decisions

NCI-owned files (\`infrastructure/cdk-eagle/config/\`, \`eagle-plugin/\`, \`.claude/commands/experts/\`) — upstream changes discarded per ownership model.
Upstream-owned files (\`server/app/*_store.py\`, \`main.py\`, frontend features) — cherry-picked in.

## Protected-pattern scan

<!-- paste Step 6 table here -->

## Review checklist

- [ ] AWS account \`695681773636\` unchanged in infra
- [ ] CDK \`environments.ts\` / \`eagle.ts\` unchanged
- [ ] \`power-user-\` IAM prefix unchanged
- [ ] Cognito pool/client IDs unchanged
- [ ] NCI VPC / subnet IDs unchanged in infra
- [ ] No \`.env\` files included

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Return the PR URL.

---

## NCI Protected-Value Reference

| Key | NCI Value | Risk if overwritten |
|-----|-----------|---------------------|
| AWS Account | `695681773636` | All resource ARNs break |
| VPC | `vpc-09def43fcabfa4df6` | ECS, ALB lose network |
| PrivateSubnet-01 | `subnet-0acfc5795a31620c4` | Fargate tasks unplaceable |
| PrivateSubnet-02 | `subnet-06c0f502dc9c178ae` | Fargate tasks unplaceable |
| EdgeSubnet-01 | `subnet-0b13e7a760e1606f3` | ALB routing breaks |
| EdgeSubnet-02 | `subnet-0a1bbbd502dc187e0` | ALB routing breaks |
| IAM prefix | `power-user-` | CDK deploy role not found |
| Cognito pool | `us-east-1_GqZzjtSu9` | Auth completely breaks |
| Cognito client | `4cv12gt73qi3nct25vl6mno72a` | Frontend login fails |
| S3 bucket | `eagle-documents-695681773636-dev` | Document upload/download fails |

---

## Files always protected (never cherry-pick over)

```
infrastructure/cdk-eagle/config/environments.ts
infrastructure/cdk-eagle/bin/eagle.ts
infrastructure/cdk-eagle/bootstrap-*.yaml
eagle-plugin/
client/.env.local
server/.env
.claude/settings.local.json
.claude/commands/experts/*/expertise.md
```
