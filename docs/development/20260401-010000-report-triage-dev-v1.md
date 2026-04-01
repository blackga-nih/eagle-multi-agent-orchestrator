# EAGLE Triage Report

**Date**: 2026-04-01
**Environment**: dev
**Window**: 1h (expanded to 24h for context — low activity in strict 1h window)
**Tenant**: default-dev
**Mode**: Full
**Sources**: DynamoDB Feedback (UNAVAILABLE), CloudWatch Logs (dev), Langfuse Traces (UNAVAILABLE)

## Executive Summary

Two distinct backend issues were identified in the dev environment over the past 24 hours. The highest-impact issue is a **Bedrock IAM permission gap** causing `knowledge_search` AI-powered document ranking to fail and fall back to basic ranking — this degrades search quality for all users. The second issue is **OTLP trace export authentication failure** (401 Unauthorized), causing all OpenTelemetry span data to be silently dropped — this means observability/tracing data is being lost. A third operational issue — a **broken Bash hook in `.claude/settings.json`** — blocked DynamoDB and Langfuse data collection during this triage, creating gaps in the report.

No errors were found in frontend or shared app log groups. Backend traffic is stable at ~720 records/hour baseline with activity spikes to ~2,400/hour during business hours (20:00-21:00 UTC).

## Data Collection Gaps

| Source | Status | Reason |
|--------|--------|--------|
| CloudWatch Logs | Collected | 3 log groups queried successfully via MCP |
| DynamoDB Feedback | **UNAVAILABLE** | Bash tool blocked by broken pre-tool hook in `.claude/settings.json` |
| Langfuse Traces | **UNAVAILABLE** | Same — Bash tool blocked |

The broken hook at `.claude/settings.json` references a Windows-specific path (`C:/Users/blackga/Desktop/eagle/sm_eagle/.claude/hooks/pre_tool_use.py`) that does not exist on the Linux CI runner. This prevents all Bash command execution, blocking boto3 (DynamoDB) and httpx (Langfuse) queries. **This is itself an actionable fix item.**

## Source Data

### DynamoDB Feedback

**Not collected** — see Data Collection Gaps above.

### CloudWatch Errors

#### `/eagle/ecs/backend-dev`

**93 total error/warning records** in 24h (21,500 total records scanned):

| Category | Count | Time Range | Severity |
|----------|-------|------------|----------|
| OTel OTLP Export 401 Unauthorized | 85 | 2026-03-31 18:31–20:47 UTC | ACTIONABLE |
| Bedrock AccessDeniedException (knowledge_search) | 8 | 2026-03-31 18:31–20:31 UTC | ACTIONABLE |

**Error 1: OTel OTLP Span Export — 401 Unauthorized** (85 occurrences)

```json
{
  "level": "ERROR",
  "logger": "opentelemetry.exporter.otlp.proto.http.trace_exporter",
  "msg": "Failed to export span batch code: 401, reason: Unauthorized"
}
```

- **Source**: `opentelemetry.exporter.otlp.proto.http.trace_exporter`
- **Log stream**: `backend/eagle-backend/049a1688cd554ade8d5466ad1f60483c` (and `edc367671f5a4e9ba4252f4c2575e0d2`)
- **Impact**: All OTel trace spans are being dropped. Langfuse observability data is lost.
- **Root cause**: The OTLP exporter uses Basic auth with Langfuse public/secret keys. A 401 means the credentials are invalid, expired, or misconfigured in the ECS task environment.
- **Relevant code**: `server/app/strands_agentic_service.py:82-149` (`_ensure_langfuse_exporter()`)

**Error 2: Bedrock AccessDeniedException — knowledge_search AI ranking** (8 occurrences)

```json
{
  "level": "WARNING",
  "logger": "eagle.knowledge_tools",
  "session_id": "c11ae897-65db-4001-88f9-fb6701ceb797",
  "msg": "knowledge_search AI ranking failed, falling back: An error occurred (AccessDeniedException) when calling the Converse operation: User: arn:aws:sts::695681773636:assumed-role/eagle-app-role-dev/... is not authorized to perform: bedrock:InvokeModel on resource: arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-haiku-20240307-v1:0 because no identity-based policy allows the bedrock:InvokeModel action"
}
```

