"""
TraceCollector — SDK-native trace accumulation.

Processes all Claude Agent SDK message types, extracts telemetry,
and serializes to JSON for persistence and display.

Promoted from server/tests/test_eagle_sdk_eval.py TraceCollector class.
"""
import json
import time
import logging
from typing import Any, Optional

logger = logging.getLogger("eagle.telemetry")


class TraceCollector:
    """Collects and categorizes SDK message traces.

    Usage:
        collector = TraceCollector(tenant_id="acme", user_id="user-1")
        async for message in query(prompt="...", options=options):
            collector.process(message)

        # After query completes:
        summary = collector.summary()
        trace_json = collector.to_trace_json()
    """

    # Class-level: most recently created collector (used by eval harness auto-capture)
    _latest: "TraceCollector | None" = None

    def __init__(self, tenant_id: str = "default", user_id: str = "anonymous"):
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.trace_id = f"t-{int(time.time() * 1000)}"
        self.start_time = time.time()

        # Message accumulation
        self.messages: list[dict] = []
        self.text_blocks: list[str] = []
        self.thinking_blocks: list[str] = []
        self.tool_use_blocks: list[dict] = []
        self.result_messages: list[dict] = []
        self.system_messages: list = []

        # Telemetry counters
        self.session_id: Optional[str] = None
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        self.total_cost_usd: float = 0.0

        # Agent/tool tracking
        self.agents_delegated: list[str] = []
        self.tools_called: list[str] = []

        # Log lines for trace display
        self.log_lines: list[str] = []

        # Auto-register as latest (used by eval harness)
        TraceCollector._latest = self

    def _log(self, msg: str):
        """Print and capture a log line."""
        logger.debug(msg)
        self.log_lines.append(msg)

    def process(self, message, indent: int = 0):
        """Process a single SDK message, extracting telemetry data."""
        prefix = "  " * indent
        msg_type = type(message).__name__
        self.messages.append({"type": msg_type, "message": message})

        if msg_type == "SystemMessage":
            self._process_system(message, prefix)
        elif msg_type == "ResultMessage":
            self._process_result(message, prefix)
        else:
            self._process_content(message, msg_type, prefix)

    def _process_system(self, message, prefix: str = ""):
        """Extract session_id from SystemMessage."""
        if hasattr(message, "data") and isinstance(message.data, dict):
            sid = message.data.get("session_id")
            if sid:
                self.session_id = sid
                self._log(f"{prefix}[SystemMessage/init] session_id={sid}")
        self.system_messages.append(message)

    def _process_result(self, message, prefix: str = ""):
        """Extract usage, cost, and session_id from ResultMessage."""
        # Capture session_id from ResultMessage too
        if hasattr(message, "session_id") and message.session_id:
            self.session_id = message.session_id

        # Usage is a dict, not an object
        if hasattr(message, "usage") and message.usage is not None:
            usage = message.usage
            if isinstance(usage, dict):
                input_t = usage.get("input_tokens", 0) or 0
                output_t = usage.get("output_tokens", 0) or 0
                cache_create = usage.get("cache_creation_input_tokens", 0) or 0
                cache_read = usage.get("cache_read_input_tokens", 0) or 0
            else:
                input_t = getattr(usage, "input_tokens", 0) or 0
                output_t = getattr(usage, "output_tokens", 0) or 0
                cache_create = getattr(usage, "cache_creation_input_tokens", 0) or 0
                cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0

            # Total billed tokens include cache creation + direct
            total_in = input_t + cache_create + cache_read
            self.total_input_tokens += total_in
            self.total_output_tokens += output_t
            self.result_messages.append({
                "input_tokens": input_t,
                "output_tokens": output_t,
                "cache_creation_input_tokens": cache_create,
                "cache_read_input_tokens": cache_read,
                "total_input_effective": total_in,
            })
            self._log(
                f"{prefix}[ResultMessage/usage] "
                f"{input_t}+{cache_create}cache_create+{cache_read}cache_read in / {output_t} out"
            )

        # Total cost USD
        cost = getattr(message, "total_cost_usd", None)
        if cost is not None:
            self.total_cost_usd += cost
            self._log(f"{prefix}[ResultMessage/cost] ${cost:.6f}")

        # Result text
        if hasattr(message, "result") and message.result:
            text = message.result
            self._log(f"{prefix}[ResultMessage/result] {text[:300]}")

    def _process_content(self, message, msg_type: str, prefix: str = ""):
        """Process AssistantMessage/UserMessage content blocks."""
        if not hasattr(message, "content") or message.content is None:
            return

        for block in message.content:
            block_class = type(block).__name__

            if block_class == "TextBlock":
                text = getattr(block, "text", "")
                if text.strip():
                    self.text_blocks.append(text)
                    self._log(f"{prefix}[{msg_type}/TextBlock] {text[:200]}")

            elif block_class == "ThinkingBlock":
                thinking = getattr(block, "thinking", getattr(block, "text", ""))
                self.thinking_blocks.append(thinking)
                self._log(f"{prefix}[{msg_type}/ThinkingBlock] {thinking[:150]}...")

            elif block_class == "ToolUseBlock":
                name = getattr(block, "name", "?")
                tool_id = getattr(block, "id", "?")
                inp = getattr(block, "input", {})
                self.tool_use_blocks.append({"tool": name, "id": tool_id, "input": inp})

                if name == "Task":
                    subagent = inp.get("subagent_type", inp.get("description", "?"))
                    if subagent not in self.agents_delegated:
                        self.agents_delegated.append(subagent)
                    self._log(f"{prefix}[{msg_type}/ToolUseBlock] SUBAGENT -> {subagent}")
                else:
                    if name not in self.tools_called:
                        self.tools_called.append(name)
                    self._log(
                        f"{prefix}[{msg_type}/ToolUseBlock] {name}({json.dumps(inp)[:120]})"
                    )

            elif block_class == "ToolResultBlock":
                tool_id = getattr(block, "tool_use_id", "?")
                content = getattr(block, "content", "")
                content_preview = str(content)[:100] if content else ""
                self._log(
                    f"{prefix}[{msg_type}/ToolResultBlock] id={tool_id} {content_preview}"
                )

        # Track subagent context
        if hasattr(message, "parent_tool_use_id") and message.parent_tool_use_id:
            parent = message.parent_tool_use_id
            is_bedrock = parent.startswith("toolu_bdrk_")
            self._log(
                f"{prefix}(subagent context, parent={parent}, bedrock={is_bedrock})"
            )

    def summary(self) -> dict:
        """Return a summary dict suitable for DynamoDB or logging."""
        elapsed_ms = int((time.time() - self.start_time) * 1000)
        return {
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "total_messages": len(self.messages),
            "text_blocks": len(self.text_blocks),
            "thinking_blocks": len(self.thinking_blocks),
            "tool_use_blocks": len(self.tool_use_blocks),
            "result_messages": len(self.result_messages),
            "system_messages": len(self.system_messages),
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cost_usd": self.total_cost_usd,
            "duration_ms": elapsed_ms,
            "tools_called": self.tools_called,
            "agents_delegated": self.agents_delegated,
        }

    def to_trace_json(self) -> list:
        """Serialize the full conversation trace to a JSON-safe list."""
        trace = []
        for entry in self.messages:
            msg_type = entry["type"]
            message = entry["message"]
            item: dict[str, Any] = {"type": msg_type}

            if msg_type == "SystemMessage":
                if hasattr(message, "data") and isinstance(message.data, dict):
                    item["session_id"] = message.data.get("session_id")

            elif msg_type == "ResultMessage":
                item["result"] = getattr(message, "result", None)
                item["session_id"] = getattr(message, "session_id", None)
                cost = getattr(message, "total_cost_usd", None)
                if cost is not None:
                    item["cost_usd"] = cost
                usage = getattr(message, "usage", None)
                if usage is not None:
                    if isinstance(usage, dict):
                        item["usage"] = usage
                    else:
                        item["usage"] = {
                            "input_tokens": getattr(usage, "input_tokens", 0) or 0,
                            "output_tokens": getattr(usage, "output_tokens", 0) or 0,
                        }

            else:
                # AssistantMessage / UserMessage — serialize content blocks
                blocks = []
                if hasattr(message, "content") and message.content:
                    for block in message.content:
                        bc = type(block).__name__
                        if bc == "TextBlock":
                            blocks.append({
                                "type": "text",
                                "text": getattr(block, "text", ""),
                            })
                        elif bc == "ThinkingBlock":
                            blocks.append({
                                "type": "thinking",
                                "text": getattr(
                                    block, "thinking", getattr(block, "text", "")
                                ),
                            })
                        elif bc == "ToolUseBlock":
                            blocks.append({
                                "type": "tool_use",
                                "tool": getattr(block, "name", ""),
                                "id": getattr(block, "id", ""),
                                "input": getattr(block, "input", {}),
                            })
                        elif bc == "ToolResultBlock":
                            content = getattr(block, "content", "")
                            blocks.append({
                                "type": "tool_result",
                                "tool_use_id": getattr(block, "tool_use_id", ""),
                                "content": str(content)[:2000] if content else "",
                            })
                item["content"] = blocks

                # Preserve subagent context
                if hasattr(message, "parent_tool_use_id") and message.parent_tool_use_id:
                    item["parent_tool_use_id"] = message.parent_tool_use_id

            trace.append(item)
        return trace
