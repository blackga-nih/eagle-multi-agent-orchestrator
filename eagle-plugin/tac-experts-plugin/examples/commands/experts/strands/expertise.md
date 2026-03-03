---
type: expert-file
file-type: expertise
domain: strands
last_updated: "2026-03-02T20:00:00"
sdk_version: "1.28.0"
tags: [strands-agents-sdk, agent, tool, bedrock, swarm, graph, multi-agent, streaming, sessions, hooks, agentskills, migration]
---

# Strands Agents SDK Expertise

> Complete mental model for `strands-agents` — the AWS-native Python SDK for building agentic applications. Context: EAGLE migration readiness from Claude Agent SDK.

---

## Part 1: SDK Overview & Installation

### Package

- **Name**: `strands-agents` (pip), `strands-agents-tools` (optional tool pack)
- **Version**: 1.0+ (GA released 2025-06)
- **Install**: `pip install strands-agents strands-agents-tools`
- **Skills**: `pip install agent-skills-sdk` (AgentSkills.io integration)

### Key Modules

| Import | Purpose |
|--------|---------|
| `strands.Agent` | Core agent class — construction, invocation, streaming |
| `strands.tool` | `@tool` decorator for custom tool functions |
| `strands.models.BedrockModel` | AWS Bedrock model provider |
| `strands.models.AnthropicModel` | Direct Anthropic API provider |
| `strands.multiagent.Swarm` | Autonomous agent handoff orchestration |
| `strands.multiagent.Graph` | Deterministic DAG execution |
| `strands.multiagent.GraphBuilder` | Fluent builder for Graph construction |
| `strands.session.FileSessionManager` | Local file session persistence |
| `strands.session.S3SessionManager` | S3-backed session persistence |

### Standard Import Block

```python
from strands import Agent, tool
from strands.models import BedrockModel
# Optional:
from strands.multiagent import Swarm, Graph, GraphBuilder
from strands.session import FileSessionManager, S3SessionManager
```

### Backend

- **Bedrock** (primary): `BedrockModel(model_id="...", region_name="us-east-1")`
- **Anthropic direct**: `AnthropicModel(api_key="...")`
- **Any provider**: Implement `Model` interface (converse/converse_stream)

---

## Part 2: Agent() API

### Constructor

```python
agent = Agent(
    model=BedrockModel(model_id="us.amazon.nova-pro-v1:0"),
    system_prompt="You are a helpful assistant.",
    tools=[my_tool_a, my_tool_b],
    callback_handler=None,            # or custom CallbackHandler
    conversation_manager=None,        # or SlidingWindowConversationManager
    session_manager=None,             # or FileSessionManager / S3SessionManager
    tool_executor=None,               # or ConcurrentToolExecutor() for parallel tools
    load_tools_from_directory=None,   # auto-load from dir
    record_direct_tool_call=True,     # record direct tool calls in history
)
```

### What Happens at Construction

1. `BedrockModel.__init__()` — creates `boto3.client("bedrock-runtime")` (~50-200ms)
2. `ToolRegistry.process_tools()` — validates `@tool` signatures, extracts JSON schemas
3. `ConversationManager.__init__()` — `SlidingWindowConversationManager` (200k token window default)
4. `HookRegistry.__init__()` — registers lifecycle hooks
5. `AgentState` initialized (empty dict or user-provided)
6. Threading `Lock` created (default: THROW mode)
7. Plugins initialized (each `.init(agent)` called)
8. `AgentInitializedEvent` fired

### Invocation (Sync)

```python
result = agent("What is the weather?")
# result is AgentResult
print(result)           # final text
print(result.stop_reason)  # "end_turn"
```

### Invocation (Async Streaming)

```python
async for event in agent.stream_async("What is the weather?"):
    # event contains streaming chunks
    pass
```

### System Prompt Mutation

```python
# System prompt is MUTABLE via setter
agent.system_prompt = "New instructions..."
agent("query")  # uses new prompt
```

**Warning**: Not thread-safe with default THROW lock mode.

---

## Part 3: BedrockModel

### Constructor

```python
from strands.models import BedrockModel

model = BedrockModel(
    model_id="us.amazon.nova-pro-v1:0",
    region_name="us-east-1",
    # Optional:
    boto_session=boto3.Session(profile_name="eagle"),
    max_tokens=4096,
    additional_model_request_fields={},  # e.g., prompt caching
)
```

### Key Properties

- Creates `boto3.client("bedrock-runtime")` at `__init__`
- Connection pool + TLS handshake on first API call
- Supports `converse()` (sync) and `converse_stream()` (streaming)
- Model ID format: `us.anthropic.claude-{tier}-{version}:0`
- Supports prompt caching via `additional_model_request_fields`

### Prompt Caching

```python
model = BedrockModel(
    model_id="us.amazon.nova-pro-v1:0",
    additional_model_request_fields={
        "anthropic_beta": ["prompt-caching-2024-07-31"]
    },
)
```

### Sharing Model Across Agents

```python
# Module-level: create once, reuse everywhere
shared_model = BedrockModel(
    model_id="us.amazon.nova-pro-v1:0",
    region_name="us-east-1",
)

# Per-request: new Agent, shared model (no boto3 overhead)
agent = Agent(model=shared_model, system_prompt="fresh prompt")
```

**This is the recommended pattern for EAGLE** — avoids ~50-200ms boto3 client creation per request.

---

## Part 4: Tools (@tool Decorator)

### Basic Tool

```python
from strands import tool

@tool
def get_weather(location: str, unit: str = "celsius") -> str:
    """Get the current weather for a location.

    Args:
        location: City name or coordinates
        unit: Temperature unit (celsius or fahrenheit)
    """
    return f"Weather in {location}: 22°{unit[0].upper()}"
```

### Tool with Context

