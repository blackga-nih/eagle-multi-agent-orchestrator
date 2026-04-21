# EAGLE Triage Report

**Date**: 2026-04-21
**Environment**: dev
**Window**: 24h (2026-04-20 00:00 UTC to 2026-04-21 23:59 UTC)
**Tenant**: default-dev
**Mode**: Full
**Sources**: CloudWatch Logs (dev) | DynamoDB Feedback (UNAVAILABLE) | Langfuse Traces (UNAVAILABLE)

## Executive Summary

The dev environment shows two actionable production issues and one CI-only IAM gap. The highest priority finding is an SSO token expiry in the ECS backend container (10 error occurrences in a burst at 05:16 UTC), which causes all AWS service calls to fail until the token is refreshed. Additionally, the CI deploy role is missing `dynamodb:Scan` permission on the `eagle-document-metadata-dev` table, causing knowledge_search test failures. The most recent test run shows 97.5% pass rate (1505 passed, 38 failed). DynamoDB feedback and Langfuse trace data remain unavailable due to a recurring CI infrastructure issue (Windows-path hook blocking Bash execution).

## Source Data

### DynamoDB Feedback

**Status**: UNAVAILABLE

Data collection blocked by CI infrastructure issue: `.claude/settings.json` PreToolUse hook references Windows path `C:/Users/blackga/Desktop/eagle/sm_eagle/.claude/hooks/pre_tool_use.py` that does not exist on the Linux CI runner, preventing all Bash tool execution including boto3 queries.

**Gap Impact**: Cannot assess user-reported bugs, thumbs_down feedback, or session-level negative signals for the last 24h.

### CloudWatch Errors

#### `/eagle/ecs/backend-dev`

| Metric | Value |
|--------|-------|
| Records scanned | 27,956 |
| Records matched (error/warning) | 402 |
| Real production errors | 10 (SSO token expiry) |
| CI/test-generated entries | ~30 (expected test behavior) |
| IAM gaps found | 2 (metadata table + Bedrock Converse) |
| Log stream | `localhost` |

##### P0: SSO Token Expiry (10 occurrences)

All at 2026-04-21 05:16:21 UTC, 5 pairs of cascading failures:

| Timestamp | Logger | Error |
|-----------|--------|-------|
| 05:16:21.240 | botocore.tokens | SSO token refresh attempt failed: `InvalidGrantException: Invalid refresh token provided` |
| 05:16:21.242 | botocore.credentials | Refreshing temporary credentials failed: `TokenRetrievalError: Token has expired and refresh failed` |
| 05:16:21.308 | botocore.tokens | SSO token refresh attempt failed (repeat) |
| 05:16:21.310 | botocore.credentials | Credential refresh failed (repeat) |
| 05:16:21.368 | botocore.tokens | SSO token refresh attempt failed (repeat) |
| 05:16:21.369 | botocore.credentials | Credential refresh failed (repeat) |
| 05:16:21.427 | botocore.tokens | SSO token refresh attempt failed (repeat) |
| 05:16:21.429 | botocore.credentials | Credential refresh failed (repeat) |
| 05:16:21.484 | botocore.tokens | SSO token refresh attempt failed (repeat) |
| 05:16:21.485 | botocore.credentials | Credential refresh failed (repeat) |

**Root Cause**: The ECS container is using SSO-based credentials (via `botocore.tokens.SSOTokenProvider`) rather than the IAM task role. When the SSO token expires, botocore attempts to refresh it via `CreateToken` API, which fails with `InvalidGrantException` because the refresh token is also invalid. This cascades to credential refresh failures, blocking all AWS SDK calls.

**Impact**: All AWS operations (DynamoDB, S3, Bedrock, CloudWatch) fail until credentials are manually refreshed or the container restarts with valid SSO tokens.

##### P1: DynamoDB AccessDeniedException on Metadata Table (3 occurrences)

All at 2026-04-21 05:05:21 UTC during CI test run:

