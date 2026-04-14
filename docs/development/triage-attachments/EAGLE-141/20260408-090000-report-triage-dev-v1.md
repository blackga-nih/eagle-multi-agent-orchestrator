# EAGLE Triage Report

**Date**: 2026-04-08
**Environment**: dev
**Window**: 24h (2026-04-07 00:00 UTC -- 2026-04-08 23:59 UTC)
**Tenant**: default-dev
**Mode**: Full
**Sources**: CloudWatch Logs (dev) | DynamoDB Feedback (SKIPPED -- Bash hook blocked) | Langfuse Traces (SKIPPED -- Bash hook blocked)

## Executive Summary

The dev environment shows **persistent Bedrock availability issues** with 1,169 error-matched records in the 24h window. The primary problem is `ServiceUnavailableException` from Bedrock affecting the `us.anthropic.claude-sonnet-4-6` model, causing the circuit breaker to open repeatedly (failures escalating from 4 to 11). At least one real user session (`a86eee77`) experienced a Strands event loop crash from this same issue. Additionally, document template lookups are failing for 5 template types (graceful fallback to markdown exists), and `asyncio.CancelledError` in `session_preloader.py` indicates a task cleanup bug. DynamoDB feedback and Langfuse trace queries were unavailable due to the same CI hook misconfiguration reported in prior triage runs.

## Data Collection Gaps

| Source | Status | Reason |
|--------|--------|--------|
| CloudWatch `/eagle/ecs/backend-dev` | Collected | 31,267 records scanned, 1,169 error matches |
| CloudWatch `/eagle/ecs/frontend-dev` | Collected | 15 records scanned, 0 errors -- clean |
| CloudWatch `/eagle/app` | Collected | 0 records scanned, 0 errors -- clean |
| DynamoDB Feedback | **SKIPPED** | Bash tool blocked by Windows-path PreToolUse hook in `.claude/settings.json` |
| Langfuse Traces | **SKIPPED** | Same hook blocker -- requires Bash for Python httpx query |

## Source Data

### CloudWatch Errors -- `/eagle/ecs/backend-dev`

**Total records scanned**: 31,267 across two log streams:
- `backend/eagle-backend/6591d1483f1b4a3db4c4360340f94b40` (ECS container)
- `localhost` (CI test runner / local dev)

#### Hourly Error Distribution

| Hour (UTC) | Error Count | Notes |
|------------|-------------|-------|
| 2026-04-07 19:00 | 306 | Peak -- test execution + keepalive |
| 2026-04-07 21:00 | 229 | Test execution cluster |
| 2026-04-07 16:00 | 205 | Keepalive + tests |
| 2026-04-07 22:00 | 203 | Test run (22:09-22:13) + keepalive |
| 2026-04-07 05:00 | 106 | Keepalive pings (ECS) |
| 2026-04-08 06:00 | 43 | Keepalive pings (ECS) |
| 2026-04-08 07:00 | 17 | Keepalive pings |
| 2026-04-08 08:00 | 9 | Keepalive pings |
| Other hours | 1-33 | Sporadic |

#### ACTIONABLE Errors

| # | Timestamp | Logger | Message | Category | Severity |
|---|-----------|--------|---------|----------|----------|
| 1 | 2026-04-08 06:18:32 | `strands.event_loop` | `cycle failed: ServiceUnavailableException ConverseStream -- Bedrock is unable to process your request` (session `a86eee77`) | Bedrock Crash | **ACTIONABLE** |
| 2 | 2026-04-08 06:18:54 | `eagle.telemetry.langfuse_client` | `Langfuse list_traces failed: 400 Bad Request` (session `a86eee77`) | Langfuse API Error | **ACTIONABLE** |
| 3 | 2026-04-07 22:13:02 | `eagle.web_search` | `web_search ClientError [AccessDeniedException]: Not authorized` (Converse operation) | IAM Permission | **ACTIONABLE** |

#### Warning-Level Errors

| # | Pattern | Count | Category | Severity |
|---|---------|-------|----------|----------|
| 1 | `keepalive_ping: us.anthropic.claude-sonnet-4-6 FAILED: ServiceUnavailableException` | ~240+ | Bedrock Availability | **Warning** (persistent) |
| 2 | `keepalive_ping: Too many connections` | ~240+ | Bedrock Rate Limit | **Warning** (persistent) |
| 3 | `circuit_breaker: -> OPEN (failures=N)` | ~120+ | Circuit Breaker | **Warning** (expected) |
| 4 | `keepalive_ping: Could not connect to endpoint URL` | 1 | Network Connectivity | **Warning** (transient) |
| 5 | `keepalive_ping: us.anthropic.claude-sonnet-4-5 FAILED: Too many connections` | 1 | Bedrock Rate Limit (Sonnet 4.5) | **Warning** |
| 6 | `Template not found for {type}, falling back to markdown` | 6 | Missing Templates (sow, igce, acquisition_plan, justification, market_research) | **Warning** |
| 7 | `asyncio CancelledError in session_preloader._load_prefs` | ~14 | Asyncio Task Cleanup | **Warning** |

#### Noise (Filtered -- Test Artifacts)

These errors originate from the `localhost` log stream during test execution at 22:09-22:13 UTC:

