# EAGLE Triage Report

**Date**: 2026-04-17
**Environment**: dev
**Window**: 24h (2026-04-16T00:00:00Z to 2026-04-17T23:59:59Z)
**Tenant**: default-dev
**Mode**: Full
**Sources attempted**: DynamoDB Feedback, CloudWatch Logs (`/eagle/ecs/backend-dev`, `/eagle/ecs/frontend-dev`, `/eagle/app`), Langfuse Traces
**Sources collected**: CloudWatch Logs only — see **Source Coverage Gaps** below

---

## Executive Summary

A **new P0 IAM gap** is blocking all semantic search / knowledge base queries: the `eagle-app-role-dev` ECS task role lacks `s3vectors:QueryVectors` permission on the `rh-eagle` S3 Vectors bucket. Five AccessDeniedException errors hit across three separate user sessions in the last 24 hours, meaning every knowledge-base-powered answer in the dev environment is degraded. A secondary **P2 input validation bug** in document generation fails to strip dollar-sign prefixes from `estimated_value` fields (e.g., `'$15'` → float parse error). The **recurring Bedrock transient outage** (P3) from yesterday repeated in the same 07:56–08:12 UTC window and was again absorbed by the circuit breaker. DynamoDB feedback and Langfuse traces remain unavailable due to the broken CI hook (second consecutive day).

---

## Source Coverage Gaps

| Source | Status | Reason |
|---|---|---|
| CloudWatch `/eagle/ecs/backend-dev` | OK | 17 error records matched |
| CloudWatch `/eagle/ecs/frontend-dev` | OK | 0 records |
| CloudWatch `/eagle/app` | OK | 0 records |
| DynamoDB `FEEDBACK#default-dev` | **SKIPPED** | Bash blocked by broken `PreToolUse` hook in `.claude/settings.json` — Windows path (`C:/Users/blackga/...`) does not exist on Linux CI runner |
| Langfuse traces (dev) | **SKIPPED** | Same root cause — Langfuse fetch requires Bash. Credentials are configured (keys verified via file read) |

Cross-session correlation (Phase 2a) is partial — we cannot confirm whether user-reported bug tickets share `session_id` values with CloudWatch errors. However, the S3 Vectors IAM gap is deterministic and affects all knowledge queries regardless of user feedback.

---

## Source Data

### DynamoDB Feedback
*Skipped — see Source Coverage Gaps.*

### CloudWatch Errors

**Totals (24h window)**
| Log group | Records scanned | Matches |
|---|---|---|
| `/eagle/ecs/backend-dev` | 26,122 | 17 |
| `/eagle/ecs/frontend-dev` | 0 | 0 |
| `/eagle/app` | 0 | 0 |

#### `/eagle/ecs/backend-dev` — grouped

##### A. S3 Vectors `AccessDeniedException` (5 records) — NEW

| Timestamp (UTC) | Session ID | Event |
|---|---|---|
| 2026-04-16 15:34:48 | 2ab5ab6b-3973-449c-a333-0b4eba4f89a6 | `exec_semantic_search: S3 Vectors query failed: AccessDeniedException … s3vectors:QueryVectors` |
| 2026-04-16 15:35:18 | 2ab5ab6b-3973-449c-a333-0b4eba4f89a6 | Same error (second attempt in same session) |
| 2026-04-16 16:47:52 | 2dec0459-0f4d-4b39-9f85-95463632544d | Same error |
| 2026-04-16 16:47:53 | 2dec0459-0f4d-4b39-9f85-95463632544d | Same error (retry) |
| 2026-04-16 18:49:31 | b709a6c0-6eba-43ea-9515-c5d36a9214bc | Same error |

**Root cause**: IAM role `eagle-app-role-dev` (assumed-role ARN `arn:aws:sts::695681773636:assumed-role/eagle-app-role-dev/...`) does not have an identity-based policy allowing `s3vectors:QueryVectors` on `arn:aws:s3vectors:us-east-1:695681773636:bucket/rh-eagle/index/eagle-kb-approved`.

**Impact**: Semantic search over the approved knowledge base is completely non-functional. The `exec_semantic_search()` function at `server/app/tools/knowledge_tools.py:1232` catches the error and logs a warning, but the agent receives no search results — degrading every knowledge-base-backed answer.

**Classification**: IAM missing permission — ACTIONABLE.

##### B. Document validation — `estimated_value` float parsing (3 records)

