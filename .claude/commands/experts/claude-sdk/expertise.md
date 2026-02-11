---
type: expert-file
file-type: expertise
domain: claude-sdk
last_updated: "2026-02-10"
sdk_version: "0.1.29+"
tags: [claude-agent-sdk, query, sessions, subagents, mcp, hooks, telemetry, cost, bedrock, multi-tenant, skill-handoff, agent-definition]
---

# Claude Agent SDK Expertise

> Complete mental model for `claude-agent-sdk` — the Python SDK powering the EAGLE agentic system.

---

## Part 1: SDK Overview & Installation

### Package

- **Name**: `claude-agent-sdk` (pip)
- **Minimum version**: 0.1.19 (hooks support), tested on 0.1.29
- **Install**: `pip install claude-agent-sdk`

### Key Modules

| Import | Purpose |
|--------|---------|
| `query` | One-shot async generator for agent execution |
| `ClaudeAgentOptions` | Configuration object for all query parameters |
| `AgentDefinition` | Subagent definition (description, prompt, tools, model) |
| `ClaudeSDKClient` | Lifecycle-controlled client (connect/query/disconnect) |
| `tool` | Decorator for custom tool functions |
| `create_sdk_mcp_server` | Factory to create MCP tool servers |
| `HookMatcher` | Hook registration matcher |
| `PreToolUseHookInput` | Hook input for pre-tool-use events |
| `PostToolUseHookInput` | Hook input for post-tool-use events |
| `StopHookInput` | Hook input for stop events |
| `SubagentStartHookInput` | Hook input for subagent start events |
| `SubagentStopHookInput` | Hook input for subagent stop events |
| `HookContext` | Context object passed to hook callbacks |

### Standard Import Block

```python
from claude_agent_sdk import (
    query,
    ClaudeAgentOptions,
    AgentDefinition,
    ClaudeSDKClient,
    tool,
    create_sdk_mcp_server,
    HookMatcher,
    PreToolUseHookInput,
    PostToolUseHookInput,
    StopHookInput,
    SubagentStartHookInput,
    SubagentStopHookInput,
    HookContext,
)
```

### Backend

- **Bedrock**: Set `CLAUDE_CODE_USE_BEDROCK=1` and `AWS_REGION=us-east-1` in `env`
- **Direct Anthropic**: Omit Bedrock env vars, use `ANTHROPIC_API_KEY`
- **Detection**: Bedrock tool IDs have `toolu_bdrk_` prefix

---

## Part 2: query() API

### Signature

```python
async for message in query(prompt: str, options: ClaudeAgentOptions):
    # message is one of: SystemMessage, AssistantMessage, UserMessage, ResultMessage
    pass
```

### Behavior

- **Async generator** yielding message objects as they arrive
- First message is always `SystemMessage` with `session_id`
- Intermediate messages are `AssistantMessage` (model output) and `UserMessage` (tool results)
- Final message is `ResultMessage` with usage stats and cost
- Automatically handles tool execution loops up to `max_turns`
- Respects `max_budget_usd` for cost control

### Code Sample (from test_eagle_sdk_eval.py:297-320)

```python
options = ClaudeAgentOptions(
    model=MODEL,
    system_prompt=system_prompt,
    allowed_tools=TIER_TOOLS[subscription_tier],
    permission_mode="bypassPermissions",
    max_turns=3,
    max_budget_usd=TIER_BUDGETS[subscription_tier],
    cwd=os.path.dirname(os.path.abspath(__file__)),
    env={
        "CLAUDE_CODE_USE_BEDROCK": "1",
        "AWS_REGION": "us-east-1",
    },
)

collector = TraceCollector()
async for message in query(
    prompt="Hello! What tenant am I from and what is my subscription tier?",
    options=options,
):
    collector.process(message, indent=2)
```

---