| Pattern | Count | Category |
|---------|-------|----------|
| `S3 NoSuchKey` for `fake-id`, `upload-123`, `upload-456`, `fake-upload-id` | 4 | Test data (mocked S3 keys) |
| `Bedrock Converse failed for test.pdf: PDF not valid` | 3 | Test data (invalid PDF) |
| `Tool execution error (boom_tool): kaboom` | 1 | Test data (exploding handler) |
| `web_fetch SSL CERTIFICATE_VERIFY_FAILED: example.com` | 3 | Test data (example.com) |
| `web_fetch DNS failure: wind.example.com` | 1 | Test data |
| `web_search timeout for query: slow query` | 1 | Test data |
| `Failed to emit telemetry event: CloudWatch down` | 1 | Test mock |
| `triage_actions dispatch failed: 422 Unprocessable` | 1 | Test data |
| `Failed to save/list test results: DDB down/timeout/boom` | 4 | Test mocks |
| `Streaming chat error: bad input / Bedrock throttle` | 2 | Test data |
| `session_preloader unexpected error: Exception("boom")` | 1 | Test mock |
| `session_preloader: asyncio.coroutine AttributeError` | 1 | Python 3.11+ compat in test |
| `Saved test run: 1330 passed, 50 failed` (INFO) | 1 | Test results (matched "fail" filter) |
| `Saved test run: 9 passed, 1 failed` (INFO) | 1 | Test results |
| `S3 NoSuchKey for package content` | 1 | Test data |

### CloudWatch Errors -- `/eagle/ecs/frontend-dev`

**Clean** -- 0 error records in the 24h window (15 records scanned total).

### CloudWatch Errors -- `/eagle/app`

**Clean** -- 0 error records in the 24h window (0 records scanned -- log group empty/inactive).

### DynamoDB Feedback

**SKIPPED** -- Could not query. The CI pre-tool-use hook in `.claude/settings.json` references a Windows path (`C:/Users/blackga/Desktop/eagle/sm_eagle/.claude/hooks/pre_tool_use.py`) that does not exist on the Linux CI runner. This is the same blocker reported in the 2026-04-06 triage.

### Langfuse Trace Errors

**SKIPPED** -- Same blocker as DynamoDB (requires Bash for Python httpx query). Langfuse dev credentials are configured (`pk-lf-47021a...`).

## Cross-Reference Analysis

### Session Correlation Map

Only one real session appeared in non-test error logs:

| Session ID | CloudWatch Errors | Langfuse | DynamoDB |
|------------|-------------------|----------|----------|
| `a86eee77-d73a-4ee1-9ec9-4389ed03b2dd` | Strands cycle failed (ServiceUnavailableException) + Langfuse 400 Bad Request | N/A (skipped) | N/A (skipped) |

### Error Pattern Clusters

| Cluster | CloudWatch Signal | Count | User Impact |
|---------|-------------------|-------|-------------|
| **Bedrock Availability** | `ServiceUnavailableException`, `Too many connections`, circuit breaker OPEN | ~718 | Session `a86eee77` crashed; other sessions may fail during OPEN circuit windows |
| **Langfuse API** | `list_traces failed: 400 Bad Request` | 1 | Telemetry gap for affected session |
| **Missing Templates** | `Template not found for {type}` | 6 | Graceful fallback to markdown; cosmetic only |
| **Asyncio Cleanup** | `CancelledError in _load_prefs` | ~14 | Potential resource leak; primarily in test execution |
| **IAM/Auth** | `AccessDeniedException: Not authorized` (web_search) | 1 | Web search Bedrock Converse call fails |

### Trend Analysis

- **Bedrock availability issues are persistent and recurring** -- this is the third consecutive triage (04-06, 04-07, 04-08) showing `ServiceUnavailableException` errors. The circuit breaker is working as designed but the underlying Bedrock capacity issue remains.
- **Error volume is increasing** -- 102 errors (04-06) -> 1,169 errors (04-08), a 10x increase. The peak hours shifted from late evening to afternoon/evening UTC.
- **Template missing errors are new** -- not seen in the 04-06 triage. Document generation now falls back to markdown for sow, igce, acquisition_plan, justification, and market_research templates.
- **The CI hook blocker persists** -- this is the third consecutive run where DynamoDB and Langfuse data collection is blocked by the same Windows-path hook issue.

## Prioritized Issue List

| Priority | Issue | Composite Score | Sources | Sessions |
|----------|-------|-----------------|---------|----------|
| **P1** | Bedrock `ServiceUnavailableException` causing circuit breaker cascades and session failures | 5 (Freq=2 + Severity=1 + Cross-source=0 + User-impact=2) | CW | 1 confirmed (a86eee77) |
| **P1** | CI hook misconfiguration blocking DynamoDB/Langfuse data collection | 5 (Freq=2 + Severity=1 + Recurring=2) | Infra | All triage runs |
| **P2** | Missing document templates (sow, igce, acquisition_plan, justification, market_research) | 3 (Freq=1 + Severity=1 + User-impact=1) | CW | Unknown |
| **P2** | Langfuse `list_traces` 400 Bad Request | 3 (Freq=0 + Severity=1 + Cross-source=2) | CW | 1 (a86eee77) |
| **P3** | `asyncio.CancelledError` in `session_preloader._load_prefs` | 2 (Freq=1 + Severity=1) | CW | Test context |
| **P3** | `AccessDeniedException` on web_search Converse call | 1 (Freq=0 + Severity=1) | CW | Test context |

## Noise Report

| Item | Count | Justification |
|------|-------|---------------|
| Test execution artifacts (S3 fake-id, boom_tool, test.pdf) | ~25 | All from `localhost` log stream during test run at 22:09-22:13 UTC. Fake IDs (`fake-id`, `upload-123`) and mock exceptions (`kaboom`, `boom`) confirm test origin. |
| `example.com` SSL/DNS errors | 4 | Test URLs -- not production traffic. |
| Test result summaries (INFO level matched by "fail" filter) | 2 | Informational, not errors. |
| Circuit breaker messages (companion to keepalive failures) | ~120 | Expected application behavior in response to Bedrock failures. Not independently actionable. |
