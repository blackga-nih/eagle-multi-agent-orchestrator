# EAGLE Triage Report

**Date**: 2026-05-02
**Environment**: dev
**Window**: 24h
**Tenant**: default-dev
**Mode**: Full
**Sources**: DynamoDB Feedback, CloudWatch Logs (dev), Langfuse Traces (dev)

## Executive Summary

The dev environment is **operationally healthy** with no user-reported bugs, no P0 issues, and a 93% Langfuse trace success rate (excluding orphan streams). The primary concern is repeated JSON parse failures in the knowledge search AI ranking pipeline (`_ai_rank_documents`), where Bedrock Haiku returns malformed JSON ~7 times in the last 24h. This degrades search quality by falling back to deterministic matching. A secondary cross-source issue links a slow research tool call (73s) on session `0743f948` to a Langfuse trace with null output, suggesting that long-running knowledge searches may intermittently fail to produce output visible to Langfuse.

No users submitted feedback (bug reports or thumbs-down) in the 24h window.

## Source Data

### DynamoDB Feedback

| Metric | Count |
|--------|-------|
| General feedback items | 0 |
| Message-level feedback items | 0 |
| Bug reports | 0 |
| Thumbs down | 0 |

No user feedback recorded for tenant `default-dev` in the last 24 hours.

### CloudWatch Errors

**Log group: `/eagle/ecs/backend-dev`** — 511 records matched / 31,703 scanned

#### Production Errors (ECS container — `backend/eagle-backend/*`)

100 records matched from deployed container. Breakdown by category:

| Category | Logger | Level | Count | Severity |
|----------|--------|-------|-------|----------|
| Knowledge AI ranking JSON parse | eagle.knowledge_tools | WARNING | 7 | Warning |
| Research tool slow (>60s) | eagle.strands_agent | WARNING | 3 | Warning |
| Document not found in S3 | eagle.knowledge_tools | WARNING | 2 | Warning |
| Document data validation (estimated_value) | eagle.ai_document_schema | WARNING | 2 | Warning |
| Document payload warnings | eagle.document_generation | WARNING | 2 | Warning |

**Knowledge AI ranking failures** — LLM returns malformed JSON, system falls back gracefully:
- `Unterminated string starting at: line 14 column 17 (char 1499)` (x2)
- `Unterminated string starting at: line 14 column 18 (char 1684)` (x2)
- `Unterminated string starting at: line 40 column 10 (char 1352)` (x1)
- `Expecting ',' delimiter: line 44 column 127 (char 1552)` (x1)
- `Expecting value: line 45 column 5 (char 1619)` (x3)

**Research tool slow calls:**
- Session `0743f948`: 73.31s (query: GAO B-302358 IDIQ minimum obligation requirements)
- Session `smoke-fca2debab8ad`: 72.33s (query: sole source exception to fair opportunity)
- Session `76a707ca`: 71.82s (query: JEFO Justification Exception Fair Opportunity)

**Document not found:**
- `eagle-knowledge-base/approved/legal-counselor/appropriations-law/appropriations_law_IDIQ_funding.txt`
- `eagle-knowledge-base/approved/financial-advisor/appropriations-law/appropriations_law_IDIQ_funding.txt`

**Document validation:** `estimated_value` field received string `$15` instead of numeric — Pydantic float parsing failed.

#### Test-Induced Errors (localhost logStream — pytest)

These are from the test suite, not production. Included for transparency:

| Category | Count | Notes |
|----------|-------|-------|
| SSO token refresh failures (botocore.tokens) | 62 | Local dev SSO expired |
| Credential refresh failures (botocore.credentials) | 62 | Same root cause as above |
| Circuit breaker OPEN events | 60+ | Test suite exercising circuit breaker |
| Template generation failures | 33 | Testing error paths (BadZipFile, template not found) |
| Knowledge base mock errors | 8 | Mock-driven InternalServerError/ServiceUnavailable |
| Auth token decode failures | 8 | Testing dev-mode edge cases |
| Teams notifier failures | 5 | Test webhook failures |
| S3 upload failures | 4 | Test document creation errors |

**Log group: `/eagle/ecs/frontend-dev`** — 0 errors (5 records scanned)

**Log group: `/eagle/app`** — 0 errors (0 records scanned)

### Langfuse Trace Errors

| Metric | Value |
|--------|-------|
| Total traces | 54 |
| Successful | 25 |
| Error traces (output=null) | 2 |
| Orphan streams filtered (noise) | 27 |
| Avg latency | 36ms |
| Total cost (24h) | $8.52 |
| Unique users | 2 |

**Error traces:**

| Trace ID | Session | User | Latency | Cost | Error |
|----------|---------|------|---------|------|-------|
| f74cc5ff... | 0743f948-b616-4cb2-88fd-60d75e8f2e90 | 64d8a488... | 77ms | $0.005 | output=null |
| 8ef96577... | d4ed9c31-775c-4a72-be0d-62d8131774c6 | 64d8a488... | 64ms | $0.003 | output=null |

