# EAGLE Triage Report

**Date**: 2026-04-14
**Environment**: dev
**Window**: 24h
**Tenant**: default-dev
**Mode**: Full
**Sources**: CloudWatch Logs (dev) | DynamoDB Feedback (UNAVAILABLE) | Langfuse Traces (UNAVAILABLE)

## Executive Summary

The dev backend is experiencing **two critical IAM permission gaps** that break semantic search and observability. The `eagle-app-role-dev` IAM role is missing `bedrock:InvokeModel` permission for the `amazon.titan-embed-text-v2:0` embeddings model, causing all semantic search queries to fail silently. Simultaneously, Langfuse OTLP authentication is failing with HTTP 401, meaning no traces are being exported for observability. Additionally, the circuit breaker for `us.anthropic.claude-sonnet-4-6` has tripped repeatedly (140+ failures), indicating systemic Bedrock model availability issues. Of 33,534 log records scanned, 328 matched error patterns (466 including warnings).

## Data Collection Gaps

> **DynamoDB Feedback** and **Langfuse Traces** could not be queried in this CI run. The `.claude/settings.json` has a `PreToolUse` hook with a hardcoded Windows path (`C:/Users/blackga/Desktop/eagle/sm_eagle/.claude/hooks/pre_tool_use.py`) that fails on the Linux CI runner, blocking all Bash tool calls. This prevents running Python/boto3 scripts for DynamoDB queries and Langfuse API calls. Cross-reference analysis is limited to CloudWatch-only data.
>
> **Fix**: Change the hook command in `.claude/settings.json` from the absolute Windows path to a relative path: `python .claude/hooks/pre_tool_use.py`

## Source Data

### DynamoDB Feedback

**Status**: UNAVAILABLE (Bash blocked by Windows hook in CI)

No feedback data could be collected. This gap means user-reported bugs, thumbs-down signals, and session IDs for cross-referencing are missing from this report.

### CloudWatch Errors

**Log groups queried:**
- `/eagle/ecs/backend-dev` — 33,534 records scanned, 328 error matches, 466 warning+error matches
- `/eagle/ecs/frontend-dev` — 10 records scanned, 0 error matches (CLEAN)
- `/eagle/app` — 0 records scanned, 0 error matches (CLEAN/EMPTY)

#### Error Breakdown by Logger (466 total)

| Level | Logger | Count | Category |
|-------|--------|-------|----------|
| WARNING | eagle.strands_agent | 156 | Circuit breaker trips |
| ERROR | opentelemetry.context | 32 | OTel detach (NOISE) |
| WARNING | eagle.document_generation | 29 | Document gen warnings |
| WARNING | eagle.knowledge_tools | 28 | Embed AccessDenied |
| WARNING | eagle.web_fetch | 20 | SSL/DNS (test env) |
| WARNING | eagle.template_service | 19 | Template warnings |
| ERROR | eagle.telemetry.langfuse_client | 16 | Langfuse auth failure |
| ERROR | eagle.strands_agent | 16 | Service tool failures |
| INFO | strands.event_loop | 13 | Max tokens recovery |
| WARNING | eagle.session_preloader | 11 | Session preload issues |
| WARNING | eagle.teams_notifier | 11 | Notification failures |
| WARNING | botocore.tokens | 8 | SSO token warnings |
| WARNING | app.streaming_routes | 8 | Stream warnings |
| WARNING | botocore.credentials | 8 | Credential warnings |
| ERROR | opentelemetry.exporter.otlp | 6 | OTLP export failures |
| WARNING | eagle.packages | 6 | Package warnings |
| ERROR | app.routers.documents | 5 | Document API errors |
| ERROR | eagle.knowledge_tools | 4 | Knowledge tool errors |
| ERROR | eagle | 4 | General errors |
| ERROR | app.feedback_store | 4 | Feedback persistence errors |
| ERROR | eagle.bedrock_document_parser | 3 | Doc parsing errors |
| WARNING | eagle.error_webhook | 3 | Webhook failures |
| ERROR | eagle.document_service | 3 | Doc service errors |
| ERROR | app.streaming_routes | 2 | Stream errors |

#### Key Error Details

**1. Bedrock Embeddings AccessDeniedException (28 occurrences)**
```
embed_text failed: An error occurred (AccessDeniedException) when calling the InvokeModel
operation: User: arn:aws:sts::695681773636:assumed-role/eagle-app-role-dev/... is not
authorized to perform: bedrock:InvokeModel on resource:
arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0
```
- **Session**: `cb3e5a3c-3c59-47c6-9d76-a5e4f74dc824`
- **Tenant**: `dev-tenant`
- **Timestamps**: 06:47 - 08:25 UTC (recurring across multiple interactions)
- **Impact**: Semantic search completely broken; `exec_semantic_search: embedding failed, skipping`

**2. Langfuse OTLP Auth Failure (22 occurrences across 3 loggers)**
```
[EAGLE] Langfuse OTLP auth FAILED (401) — exporter NOT registered.
Check LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY.
```
- **First seen**: 06:47:14 UTC
- **Impact**: No observability traces exported to Langfuse

**3. Circuit Breaker Trips (156 occurrences)**
```
circuit_breaker: us.anthropic.claude-sonnet-4-6 -> OPEN (failures=140, threshold=100)
```
- **Models affected**: `us.anthropic.claude-sonnet-4-6`, `us.anthropic.claude-sonnet-4-20250514-v1:0`
- **Peak failures**: 140 (threshold: 100)
- **Note**: Some entries with `threshold=1` are from unit tests (expected behavior)
- **Time**: Concentrated burst at 07:51:07 UTC (test run)

