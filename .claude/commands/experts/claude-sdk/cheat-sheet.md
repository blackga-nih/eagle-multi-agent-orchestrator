---
description: "Quick-reference cheat sheet for Claude Agent SDK with copy-pasteable code samples"
allowed-tools: Read
---

# Claude Agent SDK Cheat Sheet

> Quick-reference for `claude-agent-sdk` with code samples from actual project usage.

---

## 1. Quick Start — Minimal query()

```python
from claude_agent_sdk import query, ClaudeAgentOptions

async def run():
    options = ClaudeAgentOptions(
        model="haiku",
        permission_mode="bypassPermissions",
        max_turns=3,
        max_budget_usd=0.10,
        env={
            "CLAUDE_CODE_USE_BEDROCK": "1",
            "AWS_REGION": "us-east-1",
        },
    )

    async for message in query(prompt="Hello!", options=options):
        msg_type = type(message).__name__
        print(f"{msg_type}: {message}")
```

---

## 2. ClaudeAgentOptions — Field Reference

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `model` | `str` | `"sonnet"` | Model: `"haiku"`, `"sonnet"`, `"opus"` |
| `system_prompt` | `str` | `None` | Tenant context injection point |
| `allowed_tools` | `list[str]` | `[]` | Tool allowlist (tier-gated) |
| `agents` | `dict[str, AgentDefinition]` | `{}` | Subagent registry |
| `mcp_servers` | `dict[str, MCPServer]` | `{}` | Custom tool servers |
| `hooks` | `list[HookMatcher]` | `[]` | Lifecycle callbacks |
| `permission_mode` | `str` | `"default"` | `"bypassPermissions"` for server-side |
| `max_turns` | `int` | `None` | Turn limit |
| `max_budget_usd` | `float` | `None` | Cost cap |
| `resume` | `str` | `None` | Session ID for multi-turn |
| `cwd` | `str` | `None` | Working directory for file tools |
| `env` | `dict[str, str]` | `{}` | Environment variables |

---

## 3. Session Resume — 5-Line Pattern

```python
# First query: capture session_id
session_id = None
async for msg in query(prompt="Hello!", options=options):
    if type(msg).__name__ == "SystemMessage":
        if hasattr(msg, "data") and isinstance(msg.data, dict):
            session_id = msg.data.get("session_id")
    if type(msg).__name__ == "ResultMessage":
        session_id = session_id or getattr(msg, "session_id", None)

# Resume: re-provide system_prompt (NOT preserved across resume)
resume_options = ClaudeAgentOptions(
    model="haiku",
    resume=session_id,
    system_prompt="You are an assistant for tenant 'acme-corp'.",  # MUST re-provide
    permission_mode="bypassPermissions",
    max_turns=3,
    max_budget_usd=0.10,
    env={"CLAUDE_CODE_USE_BEDROCK": "1", "AWS_REGION": "us-east-1"},
)
async for msg in query(prompt="Follow-up question", options=resume_options):
    pass  # conversation history restored
```

---

## 4. Subagents — AgentDefinition + Orchestrator

```python
from claude_agent_sdk import AgentDefinition

options = ClaudeAgentOptions(
    model="haiku",
    allowed_tools=["Read", "Glob", "Grep", "Task"],
    permission_mode="bypassPermissions",
    max_turns=10,
    max_budget_usd=0.25,
    agents={
        "file-counter": AgentDefinition(
            description="Counts files matching patterns. Use for file counting tasks.",
            prompt="You count files using Glob. Return the count and list files found.",
            tools=["Glob"],
            model="haiku",
        ),
        "code-summarizer": AgentDefinition(
            description="Reads and summarizes a single code file.",
            prompt="You read one code file and give a 2-3 sentence summary.",
            tools=["Read"],
            model="haiku",
        ),
    },
    env={"CLAUDE_CODE_USE_BEDROCK": "1", "AWS_REGION": "us-east-1"},
)

# Detect subagent messages via parent_tool_use_id
async for msg in query(prompt="Count .py files and summarize config.py", options=options):
    if hasattr(msg, "parent_tool_use_id") and msg.parent_tool_use_id:
        parent = msg.parent_tool_use_id
        is_bedrock = parent.startswith("toolu_bdrk_")
        print(f"  Subagent msg (parent={parent}, bedrock={is_bedrock})")
```

---

## 5. Custom Tools — @tool + MCP Server

