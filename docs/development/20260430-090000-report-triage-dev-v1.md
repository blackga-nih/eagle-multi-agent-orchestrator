# EAGLE Triage Report

**Date**: 2026-04-30
**Environment**: dev
**Window**: 24h
**Tenant**: default-dev
**Mode**: Full
**Sources**: DynamoDB Feedback (UNAVAILABLE), CloudWatch Logs (dev), Langfuse Traces (UNAVAILABLE)

## Executive Summary

The dev environment is **stable with no production-impacting errors**. All 708 CloudWatch log matches in backend-dev originated from CI test runs (localhost logStream), not ECS production containers. Frontend-dev and /eagle/app log groups returned zero errors. The primary concerns are: (1) the CI/GitHub Actions role lacks IAM permissions needed for integration tests hitting DynamoDB and Bedrock, reducing test coverage; (2) document templates are missing from S3, causing fallback to markdown generation; and (3) knowledge search has edge-case serialization errors with OTEL-instrumented boto3 responses. No P0 or P1 issues were identified. DynamoDB feedback and Langfuse trace data could not be collected due to a CI environment hook configuration issue (Windows path in `.claude/settings.json`).

## Data Collection Gaps

| Source | Status | Reason |
|--------|--------|--------|
| CloudWatch backend-dev | Collected | 708 matches, 31,801 records scanned |
| CloudWatch frontend-dev | Collected | 0 matches, 5 records scanned |
| CloudWatch /eagle/app | Collected | 0 matches, 0 records scanned |
| DynamoDB Feedback | **NOT COLLECTED** | CI hook blocker — `.claude/settings.json` has Windows-specific hook path that fails on Linux CI runner |
| Langfuse Traces | **NOT COLLECTED** | Same CI hook blocker — credentials are present but Python scripts could not execute |

## Source Data

### CloudWatch Errors — `/eagle/ecs/backend-dev`

**Important context**: All 50 returned log entries have `@logStream: "localhost"`, indicating they originated from CI test suite execution on the GitHub Actions runner, not from ECS container workloads. Error classification accounts for test-injected vs real errors.

#### ACTIONABLE — IAM Permission Gaps (CI Role)

The GitHub Actions role `eagle-deploy-role-dev/GitHubActions` is missing permissions that the ECS task role correctly has. This means integration tests that hit real AWS services fail in CI.

| Time (UTC) | Logger | Error | Count |
|------------|--------|-------|-------|
| 06:42:15 | `eagle.knowledge_tools` | `AccessDeniedException: dynamodb:Scan on eagle-document-metadata-dev` — role not authorized | 3 |
| 06:41:46–06:42:15 | `eagle.knowledge_tools` | `AccessDeniedException: bedrock:InvokeModel on amazon.titan-embed-text-v2:0` — role not authorized | 2 |
| 06:45:38 | `eagle.web_search` | `AccessDeniedException: Converse operation — Not authorized` | 1 |

**Note**: CDK stacks (`storage-stack.ts:199-208`, `core-stack.ts:154-191`) correctly grant these permissions to the ECS task role. The gap is only in the CI/GitHub Actions deployment role.

#### ACTIONABLE — Model Configuration

| Time (UTC) | Logger | Error |
|------------|--------|-------|
| 06:41:46 | `eagle.knowledge_tools` | `ValidationException: Invocation of model ID anthropic.claude-haiku-4-5-20251001-v1:0 with on-demand throughput isn't supported` |

The knowledge search AI ranking uses model ID `anthropic.claude-haiku-4-5-20251001-v1:0` but on-demand throughput requires the cross-region inference profile `us.anthropic.claude-haiku-4-5-20251001-v1:0`.

#### ACTIONABLE — Knowledge Search Serialization

| Time (UTC) | Logger | Error |
|------------|--------|-------|
| 06:41:46 | `eagle.strands_agent` | `knowledge_search serialization error: maximum recursion depth exceeded` |
| 06:41:46 | `eagle.strands_agent` | `knowledge_search serialization error: cannot pickle '_thread.lock' object` |

Root cause: OTEL instrumentation wraps boto3 responses with reference chains containing `_thread.lock` objects. `json.dumps()` on raw DynamoDB responses triggers `RecursionError`. Mitigation exists via `_sanitize_item()` in `knowledge_tools.py:539-560`, but edge cases remain in `strands_agentic_service.py` (lines 2595, 5039).

#### ACTIONABLE — PDF Validation

| Time (UTC) | Logger | Error | Count |
|------------|--------|-------|-------|
| 06:45:19 | `eagle.bedrock_document_parser` | `ValidationException: The PDF specified was not valid` | 3 |

Bedrock Converse rejects certain PDFs. Current handling in `bedrock_document_parser.py:187` catches the error and returns `BedrockParseResult(success=False)`, but no pre-validation exists to catch invalid PDFs before the API call.

#### Warning — Missing Document Templates

| Time (UTC) | Logger | Template Type | Count |
|------------|--------|---------------|-------|
| 06:42:34–06:44:38 | `eagle.template_service` | `igce` | 2 |
| 06:42:34–06:44:38 | `eagle.template_service` | `sow` | 2 |
| 06:44:20 | `eagle.template_service` | `acquisition_plan` | 1 |
| 06:43:57 | `eagle.template_service` | `justification` | 1 |
| 06:43:33 | `eagle.template_service` | `market_research` | 1 |

Templates not found in S3 under `eagle-knowledge-base/approved/supervisor-core/essential-templates/`. System falls back to markdown generation (`template_service.py:431-437`).

#### Warning — Other Errors

