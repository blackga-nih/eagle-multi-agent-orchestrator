---
user-invocable: false
type: expert-file
file-type: expertise
domain: strands
last_updated: "2026-03-10"
strands_sdk: "strands-agents (latest)"
tags: [strands-agents, bedrock, tool, agent, subagent, streaming, multi-tenant, supervisor, skill-registry, add-tool, plugin]
---

# Strands Agents SDK Expertise

> Complete mental model for `strands-agents` — the Python SDK powering the production EAGLE agentic system via AWS Bedrock.

---

## Part 1: SDK Overview & Installation

### Packages

| Package | Purpose |
|---------|---------|
| `strands-agents` | Core SDK — Agent, @tool decorator |
| `strands-agents-bedrock` | BedrockModel provider (boto3-native converse) |

### Install

```bash
pip install strands-agents strands-agents-bedrock
```

### Key Imports

```python
from strands import Agent, tool
from strands.models import BedrockModel
```

### Documentation Links

| Resource | URL |
|----------|-----|
| GitHub repo | https://github.com/strands-agents/sdk-python |
| Quickstart | https://strandsagents.com/latest/user-guide/quickstart/ |
| @tool decorator | https://strandsagents.com/latest/user-guide/concepts/tools/custom-tools/ |
| Agent class | https://strandsagents.com/latest/user-guide/concepts/agents/ |
| BedrockModel | https://strandsagents.com/latest/user-guide/concepts/model-providers/amazon-bedrock/ |
| Multi-agent systems | https://strandsagents.com/latest/user-guide/concepts/multi-agent-systems/ |
| Streaming | https://strandsagents.com/latest/user-guide/concepts/streaming/ |
| Callback handlers | https://strandsagents.com/latest/user-guide/concepts/agents/callback-handlers/ |
| PyPI (core) | https://pypi.org/project/strands-agents/ |
| PyPI (bedrock) | https://pypi.org/project/strands-agents-bedrock/ |

### Backend

- **Bedrock**: boto3-native `converse` API — no credential bridging, no subprocess
- **Model selection**: `BedrockModel(model_id="us.anthropic.claude-sonnet-4-6", region_name="us-east-1")`
- **SSO/IAM**: Uses standard boto3 credential chain (SSO profile, IAM role, env vars)

### Key Differences from Claude Agent SDK

| Concept | Claude Agent SDK | Strands Agents SDK |
|---------|-----------------|-------------------|
| Runtime | Subprocess (CLI) | In-process (boto3 `converse`) |
| Import | `from claude_agent_sdk import query` | `from strands import Agent, tool` |
| Model | `ClaudeAgentOptions(model="haiku")` | `BedrockModel(model_id="us.anthropic.claude-haiku-4-5-...")` |
| Tool | `@tool(name, desc, InputDataclass)` | `@tool(name=name)` on a function |
| Subagent | `AgentDefinition` + `Task` tool | `@tool`-wrapped `Agent()` (fresh per-call) |
| Session | `resume=session_id` | Managed externally (EAGLE DynamoDB) |
| Credentials | `env={"CLAUDE_CODE_USE_BEDROCK": "1"}` | Native boto3 SSO/IAM — no bridging |
| Execution | Async generator (`async for msg in query(...)`) | Sync call (`agent(prompt)` returns str) |

---

## Part 2: Agent Class

### Constructor

```python
from strands import Agent
from strands.models import BedrockModel

_model = BedrockModel(
    model_id="us.anthropic.claude-sonnet-4-6",
    region_name="us-east-1",
)

agent = Agent(
    model=_model,
    system_prompt="You are a helpful assistant.",
    tools=[tool_fn_1, tool_fn_2],
    callback_handler=None,
)
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `model` | `BedrockModel` | Shared model singleton |
| `system_prompt` | `str` | Agent behavior instructions |
| `tools` | `list[callable]` | `@tool`-decorated functions |
| `callback_handler` | `callable \| None` | Streaming callback (None = no streaming) |

### Invocation

```python
result = agent("What is 2+2?")  # Sync call — returns str
result = str(agent(prompt))     # Cast to str for reliable output
```

### EAGLE Model Selection

```python
_NCI_ACCOUNT = "695681773636"
_SONNET = "us.anthropic.claude-sonnet-4-6"
_HAIKU = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

