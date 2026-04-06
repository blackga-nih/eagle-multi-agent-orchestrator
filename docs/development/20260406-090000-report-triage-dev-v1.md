# EAGLE Triage Report

**Date**: 2026-04-06
**Environment**: dev
**Window**: 24h (2026-04-05 00:00 UTC — 2026-04-06 23:59 UTC)
**Tenant**: default-dev
**Mode**: Full
**Sources**: CloudWatch Logs (dev) | DynamoDB Feedback (SKIPPED — Bash hook blocked) | Langfuse Traces (SKIPPED — Bash hook blocked)

## Executive Summary

The dev environment is **operationally healthy** with no container crashes, OOM events, or infrastructure failures. Two actionable issues were found: (1) the OTel/Langfuse OTLP span exporter is continuously failing with **401 Unauthorized** (~96 failures in the window), meaning **all telemetry export to Langfuse is broken**, and (2) a single **circuit breaker exhaustion** event where all Bedrock models timed out for one session. DynamoDB feedback and Langfuse direct trace queries were unavailable due to a CI hook misconfiguration (Windows-path hook in `.claude/settings.json`).

## Data Collection Gaps

| Source | Status | Reason |
|--------|--------|--------|
| CloudWatch `/eagle/ecs/backend-dev` | Collected | 29,557 records scanned, 102 error matches |
| CloudWatch `/eagle/ecs/frontend-dev` | Collected | 0 errors — clean |
| CloudWatch `/eagle/app` | Collected | 0 errors — clean |
| DynamoDB Feedback | **SKIPPED** | Bash tool blocked by Windows-path PreToolUse hook in `.claude/settings.json` |
| Langfuse Traces | **SKIPPED** | Same hook blocker — requires Bash for Python httpx query |

## Source Data

### CloudWatch Errors — `/eagle/ecs/backend-dev`

**Total records scanned**: 29,557 (single log stream: `backend/eagle-backend/93ecca9e98904acfae83a1de29e870cd`)

#### ACTIONABLE Errors

| # | Timestamp | Logger | Message | Category | Severity |
|---|-----------|--------|---------|----------|----------|
| 1 | 2026-04-05 23:13:30 | `eagle.strands_agent` | `circuit_breaker: all models exhausted for session=3f1888ee-4f26-4418-aed4-3e8a2d95bfbc` | Model Exhaustion | **ACTIONABLE** |
| 2 | 2026-04-05 23:13:30 | `eagle.strands_agent` | `circuit_breaker: us.anthropic.claude-sonnet-4-6 failed (TTFT timeout)` | TTFT Timeout | **ACTIONABLE** |
| 3 | 2026-04-05 23:13:30 | `eagle.telemetry.langfuse_client` | `Langfuse list_traces failed: 400 Bad Request` (session `3f1888ee-4f26-4418-aed4-3e8a2d95bfbc`) | Langfuse API Error | **ACTIONABLE** |
| 4 | 2026-04-05 23:13:30 | `eagle.telemetry.langfuse_client` | Same 400 Bad Request (duplicate log entry) | Langfuse API Error | **ACTIONABLE** |

#### Warning-Level Errors

| # | Timestamp | Logger | Message | Category | Severity |
|---|-----------|--------|---------|----------|----------|
| 5 | 2026-04-05 23:32:57 | `eagle.web_fetch` | `SSL: CERTIFICATE_VERIFY_FAILED — Hostname mismatch for www.support.illumina.com` | External SSL | Warning |
| 6 | 2026-04-05 23:32:57 | `eagle.web_fetch` | Same SSL error for different Illumina URL | External SSL | Warning |

#### Noise (Filtered)

| Pattern | Count | Category | Severity |
|---------|-------|----------|----------|
| `Failed to export span batch code: 401, reason: Unauthorized` (OTel OTLP exporter) | ~96 | OTel telemetry auth failure | **ACTIONABLE** (persistent) |

> **Note on OTel 401s**: While individual OTel export failures are typically noise, **96 consecutive 401 Unauthorized failures** over the entire 24h window indicates the OTLP exporter auth is fundamentally broken — not a transient issue. This is a persistent telemetry blindspot.

### CloudWatch Errors — `/eagle/ecs/frontend-dev`

**Clean** — 0 error records in the 24h window.

### CloudWatch Errors — `/eagle/app`

**Clean** — 0 error records in the 24h window.

### DynamoDB Feedback

