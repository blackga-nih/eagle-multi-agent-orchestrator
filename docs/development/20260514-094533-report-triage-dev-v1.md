# EAGLE Triage Report

**Date**: 2026-05-14
**Environment**: dev
**Window**: 24h
**Tenant**: default-dev
**Mode**: Full
**Sources**: DynamoDB Feedback, CloudWatch Logs (dev), Langfuse Traces (dev)

## Executive Summary

The dev environment has a **systemic SSO token expiration** causing all Bedrock agent invocations to fail — 10 of 11 real Langfuse errors are `Token has expired and refresh failed`. Additionally, the IGCE document template is corrupt (BadZipFile) causing template generation to fall back to markdown, and an S3 PutObject AccessDenied is blocking document saves. No user feedback was submitted in the last 24h, so these are backend-only signals without user-impact correlation. The frontend and `/eagle/app` log groups are clean.

## Source Data

### DynamoDB Feedback

| Metric | Count |
|--------|-------|
| General feedback (bug, suggestion, etc.) | 0 |
| Message feedback (thumbs up/down) | 0 |

No feedback items found for `FEEDBACK#default-dev` in the last 24h. No session IDs to cross-reference.

### CloudWatch Errors

**Log group: `/eagle/ecs/backend-dev`** — 457 records matched, 50 returned

| # | Timestamp | Category | Severity | Message Summary |
|---|-----------|----------|----------|-----------------|
| 1 | 2026-05-13 20:44:02 | S3 IAM | **ACTIONABLE** | `Failed to save document to S3: AccessDenied on PutObject` |
| 2 | 2026-05-13 20:44:33 | Data Quality | **ACTIONABLE** | `Template generation failed for igce: File is not a zip file` |
| 3 | 2026-05-13 20:44:02 | Data Quality | **ACTIONABLE** | `Template generation failed for igce: File is not a zip file` |
| 4 | 2026-05-13 20:41:42 | Data Quality | **ACTIONABLE** | `Template generation failed for igce: File is not a zip file` |
| 5 | 2026-05-13 20:40:40 | Test-generated | Noise | `create_document failed: S3 upload failed` (from test_create_document_observability.py) |
| 6 | 2026-05-13 20:40:39–40 | Test-generated | Noise | Circuit breaker warnings x24 (failures=1–123, from test execution) |
| 7 | 2026-05-13 19:49:22 | Test-generated | Noise | `Tool execution error (boom_tool): kaboom` (from test_tool_dispatch.py) |
| 8 | 2026-05-13 19:49:22 | Test-generated | Noise | Test results save/list failures x4 (simulated DDB failures) |
| 9 | 2026-05-13 19:49:31 | Test-generated | Noise | `S3 NoSuchKey` for test-tenant package, `triage_actions: dispatch failed 422` |
| 10 | 2026-05-13 19:51:03 | Info | Noise | `Error webhook configured` (INFO level, matched on keyword "Error") |

**Log group: `/eagle/ecs/frontend-dev`** — 0 records matched. Clean.

**Log group: `/eagle/app`** — 0 records matched. Clean.

### Langfuse Trace Errors

| Metric | Value |
|--------|-------|
| Total traces | 82 |
| Orphan traces filtered | 33 |
| Real error traces | 11 |
| Sub-span stubs (output=null, no error) | 34 |
| Successful traces | 4 |
| Success rate (non-orphan) | 8.2% |
| Avg latency | 2ms |
| Total cost | $0.3234 |
| Unique users | 6 |

**Error traces by category:**

| Category | Count | Traces | Severity |
|----------|-------|--------|----------|
| SSO Token Expired | 10 | `invoke_agent Strands Agents` — `Token has expired and refresh failed` | **ACTIONABLE** |
| TypeError in exception handling | 1 | `TypeError: catching classes that do not inherit from BaseException is not allowed` (user: test-user, cost: $0.065) | **ACTIONABLE** |
| Sub-span stubs (kb_search, semantic, s3_fetch, eagle-query) | 34 | output=null, cost=0, no error message — test sub-operations | Noise |

**SSO-expired trace details:**

| Trace ID (short) | Session | User | Latency |
|------------------|---------|------|---------|
| `3f55327f` | ses-001 | dev-user | 1.1ms |
| `ff6ff12b` | a503a045-... | dev-user | 1.0ms |
| `90ea16e5` | 06af264e-... | dev-user | 0.3ms |
| `b4baf512` | ses-alice | alice-chat-uuid | 2.4ms |
| `703c7adb` | ses-no-auth | dev-user | 0.2ms |
| `b5344583` | ses-a-iso | alice-iso | 0.3ms |
| `ea05773a` | ses-b-iso | bob-iso | 0.3ms |
| `0b5c90a5` | (none) | dev-user | 0.3ms |
| `55c2cd7c` | (none) | dev-user | 0.9ms |
| `2d500ab7` | (none) | test-user | 0.3ms |
| `dd3d0059` | (none) | test-user | 0.3ms |

