---
description: "Full ACT-LEARN-REUSE workflow: plan Git/CI-CD changes, implement them, validate, and update expertise"
allowed-tools: Read, Write, Edit, Glob, Grep, Bash
argument-hint: [workflow or pipeline change]
---

# Git/CI-CD Expert - Plan Build Improve Workflow

> Full ACT-LEARN-REUSE workflow for Git/CI-CD development.

## Purpose

Execute the complete Git/CI-CD development workflow:
1. **PLAN** - Design workflow changes using expertise
2. **VALIDATE (baseline)** - Check existing workflows compile and function
3. **BUILD** - Implement the workflow changes
4. **VALIDATE (post)** - Verify workflow syntax and logic
5. **REVIEW** - Confirm security and best practices
6. **IMPROVE** - Update expertise with learnings

## Usage

```
/experts:git:plan_build_improve add CI pipeline for PRs
/experts:git:plan_build_improve migrate to OIDC authentication
/experts:git:plan_build_improve add release workflow
```

## Variables

- `TASK`: $ARGUMENTS

## Allowed Tools

`Read`, `Write`, `Edit`, `Glob`, `Grep`, `Bash`

---

## Workflow

### Step 1: PLAN (Context Loading)

1. Read `.claude/commands/experts/git/expertise.md`
2. Read existing workflows: `.github/workflows/*.yml`
3. Analyze the TASK and create plan

### Step 2: VALIDATE (Baseline)

```bash
# Check existing workflow syntax
python -c "
import yaml, glob
files = glob.glob('.github/workflows/*.yml')
for f in files:
    try:
        with open(f) as fh:
            yaml.safe_load(fh)
        print(f'  {f}: OK')
    except Exception as e:
        print(f'  {f}: FAIL ({e})')
"
```

**STOP if baseline fails** — Fix existing workflow issues first.

### Step 3: BUILD (Implement Changes)

1. Implement workflow changes based on plan
2. Key rules:
   - **SHA-pin actions** with version comments
   - **Use OIDC** over static keys where possible
   - **Cache dependencies** (npm, pip)
   - **Parallel CI jobs** for independent checks
   - **Concurrency groups** to prevent parallel deploys

### Step 4: VALIDATE (Post-Implementation)

```bash
# Validate all workflow YAML
python -c "
import yaml, glob
files = glob.glob('.github/workflows/*.yml')
print(f'Validating {len(files)} workflow files...')
for f in files:
    try:
        with open(f) as fh:
            data = yaml.safe_load(fh)
        assert 'on' in data, 'Missing trigger'
        assert 'jobs' in data, 'Missing jobs'
        print(f'  {f}: OK ({len(data[\"jobs\"])} jobs)')
    except Exception as e:
        print(f'  {f}: FAIL ({e})')
"
```

### Step 5: REVIEW

1. Actions SHA-pinned with version comments?
2. OIDC preferred over static keys?
3. No secrets hardcoded in workflow files?
4. Concurrency groups configured for deploy jobs?
5. Caching configured for dependencies?
6. Path filters appropriate (not triggering on unrelated changes)?

### Step 6: IMPROVE (Self-Improve)

Update `.claude/commands/experts/git/expertise.md`:
- Add to learnings sections
- Update workflow inventory if new workflows added
- Update `last_updated` timestamp

---

## Report Format

```markdown
## Git/CI-CD Complete: {TASK}

### Summary

| Phase | Status | Notes |
|-------|--------|-------|
| Plan | DONE | .claude/specs/git-{feature}.md |
| Baseline | PASS | {N} workflows valid |
| Build | DONE | {description} |
| Validation | PASS | All YAML valid |
| Review | PASS | Security best practices followed |
| Improve | DONE | Expertise updated |

### Workflows Created/Modified

| File | Action | Jobs | Triggers |
|------|--------|------|----------|
| ... | ... | ... | ... |

### Learnings Captured

- Pattern: {what worked}
- Tip: {useful observation}
```

---

## Instructions

1. **Follow the workflow order** - Don't skip validation
2. **Stop on failures** - Fix before proceeding
3. **SHA-pin all actions** - With version comments
4. **Use OIDC** - No static IAM keys
5. **Always improve** - Even failed attempts have learnings
6. **Test locally** - Use `act` if available for local workflow testing
