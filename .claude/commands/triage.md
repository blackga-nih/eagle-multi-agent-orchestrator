---
description: "Unified diagnostic triage — cross-references DynamoDB user feedback, CloudWatch errors, and Langfuse traces to identify bugs and create a fix plan. Keywords: triage, diagnose, bugs, errors, feedback, health."
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Agent
argument-hint: [full|light] [1h|4h|24h|7d] [--env=dev|qa] [--tenant=default] (defaults: light, 24h, dev, default)
model: opus
---

# /triage — Unified Diagnostic Triage

> Cross-reference DynamoDB user feedback, CloudWatch log errors, and Langfuse trace failures. Identify correlated patterns, produce a unified diagnostic report, and generate a prioritized fix plan.

## Variables

- `MODE`: first positional arg — `full` | `light` (default: `light`)
- `TIME_WINDOW`: duration arg — `1h` | `4h` | `24h` | `7d` (default: `24h`)
- `ENV`: `--env=X` flag — `dev` | `qa` (default: `dev`)
- `TENANT_ID`: `--tenant=X` flag (default: `default`)
- `RESOLVED_TENANT`: `${TENANT_ID}-${ENV}` — used for DynamoDB queries (e.g., `default-dev`, `nci-oa-qa`). If TENANT_ID already ends with `-dev` or `-qa`, use as-is.
- `REPORT_DIR`: `docs/development/`
- `PLAN_DIR`: `.claude/specs/`
- `TIMESTAMP`: current datetime in `YYYYMMDD-HHMMSS` format

Parse `$ARGUMENTS` to extract MODE, TIME_WINDOW, ENV, and TENANT_ID. Any unrecognized positional is MODE if it matches `full|light`, otherwise TIME_WINDOW if it matches a duration pattern.

## Environment Configuration

| Resource | dev | qa |
|---|---|---|
| CloudWatch backend | `/eagle/ecs/backend-dev` | `/eagle/ecs/backend-qa` |
| CloudWatch frontend | `/eagle/ecs/frontend-dev` | `/eagle/ecs/frontend-qa` |
| CloudWatch app | `/eagle/app` | `/eagle/app` (shared) |
| DynamoDB table | `eagle` (shared) | `eagle` (shared) |
| DynamoDB tenant key | `FEEDBACK#{tenant}-dev` | `FEEDBACK#{tenant}-qa` |
| Langfuse keys | `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | `LANGFUSE_QA_PUBLIC_KEY` / `LANGFUSE_QA_SECRET_KEY` (fallback: dev keys) |
| ECS cluster | `eagle-dev` | `eagle-qa` |

---

## Phase 1: Prerequisites & Data Collection

### 1a. Validate AWS SSO

Run this FIRST before any CloudWatch or DynamoDB queries:

```bash
aws sts get-caller-identity --profile eagle 2>&1
```

If this returns an error containing `expired` or `Token`, STOP and tell the user to run `aws sso login --profile eagle`.

### 1b. Validate Langfuse Credentials

For QA environment, look for `LANGFUSE_QA_*` keys first, falling back to default keys:

```bash
cd server && python -c "
import os; from dotenv import load_dotenv; load_dotenv('.env')
env = '${ENV}'
if env == 'qa':
    pub = os.getenv('LANGFUSE_QA_PUBLIC_KEY', os.getenv('LANGFUSE_PUBLIC_KEY',''))
    sec = os.getenv('LANGFUSE_QA_SECRET_KEY', os.getenv('LANGFUSE_SECRET_KEY',''))
    proj = os.getenv('LANGFUSE_QA_PROJECT_ID', os.getenv('LANGFUSE_PROJECT_ID',''))
else:
    pub = os.getenv('LANGFUSE_PUBLIC_KEY','')
    sec = os.getenv('LANGFUSE_SECRET_KEY','')
    proj = os.getenv('LANGFUSE_PROJECT_ID','')
if not pub or not sec: print(f'WARN: Langfuse credentials not set for {env} — skipping Langfuse'); exit(1)
print(f'OK — Langfuse {env} keys configured (pub={pub[:10]}..., project={proj[:10] if proj else \"not set\"})')
"
```

If Langfuse credentials are missing, **continue with 2/3 sources** and note the gap in the report.

### 1c. Collect All 3 Sources IN PARALLEL

Once prerequisites pass, launch all three data collection steps **simultaneously** (multiple tool calls in a single response).

---

#### Source 1: DynamoDB Feedback

Query both feedback types using boto3. Use `RESOLVED_TENANT` (tenant_id with env suffix) as the partition key:

```bash
cd server && python -c "
import json, os, boto3
from dotenv import load_dotenv; load_dotenv('.env')
from decimal import Decimal