def _default_model() -> str:
    env_model = os.getenv("EAGLE_BEDROCK_MODEL_ID")
    if env_model:
        return env_model
    try:
        import boto3
        account = boto3.client("sts").get_caller_identity()["Account"]
        return _SONNET if account == _NCI_ACCOUNT else _HAIKU
    except Exception:
        return _HAIKU
```

---

## Part 3: @tool Decorator

### Basic Pattern

```python
from strands import tool

@tool(name="my_tool")
def my_tool(query: str) -> str:
    """Description the model sees when deciding to call this tool.

    Args:
        query: What to search for
    """
    result = do_something(query)
    return json.dumps(result)
```

### Rules

- `name` keyword arg sets the tool name the model sees
- **Docstring** = tool description (model uses this for routing)
- **Type hints** = input schema (model uses these for parameters)
- **Return type**: `str` (JSON-serialized) — NOT dict like Claude SDK
- Hyphens in names must be replaced: `safe_name = skill_name.replace("-", "_")`

### Replacing Docstrings After Creation

```python
@tool(name=safe_name)
def subagent_tool(query: str) -> str:
    """Placeholder docstring replaced below."""
    ...

subagent_tool.__doc__ = f"{description}\n\nArgs:\n    query: ..."
```

---

## Part 4: Three Tool Types in EAGLE

### Overview

| Type | Factory | Registration | Use Case |
|------|---------|-------------|----------|
| **Subagent** | `_make_subagent_tool()` | `build_skill_tools()` auto from `plugin.json` | Specialist agents (intake, legal, etc.) |
| **Service** | `_make_service_tool()` | `_build_service_tools()` auto from `_SERVICE_TOOL_DEFS` | AWS-backed ops (S3, DynamoDB, docs) |
| **Utility** | `_make_*_tool()` factories | Appended in `_build_service_tools()` | Progressive disclosure, state push |

### 4a: Subagent Tools

Each subagent is a `@tool`-wrapped function that creates a **fresh Agent per call**:

```python
def _make_subagent_tool(skill_name, description, prompt_body, result_queue=None, loop=None):
    safe_name = skill_name.replace("-", "_")

    @tool(name=safe_name)
    def subagent_tool(query: str) -> str:
        """Placeholder docstring replaced below."""
        agent = Agent(
            model=_model,              # Shared BedrockModel singleton
            system_prompt=prompt_body,  # Skill content as system prompt
            callback_handler=None,
        )
        raw = str(agent(query))

        # Emit tool_result for frontend observability
        if result_queue and loop:
            truncated = raw[:3000] + "..." if len(raw) > 3000 else raw
            loop.call_soon_threadsafe(
                result_queue.put_nowait,
                {"type": "tool_result", "name": safe_name, "result": {...}},
            )
        return raw

    subagent_tool.__doc__ = f"{description}\n\nArgs:\n    query: ..."
    return subagent_tool
```

**Key design**: Fresh Agent per call = isolated context windows. No state leaks between calls.

### 4b: Service Tools

Wrap `TOOL_DISPATCH` handler functions from `agentic_service.py`:

```python
def _make_service_tool(tool_name, description, tenant_id, user_id, session_id,
                       package_context=None, result_queue=None, loop=None):
    from .agentic_service import TOOL_DISPATCH, TOOLS_NEEDING_SESSION
    handler = TOOL_DISPATCH.get(tool_name)

    scoped_session_id = session_id
    if not scoped_session_id or "#" not in scoped_session_id:
        scoped_session_id = f"{tenant_id}#advanced#{user_id}#{session_id or ''}"

    @tool(name=tool_name)
    def service_tool(params: str) -> str:
        """Placeholder docstring replaced below."""
        parsed = json.loads(params) if isinstance(params, str) else params
        if tool_name in TOOLS_NEEDING_SESSION:
            result = handler(parsed, tenant_id, scoped_session_id)
        else:
            result = handler(parsed, tenant_id)
        return json.dumps(result, indent=2, default=str)

    service_tool.__doc__ = f"{description}\n\nArgs:\n    params: JSON string..."
    return service_tool
