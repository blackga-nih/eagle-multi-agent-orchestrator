---
name: triage
description: >
  Session-level diagnostic triage. Accepts a session ID, cross-references
  DynamoDB user feedback, CloudWatch backend/telemetry logs, and Langfuse
  traces for that session. Produces a prioritized fix spec in .claude/specs/.
  Use when someone says "triage session X", "check feedback for session",
  "diagnose session", or provides a session ID with feedback/logs context.
model: opus
---

# Session Triage — Feedback + Logs + Traces -> Fix Spec

Given a session ID, collect all evidence from three sources, cross-reference
by timestamp and tool call, classify issues, and output a prioritized fix
plan as a spec file.

## Arguments

**Required**: `SESSION_ID` — the UUID session identifier (e.g., `f2d75c92-7095-4656-8a32-8ed1ed4ddc9f`)

**Optional**:
- `--env=dev|qa` — environment (default: `dev`)
- `--tenant=TENANT` — override tenant discovery (default: auto-detect from logs)
- `--window=1h|4h|24h|7d` — time window for CloudWatch queries (default: `7d`)
- `full` — write spec file (default behavior)
- `light` — console-only output, no spec file

Parse `$ARGUMENTS` to extract SESSION_ID (first UUID-shaped arg) and flags.

## Environment Configuration

| Resource | dev | qa |
|---|---|---|
| CloudWatch backend | `/eagle/ecs/backend-dev` | `/eagle/ecs/backend-qa` |
| CloudWatch telemetry | `/eagle/telemetry` | `/eagle/telemetry` |
| CloudWatch app | `/eagle/app` | `/eagle/app` |
| DynamoDB table | `eagle` (shared) | `eagle` (shared) |
| Langfuse keys | `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | `LANGFUSE_QA_PUBLIC_KEY` / `LANGFUSE_QA_SECRET_KEY` |
| AWS profile | `eagle` | `eagle` |

---

## Phase 1: Prerequisites

### 1a. Validate AWS SSO

```bash
aws sts get-caller-identity --profile eagle 2>&1
```

If expired, STOP and tell the user to run `aws sso login --profile eagle`.

### 1b. Validate Langfuse Credentials

```bash
cd server && python -c "
import os; from dotenv import load_dotenv; load_dotenv('.env')
env = '${ENV}'
if env == 'qa':
    pub = os.getenv('LANGFUSE_QA_PUBLIC_KEY', os.getenv('LANGFUSE_PUBLIC_KEY',''))
    sec = os.getenv('LANGFUSE_QA_SECRET_KEY', os.getenv('LANGFUSE_SECRET_KEY',''))
else:
    pub = os.getenv('LANGFUSE_PUBLIC_KEY','')
    sec = os.getenv('LANGFUSE_SECRET_KEY','')
