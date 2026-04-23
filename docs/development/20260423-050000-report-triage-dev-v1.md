# EAGLE Triage Report

**Date**: 2026-04-23
**Environment**: dev
**Window**: 24h (2026-04-22 00:00 UTC to 2026-04-23 23:59 UTC)
**Tenant**: default-dev
**Mode**: Full
**Sources**: CloudWatch Logs (dev) | DynamoDB Feedback (UNAVAILABLE) | Langfuse Traces (UNAVAILABLE)

## Executive Summary

The dev environment continues to show **recurring IAM permission gaps** and **missing document templates** — the same P1 issues from the past two daily triages remain unresolved. The CI deploy role (`eagle-deploy-role-dev`) lacks `dynamodb:Scan` on `eagle-document-metadata-dev` and `bedrock:InvokeModel` on `amazon.titan-embed-text-v2:0`, breaking knowledge search and semantic embedding. Template generation falls back to markdown for 5 document types. Two new application bugs surfaced: **knowledge_search serialization errors** (recursion depth / pickle failures) and a **Bedrock model misconfiguration** (Haiku 4.5 on-demand throughput not supported). Test suite health improved to 1580/1587 (99.6% pass, up from 98.8% yesterday). Frontend-dev and `/eagle/app` log groups are clean (0 errors). DynamoDB feedback and Langfuse traces remain unavailable due to the recurring CI hook infrastructure issue.

## Source Data

### DynamoDB Feedback

**Status**: UNAVAILABLE

Data collection blocked by CI infrastructure issue: `.claude/settings.json` PreToolUse hook references Windows path `C:/Users/blackga/Desktop/eagle/sm_eagle/.claude/hooks/pre_tool_use.py` that does not exist on the Linux CI runner, preventing all Bash tool execution including boto3 queries.

**Gap Impact**: Cannot assess user-reported bugs, thumbs_down feedback, or session-level negative signals for the last 24h. This is a **3rd consecutive day** with this gap — the hook path needs to be fixed in the committed settings.json.

### Langfuse Traces

**Status**: UNAVAILABLE

Langfuse dev credentials are configured in `server/.env` (public key `pk-lf-47021a72...`), but the Python query cannot execute due to the same Bash hook blocker.

**Gap Impact**: Cannot assess trace error rates, latency trends, cost data, or orphan stream traces.

### CloudWatch Errors

#### `/eagle/ecs/backend-dev`

| Metric | Value |
|--------|-------|
| Records scanned | 36,198 |
| Records matched (error/warning) | 1,370 |
| Time range of errors | 2026-04-23 04:44–04:52 UTC |
| Log stream | `localhost` (CI test runner) |
| Test run result | 1,580 passed, 7 failed |

##### IAM: DynamoDB AccessDeniedException on Metadata Table (3 occurrences)

| Timestamp | Logger | Error |
|-----------|--------|-------|
| 04:47:24 | `eagle.knowledge_tools` | `knowledge_search DynamoDB error: AccessDeniedException... eagle-deploy-role-dev/GitHubActions is not authorized to perform: dynamodb:Scan on resource: arn:aws:dynamodb:us-east-1:695681773636:table/eagle-document-metadata-dev` |
| 04:47:24 | `eagle.knowledge_tools` | `exec_path_search DynamoDB error: AccessDeniedException... (same)` |
| 04:44:23 | `eagle.knowledge_tools` | `knowledge_search DynamoDB error: AccessDeniedException... (same)` |

**Root Cause**: CiCD stack grants `dynamodb:Scan` only on the main `eagle` table. The `eagle-document-metadata-dev` table is not included in the CI/CD deploy role policy.

**Recurrence**: 3rd consecutive day. Not yet fixed.

##### IAM: Bedrock InvokeModel AccessDeniedException — Titan Embedding (2 occurrences)

| Timestamp | Logger | Error |
|-----------|--------|-------|
| 04:47:24 | `eagle.knowledge_tools` | `embed_text failed: AccessDeniedException... eagle-deploy-role-dev/GitHubActions is not authorized to perform: bedrock:InvokeModel on resource: arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0` |
| 04:44:23 | `eagle.knowledge_tools` | `embed_text failed: AccessDeniedException... (same)` |

**Root Cause**: Deploy role missing `bedrock:InvokeModel` permission for Titan embedding model. Core stack grants Bedrock access only for Anthropic Claude models.

**Recurrence**: 3rd consecutive day. Not yet fixed.

##### IAM: Bedrock Converse AccessDeniedException — Web Search (1 occurrence)

| Timestamp | Logger | Error |
|-----------|--------|-------|
| 04:52:40 | `eagle.web_search` | `web_search ClientError [AccessDeniedException]: An error occurred (AccessDeniedException) when calling the Converse operation: Not authorized` |

**Root Cause**: Same deploy role IAM gap — missing Converse permission for the model used by web_search.

