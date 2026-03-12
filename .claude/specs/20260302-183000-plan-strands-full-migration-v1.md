# Strands Full Migration Plan: Claude Agent SDK → Strands Agents SDK

## Overview

- **Integration Type**: Full Migration (Claude Agent SDK removal)
- **Constraint**: No Claude/Anthropic models — use Llama 4, Nova Pro, DeepSeek R1 via Bedrock
- **Pattern**: Agents-as-Tools with `tool_executor=ConcurrentToolExecutor()`
- **Proven**: Single-skill POC passes 3/3 models (`test_strands_poc.py`)

### Files Modified

| File | Change |
|------|--------|
| `server/app/sdk_agentic_service.py` | Rewrite internals — same function signatures, Strands under the hood |
| `server/app/streaming_routes.py` | Adapt message consumption (Strands result format) |
| `server/app/main.py` | Adapt message consumption (same pattern as streaming_routes) |
| `server/requirements.txt` | Remove `claude-agent-sdk>=0.1.19`, keep `strands-agents>=1.0.0` |

### New Files

| File | Purpose |
|------|---------|
| `server/tests/test_strands_multi_agent.py` | Phase 2: Multi-agent supervisor test |
| `server/tests/test_strands_eval.py` | Phase 4: Full eval suite on Strands |

### Files Unchanged (SDK-agnostic)

| File | Reason |
|------|--------|
| `eagle_skill_constants.py` | Pure file discovery — proven with both SDKs |
| `app/plugin_store.py` | DynamoDB CRUD — no SDK coupling |
| `app/wspc_store.py` | Workspace overrides — no SDK coupling |
| `app/skill_store.py` | Tenant custom skills — no SDK coupling |
| `app/stream_protocol.py` | SSE event format — no SDK coupling |
| `app/cognito_auth.py` | JWT auth — no SDK coupling |
| `app/session_store.py` | DynamoDB sessions — no SDK coupling |
| `eagle-plugin/` | Agent/skill definitions — format is SDK-agnostic |

---

## Phase 1: Multi-Agent Supervisor POC Test (NEW)

**Goal**: Prove the agents-as-tools pattern works with 3+ subagents on non-Claude models.

**File**: `server/tests/test_strands_multi_agent.py`

**Design**:

```python
from strands import Agent, tool
from strands.models import BedrockModel
from eagle_skill_constants import SKILL_CONSTANTS

MODEL_ID = os.environ.get("STRANDS_MODEL_ID", "us.amazon.nova-pro-v1:0")
_model = BedrockModel(model_id=MODEL_ID, region_name="us-east-1")

@tool(name="oa_intake")
def oa_intake(query: str) -> str:
    """Handle acquisition intake requests and micro-purchases.

    Args:
        query: The acquisition intake question
    """
    prompt = SKILL_CONSTANTS.get("oa-intake", "You are an intake specialist.")
    agent = Agent(model=_model, system_prompt=prompt, callback_handler=None)
    return str(agent(query))

@tool(name="legal_counsel")
def legal_counsel(query: str) -> str:
    """Assess FAR compliance and legal risks for acquisitions.

    Args:
        query: The legal question about an acquisition
    """
    prompt = SKILL_CONSTANTS.get("legal-counsel", "You are a legal specialist.")
    agent = Agent(model=_model, system_prompt=prompt, callback_handler=None)
    return str(agent(query))

@tool(name="market_intelligence")
def market_intelligence(query: str) -> str:
    """Research market conditions, vendors, and pricing data.

    Args:
        query: The market research question
    """
    prompt = SKILL_CONSTANTS.get("market-intelligence", "You are a market analyst.")
    agent = Agent(model=_model, system_prompt=prompt, callback_handler=None)
    return str(agent(query))

def test_strands_supervisor_routes_to_subagent():
    """Supervisor delegates to oa_intake for a micro-purchase question."""
    supervisor = Agent(
        model=_model,
        system_prompt="You are the EAGLE supervisor. Delegate to specialists. "
                      "Use oa_intake for intake questions, legal_counsel for legal, "
                      "market_intelligence for market research.",
        tools=[oa_intake, legal_counsel, market_intelligence],
        callback_handler=None,
    )
    result = supervisor("I need to buy $13,800 in lab supplies. What's the fastest way?")
    result_text = str(result).lower()
    # Should route to oa_intake and mention micro-purchase
    assert any(w in result_text for w in ["micro-purchase", "micro purchase", "purchase card", "$15,000"])
```

