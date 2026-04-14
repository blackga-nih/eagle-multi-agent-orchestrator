# EAGLE Triage Report

**Date**: 2026-04-09
**Environment**: dev
**Window**: 24h
**Tenant**: default-dev
**Mode**: Full
**Sources**: CloudWatch Logs (dev) | DynamoDB Feedback (UNAVAILABLE) | Langfuse Traces (UNAVAILABLE)

## Executive Summary

The dev environment has **two IAM permission gaps** and a **sustained Bedrock availability issue**. The deploy role (`eagle-deploy-role-dev`) lacks `dynamodb:Scan` on the `eagle-document-metadata-dev` table, causing all knowledge-search calls made during CI/E2E tests to fail (19+ occurrences). Separately, S3 template fetching is returning AccessDenied for 8+ essential document templates. Bedrock's `us.anthropic.claude-sonnet-4-6` returned 629 `ServiceUnavailableException` errors in 24h, triggering repeated circuit-breaker trips. No frontend or app-layer errors were detected.

**Data Source Gaps**: DynamoDB feedback and Langfuse traces could not be queried because the CI runner's Bash hook has a hardcoded Windows path (`C:/Users/blackga/...`) that fails on Linux. This blocks Python/boto3 execution. Fix is tracked as P2 below.

## Source Data

### DynamoDB Feedback

**Status**: UNAVAILABLE — Bash tool blocked by PreToolUse hook with Windows-only path in `.claude/settings.json`.

### CloudWatch Errors

#### `/eagle/ecs/backend-dev` — 1,406 error records matched (40,241 scanned)

**ACTIONABLE Errors:**

| # | Category | Error | Count | Severity |
|---|----------|-------|-------|----------|
| 1 | IAM — DynamoDB | `AccessDeniedException: eagle-deploy-role-dev/GitHubActions not authorized for dynamodb:Scan on eagle-document-metadata-dev` | 19 | ACTIONABLE |
| 2 | IAM — S3 | `AccessDenied on s3:GetObject for template files in eagle-knowledge-base/approved/supervisor-core/essential-templates/` | 8 | ACTIONABLE |
| 3 | Bedrock | `ServiceUnavailableException: Bedrock is unable to process your request` (keepalive_ping failures) | 629 | Warning |
| 4 | S3 Upload | `S3 upload failed: PutObject InternalServerError: boom` | 1 | Noise (test mock) |
| 5 | DynamoDB | `Knowledge base list error: InternalServerError: boom` | 1 | Noise (test mock) |
| 6 | DynamoDB | `feedback_store: failed to write/list message feedback: InternalServerError: boom` | 2 | Noise (test mock) |
| 7 | Tool Dispatch | `Tool execution error (boom_tool): kaboom` | 1 | Noise (test mock) |
| 8 | Package Store | `compute_required_docs_with_checklist failed, falling back to static` (mock error from local dev) | 1 | Noise (test mock) |

**S3 Template Files Affected (AccessDenied):**
- `COR_Designation_Letter_Template.docx`
- `01.D_IGCE_for_Commercial_Organizations.xlsx`
- `statement-of-work-template-eagle-v2.docx`
- `Market_Research_Report_Template.docx`
- `HHS_Streamlined_Market_Research_Template_FY26.docx`
- `4.a. IGE for Products.xlsx`
- `4.b. IGE for Services based on Catalog Price.xlsx`
- `Attch #1 - HHS Streamlined Acquisition Plan MS WORD Template_fillable_ver 2025.05.07_FINAL VERSION.docx` (2 occurrences)

**Circuit Breaker Hourly Distribution:**

| Hour (UTC) | Events |
|------------|--------|
| Apr 8 06:00 | 54 |
| Apr 8 07:00 | 23 |
| Apr 8 08:00 | 11 |
| Apr 8 09:00 | 5 |
| Apr 8 10:00 | 12 |
| Apr 8 15:00 | 28 |
| Apr 8 20:00 | 142 |
| Apr 8 21:00 | 18 |
| Apr 9 05:00 | 63 |
| Apr 9 06:00 | **235** |
| Apr 9 07:00 | 18 |
| Apr 9 08:00 | 19 |
| Apr 9 09:00 | 1 |

Peak at Apr 9 06:00 UTC with 235 events. Second peak at Apr 8 20:00 with 142 events. Pattern suggests periodic Bedrock degradation rather than sustained outage.

#### `/eagle/ecs/frontend-dev` — 0 errors (15 records scanned)

No errors detected in the frontend log group.

#### `/eagle/app` — 0 errors (0 records scanned)

No errors detected in the shared app log group.

### Langfuse Trace Errors