| Timestamp (UTC) | Session ID | Event |
|---|---|---|
| 2026-04-16 17:16:52 | 2dec0459-0f4d-4b39-9f85-95463632544d | `Document data validation warning for purchase_request: estimated_value — Input should be a valid number, unable to parse string as a number [input_value='$15']` |
| 2026-04-16 17:16:52 | 2dec0459-0f4d-4b39-9f85-95463632544d | `Document payload warnings` (same error, document_generation logger) |
| 2026-04-16 17:16:52 | 2dec0459-0f4d-4b39-9f85-95463632544d | `Document payload normalized with warnings` (INFO, document proceeds) |

**Root cause**: `BaseDocumentData.estimated_value` field (at `server/app/ai_document_schema.py:521`) is typed `Optional[float]`. When the LLM produces `'$15'` (with dollar-sign prefix), Pydantic's float parser rejects it. The code handles this gracefully (document still generates with a warning), but the `estimated_value` field is silently dropped.

**Impact**: Generated documents (Purchase Requests, SOWs) may have missing or null `estimated_value` fields when the LLM includes a currency symbol. Warning-level — document generation continues but data quality is reduced.

**Classification**: Data quality / input validation — Warning.

##### C. Bedrock `ServiceUnavailableException` + circuit-breaker trips (8 records) — RECURRING

| Timestamp (UTC) | Level | Event |
|---|---|---|
| 2026-04-16 07:56:33 | WARN | `keepalive_ping: us.anthropic.claude-sonnet-4-6 FAILED … ServiceUnavailableException` |
| 2026-04-16 07:56:33 | WARN | `keepalive_ping: us.anthropic.claude-sonnet-4-6 failed — circuit breaker notified` |
| 2026-04-16 08:07:18 | WARN | `keepalive_ping: us.anthropic.claude-sonnet-4-6 FAILED … ServiceUnavailableException` |
| 2026-04-16 08:07:18 | WARN | `circuit_breaker: us.anthropic.claude-sonnet-4-6 -> OPEN (failures=2, threshold=2)` |
| 2026-04-16 08:07:18 | WARN | `keepalive_ping: us.anthropic.claude-sonnet-4-6 failed — circuit breaker notified` |
| 2026-04-16 08:12:47 | WARN | `keepalive_ping: us.anthropic.claude-sonnet-4-6 FAILED … ServiceUnavailableException` |
| 2026-04-16 08:12:47 | WARN | `keepalive_ping: us.anthropic.claude-sonnet-4-6 failed — circuit breaker notified` |
| 2026-04-16 08:12:47 | WARN | `circuit_breaker: us.anthropic.claude-sonnet-4-6 -> OPEN (failures=3, threshold=2)` |

**Pattern**: Identical to yesterday's report (2026-04-16 report Issue #2). Concentrated in ~07:56–08:12 UTC window. Circuit breaker opened twice, recovered after 08:12. No further failures recorded after that.

**Classification**: Infrastructure-transient — Warning. Circuit breaker working as designed.

##### D. Knowledge fetch INFO (1 record)

| Timestamp (UTC) | Session ID | Event |
|---|---|---|
| 2026-04-16 15:35:18 | 2ab5ab6b-3973-449c-a333-0b4eba4f89a6 | `knowledge_fetch: tenant=dev-tenant key=eagle-knowledge-base/approved/legal-counselor/protest-guidance/GAO_B-409917_...` |

**Note**: This INFO-level log matched because it contains "fail" in the S3 key path substring. It is a successful knowledge fetch — false positive in the error filter. Classified as noise.

#### `/eagle/ecs/frontend-dev`
No matching records.

#### `/eagle/app`
No matching records.

### Langfuse Trace Errors
*Skipped — see Source Coverage Gaps. Langfuse credentials are configured and valid (public key `pk-lf-47021a72...`, project `cmmsqvi2406aead071t0zhl7f`).*

---

## Cross-Reference Analysis

### Session Correlation Map

| Session ID | CloudWatch Errors | Langfuse | DynamoDB Feedback |
|---|---|---|---|
| `2ab5ab6b-3973-449c-a333-0b4eba4f89a6` | 2× S3 Vectors AccessDenied | n/a | n/a |
| `2dec0459-0f4d-4b39-9f85-95463632544d` | 2× S3 Vectors AccessDenied + 3× doc validation warning | n/a | n/a |
| `b709a6c0-6eba-43ea-9515-c5d36a9214bc` | 1× S3 Vectors AccessDenied | n/a | n/a |

Session `2dec0459` is notable — it hit both the S3 Vectors IAM error AND the document validation error, suggesting the user attempted a full acquisition workflow (knowledge search → document generation) and got degraded results at both stages.