```python
from strands import tool

@tool
def stateful_tool(query: str, tool_context) -> str:
    """A tool that accesses invocation state.

    Args:
        query: The search query
    """
    # Access shared state across tools in same invocation
    tool_context.invocation_state["last_query"] = query

    # Access the agent itself
    agent = tool_context.agent

    return f"Processed: {query}"
```

### Tool Registration

```python
agent = Agent(
    model=shared_model,
    tools=[get_weather, stateful_tool],
)
```

### JSON Schema Extraction

- Docstring → tool description
- Type hints → parameter types
- `Args:` section → parameter descriptions
- Default values → optional parameters

### Tool Hot-Reload (Dev Mode)

```python
agent = Agent(
    model=model,
    tools=[],
    load_tools_from_directory="./tools/",  # ToolWatcher monitors dir
)
# Changes to tool files auto-reload without restart
```

### Direct Tool Call

```python
# Call tool programmatically (bypasses LLM)
result = agent.tool.get_weather(location="London")
```

---

## Part 5: Multi-Agent Patterns

### Pattern 1: Agents-as-Tools (Closest to EAGLE's Current Architecture)

```python
from strands import Agent, tool
from strands.models import BedrockModel

shared_model = BedrockModel(model_id="us.amazon.nova-pro-v1:0")

@tool(name="legal_counsel")
def legal_counsel(query: str) -> str:
    """Assess legal risks, FAR compliance, and protest vulnerabilities.

    Args:
        query: Legal question about the acquisition
    """
    prompt = resolve_skill_from_dynamodb("legal-counsel")
    agent = Agent(model=shared_model, system_prompt=prompt, callback_handler=None)
    return str(agent(query))

@tool(name="market_intelligence")
def market_intelligence(query: str) -> str:
    """Research market conditions, vendors, and pricing data.

    Args:
        query: Market research question
    """
    prompt = resolve_skill_from_dynamodb("market-intelligence")
    agent = Agent(model=shared_model, system_prompt=prompt, callback_handler=None)
    return str(agent(query))

supervisor = Agent(
    model=shared_model,
    system_prompt="You are the EAGLE supervisor...",
    tools=[legal_counsel, market_intelligence],
)
result = supervisor("Evaluate this $500K acquisition")
```

**Context isolation**: Complete — subagent sees ONLY the query string.
**Control flow**: Supervisor retains control throughout.
**EAGLE mapping**: Direct port of current supervisor→subagent architecture.

### Pattern 2: Swarm (Autonomous Agent Handoff)

```python
from strands import Agent
from strands.multiagent import Swarm

intake_agent = Agent(
    model=shared_model,
    system_prompt="You handle acquisition intake...",
    tools=[classify_acquisition],
)

legal_agent = Agent(
    model=shared_model,
    system_prompt="You assess FAR compliance...",
    tools=[far_lookup],
)

swarm = Swarm(
    agents={
        "intake": intake_agent,
        "legal": legal_agent,
    },
    entry_point="intake",
    max_handoffs=20,
    max_iterations=20,
)
result = swarm.execute("Evaluate this acquisition")
```

**Key mechanism**: `handoff_to_agent` tool is auto-injected into every agent.
**Context**: Partial — each agent has own conversation but sees curated summary via SharedContext.
**Control flow**: Full transfer — original agent STOPS, target STARTS. No return.

**Safety bounds**:
- `max_handoffs`: 20 (total transfers)
- `max_iterations`: 20 (total event loop cycles)
- `execution_timeout`: 900s (15 min wall clock)
- `node_timeout`: 300s (5 min per agent)

### Pattern 3: Graph (Deterministic DAG)

```python
from strands import Agent
from strands.multiagent import GraphBuilder

research = Agent(model=shared_model, system_prompt="Research market...")
analysis = Agent(model=shared_model, system_prompt="Analyze findings...")
report = Agent(model=shared_model, system_prompt="Generate report...")

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

**Supports**: Parallel fan-out, fan-in, conditional edges, cycles with loop detection, nested graphs/swarms.
**Context**: Low isolation — nodes share full execution context.
**Control flow**: Deterministic — edges define execution order.

### Pattern 4: Workflow (Acyclic DAG)

Similar to Graph but strictly acyclic. Each task receives a curated summary of dependencies' results. Best for repeatable pipelines.

### Multi-Agent Pattern Decision Matrix

#### Speed & Cost Profile

| Pattern | LLM Calls (typical) | Parallelism | Latency Profile | Token Cost | Overhead |
|---------|---------------------|-------------|-----------------|------------|----------|
| **Agents-as-Tools** | 1 supervisor + N subagent (sequential) | None by default; `tool_executor=ConcurrentToolExecutor()` for parallel | **Additive**: supervisor turn + each tool call in series | Moderate — supervisor sees tool results, subagents see only query | Lowest — just `@tool` wrappers |
| **Agents-as-Tools (parallel)** | 1 supervisor + N subagent (concurrent) | Yes — `tool_executor=ConcurrentToolExecutor()` | **Near-constant**: supervisor turn + slowest tool | Same token cost, wall-clock reduced | Low — same as above |
| **Swarm** | 1 per handoff (serial chain) | None — strictly sequential handoffs | **Additive**: each agent does full turn before handing off | Higher — each agent accumulates own conversation + SharedContext summary | Medium — handoff coordination, SharedContext serialization |
| **Graph** | 1 per node; parallel branches run concurrently | Yes — fan-out edges run in parallel | **Depth of DAG**: parallel branches overlap, sequential chains add | Highest — nodes share full execution context (growing prompt) | Highest — graph construction, edge evaluation, context merging |
| **Workflow** | 1 per task (strictly sequential) | None — acyclic, no parallelism | **Additive**: sum of all task durations | Moderate — each task gets curated dependency summary, not full context | Low — simple pipeline |

#### Speed Examples (EAGLE Scenarios)

| Scenario | Best Pattern | Why | Estimated LLM Calls | Est. Latency (Llama 4 ~5s/call) |
|----------|-------------|-----|---------------------|--------------------------------|
| "Evaluate this $500K IT acquisition" (supervisor routes to legal + market) | Agents-as-Tools (parallel) | Supervisor decides who to call, gets answers back, synthesizes | 1 supervisor + 2 subagent = 3 | ~10s (supervisor + slowest parallel tool) |
| Same query, sequential tools | Agents-as-Tools | Default behavior — tools called one at a time | 1 + 2 = 3 | ~15s (supervisor + legal + market) |
| Same query via Swarm | Swarm | intake→legal→market (each hands off) | 3 agents × ~1-2 turns each = 3-6 | ~15-30s (serial chain, no return to supervisor) |
| Document generation pipeline (intake→compliance→draft→review) | Graph | Fixed steps, compliance+draft can fan-out in parallel | 4 nodes | ~10-15s (2 parallel branches) |
| Single skill call (micro-purchase intake) | Direct Agent | No orchestration needed | 1 | ~5s |

#### Control Flow Comparison

```
Agents-as-Tools (EAGLE default):
  User → Supervisor → legal_counsel(@tool) → result back → market_intel(@tool) → result back → Supervisor synthesizes → User
  Control: Supervisor ALWAYS in charge. Can call 0, 1, or N tools per turn.
  Speed:   N sequential tool calls (or parallel with ConcurrentToolExecutor).