```

### 4c: Utility / Progressive Disclosure Tools

Lightweight tools that don't call AWS:

```python
def _make_list_skills_tool(result_queue=None, loop=None):
    @tool(name="list_skills")
    def list_skills_tool(category: str = "") -> str:
        """List available skills, agents, and data files."""
        return json.dumps({...})
    return list_skills_tool

def _make_load_skill_tool(result_queue=None, loop=None):
    @tool(name="load_skill")
    def load_skill_tool(name: str) -> str:
        """Load full skill/agent instructions by name."""
        from eagle_skill_constants import SKILL_CONSTANTS
        return SKILL_CONSTANTS.get(name, "Not found")
    return load_skill_tool
```

---

## Part 5: Plugin System & Auto-Discovery

### File Locations

| Type | Path Pattern | Frontmatter File |
|------|-------------|-----------------|
| Agent | `eagle-plugin/agents/{name}/agent.md` | YAML frontmatter + system prompt body |
| Skill | `eagle-plugin/skills/{name}/SKILL.md` | YAML frontmatter + workflow body |
| Manifest | `eagle-plugin/plugin.json` | Active agents/skills list |

### YAML Frontmatter Format

```yaml
---
name: oa-intake
description: "Internal knowledge base for the strands expert. Consumed by question, plan, maintenance, and self-improve commands. Never edit directly — run /experts:strands:self-improve to update."
triggers:
  - "purchase"
  - "acquisition"
tools: []
model: null
---

# Skill content (markdown body)
...
```

### Auto-Discovery Pipeline

```
eagle_skill_constants.py
  -> _discover(_AGENTS_DIR, "agent.md")  -> AGENTS dict
  -> _discover(_SKILLS_DIR, "SKILL.md")  -> SKILLS dict
  -> PLUGIN_CONTENTS = {**AGENTS, **SKILLS}

strands_agentic_service.py
  -> _load_plugin_config()  -> reads plugin.json (+ DynamoDB overlay)
  -> _build_registry()      -> filters by plugin.json active list
  -> SKILL_AGENT_REGISTRY   -> runtime registry for build_skill_tools()
```

### plugin.json Structure

```json
{
  "agent": "supervisor",
  "agents": [
    "legal-counsel", "market-intelligence", "tech-translator",
    "public-interest", "policy-supervisor", "policy-librarian", "policy-analyst"
  ],
  "skills": [
    "oa-intake", "document-generator", "compliance",
    "knowledge-retrieval", "tech-review", "ingest-document", "admin-manager"
  ]
}
```

### 4-Layer Prompt Resolution

When building subagent tools, prompts resolve through:

1. **Workspace override** (`wspc_store.resolve_skill()`) — tenant/user customization
2. **DynamoDB PLUGIN# canonical** (`plugin_store`) — centralized override
3. **Bundled files** (`PLUGIN_CONTENTS`) — `eagle-plugin/` files on disk
4. **Tenant custom SKILL# items** (`skill_store.list_active_skills()`) — user-created

---

## Part 6: Tool Registration & Dispatch

### TOOL_DISPATCH (agentic_service.py ~line 2548)

Maps tool names to handler functions:

```python
TOOL_DISPATCH = {
    "s3_document_ops": _exec_s3_document_ops,
    "dynamodb_intake": _exec_dynamodb_intake,
    "cloudwatch_logs": _exec_cloudwatch_logs,
    "search_far": _exec_search_far,
    "create_document": _exec_create_document,
    "get_intake_status": _exec_get_intake_status,
    "intake_workflow": _exec_intake_workflow,
    "query_compliance_matrix": _exec_query_compliance_matrix,
    "knowledge_search": exec_knowledge_search,
    "knowledge_fetch": exec_knowledge_fetch,
    "manage_skills": _exec_manage_skills,
    "manage_prompts": _exec_manage_prompts,
    "manage_templates": _exec_manage_templates,
}

TOOLS_NEEDING_SESSION = {"s3_document_ops", "create_document", "get_intake_status"}
```

### Handler Signature

```python
def _exec_my_tool(params: dict, tenant_id: str, session_id: str = None) -> dict:
    """Handler receives parsed params + tenant context."""
    operation = params.get("operation", "default")
    # ... business logic ...
    return {"status": "success", "data": {...}}