**4. Web Search AccessDeniedException (1 occurrence)**
```
web_search ClientError [AccessDeniedException]: An error occurred (AccessDeniedException)
when calling the Converse operation: Not authorized
```
- **Impact**: Web search fallback path broken

**5. Document Service Errors (11 occurrences across 3 loggers)**
- `app.routers.documents`: 5 errors
- `eagle.document_service`: 3 errors
- `eagle.bedrock_document_parser`: 3 errors
- `eagle.document_generation`: 29 warnings

**6. Test Results**
```
Saved test run 2026-04-14T06-36-40: 1495 passed, 37 failed
```

### Langfuse Trace Errors

**Status**: UNAVAILABLE (Bash blocked by Windows hook in CI)

## Cross-Reference Analysis

### Session Correlation Map

Cross-referencing is limited to CloudWatch data only (DynamoDB and Langfuse unavailable).

| Session ID | CW Errors | Categories |
|------------|-----------|------------|
| `cb3e5a3c-3c59-47c6-9d76-a5e4f74dc824` | 60+ | Embed AccessDenied, OTel detach, Langfuse auth, web fetch |
| `test-tenant#advanced#test-user#sess-obs-001` | 1 | S3 upload failed (test) |

Session `cb3e5a3c-3c59-47c6-9d76-a5e4f74dc824` is the primary production session with multiple correlated failures — embeddings, Langfuse, and OTel issues all occurring in the same session context.

### Error Pattern Clusters

| Cluster | Signal | Count | Root Cause |
|---------|--------|-------|------------|
| **IAM/Permissions** | Bedrock InvokeModel AccessDenied for Titan Embed | 28 | Missing model ARN in CDK core-stack IAM policy |
| **Observability** | Langfuse 401 + OTLP export failures | 22 | Invalid/expired Langfuse credentials in ECS task |
| **Model Availability** | Circuit breaker OPEN for Sonnet 4.6 | 156 | Bedrock throttling or model availability (mostly from test burst) |
| **OTel Noise** | Failed to detach context | 32 | Known async context issue (NOISE) |
| **Web Tools** | SSL cert + DNS + AccessDenied | 24 | Test env (SSL/DNS) + missing Converse IAM action |
| **Documents** | Generation + parsing + routing errors | 40 | Multiple doc pipeline issues |

### Trend Analysis

- **Error concentration**: Bulk of circuit breaker errors at 07:51 UTC correspond to a test run execution, not organic user traffic
- **Persistent IAM gap**: Embeddings AccessDenied appears across multiple ECS tasks (different task IDs in assumed-role ARN) indicating a systemic CDK/IAM issue, not a transient problem
- **Langfuse auth**: Single occurrence at startup suggests the credentials are wrong at container boot time and never recover
- **Frontend clean**: Zero errors in frontend-dev logs — the UI layer is stable

## Prioritized Issue List

| # | Issue | Severity | Score | Sources | Sessions |
|---|-------|----------|-------|---------|----------|
| 1 | Bedrock Embeddings IAM — missing `amazon.titan-embed-text-v2:0` | **P0** | 7 | CW | 1+ |
| 2 | Langfuse OTLP auth failure (401) — no traces exported | **P1** | 5 | CW | all |
| 3 | CI hook path — Windows-only path blocks Linux CI Bash | **P1** | 5 | CI | N/A |
| 4 | Circuit breaker saturation — Sonnet 4.6 hitting 140 failures | **P1** | 4 | CW | 1+ |
| 5 | Web search Converse AccessDeniedException | **P2** | 3 | CW | 1 |
| 6 | Document pipeline errors (router + service + parser) | **P2** | 3 | CW | N/A |
| 7 | Feedback store errors | **P2** | 2 | CW | N/A |
| 8 | SSO token / credential warnings | **P3** | 1 | CW | N/A |

### Composite Severity Scoring

| Issue | User-Facing (0-3) | Frequency (0-2) | Cross-Source (0-2) | Severity (0-1) | Total |
|-------|-------------------|-----------------|-------------------|----------------|-------|
| Embeddings IAM | 3 (breaks search) | 2 (28 hits) | 1 (CW only*) | 1 (ACTIONABLE) | **7** |
| Langfuse auth | 2 (no observability) | 2 (22 hits) | 0 (CW only) | 1 (ACTIONABLE) | **5** |
| CI hook path | 2 (blocks triage) | 2 (every run) | 0 | 1 (ACTIONABLE) | **5** |
| Circuit breaker | 1 (mostly tests) | 2 (156 hits) | 0 | 1 (ACTIONABLE) | **4** |
| Web search IAM | 1 (partial feature) | 1 (1 hit) | 0 | 1 (ACTIONABLE) | **3** |

*Cross-source scores degraded because DynamoDB/Langfuse sources were unavailable

## Noise Report

| Pattern | Count | Justification |
|---------|-------|---------------|
| OTel `Failed to detach context` | 32 | Known async context issue, handled via Langfuse parent wrapper. Does not affect trace integrity. |
| `strands.event_loop._recover_message_on_max_tokens_reached` | 21 | Normal Strands SDK behavior — token recovery is working as designed. |
| `eagle.web_fetch` SSL/DNS errors for `example.com` | 20 | Test environment URLs — not real user traffic. |
| `eagle.test_results` warnings | 4 | Test run reporting — informational. |
| Circuit breaker threshold=1 entries | ~10 | Unit test circuit breaker with low threshold — expected. |
