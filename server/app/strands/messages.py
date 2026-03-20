"""
EAGLE Strands Message Adapters

Adapter dataclasses that match the interface expected by streaming_routes.py and main.py:
  - type(msg).__name__ == "AssistantMessage" | "ResultMessage"
  - AssistantMessage.content[].type, .text, .name, .input
  - ResultMessage.result, .usage
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TextBlock:
    """Adapter for text content blocks."""

    type: str = "text"
    text: str = ""


@dataclass
class ToolUseBlock:
    """Adapter for tool_use content blocks."""

    type: str = "tool_use"
    name: str = ""
    input: dict = field(default_factory=dict)


@dataclass
class AssistantMessage:
    """Adapter for assistant messages with content blocks."""

    content: list = field(default_factory=list)


@dataclass
class ResultMessage:
    """Adapter for final result messages with usage stats."""

    result: Any = ""
    usage: dict = field(default_factory=dict)
