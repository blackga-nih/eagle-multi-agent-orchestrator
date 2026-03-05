---
description: "Query Git operations, GitHub Actions, CI/CD pipelines, or release management without making changes"
allowed-tools: Read, Glob, Grep, Bash
---

# Git/CI-CD Expert - Question Mode

> Read-only command to query Git/CI-CD knowledge without making any changes.

## Purpose

Answer questions about Git branching, GitHub Actions workflows, CI/CD pipelines, release management, and PR automation — **without making any code changes**.

## Usage

```
/experts:git:question [question]
```

## Allowed Tools

`Read`, `Glob`, `Grep`, `Bash` (read-only commands only)

## Question Categories

### Category 1: Git Operations
Questions about branches, merges, tags, conflicts.
**Resolution**: Read `expertise.md` -> Part 1

### Category 2: GitHub Actions
Questions about existing workflows, triggers, actions, secrets.
**Resolution**: Read `expertise.md` -> Part 2

### Category 3: CI Pipelines
Questions about lint, test, build, type-check pipelines.
**Resolution**: Read `expertise.md` -> Part 3

### Category 4: CD Pipelines
Questions about CDK deploy, Docker push, S3 sync, ECS update.
**Resolution**: Read `expertise.md` -> Part 4

### Category 5: Release Management
Questions about versioning, tagging, changelogs, GitHub Releases.
**Resolution**: Read `expertise.md` -> Part 5

### Category 6: Claude Code Action
Questions about AI-powered PR review, merge analysis, automation.
**Resolution**: Read `expertise.md` -> Part 6

### Category 7: Troubleshooting
Questions about workflow failures, authentication issues.
**Resolution**: Read `expertise.md` -> Part 7

---

## Workflow

1. Read `.claude/commands/experts/git/expertise.md`
2. Classify the question
3. Read relevant section(s)
4. If needed, read actual workflow files (`.github/workflows/*.yml`)
5. Provide formatted answer

## Report Format

```markdown
## Answer

{Direct answer}

## Details

{Supporting information}

## Source

- expertise.md -> {section}
- .github/workflows/{file} (if referenced)
```

## Instructions

1. **Read expertise.md first**
2. **Never modify files** - Read-only command
3. **Include YAML examples** for workflow questions
4. **Suggest next steps** - e.g., `/experts:git:plan` for implementation
