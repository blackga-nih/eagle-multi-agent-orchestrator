---
type: expert-file
parent: "[[git/_index]]"
file-type: expertise
human_reviewed: false
tags: [expert-file, mental-model, git, github, actions, cicd]
last_updated: 2026-03-16T00:00:00
---

# Git/CI-CD Expertise (Complete Mental Model)

> **Sources**: Existing `.github/workflows/`, repository branch history, GitHub Actions documentation, Claude Code Action docs, multi-session observations (2026-02-11 through 2026-03-16)

---

## Part 1: Repository Structure

### Multi-Remote Setup

This repository uses a **multi-remote pattern** with NCI (origin) as upstream and personal forks for development:

```
origin       — https://github.com/gblack686/sample-multi-tenant-agent-core-app (primary personal repo)
blackga-nih  — https://github.com/blackga-nih/eagle-multi-agent-orchestrator (personal fork, alternate)
openclaw     — https://github.com/gblack686-openclaw/sample-multi-tenant-agent-core-app (org fork)
```

**Sync Pattern**:
- Pull from `origin` (or sync from upstream NCI if applicable)
- Push to `origin` for CI/CD triggers
- `blackga-nih` can serve as backup/personal tracking remote

### Branch Naming Conventions

```
main                    — Production branch (currently unprotected)
feature/*               — Feature branches (e.g., feat/api-routes-explorer)
fix/*                   — Bug fix branches
chore/*                 — Infrastructure/maintenance branches
dev/*                   — Developer working branches (legacy, use feature/* instead)
```

**Current Active Branches**:

| Branch | Purpose | Status |
|--------|---------|--------|
| `main` | Production | Primary, receives pushes from CI/CD |
| `feat/api-routes-explorer` | Feature in progress | Local development |

### Branch Protection Status

As of 2026-03-16, **`main` branch is NOT protected** (API returns 404). Recommended rules:

```yaml
main:
  - Require pull request reviews: 1
  - Require status checks to pass: [ci, lint, test]
  - Require branches to be up to date
  - Require commit signoffs (optional but recommended)
  - No force pushes
  - No deletions
  - Restrict who can push to matching branches
```

### Merge Strategy

**Recommended**: Squash merge for feature branches to main.
- Keeps main history clean
- Individual feature commits preserved in branch history
- PR description becomes the merge commit message

---

## Part 2: GitHub Actions Workflows

### Existing Workflows Inventory

#### `deploy.yml` — Infrastructure Deploy (ACTIVE, OIDC-based)

```yaml
File: .github/workflows/deploy.yml
Triggers: push to main, workflow_dispatch
Auth: OIDC (aws-actions/configure-aws-credentials@v4)
Concurrency: deploy-${{ github.ref }} with cancel-in-progress
Permissions: contents: read, id-token: write
Jobs:
  1. changes:
     - Uses dorny/paths-filter to detect changed paths
     - Outputs: infra, backend, frontend (boolean flags)
  2. ci:
     - Runs ruff (backend lint), pytest (backend tests)
     - Runs tsc --noEmit (frontend type check)
     - Runs cdk synth (infrastructure check)
  3. deploy-infra:
     - Runs: npx cdk deploy EagleCiCdStack EagleStorageStack EagleEvalStack EagleBackupStack --exclusively
     - --exclusively: prevents CDK from following addDependency() chains to skipped stacks
     - Skips EagleCoreStack (DynamoDB exists outside CFN)
     - Skips EagleComputeStack (ECS updates via force-new-deployment)
  4. deploy-backend:
     - Builds docker image, pushes to ECR
     - Updates ECS task definition with EAGLE_BEDROCK_MODEL_ID env var
     - Updates ECS service with force-new-deployment
     - Waits for service stability (ecs wait services-stable)
  5. deploy-frontend:
     - Builds docker image, pushes to ECR
     - Injects Cognito config (NEXT_PUBLIC_COGNITO_*) from EagleCoreStack CloudFormation
     - Updates ECS service with force-new-deployment
     - Syncs target group to new task IP (ALB integration)
```