```python
from dataclasses import dataclass
from claude_agent_sdk import tool, create_sdk_mcp_server

@dataclass
class ProductLookupInput:
    product_name: str

@tool("lookup_product", "Look up product details by name", ProductLookupInput)
async def lookup_product_tool(input: ProductLookupInput) -> dict:
    products = {
        "widget pro": {"id": "WP-001", "name": "Widget Pro", "price": 29.99},
    }
    result = products.get(input.product_name.lower(), {"error": "Not found"})
    return {"content": [{"type": "text", "text": json.dumps(result)}]}

# Create MCP server and register
mcp_server = create_sdk_mcp_server("inventory", tools=[lookup_product_tool])

options = ClaudeAgentOptions(
    model="haiku",
    allowed_tools=["mcp__inventory__lookup_product"],  # mcp__{server}__{tool}
    mcp_servers={"inventory": mcp_server},
    permission_mode="bypassPermissions",
    max_turns=5,
    max_budget_usd=0.10,
    env={"CLAUDE_CODE_USE_BEDROCK": "1", "AWS_REGION": "us-east-1"},
)
```

---

## 6. Hook Registration — PreToolUse / PostToolUse

```python
from claude_agent_sdk import (
    HookMatcher,
    PreToolUseHookInput,
    PostToolUseHookInput,
    StopHookInput,
    HookContext,
)

async def pre_tool_hook(input: PreToolUseHookInput, tool_use_id: str, ctx: HookContext):
    """Intercept tool calls before execution."""
    print(f"Pre-tool: {input.tool_name} (id: {tool_use_id})")
    return {
        "continue_": True,          # Python: continue_ (keyword workaround)
        "decision": None,           # or: {"permissionDecision": "allow"}
        "hookSpecificOutput": None, # or: {"updatedInput": {...}}
    }

async def post_tool_hook(input: PostToolUseHookInput, tool_use_id: str, ctx: HookContext):
    """Inspect tool results after execution."""
    print(f"Post-tool: {input.tool_name} result received")
    return {"continue_": True}

async def stop_hook(input: StopHookInput, tool_use_id: str, ctx: HookContext):
    """Control whether agent stops or continues."""
    return {"continue_": True, "decision": None}  # None = let agent decide

options = ClaudeAgentOptions(
    # ... other options ...
    hooks=[
        HookMatcher(matcher="PreToolUse", hooks=[pre_tool_hook], timeout=5000),
        HookMatcher(matcher="PostToolUse", hooks=[post_tool_hook], timeout=5000),
        HookMatcher(matcher="Stop", hooks=[stop_hook], timeout=5000),
    ],
)
```

---

## 7. Message Types — Type Discrimination

| Message Type | Key Fields | When Yielded |
|-------------|------------|--------------|
| `SystemMessage` | `data.session_id` | First message, session init |
| `AssistantMessage` | `content` (blocks) | Model responses |
| `UserMessage` | `content` (ToolResultBlock) | Tool results injected |
| `ResultMessage` | `usage`, `session_id`, `total_cost_usd`, `result` | Final message |

### Content Block Types (in AssistantMessage.content)

| Block Class | Key Fields | Description |
|-------------|------------|-------------|
| `TextBlock` | `text` | Model text output |
| `ThinkingBlock` | `thinking` or `text` | Extended thinking |
| `ToolUseBlock` | `name`, `id`, `input` | Tool call request |
| `ToolResultBlock` | `tool_use_id`, `content` | Tool execution result |

---

## 8. TraceCollector — Streaming Observer Pattern

```python
class TraceCollector:
    def __init__(self):
        self.messages, self.text_blocks, self.tool_use_blocks = [], [], []
        self.session_id = None
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cost_usd = 0.0

    def process(self, message):
        msg_type = type(message).__name__
        if msg_type == "SystemMessage":
            if hasattr(message, "data") and isinstance(message.data, dict):
                self.session_id = message.data.get("session_id")
        if hasattr(message, "content") and message.content:
            for block in message.content:
                block_class = type(block).__name__
                if block_class == "TextBlock":
                    self.text_blocks.append(block.text)
                elif block_class == "ToolUseBlock":
                    self.tool_use_blocks.append({"tool": block.name, "id": block.id})
        if msg_type == "ResultMessage":
            self.session_id = getattr(message, "session_id", self.session_id)
            if hasattr(message, "usage") and isinstance(message.usage, dict):
                self.total_input_tokens += message.usage.get("input_tokens", 0) or 0
                self.total_output_tokens += message.usage.get("output_tokens", 0) or 0
            self.total_cost_usd += getattr(message, "total_cost_usd", 0) or 0
```

---

## 9. Cost Tracking — ResultMessage.usage

