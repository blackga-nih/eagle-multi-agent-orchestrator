# EAGLE Triage Report

**Date**: 2026-04-13
**Environment**: dev
**Window**: 24h
**Tenant**: default-dev
**Mode**: Full
**Sources**: CloudWatch Logs (dev) | DynamoDB Feedback (UNAVAILABLE) | Langfuse Traces (UNAVAILABLE)

## Executive Summary

The dev environment is **healthy** with no critical production errors in the last 24 hours. The ECS container (`/eagle/ecs/backend-dev`) logged 0 errors on its Fargate log stream — a second consecutive clean day. Two issues surfaced on the `localhost` log stream (local dev machine): (1) a **document validation warning** where the AI agent passed `"$1.8"` as `estimated_value` for a SOW document, which Pydantic's float parser rejected because `BaseDocumentData` lacks a `field_validator` to strip currency symbols, and (2) **10 SSO token expired entries** from a developer's Windows machine. Yesterday's Bedrock keepalive slow warnings (6 entries) did not recur. The persistent CI hook path issue (now **3 consecutive days**) continues to block DynamoDB and Langfuse data collection.

**Data Source Gaps**: DynamoDB feedback and Langfuse traces could not be queried because the Bash tool is blocked by a PreToolUse hook in `.claude/settings.json` that references a Windows-only path (`C:/Users/blackga/Desktop/eagle/sm_eagle/.claude/hooks/pre_tool_use.py`). Both background agents confirmed the same hook error. Langfuse dev credentials are configured and valid.

## Source Data

### DynamoDB Feedback

**Status**: UNAVAILABLE — Bash tool blocked by PreToolUse hook with Windows-only path in `.claude/settings.json`. Background agent confirmed: `python: can't open file '/home/runner/work/sm_eagle/sm_eagle/C:/Users/blackga/Desktop/eagle/sm_eagle/.claude/hooks/pre_tool_use.py': [Errno 2] No such file or directory`.

### CloudWatch Errors

#### `/eagle/ecs/backend-dev` — 15 error records matched (26,866 scanned)

**Log Stream Breakdown:**

| Log Stream | Matched | Description |
|------------|---------|-------------|
| `localhost` | 15 | Local dev server logs forwarded to CloudWatch |
| ECS Fargate container | 0 | Production container — clean |

**ECS Container Errors: 0**

No errors detected on the production ECS Fargate container. Second consecutive day with zero ECS errors.

**Localhost Issues: 15 entries**

**Issue 1: Document Validation — Currency String Parsing (3 entries)**

| Timestamp | Logger | Level | Detail |
|-----------|--------|-------|--------|
| 2026-04-13 07:44:42.930 | `eagle.ai_document_schema` | WARNING | `Document data validation warning for sow: 1 validation error for SowDocumentData estimated_value Input should be a valid number, unable to parse string as a number [type=float_parsing, input_value='$1.8', input_type=str]` |
| 2026-04-13 07:44:42.931 | `eagle.document_generation` | WARNING | `Document payload warnings: [validation error for estimated_value...]` |
| 2026-04-13 07:44:42.931 | `eagle.ai_document_schema` | INFO | `Document payload normalized with warnings: doc_type=sow` |

**Root cause**: `BaseDocumentData.estimated_value` is typed as `Optional[float]` (line 517 in `server/app/ai_document_schema.py`) with no `field_validator` to strip currency symbols. When the AI agent passes `"$1.8"` (a currency-formatted string), Pydantic's float parser rejects it. The `strands_agentic_service.py:989` path already has `str(...).replace(",", "").replace("$", "")` cleanup, but this doesn't protect the Pydantic model validation path.

**Impact**: Non-critical — document generation continues with warnings (the system gracefully falls back). However, the estimated_value field is silently dropped, which may affect downstream calculations (threshold tier, approval chain, IGCE generation).

**Issue 2: SSO Token Expired — Local Dev (10 entries)**

| Timestamp | Logger | Level | Detail |
|-----------|--------|-------|--------|
| 2026-04-13 02:13:43.094–.453 | `botocore.tokens` / `botocore.credentials` | WARNING | `SSO token refresh attempt failed` / `Refreshing temporary credentials failed during mandatory refresh period` |

10 entries in rapid succession (360ms window) — all with Windows paths in stack traces (`C:\Users\blackga\AppData\...`). This is a developer's local SSO session expiry, not the ECS service.

**Root cause**: Developer `blackga`'s AWS SSO token expired while the local backend was running. The logs were forwarded to the CloudWatch log group via the `localhost` log stream.

**Impact**: None on production. Local-only.

**Issue 3: Knowledge Fetch False Positives (2 entries)**

| Timestamp | Logger | Level | Detail |
|-----------|--------|-------|--------|
| 2026-04-13 07:36:36 | `eagle.knowledge_tools` | INFO | `knowledge_fetch: key=...NIH_LISTSERV_Formal_Source_Selection_Common_Error_2018.txt` |
| 2026-04-13 07:29:35 | `eagle.knowledge_tools` | INFO | `knowledge_fetch: key=...NIH_LISTSERV_Formal_Source_Selection_Common_Error_2018.txt` |

