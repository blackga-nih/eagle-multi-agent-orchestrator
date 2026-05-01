# EAGLE Triage Report

**Date**: 2026-05-01
**Environment**: dev
**Window**: 24h (2026-04-30 00:00 UTC – 2026-05-01 09:35 UTC)
**Tenant**: default-dev
**Mode**: Full
**Sources**: DynamoDB Feedback, CloudWatch Logs (dev), Langfuse Traces (dev)

## Executive Summary

The dev environment shows **zero user-reported feedback** but significant backend error volume: **1,295 error-level CloudWatch log entries** across 37,956 records scanned, and **18 Langfuse error traces** out of 100 total (18% error rate, plus 38 orphan traces filtered). The dominant issues are **IAM permission gaps** (S3 Vectors, Bedrock embedding, DynamoDB metadata table), **missing document templates** (5 template types not found), a **corrupt IGCE template file** (BadZipFile), and **sustained circuit breaker trips** on multiple Bedrock models. Four unique users were active; total Langfuse-tracked cost was $20.86. No user-facing feedback exists to confirm direct impact, but the error volume and IAM blocks indicate degraded knowledge search and document generation capabilities.

## Source Data

### DynamoDB Feedback

| Metric | Value |
|--------|-------|
| General feedback (bug, suggestion, etc.) | 0 items |
| Message-level feedback (thumbs up/down) | 0 items |

No feedback records found for tenant `default-dev` in the last 24 hours.

### CloudWatch Errors

**Log group**: `/eagle/ecs/backend-dev` — 1,295 matches / 37,956 records scanned
**Log group**: `/eagle/ecs/frontend-dev` — 0 matches / 5 records scanned
**Log group**: `/eagle/app` — 0 matches / 0 records scanned

#### Error Pattern Breakdown (backend-dev, top 30 by count)

| # | Count | Logger | Error Message | Category | Severity |
|---|-------|--------|---------------|----------|----------|
| 1 | 64 | botocore.tokens | SSO token refresh attempt failed | SSO/Credentials | Warning |
| 2 | 57 | botocore.credentials | Refreshing temporary credentials failed during advisory refresh period | SSO/Credentials | Warning |
| 3 | 54 | httpx | HTTP Request: POST http://testserver/api/errors/report | Test suite noise | Noise |
| 4 | 42 | eagle.knowledge_tools | knowledge_search AI ranking failed: JSON object must be str, not MagicMock | Test mock leaking | Noise |
| 5 | 40 | eagle.strands_agent | circuit_breaker: claude-sonnet-4-6 -> OPEN (failures=1) | Model availability | Warning |
| 6 | 34 | eagle.template_service | Template not found for sow, falling back to markdown | Missing template | ACTIONABLE |
| 7 | 32 | eagle.teams_notifier | Teams notifier failed (category=feedback) | Notification failure | Warning |
| 8 | 22 | eagle.template_service | Template generation failed for igce: File is not a zip file | Corrupt template | ACTIONABLE |
| 9 | 18 | eagle.knowledge_tools | S3 Vectors QueryVectors AccessDeniedException (eagle-app-role-dev) | IAM permission gap | ACTIONABLE |
| 10 | 16 | eagle.strands_agent | circuit_breaker: claude-sonnet-4-5 -> OPEN (failures=1) | Model availability | Warning |
| 11 | 16 | eagle.template_service | Template not found for igce, falling back to markdown | Missing template | ACTIONABLE |
| 12 | 16 | eagle.strands_agent | circuit_breaker: claude-sonnet-4 -> OPEN (failures=1) | Model availability | Warning |
| 13 | 15 | eagle.bedrock_document_parser | Bedrock Converse failed for test.pdf: ValidationException (not valid PDF) | Invalid input | ACTIONABLE |
| 14 | 11 | eagle.knowledge_tools | embed_text AccessDeniedException: bedrock:InvokeModel on titan-embed-text-v2 (eagle-deploy-role-dev) | IAM permission gap | ACTIONABLE |
| 15 | 11 | eagle.template_service | Template not found for acquisition_plan | Missing template | ACTIONABLE |
| 16 | 11 | eagle.template_service | Template not found for justification | Missing template | ACTIONABLE |
| 17 | 11 | eagle.template_service | Template not found for market_research | Missing template | ACTIONABLE |
| 18 | 11 | eagle.knowledge_tools | exec_semantic_search: embedding failed, skipping | Cascading from #14 | ACTIONABLE |
| 19 | 10 | eagle.knowledge_tools | DynamoDB Scan AccessDeniedException on eagle-document-metadata-dev (eagle-deploy-role-dev) | IAM permission gap | ACTIONABLE |
| 20 | 10 | eagle.session_preloader | session_preloader: unexpected error during preload | Session issue | Warning |
| 21 | 9–8 | eagle.strands_agent | circuit_breaker: claude-sonnet-4-6 -> OPEN (failures=100–109) | Sustained model failure | ACTIONABLE |
| 22 | 8 | eagle.strands_agent | circuit_breaker: claude-haiku-4-5 -> OPEN (failures=1) | Model availability | Warning |
| 23 | 8 | eagle.auth | Failed to decode dev-mode token: invalid start byte | Auth decode error | Warning |
| 24 | 8 | eagle.strands_agent | Service tool create_document failed: S3 upload failed | Document creation | ACTIONABLE |

