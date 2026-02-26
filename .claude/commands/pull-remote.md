# pull-remote — Upstream Sync with NCI Guardrails

Sync `upstream` (`gblack686/sample-multi-tenant-agent-core-app`) into a review branch,
then flag every diff that touches NCI/account-specific configuration before anything lands on main.

---

## Step 1 — Fetch upstream

```bash
git fetch upstream
```

Report the number of commits upstream is ahead of `origin/main`:

```bash
git log origin/main..upstream/main --oneline
```

If upstream is 0 commits ahead, stop and tell the user: "Already in sync. Nothing to merge."

---

## Step 2 — Create a dated sync branch

```bash
BRANCH="sync/upstream-$(date +%Y%m%d)"
git checkout -b "$BRANCH" origin/main
```

---

## Step 3 — Merge upstream (no auto-commit)

```bash
git merge upstream/main --no-commit --no-ff
```

If there are merge conflicts, list them:

```bash
git diff --name-only --diff-filter=U
```

Do NOT resolve conflicts automatically. Present them to the user as a blocklist.

---

## Step 4 — Scan the staged diff for protected patterns

Run each check and collect hits:

```bash
# Account number
git diff --cached | grep -n "695681773636"

# VPC / subnet IDs
git diff --cached | grep -En "vpc-09def43fcabfa4df6|subnet-0[a-f0-9]+"

# IAM power-user roles
git diff --cached | grep -n "power-user-"

# Cognito pool / client
git diff --cached | grep -En "us-east-1_GqZzjtSu9|4cv12gt73qi3nct25vl6mno72a"

# Account-suffixed S3 buckets
git diff --cached | grep -n "695681773636"

# Protected file paths touched
git diff --cached --name-only | grep -E \
  "infrastructure/cdk-eagle/config/environments\.ts|\
infrastructure/cdk-eagle/bin/eagle\.ts|\
\.env|settings\.local\.json|bootstrap-"
```

---

## Step 5 — Categorize and report

Present a table:

| Category | Files / Lines | Action |
|---|---|---|
| **Safe** — no protected patterns | list files | Auto-staged |
| **Review required** — protected pattern hit | file:line | Must be manually verified |
| **Merge conflicts** | file list | Must be resolved before proceeding |

For every protected-pattern hit, show the upstream value vs. what the NCI config should be (from the reference table below).

---

## Step 6 — Commit what's safe, hold the rest

If there are NO protected-pattern hits and NO conflicts:

```bash
git commit -m "chore(sync): merge upstream $(date +%Y-%m-%d)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

If there ARE hits → do NOT commit. Instead tell the user exactly which files need manual review and what to change.

---

## Step 7 — Push sync branch and open PR

```bash
git push origin "$BRANCH"
gh pr create \
  --base main \
  --head "$BRANCH" \
  --title "chore(sync): upstream merge $(date +%Y-%m-%d)" \
  --body "$(cat <<'EOF'
## Upstream Sync

Merging changes from \`gblack686/sample-multi-tenant-agent-core-app\` into \`main\`.

## Protected-pattern scan

<!-- Paste Step 5 table here -->

## Review checklist

- [ ] No AWS account numbers changed (`695681773636`)
- [ ] CDK environments.ts unchanged or manually reconciled
- [ ] IAM role names keep `power-user-` prefix
- [ ] Cognito pool/client IDs unchanged
- [ ] VPC / subnet IDs unchanged
- [ ] No `.env` files included
- [ ] All merge conflicts resolved

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Return the PR URL.

---

## NCI Protected-Value Reference

Use this table when explaining what a protected diff hit means and what the correct NCI value is:

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
| CDK synth role | `power-user-cdk-cfn-exec-role-695681773636-us-east-1` | CDK deploy fails |

---

## Files always protected (never auto-merge)

```
infrastructure/cdk-eagle/config/environments.ts
infrastructure/cdk-eagle/bin/eagle.ts
infrastructure/cdk-eagle/bootstrap-*.yaml
client/.env.local
server/.env
.claude/settings.local.json
```

These files must be manually diffed and reconciled, never overwritten by upstream.