##### Application Bug: knowledge_search Serialization Errors (2 occurrences)

| Timestamp | Logger | Error |
|-----------|--------|-------|
| 04:44:22 | `eagle.strands_agent` | `knowledge_search serialization error: maximum recursion depth exceeded` |
| 04:44:22 | `eagle.strands_agent` | `knowledge_search serialization error: cannot pickle '_thread.lock' object` |

**Root Cause**: The `_sanitize_item()` function in `knowledge_tools.py:539-560` handles recursion depth but the Strands agent serialization layer encounters objects (OTEL wrappers, thread locks) that bypass the sanitizer. The pickle error suggests the agent SDK is trying to serialize tool results containing non-picklable objects.

**NEW**: Not seen in previous triages.

##### Application Bug: Bedrock Model Misconfiguration — Haiku On-Demand (1 occurrence)

| Timestamp | Logger | Error |
|-----------|--------|-------|
| 04:44:22 | `eagle.knowledge_tools` | `knowledge_search AI ranking failed, falling back: ValidationException... Invocation of model ID anthropic.claude-haiku-4-5-20251001-v1:0 with on-demand throughput isn't supported.` |

**Root Cause**: `config.py:26` (DEFAULT_BEDROCK_HAIKU_MODEL) hardcodes `anthropic.claude-haiku-4-5-20251001-v1:0` which requires a provisioned throughput inference profile, not on-demand. Should use cross-region inference profile `us.anthropic.claude-haiku-4-5-20251001-v1:0` or the latest available Haiku model ID.

**NEW**: Not seen in previous triages.

##### Missing Document Templates (7 occurrences)

| Timestamp | Doc Type | Message |
|-----------|----------|---------|
| 04:51:29 | igce | Template not found, falling back to markdown |
| 04:51:29 | sow | Template not found, falling back to markdown |
| 04:51:11 | acquisition_plan | Template not found, falling back to markdown |
| 04:50:47 | justification | Template not found, falling back to markdown |
| 04:49:31 | market_research | Template not found, falling back to markdown |
| 04:49:01 | igce | Template not found, falling back to markdown |
| 04:48:08 | sow | Template not found, falling back to markdown |

**Root Cause**: Template registry in `template_service.py:452-460` expects templates at S3 paths under `eagle-knowledge-base/approved/supervisor-core/essential-templates/` but none are uploaded for these document types.

**Recurrence**: 3rd consecutive day.

##### Bedrock PDF Validation Errors (3 occurrences)

| Timestamp | Logger | Error |
|-----------|--------|-------|
| 04:52:21 | `eagle.bedrock_document_parser` | `Bedrock Converse failed for test.pdf: ValidationException... The PDF specified was not valid.` |
| 04:52:20 | `eagle.bedrock_document_parser` | Same |
| 04:52:20 | `eagle.bedrock_document_parser` | Same |

**Root Cause**: `bedrock_document_parser.py:123-189` sends raw PDF bytes to Bedrock Converse but does not validate PDF structure before submission. Test suite intentionally tests with invalid PDFs.

##### Streaming Chat Errors (2 occurrences)

| Timestamp | Logger | Error |
|-----------|--------|-------|
| 04:48:03 | `app.streaming_routes` | `Streaming chat error user=u session=s: Bedrock throttle` (RuntimeError) |
| 04:48:03 | `app.streaming_routes` | `Streaming chat error user=u session=s: bad input` (ValueError) |

**Context**: Both originate from test code — the stack trace shows `streaming_routes.py:228` → `_sdk_with_keepalive()`. The "Bedrock throttle" error simulates ThrottlingException behavior.

##### DynamoDB ProvisionedThroughputExceededException (1 occurrence)

| Timestamp | Logger | Error |
|-----------|--------|-------|
| 04:44:23 | `eagle.knowledge_tools` | `knowledge_search DynamoDB error: ProvisionedThroughputExceededException when calling the Scan operation: boom` |

**Context**: Test-generated error simulating DDB throttling. The "boom" message confirms this is a mock exception.

#### `/eagle/ecs/frontend-dev`

| Metric | Value |
|--------|-------|
| Records scanned | 0 |
| Records matched | 0 |

**All clear** — no errors in the last 24h.

#### `/eagle/app`

| Metric | Value |
|--------|-------|
| Records scanned | 0 |
| Records matched | 0 |

**All clear** — no errors in the last 24h.

## Cross-Reference Analysis

### Session Correlation Map

**UNAVAILABLE** — DynamoDB feedback and Langfuse traces could not be queried. No session-level cross-referencing possible.

All CloudWatch errors originated from `localhost` log stream during CI test execution (04:44–04:52 UTC). No ECS task log streams were present, indicating no production user sessions generated errors in this window.

### Error Pattern Clusters