if not pub or not sec: print(f'WARN: Langfuse credentials not set for {env}'); exit(1)
print(f'OK — Langfuse {env} keys configured')
"
```

If Langfuse is missing, continue with 2/3 sources and note the gap.

---

## Phase 2: Parallel Data Collection

Launch ALL of the following simultaneously (multiple tool calls in one response).

### Source 1: CloudWatch — Backend Logs

Use `mcp__cloudwatch-mcp-server__execute_log_insights_query` to search for the session ID:

**Query** (run for `/eagle/ecs/backend-${ENV}`):
```
filter @message like /${SESSION_ID}/
| fields @timestamp, @logStream, @message
| sort @timestamp desc
| limit 50
```

**Parameters**:
- `region`: `us-east-1`
- `profile_name`: `eagle`
- `start_time`: calculated from `--window` (default 7 days ago, ISO 8601)
- `end_time`: now (ISO 8601)
- `limit`: 50

### Source 2: CloudWatch — Telemetry Events

Same query against `/eagle/telemetry`:
```
filter @message like /${SESSION_ID}/
| fields @timestamp, @logStream, @message
| sort @timestamp desc
| limit 50
```

### Source 3: DynamoDB — Feedback

**Important**: The tenant ID is NOT always `default-dev`. Discover it from CloudWatch logs first (look for `tenant_id` in the JSON messages). If no logs found yet, try common tenants.

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
session_id = '${SESSION_ID}'

# Try known tenants — check override first, then scan common ones
tenants = ['${TENANT_OVERRIDE}'] if '${TENANT_OVERRIDE}' else ['dev-tenant', 'default-dev', 'default-qa', 'default']

for tenant in tenants:
    if not tenant:
        continue
    pk = f'FEEDBACK#{tenant}'
    resp1 = table.query(
        KeyConditionExpression='PK = :pk AND begins_with(SK, :prefix)',
        ExpressionAttributeValues={':pk': pk, ':prefix': 'FEEDBACK#'},
        ScanIndexForward=False, Limit=100
    )
    resp2 = table.query(
        KeyConditionExpression='PK = :pk AND begins_with(SK, :prefix)',
        ExpressionAttributeValues={':pk': pk, ':prefix': 'MSG_FEEDBACK#'},
        ScanIndexForward=False, Limit=200
    )
    general = [i for i in resp1.get('Items', []) if i.get('session_id') == session_id]
    msg = [i for i in resp2.get('Items', []) if i.get('session_id') == session_id]
    if general or msg:
        for item in general:
            item.pop('conversation_snapshot', None)
            item.pop('cloudwatch_logs', None)
        print(json.dumps({
            'tenant': tenant,
            'general_feedback': general,
            'general_count': len(general),
            'message_feedback': msg,
            'message_count': len(msg),
        }, cls=DecimalEncoder, indent=2))
        break
else:
    print(json.dumps({'error': 'No feedback found for any known tenant', 'session_id': session_id}))
"
```

### Source 4: Langfuse — Traces + Observations

```bash
cd server && python -c "
import asyncio, json, httpx, base64, os
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

if not pub or not sec:
    print(json.dumps({'error': 'Langfuse credentials not set'}))
    exit(1)

auth = 'Basic ' + base64.b64encode(f'{pub}:{sec}'.encode()).decode()
session_id = '${SESSION_ID}'

async def fetch():
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f'{host}/api/public/traces',
            params={'limit': 50, 'sessionId': session_id},
            headers={'Authorization': auth})
        traces = resp.json()
        all_traces = traces.get('data', [])

        results = []
        for t in all_traces:
            trace_id = t['id']
            obs_resp = await client.get(f'{host}/api/public/observations',
                params={'traceId': trace_id, 'limit': 30},
                headers={'Authorization': auth})
            obs = obs_resp.json().get('data', [])

            inp = t.get('input')
            out = t.get('output')
            inp_preview = json.dumps(inp, default=str)[:300] if isinstance(inp, (dict, list)) else str(inp or '')[:300]
            out_preview = json.dumps(out, default=str)[:500] if isinstance(out, (dict, list)) else str(out or '')[:500]

            observations = []
            for o in obs:
                entry = {
                    'type': o.get('type'),
                    'name': o.get('name'),
                    'level': o.get('level', 'DEFAULT'),
                    'latency_ms': o.get('latency'),
                    'model': o.get('model'),
                    'tokens_in': o.get('promptTokens'),
                    'tokens_out': o.get('completionTokens'),
                }
                if o.get('level') == 'ERROR':
                    entry['status_message'] = (o.get('statusMessage') or '')[:500]
                observations.append(entry)

            results.append({
                'trace_id': trace_id,
                'name': t.get('name', ''),
                'timestamp': t.get('timestamp'),
                'user_id': t.get('userId'),
                'latency_ms': t.get('latency'),
                'cost': t.get('totalCost', 0),
                'tags': t.get('tags', []),
                'input_preview': inp_preview,
                'output_preview': out_preview,
                'observations': observations,
                'url': f'{host}/project/{project_id}/traces/{trace_id}' if project_id else '',
            })

        total_tokens_in = sum(
            o.get('tokens_in', 0) or 0
            for r in results for o in r['observations']
            if o.get('type') == 'GENERATION'
        )
        total_tokens_out = sum(
            o.get('tokens_out', 0) or 0
            for r in results for o in r['observations']
            if o.get('type') == 'GENERATION'
        )

        print(json.dumps({
            'trace_count': len(results),
            'total_tokens_in': total_tokens_in,
            'total_tokens_out': total_tokens_out,
            'traces': results,
        }, indent=2))

asyncio.run(fetch())
"
```

---

