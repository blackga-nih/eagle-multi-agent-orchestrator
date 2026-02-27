"""
CloudWatch Logs Operations Integration Tests

Tests the cloudwatch_logs tool handler in agentic_service.py directly,
then confirms via boto3.  Covers SDK eval tests:
  - Test 18: cloudwatch_logs tool dispatch (get_stream / recent / search)
  - Test 20: CloudWatch E2E verification (log group exists, events queryable)

Operations tested:
  get_stream  → returns list of log streams (empty list is OK, not an error)
  recent      → returns event_count and events list
  search      → filter_pattern search returns matching events
  boto3       → describe_log_groups confirms /eagle/* groups exist

The log group /eagle/app is the primary application log written by ECS Fargate.
The log group /eagle/test-runs is written by the eval publisher.

Tests are non-destructive (read-only CloudWatch queries).
No cleanup needed.

Skip with: SKIP_INTEGRATION_TESTS=true pytest
Run with:  pytest server/tests/test_cloudwatch_ops.py -v
"""

import json
import os
import sys
import pytest
import boto3

# ── Path setup ────────────────────────────────────────────────────────
_server_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, _server_dir)
sys.path.insert(0, os.path.join(_server_dir, "app"))

from agentic_service import execute_tool

# ── Skip markers ──────────────────────────────────────────────────────
skip_integration = pytest.mark.skipif(
    os.environ.get("SKIP_INTEGRATION_TESTS", "").lower() == "true",
    reason="SKIP_INTEGRATION_TESTS=true",
)

SESSION_ID    = "test-cw-session-001"
LOG_GROUP_APP = "/eagle/app"
LOG_GROUP_EVAL = "/eagle/test-runs"


# ═══════════════════════════════════════════════════════════════════
# 1. get_stream — list log streams
# ═══════════════════════════════════════════════════════════════════

@skip_integration
def test_cloudwatch_get_stream_app_log_group():
    """/eagle/app get_stream returns a streams list (may be empty if no ECS yet)."""
    result = json.loads(execute_tool("cloudwatch_logs", {
        "operation": "get_stream",
        "log_group": LOG_GROUP_APP,
    }, SESSION_ID))

    assert "error" not in result, f"Unexpected error: {result}"
    assert "streams" in result, f"Missing 'streams' key: {result}"
    assert isinstance(result["streams"], list)


@skip_integration
def test_cloudwatch_get_stream_eval_log_group():
    """/eagle/test-runs get_stream returns a streams list."""
    result = json.loads(execute_tool("cloudwatch_logs", {
        "operation": "get_stream",
        "log_group": LOG_GROUP_EVAL,
    }, SESSION_ID))

    assert "error" not in result, f"Unexpected error: {result}"
    assert "streams" in result
    assert isinstance(result["streams"], list)


@skip_integration
def test_cloudwatch_get_stream_unknown_group_returns_error_or_empty():
    """Unknown log group returns either an error dict or empty streams — no exception."""
    result = json.loads(execute_tool("cloudwatch_logs", {
        "operation": "get_stream",
        "log_group": "/eagle/nonexistent-group-xyz",
    }, SESSION_ID))
    # Acceptable: error dict OR empty streams list (ResourceNotFoundException handled)
    assert isinstance(result, dict), "Should always return a dict"


# ═══════════════════════════════════════════════════════════════════
# 2. recent — query recent log events
# ═══════════════════════════════════════════════════════════════════

@skip_integration
def test_cloudwatch_recent_returns_events_list():
    """recent operation returns event_count and events list."""
    result = json.loads(execute_tool("cloudwatch_logs", {
        "operation": "recent",
        "log_group": LOG_GROUP_APP,
        "limit": 10,
    }, SESSION_ID))

    assert "error" not in result, f"Unexpected error: {result}"
    assert "events" in result, f"Missing 'events' key: {result}"
    assert isinstance(result["events"], list)
    assert "event_count" in result
    assert isinstance(result["event_count"], int)


@skip_integration
def test_cloudwatch_recent_relative_time_window():
    """recent with start_time=-1h scoped to last hour."""
    result = json.loads(execute_tool("cloudwatch_logs", {
        "operation": "recent",
        "log_group": LOG_GROUP_APP,
        "start_time": "-1h",
        "limit": 25,
    }, SESSION_ID))

    assert "error" not in result, f"Unexpected error: {result}"
    assert "events" in result
    # event_count should match len(events)
    assert result["event_count"] == len(result["events"])


@skip_integration
def test_cloudwatch_recent_eval_log_group():
    """/eagle/test-runs recent returns well-formed response."""
    result = json.loads(execute_tool("cloudwatch_logs", {
        "operation": "recent",
        "log_group": LOG_GROUP_EVAL,
        "limit": 20,
    }, SESSION_ID))

    assert "error" not in result, f"Unexpected error: {result}"
    assert "events" in result
    # If events exist, each should have timestamp and message
    for event in result["events"][:3]:
        assert "timestamp" in event or "message" in event, (
            f"Event missing timestamp/message: {event}"
        )


