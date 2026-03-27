"""
CloudWatch structured log emitter for telemetry events.

Uses the existing CloudWatch Logs integration. Emits structured JSON
that can be queried with CloudWatch Insights.
"""

import json
import logging
import os
import time

from botocore.exceptions import ClientError, BotoCoreError

from ..db_client import get_logs

logger = logging.getLogger("eagle.telemetry.cloudwatch")

LOG_GROUP = os.getenv("EAGLE_TELEMETRY_LOG_GROUP", "/eagle/telemetry")


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
        - tool.timing    — per-tool duration_ms (from streaming_routes)
        - stream.timing  — total SSE stream duration_ms
        - agent.timing   — supervisor agent duration_ms (from strands_agentic_service)
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
        client = get_logs()
        stream_name = (
            f"telemetry/{session_id}" if session_id else f"telemetry/{tenant_id}"
        )

        _ensure_log_group_and_stream(client, stream_name)

        client.put_log_events(
            logGroupName=LOG_GROUP,
            logStreamName=stream_name,
            logEvents=[
                {
                    "timestamp": event["timestamp"],
                    "message": json.dumps(event, default=str),
                }
            ],
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


def emit_trace_started(tenant_id: str, user_id: str, session_id: str, prompt: str):
    """Emit a trace.started event when a new agent invocation begins."""
    emit_telemetry_event(
        event_type="trace.started",
        tenant_id=tenant_id,
        session_id=session_id,
        user_id=user_id,
        data={"prompt_preview": prompt[:200] if prompt else ""},
    )


def emit_tool_completed(
    tenant_id: str,
    user_id: str,
    session_id: str,
    tool_name: str,
    duration_ms: int,
    success: bool,
):
    """Emit a tool.completed event after a tool call finishes."""
    emit_telemetry_event(
        event_type="tool.completed",
        tenant_id=tenant_id,
        session_id=session_id,
        user_id=user_id,
        data={"tool_name": tool_name, "duration_ms": duration_ms, "success": success},
    )


def emit_feedback_submitted(
    tenant_id: str,
    user_id: str,
    session_id: str,
    feedback_type: str,
    feedback_id: str,
):
    """Emit a feedback.submitted event when a user submits feedback."""
    emit_telemetry_event(
        event_type="feedback.submitted",
        tenant_id=tenant_id,
        session_id=session_id,
        user_id=user_id,
        data={"feedback_type": feedback_type, "feedback_id": feedback_id},
    )