## Cross-Reference Analysis

### Session Correlation Map

No DynamoDB feedback sessions exist to cross-reference. Correlation is limited to CloudWatch ↔ Langfuse.

| Session | Langfuse Error | CloudWatch Error | Feedback |
|---------|---------------|-----------------|----------|
| ses-001 | SSO expired | — | — |
| ses-alice | SSO expired | — | — |
| ses-a-iso | SSO expired | — | — |
| ses-b-iso | SSO expired | — | — |
| ses-no-auth | SSO expired | — | — |
| test-tenant#advanced#test-user#sess-obs-001 | — | S3 upload failed (test) | — |

No sessions appear in 2+ real (non-test) sources, so no cross-source correlation bonus applies.

### Error Pattern Clusters

| Cluster | CloudWatch Signal | Langfuse Signal | Feedback Signal | Combined Count |
|---------|------------------|-----------------|-----------------|----------------|
| **IAM/SSO** | S3 PutObject AccessDenied (1) | SSO token expired (10) | — | 11 |
| **Data Quality** | BadZipFile IGCE template (3) | — | — | 3 |
| **Application Bug** | — | TypeError catching non-BaseException (1) | — | 1 |
| **Test Noise** | Circuit breaker (24), boom_tool (1), test results (4), triage dispatch (1) | Sub-span stubs (34) | — | 64 (filtered) |

### Trend Analysis

- **SSO expiration is systemic**: All 10 SSO errors occurred within a 25-minute window (15:02–15:27 UTC on 2026-05-13), suggesting the ECS task's SSO session expired and was never refreshed. Every agent invocation after expiry failed.
- **BadZipFile is repeating**: 3 occurrences in 3 minutes (20:41–20:44 UTC) for the same `igce` template type. The IGCE template file in S3 is corrupt.
- **Test noise dominates volume**: 64 of 79 total CloudWatch + Langfuse errors are from test execution. The 457 matched records in CloudWatch are heavily inflated by 24 circuit breaker warnings from a single test run.
- **No time-of-day pattern**: All errors occurred during CI/test execution windows, not during user business hours.

## Prioritized Issue List

| # | Issue | Severity | Score | Sources | Sessions | Evidence |
|---|-------|----------|-------|---------|----------|----------|
| 1 | **SSO token expiration blocks all Bedrock agent invocations** | **P1** | 5 | LF(10) + CW(1) | 7 | `Token has expired and refresh failed` on every `invoke_agent` call; S3 AccessDenied likely related |
| 2 | **IGCE template file corrupt (BadZipFile)** | **P2** | 2 | CW(3) | — | `File is not a zip file` when loading IGCE XLSX template from S3 |
| 3 | **S3 PutObject AccessDenied on document save** | **P2** | 2 | CW(1) | — | `AccessDenied when calling PutObject` in document_generation; may be SSO-related |
| 4 | **TypeError: catching non-BaseException class** | **P3** | 1 | LF(1) | — | `TypeError: catching classes that do not inherit from BaseException` during agent execution |

**Severity scoring breakdown:**

| Issue | User-facing (0-3) | Frequency (0-2) | Cross-source (0-2) | Error severity (0-1) | Total |
|-------|-------------------|-----------------|--------------------|--------------------|-------|
| SSO expired | 0 | 2 (10 occurrences) | 2 (LF + CW) | 1 (ACTIONABLE) | **5 → P1** |
| IGCE BadZipFile | 0 | 1 (3 occurrences) | 0 (CW only) | 1 (ACTIONABLE) | **2 → P2** |
| S3 AccessDenied | 0 | 0 (1 occurrence) | 1 (CW, likely linked to SSO) | 1 (ACTIONABLE) | **2 → P2** |
| TypeError | 0 | 0 (1 occurrence) | 0 (LF only) | 1 (ACTIONABLE) | **1 → P3** |

## Noise Report

| Category | Count | Justification |
|----------|-------|---------------|
| Circuit breaker test warnings | 24 | From `test_create_document_observability.py` — rapid-fire threshold triggers during test; not production traffic |
| Sub-span stubs (output=null) | 34 | `kb_search_*`, `semantic_*`, `s3_fetch_docs`, `eagle-query-*` traces — lightweight sub-operations expected to have null output |
| Orphan stream traces | 33 | `eagle-stream-*` with no sessionId, cost=0, output=null — client disconnect before span close |
| boom_tool kaboom | 1 | From `test_tool_dispatch.py` line 126 — intentional test fixture |
| Test results DDB failures | 4 | Simulated DDB failures from test suite |
| Triage dispatch 422 | 1 | Test-generated validation failure |
| S3 NoSuchKey (test-tenant) | 1 | Test data for non-existent package file |
| Error webhook INFO | 1 | INFO-level log matched on keyword "Error" — not an error |
| **Total filtered** | **99** | |