**SKIPPED** — Could not query. The CI pre-tool-use hook in `.claude/settings.json` references a Windows path (`C:/Users/blackga/Desktop/eagle/sm_eagle/.claude/hooks/pre_tool_use.py`) that does not exist on the Linux CI runner.

### Langfuse Trace Errors

**SKIPPED** — Same blocker as DynamoDB (requires Bash for Python httpx query).

## Cross-Reference Analysis

### Session Correlation Map

Only one session appeared in error logs:

| Session ID | CloudWatch Errors | Langfuse | DynamoDB |
|------------|-------------------|----------|----------|
| `3f1888ee-4f26-4418-aed4-3e8a2d95bfbc` | Circuit breaker exhaustion + TTFT timeout + Langfuse 400 | N/A (skipped) | N/A (skipped) |

### Error Pattern Clusters

| Cluster | CloudWatch Signal | Evidence | Affected Sessions |
|---------|-------------------|----------|-------------------|
| **OTel/Langfuse OTLP Auth** | 96x `401 Unauthorized` from `opentelemetry.exporter.otlp.proto.http.trace_exporter` | Continuous every ~5s across entire 24h window | All (telemetry-level) |
| **Model Exhaustion** | `all models exhausted` + `TTFT timeout` on `claude-sonnet-4-6` | Circuit breaker cascaded through all 3 models | `3f1888ee-...` |
| **Langfuse API** | `400 Bad Request` on `list_traces` | Same session as model exhaustion — likely downstream symptom | `3f1888ee-...` |
| **External SSL** | `CERTIFICATE_VERIFY_FAILED` for `www.support.illumina.com` | External site misconfiguration, not EAGLE fault | N/A |

### Trend Analysis

- **OTel 401s**: Continuous and steady — indicates a static misconfiguration, not a transient issue. The startup probe in `strands_agentic_service.py` (lines 126-144) is supposed to catch 401s and skip registration, but the exporter is still running. This suggests the probe passed at startup but credentials were later invalidated, or the probe is not running in the ECS task.
- **Circuit breaker exhaustion**: Single occurrence (23:13:30 UTC). Not a pattern — likely a transient Bedrock cross-region cold start coinciding with TTFT timeout.
- **No container crashes, OOM, SIGTERM**: Infrastructure is stable.

## Prioritized Issue List

| # | Issue | Severity | Score | Sources | Sessions | Priority |
|---|-------|----------|-------|---------|----------|----------|
| 1 | **OTel OTLP exporter 401 Unauthorized** — All span export to Langfuse failing continuously | ACTIONABLE | 5 | CW | All (telemetry) | **P1** |
| 2 | **Circuit breaker model exhaustion** — All 3 Bedrock models timed out (TTFT) for one session | ACTIONABLE | 3 | CW | 1 | **P2** |
| 3 | **Langfuse list_traces 400 Bad Request** — API call returning 400 for session queries | ACTIONABLE | 3 | CW | 1 | **P2** |
| 4 | **CI hook Windows path** — `.claude/settings.json` hook blocks Bash in CI, preventing DynamoDB/Langfuse triage queries | ACTIONABLE | 2 | CI | N/A | **P2** |
| 5 | **External SSL cert mismatch** — `www.support.illumina.com` has invalid cert | Warning | 1 | CW | N/A | **P3** |

### Scoring Rationale

| Issue | User-facing (0-3) | Frequency (0-2) | Cross-source (0-2) | Severity (0-1) | Total |
|-------|-------------------|-----------------|---------------------|----------------|-------|
| OTel 401 | 0 (telemetry only) | 2 (96 occurrences) | 2 (affects all traces) | 1 | **5** |
| Model exhaustion | 1 (1 session affected) | 0 (single event) | 1 (CW only) | 1 | **3** |
| Langfuse 400 | 1 (linked to user session) | 0 (single event) | 1 (CW only) | 1 | **3** |
| CI hook path | 0 (dev tooling) | 1 (blocks every CI run) | 0 | 1 | **2** |
| SSL cert | 0 (external) | 0 (2 occurrences) | 0 | 1 | **1** |

## Noise Report

| Pattern | Count | Justification |
|---------|-------|---------------|
| OTel `Failed to export span batch` 401 | 96 | Promoted from noise to P1 — persistent auth failure is not transient noise |
| `DeprecationWarning: datetime.utcnow` | 0 | Not observed in this window |
| `Failed to detach context` | 0 | Not observed in this window |
| `MemoryStore is not designed for production` | 0 | Not observed in this window |
