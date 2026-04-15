# EAGLE Triage Report

**Date**: 2026-04-15
**Environment**: dev
**Window**: 24h
**Tenant**: default-dev
**Mode**: Full
**Sources**: DynamoDB Feedback (UNAVAILABLE), CloudWatch Logs (dev), Langfuse Traces (UNAVAILABLE)

## Executive Summary

The dev environment has **4 actionable issues** and **2 warnings** from 542 CloudWatch error matches in the backend over the last 24 hours. The most critical problem is **missing IAM permissions** on `eagle-app-role-dev` for Bedrock Titan Embed and S3 Vectors — this completely breaks semantic search / knowledge base queries for all users (10+ failures across 3 sessions). Two application bugs — a `resolve_template()` argument-order error and a Float-to-DynamoDB type error — also block document creation and template management. Frontend and `/eagle/app` logs are clean. DynamoDB feedback and Langfuse traces could not be queried due to a CI environment limitation (broken PreToolUse hook blocking Bash execution).

## Data Source Gaps

> **DynamoDB Feedback** and **Langfuse Traces** were **not collected** this run. The `.claude/settings.json` contains a PreToolUse hook referencing a Windows-only path (`C:/Users/blackga/...`) that does not exist on the Linux CI runner, blocking all Bash tool calls. The CloudWatch MCP tool was unaffected, so CloudWatch data is complete. Fix: update the hook path in `.claude/settings.json` to use a repo-relative path, or remove it for CI.

## Source Data

### DynamoDB Feedback

**Status**: NOT AVAILABLE — Bash tool blocked by broken PreToolUse hook in CI.

### CloudWatch Errors

**Log Group: `/eagle/ecs/backend-dev`** — 542 records matched, 50 returned

| # | Timestamp | Severity | Category | Session ID | Error Summary |
|---|-----------|----------|----------|------------|---------------|
| 1 | 2026-04-14 18:22:14 | ERROR | Application Bug | `88fa6c56-...` | `resolve_template() got multiple values for argument 'user_id'` |
| 2 | 2026-04-14 18:05:39 | ERROR | Application Bug | `2b08baa0-...` | `Float types are not supported. Use Decimal types instead` (DynamoDB put_item) |
| 3 | 2026-04-14 18:21:57 | WARNING | IAM Permission | `88fa6c56-...` | `AccessDeniedException: s3vectors:QueryVectors` on `rh-eagle/index/eagle-kb-approved` |
| 4 | 2026-04-14 18:18:50 | WARNING | IAM Permission | `88fa6c56-...` | `AccessDeniedException: s3vectors:QueryVectors` (repeat) |
| 5 | 2026-04-14 18:17:29 | WARNING | IAM Permission | `88fa6c56-...` | `AccessDeniedException: s3vectors:QueryVectors` (repeat) |
| 6 | 2026-04-14 18:00:20 | WARNING | IAM Permission | `2b08baa0-...` | `AccessDeniedException: bedrock:InvokeModel` for `amazon.titan-embed-text-v2:0` |
| 7 | 2026-04-14 18:00:19 | WARNING | IAM Permission | `2b08baa0-...` | `AccessDeniedException: bedrock:InvokeModel` for Titan Embed (repeat) |
| 8 | 2026-04-14 17:32:40 | WARNING | IAM Permission | `5f95bae5-...` | `AccessDeniedException: bedrock:InvokeModel` for Titan Embed (repeat) |
| 9 | 2026-04-14 17:06:12 | WARNING | IAM Permission | `2b08baa0-...` | `embed_text failed: AccessDeniedException` for Titan Embed (repeat) |
| 10 | 2026-04-14 17:01:21 | WARNING | IAM Permission | `2b08baa0-...` | `embed_text failed: AccessDeniedException` for Titan Embed (repeat) |
| 11 | 2026-04-14 16:57:15 | WARNING | IAM Permission | `2b08baa0-...` | `embed_text failed: AccessDeniedException` for Titan Embed (3x repeat) |
| 12-30 | Multiple | WARNING | Data Quality | `88fa6c56-...`, `2b08baa0-...` | `estimated_value` parsing: `'$750,000'` cannot be parsed as float (~20 entries) |
| 31-34 | Multiple | WARNING | Data Quality | `88fa6c56-...`, `2b08baa0-...` | Unknown doc_type: `section_889`, `priority_sources_checklist` (4 entries) |

**Log Group: `/eagle/ecs/frontend-dev`** — 0 records matched. Clean.

**Log Group: `/eagle/app`** — 0 records matched. Clean.

### Langfuse Trace Errors

