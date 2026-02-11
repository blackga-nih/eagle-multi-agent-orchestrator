---
description: "Full ACT-LEARN-REUSE workflow: plan infrastructure changes, implement them, validate, and update expertise"
allowed-tools: Read, Write, Edit, Glob, Grep, Bash
argument-hint: [infrastructure change or deployment target]
---

# AWS Expert - Plan Build Improve Workflow

> Full ACT-LEARN-REUSE workflow for AWS infrastructure development.

## Purpose

Execute the complete infrastructure development workflow:
1. **PLAN** - Design infrastructure changes using expertise
2. **VALIDATE (baseline)** - Check current AWS connectivity and resource state
3. **BUILD** - Implement the infrastructure changes
4. **VALIDATE (post)** - Verify deployment and check for issues
5. **REVIEW** - Confirm resource state and security
6. **IMPROVE** - Update expertise with learnings

## Usage

```
/experts:aws:plan_build_improve add CDK stack for storage resources
/experts:aws:plan_build_improve create DynamoDB table with GSI
/experts:aws:plan_build_improve set up IAM OIDC for GitHub Actions
```

## Variables

- `TASK`: $ARGUMENTS

## Allowed Tools

`Read`, `Write`, `Edit`, `Glob`, `Grep`, `Bash`

---

## Workflow

### Step 1: PLAN (Context Loading)

1. Read `.claude/commands/experts/aws/expertise.md`
2. Analyze the TASK — search codebase for relevant files
3. Create plan: Write to `.claude/specs/aws-{feature}.md`

### Step 2: VALIDATE (Baseline)

```bash
python -c "
import boto3, json
results = []
try:
    sts = boto3.client('sts', region_name='us-east-1')
    identity = sts.get_caller_identity()
    results.append(('AWS Identity', 'OK', f'Account: {identity[\"Account\"]}'))
except Exception as e:
    results.append(('AWS Identity', 'FAIL', str(e)[:60]))
try:
    s3 = boto3.client('s3', region_name='us-east-1')
    s3.head_bucket(Bucket='nci-documents')
    results.append(('S3 nci-documents', 'OK', 'Accessible'))
except Exception as e:
    results.append(('S3 nci-documents', 'FAIL', str(e)[:60]))
try:
    ddb = boto3.client('dynamodb', region_name='us-east-1')
    resp = ddb.describe_table(TableName='eagle')
    results.append(('DynamoDB eagle', 'OK', resp['Table']['TableStatus']))
except Exception as e:
    results.append(('DynamoDB eagle', 'FAIL', str(e)[:60]))
print('Baseline Check')
print('=' * 55)
for name, status, detail in results:
    print(f'  {name:25s} {status:6s} {detail}')
ok = sum(1 for _, s, _ in results if s == 'OK')
print(f'  Summary: {ok}/{len(results)} services OK')
"
```

**STOP if baseline fails** — Fix connectivity/credential issues first.

### Step 3: BUILD (Implement Changes)

1. Implement based on plan
2. Key rules:
   - **Import existing resources** — Never recreate `nci-documents` or `eagle`
   - **Tag everything** — `Project=eagle`, `Environment={env}`, `ManagedBy=cdk`
   - **Use OIDC** — No static IAM keys in CI/CD
   - **Set HOSTNAME=0.0.0.0** — Required for containerized Next.js

### Step 4: VALIDATE (Post-Implementation)

1. Re-run connectivity check
2. Validate specific to change type:
   - **CDK**: `npx cdk synth` then `npx cdk diff`
   - **Docker**: `docker build` then health check
   - **GitHub Actions**: YAML syntax validation
3. Run eval suite: `python server/tests/test_eagle_sdk_eval.py --model haiku --tests 16,17,18,19,20`
4. Compare to baseline — no regressions?

### Step 5: REVIEW

1. Naming conventions followed?
2. Existing resources imported (not recreated)?
3. All resources tagged?
4. No secrets hardcoded?
5. IAM policies follow least privilege?
6. OIDC used instead of static keys?
7. Rollback plan documented?

### Step 6: IMPROVE (Self-Improve)

Update `.claude/commands/experts/aws/expertise.md`:
- Add to `patterns_that_work`, `patterns_to_avoid`, `common_issues`, `tips`
- Update resource inventory if new resources exist
- Update `last_updated` timestamp

---

## Report Format

```markdown
## AWS Infrastructure Complete: {TASK}

### Summary

| Phase | Status | Notes |
|-------|--------|-------|
| Plan | DONE | .claude/specs/aws-{feature}.md |
| Baseline | PASS | {N} services OK |
| Build | DONE | {description} |
| Validation | PASS | No regressions |
| Review | PASS | Security and cost approved |
| Improve | DONE | Expertise updated |

### Resources Created/Modified

| Resource | Type | Name | Action |
|----------|------|------|--------|
| ... | ... | ... | ... |

### Learnings Captured

- Pattern: {what worked}
- Tip: {useful observation}
```

---

## Instructions

1. **Follow the workflow order** - Don't skip validation steps
2. **Stop on failures** - Fix before proceeding
3. **Import existing resources** - Never recreate S3 bucket or DynamoDB table
4. **Always run eval suite** - Tests 16-20 verify AWS connectivity
5. **Always improve** - Even failed deployments have learnings
6. **Include rollback plan** - Every deployment needs an undo path
7. **Tag everything** - Project, Environment, ManagedBy
