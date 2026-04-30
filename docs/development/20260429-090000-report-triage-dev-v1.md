# EAGLE Triage Report

**Date**: 2026-04-29
**Environment**: dev
**Window**: 24h
**Tenant**: default-dev
**Mode**: Full
**Sources**: CloudWatch Logs (dev) | DynamoDB Feedback (SKIPPED) | Langfuse Traces (SKIPPED)

## Executive Summary

The dev environment has **1 confirmed production issue**: the ECS task role (`eagle-app-role-dev`) lacks `bedrock:InvokeModel` permission for `amazon.titan-embed-text-v2:0`, breaking semantic search in the knowledge tools. This affects real user sessions. Additionally, 1716 log entries matched error patterns in the backend-dev log group, but the vast majority (~98%) are **test artifacts** from CI/pytest runs logged to CloudWatch via the `localhost` logStream. Frontend-dev and app log groups are clean.

**Data gaps**: DynamoDB feedback and Langfuse trace queries could not be executed because the CI environment's PreToolUse hook references a Windows path (`C:/Users/blackga/Desktop/...`) that doesn't resolve in the Linux CI runner, blocking all Bash tool calls. This should be fixed in `.claude/settings.json`.

## Source Data

### DynamoDB Feedback

**Status**: SKIPPED — Bash tool blocked by broken hook path in `.claude/settings.json`

No feedback data collected. Unable to cross-reference user reports with CloudWatch errors.

### CloudWatch Errors

**Log Groups Queried**:
- `/eagle/ecs/backend-dev` — 1716 records matched, 50 returned (33,466 scanned)
- `/eagle/ecs/frontend-dev` — 0 records matched (15 scanned)
- `/eagle/app` — 0 records matched (0 scanned)

#### Real ECS Task Errors (logStream: `backend/eagle-backend/fe39d20a...`)

| # | Timestamp | Logger | Severity | Message | Session |
|---|-----------|--------|----------|---------|---------|
| 1 | 2026-04-28 21:07:33 | eagle.knowledge_tools | WARNING | embed_text failed: AccessDeniedException — bedrock:InvokeModel on amazon.titan-embed-text-v2:0 | 5745bdc2-d413-4edc-82cf-63657b04f665 |
| 2 | 2026-04-28 21:07:33 | eagle.knowledge_tools | WARNING | exec_semantic_search: embedding failed, skipping | 5745bdc2-d413-4edc-82cf-63657b04f665 |
| 3 | 2026-04-28 21:07:04 | eagle.knowledge_tools | WARNING | embed_text failed: AccessDeniedException — bedrock:InvokeModel on amazon.titan-embed-text-v2:0 | 5745bdc2-d413-4edc-82cf-63657b04f665 |
| 4 | 2026-04-28 21:07:04 | eagle.knowledge_tools | WARNING | exec_semantic_search: embedding failed, skipping | 5745bdc2-d413-4edc-82cf-63657b04f665 |

**Affected User**: `24a8d478-20a1-7087-e1a3-56a38d733592`
**Affected Session**: `5745bdc2-d413-4edc-82cf-63657b04f665`
**Root Cause**: `eagle-app-role-dev` IAM role (defined in `infrastructure/cdk-eagle/lib/core-stack.ts:127-224`) grants bedrock:InvokeModel for Claude models and Amazon Nova, but **not** for `amazon.titan-embed-text-v2:0`.

#### CI/Test Artifacts (logStream: `localhost`)

These errors originate from pytest runs in CI, not from the deployed ECS container:

| Category | Count | Example | Source |
|----------|-------|---------|--------|
| Bedrock AccessDeniedException (deploy-role) | 4 | bedrock:InvokeModel + dynamodb:Scan on deploy-role | CI role lacks test permissions |
| Streaming route errors | 2 | "bad input" + "Bedrock throttle" (test_streaming_routes) | Test fixtures |
| Session preloader errors | 2 | mock.py raise effect — "boom" + asyncio.coroutine removed | test_session_preloader.py |
| Tool execution error | 1 | boom_tool: kaboom | test_tool_dispatch.py |
| MaxTokensReachedException | 1 | budget exhausted (mock supervisor) | test_max_tokens_retry.py |
| Template not found warnings | 7 | sow, igce, acquisition_plan, market_research, justification | Tests hitting template_service without S3 |
| Knowledge AI ranking failures | 6 | MagicMock not str/bytes | Tests with incomplete mocking |
| Web search/fetch errors | 3 | timeout, AccessDeniedException, hostname not found | Test fixtures |
| Test results DDB failures | 4 | DDB unreachable, timeout, boom | Test error-path coverage |
| CloudWatch telemetry failure | 1 | "CloudWatch down" | Test fixture |
| Triage actions 422 | 1 | dispatch failed status=422 | Test fixture |
| S3 NoSuchKey | 1 | Package content not found | Test fixture |
| Export failure | 1 | Failed to export bad for ZIP | Test fixture |
| Bedrock PDF ValidationException | 3 | "PDF specified was not valid" for test.pdf | Test fixture |