## Part 3: ClaudeAgentOptions (Full Field Reference)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `model` | `str` | `"sonnet"` | Model tier: `"haiku"`, `"sonnet"`, `"opus"` |
| `system_prompt` | `str` | `None` | System prompt for agent behavior + tenant context |
| `allowed_tools` | `list[str]` | `[]` | Allowlist of tool names agent can use |
| `agents` | `dict[str, AgentDefinition]` | `{}` | Named subagent definitions |
| `mcp_servers` | `dict[str, MCPServer]` | `{}` | MCP tool server instances |
| `hooks` | `list[HookMatcher]` | `[]` | Lifecycle hook matchers |
| `permission_mode` | `str` | `"default"` | `"bypassPermissions"` for server-side usage |
| `max_turns` | `int` | `None` | Max tool-use loop iterations |
| `max_budget_usd` | `float` | `None` | Cost cap in USD |
| `resume` | `str` | `None` | Session ID to resume (multi-turn) |
| `cwd` | `str` | `None` | Working directory for file-based tools |
| `env` | `dict[str, str]` | `{}` | Environment variables for the agent process |

### Multi-Tenant Configuration Pattern

```python
options = ClaudeAgentOptions(
    model="haiku",
    system_prompt=f"You are an assistant for tenant '{tenant_id}'. Tier: {tier}.",
    allowed_tools=TIER_TOOLS[tier],
    permission_mode="bypassPermissions",
    max_turns=5,
    max_budget_usd=TIER_BUDGETS[tier],
    cwd=working_dir,
    env={"CLAUDE_CODE_USE_BEDROCK": "1", "AWS_REGION": "us-east-1"},
)
```

---

## Part 4: Session Management

### Session Creation

Sessions are created automatically on first `query()` call. The `session_id` is available from:

1. **SystemMessage** (first message): `message.data.get("session_id")`
2. **ResultMessage** (last message): `message.session_id`

```python
session_id = None
async for msg in query(prompt="...", options=options):
    msg_type = type(msg).__name__
    if msg_type == "SystemMessage":
        if hasattr(msg, "data") and isinstance(msg.data, dict):
            session_id = msg.data.get("session_id")
    if msg_type == "ResultMessage":
        session_id = session_id or getattr(msg, "session_id", None)
```

### Session Resume

Resume a session by passing `session_id` in options:

```python
resume_options = ClaudeAgentOptions(
    model="haiku",
    resume=session_id,  # <-- restore conversation history
    system_prompt=system_prompt,  # MUST re-provide (not preserved)
    allowed_tools=["Read", "Glob"],
    permission_mode="bypassPermissions",
    max_turns=3,
    max_budget_usd=0.10,
    env={"CLAUDE_CODE_USE_BEDROCK": "1", "AWS_REGION": "us-east-1"},
)
async for msg in query(prompt="Follow-up question", options=resume_options):
    collector.process(msg)
```

### Critical: system_prompt NOT Preserved

**KEY DISCOVERY**: `resume` restores conversation history but **NOT** `system_prompt`. The system prompt must be provided on every `query()` call. This is actually correct for multi-tenant because tenant context should always be explicitly set.

### DynamoDB Session Store Pattern

The EAGLE system stores sessions in DynamoDB:
- **Table**: `eagle`
- **PK**: `SESSION#{session_id}`
- **SK**: `META`
- **Attributes**: `tenant_id`, `user_id`, `created_at`, `last_active`, `message_count`, `total_cost_usd`

See `server/app/session_store.py` for create/resume implementation.

---

## Part 5: Subagent Orchestration

### AgentDefinition

```python
from claude_agent_sdk import AgentDefinition

agents = {
    "file-counter": AgentDefinition(
        description="Counts files matching patterns. Use for file counting tasks.",
        prompt="You count files using Glob. Return the count and list files found. Be concise.",
        tools=["Glob"],
        model="haiku",
    ),
    "code-summarizer": AgentDefinition(
        description="Reads and summarizes a single code file.",
        prompt="You read one code file and give a 2-3 sentence summary.",
        tools=["Read"],
        model="haiku",
    ),
}
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `description` | `str` | When the orchestrator should use this agent |
| `prompt` | `str` | Behavior instructions for the subagent |
| `tools` | `list[str]` | Tools the subagent can use (scoped) |
| `model` | `str` | Model for subagent (can differ from parent) |

### Registration

Subagents are registered in `ClaudeAgentOptions.agents` dict. The orchestrator (parent agent) calls them via the `Task` tool, which must be in `allowed_tools`.

```python
options = ClaudeAgentOptions(
    model="haiku",
    allowed_tools=["Read", "Glob", "Grep", "Task"],  # Task required for subagents
    agents=agents,
    # ...
)
```

### parent_tool_use_id Tracking

Messages from within a subagent have `parent_tool_use_id` set to the Task tool call ID:

```python
if hasattr(message, "parent_tool_use_id") and message.parent_tool_use_id:
    parent = message.parent_tool_use_id
    is_bedrock = parent.startswith("toolu_bdrk_")
    print(f"Subagent message, parent={parent}, bedrock={is_bedrock}")