### Langfuse Trace Errors

| Metric | Value |
|--------|-------|
| Total traces | 100 |
| Successful | 44 |
| Error traces | 18 |
| Orphan traces filtered | 38 |
| Average latency | 65 ms |
| Total cost | $20.86 |
| Unique users | 4 |

#### Error Traces with User Sessions

| Trace ID (short) | Session ID (short) | User ID (short) | Latency (ms) | Cost ($) | Category |
|---|---|---|---|---|---|
| 393b4e98 | 42c370b7 | 64d8a488 | 87 | 0.19 | output:null, has cost |
| 09b56554 | 89a68c3f | 64d8a488 | 387 | 0.63 | output:null, has cost |
| b88997c5 | d5dec6b3 | e4c88488 | 258 | 0.30 | output:null, has cost |
| 3c434dee | 18dd7d10 | 64d8a488 | 16 | 0.0001 | output:null, minimal cost |
| 23842407 | 0c0060ca | 64d8a488 | 15 | 0.0003 | output:null, minimal cost |
| 96a02f89 | 05883083 | 64d8a488 | 15 | 0.0002 | output:null, minimal cost |
| aedc9dd6 | 33769016 | 64d8a488 | 15 | 0.0002 | output:null, minimal cost |
| b09c4bbc | 0ff0ffe9 | 64d8a488 | 17 | 0.006 | output:null, low cost |

#### Initialization/Test Traces (no session, no user)

| Name Pattern | Count | Cost | Category |
|---|---|---|---|
| eagle-query-* | 10 | $0.00 | Eval/test initialization failures |

## Cross-Reference Analysis

### Session Correlation Map

No DynamoDB feedback sessions to cross-reference. Cross-referencing is limited to CloudWatch ↔ Langfuse.

The Langfuse error traces with real user sessions (42c370b7, 89a68c3f, d5dec6b3) incurred actual cost ($0.19–$0.63) but produced null output. These likely correlate with:
- **Circuit breaker trips** in CloudWatch — sonnet-4-6 circuit breaker went OPEN repeatedly, which would cause in-progress requests to fail after partial model invocation (explaining the non-zero cost but null output).
- **S3 Vectors AccessDenied** — knowledge search failures during active user sessions would degrade response quality.

The low-cost/low-latency error traces (18dd7d10, 0c0060ca, 05883083, 33769016) at 15–16ms suggest requests that failed very early — possibly during auth or session preload before reaching the model.

### Error Pattern Clusters