| Logger | Error |
|--------|-------|
| eagle.knowledge_tools | `knowledge_search DynamoDB error: AccessDeniedException... eagle-deploy-role-dev/GitHubActions is not authorized to perform: dynamodb:Scan on resource: eagle-document-metadata-dev` |
| eagle.knowledge_tools | `exec_path_search DynamoDB error: AccessDeniedException... (same)` |
| eagle.knowledge_tools | `knowledge_search DynamoDB error: AccessDeniedException... (same)` |

**Root Cause**: The CiCD stack (`infrastructure/cdk-eagle/lib/cicd-stack.ts:157-168`) grants `dynamodb:Scan` only on the main `eagle` table. The `eagle-document-metadata-dev` table (`infrastructure/cdk-eagle/config/environments.ts:70`) is not included in the deploy role's policy. The StorageStack (`infrastructure/cdk-eagle/lib/storage-stack.ts:199-208`) grants metadata table access only to the `appRole` (ECS task role), not the `deployRole` (CI/CD role).

##### P1: Bedrock Converse AccessDeniedException (1 occurrence)

At 2026-04-21 05:08:15 UTC during CI test run:

| Logger | Error |
|--------|-------|
| eagle.web_search | `web_search ClientError [AccessDeniedException]: An error occurred (AccessDeniedException) when calling the Converse operation: Not authorized` |

**Root Cause**: The CI deploy role lacks `bedrock:InvokeModel` or `bedrock:Converse` permission for the model used by web_search.

##### Warning: Template Not Found Fallbacks (8 occurrences)

At 2026-04-21 05:05-05:07 UTC during CI test run:

| Template Type | Count |
|---------------|-------|
| igce | 2 |
| sow | 2 |
| acquisition_plan | 1 |
| justification | 1 |
| market_research | 1 |
| N/A (total) | 7 unique, 8 total |

All logged as `WARNING` from `eagle.template_service` with message "Template not found for {type}, falling back to markdown". The fallback behavior works correctly, but missing templates mean users get plain markdown instead of formatted DOCX/PDF output.

**Source file**: `server/app/template_service.py`

##### Test-Generated Errors (Noise -- Expected Behavior)

~30 log entries from the CI test suite run (05:04-05:08 UTC). These are intentional test fixtures validating error handling paths:

| Category | Count | Examples |
|----------|-------|---------|
| Mock exception tests | 6 | `boom_tool: kaboom`, `session_preloader: boom`, `Bedrock timeout` |
| Synthetic data tests | 5 | S3 fetch for `fake-id`, `fake-upload-id`, `upload-123`, `upload-456` |
| Deliberate error-path tests | 4 | `bad input` ValueError, `Bedrock throttle`, `budget exhausted` |
| DDB failure simulation | 4 | `DDB unreachable`, `DDB down`, `timeout`, `boom` |
| Other test artifacts | 6 | `web_fetch wind.example.com`, `CloudWatch down`, `Export failed for bad` |
| PDF validation tests | 3 | `Bedrock Converse failed for test.pdf: ValidationException` |
| Embedding mock tests | 2 | `embed_text failed: MagicMock`, `semantic_search: embedding failed` |

**Test Run Result**: `Saved test run 2026-04-21T05-08-24-333882Z: 1505 passed, 38 failed` (97.5% pass rate)

#### `/eagle/ecs/frontend-dev`

| Metric | Value |
|--------|-------|
| Records scanned | 0 |
| Errors matched | 0 |

No log records in the query window. Frontend container is either idle or logging only to stdout without errors.

#### `/eagle/app`

| Metric | Value |
|--------|-------|
| Records scanned | 0 |
| Errors matched | 0 |

No log records in the query window. Shared application log group is clean.

### Langfuse Trace Errors

**Status**: UNAVAILABLE

Data collection blocked by the same CI hook issue as DynamoDB. Langfuse credentials are configured (dev keys present in `server/.env`), but the Python httpx script could not execute.

**Gap Impact**: Cannot assess trace-level errors, orphan streams, latency trends, or cost data.

## Cross-Reference Analysis

### Session Correlation Map

Unable to build full correlation map due to missing DynamoDB feedback and Langfuse data. Partial findings from CloudWatch only:

