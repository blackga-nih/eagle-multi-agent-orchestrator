# EAGLE Triage Report

**Date**: 2026-04-01
**Environment**: dev
**Window**: 1h (expanded to 48h for context)
**Tenant**: default-dev
**Mode**: Full
**Sources**: CloudWatch Logs (dev) | DynamoDB Feedback (SKIPPED) | Langfuse Traces (SKIPPED)

## Executive Summary

Two distinct issues found in the dev backend. (1) The OpenTelemetry OTLP trace exporter is continuously failing with 401 Unauthorized (85 errors in 48h), meaning all telemetry/traces are being lost. (2) The `knowledge_search` AI ranking feature is failing because the IAM policy does not allow the `claude-3-haiku-20240307-v1:0` model — the CDK stack only grants access to the newer Haiku 4.5 model. This affects knowledge search quality for all users in 2 observed sessions. No frontend or application-level errors were detected.

**Data Gaps**: DynamoDB feedback and Langfuse trace queries could not be executed due to a broken pre-tool-use hook in `.claude/settings.json` (Windows path incompatible with CI). The CI deploy role also lacks `cloudwatch:DescribeAlarms` permission, so active alarms could not be checked.

## Source Data

### DynamoDB Feedback

**SKIPPED** — Bash tool blocked by broken PreToolUse hook in `.claude/settings.json` (references Windows path `C:/Users/blackga/Desktop/eagle/sm_eagle/.claude/hooks/pre_tool_use.py`).

### CloudWatch Errors

#### `/eagle/ecs/backend-dev`

| # | Category | Error | Count | Severity | Time Range |
|---|----------|-------|-------|----------|------------|
| 1 | OTel Export Auth | `Failed to export span batch code: 401, reason: Unauthorized` | 85 | Warning | 2026-03-31 18:32–20:47 |
| 2 | Bedrock IAM | `AccessDeniedException: bedrock:InvokeModel on anthropic.claude-3-haiku-20240307-v1:0` | 8 | ACTIONABLE | 2026-03-31 18:31–20:31 |

**Total records scanned**: 36,248 (48h window)
**Error records matched**: 93
**Log stream**: `backend/eagle-backend/049a1688cd554ade8d5466ad1f60483c` and `edc367671f5a4e9ba4252f4c2575e0d2`

**Traffic pattern**: Consistent ~720 records/hour (health checks + heartbeats). Spikes to 2,023–2,460/hour during 2026-03-31 18:00–21:00 when user sessions were active and errors occurred.

#### `/eagle/ecs/frontend-dev`

**0 errors** — 15 records scanned, no matches. Frontend is healthy.

#### `/eagle/app`

**0 errors** — 0 records scanned. No application-level log activity in window.

### Langfuse Trace Errors

**SKIPPED** — Bash tool blocked (same hook issue as DynamoDB). However, the OTel export 401 errors suggest Langfuse OTLP ingestion auth is broken, which means traces are likely not being recorded at all.

## Cross-Reference Analysis

### Session Correlation Map

| Session ID | Source | Error |
|------------|--------|-------|
| `c11ae897-65db-4001-88f9-fb6701ceb797` | CW | Bedrock AccessDenied x5 (20:22–20:31) |
| `adca241b-5a4b-463c-837e-a4c91da5f7db` | CW | Bedrock AccessDenied x3 (18:31–18:33) |

Both sessions belong to `dev-tenant` / `dev-user`. Cross-reference with DynamoDB feedback and Langfuse was not possible due to data gaps.

### Error Pattern Clusters

| Cluster | CloudWatch Signal | Langfuse Signal | Feedback Signal |
|---------|------------------|-----------------|-----------------|
| **OTel Auth Failure** | 85x OTLP export 401 Unauthorized | N/A (skipped) | N/A (skipped) |
| **Bedrock IAM Gap** | 8x AccessDeniedException for claude-3-haiku | N/A (skipped) | N/A (skipped) |

### Trend Analysis

- **OTel errors** occur in bursts during user sessions (18:32–18:44, 20:23–20:47) — every ~5 seconds when trace batches are flushed. This is continuous and will persist until the OTLP auth is fixed.
- **Bedrock errors** occur only when `knowledge_search` is invoked — the code gracefully falls back but search quality is degraded. This will affect every session that uses knowledge search.
- **No errors in the last ~24h** (since 2026-03-31 20:47) — suggests no new user sessions have triggered these code paths since then. The underlying issues remain unfixed.

## Prioritized Issue List

### P1 — Bedrock IAM: Missing claude-3-haiku model permission (Score: 5/8)

| Factor | Score | Reasoning |
|--------|-------|-----------|
| User-facing | 2/3 | Degrades knowledge search quality (falls back to non-AI ranking) |
| Frequency | 1/2 | 8 occurrences across 2 sessions |
| Cross-source | 0/2 | Only confirmed in CloudWatch (other sources skipped) |
| Severity | 1/1 | ACTIONABLE — IAM permission gap |

**Root cause**: `infrastructure/cdk-eagle/lib/core-stack.ts` lines 145–167 only grants `bedrock:InvokeModel` for Haiku 4.5 (`anthropic.claude-haiku-4-5-20251001-v1:0`), but `server/app/` knowledge_tools code calls `anthropic.claude-3-haiku-20240307-v1:0` for AI-powered search ranking.

**Fix options**:
1. **Preferred**: Update the knowledge_tools code to use `anthropic.claude-haiku-4-5-20251001-v1:0` (newer, better model)
2. **Alternative**: Add `anthropic.claude-3-haiku-20240307-v1:0` to the CDK IAM policy

### P2 — OTel OTLP Export: 401 Unauthorized (Score: 3/8)

| Factor | Score | Reasoning |
|--------|-------|-----------|
| User-facing | 0/3 | Telemetry-only, no user impact |
| Frequency | 2/2 | 85 occurrences, continuous during sessions |
| Cross-source | 0/2 | Only CloudWatch |
| Severity | 1/1 | ACTIONABLE — all traces are being lost |

**Root cause**: The OTLP trace exporter is sending batches to an endpoint that returns 401. This is likely a Langfuse OTLP ingestion endpoint with expired or misconfigured credentials. The OTel exporter configuration needs to be checked.

### P3 — CI Role: Missing cloudwatch:DescribeAlarms (Score: 1/8)

| Factor | Score | Reasoning |
|--------|-------|-----------|
| User-facing | 0/3 | CI/operational only |
| Frequency | 0/2 | 1 occurrence (this triage run) |
| Cross-source | 0/2 | Only observed in CI |
| Severity | 1/1 | ACTIONABLE but low priority |

**Root cause**: `eagle-deploy-role-dev` IAM policy does not include `cloudwatch:DescribeAlarms`. The triage workflow cannot check active alarms.

### P3 — Broken Pre-Tool-Use Hook in settings.json (Score: 1/8)

**Root cause**: `.claude/settings.json` references a Windows-only path for the Bash hook (`C:/Users/blackga/Desktop/eagle/sm_eagle/.claude/hooks/pre_tool_use.py`). This blocks all Bash tool calls in CI (Linux).

## Noise Report

| Pattern | Count | Classification | Justification |
|---------|-------|---------------|---------------|
| OTel OTLP 401 | 85 | Promoted to P2 | Normally OTel errors are noise, but 401 means ALL telemetry is lost — not a transient issue |
| Deprecation warnings | 0 | N/A | None observed |
| Cold starts | 0 | N/A | None observed |