**Status**: UNAVAILABLE — Same Bash hook blocker as DynamoDB. Langfuse dev credentials are configured (`pk-lf-47021a72...`), but Python script could not be executed.

## Cross-Reference Analysis

### Session Correlation Map

Unable to perform full session-level cross-referencing due to DynamoDB and Langfuse data gaps. CloudWatch errors do not contain explicit session IDs in the matched records.

**Partial correlation from CloudWatch alone:**
- The DynamoDB `AccessDeniedException` errors originate from `eagle-deploy-role-dev/GitHubActions`, indicating CI/CD pipeline context rather than user sessions.
- The S3 template errors originate from `eagle.template_service` logger, suggesting user-facing document generation flows during the 21:40–21:49 UTC window on Apr 8.
- The Bedrock circuit-breaker events span both `localhost` (local dev) and ECS log streams, indicating the issue affects both environments.

### Error Pattern Clusters

| Cluster | CloudWatch Signal | Severity |
|---------|------------------|----------|
| **IAM/Permissions** | AccessDeniedException (DynamoDB Scan) + AccessDenied (S3 GetObject) | ACTIONABLE — 27 events |
| **Model Availability** | ServiceUnavailableException + circuit_breaker OPEN | Warning — 629 events |
| **Test Artifacts** | Mock-based "boom"/"kaboom" errors from unittest.mock | Noise — 6 events |
| **Local Dev Artifacts** | Windows asyncio ConnectionResetError (WinError 10054) | Noise — 20+ events |

### Trend Analysis

- **IAM errors are persistent**: DynamoDB Scan failures appear at Apr 8 15:07, 21:09, Apr 9 05:22, 06:34 — every CI run triggers them. This is a systemic gap, not transient.
- **S3 template errors are clustered**: All 8 occurrences fall within a 9-minute window (21:40–21:49 Apr 8), suggesting a single user session attempted document generation.
- **Bedrock degradation is episodic**: Two major spikes (Apr 8 20:00, Apr 9 06:00) with quieter periods between. Circuit breaker failure count escalated from 2→8 across the window, indicating repeated recovery attempts failing.
- **Noise volume is high**: 20+ Windows asyncio errors and 6 mock-based errors inflate the raw error count. After filtering, actionable errors are ~27 (IAM) + 629 (Bedrock) = 656 total.

## Prioritized Issue List

| # | Issue | Composite Score | Priority | Sources | Evidence Count |
|---|-------|----------------|----------|---------|---------------|
| 1 | **Deploy role missing `dynamodb:Scan` on `eagle-document-metadata-dev`** | 5 | **P1** | CW | 19 |
| 2 | **S3 AccessDenied on essential template files** | 5 | **P1** | CW | 8 |
| 3 | **Bedrock ServiceUnavailableException causing circuit breaker trips** | 4 | **P1** | CW | 629 |
| 4 | **CI hook path hardcoded to Windows** (blocks triage data collection) | 3 | **P2** | CI | 1 |

**Scoring Rationale:**

1. **DynamoDB Scan IAM** (5): Frequency=2 (19 events) + Severity=1 (ACTIONABLE) + Cross-source=0 + User-facing=2 (knowledge search broken for CI tests, may affect users if deploy role is used at runtime).
2. **S3 Template AccessDenied** (5): Frequency=1 (8 events) + Severity=1 (ACTIONABLE) + Cross-source=0 + User-facing=3 (document generation directly user-facing — templates are SOW, IGCE, AP).
3. **Bedrock Circuit Breaker** (4): Frequency=2 (629 events) + Severity=0 (Warning — Bedrock-side) + Cross-source=0 + User-facing=2 (chat degraded during outage windows). Not directly fixable but keepalive tuning can reduce log noise.
4. **CI Hook Path** (3): Frequency=1 + Severity=1 (ACTIONABLE) + Cross-source=0 + User-facing=1. Blocks observability tooling in CI.

## Noise Report

| Category | Count | Justification |
|----------|-------|---------------|
| Windows asyncio `ConnectionResetError` (WinError 10054) | 20+ | Local dev environment artifacts from `localhost` log stream. `_ProactorBasePipeTransport._call_connection_lost` — Windows-specific socket cleanup during process shutdown. |
| Mock-based test errors (`boom`, `kaboom`) | 6 | Stack traces show `unittest/mock.py` — these are expected test error scenarios being logged to CloudWatch during CI test runs. |
| `compute_required_docs_with_checklist` fallback | 1 | Windows local dev, mock-based. Falls back to static safely. |
| `knowledge_fetch` INFO matching "Failure" | 2 | False positive — matched because GAO document filename contains "Failure_to_Rebut". This is a successful INFO-level fetch, not an error. |
