# EAGLE Triage Report

**Date**: 2026-04-10
**Environment**: dev
**Window**: 24h
**Tenant**: default-dev
**Mode**: Full
**Sources**: CloudWatch Logs (dev) | DynamoDB Feedback (UNAVAILABLE) | Langfuse Traces (UNAVAILABLE)

## Executive Summary

The dev environment has **two active issues**: (1) Langfuse OTLP span export is failing with 401 Unauthorized (50 occurrences), flooding CloudWatch logs, and (2) AWS SSO tokens are expiring on the local dev instance, causing credential refresh failures (30 occurrences). Bedrock availability has improved dramatically from yesterday's 629 ServiceUnavailableExceptions to just 4 today, with the circuit breaker activating correctly. The IAM permission gaps (DynamoDB Scan, S3 GetObject AccessDenied) reported yesterday are no longer appearing.

**Data Source Gaps**: DynamoDB feedback and Langfuse traces could not be queried because the CI runner's Bash hook has a hardcoded Windows path (`C:/Users/blackga/...`) in `.claude/settings.json` that fails on Linux. This blocks all Python/boto3 execution. Fix is tracked as P1 below.

## Source Data

### DynamoDB Feedback

**Status**: UNAVAILABLE — Bash tool blocked by PreToolUse hook with Windows-only path in `.claude/settings.json`. The hook references `C:/Users/blackga/Desktop/eagle/sm_eagle/.claude/hooks/pre_tool_use.py` which does not resolve on Linux CI. The actual hook script exists at `.claude/hooks/pre_tool_use.py` (relative) and is Windows-specific (uses `taskkill`, `netstat`).

### CloudWatch Errors

#### `/eagle/ecs/backend-dev` — 899 records matched (37,374 scanned)

**Error Breakdown:**

| # | Category | Pattern | Count | Severity |
|---|----------|---------|-------|----------|
| 1 | OTel Export Auth | `Failed to export span batch code: 401, reason: Unauthorized` | 50 | ACTIONABLE |
| 2 | SSO Token Expiry | `Token has expired and refresh failed` / `SSO token refresh attempt failed` / `Refreshing temporary credentials failed` | 30 | ACTIONABLE |
| 3 | Bedrock Unavailable | `ServiceUnavailableException: Bedrock is unable to process your request` (keepalive_ping) | 4 | Warning |
| 4 | AsyncIO Connection Reset | `ConnectionResetError: [WinError 10054] An existing connection was forcibly closed` | 5 | Noise (Windows local dev) |
| 5 | web_fetch SSL/DNS | `CERTIFICATE_VERIFY_FAILED` on example.com + DNS failure on wind.example.com | 4 | Noise (test URLs) |
| 6 | Test Run Results | `1452 passed, 14 failed` | 1 | Informational |
| 7 | Knowledge Fetch (false positive) | INFO-level knowledge_fetch matching S3 key names containing "Failure"/"Error" | ~805 | Noise (false positive) |

**Note**: ~805 of the 899 matched records are false positives — INFO-level `eagle.knowledge_tools` messages where S3 key names like `GAO_B-423281_ECP_Evaluation_Failure_Indirect_Rate_Cap.txt` match the error filter regex. Actual error/warning count is **94**.

#### `/eagle/ecs/frontend-dev` — 0 records matched (5 scanned)

No errors detected. Frontend is clean.

#### `/eagle/app` — 0 records matched (0 scanned)

No log events in the time window.

**Hourly Distribution (all 899 matched records):**

| Hour (UTC) | Count | Notes |
|------------|-------|-------|
| 2026-04-09 05:00 | 156 | Overnight test/knowledge-fetch activity |
| 2026-04-09 06:00 | 352 | Peak — bulk knowledge-fetch (false positives) |
| 2026-04-09 07:00 | 45 | |
| 2026-04-09 08:00 | 15 | |
| 2026-04-09 09:00 | 3 | |
| 2026-04-09 16:00 | 139 | Afternoon test run |
| 2026-04-09 17:00 | 142 | Afternoon test run + test results |
| 2026-04-09 20:00 | 2 | |
| 2026-04-09 21:00 | 5 | AsyncIO connection resets |
| 2026-04-09 22:00 | 2 | |
| 2026-04-10 06:00 | 2 | Bedrock keepalive failures |
| 2026-04-10 07:00 | 14 | OTel export 401 burst |
| 2026-04-10 08:00 | 22 | SSO expiry + OTel export 401 |