Swarm:
  User → intake_agent → handoff_to("legal") → legal_agent → handoff_to("market") → market_agent → done
  Control: Each agent decides whether to hand off. No return. No supervisor synthesis.
  Speed:   N serial handoffs. Each agent does full converse() cycle + handoff overhead.

Graph:
  User → [research, compliance] (parallel) → analysis (waits for both) → report → done
  Control: Edges are fixed at construction. No LLM decides routing.
  Speed:   Depth of DAG. Parallel branches overlap. Best for known pipelines.
```

#### When NOT to Use Each Pattern

| Pattern | Avoid When | Reason |
|---------|-----------|--------|
| Agents-as-Tools | You need agents to autonomously decide the next agent | Supervisor must explicitly call tools — no autonomous routing |
| Swarm | You need a supervisor to synthesize across specialists | No return from handoff — can't combine answers |
| Graph | Routing depends on LLM judgment per-request | Edges are fixed at build time — can't dynamically skip nodes |
| Workflow | You need parallel execution or cycles | Strictly acyclic and sequential |

#### EAGLE Recommendation

**Agents-as-Tools with `ConcurrentToolExecutor`** is the right pattern because:
1. Matches current supervisor→subagent architecture (zero conceptual change)
2. Supervisor retains control to synthesize across specialists
3. Parallel tool calls reduce wall-clock time when multiple specialists needed
4. Per-request Agent construction preserves hot-reload (same as Claude SDK subprocess model)
5. Lowest overhead — no graph construction, no handoff coordination, no SharedContext serialization

### Official Reference Examples & Links

#### Agents-as-Tools (EAGLE's pattern)

- **Docs**: https://strandsagents.com/latest/documentation/docs/user-guide/concepts/multi-agent/agents-as-tools/
- **Tutorial**: https://github.com/strands-agents/samples/tree/main/01-tutorials/02-multi-agent-systems/01-agent-as-tool
- **Full example** (Teacher's Assistant): https://strandsagents.com/latest/documentation/docs/examples/python/multi_agent_example/multi_agent_example/
- **How it works**: Each specialist is a `@tool`-decorated function that creates an `Agent()` internally. The orchestrator `Agent` has `tools=[specialist_a, specialist_b, ...]` and routes via LLM judgment. Orchestrator retains control — subagent returns result string, orchestrator synthesizes. Key detail: use `callback_handler=None` on inner agents to suppress stdout, and use `response.text` or `str(response)` to extract the answer.

```python
# Official pattern from docs
@tool
def math_assistant(query: str) -> str:
    """Process math-related queries using a specialized math agent."""
    math_agent = Agent(system_prompt=MATH_PROMPT, tools=[calculator])
    response = math_agent(f"Please solve: {query}")
    return response.text
