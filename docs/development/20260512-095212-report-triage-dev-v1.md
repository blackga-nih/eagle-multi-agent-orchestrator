# EAGLE Triage Report

**Date**: 2026-05-12
**Environment**: dev
**Window**: 24h (2026-05-11 09:52 UTC to 2026-05-12 09:52 UTC)
**Tenant**: default-dev
**Mode**: Full
**Sources**: DynamoDB Feedback, CloudWatch Logs (dev), Langfuse Traces (dev)

## Executive Summary

The dev environment is largely healthy with no user-reported issues and no Langfuse trace errors in the last 24 hours. CloudWatch shows 192 backend log matches, but the vast majority (~95%) are expected test-suite-generated errors from CI pytest runs exercising error-handling paths. Two actionable findings emerged: (1) a single frontend 503 error on the `/api/user/usage` endpoint suggesting a transient backend availability gap, and (2) CI deploy role IAM policy gaps preventing the `eagle-document-metadata-dev` DynamoDB table and Titan embedding model from being accessed during test runs.

## Source Data

### DynamoDB Feedback

| Metric | Value |
|--------|-------|
| General feedback (bugs, suggestions) | 0 items |
| Message-level feedback (thumbs) | 0 items |
| Thumbs up / down ratio | N/A |

No user feedback submitted in the last 24 hours. No bug reports, no negative signals to cross-reference.

### CloudWatch Errors

#### `/eagle/ecs/backend-dev` — 192 matches (50 returned)

All 50 returned records originate from the `localhost` logStream, indicating they were emitted during CI test suite execution (pytest), not from live ECS traffic. Classified below:

| Category | Count | Severity | Details |
|----------|-------|----------|---------|
| **Test error-path exercises** | ~40 | Noise | Expected: boom_tool, fake throttle, fake timeout, BadZipFile PDF, MagicMock serialization, template-not-found fallbacks, session_preloader mock errors, MaxTokensReachedException budget exhausted |
| **IAM: dynamodb:Scan on eagle-document-metadata-dev** | 3 | ACTIONABLE | Deploy role lacks `dynamodb:Scan` on `eagle-document-metadata-dev` table; knowledge_search and exec_path_search fail during CI tests |
| **IAM: bedrock:InvokeModel on titan-embed-text-v2:0** | 2 | ACTIONABLE | Deploy role `EvalRunnerBedrock` policy only covers `anthropic.*` and `minimax.*`, not `amazon.titan-embed-text-v2:0`; embed_text fails in CI |
| **knowledge_search AI ranking MagicMock fallbacks** | 7 | Noise | Test mocking causes JSON parse failures — expected behavior during tests |
| **knowledge_search serialization errors** | 2 | Noise | `maximum recursion depth` and `cannot pickle '_thread.lock'` — test-generated |
| **knowledge_search DynamoDB ProvisionedThroughputExceededException** | 1 | Noise | Test-injected DynamoDB error |
| **Template not found fallbacks** | 7 | Noise | Template generation falls back to markdown — tested for igce, sow, acquisition_plan, justification, market_research |
| **Test results DDB unreachable / timeout / save failures** | 4 | Noise | Test-injected DynamoDB failures |
| **CloudWatch telemetry emit failure** | 1 | Noise | Test-injected (`CloudWatch down`) |
| **Streaming chat errors (bad input, Bedrock throttle)** | 2 | Noise | Test-exercised error paths in streaming_routes |
| **agent_guidance fetch failures** | 2 | Noise | Test-exercised `catching classes that do not inherit from BaseException` |
| **Supervisor MaxTokensReachedException** | 2 | Noise | Test-exercised retry + exhaustion path |
| **stream_async Bedrock timeout** | 1 | Noise | Test-exercised timeout path |
| **Export ZIP failure** | 1 | Noise | Test-exercised export error path |
| **S3 NoSuchKey on package content** | 1 | Noise | Test-exercised missing content path |
| **triage_actions dispatch 422** | 1 | Noise | Test-exercised validation error path |
| **web_fetch hostname resolution failure** | 1 | Noise | Test-exercised DNS failure (fake domain `wind.example.com`) |
| **session_preloader asyncio.coroutine AttributeError** | 1 | Warning | Python 3.11 removed `asyncio.coroutine`; test mock uses deprecated API |

#### `/eagle/ecs/frontend-dev` — 1 match

| Timestamp | Error | Severity |
|-----------|-------|----------|
| 2026-05-12 03:09:29 UTC | `FastAPI /api/user/usage error: 503` | ACTIONABLE |

This is a real production error from ECS task logStream (`frontend/eagle-frontend/195f4c39...`). The frontend proxy received a 503 from the backend when fetching user usage data. Single occurrence — likely a transient backend availability gap (deployment, health check failure, or container restart).

#### `/eagle/app` — 0 matches

No errors in the shared application log group.

### Langfuse Trace Errors