| Signal Source | Sessions Identifiable | Status |
|--------------|----------------------|--------|
| CloudWatch errors | No session IDs in SSO errors; test errors use synthetic sessions | Partial |
| DynamoDB feedback | UNAVAILABLE | Gap |
| Langfuse traces | UNAVAILABLE | Gap |

### Error Pattern Clusters

| Cluster | CloudWatch Signal | Langfuse Signal | Feedback Signal |
|---------|------------------|-----------------|-----------------|
| **IAM/SSO** | SSO token expired (10x), DDB AccessDenied (3x), Bedrock AccessDenied (1x) | UNAVAILABLE | UNAVAILABLE |
| **Template Gaps** | Template not found (8x) | UNAVAILABLE | UNAVAILABLE |
| **Test Suite Health** | 1505 pass / 38 fail (97.5%) | UNAVAILABLE | UNAVAILABLE |

### Trend Analysis

Compared to previous triage (2026-04-20):
- **New**: SSO token expiry errors appeared (0 on 4/20, 10 on 4/21). This is a regression.
- **Recurring**: The CI hook issue (`C:/Users/blackga/...` Windows path) has been present since at least 2026-04-20, blocking DynamoDB and Langfuse data collection in all CI triage runs.
- **Test suite**: 38 failures out of 1543 tests. Previous day showed 0 errors in backend CloudWatch, suggesting the test run did not execute yesterday or ran cleanly.
- **Frontend + App**: Both remain clean (0 errors) -- consistent with prior reports.

## Prioritized Issue List

| # | Issue | Severity | Score | Sources | Impact |
|---|-------|----------|-------|---------|--------|
| 1 | SSO token expiry in ECS backend container | P0 | 7 | CW | All AWS operations blocked; user-facing outage when tokens expire |
| 2 | CI deploy role missing `dynamodb:Scan` on `eagle-document-metadata-dev` | P1 | 5 | CW | knowledge_search and exec_path_search tests fail in CI |
| 3 | CI deploy role missing Bedrock Converse permission | P1 | 5 | CW | web_search tool tests fail in CI |
| 4 | CI Bash hook uses Windows path, blocking DynamoDB/Langfuse triage data | P1 | 4 | Infra | Triage reports degraded -- 2 of 3 data sources unavailable |
| 5 | Document templates missing for 5 types (igce, sow, acquisition_plan, justification, market_research) | P2 | 3 | CW | Users get markdown fallback instead of formatted documents |
| 6 | Test suite 38 failures (2.5% failure rate) | P2 | 2 | CW | Test reliability degradation |

### Severity Scoring Detail

| Issue | User-Facing (0-3) | Frequency (0-2) | Cross-Source (0-2) | Severity (0-1) | Total |
|-------|--------------------|------------------|--------------------|----------------|-------|
| SSO token expiry | 3 (blocks all users) | 2 (10 occurrences) | 1 (CW only, others unavailable) | 1 (ACTIONABLE) | 7 |
| DDB metadata IAM | 1 (indirect) | 1 (3 occurrences) | 2 (CW + CI infra) | 1 (ACTIONABLE) | 5 |
| Bedrock IAM | 1 (indirect) | 1 (1 occurrence) | 2 (CW + CI infra) | 1 (ACTIONABLE) | 5 |
| CI hook path | 2 (degrades triage) | 1 (persistent) | 0 (infra only) | 1 (ACTIONABLE) | 4 |
| Missing templates | 1 (fallback works) | 1 (8 warnings) | 0 (CW only) | 1 (Warning) | 3 |
| Test failures | 0 (CI only) | 1 (38 failures) | 0 (CW only) | 1 (Warning) | 2 |

## Noise Report

| Category | Count | Justification |
|----------|-------|---------------|
| Test-generated mock errors | ~25 | Stack traces reference `unittest/mock.py`, `test_*.py` files, synthetic data (`fake-id`, `wind.example.com`, `boom_tool`) |
| Test-generated validation errors | ~5 | Deliberate invalid inputs (`test.pdf`, `bad input`, `slow query`) |
| Frontend log group empty | 0 | Expected when no frontend-specific errors occur |
| App log group empty | 0 | Expected when no scheduled tasks or eval runs fire |
