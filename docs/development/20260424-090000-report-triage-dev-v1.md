# EAGLE Triage Report

**Date**: 2026-04-24
**Environment**: dev
**Window**: 24h (2026-04-23 00:00 UTC to 2026-04-24 23:59 UTC)
**Tenant**: default-dev
**Mode**: Full
**Sources**: CloudWatch Logs (dev) | DynamoDB Feedback (UNAVAILABLE) | Langfuse Traces (UNAVAILABLE)

## Executive Summary

Three IAM permission gaps are blocking knowledge search, semantic embedding, and document metadata operations in the dev environment. The `eagle-deploy-role-dev` lacks `dynamodb:Scan` on `eagle-document-metadata-dev` and `bedrock:InvokeModel` on `amazon.titan-embed-text-v2:0`. Additionally, a Bedrock signature expiration event triggered the circuit breaker for `us.anthropic.claude-sonnet-4-6`, opening after 56 consecutive failures. All 828 error records originated from the `localhost` logStream (CI/test runs), but the IAM issues would equally affect the live ECS service. Frontend-dev and app logs were clean (zero errors).

**Data Gap**: DynamoDB feedback and Langfuse trace queries could not be executed due to a broken PreToolUse hook in `.claude/settings.json` (Windows-specific path `C:/Users/blackga/...` on Linux CI). Cross-reference analysis is limited to CloudWatch only.

## Source Data

### DynamoDB Feedback

**STATUS: UNAVAILABLE** — Bash tool blocked by broken PreToolUse hook (Windows path on Linux CI). Cannot run boto3 queries.

### CloudWatch Errors

**Log groups queried:**
- `/eagle/ecs/backend-dev` — 828 records matched, 50 returned (30,167 scanned)
- `/eagle/ecs/frontend-dev` — 0 records matched (10 scanned)
- `/eagle/app` — 0 records matched (0 scanned)

**Note**: All backend-dev errors originated from `@logStream: localhost`, indicating CI/test runs rather than live ECS tasks. However, IAM permission errors would also affect production since they reference the same deploy role.

#### ACTIONABLE Errors

| # | Timestamp | Logger | Error | Category | Count |
|---|-----------|--------|-------|----------|-------|
| 1 | 17:32:18 | eagle.knowledge_tools | `AccessDeniedException: dynamodb:Scan on eagle-document-metadata-dev` — role `eagle-deploy-role-dev` not authorized | IAM Missing Permission | 2 |
| 2 | 17:32:18 | eagle.knowledge_tools | `AccessDeniedException: bedrock:InvokeModel on amazon.titan-embed-text-v2:0` — role `eagle-deploy-role-dev` not authorized | IAM Missing Permission | 1 |
| 3 | 17:37:05 | eagle.web_search | `AccessDeniedException: Converse operation: Not authorized` | IAM Missing Permission | 1 |
| 4 | 20:59:50 | eagle.strands_agent | `InvalidSignatureException: Signature expired` — 40-min clock skew detected, circuit breaker opened (56 failures) | Credential/Clock Skew | 3 |
| 5 | 17:36:39-40 | eagle.bedrock_document_parser | `ValidationException: The PDF specified was not valid` for test.pdf | Data Quality | 3 |
| 6 | 17:34:42 | eagle.document_service | `S3 upload failed: InternalServerError on PutObject` | AWS Infrastructure | 1 |
| 7 | 17:34:42 | eagle.document_service | `S3 upload failed: Read timeout on endpoint URL` | AWS Infrastructure | 1 |
| 8 | 17:34:42 | eagle.document_service | `Failed to create document record: Connect timeout on DynamoDB` | AWS Infrastructure | 1 |
| 9 | 17:32:39 | app.streaming_routes | `Streaming chat error: Bedrock throttle` | Model Issues | 1 |
| 10 | 17:32:39 | app.streaming_routes | `Streaming chat error: bad input (ValueError)` | Application Bug | 1 |

#### Warning Errors

| # | Timestamp | Logger | Warning | Category | Count |
|---|-----------|--------|---------|----------|-------|
| 11 | 17:32-17:34 | eagle.template_service | `Template not found for {sow,igce,acquisition_plan,justification,market_research}, falling back to markdown` | Missing Templates | 6 |
| 12 | 17:35:15 | eagle.packages | `NoSuchKey: Failed to fetch content for PKG-2026-0042 Acquisition-Plan.md` | Data Quality | 1 |
| 13 | 17:35:15 | app.routers.triage_actions | `triage_actions: dispatch failed status=422 body=Unprocessable` | Application Bug | 1 |
| 14 | 17:32:18 | eagle.knowledge_tools | `exec_semantic_search: embedding failed, skipping` (follows AccessDenied) | IAM Cascade | 1 |
| 15 | 17:32:40 | eagle.telemetry.cloudwatch | `Failed to emit telemetry event: CloudWatch down` | Test Mock | 1 |

