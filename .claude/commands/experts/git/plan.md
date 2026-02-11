---
description: "Plan Git operations, GitHub Actions workflows, CI/CD pipelines, or release strategy"
allowed-tools: Read, Write, Glob, Grep, Bash
argument-hint: [workflow or pipeline change]
---

# Git/CI-CD Expert - Plan Mode

> Create detailed plans for Git/CI-CD changes informed by expertise.

## Purpose

Generate a plan for GitHub Actions workflows, CI/CD pipelines, branch protection, release strategy, or any Git operation change.

## Usage

```
/experts:git:plan add CI pipeline for PRs
/experts:git:plan migrate deploy.yml to OIDC auth
/experts:git:plan set up release workflow with semantic versioning
/experts:git:plan add eval suite to CI pipeline
```

## Variables

- `TASK`: $ARGUMENTS

## Allowed Tools

`Read`, `Write`, `Glob`, `Grep`, `Bash`

---

## Workflow

### Phase 1: Load Context

1. Read `.claude/commands/experts/git/expertise.md`
2. Read existing workflows: `.github/workflows/*.yml`
3. Understand: What pipeline? What trigger? What environment?

### Phase 2: Analyze Current State

1. List existing workflows and their triggers
2. Check branch protection rules
3. Identify secrets and authentication method
4. Check for potential conflicts with existing workflows

### Phase 3: Generate Plan

Write plan to `.claude/specs/git-{feature}.md` with:
- Overview of the pipeline change
- Trigger configuration
- Job dependency graph
- Authentication method (OIDC recommended)
- Required secrets/variables
- Caching strategy
- Verification steps

### Phase 4: Report

Present plan summary to user.

---

## Plan Templates

### CI Pipeline for PRs
1. Backend checks (syntax, lint, type-check)
2. Frontend checks (build, lint, type-check)
3. CDK synth check
4. All run in parallel on PR events

### OIDC Migration
1. Create IAM OIDC provider
2. Create deployment role with trust policy
3. Update workflow to use `role-to-assume`
4. Remove static key secrets

### Release Workflow
1. Trigger on tag push matching `v*`
2. Generate changelog from commit history
3. Create GitHub Release with notes
4. Trigger CD pipeline for tagged version

---

## Output Location

Plans are saved to: `.claude/specs/git-{feature}.md`