```

#### Swarm (Autonomous Handoff)

- **Docs**: https://strandsagents.com/latest/documentation/docs/user-guide/concepts/multi-agent/swarm/
- **Tutorial**: https://github.com/strands-agents/samples/blob/main/01-tutorials/02-multi-agent-systems/02-swarm-agent/swarm.ipynb
- **Source**: https://github.com/strands-agents/sdk-python/blob/main/src/strands/multiagent/swarm.py
- **How it works**: Create named `Agent` instances, wrap in `Swarm(agents, entry_point, ...)`. Each agent gets auto-injected `handoff_to_agent` tool. When agent calls `handoff_to_agent("coder", message="...", context={})`, current agent STOPS and target agent STARTS. No return. Includes repetitive handoff detection (`repetitive_handoff_detection_window=8`, `repetitive_handoff_min_unique_agents=3`) to prevent ping-pong loops. Access results via `result.status` and `result.node_history`.

```python
# Official pattern from docs
swarm = Swarm(
    [coder, researcher, reviewer, architect],
    entry_point=researcher,
    max_handoffs=20, max_iterations=20,
    execution_timeout=900.0, node_timeout=300.0,
    repetitive_handoff_detection_window=8,
    repetitive_handoff_min_unique_agents=3,
)
result = swarm("Design and implement a REST API")
```

#### Graph (Deterministic DAG with Conditional Routing)

- **Docs**: https://strandsagents.com/latest/documentation/docs/user-guide/concepts/multi-agent/graph/
- **Tutorial**: https://github.com/strands-agents/samples/tree/main/01-tutorials/02-multi-agent-systems/03-graph-agent
- **How it works**: Use `GraphBuilder` to define nodes (agents) and edges (dependencies). Supports parallel fan-out (nodes with no dependency on each other run concurrently), conditional edges (Python functions that inspect `GraphState` to decide traversal), cycles with loop detection, and configurable timeouts. Entry point set via `set_entry_point()`. Nodes share execution context via `invocation_state`.

```python
# Official pattern from docs — fan-out + fan-in
builder = GraphBuilder()
builder.add_node(researcher, "research")
builder.add_node(analyst, "analysis")
builder.add_node(fact_checker, "fact_check")
builder.add_node(report_writer, "report")
builder.add_edge("research", "analysis")       # fan-out: research → analysis
builder.add_edge("research", "fact_check")      # fan-out: research → fact_check
builder.add_edge("analysis", "report")          # fan-in: both → report
builder.add_edge("fact_check", "report")
builder.set_entry_point("research")
builder.set_execution_timeout(600)
graph = builder.build()
result = graph("Research AI impact on healthcare")
```

#### Workflow (Acyclic Task Pipeline)

- **Docs**: https://strandsagents.com/latest/documentation/docs/user-guide/concepts/multi-agent/multi-agent-patterns/
- **How it works**: A pre-defined task graph (strictly acyclic DAG) executed as a single tool. Independent tasks can run in parallel. Each task receives curated dependency summaries, not full context. Best for repeatable business processes (onboarding, approvals, data pipelines). Failures halt downstream tasks automatically.

#### Pattern Comparison (Official)

- **Overview**: https://strandsagents.com/latest/documentation/docs/user-guide/concepts/multi-agent/multi-agent-patterns/
- **AWS Blog** (Amazon Nova examples): https://aws.amazon.com/blogs/machine-learning/multi-agent-collaboration-patterns-with-strands-agents-and-amazon-nova/
- **Deep dive**: https://aws.amazon.com/blogs/machine-learning/strands-agents-sdk-a-technical-deep-dive-into-agent-architectures-and-observability/
- **Samples repo**: https://github.com/strands-agents/samples

| Aspect | Graph | Swarm | Workflow | Agents-as-Tools |
|--------|-------|-------|----------|-----------------|
| Path determination | LLM decides at each node | Agents autonomously handoff | Fixed by dependency graph | Orchestrator LLM selects tools |
| Cycles allowed | Yes | Yes | No | N/A (single turn) |
| Execution model | Controlled but dynamic | Sequential & autonomous | Deterministic & parallel | Orchestrator-driven |
| State sharing | Single shared dict | SharedContext with task history | Auto output capture | Complete isolation (query string only) |
| Error handling | Explicit error edges | Agent-driven decisions | Failures halt downstream | Tool returns error string |

---

## Part 6: Session Management

### FileSessionManager (Dev/Local)

```python
from strands.session import FileSessionManager

agent = Agent(
    model=model,
    system_prompt="...",
    session_manager=FileSessionManager(session_dir="./sessions/"),
    session_id="user-123-session-456",  # explicit ID
)
```

### S3SessionManager (Production)

```python
from strands.session import S3SessionManager

agent = Agent(
    model=model,
    system_prompt="...",
    session_manager=S3SessionManager(
        bucket_name="eagle-sessions-dev",
        prefix="sessions/",
    ),
    session_id="tenant-123-user-456-session-789",
)
```

### Custom SessionManager (DynamoDB — EAGLE Pattern)

```python
from strands.session import SessionManager

class DynamoDBSessionManager(SessionManager):
    def __init__(self, table_name: str, tenant_id: str):
        self.table = boto3.resource("dynamodb").Table(table_name)
        self.tenant_id = tenant_id

    def read_session(self, session_id: str) -> list:
        item = self.table.get_item(Key={"PK": f"SESSION#{session_id}", "SK": "HISTORY"})
        return item.get("Item", {}).get("messages", [])

    def write_session(self, session_id: str, messages: list):
        self.table.put_item(Item={
            "PK": f"SESSION#{session_id}",
            "SK": "HISTORY",
            "tenant_id": self.tenant_id,
            "messages": messages,
        })
```

### Session ID Format (EAGLE Convention)

```
{tenant_id}-{tier}-{user_id}-{session_id}
```

### Multi-Agent Session Persistence

**Open issue** (#867): Swarm and Graph don't persist session history per-agent yet. Track upstream for updates.

---

## Part 7: Streaming

### Callback Handler (Default Pattern)

```python
from strands.handlers import PrintCallbackHandler

agent = Agent(
    model=model,
    callback_handler=PrintCallbackHandler(),  # prints to stdout
)
```

### Custom Callback Handler

```python
from strands.handlers import CallbackHandler

class SSECallbackHandler(CallbackHandler):
    def __init__(self, response_queue):
        self.queue = response_queue

    def on_text_chunk(self, text: str, **kwargs):
        self.queue.put({"type": "text", "content": text})

    def on_tool_use(self, tool_name: str, tool_input: dict, **kwargs):
        self.queue.put({"type": "tool_use", "tool": tool_name})

    def on_tool_result(self, tool_name: str, result: str, **kwargs):
        self.queue.put({"type": "tool_result", "tool": tool_name})
```

### Async Streaming (FastAPI SSE)

```python
from starlette.responses import StreamingResponse

async def stream_agent_response(prompt: str):
    async for event in agent.stream_async(prompt):
        yield f"data: {json.dumps(event)}\n\n"

@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    return StreamingResponse(
        stream_agent_response(req.message),
        media_type="text/event-stream",
    )