```

### Bedrock Detection

On Bedrock backend, tool IDs have prefix `toolu_bdrk_`. This is how you confirm the backend:

```python
is_bedrock = tool_use_id.startswith("toolu_bdrk_")
```

### Skill → Subagent Pattern (Separate Context Windows)

**KEY PATTERN**: Convert skill markdown files into `AgentDefinition` subagents so each skill runs in its own fresh context window, not injected into the supervisor's shared context.

**Two approaches compared:**

| Approach | Context | Use Case |
|----------|---------|----------|
| Shared context (skill injection) | Skill content appended to `system_prompt` | Simple, single-skill queries |
| Separate context (AgentDefinition) | Each skill gets own context window via `AgentDefinition.prompt` | Multi-skill orchestration, complex workflows |

**Implementation (from `server/app/sdk_agentic_service.py`):**

```python
from eagle_skill_constants import SKILL_CONSTANTS

# Step 1: Load skill content from single source of truth
intake_content = SKILL_CONSTANTS["oa-intake"]
legal_content = SKILL_CONSTANTS["02-legal.txt"]
market_content = SKILL_CONSTANTS["04-market.txt"]

# Step 2: Convert skills to AgentDefinitions
agents = {
    "oa-intake": AgentDefinition(
        description="Gathers acquisition requirements and determines type/threshold.",
        prompt=intake_content[:4000],  # Truncate to fit context budget
        tools=[],                       # Subagent tools (can be tier-gated)
        model="haiku",                  # Can use different model than supervisor
    ),
    "legal-counsel": AgentDefinition(
        description="Assesses legal risks, protest vulnerabilities, FAR compliance.",
        prompt=legal_content,
        tools=[],
        model="haiku",
    ),
    "market-intelligence": AgentDefinition(
        description="Researches market conditions, vendors, and pricing.",
        prompt=market_content,
        tools=[],
        model="haiku",
    ),
}

# Step 3: Supervisor only has Task tool — delegates to subagents
options = ClaudeAgentOptions(
    model="haiku",
    system_prompt="You are the EAGLE Supervisor. Delegate to subagents via Task tool.",
    allowed_tools=["Task"],  # ONLY Task — forces delegation
    agents=agents,
    permission_mode="bypassPermissions",
    max_turns=15,
    max_budget_usd=0.50,
    env={"CLAUDE_CODE_USE_BEDROCK": "1", "AWS_REGION": "us-east-1"},
)

# Step 4: Each subagent runs in its OWN context window
async for message in query(prompt="Assess this $500K IT acquisition", options=options):
    process(message)
```

**Key design decisions:**

1. **Supervisor has `allowed_tools=["Task"]` only** — forces delegation, prevents direct answers
2. **Skill content becomes `AgentDefinition.prompt`** — not injected into supervisor's system prompt
3. **Truncate long skills** — use `content[:4000]` to fit subagent context budget
4. **Tier-gate subagent tools** — map subscription tiers to tool lists per subagent
5. **Dual-mode support** — `sdk_query()` for supervisor+subagents, `sdk_query_single_skill()` for shared-context

**Verified in test_15_supervisor_multi_skill_chain** — supervisor delegates to 3 skill subagents (intake, market, legal) in sequence, each with separate context.

---

## Part 6: Custom Tools & MCP

### @tool Decorator

Define custom tools with the `@tool` decorator:

```python
from dataclasses import dataclass
from claude_agent_sdk import tool

