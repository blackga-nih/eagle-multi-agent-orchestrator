# Plan: Triage Fixes — 2026-03-31 (QA)

## Task Description
Fix 2 P1 issues and 2 P2 issues identified by /triage diagnostic scan across DynamoDB feedback, CloudWatch logs, and Langfuse traces for the QA environment.

## Objective
Resolve all P0 and P1 issues to improve QA environment reliability and observability.

## Problem Statement
The QA environment has two blocking infrastructure issues: (1) AWS SSO token expiration causes all Bedrock agent invocations to fail with no automatic recovery, and (2) the OTLP span exporter receives 401 Unauthorized from Langfuse, causing complete observability data loss. Additionally, QA lacks dedicated Langfuse keys, meaning trace data is not isolated from dev.

## Relevant Files
- `server/app/strands_agentic_service.py` — OTel OTLP exporter setup (lines 76-146), Bedrock boto3 client initialization
- `server/app/bedrock_service.py` — Bedrock client with boto3 credential chain (lines 11-31)
- `server/app/config.py` — Centralized config including Langfuse and Bedrock settings
- `server/app/telemetry/langfuse_client.py` — SSO error pattern detection (line 175-178)
- `server/.env` — Environment variables (QA Langfuse keys empty)
- `infrastructure/cdk-eagle/lib/` — ECS task IAM role definitions

## Implementation Phases

### Phase 1: P1 Fixes (Critical)

#### 1. Fix SSO Token Expiration on ECS (Bedrock access)
The ECS QA backend task is using SSO-based credentials instead of IAM task role credentials for Bedrock API calls. When the SSO token expires, all agent invocations fail. ECS tasks should use the task execution role's temporary credentials (automatically rotated), not SSO.

#### 2. Fix OTLP Exporter 401 Unauthorized
The OTLP span exporter in `_ensure_langfuse_exporter()` is sending Basic auth credentials that Langfuse rejects with 401. This could be caused by: (a) QA environment using dev Langfuse keys against a QA-specific Langfuse project, (b) keys rotated on Langfuse side but not updated in ECS task environment, or (c) the base64 encoding of credentials is malformed.

### Phase 2: P2 Improvements (Medium)

#### 3. Configure QA-Specific Langfuse Keys
Add `LANGFUSE_QA_PUBLIC_KEY`, `LANGFUSE_QA_SECRET_KEY`, and `LANGFUSE_QA_PROJECT_ID` to the QA ECS task definition so QA traces are isolated from dev.

#### 4. Reduce Orphan Trace Noise
Investigate the high orphan trace ratio (74%) and consider adding trace completion guards or adjusting the orphan filter to also cover `eagle-query-*` patterns.

## Step by Step Tasks

### 1. Verify ECS QA Task Role Has Bedrock Permissions
- **File**: `infrastructure/cdk-eagle/lib/compute-stack.ts` (or equivalent CDK stack defining ECS task role)
- **Problem**: ECS task may not have an IAM task role with `bedrock:InvokeModel` and `bedrock:InvokeModelWithResponseStream` permissions, causing the application to fall back to SSO credentials from a developer's `~/.aws/config` baked into the container or mounted via ECS exec.
- **Fix**: Ensure the ECS task role in the CDK stack includes a policy with:
  ```json
  {
    "Effect": "Allow",
    "Action": [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream"
    ],
    "Resource": "arn:aws:bedrock:us-east-1::foundation-model/*"
  }
  ```
  Verify the QA ECS task definition references this role. Confirm no `AWS_PROFILE` or SSO config is injected into the container environment.
- **Validation**: Deploy to QA, invoke an agent query, confirm no SSO token errors in Langfuse. Run: `aws ecs describe-task-definition --task-definition eagle-backend-qa | jq '.taskDefinition.taskRoleArn'`

### 2. Fix OTLP Exporter Credentials for QA
- **File**: `server/app/strands_agentic_service.py` (lines 89-118)
- **Problem**: The `_ensure_langfuse_exporter()` function reads `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` to construct Basic auth for the OTLP exporter. In QA, these may point to the wrong Langfuse project, or the keys may have been rotated.
- **Fix**: 
  1. Add environment-aware key resolution: if `LANGFUSE_QA_PUBLIC_KEY` is set, prefer it over `LANGFUSE_PUBLIC_KEY` (matching the pattern already used in `langfuse_client.py`).
  2. Add a startup health check that validates the OTLP endpoint responds with 200 before enabling the exporter, falling back to no-op exporter if auth fails.
  3. Update the QA ECS task definition to inject the correct Langfuse keys.
- **Validation**: `ruff check app/` passes. Deploy to QA, check CloudWatch for absence of 401 errors. Verify spans appear in Langfuse QA project.

### 3. Add QA Langfuse Keys to Environment Configuration
- **File**: `server/.env` (local dev reference), `infrastructure/cdk-eagle/lib/` (ECS task env vars)
- **Problem**: `LANGFUSE_QA_PUBLIC_KEY`, `LANGFUSE_QA_SECRET_KEY`, `LANGFUSE_QA_PROJECT_ID` are empty.
- **Fix**: 
  1. Create a dedicated Langfuse project for QA (or obtain existing project credentials).
  2. Add the keys to the QA ECS task definition environment variables in CDK.
  3. Update `server/.env` with placeholder values and documentation.
- **Validation**: Run `/triage light --env=qa` and confirm Langfuse data is QA-specific.

### 4. Extend Orphan Trace Filter to Cover `eagle-query-*` Pattern
- **File**: `server/app/telemetry/langfuse_client.py` or the trace creation code in `server/app/strands_agentic_service.py`
- **Problem**: The orphan filter in triage only catches `eagle-stream-*` traces. `eagle-query-*` orphan traces (5 in this window) pass through and inflate error counts.
- **Fix**: Either:
  (a) Update the orphan detection logic to also filter `eagle-query-*` traces with no session, no user, cost=0, and null output, OR
  (b) Fix the root cause — ensure `eagle-query-*` traces are always linked to a session ID and properly closed even when the downstream agent call fails.
- **Validation**: Re-run `/triage light` and confirm orphan query traces are either filtered or properly attributed.

### 5. Validate All Fixes
- `ruff check app/` — Python lint
- `npx tsc --noEmit` — TypeScript check (if frontend changes)
- `python -m pytest tests/ -v` — Unit tests
- Re-run `/triage light --env=qa` to confirm issues resolved

## Acceptance Criteria
- All P1 issues resolved: SSO token errors eliminated, OTLP exporter authenticated successfully
- P2 issues resolved or documented with rationale for deferral
- No new errors introduced (re-triage shows improvement)
- Validation commands pass

## Validation Commands
- `ruff check app/` — Python lint
- `python -m pytest tests/ -v` — Unit tests
- `/triage light --env=qa` — Re-triage to confirm improvement
- `aws ecs describe-task-definition --task-definition eagle-backend-qa` — Verify task role

## Notes
- Generated by /triage on 2026-03-31
- Triage report: `docs/development/20260331-000000-report-triage-qa-v1.md`
- Cross-referenced 0 feedback items, 10 CloudWatch errors, 17 Langfuse error traces
- Langfuse data sourced from dev project (QA keys not configured) — QA-specific data gap noted
