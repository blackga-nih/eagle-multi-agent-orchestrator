# EAGLE Triage Report

**Date**: 2026-04-25
**Environment**: dev
**Window**: 24h (2026-04-24 00:00 UTC to 2026-04-25 23:59 UTC)
**Tenant**: default-dev
**Mode**: Full
**Sources**: CloudWatch Logs (dev) | DynamoDB Feedback (unavailable — see gaps) | Langfuse Traces (unavailable — see gaps)

## Executive Summary

The dev environment backend logged 311 error/warning records in the last 24 hours, almost entirely from the automated test/eval pipeline (CI run on 2026-04-24 ~21:17–21:56 UTC). No errors were found in frontend-dev or /eagle/app logs. Two real infrastructure issues surfaced through test execution: **(1) SSO token expiration** causing Bedrock model keepalive failures with circuit breaker at 103 failures, and **(2) IAM permission gaps** preventing knowledge search tools from accessing the `eagle-document-metadata-dev` DynamoDB table and Titan embedding model. Additionally, 5 document template types are missing, causing graceful fallback to markdown.

**Data gaps**: DynamoDB feedback and Langfuse trace queries could not be executed due to a CI tooling issue (Bash hook misconfigured for Linux — see Noise Report). This report is based on CloudWatch data only.

## Source Data

### DynamoDB Feedback

**Status**: UNAVAILABLE — Bash tool blocked by misconfigured PreToolUse hook (Windows path in `.claude/settings.json`). Unable to execute boto3 queries for feedback data.

### CloudWatch Errors

#### /eagle/ecs/backend-dev — 311 records matched, 50 returned

| # | Timestamp (UTC) | Category | Severity | Message Summary |
|---|-----------------|----------|----------|-----------------|
| 1 | 21:56:11 | SSO/IAM | ACTIONABLE | `keepalive_ping: claude-sonnet-4-5 failed — circuit breaker notified` |
| 2 | 21:56:11 | SSO/IAM | ACTIONABLE | `circuit_breaker: claude-sonnet-4-5 -> OPEN (failures=103, threshold=2)` |
| 3 | 21:56:11 | SSO/IAM | ACTIONABLE | `keepalive_ping FAILED: Token has expired and refresh failed` |
| 4 | 21:56:11 | SSO/IAM | ACTIONABLE | `Refreshing temporary credentials failed — TokenRetrievalError` |
| 5 | 21:56:11 | SSO/IAM | ACTIONABLE | `InvalidGrantException: Invalid refresh token provided` |
| 6 | 21:23:36 | IAM | ACTIONABLE | `web_search AccessDeniedException: Converse operation: Not authorized` |
| 7 | 21:18:31 | IAM | ACTIONABLE | `knowledge_search AccessDeniedException: dynamodb:Scan on eagle-document-metadata-dev` (3x) |
| 8 | 21:18:31 | IAM | ACTIONABLE | `exec_path_search AccessDeniedException: dynamodb:Scan on eagle-document-metadata-dev` |
| 9 | 21:18:31 | IAM | ACTIONABLE | `embed_text AccessDeniedException: bedrock:InvokeModel on titan-embed-text-v2:0` |
| 10 | 21:18:31 | IAM | ACTIONABLE | `exec_semantic_search: embedding failed, skipping` (2x) |
| 11 | 21:21:19 | App Bug | Warning | `Template not found for igce, falling back to markdown` (2x) |
| 12 | 21:18:57–21:21:19 | App Bug | Warning | `Template not found for sow` (2x), `acquisition_plan`, `justification`, `market_research` |
| 13 | 21:21:47 | App Bug | Warning | `triage_actions: dispatch failed status=422 body=Unprocessable` |
| 14 | 21:21:47 | S3 | Warning | `S3 NoSuchKey: eagle/test-tenant/packages/.../Acquisition-Plan.md` |
| 15 | 21:18:50 | Throttle | Warning | `Streaming chat error: Bedrock throttle` |
| 16 | 21:18:26 | Timeout | Warning | `stream_async error: Bedrock timeout` |
| 17 | 21:18:57 | Telemetry | Warning | `Failed to emit telemetry event: CloudWatch down` (test) |

**Test-generated noise (filtered):** 18+ records from unittest.mock/MagicMock, intentional test exceptions (`kaboom`, `boom`, `bad input`), fake URLs (`wind.example.com`), invalid test PDFs, and DDB error-handling tests.

#### /eagle/ecs/frontend-dev — 0 records

No errors in the last 24 hours.

#### /eagle/app — 0 records

No errors in the last 24 hours.

### Langfuse Trace Errors

**Status**: UNAVAILABLE — Bash tool blocked (same root cause as DynamoDB). Langfuse credentials are configured (`pk-lf-47021a72...`), but the Python HTTP client could not be invoked.

## Cross-Reference Analysis

### Session Correlation Map

Unable to perform full cross-referencing without DynamoDB feedback and Langfuse trace data. CloudWatch-only analysis below.

**CloudWatch session IDs found in errors:**
- `session=None` — supervisor call with no session context (test/eval run)
- `user=u session=s` — placeholder values from streaming error tests

No real user sessions appeared in the error logs, confirming these are from the automated test pipeline.

### Error Pattern Clusters