```

### _SERVICE_TOOL_DEFS (strands_agentic_service.py ~line 1256)

Maps tool names to descriptions for the `@tool` docstring:

```python
_SERVICE_TOOL_DEFS = {
    "s3_document_ops": "Read, write, or list documents in S3...",
    "dynamodb_intake": "Create, read, update, list intake records...",
    "create_document": "Generate acquisition documents (SOW, IGCE, ...)...",
    "get_intake_status": "Get current intake package status...",
    "intake_workflow": "Manage acquisition intake workflow...",
    "search_far": "Search FAR and DFARS for clauses...",
    "knowledge_search": "Search acquisition knowledge base metadata...",
    "knowledge_fetch": "Fetch full knowledge document content from S3...",
    "manage_skills": "Create, list, update, delete custom skills...",
    "manage_prompts": "List, view, set agent prompt overrides...",
    "manage_templates": "List, view, set document templates...",
}
```

### EAGLE_TOOLS (observability schemas, ~line 345)

Anthropic-format tool schemas for `/tools` health endpoint. NOT used by the agent — purely for introspection.

---

## Part 7: Supervisor Assembly

### build_supervisor_prompt()

Builds the supervisor system prompt with:
- Tenant/user/tier header
- Base supervisor prompt (from 4-layer resolution)
- Active specialist list with descriptions
- Progressive disclosure instructions (4 layers)

### Tool Assembly Pipeline

```python
# In sdk_query_streaming():
skill_tools = build_skill_tools(tier, skill_names, tenant_id, user_id, workspace_id, result_queue, loop)
service_tools = _build_service_tools(tenant_id, user_id, session_id, package_context, result_queue, loop)
system_prompt = build_supervisor_prompt(tenant_id, user_id, tier, agent_names, workspace_id)

supervisor = Agent(
    model=_model,
    system_prompt=system_prompt,
    tools=skill_tools + service_tools,  # All @tool functions
    callback_handler=None,
)

result = supervisor(prompt)  # Strands handles the agentic loop
```

### Progressive Disclosure Layers

1. **System prompt hints** — Short descriptions already in supervisor prompt
2. **list_skills()** — Discover available skills/agents/data with descriptions
3. **load_skill(name)** — Read full skill instructions/workflows
4. **load_data(name, section?)** — Fetch reference data (thresholds, vehicles, doc rules)

---

## Part 8: Streaming & SSE Integration

### Sync-to-Async Bridge

Strands Agent runs synchronously. EAGLE bridges to async SSE via `asyncio.Queue`:

```python
result_queue = asyncio.Queue()
loop = asyncio.get_event_loop()

# Inside @tool (sync context):
loop.call_soon_threadsafe(
    result_queue.put_nowait,
    {"type": "tool_result", "name": tool_name, "result": data},
)

# In streaming_routes.py (async context):
while not result_queue.empty():
    event = result_queue.get_nowait()
    yield f"data: {json.dumps(event)}\n\n"
```

### SSE Event Types

| Event Type | Source | Content |
|-----------|--------|---------|
| `text` | Supervisor output | Model text response |
| `tool_use` | Tool call | Tool name + input |
| `tool_result` | Tool completion | Tool name + result (truncated) |
| `metadata` | State changes | document_ready, checklist_update, compliance_alert |
| `complete` | End of response | Final status |
| `error` | Failure | Error message |

---

## Part 9: Adding New Tools (Step-by-Step)

### Service Tool Checklist

1. Write handler `_exec_{name}()` in `server/app/agentic_service.py`
2. Add to `TOOL_DISPATCH` dict (~line 2548)
3. Add to `TOOLS_NEEDING_SESSION` if needs session scoping
4. Add to `_SERVICE_TOOL_DEFS` in `server/app/strands_agentic_service.py` (~line 1256)
5. (Optional) Add schema to `EAGLE_TOOLS` list (~line 345)

### Subagent Tool Checklist

1. Create `eagle-plugin/agents/{name}/agent.md` or `eagle-plugin/skills/{name}/SKILL.md`
2. Add YAML frontmatter (name, description, triggers, tools, model)
3. Register in `eagle-plugin/plugin.json` agents/skills array

### Utility Tool Checklist

1. Write `_make_{name}_tool()` factory in `strands_agentic_service.py`
2. Append `tools.append(_make_{name}_tool(...))` in `_build_service_tools()`

### Validation Commands

```bash
# Lint
cd server && ruff check app/ --select E,F,W