**Strengths**:
- OIDC-based auth (no static IAM keys)
- Path-based CI skipping (fast feedback for docs-only changes)
- Concurrency control to prevent simultaneous deployments
- SHA-pinned actions with version comments
- CloudFormation + ECS integration for full-stack deploy

**Dependencies**:
- `deploy-backend` and `deploy-frontend` both depend on `deploy-infra` (via `needs`)
- If `ci` fails, `deploy-infra` is skipped

#### `claude-code-assistant.yml` — Merge Analysis (LEGACY, being phased out)

```yaml
File: .github/workflows/claude-code-assistant.yml
Triggers: PR events, issue comments
Auth: ANTHROPIC_API_KEY secret
Action: anthropics/claude-code-action@v1
Jobs:
  1. merge-analysis (if PR opened/synchronized):
     - Collects PR/issue context
     - Runs Claude analysis → structured JSON
     - Posts report as PR comment
```

#### `eval.yml` — Evaluation Suite (NIGHTLY)

```yaml
File: .github/workflows/eval.yml
Triggers: schedule (nightly), workflow_dispatch
Runs comprehensive test suite on main branch
(Does NOT run on every deploy — separated for performance)
```

#### Other Workflows

| File | Trigger | Purpose |
|------|---------|---------|
| `jira-commits-sync.yml` | push | Sync commits to Jira |
| `linear-claude-agent.yml` | issues | AI issue triage (Linear) |
| `pr-diagram-linker.yml` | PR | Link excalidraw diagrams |
| `build.yml` | workflow_dispatch | S3 smoke test (self-hosted runner) |

### Action Pinning Conventions (SHA Required)

```yaml
# GOOD: SHA-pinned for security + version comment for auditability
- uses: actions/checkout@b4ffde65f46336ab88eb53be808477a3936bae11  # v4.1.1
- uses: actions/setup-python@0a5c61591373683505ea898e09a3ea4f39ef2b9c  # v5.0.0
- uses: actions/setup-node@60edb5dd545a775178f52524783378180af0d1f8  # v4.0.2
- uses: aws-actions/configure-aws-credentials@e3dd6a429d7300a6a4c196c26e071d42e0343502  # v4.0.2
- uses: docker/build-push-action@v5  (build-push is OK with v5, widely stable)

# OK for first-party/stable: version tag
- uses: anthropics/claude-code-action@v1

# BAD: floating tag (never use in production)
- uses: actions/checkout@v4  # Could change without notice
```

**Policy**: Always include `# vX.Y.Z` comment after SHA pin for human auditability.

### Commit Message Convention

**Format**: `{type}({scope}): {description}`

**Types**: `feat`, `fix`, `chore`, `refactor`, `docs`, `test`, `perf`

**Scope**: e.g., `arch`, `ui`, `tests`, `ci`, `deploy`

**Example**:
```
feat(arch+ui): regenerate all 9 excalidraw diagrams, Package tab, and route additions

- Regenerate all 9 architecture diagrams with codebase-validated corrections
- Add Package tab to activity panel wired to live SSE update_state metadata
- Add session routes (audit-logs, documents, summary), admin API explorer

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

**Claude Commits Trailer** (required for all Claude-assisted commits):
```
Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

Use `git commit -m "$(cat <<'EOF' ... EOF)"` to preserve trailers via HEREDOC.

### Secrets Management

| Secret | Purpose | Used By | Type |
|--------|---------|---------|------|
| `DEPLOY_ROLE_ARN` | AWS OIDC role assumption | deploy.yml | OIDC (no static key) |
| `ANTHROPIC_API_KEY` | Claude API access | claude-code-assistant.yml | Static token |

**OIDC is preferred** over static credentials. Current setup uses `aws-actions/configure-aws-credentials@v4` with `role-to-assume`.

### OIDC Authentication Pattern (Recommended)

```yaml
permissions:
  id-token: write    # Required for OIDC
  contents: read

steps:
  - uses: aws-actions/configure-aws-credentials@e3dd6a429d7300a6a4c196c26e071d42e0343502  # v4.0.2
    with:
      role-to-assume: ${{ secrets.DEPLOY_ROLE_ARN }}
      aws-region: us-east-1
```

