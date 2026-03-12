# Security CI/CD Integration Plan

**Created**: 2026-03-04
**Status**: Ready for implementation
**Type**: Plan

---

## Overview

This document provides detailed instructions for integrating automated security scanning into the EAGLE repository's CI/CD pipeline. The goal is to catch security vulnerabilities and outdated dependencies **before** code is merged to `main`, not after.

---

## Current State Analysis

### What's Missing

| Component | Status | Impact |
|-----------|--------|--------|
| CodeQL Analysis | Not configured | Security vulnerabilities discovered post-merge |
| Dependabot | Not configured | No automated dependency security updates |
| Branch Protection | No required checks | PRs can merge without validation |

### Languages Requiring Analysis

| Language | Location | CodeQL Support |
|----------|----------|----------------|
| Python | `server/app/`, `server/tests/`, `scripts/` | Full support |
| TypeScript | `client/`, `infrastructure/cdk-eagle/` | Full support |
| JavaScript | Package configs | Full support |

---

## Part 1: CodeQL Security Analysis Workflow

### Purpose

CodeQL performs Static Application Security Testing (SAST) by analyzing source code for:
- SQL injection vulnerabilities
- Cross-site scripting (XSS)
- Insecure randomness
- Clear-text credential storage
- Path traversal
- Command injection
- Information exposure through exceptions
- And 100+ other security rules

### Workflow File

**File**: `.github/workflows/codeql-analysis.yml`

```yaml
# =============================================================================
# CodeQL Security Analysis
# =============================================================================
# Runs on:
#   - Every pull request to main (blocks merge if issues found)
#   - Every push to main (catches direct commits)
#   - Weekly schedule (catches newly discovered vulnerability patterns)
#
# Languages analyzed:
#   - Python (server/, scripts/)
#   - JavaScript/TypeScript (client/, infrastructure/)
# =============================================================================

name: CodeQL Security Analysis

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  schedule:
    # Run weekly on Monday at 6:00 AM UTC
    # This catches vulnerabilities from newly updated CodeQL rules
    - cron: '0 6 * * 1'

# Minimum permissions required for CodeQL
permissions:
  contents: read
  security-events: write
  actions: read  # Required for private repos with Actions

jobs:
  analyze:
    name: Analyze (${{ matrix.language }})
    runs-on: ubuntu-latest
    timeout-minutes: 30

    strategy:
      fail-fast: false
      matrix:
        language: [python, javascript-typescript]
        include:
          - language: python
            build-mode: none
            # Python doesn't require compilation
          - language: javascript-typescript
            build-mode: none
            # TypeScript is analyzed from source, no build needed

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Initialize CodeQL
        uses: github/codeql-action/init@v3
        with:
          languages: ${{ matrix.language }}
          build-mode: ${{ matrix.build-mode }}
          # Use extended query suite for more thorough analysis
          queries: security-extended

      # For compiled languages, build steps would go here
      # Python and TypeScript don't require this

      - name: Perform CodeQL Analysis
        uses: github/codeql-action/analyze@v3
        with:
          category: "/language:${{ matrix.language }}"
          # Upload results to GitHub Security tab
          upload: true
```

### How It Works

1. **On Pull Request**: CodeQL runs and reports findings as PR checks
2. **Findings block merge**: If security issues are found, the PR cannot be merged (when branch protection is enabled)
3. **Results visible**: Findings appear in the Security tab and as PR annotations
4. **Weekly scan**: Catches issues from updated CodeQL rules

### Expected Alerts This Would Catch

Based on the 17 alerts fixed in this branch:

| Alert Type | CodeQL Rule | Files Affected |
|------------|-------------|----------------|
| Insecure randomness | `js/insecure-randomness` | `client/hooks/*.ts` |
| Clear-text logging | `py/clear-text-logging-sensitive-data` | `scripts/*.py`, `server/tests/*.py` |
| Clear-text storage | `py/clear-text-storage-sensitive-data` | `deployment/scripts/*.py` |
| Stack trace exposure | `py/stack-trace-exposure` | `server/app/main.py` |
| Untrusted CDN | `js/functionality-from-untrusted-source` | `eagle-plugin/eval/index.html` |
| Missing permissions | `actions/missing-workflow-permissions` | `.github/workflows/*.yml` |

---

## Part 2: Dependabot Configuration

### Purpose

Dependabot automatically:
- Monitors dependencies for known vulnerabilities (CVEs)
- Creates PRs to update vulnerable packages
- Keeps dependencies current with security patches

### Configuration File

**File**: `.github/dependabot.yml`