| Cluster | CloudWatch Signal | Langfuse Signal | Combined Count |
|---------|------------------|-----------------|----------------|
| **IAM/Permissions** | S3Vectors AccessDenied (18x), embed_text AccessDenied (11x), DynamoDB Scan AccessDenied (10x) | Traces with cost but null output (correlates with blocked operations) | 39 CW + correlated LF |
| **Template Failures** | Template not found: sow(34x), igce(16x), acq_plan(11x), justification(11x), market_research(11x); BadZipFile igce(22x) | — | 105 CW |
| **Model Availability** | Circuit breaker OPEN: sonnet-4-6(40x+50x sustained), sonnet-4-5(16x), sonnet-4(16x), haiku-4-5(8x) | 3 traces with real cost but null output | 130+ CW + 3 LF |
| **SSO/Credentials** | Token refresh failed (64x), credential refresh failed (57x), dev-mode token decode (8x) | — | 129 CW |
| **Document/S3** | create_document S3 upload failed (8x), Bedrock Converse invalid PDF (15x) | — | 23 CW |
| **Infrastructure** | Teams notifier failed (32x), session_preloader errors (10x) | — | 42 CW |
| **Test Suite Noise** | testserver HTTP requests (54x), MagicMock in knowledge_search (42x) | — | 96 CW (noise) |

### Trend Analysis

- **SSO errors cluster tightly** (21:35–21:37 on Apr 30) — a single developer session with expired SSO, not a systemic issue.
- **Circuit breaker trips sustained** — sonnet-4-6 reached 100+ consecutive failures, indicating a prolonged model availability issue or misconfigured model ID.
- **Template errors are persistent** — 5 template types consistently not found, suggesting templates were never provisioned for these document types, not a transient failure.
- **IAM errors affect the CI/deploy role** — the `eagle-deploy-role-dev` and `eagle-app-role-dev` are both missing permissions, suggesting CDK stack policies need updating.
- **Orphan trace ratio is high** (38/100 = 38%) — significant client disconnect rate, possibly from dev/test clients not completing requests.

## Prioritized Issue List

| # | Issue | Severity | Score | Sources | Est. Sessions |
|---|-------|----------|-------|---------|---------------|
| 1 | **S3 Vectors AccessDenied** — eagle-app-role-dev lacks `s3vectors:QueryVectors` | P1 | 5 | CW+LF | 3+ |
| 2 | **Circuit breaker sustained OPEN** — sonnet-4-6 at 100+ failures, no recovery | P1 | 5 | CW+LF | 3+ |
| 3 | **Missing document templates** — sow, igce, acquisition_plan, justification, market_research not found | P1 | 4 | CW | All doc-gen users |
| 4 | **BadZipFile for IGCE template** — corrupt .docx template file | P1 | 4 | CW | IGCE users |
| 5 | **Bedrock embed_text AccessDenied** — eagle-deploy-role-dev lacks `bedrock:InvokeModel` for titan-embed-v2 | P2 | 3 | CW | CI/test |
| 6 | **DynamoDB metadata table AccessDenied** — eagle-deploy-role-dev can't scan eagle-document-metadata-dev | P2 | 3 | CW | CI/test |
| 7 | **S3 upload failures** — create_document tool fails on S3 put | P2 | 3 | CW | 8 attempts |
| 8 | **Invalid PDF** — test.pdf fails Bedrock Converse validation | P2 | 3 | CW | Test |
| 9 | **Teams notifier failures** — webhook errors on feedback category | P2 | 3 | CW | Non-blocking |
| 10 | **Session preloader errors** — unexpected errors during preload | P2 | 2 | CW | Unknown |
| 11 | **Dev-mode auth token decode** — invalid UTF-8 in token header | P3 | 2 | CW | Dev only |
| 12 | **SSO token refresh failures** — expired developer SSO session | P3 | 1 | CW | 1 dev session |

## Noise Report

| Pattern | Count | Justification |
|---------|-------|---------------|
| HTTP POST testserver/api/errors/report | 54 | Test suite HTTP client logs — not production traffic |
| knowledge_search AI ranking: MagicMock | 42 | Test mock objects leaking into structured logs — test isolation issue |
| SSO token/credential refresh (botocore) | 121 | Single developer session with expired SSO — tight 2-minute window |
| Circuit breaker OPEN (failures=1, threshold=1) | 72 | Initial trips are expected behavior; only sustained 100+ trips are actionable |
| Orphan Langfuse traces (eagle-stream-*) | 38 | Client disconnect before span close — expected in dev |
| eagle-query-* traces (no session) | 10 | Eval/test initialization traces — expected |
