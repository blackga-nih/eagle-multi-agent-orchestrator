---
description: "Update Git/CI-CD expertise with learnings from workflow changes, pipeline runs, or troubleshooting"
allowed-tools: Read, Edit, Glob, Grep, Bash
argument-hint: [component] [outcome: success|failed|partial]
---

# Git/CI-CD Expert - Self-Improve Mode

> Update expertise.md with learnings from Git operations, workflow changes, and pipeline runs.

## Purpose

After creating workflows, debugging pipeline failures, or configuring Git operations, run self-improve to:
- Record what worked (patterns_that_work)
- Record what to avoid (patterns_to_avoid)
- Document issues encountered (common_issues)
- Add tips for future work

This is the **LEARN** step in ACT-LEARN-REUSE.

## Usage

```
/experts:git:self-improve ci-pipeline success
/experts:git:self-improve oidc-migration failed
/experts:git:self-improve release-workflow partial
```

## Variables

- `COMPONENT`: $1 (component or workflow area)
- `OUTCOME`: $2 (success | failed | partial)

## Allowed Tools

`Read`, `Edit`, `Glob`, `Grep`, `Bash`

---

## Workflow

### Phase 1: Gather Information

1. Read current `.claude/commands/experts/git/expertise.md`
2. Check recent Git changes: `git log --oneline -10`
3. List workflow files: `.github/workflows/*.yml`
4. Check GitHub Actions run status if applicable

### Phase 2: Analyze Outcome

Based on OUTCOME:
- **success**: What patterns worked? Pipeline time? Caching effective?
- **failed**: Root cause? Auth issue? Syntax error? Trigger misconfigured?
- **partial**: Which jobs passed vs failed? Blockers?

### Phase 3: Update expertise.md

Add entries to the Learnings section. Update workflow inventory if new workflows were added.

### Phase 4: Update timestamp

---

## Instructions

1. **Run after every significant Git/CI-CD change**
2. **Be specific** - Include workflow names, job names, error messages
3. **Include context** - Date, trigger, branch
4. **Don't overwrite** - Append to existing learnings
5. **Update workflow inventory** - If new workflows added, update Part 2
