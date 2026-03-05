# CloudWatch Plan: User ID Enrichment + Agent Query Tool

## Task
Ensure every document and log has the user_id so we can easily search by user_id. Including conversation logs. Then give the agent an enhanced tool to query CloudWatch logs with user_id filtering.

## Current State Audit

### Already has user_id
| Component | File | Status |
|-----------|------|--------|
| CloudWatch telemetry emitter | `telemetry/cloudwatch_emitter.py:64` | `user_id` in every event |
| ChatTraceCollector | `telemetry/chat_trace_collector.py:127` | `user_id` in summary() |
| DynamoDB trace store | `telemetry/dynamodb_trace_store.py:54` | `user_id` attribute |
| Local trace store | `telemetry/local_trace_store.py:50` | `user_id` attribute |
| Session messages (DynamoDB) | `session_store.py:334` | PK includes user_id: `SESSION#{tenant}#{user}` |
| Streaming routes | `streaming_routes.py:58,112` | user_id passed to add_message |

### Missing user_id
| Component | File | Gap |
|-----------|------|-----|
| Application logging | `main.py:111` | `format="%(message)s"` — no structured fields, no user_id |
| Streaming route logs | `streaming_routes.py:60,114,135,138` | Log messages don't include user_id |
| CloudWatch logs tool | `agentic_service.py:621` | No `user_id` parameter, can't filter by user |
| Strands tool description | `strands_agentic_service.py:699` | Doesn't mention user_id filtering |

## Changes

### 1. Structured JSON logging with user_id (`main.py`)
- Replace `format="%(message)s"` with a JSON formatter that includes user_id context
- Add a `ContextFilter` that injects `tenant_id` and `user_id` from a thread-local or context var

### 2. Enrich streaming route logs (`streaming_routes.py`)
- Include `user_id` and `tenant_id` in all logger calls

### 3. Add `user_id` filter to CloudWatch tool (`agentic_service.py`)
- Accept optional `user_id` param in `_exec_cloudwatch_logs`
- For `search` and `recent` operations, add user_id to filter pattern (same pattern as tenant scoping)
- For `get_stream`, filter results client-side or add user_id to stream prefix

### 4. Update Strands tool description (`strands_agentic_service.py`)
- Mention `user_id` optional parameter

### 5. Add conversation log query operation to CloudWatch tool
- New operation `query_conversations` that searches `/eagle/app` by user_id within a time window

## Verification
```bash
ruff check app/
# Manual: send chat message, verify user_id appears in CloudWatch /eagle/app logs
# Manual: use cloudwatch_logs tool with user_id param to filter results
```
