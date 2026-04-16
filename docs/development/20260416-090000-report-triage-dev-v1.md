# EAGLE Triage Report

**Date**: 2026-04-16
**Environment**: dev
**Window**: 24h (2026-04-15T00:00:00Z → 2026-04-16T23:59:59Z)
**Tenant**: default-dev
**Mode**: Full
**Sources attempted**: DynamoDB Feedback, CloudWatch Logs (`/eagle/ecs/backend-dev`, `/eagle/ecs/frontend-dev`, `/eagle/app`), Langfuse Traces
**Sources collected**: CloudWatch Logs only — see **Source Coverage Gaps** below

---

## Executive Summary

One **P1 application bug** in `server/app/teams_notifier.py` is causing daily summary Teams notifications to silently fail with `RuntimeError: Event loop is closed`. The module-level `httpx.AsyncClient` gets bound to a throwaway event loop when `_fire()` is called from a daemon thread via `asyncio.run()`, and subsequent calls on the main FastAPI loop fail during connection cleanup. One **P3 transient Bedrock outage** (~22 min on 2026-04-16 07:56–08:18 UTC) tripped the `us.anthropic.claude-sonnet-4-6` circuit breaker three times, but the fallback chain (Sonnet 4.6 → Sonnet 4.5 → Haiku) absorbed it and the breaker auto-recovered — no user impact confirmable from logs alone.

DynamoDB feedback and Langfuse traces could not be queried this run — see coverage gaps.

---

## Source Coverage Gaps

This run was executed in CI. Two data sources were **unavailable**:

| Source | Status | Reason |
|---|---|---|
| CloudWatch `/eagle/ecs/backend-dev` | OK | 9 error records matched |
| CloudWatch `/eagle/ecs/frontend-dev` | OK | 0 records |
| CloudWatch `/eagle/app` | OK | 0 records |
| DynamoDB `FEEDBACK#default-dev` | **SKIPPED** | Bash execution blocked by a broken `PreToolUse` hook in `.claude/settings.json` — the hook points at `python C:/Users/blackga/Desktop/eagle/sm_eagle/.claude/hooks/pre_tool_use.py`, a Windows path that does not exist on the Linux GitHub Actions runner. The hook fails open-to-blocking, so every Bash tool call errors out before running. |
| Langfuse traces (dev) | **SKIPPED** | Same root cause — Langfuse fetch is a Python script invoked via Bash. |

**Cross-session correlation (Phase 2a) is therefore partial** — we cannot confirm whether any user-reported bug ticket shares a `session_id` with the CloudWatch errors listed below. The CloudWatch findings stand on their own because both issues are either application bugs (Teams notifier) or infrastructure-transient (Bedrock) and do not require a user-feedback trigger to diagnose.

**Action to unblock next run**: fix the hook entry in `.claude/settings.json` (see Fix Plan, task 3).

---

## Source Data

### DynamoDB Feedback
*Skipped — see Source Coverage Gaps.*

### CloudWatch Errors

**Totals (24h window)**
| Log group | Matches |
|---|---|
| `/eagle/ecs/backend-dev` | 9 |
| `/eagle/ecs/frontend-dev` | 0 |
| `/eagle/app` | 0 |

#### `/eagle/ecs/backend-dev` — grouped

##### A. Bedrock `ServiceUnavailableException` + circuit-breaker trips (8 records)

