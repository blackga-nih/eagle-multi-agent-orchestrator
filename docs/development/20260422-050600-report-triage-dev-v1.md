# EAGLE Triage Report

**Date**: 2026-04-22
**Environment**: dev
**Window**: 24h (2026-04-21 00:00 UTC to 2026-04-22 23:59 UTC)
**Tenant**: default-dev
**Mode**: Full
**Sources**: CloudWatch Logs (dev) | DynamoDB Feedback (UNAVAILABLE) | Langfuse Traces (UNAVAILABLE)

## Executive Summary

The dev environment shows two recurring P1 IAM configuration gaps and a set of missing DOCX templates causing document generation fallbacks. The P0 SSO token expiry that dominated yesterday's report is **absent today** — indicating the issue was transient or resolved. The CI deploy role (`eagle-deploy-role-dev`) still lacks `dynamodb:Scan` on `eagle-document-metadata-dev` and `bedrock:Converse` permissions, causing knowledge_search and web_search test failures. Template generation falls back to markdown for 5 document types (igce, sow, acquisition_plan, justification, market_research) due to missing S3 templates. Frontend-dev and `/eagle/app` log groups are clean (0 errors). DynamoDB feedback and Langfuse traces remain unavailable due to a CI infrastructure issue (Windows-path hook blocking Bash execution).

## Source Data

### DynamoDB Feedback

**Status**: UNAVAILABLE

Data collection blocked by CI infrastructure issue: `.claude/settings.json` PreToolUse hook references Windows path `C:/Users/blackga/Desktop/eagle/sm_eagle/.claude/hooks/pre_tool_use.py` that does not exist on the Linux CI runner, preventing all Bash tool execution including boto3 queries.

**Gap Impact**: Cannot assess user-reported bugs, thumbs_down feedback, or session-level negative signals for the last 24h. This is a recurring gap — same root cause as yesterday's triage.

### Langfuse Traces

**Status**: UNAVAILABLE

Langfuse credentials are configured in `server/.env` (dev keys present), but the Python query cannot execute due to the same Bash hook blocker above.

**Gap Impact**: Cannot assess trace error rates, latency trends, cost data, or orphan stream traces.

### CloudWatch Errors

#### `/eagle/ecs/backend-dev`

| Metric | Value |
|--------|-------|
| Records scanned | 27,680 |
| Records matched (error/warning) | 481 |
| Time range of errors | 2026-04-22 05:03–05:06 UTC |
| Log stream | `localhost` (CI test runner) |
| Test run result | 1,521 passed, 18 failed |

##### P1: DynamoDB AccessDeniedException on Metadata Table (3 occurrences)

At 2026-04-22 05:03:45 UTC during CI test run:

| Logger | Error |
|--------|-------|
| `eagle.knowledge_tools` | `knowledge_search DynamoDB error: AccessDeniedException... eagle-deploy-role-dev/GitHubActions is not authorized to perform: dynamodb:Scan on resource: arn:aws:dynamodb:us-east-1:695681773636:table/eagle-document-metadata-dev` |
| `eagle.knowledge_tools` | `exec_path_search DynamoDB error: AccessDeniedException... (same)` |
| `eagle.knowledge_tools` | `knowledge_search DynamoDB error: AccessDeniedException... (same)` |

**Root Cause**: The CiCD stack (`infrastructure/cdk-eagle/lib/cicd-stack.ts:157-168`) grants `dynamodb:Scan` only on the main `eagle` table via the `EvalRunnerData` policy. The `eagle-document-metadata-dev` table is not included. The StorageStack (`infrastructure/cdk-eagle/lib/storage-stack.ts:199-208`) grants metadata table access only to the `appRole` (ECS task role), not the `deployRole` (CI/CD role).

**Recurrence**: Same issue reported in yesterday's triage (2026-04-21). Not yet fixed.

##### P1: Bedrock Converse AccessDeniedException (1 occurrence)

At 2026-04-22 05:06:32 UTC:

| Logger | Error |
|--------|-------|
| `eagle.web_search` | `web_search ClientError [AccessDeniedException]: An error occurred (AccessDeniedException) when calling the Converse operation: Not authorized` |

**Root Cause**: The CI deploy role (`cicd-stack.ts:142-154`) has `bedrock:InvokeModel` and `bedrock:InvokeModelWithResponseStream` but lacks `bedrock:Converse`. The web_search tool uses `Converse` API.

**Recurrence**: Same issue reported in yesterday's triage. Not yet fixed.

##### P2: Template Not Found Fallbacks (8 occurrences)

Templates missing from S3 for 5 document types. The `template_service.py` catches `FileNotFoundError` and falls back to markdown generation:

| Timestamp | Doc Type | Count |
|-----------|----------|-------|
| 05:04:35, 05:05:48 | `igce` | 2 |
| 05:04:03, 05:05:48 | `sow` | 2 |
| 05:05:32 | `acquisition_plan` | 1 |
| 05:05:13 | `justification` | 1 |
| 05:04:45 | `market_research` | 1 |

**Root Cause**: DOCX template files have not been uploaded to S3 for these doc types. Code path: `server/app/template_service.py:458-460` raises `FileNotFoundError`, caught at line 431-436 which logs warning and falls back.

##### P2: S3 NoSuchKey for Package Content (1 occurrence)

| Logger | Error |
|--------|-------|
| `eagle.packages` | `Failed to fetch content for eagle/test-tenant/packages/PKG-2026-0042/acquisition_plan/v2/Acquisition-Plan.md: NoSuchKey` |

##### P2: Teams Notifier DNS Failure (1 occurrence)

| Logger | Error |
|--------|-------|
| `eagle.teams_notifier` | `Teams notifier failed (category=feedback): httpx.ConnectError: [Errno -5] No address associated with hostname` |

**Root Cause**: Webhook URL not resolvable from CI environment. Expected in CI but worth monitoring in deployed ECS.

##### P2: Triage Actions Dispatch 422 (1 occurrence)

| Logger | Error |
|--------|-------|
| `app.routers.triage_actions` | `triage_actions: dispatch failed status=422 body=Unprocessable` |

##### Warning: Streaming Chat Errors (2 occurrences)

Both at 05:04:00 UTC, test-generated:

| Error | Category |
|-------|----------|
| `Streaming chat error user=u session=s: bad input` | Test: ValueError path |
| `Streaming chat error user=u session=s: Bedrock throttle` | Test: RuntimeError path |

##### Warning: Strands Agent Errors (2 occurrences)

| Error | Category |
|-------|----------|
| `stream_async error: Bedrock timeout` | Test: timeout path |
| `Supervisor call failed (context_overflow=True, max_tokens=True): budget exhausted` | Test: MaxTokensReachedException |

#### `/eagle/ecs/frontend-dev`

**Status**: Clean — 0 records matched, 0 records scanned.

The frontend-dev log group appears empty for this window. This could indicate the frontend ECS service was not running, or simply no errors occurred.

#### `/eagle/app`

**Status**: Clean — 0 records matched, 0 records scanned.

The shared app log group shows no errors for this window.

## Cross-Reference Analysis

### Session Correlation Map

No session-level correlation is possible because:
1. DynamoDB feedback data is unavailable (Bash blocked)
2. Langfuse trace data is unavailable (Bash blocked)
3. CloudWatch errors are from CI test runs (logStream: `localhost`), not from user sessions

### Error Pattern Clusters

| Cluster | CloudWatch Signal | Langfuse Signal | Feedback Signal |
|---------|------------------|-----------------|-----------------|
| **IAM/Permissions** | 4 AccessDeniedException (DDB Scan + Bedrock Converse) | N/A | N/A |
| **Missing Templates** | 8 template fallback warnings | N/A | N/A |
| **CI Infrastructure** | N/A | N/A | Bash hook blocks 2/3 data sources |
| **Test Error Paths** | ~30 expected test errors (boom, fake-id, MagicMock) | N/A | N/A |