@dataclass
class ProductLookupInput:
    product_name: str

@tool("lookup_product", "Look up product details by name", ProductLookupInput)
async def lookup_product_tool(input: ProductLookupInput) -> dict:
    products = {
        "widget pro": {"id": "WP-001", "name": "Widget Pro", "price": 29.99, "stock": 150},
    }
    key = input.product_name.lower()
    result = products.get(key, {"error": f"Product '{input.product_name}' not found"})
    return {"content": [{"type": "text", "text": json.dumps(result)}]}
```

### Decorator Signature

```python
@tool(name: str, description: str, InputDataclass: type)
async def tool_fn(input: InputDataclass) -> dict:
    return {"content": [{"type": "text", "text": "..."}]}
```

### Input: @dataclass with typed fields

- Use `@dataclass` for tool input schema
- Fields become the tool's input parameters
- Types: `str`, `int`, `float`, `bool`, `list`, `dict`

### Return Format

Tools must return MCP-compatible content:

```python
return {"content": [{"type": "text", "text": json.dumps(result)}]}
```

### create_sdk_mcp_server()

Bundle tools into an MCP server:

```python
from claude_agent_sdk import create_sdk_mcp_server

mcp_server = create_sdk_mcp_server(
    "inventory-tools",
    tools=[lookup_product_tool, calculate_total_tool],
)
```

### Tool Naming Convention

MCP tools follow the pattern: `mcp__{server_name}__{tool_name}`

```python
options = ClaudeAgentOptions(
    allowed_tools=[
        "mcp__inventory-tools__lookup_product",
        "mcp__inventory-tools__calculate_total",
    ],
    mcp_servers={"inventory-tools": mcp_server},
    # ...
)
```

### Complete Custom Tool Registration

```python
# 1. Define input dataclass
@dataclass
class MyInput:
    query: str

# 2. Define tool function
@tool("my_tool", "Does something useful", MyInput)
async def my_tool_fn(input: MyInput) -> dict:
    return {"content": [{"type": "text", "text": f"Result for: {input.query}"}]}

# 3. Create MCP server
server = create_sdk_mcp_server("my-server", tools=[my_tool_fn])

# 4. Register in options
options = ClaudeAgentOptions(
    allowed_tools=["mcp__my-server__my_tool"],
    mcp_servers={"my-server": server},
    # ...
)
```

---

## Part 7: Hook System

### HookEvent Types

| Event | When Fired | Use Case |
|-------|-----------|----------|
| `PreToolUse` | Before tool execution | Intercept/modify/deny tool calls |
| `PostToolUse` | After tool execution | Inspect results, add context |
| `UserPromptSubmit` | When user prompt received | Input validation |
| `Stop` | When agent decides to stop | Override stop decision |
| `SubagentStart` | When subagent begins | Track subagent lifecycle |
| `SubagentStop` | When subagent finishes | Post-process subagent results |
| `PreCompact` | Before context compaction | Pre-compaction actions |

### HookMatcher

```python
from claude_agent_sdk import HookMatcher

hooks = [
    HookMatcher(
        matcher="PreToolUse",     # Event type string
        hooks=[pre_tool_callback],  # List of async callbacks
        timeout=5000,              # Timeout in ms
    ),
]
```

### Callback Signature

```python
async def hook_callback(
    input: HookInputType,   # e.g., PreToolUseHookInput
    tool_use_id: str,       # The tool use ID being processed
    context: HookContext,   # Session context
) -> dict:
    return {
        "continue_": True,           # Python keyword workaround (continue -> continue_)
        "decision": None,            # Hook-specific decision
        "hookSpecificOutput": None,  # Hook-specific output
    }
```

### PreToolUse Hook

Intercept tool calls before execution:

```python
async def pre_tool_hook(input: PreToolUseHookInput, tool_use_id: str, ctx: HookContext):
    print(f"Tool: {input.tool_name}, ID: {tool_use_id}")

    # Allow the tool call
    return {"continue_": True, "decision": None, "hookSpecificOutput": None}

    # OR deny it
    return {
        "continue_": True,
        "decision": {"permissionDecision": "deny"},
        "hookSpecificOutput": None,
    }

    # OR modify the input
    return {
        "continue_": True,
        "decision": {"permissionDecision": "allow"},
        "hookSpecificOutput": {"updatedInput": {"modified_field": "new_value"}},
    }
