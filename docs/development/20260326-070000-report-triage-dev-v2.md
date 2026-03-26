# EAGLE Triage Report

**Date**: 2026-03-26
**Environment**: dev
**Window**: 24h
**Tenant**: default-dev
**Mode**: Full
**Sources**: DynamoDB Feedback, CloudWatch Logs (dev), Langfuse Traces (dev)

## Executive Summary

No critical user-facing outages in the last 24 hours. Two issues identified: (1) admin dashboard pages fail to load traces and costs due to Cognito tokens missing `custom:tenant_id`, and (2) 44% of Langfuse traces show `output=null` with `cost=0`, indicating streaming spans are not being closed properly — likely from automated tests or eval runs that don't consume the full SSE stream. Additionally, the CI deploy role lacks CloudWatch Logs Insights permissions, limiting observability in automated triage.

## Source Data

### DynamoDB Feedback

| Metric | Value |
|--------|-------|
| General feedback (bug, suggestion, etc.) | 0 |
| Message feedback (thumbs up/down) | 0 |
| Time window | Last 24h |
| Tenant | default-dev |

No user feedback submitted in the last 24 hours. This may indicate low usage in the dev environment or that the feedback mechanism is not being exercised.

### CloudWatch Errors

#### /eagle/ecs/backend-dev
**0 error events** — Backend is clean.

#### /eagle/ecs/frontend-dev
**2 error events** — Both are authentication failures on admin API routes.

| Timestamp | Error |
|-----------|-------|
| 2026-03-26T07:04:59Z | `Admin traces error: 401 - {"detail":"Authentication failed: 403: No tenant ID found in token"}` |
| 2026-03-26T07:05:03Z | `Admin costs error: 401 - {"detail":"Authentication failed: 403: No tenant ID found in token"}` |

**Category**: Application Bug — JWT token does not contain `custom:tenant_id` attribute.
**Severity**: ACTIONABLE
**Root cause**: `server/app/auth.py:54` checks `payload.get("custom:tenant_id")` and raises 403 if missing. The Cognito token being used on the admin dashboard lacks this custom attribute, possibly because the user was created without it or the attribute is not mapped in the Cognito user pool token configuration.

#### /eagle/app
**0 error events** — Shared app log group is clean.

#### IAM Gap: CloudWatch Logs Insights
The CI role (`eagle-deploy-role-dev`) lacks `logs:StartQuery` and `logs:DescribeLogGroups` permissions. This prevented using CloudWatch Logs Insights queries (the MCP tool). The `filter_log_events` API worked as a fallback but is less powerful. This is an infrastructure gap that should be fixed for CI-based triage.

### Langfuse Trace Errors

| Metric | Value |
|--------|-------|
| Total traces (24h) | 50 |
| Successful | 28 (56%) |
| Error/incomplete | 22 (44%) |
| Avg latency | 22ms |
| Total cost | $1.4811 |
| Unique users | 3 |

**All 22 error traces share the same pattern:**
- `output: null`, `cost: 0`, `latency: 0ms`
- Names: `eagle-stream-sess-001` (7), `eagle-stream-sess-del` (7), `eagle-stream-452dd10e` (2), `eagle-stream-4884aa4c` (2), `eagle-stream-d2a49e6e` (2), others (2)
- No `error_message` set on any observation
- No `session_id` or `user_id` propagated (null for 21 of 22)

**Category**: Incomplete Langfuse spans — the `eagle-stream-*` parent span is opened but never receives `_root_span.update(output=...)` or `_lf_ctx.__exit__()`.

**Likely root causes:**
1. **Eval/test runs**: Automated tests call the streaming endpoint but may not fully consume the async generator, so the Langfuse cleanup code at the end of `sdk_query_streaming()` (lines 4336-4346) never executes.
2. **Client disconnect**: If the SSE consumer disconnects mid-stream, FastAPI may abort the generator without reaching the Langfuse finalization block.
3. **Session name patterns** (`sess-001`, `sess-del`) suggest these are integration test sessions, not real user sessions.

## Cross-Reference Analysis

### Session Correlation Map

No sessions appear in 2+ sources. The CloudWatch auth errors reference admin API endpoints (not chat sessions), and the Langfuse error traces have no `session_id` populated, so cross-referencing is not possible for this window.

### Error Pattern Clusters

| Cluster | CloudWatch Signal | Langfuse Signal | Feedback Signal | Severity |
|---------|------------------|-----------------|-----------------|----------|
| **Admin Auth** | 2x "No tenant ID found in token" on admin traces + costs | None | None | P2 |
| **Incomplete Traces** | None | 22x output=null, cost=0 eagle-stream-* spans | None | P2 |
| **IAM Observability Gap** | AccessDenied on logs:StartQuery, logs:DescribeLogGroups | None | None | P1 |

### Trend Analysis

- **Admin auth errors**: Both occurred within 4 seconds of each other (07:04:59 - 07:05:03), suggesting a single admin page load that triggered both API calls. This is a recurring issue likely affecting any admin user whose Cognito token lacks `custom:tenant_id`.
- **Incomplete Langfuse traces**: Concentrated in two bursts — 04:44-04:45 UTC (sess-del, 7 traces) and 04:45 UTC (sess-001, 7 traces). This pattern matches automated test runs (eval suite or integration tests).
- **No user-reported feedback**: Either the dev environment has very low human usage, or the feedback widget is not being used. Given 3 unique Langfuse users, this is likely a low-traffic dev environment.

## Prioritized Issue List

| # | Issue | Composite Score | Priority | Sources | Sessions Affected |
|---|-------|----------------|----------|---------|-------------------|
| 1 | CI IAM role missing CloudWatch Logs Insights permissions | 4 | P1 | CW | N/A (infra) |
| 2 | Admin dashboard auth fails — "No tenant ID found in token" | 3 | P2 | CW | 1 admin session |
| 3 | Langfuse streaming spans incomplete (output=null, cost=0) | 3 | P2 | LF | 22 traces |

**Scoring breakdown:**
1. **IAM Observability Gap** (P1): Frequency=1 + Cross-source=0 + Severity=1 (ACTIONABLE) + User-facing=0 + Infra-blocking bonus=2 = **4**. Blocks automated triage from running full CloudWatch analysis.
2. **Admin Auth** (P2): Frequency=1 + Cross-source=0 + Severity=1 (ACTIONABLE) + User-facing=1 (admin page broken) = **3**
3. **Incomplete Traces** (P2): Frequency=2 + Cross-source=0 + Severity=1 (data quality) + User-facing=0 = **3**. Not user-impacting but pollutes observability data.

## Noise Report

| Category | Count | Justification |
|----------|-------|---------------|
| OTel context detach warnings | 0 | None observed in this window |
| Deprecation warnings | 0 | None observed |
| Bedrock cold starts / ModelNotReady | 0 | None observed |
| Bedrock throttling | 0 | None observed |

The dev environment is notably clean — no noise-level errors detected. The only errors are actionable.