### Trend Analysis

| Metric | Yesterday (04-21) | Today (04-22) | Trend |
|--------|-------------------|---------------|-------|
| Backend records scanned | 27,956 | 27,680 | Stable |
| Backend records matched | 402 | 481 | +20% (more test coverage) |
| P0 issues | 1 (SSO token expiry) | 0 | Improved |
| P1 IAM gaps | 2 (metadata + Converse) | 2 (same) | Unchanged |
| Template fallbacks | 8 | 8 | Unchanged |
| Frontend errors | 0 | 0 | Clean |
| App errors | 0 | 0 | Clean |
| Test pass rate | 97.5% (1505/1543) | 98.8% (1521/1539) | Improved |
| Data sources available | 1/3 | 1/3 | Unchanged |

Key observations:
- **SSO expiry resolved**: Yesterday's P0 (10 SSO token expiry errors) is absent today.
- **IAM gaps persist**: Both the metadata table and Bedrock Converse permission gaps are unchanged.
- **Test health improving**: Pass rate up from 97.5% to 98.8% (18 failures vs 38).
- **Triage infrastructure gap unchanged**: The Windows-path hook continues to block 2/3 data sources in CI.

## Prioritized Issue List

| # | Issue | Severity | Score | Sources | Recurrence |
|---|-------|----------|-------|---------|------------|
| 1 | CI deploy role missing `dynamodb:Scan` on `eagle-document-metadata-dev` | P1 | 5 | CW | Day 2+ |
| 2 | CI deploy role missing `bedrock:Converse` permission | P1 | 5 | CW | Day 2+ |
| 3 | CI settings.json hook uses Windows path (blocks DynamoDB + Langfuse triage) | P1 | 4 | CI | Day 2+ |
| 4 | DOCX templates not uploaded for 5 doc types | P2 | 3 | CW | Ongoing |
| 5 | Teams notifier webhook DNS unresolvable in CI | P2 | 2 | CW | CI-only |
| 6 | S3 package content NoSuchKey (PKG-2026-0042) | P2 | 2 | CW | Unknown |
| 7 | Triage actions dispatch 422 | P2 | 2 | CW | Unknown |

## Noise Report

| Pattern | Count | Category | Justification |
|---------|-------|----------|---------------|
| `boom_tool: kaboom` (tool dispatch test) | 1 | Test error path | Expected test behavior in `test_tool_dispatch.py` |
| Session preloader `boom` / `asyncio.coroutine` | 2 | Test error path | Expected test behavior in `test_session_preloader.py` |
| MagicMock knowledge_search AI ranking | 7+ | Test mock | Expected when Bedrock client is mocked |
| S3 NoSuchKey for `fake-id`, `fake-upload-id`, `upload-123`, `upload-456` | 4 | Test data | Expected test behavior with synthetic keys |
| MaxTokensReachedException `budget exhausted` | 1 | Test error path | Expected in `test_max_tokens_retry.py` |
| Bedrock throttle/timeout (streaming routes) | 2 | Test error path | Expected error handling tests |
| Bedrock Converse PDF ValidationException | 3 | Test data | Expected with invalid `test.pdf` |
| web_search/web_fetch timeout/DNS errors | 2 | Test error path | Expected error handling tests |
| test_results DDB failures (unreachable/timeout/boom) | 4 | Test error path | Expected DDB error handling tests |
| CloudWatch telemetry emit failure | 1 | Test error path | Expected `"CloudWatch down"` mock |
| export failure for `bad` doc | 1 | Test error path | Expected error handling test |
| embed_text MagicMock failure | 1 | Test mock | Expected when embedding client is mocked |
| semantic_search embedding failed | 2 | Test mock | Expected when embedding client is mocked |
| DynamoDB ProvisionedThroughputExceededException | 1 | Test error path | Expected capacity test |

**Total noise filtered**: ~32 entries (all from CI test suite execution on logStream `localhost`)