**Status**: NOT AVAILABLE — Bash tool blocked by broken PreToolUse hook in CI. Langfuse credentials ARE configured (public key: `pk-lf-47021a72...`).

## Cross-Reference Analysis

### Session Correlation Map

| Session ID | CloudWatch Errors | Langfuse | Feedback | Notes |
|------------|-------------------|----------|----------|-------|
| `88fa6c56-3757-40c5-a9bb-365d29ec5f72` | resolve_template() TypeError, S3 Vectors AccessDenied (3x), estimated_value warnings | N/A | N/A | Template + knowledge search both broken in single session |
| `2b08baa0-9760-4175-836f-01556618eb9e` | Float DynamoDB TypeError, Bedrock Embed AccessDenied (5x), estimated_value warnings | N/A | N/A | Document creation + search both broken |
| `5f95bae5-b1b9-4567-a32e-0570ce811ee2` | Bedrock Embed AccessDenied (2x) | N/A | N/A | Knowledge search broken |

> **Note**: Cross-referencing is limited to CloudWatch only. DynamoDB feedback and Langfuse traces unavailable this run.

### Error Pattern Clusters

| Cluster | CloudWatch Signal | Count | Sessions Affected |
|---------|------------------|-------|-------------------|
| **IAM/Permissions** | `AccessDeniedException` for `s3vectors:QueryVectors` and `bedrock:InvokeModel` (Titan Embed) | 13+ | 3 |
| **Application Bug: Templates** | `resolve_template() got multiple values for argument 'user_id'` | 1 | 1 |
| **Application Bug: DynamoDB Types** | `Float types are not supported. Use Decimal types instead` | 1 | 1 |
| **Data Quality: Value Parsing** | `estimated_value` — `'$750,000'` fails float parsing | 20+ | 2 |
| **Data Quality: Unknown Doc Types** | `section_889`, `priority_sources_checklist` not recognized | 4+ | 2 |

### Trend Analysis

- **IAM permission errors are persistent** — they appear continuously from 16:57 through 18:22 across all 3 sessions. This indicates the permissions have never been granted, not a transient issue.
- **Document validation warnings cluster together** — all in a single burst around 18:08–18:22, suggesting one user session triggering multiple document generation calls with the same `$750,000` value.
- **No container crashes or OOM events** detected — the ECS tasks are stable.
- **No frontend errors** — the Next.js frontend is healthy.

## Prioritized Issue List

| # | Issue | Severity | Score | Sources | Sessions | Root Cause |
|---|-------|----------|-------|---------|----------|------------|
| 1 | **Bedrock Titan Embed AccessDenied** — `eagle-app-role-dev` lacks `bedrock:InvokeModel` for `amazon.titan-embed-text-v2:0` | **P0** | 6 | CW | 3 | IAM policy missing Titan Embed model ARN |
| 2 | **S3 Vectors AccessDenied** — `eagle-app-role-dev` lacks `s3vectors:QueryVectors` on `rh-eagle/index/eagle-kb-approved` | **P1** | 5 | CW | 1 | IAM policy missing S3 Vectors permission |
| 3 | **Float-to-DynamoDB TypeError** — `document_service.py` passes Python `float` to DynamoDB `put_item()` | **P1** | 4 | CW | 1 | `estimated_value` stored as float, not Decimal |
| 4 | **resolve_template() argument error** — positional args in wrong order in `admin_tools.py` | **P1** | 4 | CW | 1 | Function call passes (tenant_id, doc_type, user_id=...) but signature expects (tenant_id, user_id, doc_type) |
| 5 | **estimated_value currency parsing** — `$750,000` fails Pydantic float validation | **P2** | 3 | CW | 2 | Schema uses `Optional[float]` with no currency-string preprocessor |
| 6 | **Unknown doc_type warnings** — `section_889`, `priority_sources_checklist` not recognized | **P3** | 1 | CW | 2 | Doc types not registered in schema; fallback to BaseDocumentData works |

## Noise Report

| Item | Count | Classification | Justification |
|------|-------|----------------|---------------|
| "Failed to link package PKG-2026-0001 to session test-session" | 1 | Test artifact | Logged from `localhost` logStream with mock stack trace (`unittest.mock`); test run, not production error |
| "Saved test run: 68 passed, 0 failed" / "64 passed, 0 failed" | 2 | Test artifact | Test result messages matched `fail` keyword but are actually passing test notifications |
| `estimated_value` INFO-level "Document payload normalized with warnings" | 10+ | Duplicate of WARNING | Same event logged at both INFO and WARNING level; counted once under issue #5 |
