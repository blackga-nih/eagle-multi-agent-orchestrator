---
type: expert-file
parent: "[[cloudwatch/_index]]"
file-type: expertise
human_reviewed: false
tags: [expert-file, mental-model, cloudwatch, telemetry, aws, boto3, logging]
last_updated: 2026-02-11T22:00:00
---

# CloudWatch Expertise (Complete Mental Model)

> **Sources**: server/tests/test_eagle_sdk_eval.py (~line 2222-2311), server/app/agentic_service.py (~line 589-705)

---

## Part 1: Architecture

### Overview

CloudWatch Logs is the sole telemetry backend for the EAGLE eval suite. There is no OpenTelemetry, Prometheus, or Grafana in this project. All structured test results flow through a single log group with per-run streams.

### Log Group Structure

```
/eagle/test-runs/                         # Log group (created on first emission)
  |-- run-2026-02-09T12-00-00.000000Z/   # Per-run stream (ISO timestamp, colons replaced)
  |   |-- test_result event (test_id=1)
  |   |-- test_result event (test_id=2)
  |   |-- ...
  |   |-- test_result event (test_id=20)
  |   |-- run_summary event
  |
  |-- run-2026-02-09T13-00-00.000000Z/   # Next run
  |   |-- ...
```

### Stream Naming Convention

```python
run_ts = trace_output.get("timestamp", datetime.now(timezone.utc).isoformat())
stream_name = f"run-{run_ts.replace(':', '-').replace('+', 'Z')}"
```

- Colons in ISO timestamps are replaced with hyphens (CloudWatch stream name restriction)
- `+` replaced with `Z` for UTC offset normalization
- Example: `2026-02-09T14:30:00.000000+00:00` becomes `run-2026-02-09T14-30-00.000000Z00-00`

### Event Flow

```
server/tests/test_eagle_sdk_eval.py main()
  |-- Run all tests, collect results dict
  |-- Write trace_logs.json (always succeeds)
  |-- emit_to_cloudwatch(trace_output, results)
      |-- boto3.client("logs", region_name="us-east-1")
      |-- create_log_group (idempotent)
      |-- create_log_stream (idempotent)
      |-- Build test_result events (one per test)
      |-- Build run_summary event (one per run)
      |-- Sort events by timestamp
      |-- put_log_events()
      |-- Print confirmation or error (non-fatal)
```

### Region

All CloudWatch operations use `us-east-1`:
```python
client = boto3.client("logs", region_name=os.environ.get("AWS_REGION", "us-east-1"))
```

---

## Part 2: Event Schemas

### test_result Event

One event per test in a run. Emitted as JSON in the `message` field of a CloudWatch log event.