## Phase 3: Analysis

After all data is collected, perform the following analysis.

### 3a. Build Session Timeline

From CloudWatch + Langfuse, construct a chronological timeline:

```
HH:MM:SS  [SOURCE] Event description
13:35:21  [LF] Trace started — "I need to procure cloud hosting..."
13:35:55  [LF] Trace completed — 44s, tools: knowledge_search, web_search
13:36:11  [DDB] Feedback (general): "testing feedback"
13:37:50  [CW] trace.started — "Now generate the IGCE..."
13:38:14  [CW] WARNING: GeneratorExit (client disconnect) elapsed=24071ms
...
```

### 3b. Classify Backend Events

From CloudWatch backend logs, extract and classify:

| Category | Pattern | Severity |
|---|---|---|
| Client disconnect | `GeneratorExit` | P0 if tools_called=[] (hung), P1 if mid-stream |
| Cascade violation | `CASCADE VIOLATION: web_search called without prior KB lookup` | P1 |
| Context overflow | `ContextWindowOverflowException` | P0 |
| Tool failure | `tool.*failed\|tool.*error` (case insensitive) | P0 |
| SSO expired | `Token has expired\|ExpiredToken` | P0 (actionable) |
| Throttling | `ThrottlingException` | P1 (warning) |
| Document ops | `Created document\|changelog_store: wrote` | Info (success) |
| Package ops | `Created package\|Set active package` | Info (success) |

### 3c. Extract Telemetry Metrics

From CloudWatch telemetry, extract:

- **conversation.quality**: `score`, `breakdown`, `flags` (look for `slow_response`)
- **stream.timing**: `duration_ms`, `tools_count`
- **trace.completed**: `duration_ms`, `total_input_tokens`, `total_output_tokens`, `tools_called`
- **tool.timing**: `tool_name`, `duration_ms` — flag any tool > 30s
- **agent.timing**: `agent_name`, `duration_ms`, `tools_called`

### 3d. Classify Feedback

From DynamoDB feedback items:

| feedback_type | Signal | Priority Boost |
|---|---|---|
| `bug` | User-reported defect | +3 |
| `incorrect_info` | Agent gave wrong answer | +3 |
| `thumbs_down` | Negative per-message rating | +2 |
| `suggestion` | Feature request | +1 |
| `praise` / `general` | Positive/neutral/info | +0 |

Ignore items with text like "testing feedback" or "test" (test submissions).

### 3e. Cross-Reference and Prioritize

For each feedback item, look for corroborating evidence in CW/Langfuse:
- Match timestamps (within +/- 2 minutes)
- Match tool names or error patterns mentioned in feedback text
- A feedback item corroborated by backend errors = higher priority

**Composite Severity (0-8)**:

| Factor | Weight | Range |
|---|---|---|
| User-facing (has feedback) | 3x | 0-3 |
| Frequency | 2x | 0-2 |
| Cross-source corroboration | 2x | 0-2 |
| Error severity (actionable vs warning) | 1x | 0-1 |

**Priority**: P0 (6-8), P1 (4-5), P2 (2-3), P3 (0-1)

---

## Phase 4: Output

### Spec File (default / `full` mode)

Scan `.claude/specs/` for existing `*-plan-triage-fixes-*.md` files. Use the next version number.

Write to `.claude/specs/{TIMESTAMP}-plan-triage-fixes-v{N}.md`:

```markdown
# Plan: Triage Fixes — {date} (Session {SESSION_ID_SHORT})

## Task Description
Fix {N} issues identified during session `{SESSION_ID}` on {date}.
Cross-referenced {N} DynamoDB feedback items, {N} CloudWatch events, and {N} Langfuse traces.

## Objective
Resolve all P0 and P1 issues. P2 items backlogged with clear file pointers.

## Problem Statement
{2-3 sentences: what went wrong, how many users affected, worst symptom}

## Relevant Files
| File | Issue |
|---|---|
| `server/app/...` | {what needs fixing} |

---

## Implementation Phases

### Phase 1: P0 Fixes (Critical)

#### 1. {Issue title}
- **Feedback**: {exact quote if available}
- **Evidence**: {CW/LF/telemetry corroboration}
- **Root cause**: {analysis}
- **File**: `{path}:{line}`
- **Fix**: {specific change}
- **Validation**: {how to verify}

{repeat for each P0}

### Phase 2: P1 Fixes (High)
{same format}

### Phase 3: P2 Improvements (Backlog)
{same format, briefer}

---

## Acceptance Criteria
- [ ] {one per P0/P1 issue}
- [ ] All validation commands pass
- [ ] Re-triage shows improvement

## Validation Commands
\```bash
ruff check app/
npx tsc --noEmit
python -m pytest tests/ -v
\```

## Notes
- Generated by /triage skill on {date}
- Session: `{SESSION_ID}`
- Sources: {N} feedback, {N} CW events, {N} LF traces
```

