# Plan: Triage Fixes — 2026-03-29

## Task Description

Fix 4 issues identified by /triage diagnostic scan (QA environment) across DynamoDB feedback, CloudWatch logs, and Langfuse traces.

## Objective

Resolve P2 infrastructure/observability gaps to enable meaningful QA validation and ensure the QA environment is actively monitored.

## Problem Statement

The QA environment is deployed but not actively tested or monitored. The backend is healthy, but the frontend has been idle for 2+ days, no user sessions are being recorded, Langfuse observability is not configured for QA, and the deploy role lacks CloudWatch Log Insights permissions. These gaps mean regressions could ship to production undetected.

## Relevant Files

- `infrastructure/cdk-eagle/lib/ci-cd-stack.ts` — Deploy role IAM permissions (add `logs:StartQuery`, `logs:GetQueryResults`)
- `server/.env` — Missing `LANGFUSE_QA_*` environment variables
- `infrastructure/cdk-eagle/lib/compute-stack.ts` — ECS task definitions / frontend-qa service configuration

## Implementation Phases

### Phase 1: P2 Fixes (Medium — Observability & Coverage)

#### 1. Add CloudWatch Log Insights permissions to deploy role

- **File**: `infrastructure/cdk-eagle/lib/ci-cd-stack.ts`
- **Problem**: The `eagle-deploy-role-dev` IAM role lacks `logs:StartQuery` and `logs:GetQueryResults` permissions, causing `AccessDeniedException` when triage automation runs CloudWatch Log Insights queries.
- **Fix**: Add a policy statement granting `logs:StartQuery`, `logs:GetQueryResults`, `logs:StopQuery`, and `logs:GetLogEvents` on the `/eagle/*` log group ARNs.
- **Validation**: Re-run `/triage light --env=qa` and confirm Log Insights queries succeed.

#### 2. Configure Langfuse QA environment variables

- **File**: `server/.env` (local) and ECS task definition environment (infra)
- **Problem**: No `LANGFUSE_QA_PUBLIC_KEY`, `LANGFUSE_QA_SECRET_KEY`, or `LANGFUSE_QA_PROJECT_ID` are set. QA traces either go to the dev project or are lost.
- **Fix**: Create a separate Langfuse project for QA (or use the same project with QA-prefixed tags), then add the corresponding `LANGFUSE_QA_*` env vars to both `.env` and the ECS task definition.
- **Validation**: Run a test conversation in QA and confirm traces appear in Langfuse under the QA project.

#### 3. Investigate frontend-qa idle state

- **File**: `infrastructure/cdk-eagle/lib/compute-stack.ts`
- **Problem**: The frontend-qa ECS service's last log was 2 days ago. Either the service is stopped, the task is failing silently, or no traffic is reaching it.
- **Fix**: Check ECS service desired count and task status. If the service is running but idle, verify the ALB target group health and DNS routing. If stopped, restart.
- **Validation**: `aws ecs describe-services --cluster eagle-qa --services eagle-frontend-qa` shows `runningCount >= 1` and healthy targets.

### Phase 2: P3 Improvements (Low)

#### 4. Document QA testing cadence

- **Problem**: Zero user activity in QA suggests no regular testing cadence exists.
- **Fix**: Establish a lightweight QA smoke test that runs on deploy (e.g., E2E judge pipeline against QA ALB URL).
- **Validation**: Automated smoke test runs on each QA deployment.

## Step by Step Tasks

### 1. Add Log Insights IAM permissions
- **File**: `infrastructure/cdk-eagle/lib/ci-cd-stack.ts`
- **Problem**: Deploy role `AccessDeniedException` on `logs:StartQuery`
- **Fix**: Add IAM policy statement:
  ```typescript
  deployRole.addToPolicy(new iam.PolicyStatement({
    actions: ['logs:StartQuery', 'logs:GetQueryResults', 'logs:StopQuery'],
    resources: ['arn:aws:logs:us-east-1:*:log-group:/eagle/*'],
  }));
  ```
- **Validation**: `aws logs start-query --log-group-name /eagle/ecs/backend-qa ...` succeeds

### 2. Add Langfuse QA credentials
- **File**: `server/.env`, ECS task definition
- **Problem**: Missing `LANGFUSE_QA_*` env vars
- **Fix**: Add `LANGFUSE_QA_PUBLIC_KEY`, `LANGFUSE_QA_SECRET_KEY`, `LANGFUSE_QA_PROJECT_ID` to server config
- **Validation**: QA traces visible in Langfuse dashboard

### 3. Verify frontend-qa ECS service
- **File**: `infrastructure/cdk-eagle/lib/compute-stack.ts`
- **Problem**: Frontend idle for 2+ days
- **Fix**: Check and restart ECS service if needed; verify ALB routing
- **Validation**: Health check logs resume in `/eagle/ecs/frontend-qa`

### 4. Validate All Fixes
- `ruff check app/`
- `npx tsc --noEmit`
- `python -m pytest tests/ -v`
- Re-run `/triage light --env=qa` to confirm issues resolved

## Acceptance Criteria

- All P2 issues resolved
- CloudWatch Log Insights queries work from CI deploy role
- Langfuse QA traces are captured separately from dev
- Frontend-qa ECS service is active and logging
- No new errors introduced (re-triage shows improvement)
- Validation commands pass

## Validation Commands

- `ruff check app/` — Python lint
- `npx tsc --noEmit` — TypeScript check
- `python -m pytest tests/ -v` — Unit tests
- `/triage light --env=qa` — Re-triage to confirm improvement

## Notes

- Generated by /triage on 2026-03-29
- Triage report: `docs/development/20260329-091000-report-triage-qa-v1.md`
- Cross-referenced 0 feedback items, 0 CloudWatch errors, 0 Langfuse traces
- Primary concern is lack of QA activity rather than active failures