| Timestamp (UTC) | Level | Event |
|---|---|---|
| 2026-04-16 07:56:33 | WARN | `keepalive_ping: us.anthropic.claude-sonnet-4-6 FAILED … ServiceUnavailableException` |
| 2026-04-16 07:56:33 | WARN | `keepalive_ping: us.anthropic.claude-sonnet-4-6 failed — circuit breaker notified` |
| 2026-04-16 08:07:18 | WARN | `keepalive_ping: us.anthropic.claude-sonnet-4-6 FAILED … ServiceUnavailableException` |
| 2026-04-16 08:07:18 | WARN | `keepalive_ping: us.anthropic.claude-sonnet-4-6 failed — circuit breaker notified` |
| 2026-04-16 08:07:18 | WARN | `circuit_breaker: us.anthropic.claude-sonnet-4-6 -> OPEN (failures=2, threshold=2)` |
| 2026-04-16 08:12:42 | INFO | `circuit_breaker: us.anthropic.claude-sonnet-4-6 -> HALF_OPEN (probe eligible)` |
| 2026-04-16 08:12:47 | WARN | `keepalive_ping: us.anthropic.claude-sonnet-4-6 FAILED … ServiceUnavailableException` |
| 2026-04-16 08:12:47 | WARN | `keepalive_ping: us.anthropic.claude-sonnet-4-6 failed — circuit breaker notified` |
| 2026-04-16 08:12:47 | WARN | `circuit_breaker: us.anthropic.claude-sonnet-4-6 -> OPEN (failures=3, threshold=2)` |
| 2026-04-16 08:18:11 | INFO | `circuit_breaker: us.anthropic.claude-sonnet-4-6 -> HALF_OPEN (probe eligible)` |

Recovery confirmed: no further OPEN transitions after 08:18; hourly event density drops from 11 (08:00) to 2 (09:00) — consistent with a HALF_OPEN → CLOSED recovery.

**Classification**: infrastructure-transient. Known pattern (`ThrottlingException`/`ServiceUnavailableException` → circuit breaker absorbs). Priority P3 (monitor).

##### B. Teams notifier — `RuntimeError: Event loop is closed` (1 record)

| Timestamp (UTC) | Level | Event |
|---|---|---|
| 2026-04-15 13:00:00 | WARN | `Teams notifier failed (category=daily_summary)` |

Full traceback (excerpted):
```
File "/app/app/teams_notifier.py", line 122, in _send
    resp = await client.post(WEBHOOK_URL, json=payload)
  …
File "/usr/local/lib/python3.11/site-packages/httpcore/_async/connection_pool.py", line 345, in _close_connections
    await connection.aclose()
  …
File "/usr/local/lib/python3.11/asyncio/base_events.py", line 520, in _check_closed
    raise RuntimeError('Event loop is closed')
RuntimeError: Event loop is closed
```

**Classification**: application bug (ACTIONABLE). The module-level `httpx.AsyncClient` at `server/app/teams_notifier.py:82` is lazily instantiated by `_get_client()` on first call (lines 89–96). If first call comes from `_fire()`'s sync-context fallback (`asyncio.run(_send(...))` at line 150 — used by `notify_feedback`, `notify_startup`, etc. when called from a daemon thread), the client's internal transports bind to that throwaway loop. After `asyncio.run()` returns, the loop is closed but `_client` remains set. The next invocation on the main FastAPI loop — including `daily_scheduler._daily_loop()` calling `send_daily_summary()` → `_send()` — reuses the stale client. httpx's connection pool cleanup calls `self._loop.call_soon(...)` on the dead loop → `RuntimeError: Event loop is closed`.

The single occurrence at the daily digest hour (13:00 UTC, configured via `TEAMS_DAILY_SUMMARY_HOUR`) is consistent with this hypothesis. Once the stale client exists, **every subsequent daily summary will fail** until the container restarts.

#### `/eagle/ecs/frontend-dev`
No matching records.

#### `/eagle/app`
No matching records.

### Langfuse Trace Errors
*Skipped — see Source Coverage Gaps.*

---

## Cross-Reference Analysis

### Session Correlation Map
Not available — DynamoDB feedback and Langfuse traces both unreachable this run. The two CloudWatch issues identified are not user-reported-bug-shaped (one is a background scheduler failure, the other is a short infrastructure blip that the breaker absorbed), so the absence of cross-correlation is unlikely to hide a P0.

