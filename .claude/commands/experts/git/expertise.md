---
type: expert-file
parent: "[[git/_index]]"
file-type: expertise
human_reviewed: false
tags: [expert-file, mental-model, git, github, actions, cicd]
last_updated: 2026-02-11T00:00:00
---

# Git/CI-CD Expertise (Complete Mental Model)

> **Sources**: Existing `.github/workflows/`, repository branch history, GitHub Actions documentation, Claude Code Action docs

---

## Part 1: Repository Structure

### Branch Naming Conventions

```
main                    — Production branch (protected)
dev/{name}              — Developer working branches
feat/{feature-name}     — Feature branches
fix/{bug-description}   — Bug fix branches
release/{version}       — Release preparation branches
hotfix/{description}    — Emergency production fixes
```

### Current Branches

| Branch | Purpose | Status |
|--------|---------|--------|
| `main` | Production | Primary branch |
| `dev/greg` | Developer working branch | Active |
| `feat/eagle-plugin-integration` | EAGLE plugin integration | Active |

### Merge Strategy

**Recommended**: Squash merge for feature branches to main.
- Keeps main history clean
- Individual feature commits preserved in branch history
- PR description becomes the merge commit message

### Protected Branch Rules (Recommended)

```
main:
  - Require pull request reviews: 1
  - Require status checks to pass: [ci, lint, test]
  - Require branches to be up to date
  - No force pushes
  - No deletions
```

---

## Part 2: GitHub Actions Workflows

### Existing Workflows Inventory

#### `deploy.yml` — Infrastructure Deploy

```yaml
File: .github/workflows/deploy.yml
Triggers: push to main, PR to main, workflow_dispatch
Auth: Static IAM keys (AWS_ACCESS_KEY_ID secret)
Jobs:
  1. deploy-infrastructure:
     - CDK bootstrap + deploy (infra/cdk/, Python stack)
     - Bedrock agent creation
     - Extract CDK outputs
  2. setup-frontend:
     - Depends on deploy-infrastructure
     - Creates .env.local for Next.js
     - Only runs on main branch push
```

**Issues**:
- Uses static IAM keys (should migrate to OIDC)
- Deploys Python CDK stack (`infra/cdk/`), not TypeScript eval stack
- No lint/test/build verification before deploy
- No rollback capability

#### `claude-merge-analysis.yml` — AI Code Review

```yaml
File: .github/workflows/claude-merge-analysis.yml
Triggers: PR events, PR target, issue comments, issue labels
Auth: ANTHROPIC_API_KEY secret
Action: anthropics/claude-code-action@v1
Jobs:
  1. merge-analysis:
     - Collects PR/issue context
     - Runs Claude analysis → structured JSON
     - Posts report as PR comment
     - Uploads artifact
  2. create-feature-branch:
     - Only if analysis recommends changes
     - Creates branch, applies changes via Claude
     - Creates PR
```

**Strengths**:
- Uses Claude Code Action v1
- Structured JSON output
- Automated PR creation for recommended changes
- SHA-pinned actions

### Action Pinning Conventions

```yaml
# GOOD: SHA-pinned for security
- uses: actions/checkout@b4ffde65f46336ab88eb53be808477a3936bae11  # v4.1.1

# OK for first-party: version tag
- uses: anthropics/claude-code-action@v1

# BAD: floating tag
- uses: actions/checkout@v4  # Could change without notice
```

### Secrets Management

| Secret | Purpose | Used By |
|--------|---------|---------|
| `AWS_ACCESS_KEY_ID` | AWS static credentials | deploy.yml |
| `AWS_SECRET_ACCESS_KEY` | AWS static credentials | deploy.yml |
| `ANTHROPIC_API_KEY` | Claude API access | claude-merge-analysis.yml |
| `COGNITO_USER_POOL_ID` | Cognito auth | deploy.yml |
| `COGNITO_CLIENT_ID` | Cognito auth | deploy.yml |
| `BEDROCK_AGENT_ID` | Bedrock agent | deploy.yml |
| `OPENWEATHER_API_KEY` | Weather API | deploy.yml |
| `SESSIONS_TABLE` | DynamoDB table | deploy.yml |
| `USAGE_TABLE` | DynamoDB table | deploy.yml |