```json
{
  "type": "test_result",
  "test_id": 1,
  "test_name": "1_session_creation",
  "status": "pass",
  "log_lines": 42,
  "run_timestamp": "2026-02-09T14:30:00.000000+00:00",
  "model": "haiku",
  "input_tokens": 14330,
  "output_tokens": 29,
  "cost_usd": 0.018057,
  "session_id": "d454c326-...",
  "agents": ["legal-counsel"],
  "tools_used": ["create_document"]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Always `"test_result"` |
| `test_id` | integer | Test number (1-28) |
| `test_name` | string | Format: `{N}_{snake_case_name}` |
| `status` | string | One of: `"pass"`, `"fail"`, `"skip"`, `"unknown"` |
| `log_lines` | integer | Number of captured stdout lines for this test |
| `run_timestamp` | string | ISO 8601 timestamp of the run |
| `model` | string | Model used for the run (e.g., `"haiku"`, `"sonnet"`) |
| `input_tokens` | integer | Total input tokens (incl. cache) for this test; 0 if no LLM call |
| `output_tokens` | integer | Total output tokens for this test; 0 if no LLM call |
| `cost_usd` | float | Total cost in USD for this test; 0.0 if no LLM call |
| `session_id` | string? | SDK session ID if available (omitted if none) |
| `agents` | string[]? | Subagent names invoked via Task tool (omitted if empty) |
| `tools_used` | string[]? | Non-Task tool names used (omitted if empty) |

#### test_name Mapping

```python
test_names = {
    1: "1_session_creation",       2: "2_session_resume",
    3: "3_trace_observation",      4: "4_subagent_orchestration",
    5: "5_cost_tracking",          6: "6_tier_gated_tools",
    7: "7_skill_loading",          8: "8_subagent_tool_tracking",
    9: "9_oa_intake_workflow",    10: "10_legal_counsel_skill",
   11: "11_market_intelligence_skill", 12: "12_tech_review_skill",
   13: "13_public_interest_skill", 14: "14_document_generator_skill",
   15: "15_supervisor_multi_skill_chain",
   16: "16_s3_document_ops",      17: "17_dynamodb_intake_ops",
   18: "18_cloudwatch_logs_ops",  19: "19_document_generation",
   20: "20_cloudwatch_e2e_verification",
}
```

#### Status Values

| Status | Meaning | Python Value |
|--------|---------|-------------|
| `pass` | Test passed all assertions | `True` |
| `fail` | Test failed an assertion or threw an exception | `False` |
| `skip` | Test was skipped (e.g., MCP race condition) | `None` |
| `unknown` | Status not in trace data (fallback) | missing |

### run_summary Event

One event per run, emitted after all test_result events.

```json
{
  "type": "run_summary",
  "run_timestamp": "2026-02-09T14:30:00.000000+00:00",
  "total_tests": 20,
  "passed": 18,
  "skipped": 1,
  "failed": 1,
  "pass_rate": 90.0,
  "model": "haiku",
  "total_input_tokens": 45000,
  "total_output_tokens": 12000,
  "total_cost_usd": 0.045
}
```

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Always `"run_summary"` |
| `run_timestamp` | string | ISO 8601 timestamp of the run |
| `total_tests` | integer | Number of tests executed (`len(results)`) |
| `passed` | integer | Count where result is `True` |
| `skipped` | integer | Count where result is `None` |
| `failed` | integer | Count where result is not `True` and not `None` |
| `pass_rate` | float | `round(passed / max(total_tests, 1) * 100, 1)` |
| `model` | string | Model used for the run |
| `total_input_tokens` | integer | Aggregate input tokens across all tests |
| `total_output_tokens` | integer | Aggregate output tokens across all tests |
| `total_cost_usd` | float | Aggregate cost in USD across all tests |

#### Invariant

```
passed + skipped + failed == total_tests
```

This is validated by test 20 (`cloudwatch_e2e_verification`).

---

## Part 3: Emission Pipeline

### emit_to_cloudwatch Function

Location: `server/tests/test_eagle_sdk_eval.py` (~line 3076)

```python
def emit_to_cloudwatch(trace_output: dict, results: dict):
```

#### Data Sources

The function reads from two module-level stores populated by `_run_test()`:
- `_test_summaries[test_id]` — `TraceCollector.summary()` dict with tokens, cost, session_id
- `_test_traces[test_id]` — `TraceCollector.to_trace_json()` list for agent/tool extraction

#### Parameters

| Parameter | Type | Source |
|-----------|------|--------|
| `trace_output` | dict | The full trace output dict (contains `timestamp`, `results` with per-test data) |
| `results` | dict | Maps result_key to `True`/`False`/`None` (pass/fail/skip) |

#### Pipeline Steps

1. **Create boto3 client**: `boto3.client("logs", region_name="us-east-1")`
2. **Ensure log group**: `create_log_group(logGroupName="/eagle/test-runs")` - catches `ResourceAlreadyExistsException`
3. **Create log stream**: `create_log_stream(logGroupName=..., logStreamName=stream_name)` - catches `ResourceAlreadyExistsException`
4. **Build test_result events**: Iterates `trace_output["results"]`, enriches each with model, tokens, cost, session_id, agents, tools from `_test_summaries` and `_test_traces`; `timestamp = now_ms + test_id`
5. **Build run_summary event**: Aggregates results + token/cost totals, `timestamp = now_ms + 100`
6. **Sort events**: `events.sort(key=lambda e: e["timestamp"])` - **required by CloudWatch**
7. **Put events**: `client.put_log_events(logGroupName=..., logStreamName=..., logEvents=events)`
8. **Print confirmation**: `"CloudWatch: emitted {N} events to {LOG_GROUP}/{stream_name}"`
9. **Local mirror**: Writes events JSON to `data/eval/telemetry/cw-{ts}.json`

#### Timestamp Assignment

```python
now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

# test_result events: offset by test_id (1-20)
timestamp = now_ms + test_id

# run_summary event: offset by 100
timestamp = now_ms + 100
```

This ensures deterministic ordering: tests 1-20 first, then summary at +100.

#### Error Handling

The entire function is wrapped in a try/except that catches **all exceptions**:

```python
try:
    # ... entire pipeline ...
