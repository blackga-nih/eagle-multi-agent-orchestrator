# Plan: Triage Fixes — 2026-03-30

## Task Description
Fix 4 issues identified by /triage diagnostic scan across DynamoDB feedback, CloudWatch logs (blocked), and Langfuse traces for the QA environment.

## Objective
Resolve the P1 CI IAM permission gap and P2 Langfuse instrumentation issues to restore full automated observability and reduce false error signals.

## Problem Statement
The QA triage pipeline is operating at reduced capacity: CloudWatch log analysis is entirely blocked by missing IAM permissions on the CI deploy role, Langfuse traces show a 57% error rate inflated by orphan stream traces, and one real user request failed silently without producing output or cost. No QA-specific Langfuse project is configured, so triage data mixes dev and QA environments.

## Relevant Files
- `infrastructure/cdk-eagle/lib/ci-cd-stack.ts` — CI/CD role IAM policy (needs CloudWatch Logs read permissions)
- `server/app/streaming_routes.py` — SSE streaming endpoint (creates Langfuse traces that may become orphans)
- `server/app/stream_protocol.py` — MultiAgentStreamWriter (Langfuse trace lifecycle)
- `server/app/strands_agentic_service.py` — Strands SDK orchestration (silent failure handling)
- `server/.env` — Langfuse credential configuration (missing QA keys)

## Implementation Phases

### Phase 1: P1 Fixes (Critical)

#### 1. Grant CloudWatch Logs read permissions to CI deploy role

- **File**: `infrastructure/cdk-eagle/lib/ci-cd-stack.ts`
- **Problem**: The `eagle-deploy-role-dev` IAM role assumed by GitHub Actions OIDC does not include CloudWatch Logs read permissions. This blocks all automated triage CloudWatch analysis.
- **Fix**: Add a policy statement granting CloudWatch Logs read-only actions to the deploy role:
  ```typescript
  deployRole.addToPolicy(new iam.PolicyStatement({
    effect: iam.Effect.ALLOW,
    actions: [
      'logs:StartQuery',
      'logs:StopQuery',
      'logs:GetQueryResults',
      'logs:DescribeLogGroups',
      'logs:DescribeLogStreams',
      'logs:GetLogEvents',
      'logs:FilterLogEvents',
    ],
    resources: [
      'arn:aws:logs:us-east-1:*:log-group:/eagle/*',
    ],
  }));
  ```
- **Validation**: Deploy CDK stack, then re-run triage and confirm CloudWatch queries succeed

### Phase 2: P2 Fixes (High)

#### 2. Prevent orphan Langfuse stream traces

- **File**: `server/app/streaming_routes.py` and/or `server/app/stream_protocol.py`
- **Problem**: Langfuse traces are created at SSE stream initialization but remain empty when the request fails early. This inflates the error rate.
- **Fix**: Defer Langfuse trace creation until the first meaningful event, or mark early-exit traces with explicit status.
- **Validation**: Trigger test requests in QA, verify no new orphan traces

#### 3. Add error propagation for silent request failures

- **File**: `server/app/strands_agentic_service.py`
- **Problem**: Session 114df9de shows a request that produced no output and no error message.
- **Fix**: Ensure exceptions during model invocation are logged and recorded in Langfuse trace.
- **Validation**: Simulate a Bedrock auth failure, confirm error appears in logs and trace

### Phase 3: P2 Improvements (Medium)

#### 4. Configure QA-specific Langfuse project

- **File**: QA environment config (ECS task definition / SSM)
- **Problem**: No QA-specific Langfuse keys configured. Triage uses dev project.
- **Fix**: Create QA Langfuse project and add keys to QA environment.
- **Validation**: QA test trace appears in separate QA project

## Step by Step Tasks

### 1. Add CloudWatch Logs permissions to CI role
- **File**: `infrastructure/cdk-eagle/lib/ci-cd-stack.ts`
- **Problem**: AccessDeniedException on all logs operations
- **Fix**: Add IAM policy statement with CloudWatch Logs read actions scoped to /eagle/* log groups
- **Validation**: `npx cdk synth --quiet` passes; CloudWatch queries succeed after deploy

### 2. Fix orphan Langfuse stream traces
- **File**: `server/app/streaming_routes.py`, `server/app/stream_protocol.py`
- **Problem**: 7 orphan traces with null output inflate error metrics
- **Fix**: Defer trace creation or mark early-exit traces with explicit status
- **Validation**: `ruff check app/` passes; no new orphan traces in QA

### 3. Add error propagation to Strands SDK invocation
- **File**: `server/app/strands_agentic_service.py`
- **Problem**: Silent failure with null output and no error recorded
- **Fix**: Ensure exceptions are logged and recorded in Langfuse trace
- **Validation**: `python -m pytest tests/ -v` passes

### 4. Configure QA Langfuse keys
- **File**: QA environment config
- **Problem**: QA traces go to dev Langfuse project
- **Fix**: Create QA project and add keys
- **Validation**: QA trace appears in separate project

### 5. Validate All Fixes
- `ruff check app/`
- `npx tsc --noEmit`
- `python -m pytest tests/ -v`
- `npx cdk synth --quiet`
- Re-run `/triage light --env=qa` to confirm improvement

## Acceptance Criteria
- All P1 issues resolved (CloudWatch accessible from CI)
- All P2 issues resolved or documented with rationale for deferral
- No new errors introduced
- Validation commands pass

## Validation Commands
- `ruff check app/` — Python lint
- `npx tsc --noEmit` — TypeScript check
- `python -m pytest tests/ -v` — Unit tests
- `npx cdk synth --quiet` — CDK compile
- `/triage light --env=qa` — Re-triage to confirm improvement

## Notes
- Generated by /triage on 2026-03-30
- Triage report: docs/development/20260330-091000-report-triage-qa-v2.md
- Cross-referenced 0 feedback items, 0 CloudWatch errors (blocked), 8 Langfuse error traces
- CloudWatch data gap means additional issues may exist not captured in this plan