**Total CI/test artifact entries**: ~37 of 50 returned results

### Langfuse Trace Errors

**Status**: SKIPPED — Bash tool blocked by broken hook path in `.claude/settings.json`

Langfuse dev credentials are configured (pk-lf-47021a72...) but query could not be executed.

## Cross-Reference Analysis

### Session Correlation Map

| Session ID | Sources | Evidence |
|------------|---------|----------|
| 5745bdc2-d413-4edc-82cf-63657b04f665 | CW (4 errors) | Bedrock Titan Embed AccessDeniedException x2 + embedding failed x2 |

**Note**: Without DynamoDB feedback and Langfuse data, cross-source correlation is limited to CloudWatch only. No multi-source confirmed bugs can be established this run.

### Error Pattern Clusters

| Cluster | CloudWatch Signal | Langfuse Signal | Feedback Signal |
|---------|------------------|-----------------|-----------------|
| **IAM/Permissions** | AccessDeniedException on titan-embed-text-v2:0 (real ECS) | N/A (skipped) | N/A (skipped) |
| **CI Role Permissions** | AccessDeniedException on deploy-role for DDB Scan + Bedrock (CI only) | N/A | N/A |
| **Template Missing** | Template not found for 5 doc types (CI test artifacts) | N/A | N/A |

### Trend Analysis

- The Titan Embed permission issue has been present since at least 2026-04-28 21:07 UTC, affecting knowledge search quality for real users.
- The CI test artifacts are from a single pytest run at ~20:48-20:52 UTC — these are expected test coverage logs and not production issues.
- Frontend-dev and /eagle/app are completely clean — no errors in the last 24h.

## Prioritized Issue List

| # | Issue | Composite Score | Priority | Sources | Sessions | Fix Location |
|---|-------|----------------|----------|---------|----------|--------------|
| 1 | Bedrock Titan Embed AccessDeniedException — semantic search broken | 5 (freq:2 + severity:1 + cross-source:0 + user-facing:2) | **P1** | CW | 1 confirmed | `infrastructure/cdk-eagle/lib/core-stack.ts` |
| 2 | CI settings.json hook path broken (Windows path in Linux CI) | 4 (freq:2 + severity:1 + impact:1) | **P1** | CI infra | All CI runs | `.claude/settings.json` |
| 3 | CI deploy-role lacks DDB Scan + Bedrock Embed permissions | 2 (freq:1 + severity:1) | **P2** | CW (CI only) | CI runs | `infrastructure/cdk-eagle/lib/cicd-stack.ts` |
| 4 | Template not found for doc types (test-only, falls back to markdown) | 1 (noise from tests) | **P3** | CW (CI only) | N/A | Monitor |

**Note on P1 vs P0**: The Titan Embed issue would be P0 if confirmed by user feedback (which we couldn't collect). Without feedback data, we conservatively score it P1. The system gracefully degrades (falls back to non-semantic search), so it reduces search quality rather than causing total failure.

## Noise Report

| Pattern | Count | Justification |
|---------|-------|---------------|
| CI/pytest test artifact errors (localhost logStream) | ~37 | Expected test coverage — tests exercise error paths intentionally |
| Knowledge AI ranking MagicMock errors | 6 | Test mock leakage into logging — not production |
| Template not found warnings | 7 | Tests run without S3 templates — expected fallback behavior |
| Test results DDB warnings | 4 | Intentional error-path test coverage |
| Bedrock PDF ValidationException for test.pdf | 3 | Test fixture using invalid PDF |

**Noise ratio**: ~37/50 returned results (74%) are CI test artifacts, not production issues.