```python
async for msg in query(prompt="...", options=options):
    if type(msg).__name__ == "ResultMessage":
        # usage is a dict (not an object)
        usage = msg.usage  # dict
        input_tokens = usage.get("input_tokens", 0) or 0
        output_tokens = usage.get("output_tokens", 0) or 0
        cache_create = usage.get("cache_creation_input_tokens", 0) or 0
        cache_read = usage.get("cache_read_input_tokens", 0) or 0

        # Direct cost attribute
        cost = msg.total_cost_usd  # float

        # Budget enforcement via options
        # max_budget_usd=0.25 in ClaudeAgentOptions
```

---

## 10. Environment Variables

| Variable | Value | Purpose |
|----------|-------|---------|
| `CLAUDE_CODE_USE_BEDROCK` | `"1"` | Route through AWS Bedrock |
| `AWS_REGION` | `"us-east-1"` | Bedrock region |
| `AWS_ACCESS_KEY_ID` | `"..."` | AWS credentials (or use IAM role) |
| `AWS_SECRET_ACCESS_KEY` | `"..."` | AWS credentials (or use IAM role) |

---

## 11. Common Patterns

### Multi-Tenant system_prompt Injection

```python
system_prompt = (
    f"You are an AI assistant for tenant '{tenant_id}'. "
    f"Subscription tier: {subscription_tier}. "
    f"Current user: {user_id}. "
    f"Always acknowledge the tenant and tier when greeting."
)
options = ClaudeAgentOptions(
    model="haiku",
    system_prompt=system_prompt,
    allowed_tools=TIER_TOOLS[subscription_tier],
    max_budget_usd=TIER_BUDGETS[subscription_tier],
    # ...
)
```

### EAGLE Production TIER_TOOLS (Bare Names for Subagents)

```python
# sdk_agentic_service.py — bare tool names passed to AgentDefinition.tools
TIER_TOOLS = {
    "basic":    [],
    "advanced": ["Read", "Glob", "Grep", "s3_document_ops", "create_document"],
    "premium":  ["Read", "Glob", "Grep", "Bash", "s3_document_ops",
                 "dynamodb_intake", "cloudwatch_logs", "create_document",
                 "get_intake_status", "intake_workflow", "search_far"],
}
TIER_BUDGETS = {"basic": 0.10, "advanced": 0.25, "premium": 0.75}
```

### EAGLE MCP Server — create_eagle_mcp_server()

```python
from app.eagle_tools_mcp import create_eagle_mcp_server

# Create the server scoped to a tenant and session
mcp_server = create_eagle_mcp_server(
    tenant_id="nci-oa",
    session_id="nci-oa-premium-u1-s1",
)

# Wire into sdk_query via mcp_servers (non-fatal pattern)
mcp_servers: dict = {}
try:
    mcp_servers = {"eagle-tools": create_eagle_mcp_server(
        tenant_id=tenant_id,
        session_id=session_id or f"{tenant_id}-{tier}-sdk",
    )}
except Exception as err:
    logger.warning("eagle_tools_mcp unavailable: %s", err)

options = ClaudeAgentOptions(
    # ...
    **({"mcp_servers": mcp_servers} if mcp_servers else {}),
    **({"resume": session_id} if session_id else {}),
)
```

### Bedrock Detection

```python
if parent_tool_use_id.startswith("toolu_bdrk_"):
    print("Running on Bedrock backend")
```

### ClaudeSDKClient — Multi-Query Session

```python
from claude_agent_sdk import ClaudeSDKClient

client = ClaudeSDKClient(options)
await client.connect()

# Query 1
await client.query("First question")
async for msg in client.receive_response():
    process(msg)

# Query 2 (same session, conversation continues)
await client.query("Follow-up question")
async for msg in client.receive_response():
    process(msg)

await client.disconnect()
```

### Windows MCP Cleanup Handling

```python
try:
    async for msg in query(prompt="...", options=options):
        collector.process(msg)
except ExceptionGroup as eg:
    real_errors = [e for e in eg.exceptions if "CLIConnection" not in type(e).__name__]
    if real_errors:
        raise ExceptionGroup("SDK errors", real_errors)
    # CLIConnection-only errors are expected MCP cleanup race on Windows
```

---

## 12. Links

- SDK package: `pip install claude-agent-sdk`
- Hook documentation: See `expertise.md` Part 7
- EAGLE MCP server: `server/app/eagle_tools_mcp.py` — 7 business tools
- Production SDK service: `server/app/sdk_agentic_service.py`
- Test examples: `server/tests/test_eagle_sdk_eval.py`, `server/tests/test_agent_sdk.py`