except Exception as e:
    print(f"CloudWatch: emission failed (non-fatal): {type(e).__name__}: {e}")
```

This is intentionally non-fatal. The local `trace_logs.json` file is always written before `emit_to_cloudwatch` is called, so results are never lost.

#### Common Failure Modes

| Exception | Cause | Impact |
|-----------|-------|--------|
| `NoCredentialsError` | AWS credentials not configured | Emission skipped, local file OK |
| `ClientError (AccessDenied)` | IAM policy missing `logs:*` | Emission skipped |
| `EndpointConnectionError` | No network / wrong region | Emission skipped |
| `InvalidSequenceTokenException` | Stream already has events (rare) | Emission skipped |

---

## Part 4: CloudWatch Logs Tool

### _exec_cloudwatch_logs Function

Location: `server/app/agentic_service.py` (~line 589)

This is the agent's tool for querying CloudWatch Logs at runtime, exposed as `cloudwatch_logs` via `execute_tool()`.

```python
def _exec_cloudwatch_logs(params: dict, tenant_id: str) -> dict:
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `operation` | string | `"recent"` | One of: `get_stream`, `recent`, `search` |
| `log_group` | string | `"/eagle/app"` | CloudWatch log group name |
| `filter_pattern` | string | `""` | CloudWatch filter pattern (for `search`) |
| `limit` | integer | `50` | Max events to return (capped at 100) |
| `start_time` | string | `""` | Start time: ISO string or relative (`"-1h"`, `"-30m"`, `"-24h"`) |
| `end_time` | string | `""` | End time: ISO string |

### Operation: get_stream

Lists the 5 most recent log streams in a log group, ordered by last event time.

```python
execute_tool("cloudwatch_logs", {
    "operation": "get_stream",
    "log_group": "/eagle/test-runs"
}, session_id)
```

**Return shape**:
```json
{
  "operation": "get_stream",
  "log_group": "/eagle/test-runs",
  "streams": [
    {"logStreamName": "run-2026-02-09T14-30-00Z", "lastEventTimestamp": 1739107800000}
  ]
}
```

**boto3 call**: `describe_log_streams(logGroupName=..., orderBy="LastEventTime", descending=True, limit=5)`

### Operation: recent

Fetches recent log events from a log group within a time window.

```python
execute_tool("cloudwatch_logs", {
    "operation": "recent",
    "log_group": "/eagle/test-runs",
    "limit": 25,
    "start_time": "-1h"
}, session_id)
```

**Return shape**:
```json
{
  "operation": "recent",
  "log_group": "/eagle/test-runs",
  "event_count": 21,
  "events": [
    {"timestamp": 1739107800001, "message": "{...json...}", "logStreamName": "run-..."}
  ]
}
```

**boto3 call**: `filter_log_events(logGroupName=..., startTime=..., endTime=..., limit=...)`

**Note**: Messages are truncated to 500 characters.

### Operation: search

Searches log events with a CloudWatch filter pattern, scoped by tenant_id.

```python
execute_tool("cloudwatch_logs", {
    "operation": "search",
    "log_group": "/eagle/test-runs",
    "filter_pattern": "test_result",
    "start_time": "-24h"
}, session_id)
```

**Return shape**:
```json
{
  "operation": "search",
  "log_group": "/eagle/test-runs",
  "filter_pattern": "\"demo-tenant\" test_result",
  "event_count": 20,
  "events": [
    {"timestamp": 1739107800001, "message": "{...json...}", "logStreamName": "run-..."}
  ]
}
```

**Tenant scoping**: The tool automatically prepends `"{tenant_id}"` to the filter pattern unless the tenant_id is already present.

**boto3 call**: `filter_log_events(logGroupName=..., filterPattern=..., startTime=..., endTime=..., limit=...)`

### Time Parsing

The tool supports two time formats for `start_time`:

| Format | Example | Behavior |
|--------|---------|----------|
| Relative | `"-1h"`, `"-30m"`, `"-24h"` | Offset from now. Units: `m`=minutes, `h`=hours, `d`=days |
| ISO 8601 | `"2026-02-09T14:00:00Z"` | Absolute timestamp, `Z` replaced with `+00:00` |

Default: last 1 hour (`now - 3600 * 1000` to `now`).

### Error Handling