Both traces have non-zero cost but null output, indicating the model processed tokens but the response was not captured by the Langfuse span. Possible causes: span closed before streaming completed, or an exception occurred after model invocation.

## Cross-Reference Analysis

### Session Correlation Map

| Session ID | DynamoDB | CloudWatch | Langfuse | Classification |
|------------|----------|------------|----------|----------------|
| 0743f948-b616-... | -- | research_tool.slow (73.31s), knowledge_fetch doc not found | output=null, cost=$0.005 | **Cross-source: CW+LF** |
| d4ed9c31-775c-... | -- | (no match in returned results) | output=null, cost=$0.003 | LF-only |
| smoke-fca2deba... | -- | research_tool.slow (72.33s) | -- | CW-only (smoke test) |
| 76a707ca-73b7-... | -- | research_tool.slow (71.82s) | -- | CW-only |
| 872a0901-e174-... | -- | AI ranking failed (JSON) | -- | CW-only |
| 79136581-2682-... | -- | knowledge_fetch (info) | -- | CW-only (info) |

**Session `0743f948` is the only cross-source correlated issue** — the research tool ran for 73s (well above 60s threshold), had a document-not-found warning, and the corresponding Langfuse trace recorded null output. This suggests that slow knowledge searches may intermittently prevent the trace from recording final output.

### Error Pattern Clusters

| Cluster | CloudWatch Signal | Langfuse Signal | Feedback Signal | Assessment |
|---------|------------------|-----------------|-----------------|------------|
| **Knowledge AI Ranking** | 7 JSON parse failures (WARNING) | -- | -- | Graceful fallback works; degrades ranking quality |
| **Slow Research** | 3 calls >60s (71-73s range) | 1 trace output=null (session 0743f948) | -- | Performance concern; cross-source on 1 session |
| **Missing KB Documents** | 2 document-not-found warnings | -- | -- | S3 key references stale data |
| **Document Validation** | 2 Pydantic validation warnings | -- | -- | AI sends string instead of number |
| **SSO Credential Expiry** | 124 refresh failures | -- | -- | Local dev only — not production |
| **Test Suite Noise** | 100+ mock-driven errors | -- | -- | Expected test behavior |

### Trend Analysis

- **Knowledge AI ranking failures are recurring**: Similar JSON parse errors appeared in prior triage reports. The root cause is Bedrock Haiku occasionally returning truncated or malformed JSON when ranking large document sets (94-100 docs).
- **Research tool consistently slow at ~72s**: All 3 slow calls cluster around 71-73s, suggesting a consistent bottleneck — likely the AI ranking step within the research pipeline.
- **No time-of-day pattern**: All production activity occurred in a ~1h window (19:10-19:57 UTC on May 1), corresponding to a user session.
- **Orphan stream ratio high**: 27/54 (50%) traces are orphan streams. While filtered as noise, this suggests frequent client disconnects or page refreshes during streaming.

## Prioritized Issue List

| # | Issue | Severity | Score | Sources | Sessions |
|---|-------|----------|-------|---------|----------|
| 1 | Research tool slow (>60s) + Langfuse output=null | P2 | 3 | CW+LF | 1 (0743f948) |
| 2 | Knowledge AI ranking JSON parse failures | P2 | 2 | CW | 3+ sessions |
| 3 | Document data validation (estimated_value string parsing) | P3 | 1 | CW | 1 |
| 4 | Missing KB documents in S3 | P3 | 1 | CW | 1 (0743f948) |
| 5 | Langfuse trace output=null (session d4ed9c31) | P3 | 1 | LF | 1 |
| 6 | High orphan stream ratio (50%) | P3 | 1 | LF | -- |

**Severity scores calculated as:**
- User-facing (0-3): 0 for all (no feedback)
- Frequency (0-2): based on occurrence count
- Cross-source (0-2): 2 for CW+LF, 0 for single source
- Error severity (0-1): 0 for Warning, 1 for ACTIONABLE

## Noise Report

| Category | Count | Source | Justification |
|----------|-------|--------|---------------|
| Orphan stream traces | 27 | Langfuse | Client disconnect before span close — `eagle-stream-*`, no sessionId, cost=0, output=null |
| SSO token refresh failures | 62 | CloudWatch | botocore.tokens from local dev, not ECS container |
| Credential refresh failures | 62 | CloudWatch | botocore.credentials from local dev, not ECS container |
| Circuit breaker OPEN events | 60+ | CloudWatch | Test suite exercising circuit breaker (localhost logStream) |
| Template generation failures | 33 | CloudWatch | Pytest error-path tests (localhost logStream, mock.py in stack) |
| Knowledge base mock errors | 8 | CloudWatch | Mock-driven DynamoDB errors in pytest |
| Auth token decode failures | 8 | CloudWatch | Dev-mode token edge case testing |
| Teams notifier failures | 5 | CloudWatch | Test webhook failures |
| S3 upload failures | 4 | CloudWatch | Test document creation |

**Total noise filtered: 269+ items** (test-induced + dev-session + orphan streams)