```

### Disabling Streaming Output

```python
# callback_handler=None suppresses all output
agent = Agent(model=model, system_prompt="...", callback_handler=None)
```

---

## Part 8: Hooks & Lifecycle Events

### Event Types

| Event | When Fired | Use Case |
|-------|-----------|----------|
| `AgentInitializedEvent` | After Agent() construction | Setup logging, telemetry |
| `BeforeInvocationEvent` | Before agent processes prompt | Input validation, prompt modification |
| `AfterInvocationEvent` | After agent completes | Post-processing, audit logging |
| `BeforeToolCallEvent` | Before tool execution | Tool call interception |
| `AfterToolCallEvent` | After tool execution | Result inspection |
| `ContextWindowOverflowEvent` | When context exceeds limit | Custom trimming strategy |

### Hook Registration

```python
from strands.hooks import HookRegistry

def on_before_invocation(event):
    print(f"Processing: {event.prompt}")
    # Can modify event.messages before they reach the model

def on_after_invocation(event):
    print(f"Result: {event.result}")
    # Audit logging, telemetry emission

agent = Agent(
    model=model,
    system_prompt="...",
    hooks={
        "before_invocation": [on_before_invocation],
        "after_invocation": [on_after_invocation],
    },
)
```

### Plugin System

```python
class TelemetryPlugin:
    def init(self, agent):
        agent.hooks.register("after_invocation", self.log_invocation)

    def log_invocation(self, event):
        emit_to_cloudwatch(event.result, event.usage)
```

---

## Part 9: Agent Skills (AgentSkills.io)

### SKILL.md Format (AgentSkills.io Spec)

```yaml
---
name: oa-intake
description: >
  Guide users through the NCI Office of Acquisitions intake process.
license: Apache-2.0
allowed-tools: Read Bash(python3:*)
metadata:
  author: eagle-team
  version: "1.0"
---

# OA Intake Skill

## Overview
This skill collects acquisition requirements...

## Step-by-Step Instructions
1. Ask for the acquisition description
2. Determine estimated dollar value
...
```

### Progressive Disclosure (Three Phases)

```
Phase 1 — Metadata (at construction): ~100 tokens/skill
  discover_skills("./skills")
  → [{name, description}, ...]
  → generate_skills_prompt(skills) → injected into system_prompt

Phase 2 — Instructions (on activation): ~2,000-5,000 tokens
  Agent calls skill(skill_name="oa-intake")
  → Full SKILL.md body loaded into context

Phase 3 — Resources (on demand): variable
  Agent reads scripts/ or references/ files as needed
```

**Token savings**: 91% reduction vs. loading all skills upfront (16 skills: 36,884 → 1,600 tokens).

### Three Integration Patterns

```
Pattern 1 — File-Based: Agent has file_read tool → reads SKILL.md directly
Pattern 2 — Tool-Based: skill() tool activates by name → SKILL.md body injected
Pattern 3 — Agent-as-Tool: Each skill spawns isolated sub-agent (closest to EAGLE)
```

### EAGLE SKILL.md Compatibility

EAGLE's current format is **95% compatible** with AgentSkills.io:
- Add: `license`, `allowed-tools`, `metadata` fields
- Remove: `type`, `triggers`, `model` (handle in registry layer)
- Body: Zero changes needed

---

## Part 10: Concurrency

### Lock Modes

| Mode | Behavior | Use Case |
|------|----------|----------|
| `THROW` (default) | Reject concurrent calls with error | Single-user, safety-first |
| `REENTRANT` | Allow concurrent calls (caller manages) | Multi-tenant server |

### Thread Safety

```python
# Default: throws if agent is already processing
agent = Agent(model=model, ...)

# Reentrant: allows concurrent (but shares conversation history!)
agent = Agent(model=model, concurrent_mode="REENTRANT", ...)
```

**EAGLE recommendation**: Use per-request Agent construction (not shared agents) to avoid concurrency issues entirely.

---

## Part 11: EAGLE Migration Mapping

### What You Keep (Port Directly)

| Component | Current File | Strands Equivalent |
|-----------|-------------|-------------------|
| Plugin store | `plugin_store.py` | Same — DynamoDB PLUGIN# CRUD + 60s cache |
| Workspace overrides | `wspc_store.py` | Same — WSPC# prompt overrides |
| Tenant custom skills | `skill_store.py` | Same — SKILL# entities |
| Skill discovery | `eagle_skill_constants.py` | Same — bootstrap seeder |
| Registry | `SKILL_AGENT_REGISTRY` | Same — module-level metadata |
| 4-layer resolution | `resolve_skill()` | Same — wspc → plugin → bundled |
| Tier-based gating | `TIER_TOOLS` dict | Same — map tiers to tool lists |
| Multi-tenant isolation | `system_prompt` injection | Same — Agent(system_prompt=...) |

### What Changes

| Claude SDK | Strands Equivalent |
|------------|-------------------|
| `AgentDefinition` | `@tool`-wrapped `Agent()` |
| `ClaudeAgentOptions` | `Agent()` constructor |
| `query()` subprocess | In-process `agent()` call |
| `_get_bedrock_env()` | `BedrockModel(region_name=...)` |
| SSE message types | Callback handler or async iterators |
| `resume: session_id` | `SessionManager` |

### What You Gain

- No subprocess overhead (~200-500ms saved per query)
- In-process debugging (Python stack traces, no IPC)
- Native async streaming (`stream_async()`)
- Built-in session managers (S3, file, custom)
- Tool hot-reload (ToolWatcher for dev)
- Swarm/Graph patterns for complex workflows
- Lazy subagent loading (only pay for agents invoked)
- Prompt caching (ContentBlock cache_point)

### Recommended Migration Service

```python
# strands_agentic_service.py — EAGLE on Strands

from strands import Agent, tool
from strands.models import BedrockModel

# Module-level: expensive parts created once
_model = BedrockModel(
    model_id="us.amazon.nova-pro-v1:0",
    region_name="us-east-1",
)