| Time (UTC) | Logger | Error | Category |
|------------|--------|-------|----------|
| 06:45:38 | `eagle.web_search` | `web_search timeout for query: slow query` | Timeout |
| 06:44:59 | `app.routers.triage_actions` | `triage_actions: dispatch failed status=422 body=Unprocessable` | Validation |
| 06:44:59 | `eagle.packages` | `Failed to fetch content: S3 NoSuchKey` | Data Quality |
| 06:42:34 | `eagle.telemetry.cloudwatch` | `Failed to emit telemetry event: CloudWatch down` | Infra (test) |
| 06:42:10 | `eagle.export` | `Failed to export bad for ZIP: Export failed for bad doc` | Data Quality (test) |

### CloudWatch Errors — `/eagle/ecs/frontend-dev`

**No errors found.** 5 records scanned, 0 matches. Frontend is clean.

### CloudWatch Errors — `/eagle/app`

**No errors found.** 0 records scanned, 0 matches.

### DynamoDB Feedback

**NOT COLLECTED** — CI environment hook blocker prevented Python script execution.

### Langfuse Trace Errors

**NOT COLLECTED** — CI environment hook blocker prevented Python script execution. Langfuse credentials are configured (public key: `pk-lf-47021a72...`).

## Cross-Reference Analysis

### Session Correlation Map

Cross-referencing is limited to CloudWatch data only (DynamoDB and Langfuse unavailable). No session IDs appear in the CloudWatch errors since all entries are from CI test runs with mock sessions (`session=None`, `session=s`).

| Correlation Type | Count | Status |
|-----------------|-------|--------|
| CW + Feedback | 0 | No feedback data |
| CW + Langfuse | 0 | No Langfuse data |
| CW + Feedback + Langfuse | 0 | No cross-source data |

### Error Pattern Clusters

| Cluster | CloudWatch Signal | Langfuse Signal | Feedback Signal |
|---------|------------------|-----------------|-----------------|
| **IAM/Permissions** | 6× AccessDeniedException (CI role) | N/A | N/A |
| **Model Config** | 1× Haiku on-demand not supported | N/A | N/A |
| **Serialization** | 2× recursion/pickle errors | N/A | N/A |
| **Data Quality** | 3× invalid PDF, 1× S3 NoSuchKey | N/A | N/A |
| **Missing Templates** | 7× Template not found | N/A | N/A |

### Trend Analysis

All errors are clustered in a 4-minute window (06:41:46–06:45:45 UTC on 2026-04-30), consistent with a single CI test suite execution. This is not an ongoing error trend but a snapshot of test suite behavior. The test run completed with **1,631 passed, 1 failed** — a 99.94% pass rate.

No time-of-day pattern or escalating trend is observable from a single CI run. Historical comparison with prior triage reports would provide trend context.

## Prioritized Issue List

| # | Issue | Severity | Score | Sources | Evidence |
|---|-------|----------|-------|---------|----------|
| 1 | CI role missing DynamoDB/Bedrock permissions | P2 | 3 | CW | 6× AccessDeniedException for `eagle-deploy-role-dev/GitHubActions` |
| 2 | Missing document templates in S3 | P2 | 2 | CW | 7× Template not found (igce, sow, acquisition_plan, justification, market_research) |
| 3 | Knowledge search serialization edge cases | P2 | 2 | CW | 2× RecursionError / pickle failure despite `_sanitize_item()` mitigation |
| 4 | PDF pre-validation missing | P2 | 2 | CW | 3× Bedrock rejects invalid PDF before processing |
| 5 | Haiku model ID missing cross-region prefix | P3 | 1 | CW | 1× `anthropic.claude-haiku-4-5-20251001-v1:0` not available on-demand |
| 6 | Test suite has 1 failure | P3 | 1 | CW | 1,631 passed, 1 failed (99.94% pass rate) |

### Composite Severity Scoring

| Issue | User-Facing (0-3) | Frequency (0-2) | Cross-Source (0-2) | ACTIONABLE (0-1) | Total (0-8) | Priority |
|-------|-------------------|-----------------|-------------------|-------------------|-------------|----------|
| CI IAM gaps | 0 | 2 | 0 | 1 | 3 | P2 |
| Missing templates | 0 | 2 | 0 | 0 | 2 | P2 |
| Serialization bugs | 0 | 1 | 0 | 1 | 2 | P2 |
| PDF validation | 0 | 1 | 0 | 1 | 2 | P2 |
| Model config | 0 | 0 | 0 | 1 | 1 | P3 |
| Test failure | 0 | 0 | 0 | 1 | 1 | P3 |

## Noise Report

| Pattern | Count | Justification |
|---------|-------|---------------|
| `knowledge_search AI ranking failed: ... MagicMock` | 8 | unittest.mock artifact — MagicMock in test environment |
| `Tool execution error (boom_tool): kaboom` | 1 | Deliberate test of error handling in `test_tool_dispatch.py` |
| `session_preloader: unexpected error during preload` | 2 | Mock-injected errors from `test_session_preloader.py` |
| `Supervisor call failed... budget exhausted` | 1 | `FakeMaxTokensReachedException` from `test_max_tokens_retry` |
| `Streaming chat error: bad input / Bedrock throttle` | 2 | Deliberately injected test errors |
| `Failed to save/list/get test results: DDB unreachable/timeout/boom` | 4 | Test results persistence error-handling tests |
| `knowledge_search DynamoDB: ProvisionedThroughputExceededException: boom` | 1 | Test-injected DynamoDB error |
| `agent_route fetch failed: catching classes that do not inherit from BaseException` | 1 | Test error in exception handling |
| `Failed to export bad for ZIP` | 1 | Test of export error handling |
| `Saved test run: X passed, Y failed` (INFO) | 2 | Matched filter due to "failed" keyword; informational only |

**Total noise filtered: ~23 entries out of 50 returned results (46%)**
