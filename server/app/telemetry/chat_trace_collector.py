"""
ChatTraceCollector — Trace collector for the direct Anthropic API path.

Parallel to TraceCollector (which processes SDK message types), this collector
works with raw token counts and explicit tool call/result recording from
stream_chat()'s tool-use loop. Produces the same summary()/to_trace_json()
shape so DynamoDB and CloudWatch persistence work unchanged.

No claude_agent_sdk dependency — pure Python.
"""
import time
import logging
from typing import Optional

logger = logging.getLogger("eagle.telemetry")

# Simple per-1K-token pricing lookup (USD)
# Update when model pricing changes.
MODEL_PRICING = {
    # Haiku 4.5
    "claude-haiku-4-5-20251001": {"input": 0.001, "output": 0.005},
    "us.anthropic.claude-haiku-4-5-20251001-v1:0": {"input": 0.001, "output": 0.005},
    # Sonnet 4
    "claude-sonnet-4-20250514": {"input": 0.003, "output": 0.015},
    "us.anthropic.claude-sonnet-4-20250514-v1:0": {"input": 0.003, "output": 0.015},
    # Opus 4
    "claude-opus-4-20250514": {"input": 0.015, "output": 0.075},
    "us.anthropic.claude-opus-4-20250514-v1:0": {"input": 0.015, "output": 0.075},
}

# Fallback pricing (Haiku-class)
_DEFAULT_PRICING = {"input": 0.001, "output": 0.005}


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate cost in USD from model name and token counts."""
    pricing = MODEL_PRICING.get(model, _DEFAULT_PRICING)
    return (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1000.0


class ChatTraceCollector:
    """Collects trace data from direct Anthropic API (stream_chat) calls.

    Usage:
        collector = ChatTraceCollector(tenant_id="acme", user_id="user-1")

        # After each API call:
        collector.record_api_call(input_tokens, output_tokens, model)

        # Around tool execution:
        collector.start_tool_span(tool_name, tool_input)
        # ... execute tool ...
        collector.end_tool_span(tool_name, output)

        # After stream_chat completes:
        summary = collector.summary()
        spans = collector.get_completed_spans()
    """

    def __init__(
        self,
        tenant_id: str = "default",
        user_id: str = "anonymous",
        session_id: Optional[str] = None,
    ):
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.session_id = session_id
        self.trace_id = f"t-{int(time.time() * 1000)}"
        self.start_time = time.time()

        # Token / cost accumulators
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        self.total_cost_usd: float = 0.0
        self.model: str = ""
        self.api_call_count: int = 0

        # Tool tracking
        self.tools_called: list[str] = []
        self._active_spans: dict[str, dict] = {}
        self._completed_spans: list[dict] = []

    def record_api_call(self, input_tokens: int, output_tokens: int, model: str):
        """Record token usage from one messages.stream() round-trip."""
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_cost_usd += _estimate_cost(model, input_tokens, output_tokens)
        self.model = model
        self.api_call_count += 1

    def start_tool_span(self, tool_name: str, tool_input: dict):
        """Begin timing a tool execution."""
        self._active_spans[tool_name] = {
            "name": f"tool.{tool_name}",
            "span_type": "tool",
            "start_time": time.time(),
            "input_data": {k: str(v)[:500] for k, v in tool_input.items()} if tool_input else {},
        }

    def end_tool_span(self, tool_name: str, output: str = ""):
        """End timing a tool execution and record the span."""
        span = self._active_spans.pop(tool_name, None)
        if not span:
            return
        end_time = time.time()
        span["duration_ms"] = int((end_time - span["start_time"]) * 1000)
        span["output_data"] = output[:2000] if output else ""
        # Remove raw timestamps for storage
        span.pop("start_time", None)
        self._completed_spans.append(span)

        if tool_name not in self.tools_called:
            self.tools_called.append(tool_name)

    def get_completed_spans(self) -> list[dict]:
        """Return all completed spans as dicts (matches SpanTracker interface)."""
        return list(self._completed_spans)

    def summary(self) -> dict:
        """Return a summary dict matching TraceCollector.summary() shape."""
        elapsed_ms = int((time.time() - self.start_time) * 1000)
        return {
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cost_usd": self.total_cost_usd,
            "duration_ms": elapsed_ms,
            "tools_called": self.tools_called,
            "agents_delegated": [],
            "api_call_count": self.api_call_count,
            "model": self.model,
        }

    def to_trace_json(self) -> list:
        """Serialize spans as a JSON-safe trace list."""
        trace = []
        for span in self._completed_spans:
            trace.append({
                "type": "tool_span",
                "name": span.get("name", ""),
                "duration_ms": span.get("duration_ms"),
                "input": span.get("input_data"),
                "output": span.get("output_data", "")[:500],
            })
        return trace
