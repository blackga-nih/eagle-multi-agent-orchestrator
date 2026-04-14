# EAGLE Triage Report

**Date**: 2026-04-04
**Environment**: dev
**Window**: 24h
**Tenant**: default-dev
**Mode**: Full
**Sources**: CloudWatch Logs (dev) | DynamoDB Feedback (SKIPPED - CI hook blocker) | Langfuse Traces (SKIPPED - CI hook blocker)

## Executive Summary

The dev environment shows **352 error-level log entries** in the backend over the last 24h, concentrated in a single 3-minute CI test run window (00:31-00:34 UTC). The dominant issues are: (1) missing document templates for 5 doc types causing fallback to markdown generation, (2) unhandled asyncio CancelledError in session preloader creating log noise, and (3) a Bedrock Converse AccessDeniedException in the web_search tool indicating an IAM gap. Frontend and app log groups are clean. DynamoDB feedback and Langfuse traces could not be queried due to a CI environment hook misconfiguration blocking Bash execution.

## Data Collection Gaps

| Source | Status | Reason |
|--------|--------|--------|
| CloudWatch backend-dev | Collected | 352 matches / 26,209 scanned |
| CloudWatch frontend-dev | Collected | 0 matches / 10 scanned |
| CloudWatch app | Collected | 0 matches / 0 scanned |
| DynamoDB Feedback | **SKIPPED** | CI PreToolUse hook references Windows path; blocks all Bash commands |
| Langfuse Traces | **SKIPPED** | Same Bash blocker prevents Python execution |

## Source Data

### CloudWatch Errors — `/eagle/ecs/backend-dev`

**352 records matched** across 26,209 scanned. All errors occurred 2026-04-04 00:31–00:34 UTC (CI test run window).

#### ACTIONABLE Errors

| # | Category | Logger | Count | Message Summary |
|---|----------|--------|-------|-----------------|
| 1 | Template Not Found | `eagle.template_service` | 7 | Templates missing for `sow`, `igce`, `acquisition_plan`, `justification`, `market_research` — falls back to markdown |
| 2 | IAM / AccessDenied | `eagle.web_search` | 1 | `AccessDeniedException` calling Bedrock Converse — "Not authorized" |
| 3 | Bedrock Throttle | `app.streaming_routes` | 1 | `RuntimeError: Bedrock throttle` during SSE streaming |
| 4 | Bedrock ValidationException | `eagle.bedrock_document_parser` | 3 | "The PDF specified was not valid" for `test.pdf` |
| 5 | S3 NoSuchKey | `app.routers.documents` | 4 | GetObject failures for upload IDs (`upload-123`, `upload-456`, `fake-id`, `fake-upload-id`) |
| 6 | Session Preloader Error | `eagle.session_preloader` | 2 | Unexpected errors: mock `Exception: boom` + `asyncio.coroutine` AttributeError |
| 7 | Triage Actions 422 | `app.routers.triage_actions` | 1 | Dispatch failed `status=422 body=Unprocessable` |
| 8 | Telemetry Emit Failure | `eagle.telemetry.cloudwatch` | 1 | "Failed to emit telemetry event: CloudWatch down" |
| 9 | Tool Execution Error | `eagle.tools.legacy_dispatch` | 1 | `boom_tool: kaboom` (test-injected RuntimeError) |
| 10 | Web Search Timeout | `eagle.web_search` | 1 | Timeout for query "slow query" |

#### Warning-Level Errors

| # | Category | Logger | Count | Message Summary |
|---|----------|--------|-------|-----------------|
| 1 | S3 Package Content | `eagle.packages` | 1 | NoSuchKey for `PKG-2026-0042/acquisition_plan/v2/Acquisition-Plan.md` |
| 2 | Web Fetch SSL | `eagle.web_fetch` | 3 | Certificate verify failed for `example.com` URLs |
| 3 | Web Fetch DNS | `eagle.web_fetch` | 1 | No address for `wind.example.com` |
| 4 | Test Results DDB | `eagle.test_results` | 4 | Save/list failures: "DDB down", "timeout", "boom", "DDB unreachable" |

#### Noise (Filtered)

| Category | Count | Justification |
|----------|-------|---------------|
| asyncio CancelledError (_GatheringFuture) | ~15 | Session preloader timeout cancels gather tasks; futures not retrieved — log noise, not user-facing |
| Test-injected errors (boom, kaboom, fake-id) | ~8 | Test harness exercising error paths — expected during CI |
| web_fetch SSL/DNS for example.com | 4 | Test URLs, not production traffic |

### CloudWatch Errors — `/eagle/ecs/frontend-dev`

**0 errors** — clean.

### CloudWatch Errors — `/eagle/app`

**0 errors** — clean (0 records scanned, log group may be inactive for dev).

