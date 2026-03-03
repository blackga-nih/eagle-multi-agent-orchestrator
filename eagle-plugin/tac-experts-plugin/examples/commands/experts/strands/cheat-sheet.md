---
description: "Quick-reference cheat sheet for Strands Agents SDK with copy-pasteable code samples"
allowed-tools: Read
---

# Strands Agents SDK Cheat Sheet

> Quick-reference for `strands-agents` with code samples for EAGLE migration and new development.

---

## 1. Quick Start — Minimal Agent

```python
from strands import Agent
from strands.models import BedrockModel

model = BedrockModel(
    model_id="us.anthropic.claude-haiku-4-20250514-v1:0",
    region_name="us-east-1",
)

agent = Agent(
    model=model,
    system_prompt="You are a helpful assistant. Be concise.",
    callback_handler=None,  # suppress stdout for server-side
)

result = agent("What is 2 + 2?")
print(result)  # "4"
```

---

## 2. Agent() — Constructor Reference

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | `Model` | required | BedrockModel, AnthropicModel, etc. |
| `system_prompt` | `str` | `None` | Agent behavior instructions |
| `tools` | `list` | `[]` | List of `@tool`-decorated functions |
| `callback_handler` | `CallbackHandler` | `PrintHandler` | Streaming handler (`None` = silent) |
| `conversation_manager` | `ConversationManager` | `SlidingWindow` | Context window management |
| `session_manager` | `SessionManager` | `None` | Persistence (File, S3, custom) |
| `session_id` | `str` | `None` | Explicit session ID |
| `max_parallel_tools` | `int` | `1` | Concurrent tool execution |
| `load_tools_from_directory` | `str` | `None` | Hot-reload tools from dir |

---

## 3. Shared Model — Module-Level Pattern (Recommended)

```python
# Module-level: create ONCE, reuse everywhere
# Saves ~50-200ms per request (boto3 client creation)
_model = BedrockModel(
    model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
    region_name="us-east-1",
)

# Per-request: new Agent, shared model
def handle_request(prompt: str, tenant_id: str, tier: str):
    system_prompt = f"You serve tenant '{tenant_id}'. Tier: {tier}."
    agent = Agent(model=_model, system_prompt=system_prompt, callback_handler=None)
    return agent(prompt)
```

---

## 4. @tool Decorator — Custom Tools

```python
from strands import tool

@tool
def far_lookup(clause_number: str) -> str:
    """Look up a Federal Acquisition Regulation clause.

    Args:
        clause_number: FAR clause number (e.g., "52.219-8")
    """
    # Your lookup logic here
    return f"FAR {clause_number}: Small Business Subcontracting Plan..."

# Register with Agent
agent = Agent(model=_model, tools=[far_lookup], callback_handler=None)
```

### Tool with Context (Shared State)

```python
@tool
def stateful_tool(query: str, tool_context) -> str:
    """Process query with shared state.

    Args:
        query: The query to process
    """
    # Shared across all tools in this invocation
    tool_context.invocation_state["processed"] = True
    return f"Done: {query}"
```

---

## 5. Agents-as-Tools — Supervisor Pattern (EAGLE Port)

```python
from strands import Agent, tool
from strands.models import BedrockModel

_model = BedrockModel(model_id="us.anthropic.claude-sonnet-4-20250514-v1:0")

@tool(name="legal_counsel")
def legal_counsel(query: str) -> str:
    """Assess legal risks, FAR compliance, and protest vulnerabilities.

    Args:
        query: Legal question about the acquisition
    """
    prompt = resolve_skill_from_dynamodb("legal-counsel")
    agent = Agent(model=_model, system_prompt=prompt, callback_handler=None)
    return str(agent(query))

@tool(name="market_intelligence")
def market_intelligence(query: str) -> str:
    """Research market conditions, vendors, and pricing data.

    Args:
        query: Market research question
    """
    prompt = resolve_skill_from_dynamodb("market-intelligence")
    agent = Agent(model=_model, system_prompt=prompt, callback_handler=None)
    return str(agent(query))

# Supervisor delegates to subagent tools
supervisor = Agent(
    model=_model,
    system_prompt="You are the EAGLE supervisor. Delegate to specialist agents.",
    tools=[legal_counsel, market_intelligence],
    callback_handler=None,
)
result = supervisor("Evaluate this $500K IT acquisition")
```