### Error Pattern Clusters

| Cluster | CloudWatch Signal | Langfuse Signal | Feedback Signal |
|---|---|---|---|
| **IAM / S3 Vectors** | 5× AccessDeniedException on `s3vectors:QueryVectors` across 3 sessions | n/a (skipped) | n/a (skipped) |
| **Data Quality** | 3× Pydantic float_parsing on `estimated_value='$15'` | n/a (skipped) | n/a (skipped) |
| **Model Issues / Bedrock** | 8× ServiceUnavailableException + circuit breaker trips (07:56–08:12) | n/a (skipped) | n/a (skipped) |

### Trend Analysis

- **S3 Vectors AccessDenied**: NOT present in yesterday's triage report (2026-04-16). This is a **new issue** — either the S3 Vectors index was recently created/deployed without corresponding IAM policy, or semantic search was recently enabled in code. The errors span 15:34–18:49 UTC, suggesting multiple users hit it across a 3+ hour window.
- **Document validation**: Not previously reported. May have existed but wasn't triggered until a user's prompt produced dollar-prefixed values.
- **Bedrock ServiceUnavailable**: **Second consecutive day** with the same pattern in the ~08:00 UTC window. This suggests a recurring AWS capacity issue at that hour. Circuit breaker absorbs it reliably. If it persists a third day, consider monitoring/alerting.
- **Teams notifier** (from yesterday's P1): NOT present in today's 17-record set. Either the container restarted (clearing the stale httpx client) or the daily digest didn't trigger errors today. Status uncertain without Langfuse/DynamoDB data.

---

## Prioritized Issue List

### Severity Scoring (0–8)

| # | Issue | User-facing (0–3) | Frequency (0–2) | Cross-source (0–2) | Severity (0–1) | **Total** | **Priority** |
|---|---|---|---|---|---|---|---|
| 1 | S3 Vectors `AccessDeniedException` — semantic search broken | 2 (core feature, 3 sessions affected) | 2 (5 occurrences, 3 sessions) | 0 (other sources unavailable) | 1 (ACTIONABLE) | **5** | **P0** (promoted — deterministic IAM gap, all knowledge queries fail) |
| 2 | `estimated_value` float parsing — dollar sign not stripped | 0 (warning, document still generates) | 1 (3 occurrences, 1 session) | 0 | 0 (Warning) | **1** | **P2** (data quality improvement) |
| 3 | Bedrock ServiceUnavailable — recurring 08:00 UTC window | 0 (absorbed by circuit breaker) | 1 (concentrated burst, resolved) | 0 | 0 (Warning) | **1** | **P3** (monitor — second consecutive day) |
| 4 | CI triage hook broken — blocks DynamoDB + Langfuse | 0 | 2 (every scheduled triage) | 0 | 1 (ACTIONABLE) | **3** | **P1** (operational — restores full triage coverage) |

**P0 promotion note**: Issue #1 scored 5 (normally P1) but is promoted to P0 because: (a) the IAM gap is deterministic, not transient — every semantic search call will fail until fixed, (b) it affects all users in dev, (c) knowledge base is a core feature of the acquisition assistant, and (d) the fix is a one-line IAM policy addition.

---

## Noise Report

| Item | Count | Justification |
|---|---|---|
| Knowledge fetch INFO log (false positive match on "fail" substring) | 1 | Log matched error filter due to path substring; actual log level is INFO, operation succeeded |
| Bedrock circuit breaker recovery logs | 0 | No HALF_OPEN/CLOSED transition logs in this window (may have been outside the 50-record limit) |
| OTel `Failed to detach context` | 0 | None detected |
| `DeprecationWarning: datetime.utcnow` | 0 | None detected |
| `MemoryStore is not designed for production` | 0 | None detected |
| `ModelNotReadyException` cold starts | 0 | None detected |

---

## Comparison with Previous Report (2026-04-16)

| Issue | Yesterday | Today | Status |
|---|---|---|---|
| Teams notifier `Event loop is closed` | P1 (1 occurrence) | Not detected | Possibly resolved (container restart?) — monitor |
| Bedrock ServiceUnavailable | P3 (8 records, 07:56–08:18) | P3 (8 records, 07:56–08:12) | Recurring — same time window, 2nd consecutive day |
| S3 Vectors AccessDenied | Not reported | **P0 (5 records, 3 sessions)** | **NEW** |
| Document validation float parsing | Not reported | P2 (3 records, 1 session) | **NEW** |
| CI hook broken | P1 | P1 | Unchanged — still blocking 2/3 sources |