def _make_subagent_tool(skill_name: str, description: str, skill_tools: list):
    @tool(name=skill_name)
    def subagent_tool(query: str) -> str:
        f"""<dynamic description>

        Args:
            query: The question or task for this specialist
        """
        prompt = resolve_skill_from_dynamodb(skill_name)
        agent = Agent(model=_model, system_prompt=prompt, tools=skill_tools, callback_handler=None)
        return str(agent(query))
    subagent_tool.__doc__ = f"{description}\n\nArgs:\n    query: The question for this specialist"
    return subagent_tool

async def strands_query(prompt, tenant_id, user_id, tier, session_id):
    workspace_id = get_or_create_default(tenant_id, user_id)

    subagent_tools = [
        _make_subagent_tool(name, meta["description"], meta["tools"])
        for name, meta in SKILL_AGENT_REGISTRY.items()
    ]

    supervisor_prompt = resolve_supervisor_from_dynamodb(workspace_id)
    supervisor = Agent(
        model=_model,
        system_prompt=supervisor_prompt,
        tools=subagent_tools,
        callback_handler=None,
    )

    async for event in supervisor.stream_async(prompt):
        yield event
```

---

## Part 12: Bridge Pattern — Strands on Top of Claude SDK

### Concept

Instead of a full migration (replace `sdk_agentic_service.py`), layer Strands **on top** of the existing Claude SDK backend. Strands becomes an outer orchestration shell that calls into EAGLE's existing `sdk_query()` / `sdk_query_single_skill()` via `@tool` wrappers.

```
┌──────────────────────────────────────────────────────────┐
│  Strands Orchestrator                                     │
│  Agent(model=_model, tools=[eagle_supervisor, ...])       │
│      │                                                    │
│      ├── eagle_supervisor @tool                           │
│      │   └── sdk_query() ← existing Claude SDK backend    │
│      │       └── subprocess → supervisor → subagents      │
│      │                                                    │
│      ├── eagle_oa_intake @tool                            │
│      │   └── sdk_query_single_skill("oa-intake")          │
│      │                                                    │
│      ├── pure_strands_tool @tool                          │
│      │   └── in-process (no Claude SDK dependency)        │
│      │                                                    │
│      └── external_api_tool @tool                          │
│          └── HTTP call to vendor API                      │
└──────────────────────────────────────────────────────────┘
```

### Why Bridge Instead of Full Rewrite

| Factor | Full Rewrite | Bridge Pattern |
|--------|-------------|----------------|
| Risk | High — replace entire orchestration | Low — additive layer |
| Timeline | Weeks | Hours |
| Rollback | Hard | Just remove Strands layer |
| Feature parity | Must re-implement everything | Inherits existing behavior |
| New capabilities | Native only | Mix Strands-native + Claude SDK |
| Skill definitions | Must port | `eagle-plugin/` unchanged |

### Wrapping a Skill as a Strands Tool

```python
# server/app/strands_tools/oa_intake_tool.py
from strands import tool
from app.sdk_agentic_service import sdk_query_single_skill

@tool
def oa_intake(request: str) -> str:
    """Run the OA Intake skill from eagle-plugin.

    Args:
        request: The user's acquisition intake request
    """
    result_text = ""
    async for msg in sdk_query_single_skill(
        prompt=request,
        skill_name="oa-intake",
        tenant_id="demo-tenant",
        user_id="demo-user",
        tier="advanced",
    ):
        if type(msg).__name__ == "ResultMessage":
            result_text = getattr(msg, "result", str(msg))
    return result_text
```

### Wrapping the Full Supervisor as a Strands Tool

```python
# server/app/strands_tools/eagle_supervisor_tool.py
from strands import tool
from app.sdk_agentic_service import sdk_query

@tool
def eagle_supervisor(query: str, tenant_id: str = "demo-tenant", user_id: str = "demo-user") -> str:
    """Call the EAGLE supervisor agent with full multi-agent orchestration.

    Args:
        query: The user's question or task for EAGLE
        tenant_id: Tenant identifier for multi-tenant isolation
        user_id: User identifier
    """
    session_id = f"{tenant_id}-premium-{user_id}-strands"
    result_text = ""
    async for msg in sdk_query(
        prompt=query,
        tenant_id=tenant_id,
        user_id=user_id,
        tier="premium",
        session_id=session_id,
    ):
        if type(msg).__name__ == "ResultMessage":
            result_text = getattr(msg, "result", str(msg))
    return result_text
```

### Composing the Bridge Orchestrator

```python
from strands import Agent
from strands.models import BedrockModel
from app.strands_tools.oa_intake_tool import oa_intake
from app.strands_tools.eagle_supervisor_tool import eagle_supervisor

_model = BedrockModel(
    model_id="us.amazon.nova-pro-v1:0",
    region_name="us-east-1",
)

# Strands orchestrator that mixes EAGLE backend + Strands-native tools
orchestrator = Agent(
    model=_model,
    system_prompt="""You are a Strands orchestrator layered on top of EAGLE.
Use eagle_supervisor for complex multi-agent acquisition workflows.
Use oa_intake for focused intake flows.
Use pure Strands tools for non-EAGLE tasks.""",
    tools=[eagle_supervisor, oa_intake],  # mix of bridge + native tools
    callback_handler=None,
)
```

### Architectural Layers

```
eagle-plugin/          → Defines WHAT agents/skills exist and how they behave
  └── agents/, skills/    (source of truth — never duplicated)

FastAPI backend         → Already knows HOW to execute those via Claude SDK
  └── sdk_query()         (supervisor orchestration)
  └── sdk_query_single_skill()  (single skill execution)

