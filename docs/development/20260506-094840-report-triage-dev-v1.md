# EAGLE Triage Report

**Date**: 2026-05-06
**Environment**: dev
**Window**: 24h (2026-05-05 09:47 UTC – 2026-05-06 09:47 UTC)
**Tenant**: default-dev
**Mode**: Full
**Sources**: DynamoDB Feedback, CloudWatch Logs (dev), Langfuse Traces (dev)

## Executive Summary

The dev environment is largely healthy with no P0 or P1 issues. The most significant finding is a **Float-to-Decimal conversion bug in `document_service.py`** that prevents document creation when the `source_data` dict contains Python float values — this caused 2 errors in the same user session and blocks IGCE document generation. A secondary pattern of **knowledge search AI ranking JSON parse failures** (6 occurrences) degrades search quality by falling back to deterministic ranking. No user feedback was submitted in the window, and the frontend produced zero errors.

## Source Data

### DynamoDB Feedback

| Metric | Count |
|--------|-------|
| General feedback items | 0 |
| Message-level feedback | 0 |
| Bug reports | 0 |
| Thumbs down | 0 |

No feedback was submitted for the `default-dev` tenant in the last 24 hours.

### CloudWatch Errors

**Log group: `/eagle/ecs/backend-dev`** — 603 records matched, 50 returned

| # | Timestamp (UTC) | Category | Severity | Session | Message Summary |
|---|-----------------|----------|----------|---------|-----------------|
| 1 | 2026-05-05 23:01:25 | Application Bug | ACTIONABLE | `8a1e2458-cc43-4f9f-9d4a-f16a80a0f9cc` | `create_document failed: Float types are not supported. Use Decimal types instead.` — `document_service.py:497` `table.put_item(Item=item)` |
| 2 | 2026-05-05 22:57:39 | Application Bug | ACTIONABLE | `8a1e2458-cc43-4f9f-9d4a-f16a80a0f9cc` | `batch_generate_documents: create_document raised for PKG-2026-0024/igce` — same Float/Decimal TypeError |
| 3 | 2026-05-05 23:04:40 | Data Quality | Warning | (no session) | `Document payload warnings: Unknown contract_type: T&M/LH, Unknown acquisition_method: FSS, estimated_value parse failure for '1800000 to 2200000'` |
| 4 | 2026-05-05 23:03:34 | Data Quality | Warning | (no session) | `Document payload warnings: Unknown contract_type: T&M/LH, estimated_value parse failure for '$1.8'` |
| 5 | 2026-05-05 22:35:32–05:37:42 | AI Quality | Warning | various | `knowledge_search AI ranking failed, falling back` — JSON parse errors (6 occurrences: unterminated strings, missing property names) |
| 6 | 2026-05-05 22:36:29 | Performance | Warning | `a15cf9e9-5e11-4f3a-b9d7-bdeda0e676f6` | `research_tool.slow: duration=64.22s threshold=60.0s` |

**Log group: `/eagle/ecs/frontend-dev`** — 0 errors

**Log group: `/eagle/app`** — 0 errors

### Langfuse Trace Errors

| Metric | Value |
|--------|-------|
| Total traces | 38 |
| Successful | 18 |
| Error traces | 1 |
| Orphan traces (filtered) | 19 |
| Avg latency | 97ms |
| Total cost (24h) | $10.09 |
| Unique users | 2 |

| Trace ID | Timestamp | Session | User | Latency | Cost | Error |
|----------|-----------|---------|------|---------|------|-------|
| `5a030a1d...` | 2026-05-05 20:42:53 | `1bbac815-7b86-46d1-b03d-00e5538db3f3` | `24a8d478-...` | 65ms | $0.003 | No error observation; output=null with non-zero cost — likely instrumentation gap |

## Cross-Reference Analysis

### Session Correlation Map