```

### PostToolUse Hook

Inspect and augment tool results:

```python
async def post_tool_hook(input: PostToolUseHookInput, tool_use_id: str, ctx: HookContext):
    print(f"Tool result for: {input.tool_name}")
    return {
        "continue_": True,
        "hookSpecificOutput": {"additionalContext": "Extra info for the model"},
    }
```

### Stop Hook

Control agent termination:

```python
async def stop_hook(input: StopHookInput, tool_use_id: str, ctx: HookContext):
    # Let agent decide (default)
    return {"continue_": True, "decision": None}

    # OR force continue
    return {"continue_": True, "decision": "continue"}

    # OR force stop
    return {"continue_": True, "decision": "stop"}
```

### Python Keyword Handling

The SDK uses Python-safe field names:
- `continue_` maps to JSON `continue` (Python keyword)
- `async_` maps to JSON `async` (Python keyword)

### Hook Registration

```python
options = ClaudeAgentOptions(
    hooks=[
        HookMatcher(matcher="PreToolUse", hooks=[pre_tool_hook], timeout=5000),
        HookMatcher(matcher="PostToolUse", hooks=[post_tool_hook], timeout=5000),
        HookMatcher(matcher="Stop", hooks=[stop_hook], timeout=5000),
    ],
    # ...
)
```

### BaseHookInput Fields

All hook inputs share base fields:
- `session_id`: Current session ID
- `transcript_path`: Path to conversation transcript
- `cwd`: Working directory

---

## Part 8: Message Types & Telemetry

### SystemMessage

First message yielded by `query()`. Contains session initialization data.

```python
if msg_type == "SystemMessage":
    if hasattr(message, "data") and isinstance(message.data, dict):
        session_id = message.data.get("session_id")
```

### AssistantMessage

Model output. Contains `content` array with mixed block types:

| Block Class | Key Fields | Description |
|-------------|------------|-------------|
| `TextBlock` | `text` | Model text response |
| `ThinkingBlock` | `thinking` or `text` | Extended thinking (if enabled) |
| `ToolUseBlock` | `name`, `id`, `input` | Tool call request |

```python
for block in message.content:
    block_class = type(block).__name__
    if block_class == "TextBlock":
        print(block.text)
    elif block_class == "ThinkingBlock":
        thinking = getattr(block, "thinking", getattr(block, "text", ""))
    elif block_class == "ToolUseBlock":
        print(f"Tool: {block.name}, ID: {block.id}, Input: {block.input}")
```

### UserMessage

Injected after tool execution. Contains `ToolResultBlock`:

```python
# ToolResultBlock fields:
# - tool_use_id: str (matches ToolUseBlock.id)
# - content: str or list (tool output)
```

### ResultMessage

Final message with usage stats:

```python
if msg_type == "ResultMessage":
    # Session ID
    session_id = message.session_id

    # Usage dict
    usage = message.usage  # dict, not object
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    cache_create = usage.get("cache_creation_input_tokens", 0)
    cache_read = usage.get("cache_read_input_tokens", 0)

    # Cost
    cost = message.total_cost_usd  # float

    # Result text (final model output)
    text = message.result  # str