Strands layer          → OUTER orchestration that:
  └── treats backend entry points as @tool functions
  └── can mix in pure Strands-native tools (HTTP, retrieval, etc.)
  └── can introduce Swarm/Graph patterns on top
  └── does NOT replace eagle-plugin definitions
```

### Async Bridge Consideration

`sdk_query()` is an async generator. Strands `@tool` functions are sync by default. Two options:

1. **Collect all messages**: Run the async generator to completion, return final result (simple, lossy)
2. **Bridge with asyncio.run()**: If Strands is running in a sync context, use `asyncio.run()` or `loop.run_until_complete()` to drive the async generator

For streaming, the bridge tool should collect `ResultMessage.result` and return it as the tool output. SSE streaming from the outer Strands agent handles real-time delivery.

---

## Learnings

### patterns_that_work

- **Shared BedrockModel, per-request Agent**: Module-level `BedrockModel` avoids ~50-200ms boto3 overhead per request. Agent construction with fresh `system_prompt` gives hot-reload. This is the hybrid pattern (Option C). (discovered: 2026-03-02)
- **Agents-as-tools for supervisor pattern**: Wrap each subagent as a `@tool` function. Supervisor calls them as tools. Direct port of Claude SDK's AgentDefinition + Task pattern. (discovered: 2026-03-02)
- **DynamoDB prompt infrastructure for hot-reload**: Neither SDK gives hot-reload natively. EAGLE's existing `plugin_store.py` + `wspc_store.py` + 60s cache IS the hot-reload mechanism. Carry forward to any framework. (discovered: 2026-03-02)
- **callback_handler=None for subagents**: Suppresses all output from subagents. Only the return value goes back to the supervisor. (discovered: 2026-03-02)
- **Progressive skill disclosure**: Load only skill metadata (~100 tokens each) at construction. Full body (~2-5k tokens) loaded on-demand. 91% token savings with 16 skills. (discovered: 2026-03-02)
- **Bridge pattern — Strands on top of Claude SDK**: Wrap `sdk_query()` and `sdk_query_single_skill()` as `@tool` functions callable by a Strands `Agent`. No need to rewrite skill execution — `eagle-plugin/` stays source of truth, FastAPI backend stays the executor, Strands adds an outer orchestration layer. Hours to implement vs. weeks for full rewrite. (discovered: 2026-03-02, component: migration)
- **Mix bridge + native tools**: A Strands orchestrator can combine `@tool`-wrapped EAGLE backend calls with pure Strands-native tools (HTTP, retrieval, calculators). This allows incremental adoption — start with bridge, migrate individual skills to native Strands as needed. (discovered: 2026-03-02, component: migration)
- **Wrap at two granularities**: Wrap `sdk_query()` as a "full supervisor" tool for complex multi-agent workflows, and wrap `sdk_query_single_skill()` per-skill for focused tasks. The Strands orchestrator decides which granularity to use per-request. (discovered: 2026-03-02, component: migration)
- **Sync `agent(prompt)` for tests**: `agent(prompt)` returns an `AgentResult` synchronously — no `pytest-asyncio` required. Use `str(result)` to extract the full text response. Simple and reliable for eval-style tests. (discovered: 2026-03-02, component: poc-test)
- **`eagle_skill_constants.SKILL_CONSTANTS` is SDK-agnostic**: The bundled fallback in `eagle_skill_constants.py` loads all 14 skills from `eagle-plugin/` disk files. Works identically with Claude SDK and Strands — zero coupling to either SDK. (discovered: 2026-03-02, component: skill-loader)
- **strands-agents coexists with claude-agent-sdk**: Both packages install cleanly in the same venv (tested: strands-agents 1.28.0 + claude-agent-sdk 0.1.19). No dependency conflicts. Enables incremental migration. (discovered: 2026-03-02, component: installation)
- **Multi-agent agents-as-tools proven on Nova Pro**: Supervisor with 3 @tool-wrapped subagents (oa_intake, legal_counsel, market_intelligence) routes correctly every time. 11/12 indicators found across 3 tests. ~18-24s per supervisor+subagent call on Nova Pro. (discovered: 2026-03-02, component: multi-agent-poc)
- **Supervisor reliably delegates with explicit tool descriptions**: The supervisor's system_prompt should list available tools with clear descriptions. Nova Pro correctly maps "buy lab supplies" to oa_intake, "sole-source contract" to legal_counsel, "FedRAMP cloud vendors" to market_intelligence. (discovered: 2026-03-02, component: multi-agent-poc)
- **Adapter dataclasses for drop-in replacement**: Use `@dataclass` classes named exactly `AssistantMessage` and `ResultMessage` (matching Claude SDK class names) so callers checking `type(msg).__name__` work unchanged. `TextBlock` and `ToolUseBlock` adapt content blocks. Zero changes needed in `streaming_routes.py` or `main.py`. (discovered: 2026-03-02, component: service-migration)
- **Skill name hyphen-to-underscore for @tool names**: Strands `@tool(name=...)` must use Python-valid identifiers. Use `skill_name.replace("-", "_")` (e.g., "oa-intake" -> "oa_intake"). The supervisor still sees the underscore name in the tool schema. (discovered: 2026-03-02, component: service-migration)
- **sdk_query() as async generator with sync Agent inside**: Even though Strands `agent()` is sync, the wrapper is `async def ... -> AsyncGenerator` with `yield`. This preserves the async generator interface for callers without needing `stream_async()`. Works because Python allows `yield` in `async def`. (discovered: 2026-03-02, component: service-migration)

### patterns_to_avoid

- **Module-level Agent with frozen prompt**: `agent = Agent(system_prompt="frozen")` at module level means prompt changes require container restart. Use per-request construction instead. (reason: no hot-reload)
- **Per-request BedrockModel**: Creating `BedrockModel()` per request adds ~50-200ms for boto3 client creation + TLS. Share the model object. (reason: unnecessary latency)
- **Shared agent for concurrent requests**: Default THROW lock mode rejects concurrent calls. Even REENTRANT mode shares conversation history. Use per-request Agent construction. (reason: thread safety, context pollution)
- **system_prompt setter in concurrent context**: `agent.system_prompt = "..."` is not thread-safe. Race condition between setting prompt and invoking agent. (reason: data race)
- **Calling async sdk_query() from sync @tool without bridge**: Strands `@tool` functions are sync. `sdk_query()` is an async generator. You can't just `await` inside a sync tool. Must use `asyncio.run()` or collect results in an async wrapper. (reason: RuntimeError — event loop mismatch)
- **Duplicating skill definitions in Strands**: Don't redefine skills that already exist in `eagle-plugin/`. Use the bridge pattern to call them via `sdk_query_single_skill()`. (reason: drift between two sources of truth)

### common_issues

- **Multi-agent session persistence**: Swarm and Graph don't persist per-agent session history (GitHub #867). Workaround: implement custom session tracking. (component: multi-agent)
- **Temporary system_prompt override lost after invocation**: Agent resets to original prompt after `agent(prompt, system_prompt="temp")`. See GitHub #344. (component: agent-core)
- **Tool docstring required for schema**: `@tool` functions without docstrings get empty descriptions and no parameter docs. Always write Google-style docstrings. (component: tools)
- **`strands.__version__` does not exist**: Unlike most packages, `import strands; strands.__version__` raises `AttributeError`. Use `pip show strands-agents` to check version. (component: installation)
- **`max_parallel_tools` is not a valid Agent parameter in v1.28.0**: Despite appearing in some docs/examples, it raises `TypeError: Agent.__init__() got an unexpected keyword argument`. Use `tool_executor=ConcurrentToolExecutor()` from `strands.tools.executors` instead. (component: agent-constructor, discovered: 2026-03-02)
- **Windows cp1252 encoding breaks on Unicode in test output**: `print()` with Unicode chars (arrows, emojis) on Windows raises `UnicodeEncodeError: 'charmap'`. Use `PYTHONIOENCODING=utf-8` env var or `.encode('ascii', 'replace').decode()` for test output. (component: testing, discovered: 2026-03-02)

### tips

- Use `callback_handler=None` for headless/server-side agents (no stdout noise)
- `tool_context.invocation_state` is a shared dict across all tools in a single invocation — use for cross-tool state
- `agent.tool.{tool_name}()` for programmatic direct tool calls (bypasses LLM)
- `load_tools_from_directory` + `ToolWatcher` for dev-mode hot-reload of tool code
- Start migration with agents-as-tools pattern, graduate to Swarm/Graph as workflows mature. Swarm is wrong for EAGLE — no return from handoff means no supervisor synthesis
- Use `tool_executor=ConcurrentToolExecutor()` from `strands.tools.executors` on the supervisor to run subagent @tool calls concurrently — cuts wall-clock time from (supervisor + N tools) to (supervisor + slowest tool). NOTE: `max_parallel_tools` does NOT exist in v1.28.0 despite being in some docs
- Swarm latency is additive per handoff and includes SharedContext serialization overhead. Graph latency is depth-of-DAG with parallel branches overlapping. Agents-as-tools is simplest and fastest for supervisor-routes-to-specialist patterns
- EAGLE's `eagle-plugin/` SKILL.md format is 95% compatible with AgentSkills.io — add `license`, `allowed-tools`, `metadata` fields
- Bridge pattern is the lowest-risk migration path: wrap `sdk_query()` and `sdk_query_single_skill()` as `@tool` functions, compose into a Strands orchestrator. Zero changes to `eagle-plugin/`, zero changes to existing backend
- The two backend entry points for bridge wrapping: `sdk_query()` (full supervisor + subagents) at `server/app/sdk_agentic_service.py:300` and `sdk_query_single_skill()` (single skill, no supervisor) at line 375
- Bridge tools can be migrated one-by-one from "calls Claude SDK" to "native Strands Agent" without changing the outer orchestrator's interface
- For the async→sync bridge in `@tool`, collect `ResultMessage.result` from the async generator — that's the final answer text
- `str(result)` on Strands `AgentResult` gives the full text response — no need for `.result` attribute or TraceCollector
- Version check: use `pip show strands-agents` not `strands.__version__` (the latter raises AttributeError)
- POC tests can reuse `SKILL_CONSTANTS` dict directly — same loader works for both SDKs, proven in `test_strands_poc.py`
- Official Strands samples repo has runnable notebooks for each multi-agent pattern: https://github.com/strands-agents/samples/tree/main/01-tutorials/02-multi-agent-systems
- Use `response.text` (not just `str(response)`) to extract answer from inner agents in agents-as-tools pattern — confirmed in official Teacher's Assistant example
- Swarm has built-in ping-pong detection: `repetitive_handoff_detection_window` + `repetitive_handoff_min_unique_agents` prevent infinite handoff loops
- Graph supports conditional edges via Python functions that inspect `GraphState` — enables skip-node logic without LLM calls
- For parallel tool execution in v1.28.0, use `tool_executor=ConcurrentToolExecutor()` from `strands.tools.executors`. `max_parallel_tools` is NOT a valid parameter despite appearing in some documentation
- `ConcurrentToolExecutor()` and `SequentialToolExecutor()` are zero-arg constructors — just instantiate and pass to Agent. Available at `from strands.tools.executors import ConcurrentToolExecutor`
- Multi-agent supervisor+subagent latency on Nova Pro: ~18-24s per test (1 supervisor call + 1 subagent call). Plan for ~5-10s per LLM call in latency estimates
- Always use ASCII in test output on Windows — `PYTHONIOENCODING=utf-8` helps but `print()` with Unicode arrows/emojis still fails on cp1252 terminals