**Requires**: IAM OIDC provider configured (see aws expert for setup).

---

## Part 3: CI Pipeline Patterns

### Python Backend CI (deploy.yml)

```yaml
backend-ci:
  needs: changes
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@b4ffde65f46336ab88eb53be808477a3936bae11  # v4.1.1
    - uses: actions/setup-python@0a5c61591373683505ea898e09a3ea4f39ef2b9c  # v5.0.0
      with:
        python-version: '3.11'
        cache: 'pip'
        cache-dependency-path: server/requirements.txt
    - name: Install dependencies
      run: pip install -r server/requirements.txt ruff pytest pytest-asyncio
    - name: Lint (ruff)
      run: cd server && ruff check app/
    - name: Test (pytest)
      env:
        USE_BEDROCK: 'false'
        AWS_DEFAULT_REGION: us-east-1
      run: cd server && python -m pytest tests/test_agentcore_services.py -v
```

### Next.js Frontend CI (deploy.yml)

```yaml
frontend-ci:
  needs: changes
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@b4ffde65f46336ab88eb53be808477a3936bae11  # v4.1.1
    - uses: actions/setup-node@60edb5dd545a775178f52524783378180af0d1f8  # v4.0.2
      with:
        node-version: '20'
        cache: 'npm'
        cache-dependency-path: client/package-lock.json
    - name: Install dependencies
      run: cd client && npm ci
    - name: Type check (tsc)
      run: cd client && npx tsc --noEmit
```

### CDK Synth CI (deploy.yml)

```yaml
cdk-ci:
  needs: changes
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@b4ffde65f46336ab88eb53be808477a3936bae11  # v4.1.1
    - uses: actions/setup-node@60edb5dd545a775178f52524783378180af0d1f8  # v4.0.2
      with:
        node-version: '20'
        cache: 'npm'
        cache-dependency-path: infrastructure/cdk-eagle/package-lock.json
    - name: Install dependencies
      run: cd infrastructure/cdk-eagle && npm ci
    - name: CDK Synth
      run: cd infrastructure/cdk-eagle && npx cdk synth --quiet
```

### Conditional Execution via Path Filters (deploy.yml)

Uses `dorny/paths-filter@v3` to detect changed paths:

```yaml
changes:
  outputs:
    infra: ${{ steps.filter.outputs.infra }}
    backend: ${{ steps.filter.outputs.backend }}
    frontend: ${{ steps.filter.outputs.frontend }}
  steps:
    - uses: dorny/paths-filter@v3
      id: filter
      with:
        filters: |
          infra:
            - 'infrastructure/**'
          backend:
            - 'server/**'
            - 'eagle-plugin/**'
            - 'deployment/docker/Dockerfile.backend'
          frontend:
            - 'client/**'
            - 'deployment/docker/Dockerfile.frontend'

ci:
  needs: changes
  steps:
    - if: needs.changes.outputs.backend == 'true' || github.event_name == 'workflow_dispatch'
      run: ruff check server/
```

This skips lint/test for paths that didn't change, reducing CI time.

### Parallel Job Execution

```yaml
jobs:
  changes:
    runs-on: ubuntu-latest
    # Outputs detected path changes
  ci:
    needs: changes
    runs-on: ubuntu-latest
    # Runs all CI steps conditionally based on changes
  deploy-infra:
    needs: [changes, ci]
    # Waits for CI to complete
  deploy-backend:
    needs: [changes, ci, deploy-infra]
    # Waits for infra deploy to complete
  deploy-frontend:
    needs: [changes, ci, deploy-infra]
    # Waits for infra deploy to complete (parallel with backend)
```

### Caching Strategies

| Language | Cache Key | Path | Config |
|----------|-----------|------|--------|
| Python | `server/requirements.txt` | `~/.cache/pip` | `cache: 'pip'` |
| Node.js | `client/package-lock.json` | `~/.npm` | `cache: 'npm'` |
| Node.js (CDK) | `infrastructure/cdk-eagle/package-lock.json` | `~/.npm` | `cache: 'npm'` |