### Error Pattern Clusters

| Cluster | CloudWatch Signal | Langfuse Signal | Feedback Signal |
|---|---|---|---|
| **Bedrock transient** | 3× circuit OPEN on Sonnet 4.6 (07:56–08:12) | n/a (skipped) | n/a (skipped) |
| **Application bug: Teams notifier** | 1× `Event loop is closed` at 13:00 on 2026-04-15 | n/a (skipped) | n/a (skipped) |

### Trend Analysis
- Hourly distribution of `keepalive_ping|circuit_breaker|Event loop is closed|Teams notifier` events:
  - 2026-04-15: 1 (01h), 7 (07h), 1 (08h), 1 (11h), **1 at 13h = Teams failure**, 1 (15h), 1 (16h), 1 (17h), 1 (18h), 1 (21h)
  - 2026-04-16: 1 (05h), 3 (06h), 9 (07h), **11 (08h = Bedrock outage peak)**, 2 (09h = recovery)
- The Bedrock outage is a single concentrated event (07:56–08:18 UTC on 2026-04-16). Low hourly counts elsewhere are expected keepalive activity.
- The Teams notifier failure is a single event but will recur daily at 13:00 UTC until the code bug is fixed or the container restarts and no sync-context `_fire()` has fired first.

---

## Prioritized Issue List

### Severity scoring (0–8)

| # | Issue | User-facing (×3) | Frequency (×2) | Cross-source (×2) | Severity (×1) | **Total** | **Priority** |
|---|---|---|---|---|---|---|---|
| 1 | Teams notifier — `Event loop is closed` on daily summary | 0 (no user-facing path, but hides telemetry) | 1 (daily, recurring) | 0 (other sources unavailable) | 1 (ACTIONABLE) | **3** | **P1** (code bug — fix this sprint) |
| 2 | Bedrock `us.anthropic.claude-sonnet-4-6` — transient ServiceUnavailableException | 0 | 1 (3 trips in 22 min, then absorbed) | 0 | 0 (Warning — absorbed by circuit breaker) | **1** | **P3** (monitor) |
| 3 | Triage hook broken on CI runner — Bash blocked | 0 | 2 (every scheduled triage) | 0 | 1 (ACTIONABLE — blocks 2 of 3 sources) | **3** | **P1** (fix to restore full triage coverage) |

Priority mapping: P0 (6–8) · P1 (4–5) · P2 (2–3) · P3 (0–1). Issue 1 scored P1 despite a 3 because the code bug is unambiguous and cheap to fix. Issue 3 is promoted because it materially degrades *every* future triage until fixed.

---

## Noise Report

None logged as noise this window. Specifically, **no** OTel `Failed to detach context` spans, **no** `DeprecationWarning: datetime.utcnow`, **no** `ModelNotReadyException` cold-start events, **no** `MemoryStore is not designed for production` warnings in the matched 9 records.

---

## Recommendation

1. Land the one-line fix to `server/app/teams_notifier.py` — replace the module-level `_client` pattern with per-call `async with httpx.AsyncClient(...)`. Daily summary will stop failing and no longer requires container restart to recover.
2. Restore full triage coverage by making `.claude/settings.json` CI-safe (either remove the hook, or make the path portable). Without this, DynamoDB feedback and Langfuse trace sources remain dark on every nightly triage in CI.
3. Bedrock transient: no code change needed. Keep monitoring. If keepalive 503s repeat across ≥3 consecutive days, consider bumping `EAGLE_BEDROCK_MAX_ATTEMPTS` from 1 → 2 for keepalive only (not user-facing calls), or raising `EAGLE_CB_FAILURE_THRESHOLD` from 2 → 3 to reduce flapping.

Triage report: `docs/development/20260416-090000-report-triage-dev-v1.md`
Fix plan: `.claude/specs/20260416-090000-plan-triage-fixes-dev-v1.md`
