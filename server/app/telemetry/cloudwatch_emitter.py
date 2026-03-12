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

LOG_GROUP = os.getenv("EAGLE_TELEMETRY_LOG_GROUP", "/eagle/app")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# Max size for preview fields (prompt, response, tool input/output)
_PREVIEW_LIMIT = 1000
_TOOL_IO_LIMIT = 2000

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


def _truncate(value, limit: int = _PREVIEW_LIMIT) -> str:
    """Safely truncate a value to string within limit."""
    s = str(value) if value else ""
    return s[:limit]


def _safe_json_preview(obj, limit: int = _TOOL_IO_LIMIT) -> str:
    """JSON-serialize an object, truncate to limit."""
    try:
        s = json.dumps(obj, default=str)
    except (TypeError, ValueError):
        s = str(obj)
    return s[:limit]


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
        - tool.started
        - tool.result
        - tool.completed  (legacy — kept for backwards compat)
        - agent.delegated
        - agent.completed
        - error.occurred
        - feedback.submitted
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
        stream_name = f"session/{session_id}" if session_id else f"tenant/{tenant_id}"

        _ensure_log_group_and_stream(client, stream_name)

        client.put_log_events(
            logGroupName=LOG_GROUP,
            logStreamName=stream_name,
            logEvents=[{
                "timestamp": event["timestamp"],
                "message": json.dumps(event, default=str),
            }],
        )
        logger.debug("CW emitted %s → %s/%s", event_type, LOG_GROUP, stream_name)
    except (ClientError, BotoCoreError, Exception) as e:
        # Telemetry should never break the main flow
        logger.warning("CW telemetry FAILED [%s]: %s", event_type, e)


def emit_trace_started(
    tenant_id: str,
    user_id: str,
    session_id: str,
    prompt_preview: str = "",
):
    """Emit trace.started when a chat request begins."""
    emit_telemetry_event(
        event_type="trace.started",
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        data={"prompt_preview": _truncate(prompt_preview, _PREVIEW_LIMIT)},
    )


def emit_trace_completed(summary: dict):
    """Emit trace.completed with full turn summary including per-tool metrics."""
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
            "response_preview": _truncate(
                summary.get("response_preview", ""), _PREVIEW_LIMIT
            ),
            "cycle_count": summary.get("cycle_count", 0),
            "stop_reason": summary.get("stop_reason", ""),
            "tool_metrics": summary.get("tool_metrics", {}),
        },
    )


def emit_tool_started(
    tenant_id: str,
    user_id: str,
    session_id: str,
    tool_name: str,
    tool_input: dict | str | None = None,
    tool_use_id: str = "",
):
    """Emit tool.started when a tool call begins (before execution)."""
    emit_telemetry_event(
        event_type="tool.started",
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        data={
            "tool_name": tool_name,
            "tool_use_id": tool_use_id,
            "tool_input": _safe_json_preview(tool_input, _TOOL_IO_LIMIT),
        },
    )


def emit_tool_result(
    tenant_id: str,
    user_id: str,
    session_id: str,
    tool_name: str,
    result_preview: str = "",
    duration_ms: int = 0,
    input_tokens: int = 0,
    output_tokens: int = 0,
    has_reasoning: bool = False,
    success: bool = True,
):
    """Emit tool.result when a tool call completes with full details."""
    emit_telemetry_event(
        event_type="tool.result",
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        data={
            "tool_name": tool_name,
            "result_preview": _truncate(result_preview, _TOOL_IO_LIMIT),
            "duration_ms": duration_ms,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "has_reasoning": has_reasoning,
            "success": success,
        },
    )


def emit_tool_completed(
    tenant_id: str,
    user_id: str,
    session_id: str,
    tool_name: str,
    duration_ms: int = 0,
    success: bool = True,
):
    """Emit tool.completed after a tool call finishes (legacy compat)."""
    emit_telemetry_event(
        event_type="tool.completed",
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        data={"tool_name": tool_name, "duration_ms": duration_ms, "success": success},
    )


def emit_feedback_submitted(
    tenant_id: str,
    user_id: str,
    session_id: str,
    feedback_type: str,
    feedback_id: str,
):
    """Emit feedback.submitted after feedback is written to DynamoDB."""
    emit_telemetry_event(
        event_type="feedback.submitted",
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        data={"feedback_type": feedback_type, "feedback_id": feedback_id},
    )