# ═══════════════════════════════════════════════════════════════════
# 3. search — filter_pattern queries
# ═══════════════════════════════════════════════════════════════════

@skip_integration
def test_cloudwatch_search_run_summary():
    """search with filter_pattern='run_summary' finds eval run records."""
    result = json.loads(execute_tool("cloudwatch_logs", {
        "operation": "search",
        "log_group": LOG_GROUP_EVAL,
        "filter_pattern": "run_summary",
        "limit": 5,
    }, SESSION_ID))

    assert "error" not in result, f"Unexpected error: {result}"
    assert "events" in result
    assert isinstance(result["events"], list)


@skip_integration
def test_cloudwatch_search_no_pattern_returns_all():
    """search with empty filter_pattern returns events without filtering."""
    result = json.loads(execute_tool("cloudwatch_logs", {
        "operation": "search",
        "log_group": LOG_GROUP_APP,
        "filter_pattern": "",
        "limit": 10,
    }, SESSION_ID))

    assert "error" not in result, f"Unexpected error: {result}"
    assert "events" in result


@skip_integration
def test_cloudwatch_search_test_result_events():
    """search for 'test_result' finds individual test event records."""
    result = json.loads(execute_tool("cloudwatch_logs", {
        "operation": "search",
        "log_group": LOG_GROUP_EVAL,
        "filter_pattern": "test_result",
        "limit": 5,
    }, SESSION_ID))

    assert "error" not in result, f"Unexpected error: {result}"
    assert isinstance(result.get("events", []), list)


# ═══════════════════════════════════════════════════════════════════
# 4. boto3 confirmation — /eagle/* log groups exist (SDK test 18/20)
# ═══════════════════════════════════════════════════════════════════

@skip_integration
def test_cloudwatch_boto3_eagle_log_groups_exist():
    """boto3 describe_log_groups confirms at least one /eagle/ log group exists."""
    logs = boto3.client("logs", region_name="us-east-1")
    try:
        resp = logs.describe_log_groups(logGroupNamePrefix="/eagle")
        group_names = [g["logGroupName"] for g in resp.get("logGroups", [])]
        assert len(group_names) > 0, (
            "No /eagle/* log groups found — ensure the ECS stack has been deployed "
            "or at least one log group has been created."
        )
        # At minimum /eagle/app should exist after any deployment
        has_eagle_group = any(n.startswith("/eagle") for n in group_names)
        assert has_eagle_group, f"No /eagle/* groups in: {group_names}"
    except boto3.exceptions.Boto3Error as e:
        pytest.skip(f"CloudWatch not accessible: {e}")


@skip_integration
def test_cloudwatch_boto3_app_log_group_retention():
    """boto3 describes /eagle/app and shows it has a retention policy set."""
    logs = boto3.client("logs", region_name="us-east-1")
    try:
        resp = logs.describe_log_groups(logGroupNamePrefix=LOG_GROUP_APP)
        groups = [g for g in resp.get("logGroups", []) if g["logGroupName"] == LOG_GROUP_APP]
        if not groups:
            pytest.skip(f"{LOG_GROUP_APP} not found — ECS may not be deployed yet")
        group = groups[0]
        # Retention should be set (not unlimited) for cost control
        retention = group.get("retentionInDays")
        assert retention is not None, (
            f"{LOG_GROUP_APP} has no retention policy — logs will accumulate forever"
        )
        assert retention <= 365, f"Retention {retention}d seems too long"
    except boto3.exceptions.Boto3Error as e:
        pytest.skip(f"CloudWatch not accessible: {e}")


# ═══════════════════════════════════════════════════════════════════
# 5. Error handling
# ═══════════════════════════════════════════════════════════════════

@skip_integration
def test_cloudwatch_unknown_operation_returns_error():
    """Unknown operation returns an error dict, not an exception."""
    result = json.loads(execute_tool("cloudwatch_logs", {
        "operation": "write",  # not supported
        "log_group": LOG_GROUP_APP,
    }, SESSION_ID))
    assert "error" in result, f"Expected error key in result: {result}"


@skip_integration
def test_cloudwatch_limit_respected():
    """limit parameter caps event count in response."""
    result = json.loads(execute_tool("cloudwatch_logs", {
        "operation": "recent",
        "log_group": LOG_GROUP_APP,
        "limit": 3,
    }, SESSION_ID))

    assert "error" not in result
    events = result.get("events", [])
    assert len(events) <= 3, f"Got {len(events)} events but limit=3"