### Console Output (light mode)

Print the report to console without writing files:

```
Session Triage — {SESSION_ID}
Date: {date} | Env: {ENV} | Tenant: {tenant} | User: {user_id}

Source Summary
| Source              | Total | Issues |
|---------------------|-------|--------|
| DynamoDB Feedback   | {N}   | {N}    |
| CloudWatch Backend  | {N}   | {N}    |
| CloudWatch Telemetry| {N}   | {N}    |
| Langfuse Traces     | {N}   | {N}    |

Quality Scores
| Trace | Score | Flag | Duration |
|-------|-------|------|----------|
...

Top Issues (by severity)
| # | Issue | Sev | Sources | Evidence |
|---|-------|-----|---------|----------|
...

Recommendation: {1-2 sentence summary}
```

---

## Root Cause Investigation Tips

When analyzing issues, look up the actual source code to provide precise file:line references:

1. **For tool failures**: grep for the tool name in `server/app/tools/` and `server/app/strands_agentic_service.py`
2. **For document issues**: check `server/app/document_service.py`, `server/app/tools/package_document_tools.py`
3. **For streaming issues**: check `server/app/streaming_routes.py`, `server/app/strands_agentic_service.py` (GeneratorExit handler)
4. **For cascade violations**: grep for `CASCADE VIOLATION` in `server/app/strands_agentic_service.py`
5. **For KB/knowledge issues**: check `server/app/tools/knowledge_tools.py`
6. **For frontend issues**: check `client/components/chat-simple/simple-chat-interface.tsx`

Always read the relevant source before writing the fix recommendation — do not guess at line numbers.

---

## Known Error Patterns

### CloudWatch
| Pattern | Category | Severity |
|---|---|---|
| `GeneratorExit.*tools_called=\[\]` | Hung stream (no tool output) | P0 |
| `GeneratorExit.*elapsed_ms=[0-9]{5,}` | Long-running disconnect (>10s) | P1 |
| `CASCADE VIOLATION` | KB bypass | P1 |
| `ContextWindowOverflowException` | Context too large | P0 |
| `Token has expired` | SSO expired | P0 (actionable) |
| `ThrottlingException` | Bedrock rate limit | P1 |
| `AccessDeniedException` | IAM missing permission | P0 |
| `BadZipFile` | Corrupt upload | P1 |
| `OOM\|OutOfMemory\|SIGKILL` | Container crash | P0 |

### Langfuse
| Pattern | Category | Severity |
|---|---|---|
| `level=ERROR` on any observation | Model/tool error | P0-P1 |
| `output: null` with cost=0 | Request never reached model | P0 |
| Trace with 200K+ input tokens | Context bloat | P1 |
| Tool latency > 30s | Slow tool | P1 |

### Feedback
| feedback_type | Signal | Priority |
|---|---|---|
| `bug` | User-reported defect | P0 |
| `incorrect_info` | Wrong answer | P0 |
| `thumbs_down` | Negative rating | P1 |
| `suggestion` | Feature request | P2 |

---

## Relationship to /triage Command

The `/triage` command (`.claude/commands/triage.md`) does a **broad sweep** across all
recent sessions — it scans all feedback, all CW errors, and all Langfuse traces within
a time window to find patterns across the system.

This **triage skill** is **session-focused** — it deep-dives into a single session to
build a complete picture of what happened, correlate feedback with backend events, and
produce a targeted fix plan. Use this when you have a specific session to investigate.

Typical workflow:
1. `/triage light` → spot problematic sessions
2. `/triage {session_id}` → deep-dive into the worst one
