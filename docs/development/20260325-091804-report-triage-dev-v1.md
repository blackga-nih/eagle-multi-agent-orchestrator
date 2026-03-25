# EAGLE Triage Report

**Date**: 2026-03-25
**Environment**: dev
**Window**: 24h
**Tenant**: default-dev
**Mode**: Full
**Sources**: DynamoDB Feedback, CloudWatch Logs (dev), Langfuse Traces (dev)

## Executive Summary

The dev environment has **two active issues**: (1) an IAM permissions gap preventing CloudWatch Logs access from the CI/CD deploy role, and (2) Langfuse traces showing a 24% error rate (12/50 traces) driven by SSO token expiration and null-output test traces. No user feedback was submitted in the last 24 hours. The CloudWatch gap is the most critical finding — it means the deploy pipeline and triage automation cannot query operational logs.

## Source Data

### DynamoDB Feedback

| Metric | Value |
|--------|-------|
| General feedback (bug, suggestion, etc.) | 0 items |
| Message feedback (thumbs up/down) | 0 items |
| Time window | Last 24h |
| Tenant | default-dev |

No user feedback submitted in the last 24 hours. This is expected for a dev environment with low traffic.

### CloudWatch Errors

**All 3 log groups returned AccessDeniedException.**

| Log Group | Status | Error |
|-----------|--------|-------|
| `/eagle/ecs/backend-dev` | ACCESS_DENIED | `eagle-deploy-role-dev` not authorized for `logs:DescribeLogGroups`, `logs:StartQuery` |
| `/eagle/ecs/frontend-dev` | ACCESS_DENIED | Same — missing CloudWatch Logs permissions |
| `/eagle/app` | ACCESS_DENIED | Same — missing CloudWatch Logs permissions |

**Root cause**: The `eagle-deploy-role-dev` IAM role (assumed via GitHub Actions OIDC) lacks CloudWatch Logs Insights permissions. The role can deploy (ECS, CDK) but cannot read logs.

**Category**: IAM/SSO — ACTIONABLE
**Impact**: CI/CD triage pipeline is blind to runtime errors. Manual SSO login required to check logs.

### Langfuse Trace Errors

| Metric | Value |
|--------|-------|
| Total traces (24h) | 50 |
| Successful | 38 (76%) |
| Errors | 12 (24%) |
| Avg latency | 19ms |
| Total cost | $0.7624 |
| Unique users | 2 |

#### Error Traces

| # | Timestamp | Name | Error | Category | Severity |
|---|-----------|------|-------|----------|----------|
| 1 | 2026-03-25T07:29:37Z | `invoke_agent Strands Agents` | `TokenRetrievalError: Token has expired and refresh failed` | SSO Expired | ACTIONABLE |
| 2 | 2026-03-25T07:24:30Z | `eagle-stream-sess-001` | output: null, cost: 0 | Auth/Infra Failure | ACTIONABLE |
| 3 | 2026-03-25T07:24:29Z | `eagle-stream-s` | output: null, cost: 0 | Auth/Infra Failure | ACTIONABLE |
| 4 | 2026-03-25T07:24:29Z | `eagle-stream-s` | output: null, cost: 0 | Auth/Infra Failure | ACTIONABLE |
| 5 | 2026-03-25T07:24:28Z | `eagle-stream-sess-001` | output: null, cost: 0 | Auth/Infra Failure | ACTIONABLE |
| 6 | 2026-03-25T07:24:28Z | `eagle-stream-sess-001` | output: null, cost: 0 | Auth/Infra Failure | ACTIONABLE |
| 7 | 2026-03-25T07:24:27Z | `eagle-stream-sess-001` | output: null, cost: 0 | Auth/Infra Failure | ACTIONABLE |
| 8 | 2026-03-25T07:24:27Z | `eagle-stream-sess-001` | output: null, cost: 0 | Auth/Infra Failure | ACTIONABLE |
| 9 | 2026-03-25T07:24:26Z | `eagle-stream-sess-001` | output: null, cost: 0 | Auth/Infra Failure | ACTIONABLE |
| 10 | 2026-03-25T07:24:26Z | `eagle-stream-sess-001` | output: null, cost: 0 | Auth/Infra Failure | ACTIONABLE |
| 11 | 2026-03-25T07:22:49Z | `eagle-stream-ses-001` | output: null, cost: 0 | Auth/Infra Failure | ACTIONABLE |
| 12 | 2026-03-25T05:39:28Z | `eagle-stream-4557cf61` | output: null, cost: 0 | Auth/Infra Failure | ACTIONABLE |

