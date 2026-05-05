# EAGLE Triage Report

**Date**: 2026-05-05
**Environment**: dev
**Window**: 24h
**Tenant**: default-dev
**Mode**: Full
**Sources**: DynamoDB Feedback, CloudWatch Logs (dev), Langfuse Traces (dev)

## Executive Summary

Document creation is broken for users when `estimated_value` contains currency-formatted strings (e.g., "$750,000"). The value fails Pydantic float parsing validation, and even when coerced, floats crash DynamoDB's `put_item` (which requires `Decimal`). This affected 1 confirmed user session across both CloudWatch and Langfuse. No user feedback was submitted, but the error is blocking — documents fail to persist.

## Source Data

### DynamoDB Feedback

| Metric | Value |
|--------|-------|
| General feedback items | 0 |
| Message feedback items | 0 |
| Bug reports | 0 |
| Thumbs down | 0 |

No feedback submitted in the last 24h for tenant `default-dev`.

### CloudWatch Errors

**Log group: `/eagle/ecs/backend-dev`**
- Records scanned: 30,930
- Records matched (error/warning filter): 659
- Distinct errors returned: 50

| # | Category | Severity | Count | Description |
|---|----------|----------|-------|-------------|
| 1 | Float→Decimal DynamoDB crash | ACTIONABLE | 3 | `TypeError: Float types are not supported. Use Decimal types instead` in `document_service.py:497` during `put_item` |
| 2 | estimated_value parsing failure | ACTIONABLE | ~20 | `Input should be a valid number, unable to parse string as a number` for input `'$750,000'` |
| 3 | Unknown acquisition_method | Warning | 3 | `Unknown acquisition_method: Full and Open Competition via NITAAC CIO-SP3` |
| 4 | Template not found (fallback to MD) | Warning | 8 | Templates missing for: igce, sow, acquisition_plan, justification, market_research |
| 5 | web_search AccessDeniedException | ACTIONABLE (test) | 1 | `AccessDeniedException when calling the Converse operation: Not authorized` |
| 6 | web_search timeout | Warning (test) | 1 | Timeout for query "slow query" |
| 7 | web_fetch DNS resolution failure | Noise (test) | 1 | `wind.example.com` — test fixture |
| 8 | Bedrock PDF validation error | Warning (test) | 3 | `test.pdf` — invalid PDF in test |
| 9 | Streaming chat errors | Warning (test) | 2 | "bad input" + "Bedrock throttle" from test (user=u, session=s) |
| 10 | session_preloader error | Noise (test) | 1 | Mock-raised exception in unit test |
| 11 | Tool dispatch error (boom_tool) | Noise (test) | 1 | Intentional test explosion |
| 12 | CloudWatch telemetry emit failure | Noise (test) | 1 | "CloudWatch down" — test simulation |
| 13 | test_results DDB failures | Noise (test) | 4 | Test simulations for DDB errors |
| 14 | triage_actions 422 | Noise (test) | 1 | Test dispatch failure |
| 15 | S3 NoSuchKey (test-tenant) | Noise (test) | 1 | Missing test-tenant key |

**Log group: `/eagle/ecs/frontend-dev`** — 0 errors.

**Log group: `/eagle/app`** — 0 errors.

### Langfuse Trace Errors

| Metric | Value |
|--------|-------|
| Total traces (24h) | 30 |
| Successful | 14 |
| Error traces | 1 |
| Orphan streams (filtered) | 15 |
| Avg latency | 88ms |
| Total cost | $3.83 |
| Unique users | 2 |

**Error trace:**

| Trace ID | Session | User | Latency | Cost | Error |
|----------|---------|------|---------|------|-------|
| `a39693af8c4dc934...` | `a3d4928d-f8ab-45a0-a1e6-6a7972774889` | `64d8a488-4081-707e-0ff4-2bab1ffad3e1` | 950ms | $0.86 | No explicit error message (output present but document tool failed mid-session) |

## Cross-Reference Analysis

### Session Correlation Map

| Session ID | CloudWatch | Langfuse | Feedback | Verdict |
|------------|-----------|----------|----------|---------|
| `a3d4928d-f8ab-45a0-a1e6-6a7972774889` | 3x Float TypeError + ~20 validation warnings | 1 error trace (cost=$0.86) | None | **Confirmed user-impacting bug** (2 sources) |

### Error Pattern Clusters

| Cluster | Root Cause | CW Signal | LF Signal | FB Signal | Composite Score |
|---------|-----------|-----------|-----------|-----------|-----------------|
| **Document Persistence Failure** | Float type not converted to Decimal before DynamoDB put_item | 3 ERROR + 20 WARNING | 1 error trace | None | **P0 (6)** |
| **Currency Parsing** | `estimated_value` field receives "$750,000" string but schema expects raw float | 20 WARNING (validation) | — | None | **P1 (4)** |
| **Missing Templates** | Template registry lacks entries for several doc types | 8 WARNING | — | None | **P2 (2)** |
| **Unknown Acquisition Methods** | Enum doesn't include "Full and Open Competition via NITAAC CIO-SP3" | 3 WARNING | — | None | **P3 (1)** |

### Trend Analysis

- **Float/Decimal errors**: Concentrated in a single session (21:05–21:15 UTC on May 4). This suggests one user attempted document generation and hit the bug repeatedly across multiple document types (igce, qasp, sb_review, pws, buy_american, subk_review, required_sources).
- **Template warnings**: Appeared across the same time window — same session triggered template fallbacks.
- **Test noise**: All `localhost` logStream entries are from the CI test run at ~21:03–21:08 UTC. These are expected.
- **No recurring pattern from prior days** visible in this 24h window.

## Prioritized Issue List

| Priority | Issue | Score | Sources | Sessions | Action Required |
|----------|-------|-------|---------|----------|-----------------|
| **P0** | Float→Decimal crash in document_service.py:497 | 6 | CW+LF | 1 | Convert floats to Decimal before DynamoDB put_item |
| **P1** | Currency string parsing ("$750,000" → float) | 4 | CW | 1 | Strip `$`, `,` before float coercion in schema validator |
| **P2** | Missing document templates (igce, sow, etc.) | 2 | CW | 1 | Add templates or suppress warning |
| **P3** | Unknown acquisition_method enum value | 1 | CW | 1 | Add NITAAC CIO-SP3 to enum or use fuzzy match |

## Noise Report

| Pattern | Count | Justification |
|---------|-------|---------------|
| Test fixture errors (localhost logStream) | ~14 | Intentional test simulations — boom_tool, DDB down, mock exceptions |
| web_fetch DNS error (wind.example.com) | 1 | Non-existent test domain |
| Bedrock PDF validation (test.pdf) | 3 | Test with invalid PDF fixture |
| Streaming errors (user=u, session=s) | 2 | Synthetic test input |
| Orphan Langfuse traces | 15 | Client disconnect before span close — known noise pattern |