**Pass criteria**: Supervisor routes to at least one subagent, response contains domain-relevant content.

**Validation**:
```bash
AWS_PROFILE=eagle python -m pytest tests/test_strands_multi_agent.py -v -s
```

---

## Phase 2: `strands_agentic_service.py` — Drop-In Replacement

**Goal**: Replace Claude SDK internals while keeping the EXACT same function signatures.

**Key constraint**: `sdk_query()` and `sdk_query_single_skill()` are async generators that yield SDK message objects. Callers (`main.py`, `streaming_routes.py`) consume these via `async for`. We must preserve this interface.

### 2a. Module-Level Shared Model

```python
# strands_agentic_service.py (top of file)

from strands import Agent, tool
from strands.models import BedrockModel

# Shared model — created once, reused per-request
_model = BedrockModel(
    model_id=os.getenv("EAGLE_BEDROCK_MODEL_ID", "us.amazon.nova-pro-v1:0"),
    region_name=os.getenv("AWS_REGION", "us-east-1"),
)
```

**Replaces**: `_get_bedrock_env()` + CLI subprocess. No more credential bridging needed — boto3 handles SSO/IAM natively.

### 2b. Replace `build_skill_agents()` → `build_skill_tools()`

**Current** (returns `dict[str, AgentDefinition]`):
```python
agents[name] = AgentDefinition(
    description=meta["description"],
    prompt=_truncate_skill(prompt_body),
    tools=meta["tools"] or tier_tools,
    model=meta.get("model") or agent_model,
)
```

**New** (returns `list[@tool]`):
```python
def build_skill_tools(tier, skill_names, tenant_id, user_id, workspace_id) -> list:
    """Build @tool-wrapped subagent functions from skill registry."""
    tools = []
    for name, meta in SKILL_AGENT_REGISTRY.items():
        if skill_names and name not in skill_names:
            continue

        # Same 4-layer prompt resolution (unchanged)
        prompt_body = _resolve_skill_prompt(name, meta, tenant_id, user_id, workspace_id)
        if not prompt_body:
            continue

        # Create @tool-wrapped subagent
        tools.append(_make_subagent_tool(
            skill_name=name,
            description=meta["description"],
            prompt_body=prompt_body,
        ))

    # Merge tenant custom SKILL# items (unchanged logic)
    tools.extend(_merge_tenant_skills(tenant_id, skill_names))
    return tools
```

### 2c. Dynamic `@tool` Factory

```python
def _make_subagent_tool(skill_name: str, description: str, prompt_body: str):
    """Create a @tool-wrapped subagent from skill registry entry."""
    @tool(name=skill_name)
    def subagent_tool(query: str) -> str:
        f"""{description}

        Args:
            query: The question or task for this specialist
        """
        agent = Agent(
            model=_model,
            system_prompt=prompt_body,
            callback_handler=None,
        )
        return str(agent(query))

    # Override docstring (required for Strands schema extraction)
    subagent_tool.__doc__ = f"{description}\n\nArgs:\n    query: The question or task for this specialist"
    return subagent_tool
```

### 2d. Replace `sdk_query()` — Same Signature, Strands Inside

**Current interface** (must preserve):
```python
async def sdk_query(prompt, tenant_id, user_id, tier, model, skill_names,
                    session_id, workspace_id, max_turns) -> AsyncGenerator[Any, None]:
    # yields SystemMessage, AssistantMessage, ResultMessage
```