class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal): return float(o)
        return super().default(o)

ddb = boto3.resource('dynamodb', region_name='us-east-1')
table = ddb.Table(os.getenv('TABLE_NAME', 'eagle'))
tenant = '${RESOLVED_TENANT}'  # e.g. 'default-dev' or 'default-qa'

# General feedback (bug reports, suggestions, etc.)
resp1 = table.query(
    KeyConditionExpression='PK = :pk AND begins_with(SK, :prefix)',
    ExpressionAttributeValues={':pk': f'FEEDBACK#{tenant}', ':prefix': 'FEEDBACK#'},
    ScanIndexForward=False, Limit=100
)

# Message-level feedback (thumbs up/down)
resp2 = table.query(
    KeyConditionExpression='PK = :pk AND begins_with(SK, :prefix)',
    ExpressionAttributeValues={':pk': f'FEEDBACK#{tenant}', ':prefix': 'MSG_FEEDBACK#'},
    ScanIndexForward=False, Limit=200
)

print(json.dumps({
    'environment': '${ENV}',
    'resolved_tenant': tenant,
    'general_feedback': resp1.get('Items', []),
    'general_count': len(resp1.get('Items', [])),
    'message_feedback': resp2.get('Items', []),
    'message_count': len(resp2.get('Items', [])),
}, cls=DecimalEncoder, indent=2))
"
```

**From the results, extract:**
- **Bug reports**: items where `feedback_type` is `bug` or `incorrect_info`
- **Negative signals**: items where `feedback_type` is `thumbs_down`
- **Session IDs**: collect all `session_id` values from negative feedback for cross-referencing in Phase 2
- **Time filter**: only include items where `created_at` falls within TIME_WINDOW

---

#### Source 2: CloudWatch Errors

Use `mcp__cloudwatch-mcp-server__execute_log_insights_query` to query these log groups **in parallel** (substitute `${ENV}` for the environment):

1. `/eagle/ecs/backend-${ENV}` (e.g., `/eagle/ecs/backend-dev` or `/eagle/ecs/backend-qa`)
2. `/eagle/ecs/frontend-${ENV}` (e.g., `/eagle/ecs/frontend-dev` or `/eagle/ecs/frontend-qa`)
3. `/eagle/app` (shared across environments)

**Query for each:**

```
filter @message like /(?i)(error|ERROR|exception|Exception|FATAL|fatal|crash|fail|FAIL)/
| fields @timestamp, @logStream, @message
| sort @timestamp desc
| limit 50
```

**Parameters for every query:**
- `region: "us-east-1"`
- `profile_name: "eagle"`
- `start_time`: calculated from TIME_WINDOW (e.g., 24 hours ago)
- `end_time`: now

**Classify each error using the Known Error Patterns table below.**

---

#### Source 3: Langfuse Trace Errors

```bash
cd server && python -c "
import asyncio, json, httpx, base64, os
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv; load_dotenv('.env')

env = '${ENV}'
if env == 'qa':
    pub = os.getenv('LANGFUSE_QA_PUBLIC_KEY', os.getenv('LANGFUSE_PUBLIC_KEY'))
    sec = os.getenv('LANGFUSE_QA_SECRET_KEY', os.getenv('LANGFUSE_SECRET_KEY'))
    project_id = os.getenv('LANGFUSE_QA_PROJECT_ID', os.getenv('LANGFUSE_PROJECT_ID', ''))
else:
    pub = os.getenv('LANGFUSE_PUBLIC_KEY')
    sec = os.getenv('LANGFUSE_SECRET_KEY')
    project_id = os.getenv('LANGFUSE_PROJECT_ID', '')
host = os.getenv('LANGFUSE_HOST', 'https://us.cloud.langfuse.com')
auth = 'Basic ' + base64.b64encode(f'{pub}:{sec}'.encode()).decode()

window_hours = {'1h': 1, '4h': 4, '24h': 24, '7d': 168}
hours = window_hours.get('${TIME_WINDOW}', 24)
from_ts = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

