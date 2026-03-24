---
description: Query Langfuse traces for errors, latency issues, and usage patterns. Run on-demand or with /loop.
argument-hint: [1h|4h|24h|7d] [trace-id] [--errors|--slow|--all]
---

# Check Langfuse Traces

Query Langfuse Cloud API for recent traces, errors, and usage patterns across the EAGLE backend.

## Prerequisites

Langfuse credentials must be set in `server/.env`:
- `LANGFUSE_PUBLIC_KEY` (pk-lf-...)
- `LANGFUSE_SECRET_KEY` (sk-lf-...)
- `LANGFUSE_HOST` (default: https://us.cloud.langfuse.com)
- `LANGFUSE_PROJECT_ID` (for trace URLs)

Quick check — run this Python snippet to verify connectivity:

```bash
cd server && python -c "
import asyncio, os, base64, httpx
from dotenv import load_dotenv; load_dotenv('.env')
pub, sec = os.getenv('LANGFUSE_PUBLIC_KEY',''), os.getenv('LANGFUSE_SECRET_KEY','')
if not pub: print('ERROR: LANGFUSE_PUBLIC_KEY not set'); exit(1)
auth = 'Basic ' + base64.b64encode(f'{pub}:{sec}'.encode()).decode()
async def check():
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(f'{os.getenv(\"LANGFUSE_HOST\",\"https://us.cloud.langfuse.com\")}/api/public/traces', params={'limit':1}, headers={'Authorization': auth})
        print(f'OK — {r.status_code}, total traces: {r.json().get(\"meta\",{}).get(\"totalItems\",\"?\")}')
asyncio.run(check())
"
```

## Instructions

### If a specific trace ID is provided

1. Use the `langfuse_client.get_trace(trace_id)` function to fetch the trace
2. Use `langfuse_client.list_observations(trace_id=trace_id)` to get all spans/generations
3. Report:
   - Trace name, timestamp, latency, cost
   - User ID, session ID, tenant ID (from metadata.attributes)
   - Model used
   - Each observation: type, name, level, statusMessage, duration
   - Input/output summaries (truncate long system prompts)
   - If level=ERROR: highlight the error with root cause analysis

### If no trace ID — scan recent traces

1. Fetch traces using the Langfuse REST API directly (the `list_traces` wrapper has a known bug with `orderBy`). Use this pattern:

```python
import asyncio, json, httpx, base64, os
from dotenv import load_dotenv; load_dotenv('.env')

pub = os.getenv('LANGFUSE_PUBLIC_KEY')
sec = os.getenv('LANGFUSE_SECRET_KEY')
auth = 'Basic ' + base64.b64encode(f'{pub}:{sec}'.encode()).decode()
host = os.getenv('LANGFUSE_HOST', 'https://us.cloud.langfuse.com')

async with httpx.AsyncClient(timeout=15.0) as client:
    resp = await client.get(f'{host}/api/public/traces', params={'limit': 50}, headers={'Authorization': auth})
    data = resp.json()
```

2. **Time window:** Default is **1 hour**. Parse arguments:
   - `1h`, `4h`, `24h`, `7d` — filter by `fromTimestamp` parameter (ISO 8601)
   - `--errors` — only show traces with ERROR-level observations
   - `--slow` — only show traces with latency > 10s
   - `--all` — show all traces (not just errors)

3. **For each page of results**, categorize traces:
   - **Errors**: Fetch observations for error traces, extract `statusMessage`
   - **Successful**: Count, average latency, total cost
   - **Repeated inputs**: Flag duplicate/repeated messages (e.g., "Hello" spam)

4. **For error traces**, fetch observations to get root cause:
   ```python
   resp = await client.get(f'{host}/api/public/observations', params={'traceId': trace_id, 'limit': 20}, headers={'Authorization': auth})
   ```

## Known Error Patterns

| Pattern | Root Cause | Severity |
|---------|-----------|----------|
| `Token has expired and refresh failed` | AWS SSO session expired — Bedrock calls fail | ACTIONABLE |
| `ThrottlingException` | Bedrock rate limit hit | Warning |
| `ModelNotReadyException` | Bedrock cold start | Noise |
| `AccessDeniedException` | IAM role missing Bedrock permission | ACTIONABLE |
| `ValidationException` | Invalid model request (too long, bad params) | ACTIONABLE |
| Repeated "Hello" inputs with ERROR | Frontend health checks or retry loops hitting expired SSO | ACTIONABLE |
| `output: null` with cost=0 | Request never reached model (auth/infra failure) | ACTIONABLE |

## Report Format

```
EAGLE Langfuse Trace Scan — {timestamp}
Window: last {duration}
Project: {project_id}

Summary
┌──────────────────────┬───────┐
│ Total traces         │ {N}   │
│ Successful           │ {N}   │
│ Errors               │ {N}   │
│ Avg latency          │ {N}s  │
│ Total cost           │ ${N}  │
│ Unique users         │ {N}   │
│ Repeated inputs      │ {N}   │
└──────────────────────┴───────┘

Errors by Category
┌──────────────────────────────┬───────┬────────────┐
│ Error Type                   │ Count │ Severity   │
├──────────────────────────────┼───────┼────────────┤
│ SSO Token Expired            │ {N}   │ ACTIONABLE │
│ ...                          │ ...   │ ...        │
└──────────────────────────────┴───────┴────────────┘

Recent Errors (last 5)
  [{timestamp}] {trace_id} — {error_message}
    Model: {model} | User: {user_id} | Input: {first_50_chars}
    Langfuse URL: {trace_url}

Repeated Input Analysis
  "Hello" — {N} occurrences, {N} errors, {N} unique users
```

If zero errors found, report "All clear — no errors in the last {duration}."

## Langfuse Trace URL Format

```
https://us.cloud.langfuse.com/project/{LANGFUSE_PROJECT_ID}/traces/{trace_id}
```

## Hourly Loop Usage

```
/loop 1h /check-langfuse-logs
```
