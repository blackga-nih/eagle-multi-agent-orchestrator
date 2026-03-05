---
description: "Scaffold new GitHub Actions workflows — CI, CD, PR checks, release"
allowed-tools: Read, Write, Edit, Glob, Grep, Bash
argument-hint: [ci | cd | pr | release]
---

# Git/CI-CD Expert - Workflow Scaffold Command

> Scaffold new GitHub Actions workflow files from templates.

## Purpose

Generate GitHub Actions workflow boilerplate for common pipeline patterns, pre-configured with EAGLE project conventions.

## Usage

```
/experts:git:workflow-scaffold ci       → Lint + test + build pipeline for PRs
/experts:git:workflow-scaffold cd       → CDK deploy + S3 sync pipeline for main
/experts:git:workflow-scaffold pr       → PR checks + Claude Code review
/experts:git:workflow-scaffold release  → Tag-based release + changelog + GitHub Release
```

## Variables

- `WORKFLOW_TYPE`: $ARGUMENTS

## Allowed Tools

`Read`, `Write`, `Edit`, `Glob`, `Grep`, `Bash`

---

## Workflow

### Phase 1: Load Context

1. Read `.claude/commands/experts/git/expertise.md` -> Parts 2-6
2. Check existing workflows: `.github/workflows/*.yml`
3. Determine filename (avoid conflicts with existing)

### Phase 2: Scaffold Workflow

Create `.github/workflows/{type}.yml` with:
- EAGLE naming conventions
- SHA-pinned actions with version comments
- Appropriate triggers
- Caching for npm/pip
- Concurrency groups for deploy workflows

### Phase 3: Validate

```bash
python -c "
import yaml
with open('.github/workflows/{file}.yml') as f:
    data = yaml.safe_load(f)
assert 'on' in data and 'jobs' in data
print('Workflow YAML is valid')
"
```

---

## Scaffold Templates

### ci — Continuous Integration

```yaml
name: CI
on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11', cache: 'pip', cache-dependency-path: server/requirements.txt }
      - run: pip install -r server/requirements.txt
      - run: python -m py_compile server/app/agentic_service.py

  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20', cache: 'npm', cache-dependency-path: client/package-lock.json }
      - run: cd client && npm ci
      - run: cd client && npm run build
```

### cd — Continuous Deployment

```yaml
name: Deploy
on:
  push:
    branches: [main]
  workflow_dispatch:
    inputs:
      environment:
        description: 'Target environment'
        required: true
        default: 'dev'
        type: choice
        options: [dev, staging, prod]

concurrency:
  group: deploy-${{ github.event.inputs.environment || 'dev' }}
  cancel-in-progress: false

permissions:
  id-token: write
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: ${{ github.event.inputs.environment || 'dev' }}
    steps:
      - uses: actions/checkout@v4
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ vars.CDK_DEPLOY_ROLE_ARN }}
          aws-region: us-east-1
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - run: cd infrastructure/eval && npm ci && npx cdk deploy --require-approval never
```

### pr — PR Checks with Claude Review

```yaml
name: PR Checks
on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  ci:
    uses: ./.github/workflows/ci.yml

  claude-review:
    runs-on: ubuntu-latest
    if: github.event.pull_request.draft == false
    steps:
      - uses: actions/checkout@v4
      - uses: anthropics/claude-code-action@v1
        with:
          prompt: |
            Review this PR for code quality, security, and best practices.
            Focus on: EAGLE project conventions, AWS service usage, test coverage.
          claude_args: |
            --model claude-sonnet-4-5-20250929
            --max-tokens 4000
```

### release — Tag-Based Release

```yaml
name: Release
on:
  push:
    tags: ['v*']

permissions:
  contents: write

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - name: Generate changelog
        run: |
          PREV_TAG=$(git describe --tags --abbrev=0 HEAD~1 2>/dev/null || echo "")
          if [ -n "$PREV_TAG" ]; then
            git log ${PREV_TAG}..HEAD --oneline --no-merges > CHANGELOG_DELTA.md
          else
            git log --oneline -20 > CHANGELOG_DELTA.md
          fi
      - uses: softprops/action-gh-release@v2
        with:
          generate_release_notes: true
          body_path: CHANGELOG_DELTA.md
```

---

## Instructions

1. **Check existing workflows first** - Don't create duplicates
2. **SHA-pin actions** - Use SHA hashes with version comments
3. **Add concurrency groups** - Prevent parallel deploys
4. **Cache dependencies** - npm and pip caching
5. **Validate syntax** - Run YAML validation after scaffolding
6. **Use OIDC** - Prefer over static IAM keys for AWS auth