| Error Code | Response |
|------------|----------|
| `AccessDenied` / `AccessDeniedException` | `{"error": "AWS permission denied...", "detail": ..., "suggestion": ...}` |
| `ResourceNotFoundException` | `{"error": "Log group '...' not found."}` |
| Other `ClientError` | `{"error": "CloudWatch error ({code}): {msg}"}` |
| `BotoCoreError` | `{"error": "AWS connection error: ..."}` |

---

## Part 5: boto3 API Patterns

### Client Initialization

```python
# Emission (server/tests/test_eagle_sdk_eval.py)
client = boto3.client("logs", region_name=os.environ.get("AWS_REGION", "us-east-1"))

# Tool handler (agentic_service.py) — uses cached client via _get_logs()
logs = _get_logs()  # Returns boto3.client("logs", region_name="us-east-1")
```

### put_log_events

Used by `emit_to_cloudwatch()` to write test results.

```python
client.put_log_events(
    logGroupName="/eagle/test-runs",
    logStreamName="run-2026-02-09T14-30-00Z",
    logEvents=[
        {"timestamp": 1739107800001, "message": '{"type":"test_result",...}'},
        {"timestamp": 1739107800002, "message": '{"type":"test_result",...}'},
        # ...
        {"timestamp": 1739107800100, "message": '{"type":"run_summary",...}'},
    ],
)
```

**Requirements**:
- Events MUST be sorted by timestamp in ascending order
- Timestamps are in milliseconds since epoch (UTC)
- Each message is a JSON string
- Max batch size: 1MB or 10,000 events (we send ~21 per run)

### create_log_group / create_log_stream

Used by `emit_to_cloudwatch()` for idempotent creation.

```python
try:
    client.create_log_group(logGroupName="/eagle/test-runs")
except client.exceptions.ResourceAlreadyExistsException:
    pass

try:
    client.create_log_stream(logGroupName="/eagle/test-runs", logStreamName=stream_name)
except client.exceptions.ResourceAlreadyExistsException:
    pass
```

### describe_log_streams

Used by `_exec_cloudwatch_logs` (operation=`get_stream`) and test 20.

```python
resp = logs.describe_log_streams(
    logGroupName="/eagle/test-runs",
    orderBy="LastEventTime",
    descending=True,
    limit=5,
)
streams = resp.get("logStreams", [])
# Each stream: {"logStreamName": "run-...", "lastEventTimestamp": ..., ...}
```

### filter_log_events

Used by `_exec_cloudwatch_logs` (operations `recent` and `search`).

```python
resp = logs.filter_log_events(
    logGroupName="/eagle/test-runs",
    filterPattern='"test_result"',  # CloudWatch filter syntax
    startTime=start_ms,
    endTime=end_ms,
    limit=100,
)
events = resp.get("events", [])
# Each event: {"timestamp": ..., "message": "...", "logStreamName": "..."}
```

### get_log_events

Used by test 20 (`cloudwatch_e2e_verification`) to read events from a specific stream.

```python
resp = logs.get_log_events(
    logGroupName="/eagle/test-runs",
    logStreamName="run-2026-02-09T14-30-00Z",
    startFromHead=True,
)
events = resp.get("events", [])
```

### describe_log_groups

Used by test 18 (`cloudwatch_logs_ops`) for boto3 independent confirmation.

```python
resp = logs.describe_log_groups(
    logGroupNamePrefix="/eagle",
)
groups = resp.get("logGroups", [])
```

---

## Part 6: Querying and Analysis

### Find the Most Recent Run

```python
# Via tool
result = execute_tool("cloudwatch_logs", {
    "operation": "get_stream",
    "log_group": "/eagle/test-runs"
}, session_id)
# result["streams"][0]["logStreamName"] -> most recent stream

# Via boto3
logs = boto3.client("logs", region_name="us-east-1")
resp = logs.describe_log_streams(
    logGroupName="/eagle/test-runs",
    orderBy="LastEventTime",
    descending=True,
    limit=1,
)
latest_stream = resp["logStreams"][0]["logStreamName"]
```

### Read All Events from a Run

```python
resp = logs.get_log_events(
    logGroupName="/eagle/test-runs",
    logStreamName=latest_stream,
    startFromHead=True,
)
for event in resp["events"]:
    data = json.loads(event["message"])
    if data["type"] == "test_result":
        print(f"  Test {data['test_id']}: {data['status']}")
    elif data["type"] == "run_summary":
        print(f"  Summary: {data['passed']}P {data['failed']}F {data['skipped']}S")
```