| Cluster | CloudWatch Signal | Langfuse Signal | Feedback Signal | Count | Priority |
|---------|------------------|-----------------|-----------------|-------|----------|
| **SSO Token Expired** | TokenRetrievalError, InvalidGrant, circuit breaker OPEN (103 failures) | N/A | N/A | 5 | P1 |
| **IAM Permission Gaps** | AccessDeniedException on document-metadata-dev table + Titan embed model | N/A | N/A | 7 | P1 |
| **Missing Templates** | Template not found for 5 doc types (igce, sow, ap, justification, market_research) | N/A | N/A | 7 | P2 |
| **Bedrock Throttle/Timeout** | Bedrock throttle + timeout in streaming | N/A | N/A | 2 | P2 |
| **Triage Dispatch** | 422 Unprocessable on triage_actions | N/A | N/A | 1 | P3 |
| **S3 Missing Artifact** | NoSuchKey for package document | N/A | N/A | 1 | P3 |

### Trend Analysis

- **Error timing**: All 311 records clustered in a ~40-minute window (21:17–21:56 UTC), coinciding with the nightly eval/test pipeline run.
- **No real user traffic errors**: All stack traces reference CI paths (`/home/runner/work/sm_eagle/`) or test mocks.
- **SSO token degradation**: Circuit breaker at 103 failures suggests the SSO token expired well before the keepalive ping detected it. The `OPEN` state blocks all subsequent Bedrock calls through this credential path.
- **Recurring pattern**: Template-not-found warnings appear consistently across triage reports (check prior reports for trend).

## Prioritized Issue List

### P1 — Fix This Sprint (Severity 5-6)

| # | Issue | Severity | Sources | Evidence |
|---|-------|----------|---------|----------|
| 1 | **SSO Token Expiration — Circuit Breaker OPEN** | 6 | CW | 103 consecutive failures on `claude-sonnet-4-5`, `InvalidGrantException`, token refresh failed. Blocks all Bedrock model calls via SSO credential path. |
| 2 | **IAM Missing Permissions — Knowledge Tools** | 5 | CW | `eagle-deploy-role-dev/GitHubActions` lacks `dynamodb:Scan` on `eagle-document-metadata-dev` and `bedrock:InvokeModel` on `amazon.titan-embed-text-v2:0`. Knowledge search, path search, and semantic search all fail. |

### P2 — Backlog (Severity 3-4)

| # | Issue | Severity | Sources | Evidence |
|---|-------|----------|---------|----------|
| 3 | **Missing Document Templates** | 3 | CW | Templates not found for igce, sow, acquisition_plan, justification, market_research. Graceful fallback to markdown, but output quality is degraded. |
| 4 | **Bedrock Throttle/Timeout** | 3 | CW | Streaming errors from Bedrock rate limiting and timeouts. May need retry backoff or throughput provisioning. |

### P3 — Monitor (Severity 1-2)

| # | Issue | Severity | Sources | Evidence |
|---|-------|----------|---------|----------|
| 5 | **Triage Actions 422** | 2 | CW | `dispatch failed status=422 body=Unprocessable` — likely a payload validation issue in the triage router. |
| 6 | **S3 Missing Package Artifact** | 1 | CW | NoSuchKey for test-tenant package — likely test data, but indicates package store may have stale references. |

## Noise Report

| Pattern | Count | Justification |
|---------|-------|---------------|
| Test exception handlers (`boom`, `kaboom`, `DDB down`, `DDB unreachable`) | 6 | Intentional test scenarios verifying error handling paths |
| MagicMock/unittest.mock errors (`AI ranking failed: MagicMock`) | 7 | Test mock objects leaking into ranked search — expected in test env |
| Invalid test PDF (`Bedrock Converse failed for test.pdf`) | 3 | Intentional test with corrupt/invalid PDF file |
| Fake URL (`web_fetch: wind.example.com`) | 1 | Test with non-existent domain |
| Test streaming error (`bad input`) | 1 | Intentional test of streaming error path |
| `asyncio.coroutine` AttributeError in session preloader test | 1 | Python 3.11+ removed `asyncio.coroutine` — test compatibility issue (minor) |
| CloudWatch telemetry emission failure (`CloudWatch down`) | 1 | Intentional test of telemetry error handling |
| `Saved test run: 1620 passed, 0 failed` (matched due to "failed" keyword) | 1 | False positive — successful test run summary |

**Total noise filtered**: ~21 records out of 50 sampled

## Data Gaps

| Source | Status | Impact |
|--------|--------|--------|
| DynamoDB Feedback | UNAVAILABLE | Cannot assess user-reported bugs, thumbs_down signals, or feature requests. No user-facing severity boost possible. |
| Langfuse Traces | UNAVAILABLE | Cannot cross-reference trace errors, measure latency/cost, or identify orphan streams. |
| Root cause | `.claude/settings.json` PreToolUse hook references Windows path (`C:/Users/blackga/...`) which fails on Linux CI runner, blocking all Bash commands including Python/boto3/httpx scripts. |

**Recommendation**: Fix the hook path in `.claude/settings.json` to use a relative path (`python .claude/hooks/pre_tool_use.py`) or add CI detection to skip the hook. This will restore DynamoDB and Langfuse data collection for future triage runs.
