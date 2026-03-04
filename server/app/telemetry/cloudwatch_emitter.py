"""
CloudWatch structured log emitter for telemetry events.

Uses the existing CloudWatch Logs integration. Emits structured JSON
that can be queried with CloudWatch Insights.
"""
import json
import logging
import os
import time

import boto3
from botocore.exceptions import ClientError, BotoCoreError

logger = logging.getLogger("eagle.telemetry.cloudwatch")

LOG_GROUP = os.getenv("EAGLE_TELEMETRY_LOG_GROUP", "/eagle/telemetry")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

_logs_client = None


def _get_client():
    global _logs_client
    if _logs_client is None:
        _logs_client = boto3.client("logs", region_name=AWS_REGION)
    return _logs_client


def _ensure_log_group_and_stream(client, stream_name: str):
    """Create log group and stream if they don't exist."""
    try:
        client.create_log_group(logGroupName=LOG_GROUP)
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceAlreadyExistsException":
            raise
    try:
        client.create_log_stream(logGroupName=LOG_GROUP, logStreamName=stream_name)
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceAlreadyExistsException":
            raise


def emit_telemetry_event(
    event_type: str,
    tenant_id: str,
    data: dict,
    session_id: str = None,
    user_id: str = None,
):
    """Emit a structured telemetry event to CloudWatch Logs.

    Event types:
        - trace.started
        - trace.completed
        - tool.completed
        - agent.delegated
        - agent.completed
        - error.occurred
    """
    event = {
        "event_type": event_type,
        "tenant_id": tenant_id,
        "user_id": user_id or "anonymous",
        "session_id": session_id,
        "timestamp": int(time.time() * 1000),
        **data,
    }

    try:
        client = _get_client()
        stream_name = f"telemetry/{tenant_id}"

        _ensure_log_group_and_stream(client, stream_name)

        client.put_log_events(
            logGroupName=LOG_GROUP,
            logStreamName=stream_name,
            logEvents=[{
                "timestamp": event["timestamp"],
                "message": json.dumps(event, default=str),
            }],
        )
    except (ClientError, BotoCoreError, Exception) as e:
        # Telemetry should never break the main flow
        logger.warning("Failed to emit telemetry event: %s", e)


def emit_trace_completed(summary: dict):
    """Convenience: emit a trace.completed event from a TraceCollector summary."""
    emit_telemetry_event(
        event_type="trace.completed",
        tenant_id=summary.get("tenant_id", "default"),
        session_id=summary.get("session_id"),
        user_id=summary.get("user_id"),
        data={
            "trace_id": summary.get("trace_id"),
            "duration_ms": summary.get("duration_ms"),
            "total_input_tokens": summary.get("total_input_tokens"),
            "total_output_tokens": summary.get("total_output_tokens"),
            "total_cost_usd": summary.get("total_cost_usd"),
            "tools_called": summary.get("tools_called", []),
            "agents_delegated": summary.get("agents_delegated", []),
        },
    )