**New implementation**:
```python
from dataclasses import dataclass

@dataclass
class StrandsResultMessage:
    """Adapter to match Claude SDK ResultMessage interface."""
    result: str
    usage: dict

@dataclass
class StrandsAssistantMessage:
    """Adapter to match Claude SDK AssistantMessage interface."""
    content: list

@dataclass
class TextBlock:
    type: str = "text"
    text: str = ""

async def sdk_query(
    prompt: str,
    tenant_id: str = "demo-tenant",
    user_id: str = "demo-user",
    tier: str = "advanced",
    model: str = None,
    skill_names: list[str] | None = None,
    session_id: str | None = None,
    workspace_id: str | None = None,
    max_turns: int = 15,
) -> AsyncGenerator[Any, None]:
    """Run a supervisor query with skill subagents (Strands implementation).

    Same signature as Claude SDK version. Yields adapter objects that match
    the AssistantMessage/ResultMessage interface expected by callers.
    """
    resolved_workspace_id = _resolve_workspace(workspace_id, tenant_id, user_id)
    skill_tools = build_skill_tools(
        tier=tier,
        skill_names=skill_names,
        tenant_id=tenant_id,
        user_id=user_id,
        workspace_id=resolved_workspace_id,
    )

    system_prompt = build_supervisor_prompt(
        tenant_id=tenant_id, user_id=user_id, tier=tier,
        agent_names=[t.__name__ for t in skill_tools],
        workspace_id=resolved_workspace_id,
    )

    supervisor = Agent(
        model=_model,
        system_prompt=system_prompt,
        tools=skill_tools,
        callback_handler=None,
        tool_executor=ConcurrentToolExecutor()=3,  # parallel subagent calls
    )

    # Synchronous call — Strands handles the agentic loop internally
    result = supervisor(prompt)
    result_text = str(result)

    # Yield adapter messages matching Claude SDK interface
    yield StrandsAssistantMessage(content=[TextBlock(text=result_text)])
    yield StrandsResultMessage(
        result=result_text,
        usage=getattr(result, "usage", {}),
    )
```

**Key insight**: The callers (`streaming_routes.py:70-86`, `main.py:225-244`) only check `type(msg).__name__` and access `.content`, `.text`, `.result`, `.usage`. The adapter dataclasses satisfy this contract.

### 2e. Replace `sdk_query_single_skill()` — Same Pattern

```python
async def sdk_query_single_skill(
    prompt: str, skill_name: str, tenant_id: str = "demo-tenant",
    user_id: str = "demo-user", tier: str = "advanced",
    model: str = None, max_turns: int = 5,
) -> AsyncGenerator[Any, None]:
    """Single-skill query — direct Agent, no supervisor."""
    prompt_body = _resolve_single_skill_prompt(skill_name)
    tenant_context = f"Tenant: {tenant_id} | User: {user_id} | Tier: {tier}\n"

    agent = Agent(
        model=_model,
        system_prompt=tenant_context + prompt_body,
        callback_handler=None,
    )
    result = agent(prompt)
    result_text = str(result)

    yield StrandsAssistantMessage(content=[TextBlock(text=result_text)])
    yield StrandsResultMessage(result=result_text, usage=getattr(result, "usage", {}))
```

---

## Phase 3: Route Wiring

**Goal**: Swap import and verify streaming + REST endpoints work.

### 3a. `streaming_routes.py` — One-Line Change

```python
# Before:
from .sdk_agentic_service import sdk_query

# After (no change needed if we keep the same module name):
from .sdk_agentic_service import sdk_query  # now backed by Strands
```

**No changes to `stream_generator()`** — it consumes `AssistantMessage.content[].type == "text"` and `ResultMessage`. Our adapter dataclasses satisfy both checks.

### 3b. `main.py` — Same Pattern

The REST endpoint at line 225 uses the same consumption pattern. No changes needed if the adapter messages match.

### 3c. Health Check Update

Update `streaming_routes.py:187` to remove `"anthropic": True`:
```python
"services": {
    "bedrock": True,       # was: "anthropic": True
    "dynamodb": True,
    "cognito": True,
    "s3": True,
},
```

---

## Phase 4: Eval Suite Migration

**Goal**: Port the 28-test eval suite from Claude SDK to Strands.

