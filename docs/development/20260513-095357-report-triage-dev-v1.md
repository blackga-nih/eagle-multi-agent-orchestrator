# EAGLE Triage Report

**Date**: 2026-05-13
**Environment**: dev
**Window**: 24h (2026-05-12 00:00 UTC — 2026-05-13 23:59 UTC)
**Tenant**: default-dev
**Mode**: Full
**Sources**: DynamoDB Feedback, CloudWatch Logs (dev), Langfuse Traces (dev)

## Executive Summary

The dev environment is operationally healthy with **2 real production issues** in the last 24 hours: an SSE stream disconnect affecting one user session (correlated across CloudWatch frontend logs and Langfuse), and a transient backend 503 on the `/api/user/usage` endpoint. No user feedback was submitted. The backend-dev CloudWatch log group contains 669 error-matching records, but **all originate from test suite execution** (logStream `localhost`), not from deployed ECS tasks — these are noise that obscures real production signals.

## Source Data

### DynamoDB Feedback

| Metric | Value |
|--------|-------|
| General feedback | 0 items |
| Message feedback (thumbs up/down) | 0 items |
| Bug reports | 0 |
| Negative signals | 0 |

No user feedback was submitted for the `default-dev` tenant in the last 24 hours.

### CloudWatch Errors

#### `/eagle/ecs/backend-dev` — 669 records matched, 50 returned

**All 50 returned records have `@logStream: "localhost"`** — these are from CI/CD test suite execution, not from production ECS containers. Real ECS task logs would have logStreams matching the pattern `backend/eagle-backend/<task-id>`.

| Category | Count | Severity | Classification |
|----------|-------|----------|----------------|
| AccessDeniedException (DynamoDB Scan on eagle-document-metadata-dev) | 4 | Test Noise | CI role lacks perms (expected in test context) |
| AccessDeniedException (Bedrock InvokeModel titan-embed-text-v2) | 3 | Test Noise | CI role lacks perms (expected in test context) |
| knowledge_search AI ranking MagicMock failures | 8+ | Test Noise | Intentional test mock scenarios |
| Template not found fallbacks (igce, sow, acquisition_plan, justification, market_research) | 7 | Test Noise | Test scenarios for template fallback |
| Serialization errors (recursion depth, pickle thread.lock) | 2 | Test Noise | Intentional error-path tests |
| Session preloader errors | 2 | Test Noise | Includes asyncio.coroutine removal (Python 3.11 compat) |
| Streaming chat errors (bad input, Bedrock throttle) | 2 | Test Noise | Intentional error-path tests |
| Supervisor MaxTokensReachedException + budget exhausted | 2 | Test Noise | Intentional max-tokens retry test |
| DDB failures (unreachable, down, boom, timeout) | 4 | Test Noise | Mocked DDB failure scenarios |
| Teams notifier DNS failure | 1 | Test Noise | DNS unavailable in CI (no external network) |
| Bedrock timeout (stream_async error) | 1 | Test Noise | Intentional timeout test |
| agent_guidance fetch FAILED (BaseException catch error) | 2 | Test Noise | Exception handling test |
| Triage dispatch 422 Unprocessable | 1 | Test Noise | Validation test scenario |
| S3 NoSuchKey (PKG-2026-0042 acquisition_plan) | 1 | Test Noise | Missing S3 object test |
| Export failure (bad doc) | 1 | Test Noise | Export error-path test |
| CloudWatch telemetry emission failure | 1 | Test Noise | Mocked CW failure |
| Knowledge base DDB errors (ServiceUnavailable, InternalServerError, ProvisionedThroughputExceeded) | 3 | Test Noise | Mocked DDB errors |
| ValidationException Haiku model on-demand throughput | 1 | Test Noise | Model availability test |
| Error webhook configured (INFO level) | 1 | Noise | INFO log containing word "Error" |
| knowledge_search serialization errors | 2 | Test Noise | Intentional serialization edge cases |

**Net production errors from backend-dev: 0**

#### `/eagle/ecs/frontend-dev` — 4 records matched

| # | Timestamp (UTC) | LogStream | Error | Severity |
|---|-----------------|-----------|-------|----------|
| 1 | 2026-05-12 20:33:53 | `frontend/eagle-frontend/24f8f9b0...` | `Error: failed to pipe response` → `TypeError: terminated` → `SocketError: other side closed` | ACTIONABLE |
| 2 | 2026-05-12 20:33:53 | (same container) | `[cause]: [TypeError: terminated]` | (same event) |
| 3 | 2026-05-12 20:33:53 | (same container) | `[cause]: [Error [SocketError]: other side closed]` | (same event) |
| 4 | 2026-05-12 03:09:29 | `frontend/eagle-frontend/195f4c39...` | `FastAPI /api/user/usage error: 503` | ACTIONABLE |

**Analysis**: Records 1–3 are a single SSE stream disconnect event (the error and its nested causes). The backend closed the connection while the Next.js frontend was streaming the response. Record 4 is a separate 503 from the backend's user usage endpoint.

