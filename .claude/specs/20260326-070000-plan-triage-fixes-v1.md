# Plan: Triage Fixes — 2026-03-26

## Task Description
Fix 3 issues identified by /triage diagnostic scan across DynamoDB feedback, CloudWatch logs, and Langfuse traces.

## Objective
Resolve all P0 and P1 issues to improve user experience and system reliability. Address P2 issues to improve observability and admin functionality.

## Problem Statement
The CI deploy role lacks CloudWatch Logs Insights permissions, blocking automated triage analysis. Admin dashboard pages fail due to missing tenant ID in Cognito tokens. Langfuse streaming spans are not properly closed during test/eval runs, polluting trace data with 44% incomplete entries.

## Relevant Files
- `infrastructure/cdk-eagle/lib/cicd-stack.ts` — CI/CD role IAM permissions (add CloudWatch Logs Insights)
- `server/app/auth.py` — Cognito JWT verification, tenant_id extraction (admin auth fix)
- `server/app/strands_agentic_service.py` — Langfuse span lifecycle in sdk_query_streaming() (lines 3968-4346)
- `infrastructure/cdk-eagle/lib/core-stack.ts` — Cognito user pool custom attributes configuration

## Implementation Phases

### Phase 1: P1 Fix — CI IAM CloudWatch Permissions

**File**: `infrastructure/cdk-eagle/lib/cicd-stack.ts`

The eagle-deploy-role-dev IAM role is missing these CloudWatch Logs actions:
- logs:StartQuery
- logs:StopQuery
- logs:GetQueryResults
- logs:DescribeLogGroups

These are needed for CloudWatch Logs Insights queries used by the automated triage pipeline.

#### Steps:
1. Open infrastructure/cdk-eagle/lib/cicd-stack.ts
2. Find the IAM policy attached to the deploy role
3. Add a policy statement granting logs:StartQuery, logs:StopQuery, logs:GetQueryResults, logs:DescribeLogGroups on arn:aws:logs:us-east-1:*:log-group:/eagle/*
4. Run cd infrastructure/cdk-eagle && npm run build && npx cdk synth --quiet to validate

### Phase 2: P2 Fix — Admin Auth Tenant ID

**File**: `server/app/auth.py` (lines 47-55)

The admin dashboard calls /api/admin/traces and /api/admin/costs with a Cognito token that lacks the custom:tenant_id attribute. The verify_token() method raises 403 when this is missing.

#### Options:
**Option A (Recommended)**: Fall back to a default tenant for admin users. If custom:tenant_id is missing but the user is in an admin group (cognito:groups contains *-admins), infer tenant from the group name prefix.

**Option B**: Ensure all Cognito users have custom:tenant_id set. Check infrastructure/cdk-eagle/lib/core-stack.ts for the Cognito user pool custom attribute definition and verify the attribute is required and has a default.

#### Steps:
1. In server/app/auth.py:54, before raising the 403, check if the user is an admin and infer tenant_id from their group membership
2. Add fallback: tenant_id = tenant_id or _infer_tenant_from_groups(user_groups)
3. Add unit test for the fallback path
4. Run ruff check app/ and python -m pytest tests/ -v

### Phase 3: P2 Fix — Langfuse Span Completion

**File**: `server/app/strands_agentic_service.py` (lines 3968-4346)

The sdk_query_streaming() async generator opens a Langfuse span at line 3976 but only closes it at lines 4336-4346 (after all yields). If the consumer disconnects or the generator is garbage-collected without full consumption, the span is never closed.

#### Steps:
1. Wrap the Langfuse finalization in a try/finally that covers the entire generator body, not just the yield loop
2. Alternatively, use contextlib.aclosing() or register cleanup via asyncio to ensure __aexit__ is called
3. Consider moving the Langfuse span close into the existing finally block (around line 4280) rather than after all yields
4. Verify with a test that simulates early disconnect
5. Run python -m pytest tests/ -v

## Step by Step Tasks

### 1. Add CloudWatch Logs Insights Permissions to CI Role
- **File**: infrastructure/cdk-eagle/lib/cicd-stack.ts
- **Problem**: eagle-deploy-role-dev lacks logs:StartQuery, logs:StopQuery, logs:GetQueryResults, logs:DescribeLogGroups
- **Fix**: Add IAM policy statement for CloudWatch Logs Insights actions on /eagle/* log groups
- **Validation**: cd infrastructure/cdk-eagle && npm run build && npx cdk synth --quiet

### 2. Fix Admin Auth Tenant ID Fallback
- **File**: server/app/auth.py
- **Problem**: Admin users without custom:tenant_id in JWT get 403 on admin pages
- **Fix**: Infer tenant_id from admin group name when custom attribute is missing
- **Validation**: ruff check app/ && python -m pytest tests/ -v

### 3. Ensure Langfuse Spans Close on Generator Abort
- **File**: server/app/strands_agentic_service.py
- **Problem**: Langfuse _lf_ctx.__exit__() at line 4344 is unreachable if generator is not fully consumed
- **Fix**: Move Langfuse cleanup into the existing finally block or use try/finally wrapping the full generator
- **Validation**: python -m pytest tests/ -v

### 4. Validate All Fixes
- ruff check app/
- npx tsc --noEmit
- python -m pytest tests/ -v
- Re-run /triage light to confirm issues resolved

## Acceptance Criteria
- All P0 issues resolved (none identified)
- All P1 issues resolved: CI role can run CloudWatch Logs Insights queries
- P2 issues resolved or documented with rationale for deferral
- No new errors introduced (re-triage shows improvement)
- Validation commands pass

## Validation Commands
- ruff check app/ — Python lint
- npx tsc --noEmit — TypeScript check
- python -m pytest tests/ -v — Unit tests
- cd infrastructure/cdk-eagle && npm run build && npx cdk synth --quiet — CDK compile
- /triage light — Re-triage to confirm improvement

## Notes
- Generated by /triage on 2026-03-26
- Triage report: docs/development/20260326-070000-report-triage-dev-v2.md
- Cross-referenced 0 feedback items, 2 CloudWatch errors, 22 Langfuse error traces
- Dev environment is low-traffic with 3 unique users in 24h window
- No P0 (critical) issues found — system is stable