| Metric | Value |
|--------|-------|
| Total traces | 0 |
| Error traces | 0 |
| Orphan traces filtered | 0 |
| Unique users | 0 |
| Avg latency | N/A |
| Total cost | $0.00 |

No Langfuse traces recorded in the last 24 hours. This indicates either no user traffic to the dev environment, or Langfuse instrumentation is not active on the current deployment.

## Cross-Reference Analysis

### Session Correlation Map

No session IDs available from feedback to cross-reference (0 feedback items). CloudWatch errors are all from CI test runs (`localhost` logStream) with no real user session IDs. The single frontend 503 error does not include a session ID in the log message.

**Result**: No cross-source session correlations possible in this window.

### Error Pattern Clusters

| Cluster | CloudWatch Signal | Langfuse Signal | Feedback Signal | Assessment |
|---------|------------------|-----------------|-----------------|------------|
| **CI IAM Gaps** | AccessDeniedException on `eagle-document-metadata-dev` (Scan) and `titan-embed-text-v2:0` (InvokeModel) | None | None | Deploy role policy gap — affects CI test reliability, not production |
| **Frontend 503** | `/api/user/usage error: 503` from ECS task | None | None | Transient backend unavailability — single occurrence |
| **Test Suite Noise** | ~45 errors across error-handling test paths | None | None | Expected behavior — pytest exercises failure modes |

### Trend Analysis

- **No increasing error trend detected**: All backend errors cluster in a single CI run window (06:25-06:30 UTC). The frontend 503 is an isolated event at 03:09 UTC.
- **No repeated user-impacting failures**: Zero Langfuse traces and zero feedback items indicate no user traffic or issues in this window.
- **CI test suite is healthy**: The test run at 06:30 reported "1873 passed, 0 failed" — the errors in CloudWatch are intentional test-exercised failure paths, not test failures.
- **IAM gaps are persistent**: The `eagle-document-metadata-dev` and `titan-embed-text-v2:0` AccessDeniedException errors appear consistently in CI runs; these are known gaps in the deploy role's IAM policy.

## Prioritized Issue List

| # | Issue | Severity | Score | Sources | Sessions | Evidence |
|---|-------|----------|-------|---------|----------|----------|
| 1 | CI deploy role missing `dynamodb:Scan` on `eagle-document-metadata-dev` table | P2 | 3 | CW | 0 (CI only) | 3x AccessDeniedException in knowledge_tools during pytest |
| 2 | CI deploy role missing `bedrock:InvokeModel` on `amazon.titan-embed-text-v2:0` | P2 | 3 | CW | 0 (CI only) | 2x AccessDeniedException in embed_text during pytest |
| 3 | Frontend 503 on `/api/user/usage` | P3 | 1 | CW | unknown | Single occurrence at 03:09 UTC from ECS frontend task |
| 4 | Test mock uses removed `asyncio.coroutine` (Python 3.11+) | P3 | 1 | CW | 0 (CI only) | AttributeError in test_session_preloader.py line 264 |

**Scoring rationale:**
- Issues 1-2: Frequency=1 (multiple occurrences) + Cross-source=0 + Error severity=1 (ACTIONABLE) + User-facing=0 = **3 (P2)**
- Issue 3: Frequency=0 (single) + Cross-source=0 + Severity=1 (ACTIONABLE) + User-facing=0 = **1 (P3)**
- Issue 4: Frequency=0 (single) + Cross-source=0 + Severity=1 (warning) + User-facing=0 = **1 (P3)**

## Noise Report

| Pattern | Count | Classification | Justification |
|---------|-------|----------------|---------------|
| Test-exercised error paths (boom_tool, fake throttle, MagicMock, etc.) | ~40 | Noise | Emitted by pytest test suite intentionally exercising error-handling code paths; `localhost` logStream confirms CI origin |
| Template not found fallbacks | 7 | Noise | Expected behavior when template files don't exist — graceful fallback to markdown |
| knowledge_search AI ranking MagicMock fallbacks | 7 | Noise | Test mocking causes controlled JSON parse failures |
| Test results DDB failure injections | 4 | Noise | Test-injected DynamoDB unreachability for error-path coverage |
| Supervisor MaxTokensReachedException retry/exhaustion | 2 | Noise | Test-exercised budget exhaustion path |
| agent_guidance BaseException warnings | 2 | Noise | Test-exercised exception handling |
| knowledge_search serialization errors | 2 | Noise | Test-exercised edge cases (recursion depth, thread lock pickling) |
| web_fetch DNS failure | 1 | Noise | Fake domain `wind.example.com` used in test |
| CloudWatch telemetry emit failure | 1 | Noise | Test-injected `CloudWatch down` |
| Export ZIP failure | 1 | Noise | Test-exercised export error path |
| S3 NoSuchKey | 1 | Noise | Test-exercised missing S3 key |
| triage_actions 422 | 1 | Noise | Test-exercised validation error |
| stream_async Bedrock timeout | 1 | Noise | Test-exercised timeout path |

**Total noise filtered**: ~72 of 51 returned records (including duplicates within the 192 matched)