**Approach**: Create `test_strands_eval.py` that mirrors `test_eagle_sdk_eval.py` but uses Strands `Agent()` directly instead of `claude_agent_sdk.query()`.

**Key changes per test**:

| Claude SDK Pattern | Strands Replacement |
|-------------------|-------------------|
| `ClaudeAgentOptions(model="haiku", system_prompt=..., agents={...})` | `Agent(model=_model, system_prompt=..., tools=[...])` |
| `AgentDefinition(description=..., prompt=..., tools=...)` | `@tool`-wrapped `Agent()` |
| `async for msg in query(prompt, options)` | `result = supervisor(prompt)` |
| `ResultMessage.usage` | `result.usage` (if available) |
| `env=_get_bedrock_env()` | Not needed — boto3 handles natively |

**Estimation**: 28 tests, each ~20 lines to adapt. Mechanical transformation.

---

## Phase 5: Cleanup

1. **Remove `claude-agent-sdk`** from `requirements.txt`
2. **Remove `anthropic`** from `requirements.txt` (unless other code uses it)
3. **Archive** `test_agent_sdk.py` and `test_eagle_sdk_eval.py` (rename to `_archived_*`)
4. **Update** CLAUDE.md line 1: "Strands Agents SDK" instead of "Claude SDK"
5. **Update** expert primitives: `/experts:claude-sdk:*` → reference only for historical context

---

## Migration Checklist

- [ ] **Phase 1**: Multi-agent POC test passes on 3 models
- [ ] **Phase 2a**: Module-level `BedrockModel` (shared)
- [ ] **Phase 2b**: `build_skill_tools()` replaces `build_skill_agents()`
- [ ] **Phase 2c**: `_make_subagent_tool()` factory with proper docstrings
- [ ] **Phase 2d**: `sdk_query()` with adapter messages
- [ ] **Phase 2e**: `sdk_query_single_skill()` with adapter messages
- [ ] **Phase 3a**: `streaming_routes.py` works with Strands
- [ ] **Phase 3b**: `main.py` REST endpoint works with Strands
- [ ] **Phase 3c**: Health check updated (no "anthropic" reference)
- [ ] **Phase 4**: Eval suite ported (28 tests pass)
- [ ] **Phase 5a**: `claude-agent-sdk` removed from requirements
- [ ] **Phase 5b**: CLAUDE.md updated
- [ ] **Phase 5c**: Old test files archived

## Validation Commands

```bash
# Phase 1
AWS_PROFILE=eagle python -m pytest tests/test_strands_multi_agent.py -v -s

# Phase 2-3 (integration)
AWS_PROFILE=eagle python -m pytest tests/test_strands_poc.py tests/test_strands_multi_agent.py -v -s

# Phase 4 (full eval)
AWS_PROFILE=eagle python -m pytest tests/test_strands_eval.py -v -s

# Phase 5 (no Claude SDK imports remain)
grep -r "claude_agent_sdk" server/app/ --include="*.py"  # should return nothing
python -c "from app.sdk_agentic_service import sdk_query; print('OK')"
```

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| Non-Claude models less capable for complex routing | Test supervisor routing explicitly in Phase 1; Nova Pro scored 5/5 |
| Strands `@tool` docstring schema extraction differs from AgentDefinition | Test with real tool calls; override `__doc__` explicitly |
| Adapter messages miss edge cases in callers | Grep for ALL `sdk_msg` consumption patterns; test SSE stream end-to-end |
| DynamoDB prompt resolution fails differently under Strands | Unchanged — same Python code, same boto3 calls |
| Session persistence (resume) not yet mapped | Phase 2 uses no session; add DynamoDBSessionManager in follow-up |

## Model Selection

| Model | Score (POC) | Speed | Recommendation |
|-------|-------------|-------|----------------|
| Amazon Nova Pro | 5/5 | 4.40s | **Default** — best score + fastest |
| Llama 4 Maverick 17B | 4/5 | 4.90s | Good alternative |
| DeepSeek R1 | 5/5 | 9.01s | Best for reasoning-heavy tasks |