- **Source**: `eagle.knowledge_tools`
- **Sessions affected**: 2 (`c11ae897-65db-4001-88f9-fb6701ceb797`, `adca241b-5a4b-463c-837e-a4c91da5f7db`)
- **Impact**: Knowledge search falls back to non-AI ranking, degrading document relevance for users.
- **Root cause**: IAM policy mismatch. The CDK core-stack grants `bedrock:InvokeModel` for `anthropic.claude-haiku-4-5-20251001-v1:0` (Haiku 4.5), but the error shows the code is calling `anthropic.claude-3-haiku-20240307-v1:0` (Haiku 3.0). Either the `KNOWLEDGE_SEARCH_MODEL` env var is overridden in the ECS task to the old model, or there's a secondary code path using the legacy model ID.
- **Relevant code**: `server/app/tools/knowledge_tools.py:285-287` (model ID config), `infrastructure/cdk-eagle/lib/core-stack.ts:145-167` (IAM policy)

#### `/eagle/ecs/frontend-dev`

**0 errors** — 0 records scanned (no frontend log activity in window).

#### `/eagle/app`

**0 errors** — 0 records scanned (no app log activity in window).

### Langfuse Trace Errors

**Not collected** — see Data Collection Gaps above.

## Cross-Reference Analysis

### Session Correlation Map

Cross-referencing is limited to CloudWatch-only data due to DynamoDB/Langfuse gaps.

| Session ID | CW Errors | Feedback | Langfuse |
|------------|-----------|----------|----------|
| `c11ae897-65db-4001-88f9-fb6701ceb797` | 5x AccessDeniedException (knowledge_search) | N/A | N/A |
| `adca241b-5a4b-463c-837e-a4c91da5f7db` | 3x AccessDeniedException (knowledge_search) | N/A | N/A |

### Error Pattern Clusters

| Cluster | CloudWatch Signal | Langfuse Signal | Feedback Signal |
|---------|------------------|-----------------|-----------------|
| **OTel/Observability** | 85x OTLP 401 Unauthorized | N/A | N/A |
| **IAM/Bedrock** | 8x AccessDeniedException on Haiku 3.0 | N/A | N/A |
| **CI/Tooling** | N/A (settings.json hook) | N/A | N/A |

### Trend Analysis

- **OTel 401 errors** are concentrated in a ~30-minute burst (20:23–20:47 UTC) plus an earlier cluster at 18:31–18:45 UTC. These correlate with ECS task container IDs, suggesting the errors fire on every span export batch (every ~5 seconds) while the task is active.
- **Bedrock AccessDeniedException** fires only during knowledge_search tool invocations — 2 distinct sessions triggered it, consistent with active user queries.
- **Traffic pattern**: Stable ~720 records/hour with a 3.4x spike during 20:00–21:00 UTC (likely active testing or usage).
- **No escalation trend**: Errors are steady-state, not worsening. The OTel issue has persisted since at least 18:31 UTC.

## Prioritized Issue List

| # | Issue | Severity | Score | Sources | Sessions | Priority |
|---|-------|----------|-------|---------|----------|----------|
| 1 | Bedrock IAM: knowledge_search Haiku 3.0 AccessDenied | ACTIONABLE | 4 | CW | 2 | **P1** |
| 2 | OTel OTLP Export 401 Unauthorized — trace data loss | ACTIONABLE | 3 | CW | N/A (infra) | **P2** |
| 3 | Broken .claude/settings.json hook blocks CI triage | ACTIONABLE | 3 | CI | N/A (tooling) | **P2** |

### Severity Scoring Detail

**Issue 1 — Bedrock AccessDeniedException (P1, score 4)**
- User-facing: 2 (degrades search quality silently — falls back to basic ranking)
- Frequency: 1 (8 occurrences in 2 sessions)
- Cross-source: 0 (CW only — DynamoDB/Langfuse unavailable)
- Error severity: 1 (ACTIONABLE per Known Patterns: IAM missing permission)

**Issue 2 — OTel OTLP 401 (P2, score 3)**
- User-facing: 0 (no direct user impact — observability loss only)
- Frequency: 2 (85 occurrences, continuous)
- Cross-source: 0 (CW only)
- Error severity: 1 (ACTIONABLE — observability data being lost)

**Issue 3 — Broken hook (P2, score 3)**
- User-facing: 0 (CI/tooling only)
- Frequency: 2 (blocks every Bash command)
- Cross-source: 0 (N/A)
- Error severity: 1 (ACTIONABLE — prevents CI triage from collecting 2/3 data sources)

## Noise Report

| Pattern | Count | Classification | Justification |
|---------|-------|----------------|---------------|
| OTel `Failed to detach context` | 0 | Noise | Not observed in this window |
| `DeprecationWarning: datetime.utcnow` | 0 | Noise | Not observed |
| `ThrottlingException` (Bedrock) | 0 | Warning | Not observed |
| `ModelNotReadyException` (cold start) | 0 | Noise | Not observed |
| `MemoryStore is not designed for production` | 0 | Warning | Not observed |

No noise items were found — all 93 matched records are actionable errors.