### Find All Failures Across Runs

```python
# Via tool
result = execute_tool("cloudwatch_logs", {
    "operation": "search",
    "log_group": "/eagle/test-runs",
    "filter_pattern": '"fail"',
    "start_time": "-24h"
}, session_id)

# Via boto3
resp = logs.filter_log_events(
    logGroupName="/eagle/test-runs",
    filterPattern='"fail"',
    startTime=int((datetime.now(timezone.utc) - timedelta(hours=24)).timestamp() * 1000),
    endTime=int(datetime.now(timezone.utc).timestamp() * 1000),
)
```

### Aggregate Pass Rates Over Time

```python
# 1. List recent streams
resp = logs.describe_log_streams(
    logGroupName="/eagle/test-runs",
    orderBy="LastEventTime",
    descending=True,
    limit=10,
)

# 2. For each stream, find the run_summary event
for stream in resp["logStreams"]:
    events_resp = logs.get_log_events(
        logGroupName="/eagle/test-runs",
        logStreamName=stream["logStreamName"],
        startFromHead=True,
    )
    for event in events_resp["events"]:
        data = json.loads(event["message"])
        if data["type"] == "run_summary":
            print(f"{stream['logStreamName']}: {data['pass_rate']}% ({data['passed']}/{data['total_tests']})")
```

### Find a Specific Test Across Runs

```python
# Find all results for test 17 (DynamoDB)
resp = logs.filter_log_events(
    logGroupName="/eagle/test-runs",
    filterPattern='"test_id": 17',
    startTime=int((datetime.now(timezone.utc) - timedelta(days=7)).timestamp() * 1000),
)
for event in resp["events"]:
    data = json.loads(event["message"])
    print(f"  {event['logStreamName']}: test_id={data['test_id']} status={data['status']}")
```

### AWS CLI Equivalents

```bash
# List recent streams
aws logs describe-log-streams \
  --log-group-name /eagle/test-runs \
  --order-by LastEventTime \
  --descending \
  --limit 5

# Get events from a stream
aws logs get-log-events \
  --log-group-name /eagle/test-runs \
  --log-stream-name "run-2026-02-09T14-30-00Z" \
  --start-from-head

# Search for failures
aws logs filter-log-events \
  --log-group-name /eagle/test-runs \
  --filter-pattern '"fail"' \
  --start-time $(date -d '-24 hours' +%s000)
```

---

## Part 7: Known Issues

### Eventual Consistency

CloudWatch Logs has eventual consistency for reads after writes. Test 20 (`cloudwatch_e2e_verification`) validates the **previous** run's data, not the current run, because events from the current run may not be immediately queryable.

**Impact**: If you run the eval suite twice in rapid succession, test 20 may read stale data from two runs ago.

**Mitigation**: Wait at least 5-10 seconds between runs if test 20 accuracy matters.

### Sequence Tokens (Legacy)

Older versions of the `put_log_events` API required a `sequenceToken` for appending to an existing stream. Modern boto3 handles this automatically. The emission function creates a new stream per run, so sequence tokens are never an issue.

**If you see `InvalidSequenceTokenException`**: This means a stream was reused (should not happen with the `run-{timestamp}` naming pattern). The exception is caught by the non-fatal handler.

### Log Group Creation Race

If multiple processes call `emit_to_cloudwatch` simultaneously, both may try to create the log group. The `ResourceAlreadyExistsException` catch handles this safely.

### Stream Name Character Restrictions

CloudWatch stream names cannot contain colons (`:`). The emission function replaces them:
```python
stream_name = f"run-{run_ts.replace(':', '-').replace('+', 'Z')}"
```

If the timestamp format changes (e.g., different ISO variant), the replacement logic may need updating.

### Message Size Limit

CloudWatch log event messages have a 256 KB limit. The structured JSON events are well under this (typically < 200 bytes). However, if `log_lines` counts are ever replaced with actual log content, this limit could be hit.

### Tool Default Log Group Mismatch

The `_exec_cloudwatch_logs` tool defaults to `"/eagle/app"` (the application log group), not `"/eagle/test-runs"` (the eval telemetry log group). When querying test runs via the tool, you must explicitly set `log_group`:

```python
execute_tool("cloudwatch_logs", {
    "operation": "recent",
    "log_group": "/eagle/test-runs"  # Must specify explicitly
}, session_id)
```

### Filter Pattern Tenant Scoping

