# Plan: Triage Fixes — 2026-03-27

## Task Description
Fix 4 issues identified by /triage diagnostic scan across DynamoDB feedback, CloudWatch logs, and Langfuse traces for the dev environment.

## Objective
Resolve P2 issues to improve observability accuracy and system reliability. No P0/P1 issues exist — the dev environment is operationally healthy.

## Problem Statement
Langfuse trace instrumentation creates 53 wrapper traces with null output that inflate error metrics, making it difficult to distinguish real failures from instrumentation artifacts. A 4-minute burst of 7 Strands agent failures suggests an auth/init barrier during automated testing. The `/eagle/app` CloudWatch log group has been inactive for 9 days, indicating a potential logging gap. The CI deploy role lacks CloudWatch Log Insights query permissions, limiting automated triage capability.

## Relevant Files
- `server/app/strands_agentic_service.py` — Langfuse trace instrumentation for agent invocations
- `server/app/streaming_routes.py` — SSE streaming endpoint that creates wrapper traces
- `infrastructure/cdk-eagle/lib/ci-cd-stack.ts` — CI/CD IAM role permissions
- `infrastructure/cdk-eagle/lib/compute-stack.ts` — ECS task logging configuration
- `server/app/main.py` — Application startup and logging configuration

## Implementation Phases

### Phase 1: P2 Fixes (Medium Priority)

#### 1. Fix Langfuse trace wrapper output capture
- **File**: `server/app/strands_agentic_service.py`
- **Problem**: Eval/QA/stream wrapper traces (`eagle-query-*`, `eagle-stream-*`) are created but never receive output, inflating null-output counts in Langfuse. The inner `invoke_agent Strands` trace captures the real output, but outer wrappers are left with `output=None`.
- **Fix**: Either (a) set a sentinel output on wrapper traces (e.g., `{"type": "wrapper", "inner_trace": "<trace_id>"}`) so they are distinguishable from real failures, or (b) suppress wrapper trace creation for eval/QA runs by checking the trace name prefix before creating the outer trace.
- **Validation**: Run eval suite, verify Langfuse traces — wrapper traces should either have output set or not be created.

#### 2. Investigate and fix /eagle/app log group inactivity
- **File**: `server/app/main.py` and `infrastructure/cdk-eagle/lib/compute-stack.ts`
- **Problem**: `/eagle/app` log group has not received events since 2026-03-18 (9 days). Session-level logging may have been disabled or the log stream configuration changed.
- **Fix**: Check if the application still references the `/eagle/app` log group. If logging was intentionally moved to `/eagle/ecs/backend-dev`, document the change and consider removing the stale log group. If logging was accidentally disabled, re-enable it.
- **Validation**: Send a test request to the dev backend and verify logs appear in the expected log group.

#### 3. Investigate Strands agent init failures during test burst
- **File**: `server/app/strands_agentic_service.py`
- **Problem**: 7 Strands agent calls with "Hello" input failed with <3ms latency and $0 cost, suggesting the agent never reached Bedrock. All occurred in a 4-minute window from `dev-user`.
- **Fix**: Add error-level logging when Strands agent initialization fails before reaching the model. Currently, these failures are silent (no CloudWatch errors). The root cause is likely a transient auth/credential issue during the test run, but the lack of error logging obscures the cause.
- **Validation**: Intentionally trigger an agent init failure (e.g., with invalid credentials) and verify an error log appears in CloudWatch.

### Phase 2: P3 Improvements (Low Priority)

#### 4. Add logs:StartQuery permission to CI deploy role
- **File**: `infrastructure/cdk-eagle/lib/ci-cd-stack.ts`
- **Problem**: The `eagle-deploy-role-dev` IAM role used by GitHub Actions OIDC lacks `logs:StartQuery` and `logs:GetQueryResults` permissions, preventing CloudWatch Log Insights queries during automated triage.
- **Fix**: Add `logs:StartQuery`, `logs:GetQueryResults`, `logs:StopQuery` to the CI/CD role's IAM policy for the three log groups (`/eagle/ecs/backend-dev`, `/eagle/ecs/frontend-dev`, `/eagle/app`).
- **Validation**: `npx cdk synth --quiet` passes, and after deploy, the triage workflow can run Log Insights queries.

## Step by Step Tasks

### 1. Fix Langfuse wrapper trace output
- **File**: `server/app/strands_agentic_service.py`
- **Problem**: Wrapper traces left with null output inflate error metrics
- **Fix**: Add `trace.update(output={"type": "wrapper"})` or conditional trace creation
- **Validation**: Run eval suite, check Langfuse for reduced null-output count

### 2. Audit /eagle/app log group usage
- **File**: `server/app/main.py`, `infrastructure/cdk-eagle/lib/compute-stack.ts`
- **Problem**: Log group inactive 9+ days
- **Fix**: Confirm whether logging was redirected; update or remove stale config
- **Validation**: Check log group receives events after next deploy

### 3. Add error logging for Strands init failures
- **File**: `server/app/strands_agentic_service.py`
- **Problem**: Agent failures before Bedrock are silent
- **Fix**: Add try/except with `logger.error()` around agent initialization
- **Validation**: Verify error appears in CloudWatch when agent init fails

### 4. Add CloudWatch Insights IAM permissions for CI role
- **File**: `infrastructure/cdk-eagle/lib/ci-cd-stack.ts`
- **Problem**: CI role cannot run Log Insights queries
- **Fix**: Add `logs:StartQuery`, `logs:GetQueryResults`, `logs:StopQuery` actions
- **Validation**: `npx cdk synth --quiet` && re-run triage in CI

### 5. Validate All Fixes
- `ruff check app/`
- `npx tsc --noEmit`
- `python -m pytest tests/ -v`
- Re-run `/triage light` to confirm issues resolved

## Acceptance Criteria
- All P2 issues resolved or documented with rationale for deferral
- No new errors introduced (re-triage shows improvement)
- Langfuse null-output wrapper traces are either tagged or suppressed
- Validation commands pass

## Validation Commands
- `ruff check app/` — Python lint
- `npx tsc --noEmit` — TypeScript check
- `python -m pytest tests/ -v` — Unit tests
- `/triage light` — Re-triage to confirm improvement

## Notes
- Generated by /triage on 2026-03-27
- Triage report: `docs/development/20260327-091734-report-triage-dev-v3.md`
- Cross-referenced 0 feedback items, 0 CloudWatch errors, 100 Langfuse traces (7 real failures, 53 instrumentation artifacts)
- No P0/P1 issues — dev environment is operationally healthy
