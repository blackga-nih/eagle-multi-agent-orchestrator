---
description: "Quick-reference cheat sheet for Strands Agents SDK with copy-pasteable code samples"
allowed-tools: Read
---

# Strands Agents SDK Cheat Sheet

> Quick-reference for `strands-agents` with code samples from actual EAGLE project usage.

---

## 1. Quick Start — Minimal Agent

```python
from strands import Agent, tool
from strands.models import BedrockModel

model = BedrockModel(
    model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0",
    region_name="us-east-1",
)

agent = Agent(
    model=model,
    system_prompt="You are a helpful assistant.",
    tools=[],
    callback_handler=None,
)

result = str(agent("Hello!"))
print(result)
```

---

## 2. @tool Decorator — Three Patterns

### Service Tool (wraps TOOL_DISPATCH handler)

```python
@tool(name="my_service_tool")
def my_service_tool(params: str) -> str:
    """Description the model sees. Pass JSON with 'operation' and fields."""
    parsed = json.loads(params) if isinstance(params, str) else params
    result = handler(parsed, tenant_id)
    return json.dumps(result, indent=2, default=str)
```

### Subagent Tool (creates fresh Agent per call)

```python
@tool(name="specialist_agent")
def specialist_tool(query: str) -> str:
    """Specialist agent for X. Delegates complex X queries."""
    agent = Agent(model=_model, system_prompt=skill_prompt, callback_handler=None)
    return str(agent(query))
```

### Utility Tool (lightweight, no AWS)

```python
@tool(name="list_skills")
def list_skills_tool(category: str = "") -> str:
    """List available skills, agents, and data files."""
    return json.dumps({"skills": [...], "agents": [...]})
```

---

## 3. BedrockModel — Shared Singleton

```python
from strands.models import BedrockModel

# Create once at module level
_model = BedrockModel(
    model_id="us.anthropic.claude-sonnet-4-6",  # NCI account
    region_name="us-east-1",
)

# Reuse across all Agent instances
agent1 = Agent(model=_model, system_prompt="...", tools=[...])
agent2 = Agent(model=_model, system_prompt="...", tools=[...])
```

---

## 4. Adding a Service Tool — 3 Steps

### Step 1: Handler in `agentic_service.py`

```python
def _exec_my_tool(params: dict, tenant_id: str, session_id: str = None) -> dict:
    operation = params.get("operation", "default")
    return {"status": "success", "data": {...}}
```

### Step 2: Register in TOOL_DISPATCH

```python
TOOL_DISPATCH = {
    ...,
    "my_tool": _exec_my_tool,
}
# If needs session: TOOLS_NEEDING_SESSION.add("my_tool")
```

### Step 3: Add to _SERVICE_TOOL_DEFS

```python
_SERVICE_TOOL_DEFS = {
    ...,
    "my_tool": "Description. Pass JSON with 'operation' and fields.",
}
```

Done. `_build_service_tools()` auto-wraps it.

---

## 5. Adding a Subagent — 2 Steps

### Step 1: Create `eagle-plugin/agents/my-agent/agent.md`

```yaml
---
name: my-agent
description: "One-line description for supervisor routing"
triggers: ["keyword1", "keyword2"]
tools: []
model: null
---

# System prompt body for the subagent...
```

### Step 2: Register in `eagle-plugin/plugin.json`

```json
{ "agents": [..., "my-agent"] }
```

Done. Auto-discovery handles the rest.

---

## 6. Supervisor Assembly

```python
skill_tools = build_skill_tools(tier, skill_names, tenant_id, user_id, workspace_id, rq, loop)
service_tools = _build_service_tools(tenant_id, user_id, session_id, pkg_ctx, rq, loop)
system_prompt = build_supervisor_prompt(tenant_id, user_id, tier, agent_names, workspace_id)

supervisor = Agent(
    model=_model,
    system_prompt=system_prompt,
    tools=skill_tools + service_tools,
    callback_handler=None,
)
result = supervisor(prompt)
```

---

## 7. SSE Streaming Bridge (Sync -> Async)

```python
# Inside @tool function (sync context):
if result_queue and loop:
    loop.call_soon_threadsafe(
        result_queue.put_nowait,
        {"type": "tool_result", "name": tool_name, "result": data},
    )

# In streaming route (async context):
while not result_queue.empty():
    event = result_queue.get_nowait()
    yield f"data: {json.dumps(event)}\n\n"
```

---

## 8. Verification Commands

```bash
# Import check
python -c "from strands import Agent, tool; print('OK')"

# Tool dispatch check
cd server && python -c "
from app.agentic_service import TOOL_DISPATCH
print(list(TOOL_DISPATCH.keys()))
"

# Plugin discovery check
cd server && python -c "
from eagle_skill_constants import AGENTS, SKILLS
print(f'Agents: {list(AGENTS.keys())}')
print(f'Skills: {list(SKILLS.keys())}')
"

# Registry check
cd server && python -c "
from app.strands_agentic_service import SKILL_AGENT_REGISTRY
print(f'Registry: {list(SKILL_AGENT_REGISTRY.keys())}')
"

# Lint
cd server && ruff check app/ --select E,F,W
```

---

## 9. Key Rules

| Rule | Detail |
|------|--------|
| @tool returns `str` | NOT dict — use `json.dumps()` |
| Tool names use underscores | `my_tool` not `my-tool` |
| Docstring = description | Model uses docstring for routing |
| Type hints = schema | Model uses hints for parameters |
| Fresh Agent per subagent call | Isolated context, no state leaks |
| Shared BedrockModel singleton | `_model` created once, reused everywhere |
| result_queue is optional | Pass `None` for non-streaming contexts |
| Handler returns `dict` | `{"status": "success", "data": {...}}` or `{"error": "..."}` |

---

## 10. Documentation Links

| Resource | URL |
|----------|-----|
| GitHub | https://github.com/strands-agents/sdk-python |
| Quickstart | https://strandsagents.com/latest/user-guide/quickstart/ |
| @tool docs | https://strandsagents.com/latest/user-guide/concepts/tools/custom-tools/ |
| Agent class | https://strandsagents.com/latest/user-guide/concepts/agents/ |
| BedrockModel | https://strandsagents.com/latest/user-guide/concepts/model-providers/amazon-bedrock/ |
| Multi-agent | https://strandsagents.com/latest/user-guide/concepts/multi-agent-systems/ |
| Streaming | https://strandsagents.com/latest/user-guide/concepts/streaming/ |

---

## 11. Key Source Files

| File | Purpose |
|------|---------|
| `server/app/strands_agentic_service.py` | @tool factories, Agent instantiation, supervisor |
| `server/app/agentic_service.py` | TOOL_DISPATCH, handler implementations |
| `server/eagle_skill_constants.py` | Plugin auto-discovery |
| `eagle-plugin/plugin.json` | Active agents/skills manifest |
| `server/app/streaming_routes.py` | SSE endpoint |
| `server/app/stream_protocol.py` | SSE event format |