```yaml
# =============================================================================
# Dependabot Configuration
# =============================================================================
# Monitors and updates dependencies across:
#   - Python (server backend)
#   - npm (frontend, infrastructure CDK)
#   - GitHub Actions (workflow security)
#
# PRs are created weekly with security patches and version updates
# =============================================================================

version: 2

updates:
  # ─────────────────────────────────────────────────────────────────────────
  # Python Backend (server/)
  # ─────────────────────────────────────────────────────────────────────────
  - package-ecosystem: pip
    directory: /server
    schedule:
      interval: weekly
      day: monday
      time: "06:00"
      timezone: America/New_York
    open-pull-requests-limit: 5
    labels:
      - dependencies
      - python
      - security
    commit-message:
      prefix: "deps(python)"
    groups:
      python-minor:
        patterns:
          - "*"
        update-types:
          - minor
          - patch

  # ─────────────────────────────────────────────────────────────────────────
  # Frontend (client/)
  # ─────────────────────────────────────────────────────────────────────────
  - package-ecosystem: npm
    directory: /client
    schedule:
      interval: weekly
      day: monday
      time: "06:00"
      timezone: America/New_York
    open-pull-requests-limit: 5
    labels:
      - dependencies
      - frontend
      - security
    commit-message:
      prefix: "deps(frontend)"
    ignore:
      - dependency-name: "next"
        update-types: ["version-update:semver-major"]
      - dependency-name: "react"
        update-types: ["version-update:semver-major"]
    groups:
      npm-minor:
        patterns:
          - "*"
        update-types:
          - minor
          - patch

  # ─────────────────────────────────────────────────────────────────────────
  # Infrastructure CDK (infrastructure/cdk-eagle/)
  # ─────────────────────────────────────────────────────────────────────────
  - package-ecosystem: npm
    directory: /infrastructure/cdk-eagle
    schedule:
      interval: weekly
      day: monday
      time: "06:00"
      timezone: America/New_York
    open-pull-requests-limit: 3
    labels:
      - dependencies
      - infrastructure
      - cdk
    commit-message:
      prefix: "deps(cdk)"
    groups:
      aws-cdk:
        patterns:
          - "aws-cdk*"
          - "@aws-cdk/*"
        update-types:
          - minor
          - patch

  # ─────────────────────────────────────────────────────────────────────────
  # Eval Infrastructure (infrastructure/eval/)
  # ─────────────────────────────────────────────────────────────────────────
  - package-ecosystem: npm
    directory: /infrastructure/eval
    schedule:
      interval: weekly
    open-pull-requests-limit: 2
    labels:
      - dependencies
      - infrastructure
    commit-message:
      prefix: "deps(eval)"

  # ─────────────────────────────────────────────────────────────────────────
  # GitHub Actions Workflows
  # ─────────────────────────────────────────────────────────────────────────
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly
    open-pull-requests-limit: 3
    labels:
      - dependencies
      - ci
      - github-actions
    commit-message:
      prefix: "ci(actions)"
```

### What Dependabot Will Do

1. **Security alerts**: Immediate PRs for vulnerable dependencies
2. **Weekly updates**: Batched PRs for minor/patch updates
3. **Grouped updates**: Similar packages updated together
4. **Auto-labels**: PRs labeled for easy filtering

---

## Part 3: Branch Protection Rules

### Purpose

Require CodeQL checks to pass before PRs can be merged.

### Setup Instructions

1. Go to **GitHub Repository → Settings → Branches**
2. Click **Add branch protection rule**
3. Configure:

| Setting | Value |
|---------|-------|
| Branch name pattern | `main` |
| Require a pull request before merging | ✅ Enabled |
| Require status checks to pass | ✅ Enabled |
| Status checks required | `Analyze (python)`, `Analyze (javascript-typescript)` |
| Require branches to be up to date | ✅ Enabled |
| Do not allow bypassing | ✅ Enabled (for admins too) |

### Result

- PRs cannot be merged until CodeQL analysis passes
- Direct pushes to `main` are blocked
- Security issues must be fixed before merge

---

## Part 4: Viewing Results

### GitHub Security Tab

After CodeQL is configured:
1. Go to **Repository → Security → Code scanning alerts**
2. View all detected vulnerabilities
3. Filter by severity, rule, or file

### PR Annotations

CodeQL findings appear as:
- ❌ Failing check (blocks merge)
- Inline annotations on affected code
- Detailed remediation suggestions

### Dependabot PRs

Automated PRs appear with:
- Vulnerability details in PR description
- Compatibility score
- Release notes from upstream

---

## Implementation Checklist

- [ ] Create `.github/workflows/codeql-analysis.yml`
- [ ] Create `.github/dependabot.yml`
- [ ] Push changes to feature branch
- [ ] Open PR and verify CodeQL runs
- [ ] Merge to main
- [ ] Configure branch protection rules in GitHub settings
- [ ] Verify Dependabot creates PRs within 24 hours

---

## Validation Commands

```bash
# Verify workflow file syntax
cat .github/workflows/codeql-analysis.yml | python3 -c "import yaml, sys; yaml.safe_load(sys.stdin)"

# Verify dependabot config syntax
cat .github/dependabot.yml | python3 -c "import yaml, sys; yaml.safe_load(sys.stdin)"
```

---

## References

- [GitHub CodeQL Documentation](https://docs.github.com/en/code-security/code-scanning/introduction-to-code-scanning/about-code-scanning-with-codeql)
- [Dependabot Configuration](https://docs.github.com/en/code-security/dependabot/dependabot-version-updates/configuration-options-for-the-dependabot.yml-file)
- [Branch Protection Rules](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)
