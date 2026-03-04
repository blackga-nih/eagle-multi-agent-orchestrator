"""
SpanTracker — Lightweight span tracking using SDK hooks.

No external dependencies. Uses SDK PreToolUse/PostToolUse/SubagentStart/SubagentStop
hooks to build a span tree with timing data.
"""
import time
import logging
from typing import Optional, Callable, Awaitable
from dataclasses import dataclass, field, asdict

logger = logging.getLogger("eagle.telemetry.spans")


@dataclass
class Span:
    """A single timed operation span."""
    name: str
    span_type: str  # "tool" | "agent"
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    duration_ms: Optional[int] = None
    input_data: Optional[dict] = None
    output_data: Optional[str] = None
    parent_id: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def end(self, output: Optional[str] = None, **meta):
        self.end_time = time.time()
        self.duration_ms = int((self.end_time - self.start_time) * 1000)
        if output:
            self.output_data = output[:2000]
        self.metadata.update(meta)

    def to_dict(self) -> dict:
        d = asdict(self)
        # Remove raw timestamps, keep duration
        d.pop("start_time", None)
        d.pop("end_time", None)
        return {k: v for k, v in d.items() if v is not None}


# Callback type for status emission
StatusCallback = Callable[..., Awaitable[None]]


class SpanTracker:
    """Tracks active spans from SDK hook events.

    Usage:
        tracker = SpanTracker(on_status=emit_status_callback)

        # Register hooks with SDK:
        options = ClaudeAgentOptions(
            hooks=tracker.get_hook_matchers(),
            ...
        )

        # After query, retrieve spans:
        spans = tracker.get_completed_spans()
    """

    def __init__(self, on_status: Optional[StatusCallback] = None):
        self.on_status = on_status
        self._active_spans: dict[str, Span] = {}
        self._completed_spans: list[Span] = []

    async def on_subagent_start(self, input, tool_use_id: str, ctx):
        """SDK SubagentStart hook callback."""
        agent_name = getattr(input, "agent_name", "unknown")

        span = Span(
            name=f"agent.{agent_name}",
            span_type="agent",
            input_data={"agent": agent_name},
        )
        self._active_spans[tool_use_id] = span

        if self.on_status:
            await self.on_status(
                agent_name=agent_name,
                message="Analyzing...",
                status="in_progress",
            )

        return {"continue_": True}

    async def on_subagent_stop(self, input, tool_use_id: str, ctx):
        """SDK SubagentStop hook callback."""
        span = self._active_spans.pop(tool_use_id, None)
        if not span:
            return {"continue_": True}

        result = getattr(input, "result", None)
        span.end(
            output=str(result)[:2000] if result else None,
            input_tokens=getattr(input, "input_tokens", 0),
            output_tokens=getattr(input, "output_tokens", 0),
        )
        self._completed_spans.append(span)

        agent_name = span.input_data.get("agent", "unknown") if span.input_data else "unknown"
        if self.on_status:
            await self.on_status(
                agent_name=agent_name,
                message=f"Complete ({span.duration_ms}ms)",
                status="complete",
            )

        return {"continue_": True}

    async def on_pre_tool_use(self, input, tool_use_id: str, ctx):
        """SDK PreToolUse hook callback."""
        tool_name = getattr(input, "tool_name", "unknown")
        tool_input = getattr(input, "tool_input", {})

        span = Span(
            name=f"tool.{tool_name}",
            span_type="tool",
            input_data=tool_input if isinstance(tool_input, dict) else {"raw": str(tool_input)[:500]},
        )
        self._active_spans[tool_use_id] = span

        if self.on_status:
            from .status_messages import get_tool_status_message
            message = get_tool_status_message(tool_name, tool_input)
            await self.on_status(
                agent_name=tool_name,
                message=message,
                status="in_progress",
            )

        return {"continue_": True, "decision": None, "hookSpecificOutput": None}

    async def on_post_tool_use(self, input, tool_use_id: str, ctx):
        """SDK PostToolUse hook callback."""
        span = self._active_spans.pop(tool_use_id, None)
        if not span:
            return {"continue_": True, "hookSpecificOutput": None}

        result = getattr(input, "tool_result", None)
        span.end(output=str(result)[:2000] if result else None)
        self._completed_spans.append(span)

        tool_name = span.name.replace("tool.", "")
        if self.on_status:
            await self.on_status(
                agent_name=tool_name,
                message=f"Complete ({span.duration_ms}ms)",
                status="complete",
            )

        return {"continue_": True, "hookSpecificOutput": None}

    def get_hook_matchers(self) -> dict:
        """Return hooks dict for ClaudeAgentOptions.hooks.

        Format: {HookEvent: [HookMatcher, ...]}
        """
        from claude_agent_sdk import HookMatcher

        return {
            "SubagentStart": [HookMatcher(matcher="SubagentStart", hooks=[self.on_subagent_start], timeout=5000)],
            "SubagentStop": [HookMatcher(matcher="SubagentStop", hooks=[self.on_subagent_stop], timeout=5000)],
            "PreToolUse": [HookMatcher(matcher="PreToolUse", hooks=[self.on_pre_tool_use], timeout=5000)],
            "PostToolUse": [HookMatcher(matcher="PostToolUse", hooks=[self.on_post_tool_use], timeout=5000)],
        }

    def get_completed_spans(self) -> list[dict]:
        """Return all completed spans as dicts."""
        return [s.to_dict() for s in self._completed_spans]