**Pattern**: 10 traces clustered at 07:24 UTC are from a batch test/eval run. All have `output: null` and `cost: 0`, indicating the Strands agent never reached Bedrock (likely due to expired SSO token on the dev ECS task role or test runner).

## Cross-Reference Analysis

### Session Correlation Map

No session IDs were present in the Langfuse error traces (all `session_id: null`), and no DynamoDB feedback was submitted. Cross-referencing by session is not possible for this window.

CloudWatch logs were inaccessible, preventing correlation with Langfuse trace timestamps.

### Error Pattern Clusters

| Cluster | CloudWatch Signal | Langfuse Signal | Feedback Signal | Confirmed |
|---------|------------------|-----------------|-----------------|-----------|
| **IAM Permissions Gap** | AccessDeniedException on all 3 log groups | N/A | None | Single-source (CW) |
| **SSO Token Expiration** | Inaccessible | 1 explicit `Token has expired` error | None | Single-source (LF) |
| **Null-Output Traces** | Inaccessible | 11 traces with output=null, cost=0 | None | Single-source (LF) |

**Likely root cause for clusters 2+3**: The SSO token expiration (trace #1) is the upstream cause of the null-output traces. When the Bedrock session token expires, Strands agent calls fail silently, producing traces with no output and zero cost. The 10 rapid-fire traces at 07:24 UTC suggest an automated test run hitting this failure repeatedly.

### Trend Analysis

- **Temporal clustering**: 10/12 error traces occurred within a 4-second window (07:24:26–07:24:30 UTC), indicating an automated batch — not organic user failures.
- **Low user impact**: Only 2 unique users in the window, and no feedback was submitted, suggesting these are CI/test traces rather than production user sessions.
- **Recurring pattern**: SSO token expiration is a known recurring issue in dev environments where the ECS task role or local SSO session is not refreshed.

## Prioritized Issue List

| # | Issue | Composite Score | Priority | Sources | Sessions Affected |
|---|-------|----------------|----------|---------|-------------------|
| 1 | IAM role `eagle-deploy-role-dev` missing CloudWatch Logs permissions (`logs:DescribeLogGroups`, `logs:StartQuery`, `logs:GetQueryResults`) | 5 | **P1** | CW | N/A (infra) |
| 2 | SSO token expiration causing Strands agent failures (12 null-output traces) | 4 | **P1** | LF | 0 (test/CI traces) |

**Scoring breakdown:**

| Issue | User-facing (0-3) | Frequency (0-2) | Cross-source (0-2) | Severity (0-1) | Total |
|-------|--------------------|-----------------|---------------------|----------------|-------|
| #1 IAM permissions | 0 (no user feedback) | 2 (affects every CI run) | 0 (single source) | 1 (ACTIONABLE) | 5 (weighted: 0*3 + 2*2 + 0*2 + 1*1) |
| #2 SSO token expiry | 0 (no user feedback) | 2 (12 occurrences) | 0 (single source) | 1 (ACTIONABLE) | 5 (weighted: 0*3 + 2*2 + 0*2 + 1*1) |

Both are P1 — fix this sprint. Neither is P0 because there is no user-facing impact confirmed via feedback.

## Noise Report

| Category | Count | Justification |
|----------|-------|---------------|
| OTel detach context | 0 | Not observable (CloudWatch inaccessible) |
| Deprecation warnings | 0 | Not observable (CloudWatch inaccessible) |
| Bedrock cold starts | 0 | None in Langfuse traces |

**Note**: The noise baseline cannot be established without CloudWatch access. Fixing issue #1 (IAM permissions) will enable future triage runs to filter noise properly.
