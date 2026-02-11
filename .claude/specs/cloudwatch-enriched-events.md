# Spec: CloudWatch Enriched Events — Tokens, Cost, Model, Agents per Test

## Problem

`emit_to_cloudwatch()` only emits: `test_id`, `test_name`, `status`, `log_lines`, `run_timestamp`.
`publish_eval_metrics()` only emits: `PassRate`, `TestsPassed/Failed/Skipped`, `TotalCost` (run-level), `TestStatus` per test.

TraceCollector captures **per test**: `total_input_tokens`, `total_output_tokens`, `total_cost_usd`, `session_id`, tool_use_blocks (contain agent/skill names). This data never flows to CloudWatch.

## Solution

### 1. New module-level store: `_test_summaries`

```python
_test_summaries: dict[int, dict] = {}
```

In `_run_test()`, right before clearing `TraceCollector._latest`, also capture summary:

```python
if TraceCollector._latest is not None and TraceCollector._latest.messages:
    try:
        _test_traces[test_id] = TraceCollector._latest.to_trace_json()
        _test_summaries[test_id] = TraceCollector._latest.summary()  # NEW
    except Exception:
        pass
    TraceCollector._latest = None
```

### 2. Enrich `emit_to_cloudwatch()` test_result events

For each test_id, look up `_test_summaries[test_id]` and add:

```json
{
  "type": "test_result",
  "test_id": 10,
  "test_name": "10_legal_counsel_skill",
  "status": "pass",
  "log_lines": 42,
  "run_timestamp": "2026-02-11T...",
  "model": "haiku",
  "input_tokens": 1234,
  "output_tokens": 567,
  "cost_usd": 0.001234,
  "session_id": "sess_abc...",
  "agents": ["legal-counsel"],
  "tools_used": ["create_document", "s3_read"]
}
```

Agent/skill names extracted from `_test_traces[test_id]` tool_use blocks where tool == "Task".

### 3. Enrich run_summary event

Aggregate across all tests:

```json
{
  "type": "run_summary",
  "run_timestamp": "...",
  "total_tests": 28,
  "passed": 25,
  "skipped": 0,
  "failed": 3,
  "pass_rate": 89.3,
  "model": "haiku",
  "total_input_tokens": 45000,
  "total_output_tokens": 12000,
  "total_cost_usd": 0.045
}
```

### 4. Enrich `publish_eval_metrics()`

Add new signature parameter: `test_summaries: dict = None`

New metrics:
- `TotalInputTokens` (aggregate, no dimension)
- `TotalOutputTokens` (aggregate, no dimension)
- Per-test: `InputTokens` with TestName dimension
- Per-test: `OutputTokens` with TestName dimension
- Per-test: `CostUSD` with TestName dimension

### 5. Update main() call site

Pass `_test_summaries` to `publish_eval_metrics`:

```python
publish_eval_metrics(results, run_ts_file, total_cost_usd=total_cost, test_summaries=_test_summaries)
```

## Files Modified

| File | Change |
|------|--------|
| `server/tests/test_eagle_sdk_eval.py` | Add `_test_summaries`, capture in `_run_test`, enrich `emit_to_cloudwatch` |
| `server/tests/eval_aws_publisher.py` | Add `test_summaries` param to `publish_eval_metrics`, emit per-test token/cost metrics |

## Verification

1. Syntax check both files
2. Run tests 18, 20 — no regressions
3. Check local telemetry mirror JSON for enriched fields
4. Check CloudWatch for enriched events