async def fetch():
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f'{host}/api/public/traces',
            params={'limit': 100, 'fromTimestamp': from_ts},
            headers={'Authorization': auth})
        traces = resp.json()

        error_traces = []
        all_traces = traces.get('data', [])
        for t in all_traces:
            obs_resp = await client.get(f'{host}/api/public/observations',
                params={'traceId': t['id'], 'limit': 20},
                headers={'Authorization': auth})
            obs = obs_resp.json().get('data', [])
            has_error = any(o.get('level') == 'ERROR' for o in obs)
            error_msg = next((o.get('statusMessage','') for o in obs if o.get('level')=='ERROR'), '')
            if has_error or t.get('output') is None:
                error_traces.append({
                    'trace_id': t['id'],
                    'timestamp': t.get('timestamp'),
                    'session_id': t.get('sessionId', ''),
                    'user_id': t.get('userId', ''),
                    'name': t.get('name', ''),
                    'latency_ms': t.get('latency'),
                    'cost': t.get('totalCost', 0),
                    'error_message': error_msg,
                    'url': f'{host}/project/{project_id}/traces/{t[\"id\"]}' if project_id else '',
                })

        total = len(all_traces)
        successful = total - len(error_traces)
        avg_latency = sum(t.get('latency', 0) or 0 for t in all_traces) / max(total, 1)
        total_cost = sum(t.get('totalCost', 0) or 0 for t in all_traces)
        unique_users = len(set(t.get('userId', '') for t in all_traces if t.get('userId')))

        print(json.dumps({
            'total_traces': total,
            'successful': successful,
            'error_count': len(error_traces),
            'error_traces': error_traces,
            'avg_latency_ms': round(avg_latency),
            'total_cost_usd': round(total_cost, 4),
            'unique_users': unique_users,
        }, indent=2))

asyncio.run(fetch())
"
```

---

## Known Error Patterns

### CloudWatch Patterns

| Pattern | Category | Severity |
|---------|----------|----------|
| `Failed to detach context` | OTel async context (handled — spans nest via Langfuse parent wrapper) | Noise |
| `s3:PutObject` / `s3:GetObject` AccessDenied | IAM missing permission | ACTIONABLE |
| `logs:CreateLogGroup` AccessDenied | IAM missing permission | ACTIONABLE |
| `BadZipFile: File is not a zip file` | Corrupt upload | ACTIONABLE |
| `MemoryStore is not designed for production` | Session store warning | Warning |
| `DeprecationWarning: datetime.utcnow` | Python 3.12 deprecation | Noise |
| `Task stopped` + `Essential container` | ECS task crash | ACTIONABLE |
| `OOM` / `OutOfMemory` | Memory limit exceeded | ACTIONABLE |
| `ThrottlingException` | Bedrock rate limit | Warning |
| `ModelNotReadyException` | Bedrock cold start | Warning |
| `SIGTERM` / `SIGKILL` | Container killed | ACTIONABLE |

### Langfuse Patterns

| Pattern | Category | Severity |
|---------|----------|----------|
| `Token has expired and refresh failed` | SSO expired | ACTIONABLE |
| `ThrottlingException` | Bedrock rate limit | Warning |
| `ModelNotReadyException` | Bedrock cold start | Noise |
| `AccessDeniedException` | IAM role error | ACTIONABLE |
| `ValidationException` | Bad model request | ACTIONABLE |
| Repeated "Hello" inputs with ERROR | Retry loops / expired SSO | ACTIONABLE |
| `output: null` with cost=0 | Auth/infra failure | ACTIONABLE |

### Feedback Patterns

| feedback_type | Signal | Priority Boost |
|---------------|--------|----------------|
| `bug` | User-reported defect | +3 (user-facing) |
| `incorrect_info` | Agent gave wrong answer | +3 (user-facing) |
| `thumbs_down` | Negative per-message rating | +2 (user-facing) |
| `suggestion` | Feature request | +0 (informational) |
| `praise` / `general` | Positive/neutral | +0 (context only) |

---

## Phase 2: Cross-Reference Analysis

### 2a. Session-Level Correlation

For each `session_id` from **negative feedback** (bug, incorrect_info, thumbs_down):

1. Check if same `session_id` appears in **Langfuse error traces**
2. Check if same `session_id` appears in **CloudWatch error messages** (search `@message` for the session_id)

Build a correlation map: `{session_id -> {feedback: [...], cw_errors: [...], lf_errors: [...]}}`

Sessions appearing in **2+ sources** are confirmed user-impacting bugs — assign cross-source correlation bonus.

### 2b. Error Pattern Clustering

Group errors from ALL sources by root cause:

| Cluster | CloudWatch Signal | Langfuse Signal | Feedback Signal |
|---------|------------------|-----------------|-----------------|
| **IAM/SSO** | AccessDenied errors | sso-expired, AccessDeniedException | "not working", "error" |
| **Container Crash** | OOM, SIGTERM, Task stopped | output:null, cost=0 | "no response", "crashed" |
| **Model Issues** | ThrottlingException | ThrottlingException, ModelNotReady | "slow", "timeout" |
| **Data Quality** | BadZipFile | ValidationException | "incorrect", "wrong" |
| **Application Bug** | Specific error messages | statusMessage with stack trace | "bug", "broken" |

### 2c. Composite Severity Scoring

For each identified issue, calculate severity (0-8):

| Factor | Weight | Score Range |
|--------|--------|-------------|
| User-facing (has matching feedback) | 3x | 0-3 |
| Frequency (occurrence count) | 2x | 0-2 |
| Cross-source correlation (appears in 2+ sources) | 2x | 0-2 |
| Error severity (ACTIONABLE vs Warning) | 1x | 0-1 |

**Priority mapping:**
- **P0** (6-8): Fix immediately
- **P1** (4-5): Fix this sprint
- **P2** (2-3): Backlog
- **P3** (0-1): Monitor

---

## Phase 3: Diagnostic Report

### LIGHT Mode — Console Output (No Files)

```
EAGLE Triage Report — {timestamp}
Environment: {ENV} | Window: last {TIME_WINDOW} | Tenant: {RESOLVED_TENANT}