The `search` operation in `_exec_cloudwatch_logs` automatically prepends the tenant_id to the filter pattern. This is correct for application logs but may cause unexpected filtering when querying `/eagle/test-runs` (which does not contain tenant_id in events). When searching test-runs, use the `recent` operation or bypass tenant scoping by including the tenant_id in your filter pattern.

### 500-Character Message Truncation

The `_exec_cloudwatch_logs` tool truncates event messages to 500 characters:
```python
"message": e["message"][:500]
```

With enriched events (tokens, cost, model, agents, tools), test_result events are ~300-500 bytes. run_summary events ~250 bytes. Still within 500 chars but getting close — watch for truncation if adding more fields.

---

## Part 8: CloudWatch Custom Metrics (EAGLE/Eval)

Location: `server/tests/eval_aws_publisher.py` — `publish_eval_metrics()`

### Namespace

`EAGLE/Eval`

### Aggregate Metrics (no dimensions)

| Metric | Unit | Description |
|--------|------|-------------|
| `PassRate` | Percent | Overall pass rate for the run |
| `TestsPassed` | Count | Number of passing tests |
| `TestsFailed` | Count | Number of failing tests |
| `TestsSkipped` | Count | Number of skipped tests |
| `TotalCost` | None | Total USD cost for the run (if > 0) |
| `TotalInputTokens` | Count | Aggregate input tokens across all tests (if > 0) |
| `TotalOutputTokens` | Count | Aggregate output tokens across all tests (if > 0) |

### Per-Run Metrics (RunId dimension)

| Metric | Dimension | Unit |
|--------|-----------|------|
| `PassRate` | `RunId=<timestamp>` | Percent |

### Per-Test Metrics (TestName dimension)

| Metric | Dimension | Unit | Description |
|--------|-----------|------|-------------|
| `TestStatus` | `TestName` | None | 1.0 = pass, 0.0 = fail/skip |
| `InputTokens` | `TestName` | Count | Per-test input tokens (if > 0) |
| `OutputTokens` | `TestName` | Count | Per-test output tokens (if > 0) |
| `CostUSD` | `TestName` | None | Per-test cost in USD (if > 0) |

### API Batching

CloudWatch `put_metric_data` has a limit of 1000 metric data points per call. The publisher batches in chunks of 1000.

---

## Learnings

### patterns_that_work
- Per-run streams with ISO timestamp naming provide clean run isolation
- Non-fatal emission with local file fallback ensures no data loss
- Idempotent create_log_group/create_log_stream handles first-run and race conditions
- Timestamp offset by test_id ensures deterministic event ordering
- run_summary invariant (passed + skipped + failed == total) enables validation
- `_test_summaries` dict (parallel to `_test_traces`) captures per-test token/cost data from TraceCollector.summary() before it's cleared
- Enriched test_result events include model, input_tokens, output_tokens, cost_usd, session_id, agents[], tools_used[] — all optional/gracefully defaulting
- `_extract_agents_and_tools()` helper walks trace JSON to find Task tool invocations (agents) and other tool names
- publish_eval_metrics batches put_metric_data in chunks of 1000 (CloudWatch API limit)
- Per-test InputTokens/OutputTokens/CostUSD metrics use TestName dimension for drill-down

### patterns_to_avoid
- Don't query the current run's events in the same execution (eventual consistency)
- Don't rely on the tool's default log_group when querying test-runs
- Don't use the `search` operation for test-runs without accounting for tenant scoping
- Don't embed large payloads in event messages (256 KB limit)
- Don't clear TraceCollector._latest before capturing both trace and summary

### common_issues
- AWS credentials not configured -> emission silently skipped
- Log group doesn't exist on first run -> auto-created, but describe_log_streams returns empty
- `search` operation adds tenant_id prefix -> unexpected results for test-run queries
- boto3-only tests (18, 20) report tokens=0, cost=0 — this is correct, not a bug (no LLM calls)

### tips
- Test 18 validates the CloudWatch tool; test 20 validates the emission pipeline
- Use `get_stream` operation to find the latest run, then `get_log_events` to read it
- The `recent` operation is better than `search` for test-runs (no tenant scoping)
- Check `trace_logs.json` first for quick debugging; CloudWatch is for historical analysis
- Local telemetry mirror at `data/eval/telemetry/cw-*.json` has the same events as CloudWatch — useful for offline verification
- To verify enriched fields, run a single LLM test (e.g., `--tests 1`) and check the telemetry mirror JSON