---

## 6. Dynamic Subagent Factory — EAGLE Migration Pattern

```python
def _make_subagent_tool(skill_name: str, description: str, skill_tools: list):
    """Create a @tool-wrapped subagent from EAGLE skill registry."""
    @tool(name=skill_name)
    def subagent_tool(query: str) -> str:
        f"""{description}

        Args:
            query: The question for this specialist
        """
        prompt = resolve_skill_from_dynamodb(skill_name)
        agent = Agent(
            model=_model,
            system_prompt=prompt,
            tools=skill_tools,
            callback_handler=None,
        )
        return str(agent(query))
    subagent_tool.__doc__ = f"{description}\n\nArgs:\n    query: The question for this specialist"
    return subagent_tool

# Build all subagent tools from registry
subagent_tools = [
    _make_subagent_tool(name, meta["description"], meta["tools"])
    for name, meta in SKILL_AGENT_REGISTRY.items()
]
```

---

## 7. Swarm — Autonomous Agent Handoff

```python
from strands import Agent
from strands.multiagent import Swarm

intake = Agent(model=_model, system_prompt="You handle intake...")
legal = Agent(model=_model, system_prompt="You assess FAR compliance...")
market = Agent(model=_model, system_prompt="You research markets...")

swarm = Swarm(
    agents={"intake": intake, "legal": legal, "market": market},
    entry_point="intake",
    max_handoffs=20,
)
result = swarm.execute("Evaluate this IT modernization acquisition")
```

---

## 8. Graph — Deterministic Pipeline

```python
from strands import Agent
from strands.multiagent import GraphBuilder

research = Agent(model=_model, system_prompt="Research market data...")
analysis = Agent(model=_model, system_prompt="Analyze findings...")
report = Agent(model=_model, system_prompt="Generate report...")

graph = (
    GraphBuilder()
    .add_node("research", research)
    .add_node("analysis", analysis)
    .add_node("report", report)
    .add_edge("research", "analysis")
    .add_edge("analysis", "report")
    .build()
)
result = graph.execute("Analyze IT modernization market")
```

---

## 9. Session Persistence

```python
# File-based (dev)
from strands.session import FileSessionManager

agent = Agent(
    model=_model,
    session_manager=FileSessionManager(session_dir="./sessions/"),
    session_id="tenant-123-session-456",
)

# S3-based (production)
from strands.session import S3SessionManager

agent = Agent(
    model=_model,
    session_manager=S3SessionManager(bucket_name="eagle-sessions-dev"),
    session_id="tenant-123-session-456",
)
```

---

## 10. Streaming — FastAPI SSE

```python
from starlette.responses import StreamingResponse

async def stream_response(prompt: str, tenant_id: str):
    agent = Agent(model=_model, system_prompt=f"Tenant: {tenant_id}", callback_handler=None)
    async for event in agent.stream_async(prompt):
        yield f"data: {json.dumps(event)}\n\n"

@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    return StreamingResponse(
        stream_response(req.message, req.tenant_id),
        media_type="text/event-stream",
    )
```

---

## 11. System Prompt Hot-Reload (Per-Request Pattern)

```python
# DON'T: Module-level agent with frozen prompt
# legal_agent = Agent(model=_model, system_prompt="frozen...")  # NO!

# DO: Per-request agent with fresh prompt from DynamoDB
async def handle_chat(req):
    prompt = resolve_skill_from_dynamodb(req.agent_name)  # hot-reload
    agent = Agent(
        model=_model,         # shared (no boto3 overhead)
        system_prompt=prompt,  # fresh from DynamoDB
        callback_handler=None,
    )
    return agent(req.message)
```