Source Summary
┌──────────────────────┬───────┬──────────┐
│ Source                │ Total │ Issues   │
├──────────────────────┼───────┼──────────┤
│ DynamoDB Feedback    │ {N}   │ {N} bugs │
│ CloudWatch Logs      │ {N}   │ {N}      │
│ Langfuse Traces      │ {N}   │ {N}      │
└──────────────────────┴───────┴──────────┘

Message Feedback: {N} thumbs_up / {N} thumbs_down ({pct}% positive)

Top Issues (by composite severity)
┌────┬──────────────────────────────┬──────┬────────────┬───────────────────────┐
│ #  │ Issue                        │ Sev  │ Sources    │ Sessions Affected     │
├────┼──────────────────────────────┼──────┼────────────┼───────────────────────┤
│ 1  │ {issue description}          │ P0   │ CW+LF+FB  │ {N}                   │
│ 2  │ {issue description}          │ P1   │ CW+LF     │ {N}                   │
│ ...│ ...                          │ ...  │ ...        │ ...                   │
└────┴──────────────────────────────┴──────┴────────────┴───────────────────────┘

Correlated Sessions (feedback + errors on same session)
  {session_id} — Feedback: "{text}" | CW: {error} | LF: {error}
  ...

Noise Filtered: {N} OTel detach, {N} deprecation warnings, {N} cold starts

Recommendation: {1-2 sentence summary of highest priority action}
```

If zero issues found across all sources, report: "All clear — no issues in the last {TIME_WINDOW}."

### FULL Mode — Report + Plan Files

Write a diagnostic report to `docs/development/{TIMESTAMP}-report-triage-v{N}.md`.

Scan the destination directory for existing `*-report-triage-v*.md` files and use the next version number (never overwrite).

```markdown
# EAGLE Triage Report

**Date**: {date}
**Environment**: {ENV}
**Window**: {TIME_WINDOW}
**Tenant**: {RESOLVED_TENANT}
**Mode**: Full
**Sources**: DynamoDB Feedback, CloudWatch Logs ({ENV}), Langfuse Traces ({ENV})

## Executive Summary
{2-3 sentences: what is the biggest problem? how many users affected?}

## Source Data

### DynamoDB Feedback
{Full feedback table — feedback_type, session_id, user_id, text excerpt, created_at}

### CloudWatch Errors
{Grouped by log group, categorized by severity — same format as /check-cloudwatch-logs}

### Langfuse Trace Errors
{Error traces with URLs, classified by category — same format as /check-langfuse-logs}

## Cross-Reference Analysis

### Session Correlation Map
{Table of sessions that appear in 2+ sources with all associated errors}