### Langfuse Trace Errors

**Status**: UNAVAILABLE — Langfuse dev keys are configured in `server/.env` (public key: `pk-lf-47021a72...`), but Langfuse API queries require Python/Bash execution which is blocked by the hook issue.

## Cross-Reference Analysis

### Session Correlation Map

Limited cross-referencing possible due to DynamoDB and Langfuse being unavailable. From CloudWatch alone:

| Session ID | Source | Error |
|------------|--------|-------|
| `825d9cf5-5ac7-403d-825d-635da652ed36` | CW | Active during OTel export failures (08:03 UTC) — knowledge_fetch working normally |
| `7397498f-0a8f-447d-ba8e-6e0d1e51f782` | CW | Active during OTel export failures (07:58 UTC) — knowledge_fetch working normally |

Sessions are functioning (knowledge_fetch succeeds) despite OTel export failures — the exporter failures are non-blocking to user operations.

### Error Pattern Clusters

| Cluster | CloudWatch Signal | Root Cause | Impact |
|---------|-------------------|------------|--------|
| **Langfuse Auth** | 50x OTel export 401 | Langfuse OTLP exporter credentials invalid or endpoint auth changed | Traces not exported; CloudWatch log noise |
| **SSO Expiry** | 30x token/credential refresh failures | Developer's AWS SSO session expired on local dev | Bedrock API calls fail until `aws sso login` |
| **Bedrock Availability** | 4x ServiceUnavailable + circuit breaker OPEN | Transient Bedrock service unavailability | Circuit breaker correctly activates; auto-recovers |
| **Windows Async** | 5x ConnectionResetError WinError 10054 | Windows ProactorEventLoop connection teardown race | Non-functional; cosmetic only |

### Trend Analysis

**Improving**: Bedrock ServiceUnavailableException dropped from 629 (Apr 9 triage) to 4 today — a 98.4% reduction. Circuit breaker implementation is working effectively.

**New Issue**: OTel export 401 Unauthorized (50 occurrences) is new compared to yesterday's triage. This suggests either Langfuse API key rotation or endpoint auth change since last successful export.

**Persistent**: SSO token expiration continues to appear in logs from local dev (Windows paths visible in stack traces). This is a developer workflow issue, not a deployment problem.

**Resolved**: IAM permission gaps (DynamoDB Scan AccessDenied, S3 GetObject AccessDenied) reported in the Apr 9 triage are no longer appearing.

## Prioritized Issue List

### Composite Severity Scoring

| # | Issue | User-Facing (0-3) | Frequency (0-2) | Cross-Source (0-2) | Severity (0-1) | **Total** | **Priority** |
|---|-------|-------------------|------------------|---------------------|----------------|-----------|--------------|
| 1 | CI hook Windows path blocks DynamoDB + Langfuse data collection | 0 | 2 | 0 | 1 | **3** | P2 |
| 2 | OTel export 401 Unauthorized (Langfuse traces not exported) | 0 | 2 | 0 | 1 | **3** | P2 |
| 3 | SSO token expiration on local dev | 0 | 1 | 0 | 1 | **2** | P2 |
| 4 | Bedrock ServiceUnavailable (4 occurrences) | 0 | 0 | 0 | 0 | **0** | P3 (monitor) |

**Note**: No issues scored P0 or P1 because DynamoDB feedback (the user-facing signal) was unavailable. Without feedback correlation, no issue can earn the user-facing weight (3x). The CI hook fix is elevated to P1 in the fix plan because it blocks future triage completeness.

## Noise Report

| Pattern | Count | Justification |
|---------|-------|---------------|
| Knowledge fetch filename matches | ~805 | INFO-level logs where S3 key names contain "Failure"/"Error" — not actual errors |
| AsyncIO ConnectionResetError (WinError 10054) | 5 | Windows ProactorEventLoop connection teardown race; cosmetic, non-functional |
| web_fetch SSL/DNS on test URLs | 4 | Test URLs (example.com, wind.example.com) failing as expected |
| Test run "14 failed" | 1 | Matched regex due to "failed" — this is a test results summary, not an error |