```

### TraceCollector Pattern

The project uses a `TraceCollector` class (see `test_eagle_sdk_eval.py:138-272`) to:
1. Categorize all message types
2. Extract session_id from both SystemMessage and ResultMessage
3. Accumulate token usage across multiple ResultMessages
4. Track tool_use_blocks for frontend rendering
5. Detect subagent context via parent_tool_use_id

---

## Part 9: Cost & Usage Tracking

### ResultMessage.usage Dict

```python
usage = message.usage  # dict (not an object)
{
    "input_tokens": 1234,           # Direct input tokens
    "output_tokens": 567,           # Output tokens
    "cache_creation_input_tokens": 0, # Cache creation tokens
    "cache_read_input_tokens": 890,   # Cache read tokens (cheaper)
}
```

### Total Billed Input Tokens

```python
total_input = (
    usage.get("input_tokens", 0)
    + usage.get("cache_creation_input_tokens", 0)
    + usage.get("cache_read_input_tokens", 0)
)
```

### ResultMessage.total_cost_usd

Direct cost attribute on ResultMessage:

```python
cost = message.total_cost_usd  # float, e.g., 0.001234
```

### Budget Enforcement

Set `max_budget_usd` in ClaudeAgentOptions to cap spending:

```python
options = ClaudeAgentOptions(
    max_budget_usd=0.25,  # Hard cap at $0.25
    # ...
)
```

### Accumulation Across Queries

When running multiple queries (e.g., session resume), accumulate costs:

```python
total_cost = 0.0
total_input = 0
total_output = 0

async for msg in query(prompt="...", options=options):
    if type(msg).__name__ == "ResultMessage":
        usage = msg.usage or {}
        total_input += (usage.get("input_tokens", 0) or 0)
        total_output += (usage.get("output_tokens", 0) or 0)
        total_cost += (msg.total_cost_usd or 0)
```

### Pricing

Configurable via environment or constants:
- `COST_INPUT_PER_1K`: Input token pricing per 1K tokens
- `COST_OUTPUT_PER_1K`: Output token pricing per 1K tokens
- See `server/app/admin_service.py` for the EAGLE cost calculation logic

---

## Part 10: ClaudeSDKClient (Lifecycle Control)

### Overview

`ClaudeSDKClient` provides fine-grained lifecycle control vs. one-shot `query()`:

```python
from claude_agent_sdk import ClaudeSDKClient

client = ClaudeSDKClient(options)
```

### Lifecycle

```python
# 1. Connect
await client.connect()

# 2. Query (can call multiple times, same session)
await client.query("First question")
async for msg in client.receive_response():
    process(msg)

# 3. Follow-up query (conversation continues)
await client.query("Follow-up question")
async for msg in client.receive_response():
    process(msg)

# 4. Disconnect
await client.disconnect()
```

### Key Difference from query()

| Feature | `query()` | `ClaudeSDKClient` |
|---------|-----------|-------------------|
| Session | New per call (unless `resume`) | Maintained across queries |
| Lifecycle | Automatic | Manual (connect/disconnect) |
| Multi-query | Requires session resume | Built-in, same client |
| Use case | One-shot or resume | Long-running conversations |

### Code Sample (from test_agent_sdk.py:313-381)

```python
options = ClaudeAgentOptions(
    model="haiku",
    allowed_tools=["Read", "Glob"],
    permission_mode="bypassPermissions",
    max_turns=3,
    max_budget_usd=0.05,
    cwd=os.path.dirname(os.path.abspath(__file__)),
    env={"CLAUDE_CODE_USE_BEDROCK": "1", "AWS_REGION": "us-east-1"},
)

client = ClaudeSDKClient(options)
try:
    await client.connect()

    # Query 1
    await client.query("Read config.py and tell me the port. Be concise.")
    async for msg in client.receive_response():
        log_message(msg)

    # Query 2 (same session)
    await client.query("What model ID does bedrock_service.py use?")
    async for msg in client.receive_response():
        log_message(msg)

finally:
    await client.disconnect()
