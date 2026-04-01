# EAGLE Triage Report

**Date**: 2026-04-01
**Environment**: dev
**Window**: 24h
**Tenant**: default-dev
**Mode**: Full
**Sources**: DynamoDB Feedback, CloudWatch Logs (dev), Langfuse Traces (dev — unavailable, rate-limited)

## Executive Summary

Two distinct issues found in the dev environment over the last 24 hours. The OpenTelemetry OTLP span exporter is continuously failing with HTTP 401 Unauthorized (91 occurrences), meaning all observability trace data is being silently dropped. Separately, the knowledge search AI ranking feature is falling back to basic search because the ECS task role lacks permission to invoke the `claude-3-haiku-20240307-v1:0` model — the IAM policy only permits Haiku 4.5. No user feedback was submitted in this window. Langfuse trace data was unavailable due to API rate limiting during collection.

## Source Data

### DynamoDB Feedback

| Type | Count |
|------|-------|
| General feedback (bug, suggestion, etc.) | 0 |
| Message feedback (thumbs up/down) | 0 |

No user feedback submitted for tenant `default-dev` in the last 24 hours.

### CloudWatch Errors

#### `/eagle/ecs/backend-dev` — 93 errors matched (27,508 records scanned)

| Category | Count | Severity | Pattern |
|----------|-------|----------|---------|
| OTel OTLP Export 401 Unauthorized | ~91 | Warning | `Failed to export span batch code: 401, reason: Unauthorized` |
| Bedrock AccessDeniedException (Haiku) | 2 | ACTIONABLE | `knowledge_search AI ranking failed, falling back: AccessDeniedException...bedrock:InvokeModel...anthropic.claude-3-haiku-20240307-v1:0` |

**OTel OTLP 401 Detail**: The OpenTelemetry HTTP trace exporter is failing every ~5-10 seconds continuously from 20:23 to 20:47 UTC on 2026-03-31. Logger: `opentelemetry.exporter.otlp.proto.http.trace_exporter`. This means all Langfuse spans generated via the OTLP bridge are being dropped silently. The application continues to function but observability is degraded.

**Bedrock AccessDeniedException Detail**: The `eagle-app-role-dev` ECS task role is not authorized to invoke `anthropic.claude-3-haiku-20240307-v1:0`. The IAM policy in `core-stack.ts` only allows `anthropic.claude-haiku-4-5-20251001-v1:0` (Haiku 4.5). The `knowledge_tools.py` code defaults to the old Claude 3 Haiku model ID. The feature degrades gracefully (falls back to non-AI ranking) but search result quality is reduced.

- Session affected: `c11ae897-65db-4001-88f9-fb6701ceb797` (user: `dev-user`, tenant: `dev-tenant`)

#### `/eagle/ecs/frontend-dev` — 0 errors (10 records scanned)

No errors detected in the frontend logs.

#### `/eagle/app` — 0 errors (0 records scanned)

No log data in this shared log group during the query window.

### Langfuse Trace Errors

**Unavailable** — Langfuse API returned HTTP 429 (rate limit exceeded) during data collection. This is a gap in the triage data. The OTel OTLP 401 errors suggest that Langfuse trace ingestion has been failing, so Langfuse data for this window may be incomplete even when accessible.

## Cross-Reference Analysis

### Session Correlation Map

| Session ID | DynamoDB Feedback | CloudWatch Errors | Langfuse Traces |
|------------|-------------------|-------------------|-----------------|
| `c11ae897-65db-4001-88f9-fb6701ceb797` | None | 2x AccessDeniedException (Bedrock Haiku) | Unavailable |

Only one session appears in CloudWatch errors. No feedback was submitted for this session, and Langfuse was unavailable for cross-referencing.

### Error Pattern Clusters

| Cluster | CloudWatch Signal | Langfuse Signal | Feedback Signal | Root Cause |
|---------|-------------------|-----------------|-----------------|------------|
| **OTel Auth Failure** | 91x OTLP 401 Unauthorized | N/A (data loss) | None | OTLP exporter credentials invalid or expired — Langfuse public/secret key pair used for OTLP Basic auth may be stale or endpoint misconfigured |
| **Bedrock IAM Gap** | 2x AccessDeniedException for claude-3-haiku | N/A | None | `knowledge_tools.py` defaults to `claude-3-haiku-20240307-v1:0` but IAM only allows `claude-haiku-4-5-20251001-v1:0` |

### Trend Analysis

- **OTel 401 errors are continuous and persistent** — they occur every 5-10 seconds during the observed window (20:23–20:47 UTC), indicating a systemic configuration issue rather than intermittent failure. This has likely been ongoing since the last deployment that changed OTLP credentials or Langfuse project configuration.
- **Bedrock AccessDeniedException is session-triggered** — only 2 occurrences tied to a single session, meaning it fires only when knowledge_search is invoked. The graceful fallback masks the issue from users.
- **No user-reported feedback** — either the system is not actively used by end users in dev, or users are not reporting issues.

## Prioritized Issue List

| # | Issue | Severity | Score | Sources | Sessions | Priority |
|---|-------|----------|-------|---------|----------|----------|
| 1 | OTel OTLP span export failing with 401 Unauthorized — all observability data lost | Warning | 3 | CW | 0 (infra) | **P1** |
| 2 | Bedrock IAM denies claude-3-haiku for knowledge_search AI ranking | ACTIONABLE | 3 | CW | 1 | **P1** |

### Scoring Breakdown

**Issue 1 — OTel OTLP 401**:
- User-facing: 0 (no feedback, backend-only)
- Frequency: 2 (91 occurrences — high)
- Cross-source: 0 (single source)
- Severity: 1 (ACTIONABLE — data loss)
- **Total: 3 → P1**

**Issue 2 — Bedrock Haiku IAM**:
- User-facing: 0 (no feedback, graceful fallback)
- Frequency: 1 (2 occurrences — low)
- Cross-source: 0 (single source)
- Severity: 1 (ACTIONABLE — IAM gap)
- **Total: 2 → P2** (bumped to P1 because it degrades search quality silently)

## Noise Report

| Pattern | Count | Classification | Justification |
|---------|-------|----------------|---------------|
| OTel OTLP 401 Unauthorized | 91 | **Not noise — promoted to P1** | Unlike "Failed to detach context" (benign OTel async issue), 401 Unauthorized means spans are actively being dropped. Observability is degraded. |

No items classified as pure noise in this window. The frontend and app log groups had zero errors.

## Data Gaps

1. **Langfuse traces**: API rate-limited (HTTP 429) during collection — no trace-level data available for cross-referencing.
2. **OTel OTLP failures may cause Langfuse data gaps**: Since the OTLP exporter is failing with 401, Langfuse may have incomplete or missing trace data for the backend even when accessible.