GitHub Actions uses GHA (GitHub Actions Cache) by default; Docker also uses `cache-from: type=gha,scope=backend`.

---

## Part 4: CD Pipeline Patterns

### CDK Deploy (deploy.yml)

```yaml
deploy-infra:
  needs: [changes, ci]
  if: github.event_name == 'push' || (github.event_name == 'workflow_dispatch' && inputs.deploy_infra == 'true')
  steps:
    - uses: aws-actions/configure-aws-credentials@e3dd6a429d7300a6a4c196c26e071d42e0343502  # v4.0.2
      with:
        role-to-assume: ${{ secrets.DEPLOY_ROLE_ARN }}
        aws-region: us-east-1
    - run: |
        cd infrastructure/cdk-eagle
        # EagleCoreStack: skip — DynamoDB table exists outside CloudFormation
        # EagleComputeStack: skip — ECS service logical IDs changed
        # --exclusively: prevent CDK from following addDependency() chains
        npx cdk deploy EagleCiCdStack EagleStorageStack EagleEvalStack EagleBackupStack \
          --exclusively --require-approval never --outputs-file outputs.json
```

**Key Flags**:
- `--exclusively`: Prevents CDK from deploying dependent stacks (EagleCoreStack, EagleComputeStack)
- `--require-approval never`: Skips manual approval in CI (safe because code is reviewed in PR)

### Docker Build + ECR Push (deploy.yml)

```yaml
deploy-backend:
  needs: [changes, ci, deploy-infra]
  steps:
    - uses: aws-actions/configure-aws-credentials@e3dd6a429d7300a6a4c196c26e071d42e0343502  # v4.0.2
      with:
        role-to-assume: ${{ secrets.DEPLOY_ROLE_ARN }}
        aws-region: us-east-1
    - name: Derive ECR URI
      id: ecr
      run: |
        ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
        echo "uri=${ACCOUNT}.dkr.ecr.us-east-1.amazonaws.com/eagle-backend-dev" >> $GITHUB_OUTPUT
    - uses: aws-actions/amazon-ecr-login@062b18b96a7aff071d4dc91bc00c4c1a7945b076  # v2.0.1
    - uses: docker/setup-buildx-action@v3
    - uses: docker/build-push-action@v5
      with:
        context: .
        file: deployment/docker/Dockerfile.backend
        push: true
        tags: |
          ${{ steps.ecr.outputs.uri }}:${{ github.sha }}
          ${{ steps.ecr.outputs.uri }}:latest
        cache-from: type=gha,scope=backend
        cache-to: type=gha,mode=max,scope=backend
```

**Tagging Strategy**:
- `{uri}:{github.sha}` — immutable commit-based tag (for rollback)
- `{uri}:latest` — latest successful build

### ECS Task Definition + Service Update (deploy.yml)

```yaml
deploy-backend:
  steps:
    - name: Update task definition
      id: task-def
      run: |
        # Fetch current task def, remove read-only fields, inject env vars
        aws ecs describe-task-definition --task-definition eagle-backend-dev \
          --query 'taskDefinition' --output json > /tmp/current_td.json

        # Python script removes: taskDefinitionArn, revision, status, etc.
        # Injects: EAGLE_BEDROCK_MODEL_ID env var
        python3 - <<'PYEOF'
        import json
        with open('/tmp/current_td.json') as f:
            td = json.load(f)
        for key in ['taskDefinitionArn', 'revision', 'status', ...]:
            td.pop(key, None)
        env = td['containerDefinitions'][0].get('environment', [])
        env = [e for e in env if e['name'] != 'EAGLE_BEDROCK_MODEL_ID']
        env.append({'name': 'EAGLE_BEDROCK_MODEL_ID', 'value': 'us.anthropic.claude-sonnet-4-6'})
        td['containerDefinitions'][0]['environment'] = env
        with open('/tmp/new_td.json', 'w') as f:
            json.dump(td, f)
        PYEOF

        # Register new task definition
        NEW_TD_ARN=$(aws ecs register-task-definition \
          --cli-input-json file:///tmp/new_td.json \
          --query 'taskDefinition.taskDefinitionArn' --output text)
        echo "task-def-arn=$NEW_TD_ARN" >> $GITHUB_OUTPUT

    - name: Update service
      run: |
        aws ecs update-service \
          --cluster eagle-dev \
          --service eagle-backend-dev \
          --task-definition ${{ steps.task-def.outputs.task-def-arn }} \
          --force-new-deployment

    - name: Wait for stability
      run: |
        aws ecs wait services-stable \
          --cluster eagle-dev \
          --services eagle-backend-dev
```