These are INFO-level logs that matched the error filter because the S3 key filename contains "Error". Not actual errors.

**No Critical Patterns Detected (secondary scan):**

| Pattern Searched | Result |
|-----------------|--------|
| ThrottlingException | Not found |
| ModelNotReadyException | Not found |
| OOM / OutOfMemory | Not found |
| SIGTERM / SIGKILL | Not found |
| Task stopped / Essential container | Not found |
| MemoryStore warning | Not found |
| Failed to detach context (OTel) | Not found |
| DeprecationWarning | Not found |

#### `/eagle/ecs/frontend-dev` — 0 records matched (0 scanned)

No errors detected. No log events in the 24h window.

#### `/eagle/app` — 0 records matched (0 scanned)

No errors detected. No log events in the 24h window.

### Langfuse Trace Errors

**Status**: UNAVAILABLE — Background agent confirmed Bash blocked by same PreToolUse hook error. Langfuse dev keys are configured (`pk-lf-47021a72...`, project `cmmsqvi2406aead071t0zhl7f`, host `https://us.cloud.langfuse.com`).

## Cross-Reference Analysis

### Session Correlation Map

No session-level correlation possible — DynamoDB feedback and Langfuse traces unavailable. The document validation warning does not include a session_id in the matched log entries. The SSO token expiry affects local dev only (no ECS sessions).

### Error Pattern Clusters

| Cluster | CloudWatch Signal | Langfuse Signal | Feedback Signal |
|---------|------------------|-----------------|-----------------|
| **Data Quality** | `$1.8` float_parsing validation warning for SOW estimated_value | N/A | N/A |
| **IAM/SSO (local)** | 10x SSO token expired from `localhost` (Windows dev machine) | N/A | N/A |
| **CI Observability Gap** | N/A (prevents data collection for 3 consecutive days) | N/A | N/A |

### Trend Analysis

**Compared to yesterday (2026-04-12 report):**

| Issue | Yesterday | Today | Trend |
|-------|-----------|-------|-------|
| ECS container errors | 0 | 0 | **STABLE** (2nd clean day) |
| Bedrock Titan Embed AccessDeniedException | 0 (resolved 4/12) | 0 | **RESOLVED** |
| Bedrock keepalive slow warnings | 6 (Warning) | 0 | **IMPROVED** |
| SSO Token Expiry (local) | 0 | 10 | **REAPPEARED** (local dev only) |
| Document validation warning | 0 | 3 | **NEW** |
| Localhost noise total | 23 | 15 | **REDUCED** |
| CI hook path blocker | Present (2nd day) | Present (3rd day) | **PERSISTENT** |
| Frontend errors | 0 | 0 | Stable |
| App log group | 0 events | 0 events | Stable |

**Key trends:**
1. **Production is clean**: Two consecutive days with zero ECS container errors. The Bedrock IAM fix from 4/11 is holding.
2. **Bedrock cold starts resolved**: Yesterday's 6 keepalive slow warnings did not recur — model may be staying warm with higher traffic.
3. **New document validation bug**: The `estimated_value` currency parsing issue is a code gap — the Pydantic model doesn't have the same `$`/`,` stripping that `strands_agentic_service.py:989` uses.
4. **CI observability gap worsening**: 3rd day without DynamoDB/Langfuse data. This is the longest continuous gap and reduces triage confidence.
5. **Localhost noise trending down**: 15 matches (down from 23 yesterday, 88+ on 4/11).

## Prioritized Issue List

| # | Issue | Composite Score | Priority | Sources | Sessions Affected |
|---|-------|----------------|----------|---------|-------------------|
| 1 | **CI hook Windows path blocks DynamoDB + Langfuse triage** — `.claude/settings.json` PreToolUse hook references `C:/Users/blackga/...`, 3rd consecutive day | 4 (user-facing=1, freq=2, cross-source=0, severity=1) | **P1** | CI | All CI triage runs |
| 2 | **Document estimated_value currency parsing** — `BaseDocumentData.estimated_value: Optional[float]` lacks `field_validator` to strip `$`/`,` before Pydantic float parsing | 2 (user-facing=0, freq=1, cross-source=0, severity=1) | **P2** | CW | Unknown |
| 3 | **SSO token expired (local dev)** — Developer `blackga`'s SSO expired at 02:13 UTC, 10 entries on `localhost` log stream | 1 (user-facing=0, freq=1, cross-source=0, severity=0) | **P3** | CW | N/A (local dev) |

**No P0 issues detected.**

## Noise Report

| Category | Count | Justification |
|----------|-------|---------------|
| Knowledge fetch filename false positives | 2 | INFO-level logs where S3 key contains "Error" in document filename |
| SSO token expired (classified as local noise) | 10 | All from `localhost` log stream with Windows paths — developer machine, not ECS |
| Frontend errors | 0 | Clean — no events in log group |
| App log group | 0 | No events in time window |
| OTel detach / DeprecationWarning / cold starts | 0 | None detected in secondary scan |
