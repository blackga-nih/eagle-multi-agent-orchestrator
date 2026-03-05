---
type: expert-file
file-type: index
domain: cloudwatch
tags: [expert, cloudwatch, telemetry, aws, boto3, logging, eagle]
---

# CloudWatch Expert

> CloudWatch Logs specialist for eval suite telemetry emission, structured event querying, and log pipeline maintenance.

## Domain Scope

This expert covers:
- **Telemetry Emission** - `emit_to_cloudwatch()` in `server/tests/test_eagle_sdk_eval.py` (~line 2224)
- **Log Group Structure** - `/eagle/test-runs` with per-run streams (`run-{ISO-timestamp}Z`)
- **Event Schemas** - `test_result` and `run_summary` structured JSON events
- **CloudWatch Logs Tool** - `_exec_cloudwatch_logs()` in `server/app/agentic_service.py` (~line 589)
- **boto3 API Patterns** - `put_log_events`, `describe_log_groups`, `describe_log_streams`, `get_log_events`, `filter_log_events`
- **Querying and Analysis** - Finding failures, aggregating pass rates, inspecting run history

## Available Commands

| Command | Purpose |
|---------|---------|
| `/experts:cloudwatch:question` | Answer CloudWatch questions without coding |
| `/experts:cloudwatch:plan` | Plan CloudWatch telemetry changes |
| `/experts:cloudwatch:self-improve` | Update expertise after telemetry work |
| `/experts:cloudwatch:plan_build_improve` | Full ACT-LEARN-REUSE workflow |
| `/experts:cloudwatch:maintenance` | Check connectivity, query runs, validate telemetry |

## Key Files

| File | Purpose |
|------|---------|
| `expertise.md` | Complete mental model for CloudWatch domain |
| `question.md` | Query command for read-only questions |
| `plan.md` | Planning command for CloudWatch changes |
| `self-improve.md` | Expertise update command |
| `plan_build_improve.md` | Full workflow command |
| `maintenance.md` | Connectivity checks and telemetry validation |

## Architecture

```
server/tests/test_eagle_sdk_eval.py
  |-- LOG_GROUP = "/eagle/test-runs"          # Constant (~line 2222)
  |-- emit_to_cloudwatch(trace_output, results)  # Emission function (~line 2224)
      |-- create_log_group (if needed)
      |-- create_log_stream: run-{timestamp}
      |-- build events: one test_result per test
      |-- build event: one run_summary
      |-- sort events by timestamp
      |-- put_log_events -> /eagle/test-runs/{stream}
      |-- Non-fatal: catches all exceptions

server/app/agentic_service.py
  |-- _exec_cloudwatch_logs(params, tenant_id)   # Tool handler (~line 589)
      |-- operation="get_stream" -> describe_log_streams
      |-- operation="recent"     -> filter_log_events (time-bounded)
      |-- operation="search"     -> filter_log_events (with filter_pattern)
      |-- Error handling: AccessDenied, ResourceNotFound, BotoCoreError
```

## ACT-LEARN-REUSE Pattern

```
ACT    ->  Modify emission pipeline, add queries, update schemas
LEARN  ->  Update expertise.md with patterns and failures
REUSE  ->  Apply patterns to future telemetry development
```