---

## 12. Claude SDK → Strands Migration Cheat Sheet

| Claude SDK | Strands Equivalent |
|------------|-------------------|
| `ClaudeAgentOptions(model="haiku")` | `Agent(model=BedrockModel(...))` |
| `AgentDefinition(prompt=..., tools=[...])` | `@tool`-wrapped `Agent()` |
| `query(prompt, options)` | `agent(prompt)` or `agent.stream_async(prompt)` |
| `allowed_tools=["Task"]` | `tools=[subagent_tool_a, subagent_tool_b]` |
| `resume=session_id` | `session_manager=..., session_id=...` |
| `permission_mode="bypassPermissions"` | Not needed (in-process, no CLI) |
| `env={"CLAUDE_CODE_USE_BEDROCK": "1"}` | `BedrockModel(region_name=...)` |
| `max_budget_usd=0.25` | Manual tracking (no built-in budget) |
| `SystemMessage` → session_id | `session_id` param at construction |
| `ResultMessage.usage` | `result.usage` or callback handler |
| `parent_tool_use_id` (subagent) | `tool_context` in `@tool` function |

---

## 13. Key Differences from Claude SDK

| Dimension | Claude SDK | Strands |
|-----------|-----------|---------|
| Architecture | Subprocess (Node.js CLI) | In-process (Python) |
| Overhead | ~200-500ms per query | Near zero |
| Debugging | IPC, separate process | Python stack traces |
| Multi-agent | Task tool only | 4 patterns (tools, swarm, graph, workflow) |
| Sessions | External (DynamoDB) | Built-in managers + custom |
| Streaming | SSE via IPC | Async iterators + callbacks |
| Hot-reload | Natural (defs rebuilt per-request) | Requires per-request Agent pattern |
| Budget | Built-in `max_budget_usd` | Manual tracking |

---

## 14. Bridge Pattern — Strands on Top of Claude SDK (Incremental Migration)

```python
import asyncio
from strands import Agent, tool
from strands.models import BedrockModel
from app.sdk_agentic_service import sdk_query, sdk_query_single_skill

_model = BedrockModel(
    model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
    region_name="us-east-1",
)

# Bridge tool: wrap existing Claude SDK single-skill call
@tool
def oa_intake(request: str) -> str:
    """Run the OA Intake skill from eagle-plugin via Claude SDK backend.

    Args:
        request: The user's acquisition intake request
    """
    async def _run():
        result = ""
        async for msg in sdk_query_single_skill(
            prompt=request, skill_name="oa-intake",
            tenant_id="demo-tenant", user_id="demo-user", tier="advanced",
        ):
            if type(msg).__name__ == "ResultMessage":
                result = getattr(msg, "result", str(msg))
        return result
    return asyncio.run(_run())

# Bridge tool: wrap full supervisor orchestration
@tool
def eagle_supervisor(query: str) -> str:
    """Call EAGLE supervisor with full multi-agent orchestration.

    Args:
        query: The user's question or task
    """
    async def _run():
        result = ""
        async for msg in sdk_query(prompt=query, tier="premium"):
            if type(msg).__name__ == "ResultMessage":
                result = getattr(msg, "result", str(msg))
        return result
    return asyncio.run(_run())

# Strands orchestrator mixing bridge + native tools
orchestrator = Agent(
    model=_model,
    system_prompt="Route to eagle_supervisor for acquisitions, oa_intake for intake.",
    tools=[eagle_supervisor, oa_intake],
    callback_handler=None,
)
```

---

## 15. Links

- SDK: `pip install strands-agents`
- Docs: https://strandsagents.com/latest/
- GitHub: https://github.com/strands-agents/sdk-python
- Multi-agent: https://strandsagents.com/latest/documentation/docs/user-guide/concepts/multi-agent/
- AgentSkills: https://agentskills.io/specification
- EAGLE comparison report: `docs/development/20260302-*-report-claude-sdk-vs-strands-v1.md`