| Session ID | DynamoDB Feedback | CloudWatch Errors | Langfuse Errors | Correlation |
|------------|-------------------|-------------------|-----------------|-------------|
| `8a1e2458-cc43-4f9f-9d4a-f16a80a0f9cc` | — | 2 errors (Float/Decimal TypeError in create_document) | — | CW only |
| `a15cf9e9-5e11-4f3a-b9d7-bdeda0e676f6` | — | 1 warning (research_tool.slow) | — | CW only |
| `1bbac815-7b86-46d1-b03d-00e5538db3f3` | — | — | 1 trace (output=null) | LF only |
| `13e1ebdf-118b-4ec5-bb97-0c86ffa44bff` | — | 5 errors (OTel detach — noise) | — | CW noise |

No sessions appear across 2+ sources. No feedback correlates with any error sessions.

### Error Pattern Clusters

| Cluster | CloudWatch Signal | Langfuse Signal | Feedback Signal | Count |
|---------|-------------------|-----------------|-----------------|-------|
| **Application Bug — Float/Decimal** | `TypeError: Float types not supported` in `document_service.py:497` | — | — | 2 |
| **AI Quality — JSON Parse** | `knowledge_search AI ranking failed, falling back: Unterminated string / Expecting property name` | — | — | 6 |
| **Data Quality — Value Parsing** | `estimated_value` float parsing fails for range strings and currency-prefixed strings | — | — | 4 (warnings) |
| **Performance** | `research_tool.slow: 64.22s > 60s threshold` | — | — | 1 |
| **Instrumentation** | — | output=null, cost=$0.003 | — | 1 |

### Trend Analysis

- **Float/Decimal bug**: New pattern — both occurrences within 4 minutes of each other (22:57–23:01 UTC on May 5), triggered by document generation for PKG-2026-0024 (IGCE). This is a regression-candidate — the `source_data` dict from IGCE generation contains Python floats that are not converted to Decimal before DynamoDB `put_item`.
- **AI ranking failures**: Recurring pattern (6 occurrences across 7 hours). The Bedrock model intermittently returns malformed JSON when ranking knowledge base results. The fallback to deterministic ranking works, but search quality degrades.
- **Document validation warnings**: The Pydantic model for `estimated_value` expects a parseable float, but users provide range values ("1800000 to 2200000") and currency-prefixed strings ("$1.8"). This is a schema rigidity issue, not a bug.
- **No frontend errors**: The frontend is stable with zero errors in 24h.

## Prioritized Issue List

| # | Issue | Composite Score | Priority | Sources | Sessions | Evidence |
|---|-------|----------------|----------|---------|----------|----------|
| 1 | **Float-to-Decimal conversion missing in `_create_document_record`** | 3 (freq=2, sev=1) | **P2** | CW | 1 | `document_service.py:497` — `source_data` dict contains Python floats; DynamoDB rejects them |
| 2 | **Knowledge search AI ranking returns malformed JSON** | 2 (freq=2) | **P3** | CW | multiple | `knowledge_tools.py:883` — model intermittently returns unterminated strings; deterministic fallback engages |
| 3 | **Document `estimated_value` rejects range/currency strings** | 2 (freq=2) | **P3** | CW | N/A | `ai_document_schema.py` — Pydantic validation rejects "1800000 to 2200000" and "$1.8" |
| 4 | **Langfuse trace with null output** | 0 | **P3** | LF | 1 | Likely instrumentation gap — cost=$0.003 suggests successful model call but output not recorded |
| 5 | **Research tool slow (64s)** | 0 | **P3** | CW | 1 | Single occurrence slightly over 60s threshold — monitor only |

## Noise Report

| Category | Count | Justification |
|----------|-------|---------------|
| OTel `Failed to detach context` | 5 | Known noise per error patterns table — async context mismatch in OpenTelemetry, handled by Langfuse parent wrapper |
| Orphan stream traces | 19 | Client disconnect before span close — filtered by Langfuse query |
| Test suite artifacts (`boom_tool`, `test.pdf`, `web_search timeout`, `AccessDeniedException`, DDB unreachable/timeout) | 8+ | All from test execution at 17:36–17:38 UTC on localhost logStream, coinciding with test run "1775 passed, 0 failed" |
| `web_fetch request error: wind.example.com` | 1 | Test fixture with fake domain |
| `triage_actions dispatch failed status=422` | 1 | Test execution artifact |
| `Failed to get test run results: DDB unreachable` | 1 | Test execution artifact |