### OIDC Authentication Pattern

```yaml
# Preferred over static keys
permissions:
  id-token: write
  contents: read

steps:
  - uses: aws-actions/configure-aws-credentials@v4
    with:
      role-to-assume: arn:aws:iam::{ACCOUNT_ID}:role/github-actions-deploy
      aws-region: us-east-1
```

**Requires**: IAM OIDC provider + trust policy (see aws expert).

---

## Part 3: CI Pipeline Patterns

### Python Backend CI

```yaml
backend-ci:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: '3.11'
        cache: 'pip'
        cache-dependency-path: server/requirements.txt
    - name: Install dependencies
      run: pip install -r server/requirements.txt
    - name: Syntax check
      run: python -m py_compile server/app/agentic_service.py
    - name: Type check (optional)
      run: pip install mypy && mypy server/app/ --ignore-missing-imports
    - name: Lint (optional)
      run: pip install ruff && ruff check server/
```

### Next.js Frontend CI

```yaml
frontend-ci:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-node@v4
      with:
        node-version: '20'
        cache: 'npm'
        cache-dependency-path: client/package-lock.json
    - name: Install dependencies
      run: cd client && npm ci
    - name: Type check
      run: cd client && npx tsc --noEmit
    - name: Lint
      run: cd client && npm run lint
    - name: Build
      run: cd client && npm run build
```

### CDK Synth CI

```yaml
cdk-ci:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-node@v4
      with:
        node-version: '20'
    - name: Install CDK dependencies
      run: cd infra/eval && npm ci
    - name: CDK Synth
      run: cd infra/eval && npx cdk synth
```

### Parallel Job Execution

```yaml
jobs:
  backend-ci:   # Independent
    ...
  frontend-ci:  # Independent
    ...
  cdk-ci:       # Independent
    ...
  deploy:       # Depends on all CI jobs
    needs: [backend-ci, frontend-ci, cdk-ci]
    if: github.ref == 'refs/heads/main'
    ...
```

### Caching Strategies

| Dependency Manager | Cache Key | Path |
|-------------------|-----------|------|
| npm | `client/package-lock.json` | `~/.npm` |
| pip | `server/requirements.txt` | `~/.cache/pip` |
| CDK | `infra/eval/package-lock.json` | `~/.npm` |

---

## Part 4: CD Pipeline Patterns

### CDK Deploy

```yaml
deploy-cdk:
  needs: [ci]
  if: github.ref == 'refs/heads/main'
  steps:
    - name: Configure AWS (OIDC)
      uses: aws-actions/configure-aws-credentials@v4
      with:
        role-to-assume: ${{ vars.CDK_DEPLOY_ROLE_ARN }}
        aws-region: us-east-1
    - name: CDK Diff
      run: cd infra/eval && npx cdk diff
    - name: CDK Deploy
      run: cd infra/eval && npx cdk deploy --require-approval never
```

### Docker Build + ECR Push

```yaml
build-push:
  steps:
    - uses: aws-actions/amazon-ecr-login@v2
      id: ecr-login
    - name: Build and Push
      env:
        REGISTRY: ${{ steps.ecr-login.outputs.registry }}
        REPOSITORY: eagle-frontend
        IMAGE_TAG: ${{ github.sha }}
      run: |
        docker build -t $REGISTRY/$REPOSITORY:$IMAGE_TAG .
        docker push $REGISTRY/$REPOSITORY:$IMAGE_TAG
```

### S3 Static Deploy + CloudFront Invalidation

```yaml
deploy-static:
  steps:
    - run: cd client && npm run build
    - run: |
        aws s3 sync client/out/ s3://eagle-frontend-${STAGE}/ --delete
        aws cloudfront create-invalidation --distribution-id $CF_ID --paths "/*"
```