### Langfuse Trace Errors

**STATUS: UNAVAILABLE** — Bash tool blocked by broken PreToolUse hook. Langfuse credentials are configured (`pk-lf-47021a72...`), but Python/httpx query cannot be executed.

## Cross-Reference Analysis

### Session Correlation Map

Cross-referencing not possible — DynamoDB feedback and Langfuse data unavailable. Only CloudWatch errors were collected.

### Error Pattern Clusters

| Cluster | CloudWatch Signal | Langfuse Signal | Feedback Signal |
|---------|------------------|-----------------|-----------------|
| **IAM/Permissions** | 4 AccessDeniedException errors across DynamoDB Scan, Bedrock InvokeModel, Bedrock Converse | N/A | N/A |
| **Credential Expiry** | InvalidSignatureException with 40-min clock skew, circuit breaker opened | N/A | N/A |
| **Data Quality** | 3 invalid PDF errors, 1 S3 NoSuchKey | N/A | N/A |
| **AWS Timeouts** | S3 Read timeout, DynamoDB Connect timeout | N/A | N/A |
| **Template Gaps** | 6 template-not-found warnings across 5 doc types | N/A | N/A |

### Trend Analysis

All CloudWatch errors occurred in a concentrated 5-minute window (17:32-17:37) from a single CI test run, plus one cluster at 20:59:50 (circuit breaker event). The CI test run pattern suggests these are test-generated but the IAM errors represent real permission gaps. The circuit breaker event at 20:59 with 56 failures is concerning — it indicates sustained Bedrock unavailability, possibly from credential rotation.

No increasing trend detected within the 24h window — errors are clustered, not spread across time.

## Prioritized Issue List

### P1 — Fix This Sprint (Score 4-5)

| # | Issue | Severity Score | Sources | Evidence |
|---|-------|---------------|---------|----------|
| 1 | **IAM: eagle-deploy-role-dev lacks dynamodb:Scan on eagle-document-metadata-dev** | 5 (freq=2, actionable=1, cross-source=0, user-facing=2) | CW | `knowledge_search` and `exec_path_search` both fail with AccessDeniedException |
| 2 | **IAM: eagle-deploy-role-dev lacks bedrock:InvokeModel for amazon.titan-embed-text-v2:0** | 4 (freq=1, actionable=1, cross-source=0, user-facing=2) | CW | Semantic search embedding completely broken |
| 3 | **Bedrock Signature Expired / Circuit Breaker** | 4 (freq=3, actionable=1, cross-source=0, user-facing=0) | CW | 56 failures, circuit breaker opened for claude-sonnet-4-6 |

### P2 — Backlog (Score 2-3)

| # | Issue | Severity Score | Sources | Evidence |
|---|-------|---------------|---------|----------|
| 4 | **Missing document templates (sow, igce, acquisition_plan, justification, market_research)** | 3 (freq=6, actionable=0, cross-source=0, user-facing=1) | CW | Falls back to markdown — functional but degraded output quality |
| 5 | **Invalid PDF handling in Bedrock document parser** | 2 (freq=3, actionable=1, cross-source=0, user-facing=0) | CW | test.pdf fails validation — need better pre-validation |
| 6 | **IAM: Bedrock Converse AccessDeniedException for web_search** | 3 (freq=1, actionable=1, cross-source=0, user-facing=1) | CW | Web search tool completely non-functional |

### P3 — Monitor (Score 0-1)

| # | Issue | Severity Score | Sources | Evidence |
|---|-------|---------------|---------|----------|
| 7 | **S3/DynamoDB timeouts during document operations** | 1 (freq=2, actionable=0) | CW | Likely transient — from test environment |
| 8 | **Streaming chat Bedrock throttle** | 1 (freq=1, actionable=0) | CW | From test, but retry logic should handle |
| 9 | **PreToolUse hook uses Windows-specific path** | 1 (config issue) | CI | Blocks Bash in CI; file: `.claude/settings.json` |

## Noise Report

| Pattern | Count | Justification |
|---------|-------|---------------|
| Test mock errors (boom_tool kaboom, DDB down, webhook refused) | ~15 | Stack traces reference `unittest/mock.py`, test fixture error messages ("kaboom", "boom", "DDB down") |
| httpx test request logs (POST testserver/api/errors/report) | ~10 | Test server requests, not production traffic |
| web_fetch `wind.example.com` DNS failure | 1 | Test fixture URL, not a real endpoint |
| Error webhook rate-limited/timed-out/failed | 3 | Test mocks, ConnectionError with mock paths |
| CloudWatch telemetry "CloudWatch down" | 1 | Test mock failure message |
| Test results DDB failures (DDB down/unreachable/timeout) | 3 | Test mock failure messages |

**Total noise filtered**: ~33 entries out of 50 returned (~66%)