| Cluster | CloudWatch Signal | Langfuse Signal | Feedback Signal | Sessions |
|---------|------------------|-----------------|-----------------|----------|
| **IAM/Permissions** | 6 AccessDeniedException (DDB Scan + Bedrock InvokeModel + Converse) | N/A | N/A | 0 (CI only) |
| **Missing Templates** | 7 "Template not found" warnings | N/A | N/A | 0 (CI only) |
| **Serialization Bugs** | 2 serialization errors (recursion + pickle) | N/A | N/A | 0 (CI only) |
| **Model Config** | 1 Haiku on-demand ValidationException | N/A | N/A | 0 (CI only) |
| **PDF Validation** | 3 "PDF not valid" ValidationException | N/A | N/A | 0 (CI only) |
| **Bedrock Rate Limit** | 1 ThrottlingException + 1 Timeout | N/A | N/A | 0 (CI only) |

### Trend Analysis

| Metric | 2026-04-21 | 2026-04-22 | 2026-04-23 | Trend |
|--------|------------|------------|------------|-------|
| Records scanned | — | 27,680 | 36,198 | +31% |
| Records matched | — | 481 | 1,370 | +185% (more test coverage) |
| Tests passed | — | 1,521 | 1,580 | +59 tests |
| Tests failed | — | 18 | 7 | -11 failures (improving) |
| Pass rate | — | 98.8% | 99.6% | Improving |
| IAM errors | recurring | 4 | 6 | Stable (unresolved) |
| Template errors | recurring | 5 | 7 | Stable (unresolved) |
| Serialization bugs | not seen | not seen | 2 | NEW |
| Model config errors | not seen | not seen | 1 | NEW |
| Frontend errors | 0 | 0 | 0 | Clean |
| App errors | 0 | 0 | 0 | Clean |

**Key trends**:
- Test suite is improving (+59 tests, -11 failures)
- IAM permission gaps persist for 3+ days — need CDK fix
- Two new bug categories emerged: serialization and model configuration
- Frontend and app log groups remain consistently clean
- All errors are from CI test runs, not production ECS tasks

## Prioritized Issue List

| # | Issue | Severity | Score | Sources | Recurrence |
|---|-------|----------|-------|---------|------------|
| 1 | IAM: Deploy role missing `dynamodb:Scan` on `eagle-document-metadata-dev` | **P1** | 5 | CW | 3 days |
| 2 | IAM: Deploy role missing `bedrock:InvokeModel` for Titan Embed v2 | **P1** | 5 | CW | 3 days |
| 3 | IAM: Deploy role missing Converse permission for web_search | **P1** | 4 | CW | 2+ days |
| 4 | Missing DOCX templates for 5 document types | **P1** | 4 | CW | 3 days |
| 5 | knowledge_search serialization: recursion + pickle errors | **P1** | 4 | CW | NEW |
| 6 | Haiku model config: on-demand throughput not supported | **P2** | 2 | CW | NEW |
| 7 | PDF validation: no pre-check before Bedrock Converse | **P2** | 2 | CW | Recurring |
| 8 | CI hook blocker: Windows path in settings.json | **P2** | 3 | Infra | 3 days |

**Note**: No P0 issues found. All errors are from CI test runs, not production traffic. Issues are P1 because they cause test failures and would impact production if the same code paths are exercised by users.

## Noise Report

| Category | Count | Justification |
|----------|-------|---------------|
| Test-generated tool errors (`boom_tool: kaboom`) | 1 | Intentional test — `test_tool_dispatch.py:120` raises RuntimeError |
| Test-generated DDB failures (save/list/get test runs) | 4 | Intentional — tests simulate DDB unreachable/timeout/down |
| Test-generated session preloader errors | 2 | Intentional — `test_session_preloader.py:227` mock side effects |
| Test-generated supervisor budget exhausted | 1 | Intentional — `test_max_tokens_retry` mock exception |
| Test-generated MagicMock AI ranking failures | 8 | Intentional — tests pass MagicMock instead of real Bedrock response |
| Test-generated streaming errors (bad input) | 1 | Intentional — tests simulate ValueError |
| Test-generated CloudWatch emit failure | 1 | Intentional — tests simulate CloudWatch down |
| Test-generated export failure ("bad" doc) | 1 | Intentional — tests exercise error path |
| Test-generated web_fetch DNS error (wind.example.com) | 1 | Intentional — uses fake domain |
| Test-generated web_search timeout | 1 | Intentional — tests timeout path |
| Test-generated triage dispatch 422 | 1 | Intentional — tests validation error |
| Test-generated S3 NoSuchKey (test-tenant) | 1 | Intentional — tests missing object path |
| Test-generated MaxTokens retry warning | 1 | Intentional — tests retry behavior |
| DDB ProvisionedThroughputExceededException ("boom") | 1 | Intentional — mock DDB throttle |
| HTTP 500 on testserver | 1 | Intentional — test endpoint |
| **Total noise filtered** | **27** | |