**Pattern**:
1. Register new task definition (immutable snapshot)
2. Update service with `--force-new-deployment` (forces rolling update)
3. Wait for service to stabilize (`ecs wait services-stable`)

### Environment Promotion

```
dev/staging  → auto-deploy on push to main (via deploy.yml push trigger)
production   → manual approval (workflow_dispatch with inputs)
```

---

## Part 5: Release Management

### Semantic Versioning

```
MAJOR.MINOR.PATCH
  |     |     |
  |     |     +-- Bug fixes, patches
  |     +-------- New features, backward compatible
  +-------------- Breaking changes
```

### Git Tag Convention

```bash
# Create annotated tag
git tag -a v1.2.3 -m "Release v1.2.3: Feature description"
git push origin v1.2.3

# Tag naming: v{MAJOR}.{MINOR}.{PATCH}
```

### Changelog Generation Pattern (eval.yml reference)

```yaml
release:
  steps:
    - name: Generate changelog
      run: |
        PREV_TAG=$(git describe --tags --abbrev=0 HEAD~1 2>/dev/null || echo "")
        if [ -n "$PREV_TAG" ]; then
          git log ${PREV_TAG}..HEAD --oneline --no-merges > CHANGELOG_DELTA.md
        else
          git log --oneline -20 > CHANGELOG_DELTA.md
        fi
```

### Rollback Procedures

```bash
# Revert to previous release
git revert HEAD --no-edit
git push origin main
# CI/CD will auto-deploy the revert

# Or: deploy a specific tag via workflow_dispatch
git checkout v1.2.2
# Trigger deploy.yml manually with branch=v1.2.2
```

---

## Part 6: Claude Code Action Integration

### anthropics/claude-code-action@v1 (Legacy, being phased out)

```yaml
- uses: anthropics/claude-code-action@v1
  with:
    prompt: |
      Analyze this PR and provide structured feedback...
    claude_args: |
      --model claude-opus-4-6
      --max-tokens 8000
      --temperature 0.2
    structured_outputs: true
    output_file: analysis.json
```

### Integration Notes

- `claude-code-assistant.yml` uses this for merge analysis
- Structured outputs can be parsed as JSON
- Outputs posted as PR comments for visibility

---

## Part 7: Known Issues & Patterns

### Action SHA Pinning

**Issue**: SHA hashes are opaque and hard to audit
**Fix**: Always include version comment: `@{sha}  # v4.1.1`

Current status (2026-03-16): **All third-party actions in deploy.yml are SHA-pinned with version comments** ✓

### Secrets Not Available in Fork PRs

**Issue**: `${{ secrets.* }}` are empty for `pull_request` from forks
**Fix**: Use `pull_request_target` trigger (with security review of the PR changes first)

### OIDC vs Static Credentials

**Issue**: Legacy workflows used static IAM keys
**Current Status** (2026-03-16): **deploy.yml uses OIDC** ✓

### Branch Protection Missing

**Issue**: `main` branch is NOT protected (404 from API)
**Recommended Action**: Enable protection with PR reviews, status checks, commit signoffs

### Multi-Remote Complexity

**Issue**: Multiple remotes (origin, blackga-nih, openclaw) can cause confusion
**Recommended Practice**:
- Use `origin` as primary push target
- Sync from `origin` on daily basis
- Use `blackga-nih` only for personal backup/tracking (if needed)
- Clearly document remote purposes in team wiki

### Workflow Dispatch Manual Triggers

**Status**: deploy.yml defines `workflow_dispatch` inputs properly:

```yaml
on:
  workflow_dispatch:
    inputs:
      deploy_infra:
        description: 'Deploy CDK infrastructure'
        required: false
        default: 'true'
        type: string
      deploy_app:
        description: 'Build and deploy application'
        required: false
        default: 'true'
        type: string
```

This allows selective deployment (infra without app, or vice versa).

### Windows Line Ending Issues

**Status**: Repository is configured with `.gitattributes` (check if present)

```gitattributes
*.sh text eol=lf
*.yml text eol=lf
```

Ensures YAML files maintain LF line endings even on Windows clones.

---

## Part 8: Learnings & Best Practices

### patterns_that_work

- **SHA-pinned actions with version comments** — provides security + auditability
- **Path-based CI skipping** (dorny/paths-filter) — reduces feedback time for docs-only changes
- **Concurrency groups** (`deploy-${{ github.ref }}`) — prevents simultaneous deploys to same environment
- **OIDC for AWS auth** — eliminates static credential management
- **Task definition versioning** — register new TD before updating service (immutable snapshots)
- **ECS wait services-stable** — ensures deployment is complete before marking job done
- **Large atomic commits** — fine for diagram batches or refactors (e.g., 8 excalidraw files in one commit)
- **Commit trailers** — `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>` documents AI involvement
- **Squash merge strategy** — keeps main history clean while preserving branch work

### patterns_to_avoid

- **Static IAM keys** in GitHub secrets (use OIDC instead)
- **Floating action version tags** (use SHA pins with version comments)
- **Single monolithic workflow file** (split CI/CD into separate workflows if possible)
- **Force pushing to main** (even with permissions, breaks history for team)
- **Committing .env files or secrets** (use `.gitignore` + `.env.example`)
- **Unprotected main branch** — enable PR reviews + status checks
- **Workflow files with hardcoded account IDs** — use `${{ secrets.DEPLOY_ROLE_ARN }}` instead

### common_issues

- `OIDC provider not configured` — Need to create IAM OIDC provider for GitHub Actions (see aws expert)
- `Workflow not triggered` — Check trigger conditions, branch filters, path filters
- `Deploy fails on main but works on feature branch` — Check `if:` conditions and concurrency settings
- `Task definition update fails` — Verify read-only fields are removed (taskDefinitionArn, revision, etc.)
- `Branch protection not enforced` — API returns 404 = not configured; use GitHub web UI to enable
- `Multi-remote confusion` — Document which remotes are used and why (e.g., origin=primary, blackga-nih=backup)

### tips

- Run `/experts:git:maintenance` to validate all workflow YAML files before committing
- Use `workflow_dispatch` with typed inputs for manual deployment control (e.g., selective infra vs app deploy)
- Add `concurrency` groups to prevent parallel deploys to the same environment
- Cache npm and pip dependencies for faster CI runs (use `cache-dependency-path` for precision)
- Use `actions/upload-artifact` to preserve build outputs across jobs (useful for CDK outputs)
- Test large workflow changes locally with `act --dry-run` before pushing
- Always include commit trailers for Claude-assisted work: `Co-Authored-By: Claude {Model} <noreply@anthropic.com>`
- Monitor multi-remote pushes: verify `git push origin main` is going to the right remote

---

## Changelog (2026-03-16 Update)

### Added
- Multi-remote setup documentation (origin, blackga-nih, openclaw)
- Branch protection status assessment (currently missing)
- Co-Authored-By trailer convention for Claude-assisted commits
- Detailed deploy.yml job documentation with OIDC patterns
- Path-based CI skipping (dorny/paths-filter) patterns
- ECS task definition + service update patterns
- Commit message format standardization
- `--exclusively` flag documentation for CDK deploy

### Updated
- Section 1: Branch naming to include unprotected main status
- Section 2: Workflow inventory with current active patterns
- Section 3: CI pipeline patterns with conditional execution
- Section 4: CD pipeline patterns with ECS integration details
- Part 7: Known issues with 2026-03-16 status checks
- Part 8: Learnings with multi-remote and commit trailer best practices

### Removed
- Obsolete Python CDK patterns (infrastructure/cdk/ was deprecated)
- References to static IAM key auth (migrated to OIDC)