```

---

## Learnings

### patterns_that_work

- **TraceCollector pattern**: Process all message types in a single class, categorize by `type(msg).__name__`, accumulate usage stats. Proven in test_eagle_sdk_eval.py across 27 tests. (discovered: 2026-02-10)
- **Tier-gated tools**: Map subscription tiers to `allowed_tools` lists. Simple dict lookup, no runtime overhead. (discovered: 2026-02-10)
- **system_prompt injection**: Embed tenant_id, user_id, and tier directly in system_prompt. Agent always has context. (discovered: 2026-02-10)
- **Bedrock detection via toolu_bdrk_ prefix**: Reliable way to confirm backend without config inspection. (discovered: 2026-02-10)
- **max_budget_usd for cost control**: Always set this. Prevents runaway costs during development. (discovered: 2026-02-10)
- **haiku for testing**: Use haiku model for all eval/test runs. Cost-effective, fast, sufficient for validation. (discovered: 2026-02-10)
- **Skill→Subagent via AgentDefinition**: Load skill markdown from SKILL_CONSTANTS, pass as `AgentDefinition.prompt`, register in `ClaudeAgentOptions.agents`. Each skill gets own context window. Supervisor delegates via `Task` tool with `allowed_tools=["Task"]`. See `sdk_agentic_service.py`. (discovered: 2026-02-10)
- **Dual-mode skill invocation**: `sdk_query()` for multi-skill orchestration (supervisor + subagents), `sdk_query_single_skill()` for focused single-skill queries (shared context injection). Choose based on query complexity. (discovered: 2026-02-10)
- **Truncate long skill prompts**: Cap subagent prompts at ~4000 chars to avoid context overflow. Use `content[:4000]` + truncation marker. (discovered: 2026-02-10)

### patterns_to_avoid

- **Assuming system_prompt survives resume**: It does NOT. Always re-provide on every query. (reason: SDK design — stateless system prompt)
- **Forgetting Task in allowed_tools for subagents**: Subagents are called via Task tool. Without it in allowed_tools, orchestrator cannot dispatch. (reason: silent failure)
- **Using object attribute access on usage**: `ResultMessage.usage` is a `dict`, not an object. Use `.get()` not `.attribute`. (reason: AttributeError at runtime)
- **Ignoring ExceptionGroup on Windows**: MCP server cleanup can race on Windows. Wrap with ExceptionGroup handler. (reason: CLIConnection error on test teardown)
- **Hardcoding session_id extraction to only SystemMessage**: Also available on `ResultMessage.session_id`. Check both for reliability. (reason: not all SDK versions emit in same order)
- **Confusing skill injection with subagent delegation**: Injecting skill content into `system_prompt` = shared context window (prompt switching). Using `AgentDefinition` with skill as `prompt` = separate context windows (true subagent delegation). They look similar but have very different context isolation properties. (reason: architectural confusion leads to wrong pattern choice)
- **Passing full skill content to AgentDefinition without truncation**: Long skill markdown can overflow subagent context. Always truncate with `content[:4000]`. (reason: context budget exceeded silently)

### common_issues

- **MCP server cleanup race on Windows**: `ExceptionGroup` with `CLIConnection` errors during teardown. Solution: catch `ExceptionGroup`, filter `CLIConnection` errors, re-raise others. (component: custom-tools)
- **usage dict values can be None**: Always use `or 0` when extracting: `usage.get("input_tokens", 0) or 0`. (component: cost-tracking)
- **Block type detection**: Use `type(block).__name__` not `block.type`. SDK blocks are Python classes, not dicts. (component: telemetry)
- **ThinkingBlock field name**: Can be `thinking` or `text` depending on SDK version. Use `getattr(block, "thinking", getattr(block, "text", ""))`. (component: telemetry)

### tips

- Use `permission_mode="bypassPermissions"` for all server-side SDK usage (no human in the loop)
- Set `cwd` to the directory containing files the agent should access
- The `env` dict in ClaudeAgentOptions sets environment variables for the agent subprocess
- Subagent `description` field is what the orchestrator uses to decide when to call it — make it specific
- MCP tool names must exactly match in both `allowed_tools` and the server's tool registry
- `ResultMessage.result` contains the final text output (useful for extracting the answer)
- Multiple `ResultMessage` instances can be yielded if the agent does multiple tool loops — accumulate, don't overwrite
- Two entry points for SDK-based agent: `sdk_query()` (supervisor + subagents) vs `sdk_query_single_skill()` (shared context). Use subagents for multi-skill workflows, shared context for simple focused queries
- Supervisor `allowed_tools=["Task"]` (only Task) forces delegation — prevents the supervisor from answering directly
- `AgentDefinition.description` drives the supervisor's routing decision — make descriptions specific about WHEN to use each subagent
- `build_skill_agents()` in `sdk_agentic_service.py` converts all skill constants to AgentDefinitions in one call
- Production module: `server/app/sdk_agentic_service.py` — SDK-based service with skill→subagent orchestration