### Error Pattern Clusters
{Grouped by root cause with evidence from each source}

### Trend Analysis
{Are errors increasing? Repeating across sessions? Time-of-day pattern?}

## Prioritized Issue List
{Full issue list with composite severity scores — P0 through P3}

## Noise Report
{Items classified as noise with justification — kept separate for transparency}
```

---

## Phase 4: Fix Plan Generation (FULL Mode Only)

After generating the report, create a prioritized fix plan at `.claude/specs/{TIMESTAMP}-plan-triage-fixes-v{N}.md`.

Scan `.claude/specs/` for existing `*-plan-triage-fixes-v*.md` files for version numbering.

```markdown
# Plan: Triage Fixes — {date}

## Task Description
Fix {N} issues identified by /triage diagnostic scan across DynamoDB feedback, CloudWatch logs, and Langfuse traces.

## Objective
Resolve all P0 and P1 issues to improve user experience and system reliability.

## Problem Statement
{Summary from triage report executive summary}

## Relevant Files
{List files that need modification based on error analysis, e.g.:}
- `server/app/strands_agentic_service.py` — {what needs fixing}
- `infrastructure/cdk-eagle/lib/core-stack.ts` — {what needs fixing}
- `server/app/streaming_routes.py` — {what needs fixing}

## Implementation Phases

### Phase 1: P0 Fixes (Critical)
{Steps to fix each P0 issue with specific file changes}

### Phase 2: P1 Fixes (High)
{Steps to fix each P1 issue}

### Phase 3: P2 Improvements (Medium)
{Steps for lower-priority improvements}

## Step by Step Tasks

### 1. {First P0 fix}
- **File**: {path}
- **Problem**: {what's wrong, with evidence from triage}
- **Fix**: {specific code change needed}
- **Validation**: {how to verify the fix}

### 2. {Second P0 fix}
...

### N. Validate All Fixes
- `ruff check app/`
- `npx tsc --noEmit`
- `python -m pytest tests/ -v`
- Re-run `/triage light` to confirm issues resolved

## Acceptance Criteria
- All P0 issues resolved
- All P1 issues resolved or documented with rationale for deferral
- No new errors introduced (re-triage shows improvement)
- Validation commands pass

## Validation Commands
- `ruff check app/` — Python lint
- `npx tsc --noEmit` — TypeScript check
- `python -m pytest tests/ -v` — Unit tests
- `/triage light` — Re-triage to confirm improvement

## Notes
- Generated by /triage on {date}
- Triage report: docs/development/{report-filename}
- Cross-referenced {N} feedback items, {N} CloudWatch errors, {N} Langfuse traces
```

---

## Instructions

1. **Always validate SSO + Langfuse credentials first** — if SSO is expired, stop. If Langfuse is unavailable, continue with 2/3 sources and note the gap.

2. **Collect all 3 sources in parallel** — launch DynamoDB query, CloudWatch queries (3 log groups), and Langfuse fetch simultaneously using multiple tool calls.

3. **Cross-reference by session_id** — this is the primary correlation key. A session that appears in feedback AND error logs is a confirmed user-impacting bug.

4. **Filter noise aggressively** — use the Known Error Patterns tables. Do not inflate the issue count with OTel detach errors, deprecation warnings, or cold starts.

5. **Score and prioritize** — use the composite severity scoring. User-facing issues with feedback are always higher priority than backend-only errors.

6. **LIGHT mode is fast** — no file writes, no plan generation, just console output.

7. **FULL mode is thorough** — writes report + plan files, includes trend analysis and fix plan.

8. **Never expose secrets** — filter AWS account IDs (beyond 695681773636), credentials, tokens, and PII from output.

9. **Reuse existing patterns** — the CloudWatch queries use the same MCP tool and known patterns as `/check-cloudwatch-logs`. The Langfuse queries use the same REST API pattern as `/check-langfuse-logs`. The plan format follows `/plan`.

## Usage Examples

```
/triage                          # light mode, dev env, 24h window, default tenant
/triage light 4h                 # light mode, dev env, 4h window
/triage light --env=qa           # light mode, QA env (queries backend-qa, frontend-qa logs)
/triage full 24h                 # full mode, dev env, report + fix plan
/triage full 24h --env=qa        # full mode, QA env, report + fix plan
/triage full 7d --env=qa --tenant=nci-oa  # full mode, QA env, 7d window, nci-oa-qa tenant
```
