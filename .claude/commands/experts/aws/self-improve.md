---
description: "Update AWS expertise with learnings from infrastructure changes, CDK deployments, or troubleshooting"
allowed-tools: Read, Edit, Glob, Grep, Bash
argument-hint: [component] [outcome: success|failed|partial]
---

# AWS Expert - Self-Improve Mode

> Update expertise.md with learnings from AWS infrastructure changes, CDK deployments, and troubleshooting.

## Purpose

After deploying CDK stacks, creating DynamoDB tables, configuring IAM policies, or troubleshooting infrastructure, run self-improve to:
- Record what worked (patterns_that_work)
- Record what to avoid (patterns_to_avoid)
- Document issues encountered (common_issues)
- Add tips for future work

This is the **LEARN** step in ACT-LEARN-REUSE.

## Usage

```
/experts:aws:self-improve cdk-eval-stack success
/experts:aws:self-improve dynamodb-gsi failed
/experts:aws:self-improve iam-oidc partial
```

## Variables

- `COMPONENT`: $1 (component or AWS service area)
- `OUTCOME`: $2 (success | failed | partial)

## Allowed Tools

`Read`, `Edit`, `Glob`, `Grep`, `Bash`

---

## Workflow

### Phase 1: Gather Information

1. Read current `.claude/commands/experts/aws/expertise.md`
2. Check recent changes: `git log --oneline -10`
3. Check AWS resource state via boto3
4. Check for new infrastructure files

### Phase 2: Analyze Outcome

Based on OUTCOME:
- **success**: What patterns worked? Any surprises? Deployment time?
- **failed**: Root cause? AWS permissions? Resource conflict? Configuration error?
- **partial**: Which components deployed vs failed? Blockers? Workarounds?

### Phase 3: Update expertise.md

Add entries to the Learnings section:
```markdown
### patterns_that_work
- {what worked} (discovered: {date}, component: {COMPONENT})

### patterns_to_avoid
- {what to avoid} (reason: {why})

### common_issues
- {issue}: {solution} (component: {COMPONENT})

### tips
- {useful tip learned}
```

Update other sections if needed:
- Part 1: If provisioning model changed
- Part 2: If new resources were created
- Part 3: If CDK stack patterns learned
- Part 4: If DynamoDB design patterns discovered
- Part 5: If IAM policy patterns learned

### Phase 4: Update timestamp

Update the `last_updated` field in the frontmatter.

---

## Instructions

1. **Run after every significant infrastructure change**
2. **Be specific** - Include AWS service names, error codes, solutions
3. **Include context** - Date, component, account/region
4. **Keep it actionable** - Learnings should help future deployments
5. **Don't overwrite** - Append to existing learnings
6. **Update resource inventory** - If new AWS resources were created, add to Part 2