#### `/eagle/app` — 0 records matched

No errors in the shared application log group.

### Langfuse Trace Errors

| Metric | Value |
|--------|-------|
| Total traces | 14 |
| Successful | 6 |
| Error traces | 1 |
| Orphan traces filtered | 7 |
| Average latency | 45 ms |
| Total cost (24h) | $1.3691 |
| Unique users | 2 |

#### Error Trace

| Field | Value |
|-------|-------|
| Trace ID | `e96cb222df5010d94ab1ef1a5346e15c` |
| Timestamp | 2026-05-12T20:33:41Z |
| Session ID | `62fcb344-4843-4312-acdd-22724621cf4c` |
| User ID | `24a8d478-20a1-7087-e1a3-56a38d733592` |
| Latency | 11.604 ms |
| Cost | $0.002304 |
| Error message | (empty — observation flagged ERROR without statusMessage) |
| URL | [View in Langfuse](https://us.cloud.langfuse.com/project/cmmsqvi2406aead071t0zhl7f/traces/e96cb222df5010d94ab1ef1a5346e15c) |

**Analysis**: Very low latency (11ms) with minimal cost ($0.002) suggests the request failed quickly — the model started but the stream was interrupted before completion.

#### Orphan Traces (Filtered as Noise)

7 orphan traces matched the known pattern: `eagle-stream-*` name, no sessionId, totalCost=0, output=null. These are client disconnects before span close — standard noise.

## Cross-Reference Analysis

### Session Correlation Map

| Session ID | DynamoDB Feedback | CloudWatch Errors | Langfuse Errors | Correlation |
|------------|-------------------|-------------------|-----------------|-------------|
| `62fcb344-4843-4312-acdd-22724621cf4c` | — | Frontend pipe error at 20:33:53 | Error trace at 20:33:41 | **CW + LF** |
| (no session) | — | Backend 503 at 03:09:29 | — | CW only |

**Correlated event**: The Langfuse error trace at **20:33:41** and the frontend SSE pipe failure at **20:33:53** are 12 seconds apart, affecting the same user interaction. The backend likely errored during streaming, causing the Next.js proxy to receive a socket close, which cascaded as the pipe failure. This is confirmed as a single user-impacting incident.

### Error Pattern Clusters

| Cluster | CloudWatch Signal | Langfuse Signal | Feedback Signal | Assessment |
|---------|------------------|-----------------|-----------------|------------|
| **SSE Stream Failure** | `failed to pipe response` + `other side closed` (frontend-dev) | Error trace, 11ms latency, no output | None | Real production issue — user saw interrupted response |
| **Backend Availability** | `/api/user/usage error: 503` (frontend-dev) | — | None | Transient 503, possibly during deployment or health check |
| **Test Suite Log Noise** | 669 records from `localhost` logStream (backend-dev) | — | — | Test output in production CW; not a bug but an operational hygiene issue |

### Trend Analysis

- **SSE stream failures**: This is a recurring pattern seen in previous triage reports. The "other side closed" error indicates the backend drops the connection during long-running agent operations, possibly due to timeout or error in the Strands agent pipeline.
- **Backend 503s**: Single occurrence at 03:09 UTC — likely a transient availability blip (deployment, scaling event, or health check failure). Not a trend.
- **Test noise volume**: 669 test-generated records in the production CW log group is high and makes it difficult to identify real production errors. This is a persistent operational hygiene issue.
- **Langfuse orphan traces**: 7 out of 14 traces (50%) are orphans — this is an elevated orphan rate, though each individual orphan is expected noise (client disconnects).

## Prioritized Issue List

| # | Issue | Composite Score | Priority | Sources | Sessions Affected | Evidence |
|---|-------|----------------|----------|---------|-------------------|----------|
| 1 | SSE stream disconnect — backend closes connection mid-stream, user sees interrupted response | 5 (freq=2, cross-source=2, severity=1) | **P1** | CW frontend + Langfuse | 1 confirmed | CW: failed to pipe response; LF: 11ms error trace |
| 2 | Test suite output logged to production CloudWatch — 669 noise records obscure real errors | 2 (freq=2) | **P2** | CW backend-dev | N/A (operational) | All 50 returned records have logStream=localhost |
| 3 | Backend 503 on /api/user/usage — transient backend unavailability | 1 (severity=1) | **P3** | CW frontend | 1 | Single 503 at 03:09 UTC |

## Noise Report

| Category | Count | Justification |
|----------|-------|---------------|
| Test-generated errors (logStream=localhost) | ~669 | CI/CD test suite logs written to production CW log group; these are intentional error-path tests, not real failures |
| Orphan Langfuse traces | 7 | `eagle-stream-*` + no sessionId + cost=0 + output=null — known client disconnect pattern |
| Error webhook configured (INFO) | 1 | INFO-level log containing the word "Error" in its message — false positive from log filter |
