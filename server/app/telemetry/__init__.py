"""
SDK-Native Telemetry Module

Zero external dependencies. Uses Claude Agent SDK message types,
hooks, and existing AWS infrastructure (DynamoDB, CloudWatch).
"""
from .trace_collector import TraceCollector
from .chat_trace_collector import ChatTraceCollector
from .span_tracker import SpanTracker, Span
from .status_messages import (
    AGENT_DISPLAY_NAMES,
    SKILL_DISPLAY_NAMES,
    TOOL_STATUS_MESSAGES,
    get_tool_status_message,
    get_agent_display_name,
)

__all__ = [
    "TraceCollector",
    "ChatTraceCollector",
    "SpanTracker",
    "Span",
    "AGENT_DISPLAY_NAMES",
    "SKILL_DISPLAY_NAMES",
    "TOOL_STATUS_MESSAGES",
    "get_tool_status_message",
    "get_agent_display_name",
]
