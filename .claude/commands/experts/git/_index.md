---
type: expert-file
file-type: index
domain: git
tags: [expert, git, github, actions, cicd, pipeline, release]
---

# Git/CI-CD Expert

> Git operations, GitHub Actions workflows, CI/CD pipeline design, branch strategy, release management, and PR automation.

## Domain Scope

This expert covers:
- **Git Operations** - Branch strategy, merge policies, conflict resolution, tagging
- **GitHub Actions** - Workflow authoring, triggers, OIDC auth, action pinning
- **CI Pipelines** - Lint, test, build, type-check for Python and Next.js
- **CD Pipelines** - CDK deploy, Docker push, S3 sync, ECS update
- **Release Management** - Semantic versioning, changelogs, GitHub Releases
- **PR Automation** - Claude Code Action integration, merge analysis, review bots
- **Repository Configuration** - Branch protection, secrets, environments

## Current State

| Component | Status | Details |
|-----------|--------|---------|
| Branch strategy | Active | `main`, `dev/*`, `feat/*` branches |
| GitHub Actions | Partial | `deploy.yml` (static keys), `claude-merge-analysis.yml` |
| CI pipeline | Not configured | No lint/test/build checks on PR |
| CD pipeline | Partial | CDK deploy via static IAM keys |
| Release tagging | Not configured | No semantic versioning |
| Branch protection | Unknown | Not yet configured |
| Claude Code Action | Configured | PR analysis workflow exists |

## Available Commands

| Command | Purpose |
|---------|---------|
| `/experts:git:question` | Answer Git/CI-CD questions without coding |
| `/experts:git:plan` | Plan Git operations, workflows, or pipeline changes |
| `/experts:git:self-improve` | Update expertise after Git/CI-CD changes |
| `/experts:git:plan_build_improve` | Full ACT-LEARN-REUSE workflow for Git/CI-CD |
| `/experts:git:maintenance` | Validate workflow syntax, check Actions status |
| `/experts:git:workflow-scaffold` | Scaffold new GitHub Actions workflows |

## Key Files

| File | Purpose |
|------|---------|
| `expertise.md` | Complete mental model for Git/CI-CD domain |
| `question.md` | Query command for read-only questions |
| `plan.md` | Planning command for pipeline changes |
| `self-improve.md` | Expertise update command |
| `plan_build_improve.md` | Full workflow command |
| `maintenance.md` | Workflow validation and Actions status |
| `workflow-scaffold.md` | GitHub Actions workflow scaffolding |

## Architecture

```
Git/CI-CD Ecosystem
  |
  |-- Repository
  |     |-- main (protected, production)
  |     |-- dev/* (development branches)
  |     |-- feat/* (feature branches)
  |
  |-- GitHub Actions
  |     |-- .github/workflows/deploy.yml
  |     |     |-- Trigger: push to main
  |     |     |-- CDK deploy + frontend setup
  |     |
  |     |-- .github/workflows/claude-merge-analysis.yml
  |           |-- Trigger: PR events, issue comments
  |           |-- Claude-powered code review + feature branch creation
  |
  |-- Secrets
  |     |-- AWS_ACCESS_KEY_ID (static, should migrate to OIDC)
  |     |-- AWS_SECRET_ACCESS_KEY
  |     |-- ANTHROPIC_API_KEY
  |     |-- COGNITO_*, BEDROCK_*, SESSIONS_TABLE, USAGE_TABLE
  |
  |-- Future
        |-- CI pipeline (lint + test + build on PR)
        |-- CD pipeline (OIDC auth + CDK deploy)
        |-- Release workflow (tag + changelog + GitHub Release)
```

## Cross-References

| Related Expert | When to Use |
|---------------|-------------|
| aws | When pipelines need to deploy CDK stacks or AWS resources |
| eval | When CI pipeline should run eval suite tests |
| frontend | When pipeline builds/deploys the Next.js frontend |
| backend | When pipeline deploys the Python backend |
| cloudwatch | When CI/CD results should emit telemetry |

## ACT-LEARN-REUSE Pattern

```
ACT    ->  Create workflows, configure pipelines, set up branch protection
LEARN  ->  Update expertise.md with workflow patterns, issues, and tips
REUSE  ->  Apply patterns to future workflows and pipeline configurations
```