# Verify tool discovery
cd server && python -c "
from app.strands_agentic_service import _build_service_tools, build_skill_tools
print('Service tools:', len(_build_service_tools('test', 'test', None)))
print('Skill tools:', len(build_skill_tools()))
"

# Verify dispatch (service tools)
cd server && python -c "
from app.agentic_service import TOOL_DISPATCH
print('Tools:', list(TOOL_DISPATCH.keys()))
"
```

---

## Learnings

### patterns_that_work

- **Fresh Agent per subagent call**: Each `_make_subagent_tool()` invocation creates a new `Agent()` — isolated context, no state leaks between calls. (discovered: 2026-03-10)
- **Shared BedrockModel singleton**: `_model` is created once at module level and reused across all Agent instances — avoids per-request boto3 overhead. (discovered: 2026-03-10)
- **result_queue + loop.call_soon_threadsafe**: Bridge sync Strands agent to async SSE streaming. Tool results pushed from sync @tool context to async streaming context. (discovered: 2026-03-10)
- **Truncate skill prompts at 4000 chars**: `_truncate_skill(content, MAX_SKILL_PROMPT_CHARS)` prevents context overflow in subagents. (discovered: 2026-03-10)
- **Hyphen-to-underscore in tool names**: `safe_name = skill_name.replace("-", "_")` — Strands @tool names must be valid Python identifiers. (discovered: 2026-03-10)
- **4-layer prompt resolution**: workspace → DynamoDB → bundled → user-created. Non-fatal at each layer (try/except, fallthrough). (discovered: 2026-03-10)
- **_SERVICE_TOOL_DEFS auto-registration**: Adding a name+description to `_SERVICE_TOOL_DEFS` is all that's needed — `_build_service_tools()` wraps it automatically. (discovered: 2026-03-10)

### patterns_to_avoid

- **Returning dict from @tool**: Strands @tool must return `str`, not `dict`. Use `json.dumps()`. Claude SDK returns `{"content": [...]}` — different pattern. (reason: TypeError at runtime)
- **Using hyphens in @tool name**: `@tool(name="my-tool")` fails. Must use underscores: `@tool(name="my_tool")`. (reason: Strands validation)
- **Forgetting to add to TOOL_DISPATCH**: If you write a handler but don't register in `TOOL_DISPATCH`, `_make_service_tool()` will raise `ValueError`. (reason: hard crash on tool assembly)
- **Skipping _SERVICE_TOOL_DEFS**: Even if `TOOL_DISPATCH` has the handler, the supervisor won't see the tool without a `_SERVICE_TOOL_DEFS` entry. (reason: tool invisible to model)

### common_issues

- **Model ID mismatch**: NCI account uses `us.anthropic.claude-sonnet-4-6`, personal accounts use `us.anthropic.claude-haiku-4-5-...`. If you get model access errors, check `_default_model()` logic. (component: model-selection)
- **Scoped session ID format**: Must be `{tenant}#{tier}#{user}#{session}`. If `#` not in session_id, `_make_service_tool` auto-generates composite format. (component: service-tools)
- **Plugin auto-discovery fails silently**: If `agent.md` or `SKILL.md` has bad YAML frontmatter, the entry is skipped without error. Check `SKILL_AGENT_REGISTRY` length. (component: plugin-system)

### tips

- `EAGLE_BEDROCK_MODEL_ID` env var overrides all model selection logic
- Supervisor `tools=skill_tools + service_tools` — order doesn't matter
- Subagent tool descriptions drive supervisor routing — make them specific about WHEN to use
- `result_queue` is optional in all factories — pass `None` for non-streaming contexts
- Test tool registration without running the agent: `python -c "from app.strands_agentic_service import SKILL_AGENT_REGISTRY; print(list(SKILL_AGENT_REGISTRY.keys()))"`
- The `callback_handler=None` suppresses Strands' built-in stdout printing — EAGLE uses queue-based SSE instead