## Cross-Reference Analysis

### Session Correlation Map

Cross-referencing could not be performed because DynamoDB feedback and Langfuse trace data were unavailable (CI hook blocker). The CloudWatch errors do not contain user session IDs — they originate from CI test execution, not user sessions.

### Error Pattern Clusters

| Cluster | CloudWatch Signal | Langfuse Signal | Feedback Signal |
|---------|------------------|-----------------|-----------------|
| **Template/Doc Gen** | 7x template_not_found + 1x S3 NoSuchKey for package content | N/A | N/A |
| **IAM/Auth** | 1x AccessDeniedException on Bedrock Converse | N/A | N/A |
| **Bedrock Capacity** | 1x Bedrock throttle in streaming | N/A | N/A |
| **Async Lifecycle** | ~15x CancelledError + 2x preloader errors | N/A | N/A |
| **Data Validation** | 3x invalid PDF + 4x S3 NoSuchKey for uploads | N/A | N/A |

### Trend Analysis

- **All errors concentrated in a single 3-minute CI window** (00:31-00:34 UTC on 2026-04-04). No spread across the 24h window, suggesting these are test-generated, not from ongoing user traffic.
- **Template not found is a recurring pattern** — seen across 5 different doc types (`sow`, `igce`, `acquisition_plan`, `justification`, `market_research`). This is a systemic configuration gap, not a one-off.
- **Session preloader CancelledError is chronic** — 15+ occurrences per test run. While not user-facing, it pollutes logs and masks real errors.
- **Frontend and app logs are clean** — no errors at all, suggesting frontend is stable.

## Prioritized Issue List

| # | Issue | Severity | Score | Sources | Evidence |
|---|-------|----------|-------|---------|----------|
| 1 | Template not found for 5 doc types (sow, igce, acquisition_plan, justification, market_research) | **P1** | 4 | CW | 7 occurrences; falls back to markdown; affects document generation quality |
| 2 | Web search Bedrock Converse AccessDeniedException | **P1** | 4 | CW | IAM permission gap; web_search tool non-functional when hitting Converse |
| 3 | Session preloader asyncio CancelledError log spam | **P2** | 3 | CW | ~15 occurrences per run; _GatheringFuture exceptions never retrieved; pollutes logs |
| 4 | Bedrock throttle during SSE streaming | **P2** | 2 | CW | 1 occurrence; known pattern; needs retry/backoff in streaming path |
| 5 | Bedrock PDF validation failure | **P2** | 2 | CW | 3 occurrences; test.pdf invalid; needs input validation before Converse call |
| 6 | Triage actions 422 Unprocessable | **P3** | 1 | CW | 1 occurrence; likely test-injected; needs input validation |
| 7 | Telemetry emit failure | **P3** | 1 | CW | 1 occurrence; test-injected "CloudWatch down"; code handles gracefully |
| 8 | CI hook misconfiguration (Windows path in .claude/settings.json) | **P1** | 4 | CI | Blocks all Bash execution in CI; prevents DynamoDB/Langfuse data collection |

**Severity Scoring** (0-8 scale):
- User-facing (3x): Not confirmed — DynamoDB/Langfuse unavailable for cross-reference
- Frequency (2x): Template errors score 2 (7 occurrences); CancelledError scores 2 (15+)
- Cross-source (2x): Cannot score — only 1 source available
- Error severity (1x): AccessDenied and template_not_found are ACTIONABLE (1)

## Noise Report

| Item | Count | Classification | Justification |
|------|-------|----------------|---------------|
| asyncio CancelledError in session_preloader | ~15 | Noise (promoted to P2 due to volume) | `asyncio.wait_for` timeout cancels gather tasks; CancelledError propagates but isn't caught by asyncio's default handler |
| `boom_tool: kaboom` RuntimeError | 1 | Noise | Test in `test_tool_dispatch.py:120` intentionally throws |
| S3 NoSuchKey for `fake-id`, `fake-upload-id` | 2 | Noise | Test data — non-existent upload IDs |
| web_fetch SSL cert errors for example.com | 3 | Noise | Test URLs — example.com doesn't have valid SSL for programmatic access |
| web_fetch DNS failure for wind.example.com | 1 | Noise | Non-existent test domain |
| web_search timeout "slow query" | 1 | Noise | Test scenario exercising timeout path |
| Test results DDB failures | 4 | Noise | Test scenarios: "DDB down", "boom", "timeout", "DDB unreachable" |
| Session preloader `asyncio.coroutine` AttributeError | 1 | Noise | Test code uses deprecated Python API (`asyncio.coroutine` removed in 3.11) |
| Test run "1323 passed, 57 failed" INFO | 1 | Informational | Test results summary — 57 failures warrant separate investigation |