### Environment Promotion

```
dev    → auto-deploy on push to dev/*
staging → auto-deploy on PR merge to main
prod   → manual approval (workflow_dispatch)
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

### Changelog Generation Pattern

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
    - name: Create GitHub Release
      uses: softprops/action-gh-release@v2
      with:
        tag_name: ${{ github.ref_name }}
        body_path: CHANGELOG_DELTA.md
        generate_release_notes: true
```

### Rollback Procedures

```bash
# Revert to previous release
git revert HEAD --no-edit
git push origin main

# Or: deploy a specific tag
git checkout v1.2.2
# Then trigger CD pipeline manually
```

---

## Part 6: Claude Code Action Integration

### anthropics/claude-code-action@v1

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
    context_files: |
      additional_context.json
```

### Key Features

| Feature | Description |
|---------|-------------|
| `prompt` | Main instruction to Claude |
| `claude_args` | Model, tokens, temperature |
| `structured_outputs` | Parse JSON from Claude response |
| `output_file` | Save response to file |
| `context_files` | Additional files for context |

### Workflow Patterns

| Pattern | Trigger | Action |
|---------|---------|--------|
| PR Review | `pull_request: [opened, synchronize]` | Analyze diff, post comment |
| Issue Triage | `issues: [opened, labeled]` | Classify, assign labels |
| Merge Analysis | `pull_request: [opened]` | Risk assessment, conflict detection |
| Feature Branch | Output `has_changes: true` | Create branch + PR with fixes |

---

## Part 7: Known Issues

### Action SHA Pinning

**Issue**: SHA hashes are opaque and hard to audit
**Fix**: Always include version comment: `@{sha}  # v4.1.1`

### Secrets Not Available in Fork PRs

**Issue**: `${{ secrets.* }}` are empty for pull_request from forks
**Fix**: Use `pull_request_target` trigger for workflows that need secrets (with security review of the PR changes first)

### OIDC vs Static Credentials

**Issue**: deploy.yml currently uses static IAM keys
**Fix**: Create IAM OIDC provider + deployment role, update workflow to use `role-to-assume`

### Workflow Dispatch Manual Triggers

**Issue**: `workflow_dispatch` doesn't show inputs in GitHub UI unless defined
**Fix**: Define inputs explicitly:
```yaml
on:
  workflow_dispatch:
    inputs:
      environment:
        description: 'Target environment'
        required: true
        default: 'dev'
        type: choice
        options: [dev, staging, prod]
```

### Windows-Style Line Endings

**Issue**: Scripts fail in Actions runner (ubuntu) if saved with CRLF
**Fix**: Add `.gitattributes`:
```
*.sh text eol=lf
*.yml text eol=lf
```

---

## Learnings

### patterns_that_work
- SHA-pinned actions with version comments for auditability
- Claude Code Action structured_outputs for parsing JSON from AI analysis
- Parallel CI jobs (backend, frontend, CDK) reduce pipeline time
- `pull_request_target` + security review for fork PRs needing secrets
- Squash merge keeps main branch history clean

### patterns_to_avoid
- Static IAM keys in GitHub secrets (use OIDC instead)
- Floating action version tags (use SHA pins)
- Single monolithic workflow file (split CI/CD into separate workflows)
- Force pushing to main (even with permissions)
- Committing .env files or secrets

### common_issues
- `OIDC provider not configured`: Need to create IAM OIDC provider for GitHub Actions
- `CRLF line endings`: Scripts saved on Windows need `.gitattributes` with `eol=lf`
- `Workflow not triggered`: Check trigger conditions, branch filters, and path filters
- `Secret not available`: Fork PRs don't have access to secrets; use `pull_request_target`

### tips
- Run `/experts:git:maintenance` to validate all workflow YAML files
- Use `workflow_dispatch` with typed inputs for manual deployment control
- Add `concurrency` groups to prevent parallel deploys to the same environment
- Cache npm and pip dependencies for faster CI runs
- Use `actions/upload-artifact` to preserve build outputs across jobs
