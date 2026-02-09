"""
Stream Protocol for Multi-Tenant Agent Core Application

Ported from eagle-intake-app/server/shared/stream_protocol.py and adapted
for the multi-tenant architecture. Provides structured SSE (Server-Sent Events)
streaming with agent identification, supporting multi-agent orchestration
scenarios including handoffs, tool use, and reasoning transparency.
"""
import json
from datetime import datetime, timezone
from typing import Optional, Any, Dict
from dataclasses import dataclass, asdict
from enum import Enum


class StreamEventType(str, Enum):
    TEXT = "text"
    REASONING = "reasoning"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    ELICITATION = "elicitation"
    METADATA = "metadata"
    COMPLETE = "complete"
    ERROR = "error"
    HANDOFF = "handoff"


@dataclass
class StreamEvent:
    """A single stream event emitted by an agent during processing.

    Each event is tagged with the originating agent_id and agent_name so that
    downstream consumers (e.g. a frontend multiplexing several agent streams)
    can attribute content to the correct source.
    """

    type: StreamEventType
    agent_id: str
    agent_name: str
    content: Optional[str] = None
    reasoning: Optional[str] = None
    tool_use: Optional[Dict[str, Any]] = None
    tool_result: Optional[Dict[str, Any]] = None
    elicitation: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    timestamp: Optional[str] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        """Convert to a dictionary, omitting None-valued fields."""
        data = asdict(self)
        data = {k: v for k, v in data.items() if v is not None}
        data["type"] = self.type.value
        return data

    def to_json(self) -> str:
        """Serialize to a JSON string."""
        return json.dumps(self.to_dict())

    def to_sse(self) -> str:
        """Format as a Server-Sent Events data line."""
        return f"data: {self.to_json()}\n\n"


class MultiAgentStreamWriter:
    """Helper for writing typed stream events into an asyncio queue.

    Instantiate one writer per agent so that every event is automatically
    tagged with the correct agent_id and agent_name.  All write methods
    accept an asyncio.Queue (or any object with an async ``put`` method)
    and push SSE-formatted strings into it.
    """

    def __init__(self, agent_id: str, agent_name: str):
        self.agent_id = agent_id
        self.agent_name = agent_name

    def _create_event(self, event_type: StreamEventType, **kwargs) -> StreamEvent:
        """Create a StreamEvent pre-filled with this writer's agent identity."""
        return StreamEvent(
            type=event_type,
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            **kwargs,
        )

    async def write_text(self, queue, content: str):
        """Emit a TEXT event containing assistant-generated content."""
        event = self._create_event(StreamEventType.TEXT, content=content)
        await queue.put(event.to_sse())

    async def write_reasoning(self, queue, reasoning: str):
        """Emit a REASONING event exposing the agent's chain-of-thought."""
        event = self._create_event(StreamEventType.REASONING, reasoning=reasoning)
        await queue.put(event.to_sse())

    async def write_tool_use(self, queue, tool_name: str, tool_input: Dict[str, Any]):
        """Emit a TOOL_USE event when the agent invokes a tool."""
        event = self._create_event(
            StreamEventType.TOOL_USE,
            tool_use={"name": tool_name, "input": tool_input},
        )
        await queue.put(event.to_sse())

    async def write_tool_result(self, queue, tool_name: str, result: Any):
        """Emit a TOOL_RESULT event with the output of a tool invocation."""
        event = self._create_event(
            StreamEventType.TOOL_RESULT,
            tool_result={"name": tool_name, "result": result},
        )
        await queue.put(event.to_sse())

    async def write_handoff(self, queue, target_agent_id: str, reason: str):
        """Emit a HANDOFF event signalling transfer to another agent."""
        event = self._create_event(
            StreamEventType.HANDOFF,
            metadata={"target_agent": target_agent_id, "reason": reason},
        )
        await queue.put(event.to_sse())

    async def write_complete(self, queue):
        """Emit a COMPLETE event indicating the agent has finished."""
        event = self._create_event(StreamEventType.COMPLETE)
        await queue.put(event.to_sse())

    async def write_error(self, queue, error_message: str):
        """Emit an ERROR event with a human-readable error description."""
        event = self._create_event(StreamEventType.ERROR, content=error_message)
        await queue.put(event.to_sse())
