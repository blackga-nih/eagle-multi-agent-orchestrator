---
description: "Update deployment expertise with learnings from deployments, infrastructure changes, or troubleshooting"
allowed-tools: Read, Edit, Glob, Grep, Bash
argument-hint: [component] [outcome: success|failed|partial]
---

# Deployment Expert - Self-Improve Mode

> Update expertise.md with learnings from deployments, infrastructure changes, and troubleshooting sessions.

## Purpose

After deploying services, provisioning resources, or troubleshooting infrastructure issues, run self-improve to:
- Record what worked (patterns_that_work)
- Record what to avoid (patterns_to_avoid)
- Document issues encountered (common_issues)
- Add tips for future deployments

This is the **LEARN** step in ACT-LEARN-REUSE.

## Usage

```
/experts:deployment:self-improve cdk-stack-creation success
/experts:deployment:self-improve ecs-deployment failed
/experts:deployment:self-improve cloudfront-setup partial
```

## Variables

- `COMPONENT`: $1 (component or infrastructure area)
- `OUTCOME`: $2 (success | failed | partial)

## Allowed Tools

`Read`, `Edit`, `Glob`, `Grep`, `Bash`

---

## Workflow

### Phase 1: Gather Information

1. Read current `.claude/commands/experts/deployment/expertise.md`
2. Check recent infrastructure changes:
   ```bash
   git log --oneline -10
   git diff HEAD~3 --stat
   ```
3. Check AWS resource state:
   ```bash
   python -c "
   import boto3, json
   sts = boto3.client('sts', region_name='us-east-1')
   identity = sts.get_caller_identity()
   print(f'Account: {identity[\"Account\"]}')
   "
   ```
4. Check for new infrastructure files:
   ```bash
   ls cdk/ 2>/dev/null
   ls Dockerfile docker-compose.yml 2>/dev/null
   ls .github/workflows/ 2>/dev/null
   ```

### Phase 2: Analyze Outcome

Based on OUTCOME:

**success**:
- What made the deployment successful?
- Any patterns worth recording?
- Were there any surprises?
- Which AWS services or CDK constructs worked well?
- What was the deployment time?

**failed**:
- What caused the failure?
- AWS permissions issue? Resource conflict? Configuration error?
- What should be avoided next time?
- What needs to happen before retry?
- Was the rollback plan effective?

**partial**:
- Which components deployed vs failed?
- What remains to be done?
- What blockers were encountered?
- Is there a workaround?

### Phase 3: Update expertise.md

#### Update `Learnings` section:

Add entries to the appropriate subsection:

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

#### Update other sections if needed:

- **Part 1** (Current Infrastructure): Update if provisioning model changed
- **Part 2** (AWS Resources): Update if new resources were created
- **Part 3** (Next.js Deployment): Update if deployment option was tested
- **Part 4** (CDK Patterns): Update if CDK stack was created
- **Part 5** (Docker Patterns): Update if Dockerfile was created
- **Part 6** (CI/CD Patterns): Update if GitHub Actions were configured
- **Part 7** (Known Issues): Add any new issues discovered

### Phase 4: Update timestamp

Update the `last_updated` field in the frontmatter.

---

## Report Format

```markdown
## Self-Improve Report: {COMPONENT}

### Outcome: {OUTCOME}

### Learnings Recorded

**Patterns that work:**
- {pattern 1}

**Patterns to avoid:**
- {pattern 1}

**Issues documented:**
- {issue 1}

**Tips added:**
- {tip 1}

### Expertise Updated

- expertise.md -> Learnings section
- expertise.md -> {other sections updated}
- expertise.md -> last_updated timestamp
```

---

## Instructions

1. **Run after every significant deployment or infrastructure change** - Even failed deployments have learnings
2. **Be specific** - Record concrete patterns with AWS service names, error codes, and solutions
3. **Include context** - Date, component, account/region, and circumstances
4. **Keep it actionable** - Learnings should help future deployments
5. **Don't overwrite** - Append to existing learnings, don't replace
6. **Update resource inventory** - If new AWS resources were created, add to Part 2

---

## Data Sources

| Source | Location | Content |
|--------|----------|---------|
| AWS Console | Browser | Resource state and configuration |
| CloudWatch | `/eagle/test-runs` | Eval suite health after deployment |
| Git history | `git log` | Recent changes and context |
| CDK output | `cdk deploy` stdout | Stack outputs and resource ARNs |
| Docker logs | `docker logs` | Container runtime output |
| GitHub Actions | `.github/workflows/` run logs | CI/CD pipeline results |
