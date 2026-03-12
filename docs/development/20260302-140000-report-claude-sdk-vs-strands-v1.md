# Agent/Prompt Loading: Claude Agent SDK vs Strands Agents SDK

**Date**: 2026-03-02
**Type**: Technical Comparison Report
**Context**: EAGLE migration readiness assessment

---

## Executive Summary

Claude Agent SDK and Strands Agents SDK take fundamentally different approaches to
when and how agents and prompts are loaded. Claude Agent SDK is **definition-oriented**
— you declare lightweight `AgentDefinition` data objects per-request and hand them to
a subprocess. Strands is **instance-oriented** — you construct live `Agent` objects
with model connections, tool registries, and state, then invoke them directly in-process.

This distinction has major implications for hot-reloading prompts, memory usage,
concurrency, and migration effort.

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                     CLAUDE AGENT SDK                                │
│                                                                     │
│  Python Process (FastAPI)           Node.js Subprocess (CLI)        │
│  ┌──────────────────────┐          ┌──────────────────────────┐    │
│  │                      │          │                          │    │
│  │  AgentDefinition     │──JSON──▶│  Supervisor Agent        │    │
│  │  (data only —        │          │  (live orchestrator)     │    │
│  │   no model client,   │          │                          │    │
│  │   no tools,          │          │  ┌─────────────────┐    │    │
│  │   no state)          │          │  │ Subagent A      │    │    │
│  │                      │          │  │ (fresh context)  │    │    │
│  │  ClaudeAgentOptions  │          │  └─────────────────┘    │    │
│  │  (config envelope)   │          │  ┌─────────────────┐    │    │
│  │                      │          │  │ Subagent B      │    │    │
│  └──────────────────────┘          │  │ (fresh context)  │    │    │
│                                     │  └─────────────────┘    │    │
│                                     └──────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                     STRANDS AGENTS SDK                              │
│                                                                     │
│  Python Process (FastAPI) — everything in-process                   │
│  ┌──────────────────────────────────────────────────────────┐      │
│  │                                                          │      │
│  │  Agent (live object)                                     │      │
│  │  ├── BedrockModel (boto3 client created at __init__)     │      │
│  │  ├── ToolRegistry  (tools loaded + initialized)          │      │
│  │  ├── ConversationManager (history buffer)                │      │
│  │  ├── HookRegistry  (lifecycle hooks)                     │      │
│  │  ├── AgentState    (mutable dict)                        │      │
│  │  └── Lock          (concurrency guard)                   │      │
│  │                                                          │      │
│  │  On invoke: agent("prompt")                              │      │
│  │  └── converse_stream() called directly via boto3         │      │
│  │      └── tool execution in-process                       │      │
│  │          └── loop until stop_reason = end_turn           │      │
│  │                                                          │      │
│  └──────────────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Loading Timeline Comparison

### Claude Agent SDK — What loads when

```
APPLICATION STARTUP (once)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  eagle_skill_constants.py imports
  │
  ├─ _discover(_AGENTS_DIR, "agent.md")    ← Walk eagle-plugin/agents/*
  │  └─ Parse YAML frontmatter + body      ← File I/O, regex parsing
  │     └─ Store in AGENTS dict            ← {name: {meta, body, ...}}
  │
  ├─ _discover(_SKILLS_DIR, "SKILL.md")    ← Walk eagle-plugin/skills/*
  │  └─ Parse YAML frontmatter + body
  │     └─ Store in SKILLS dict
  │
  ├─ PLUGIN_CONTENTS = {**AGENTS, **SKILLS}
  │
  ├─ SKILL_CONSTANTS = {name: body, ...}   ← Convenience lookup
  │
  └─ ensure_plugin_seeded()                ← Seed DynamoDB from files
     ├─ Check PLUGIN#manifest version
     ├─ If stale: write PLUGIN#agents/*, PLUGIN#skills/*
     └─ Write PLUGIN#manifest with version

  sdk_agentic_service.py imports
  │
  └─ SKILL_AGENT_REGISTRY = _build_registry()
     ├─ _load_plugin_config()              ← DynamoDB PLUGIN#manifest
     │                                       (fallback: bundled plugin.json)
     └─ Filter AGENTS + SKILLS by active list
        └─ Store metadata: description, skill_key, tools, model


PER CHAT MESSAGE (every request)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  POST /api/chat/stream
  │
  ├─ Extract tenant_id, user_id, tier from JWT
  │
  └─ sdk_query(prompt, tenant_id, user_id, tier, session_id)
     │
     ├─ get_or_create_default(tenant_id, user_id)
     │  └─ Auto-provision workspace if none exists
     │
     ├─ build_skill_agents(model, tier, ..., workspace_id)  ← BUILT FRESH
     │  │
     │  │  For each skill in SKILL_AGENT_REGISTRY:
     │  │  ┌──────────────────────────────────────────┐
     │  │  │ PROMPT RESOLUTION (4-layer chain)        │
     │  │  │                                          │
     │  │  │ 1. wspc_store.resolve_skill()            │ ← Workspace override
     │  │  │    (DynamoDB WSPC# per tenant/user)      │
     │  │  │              │                           │
     │  │  │    empty?    ▼                           │
     │  │  │ 2. PLUGIN_CONTENTS[skill_key]["body"]    │ ← DynamoDB PLUGIN#
     │  │  │    (60-second in-process cache)           │   or bundled fallback
     │  │  │              │                           │
     │  │  │              ▼                           │
     │  │  │ 3. AgentDefinition(                      │
     │  │  │      description=...,                    │
     │  │  │      prompt=resolved_body,   ← STRING    │
     │  │  │      tools=[...],            ← NAMES     │
     │  │  │      model="haiku"           ← STRING    │
     │  │  │    )                                     │
     │  │  └──────────────────────────────────────────┘
     │  │
     │  └─ Merge tenant custom skills (SKILL# entities)
     │
     ├─ build_supervisor_prompt(tenant_id, user_id, tier, ...)
     │  ├─ Try wspc_store.resolve_agent("supervisor")
     │  └─ Fallback: AGENTS["supervisor"]["body"]
     │
     ├─ ClaudeAgentOptions(                    ← CONFIG ENVELOPE
     │    model="haiku",
     │    system_prompt=supervisor_prompt,
     │    agents={name: AgentDefinition, ...},  ← ALL DEFINITIONS
     │    env=_get_bedrock_env(),               ← AWS creds
     │    allowed_tools=["Task"],
     │    permission_mode="bypassPermissions",
     │  )
     │
     └─ async for msg in query(prompt, options)
        └─ SPAWNS NODE.JS SUBPROCESS
           ├─ CLI receives full config as JSON
           ├─ CLI instantiates live agents internally
           ├─ Supervisor routes via Task tool
           └─ Streams messages back to Python
```

### Strands Agents SDK — What loads when

```
AGENT CONSTRUCTION (module-level OR per-request — developer's choice)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  agent = Agent(
      model=BedrockModel(...),
      system_prompt="...",
      tools=[tool_a, tool_b],
  )
  │
  ├─ BedrockModel.__init__()
  │  └─ boto3.Session().client("bedrock-runtime")  ← CLIENT CREATED NOW
  │     (connection pool, TLS handshake on first call)
  │
  ├─ ToolRegistry.process_tools()
  │  ├─ Validate @tool signatures
  │  ├─ Extract JSON schema from docstrings + type hints
  │  └─ Store: {tool_name: {spec, handler, ...}}
  │
  ├─ ConversationManager.__init__()
  │  └─ SlidingWindowConversationManager (default, 200k token window)
  │
  ├─ HookRegistry.__init__()
  │  └─ Register lifecycle hooks
  │
  ├─ AgentState initialized (empty dict or user-provided)
  │
  ├─ Threading Lock created
  │  └─ Default: THROW mode (reject concurrent calls)
  │
  ├─ Plugins initialized (each .init(agent) called)
  │
  └─ AgentInitializedEvent fired


PER INVOCATION (every request)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  result = agent("user prompt")
  │
  ├─ Acquire lock (or throw if already held)
  │
  ├─ Convert prompt → Messages format
  │
  ├─ Fire BeforeInvocationEvent (hooks can modify messages)
  │
  ├─ Append user message to conversation history
  │
  └─ EVENT LOOP (in-process, no subprocess)
     │
     ├─ Send to model:
     │  │  system_prompt (from agent._system_prompt)
     │  │  + conversation history
     │  │  + tool_specs (from ToolRegistry)
     │  │
     │  └─ bedrock_client.converse_stream()  ← DIRECT BOTO3 CALL
     │     └─ Streams response chunks
     │
     ├─ If model returns tool_use:
     │  ├─ Execute tool handler IN-PROCESS
     │  ├─ Append tool result to history
     │  └─ Loop back to "Send to model"
     │
     ├─ If ContextWindowOverflow:
     │  ├─ ConversationManager trims history
     │  └─ Retry
     │
     └─ If stop_reason == "end_turn":
        ├─ Fire AfterInvocationEvent
        ├─ Release lock
        └─ Return AgentResult
```

---

## 3. The Hot-Reload Question

### What "hot-reload" means for EAGLE

EAGLE needs to update agent system prompts (the markdown files that define each
specialist agent's behavior) **without restarting the container**. The goal is:
admin edits a prompt in the dashboard → next chat message uses the new version.

### Claude Agent SDK: Hot-reload is natural

```
                    ┌─────────────────────┐
                    │   DynamoDB          │
                    │   PLUGIN#agents/*   │
  Admin edits  ──▶  │   PLUGIN#skills/*   │
  via dashboard     │   WSPC#overrides    │
                    └────────┬────────────┘
                             │
                    ┌────────▼────────────┐
                    │ build_skill_agents() │  ← Called EVERY request
                    │ resolve_skill()      │  ← Reads DynamoDB (60s cache)
                    │ → AgentDefinition()  │  ← New data object each time
                    └────────┬────────────┘
                             │
                    ┌────────▼────────────┐
                    │ query(prompt, opts)  │  ← Subprocess gets fresh defs
                    │ subprocess starts    │  ← No stale state possible
                    └─────────────────────┘
```

**Why it works**: `AgentDefinition` is a **data transfer object** — it holds strings
(prompt, description, model name, tool names). It has no connection to a model client,
no loaded tools, no state. You build it fresh from DynamoDB per-request and send it to
the subprocess. The subprocess is ephemeral — it starts, runs, and dies per query.
There is zero cached state to go stale.

**Latency**: 60-second DynamoDB cache TTL means prompt changes take effect within
1 minute. No container restart. No redeploy.

### Strands: Hot-reload requires deliberate architecture

Strands agents are **live objects** with real connections and state. You have two
choices, each with trade-offs:

#### Option A: Module-level agents (Strands default pattern)

```python
# Created ONCE at import time — prompt baked in
legal_agent = Agent(
    model=BedrockModel(model_id="us.anthropic.claude-sonnet-4-20250514-v1:0"),
    system_prompt="You are a legal counsel...",   # ← FROZEN
    tools=[far_lookup, case_search],
)

# Every request reuses the same agent
@app.post("/chat")
async def chat(req: ChatRequest):
    return legal_agent(req.message)
```

```
  ┌──────────────────────────────────────────────────────────┐
  │ Module load (once)                                       │
  │                                                          │
  │  legal_agent = Agent(system_prompt="frozen string")      │
  │       │                                                  │
  │       ├── boto3 client created                           │
  │       ├── tool registry built                            │
  │       └── system_prompt stored as string                 │
  │                                                          │
  │ Request 1:  legal_agent("query")  → uses frozen prompt   │
  │ Request 2:  legal_agent("query")  → uses frozen prompt   │
  │                                                          │
  │   Admin changes prompt in DB ──▶ NOTHING HAPPENS         │
  │                                                          │
  │ Request 3:  legal_agent("query")  → still frozen prompt  │
  └──────────────────────────────────────────────────────────┘
```

**Problem**: Prompt changes require container restart. This is the pattern most
Strands examples and tutorials use.

**Workaround — property setter**:

```python
# You CAN mutate the prompt between calls
legal_agent.system_prompt = fetch_prompt_from_dynamodb("legal-counsel")
legal_agent("query")
```

But this requires a custom middleware layer that fetches and sets prompts
before each invocation, and it's not thread-safe with the default THROW lock.

#### Option B: Per-request agents (EAGLE-compatible pattern)

```python
@app.post("/chat")
async def chat(req: ChatRequest):
    # Built fresh per-request — just like Claude Agent SDK
    prompt = get_prompt_from_dynamodb("legal-counsel")  # hot-reloadable
    agent = Agent(
        model=BedrockModel(model_id="..."),
        system_prompt=prompt,
        tools=[far_lookup],
    )
    return agent(req.message)
```

```
  ┌──────────────────────────────────────────────────────────┐
  │ Request 1:                                               │
  │   prompt = DynamoDB("legal-counsel")  → "Version 1"      │
  │   agent = Agent(system_prompt=prompt)                    │
  │       ├── boto3 client created  ← OVERHEAD               │
  │       ├── tool registry built   ← OVERHEAD               │
  │       └── system_prompt = "Version 1"                    │
  │   agent("query") → uses Version 1                        │
  │   agent garbage collected                                │
  │                                                          │
  │   Admin changes prompt in DB ──▶ DynamoDB updated        │
  │                                                          │
  │ Request 2:                                               │
  │   prompt = DynamoDB("legal-counsel")  → "Version 2"      │
  │   agent = Agent(system_prompt=prompt)  ← NEW OBJECT      │
  │       ├── boto3 client created  ← OVERHEAD AGAIN         │
  │       ├── tool registry built   ← OVERHEAD AGAIN         │
  │       └── system_prompt = "Version 2"                    │
  │   agent("query") → uses Version 2  ✓ HOT-RELOADED       │
  └──────────────────────────────────────────────────────────┘
```

**Problem**: Per-request agent construction creates a new boto3 client every time.
boto3 client creation is ~50-200ms (TLS setup, credential resolution). This adds
measurable latency to every chat message.

#### Option C: Hybrid — shared model, per-request agent (recommended)

```python
# Module-level: reuse the expensive parts
shared_model = BedrockModel(
    model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
    region_name="us-east-1",
)
shared_tools = [far_lookup, case_search, market_search]

@app.post("/chat")
async def chat(req: ChatRequest):
    prompt = get_prompt_from_dynamodb(req.agent_name)  # hot-reloadable
    agent = Agent(
        model=shared_model,        # ← REUSED (no boto3 overhead)
        system_prompt=prompt,       # ← FRESH from DynamoDB
        tools=shared_tools,         # ← REUSED (pre-validated)
        callback_handler=None,
    )
    return agent(req.message)
```

```
  ┌──────────────────────────────────────────────────────────┐
  │ Module load (once):                                      │
  │   shared_model = BedrockModel(...)  ← boto3 client once  │
  │   shared_tools = [far_lookup, ...]  ← validated once     │
  │                                                          │
  │ Request 1:                                               │
  │   prompt = DynamoDB("legal")  → "Version 1"              │
  │   agent = Agent(                                         │
  │     model=shared_model,  ← NO new boto3 client           │
  │     system_prompt=prompt,                                │
  │     tools=shared_tools,  ← NO re-validation              │
  │   )                                                      │
  │   agent("query") → Version 1                             │
  │                                                          │
  │   Admin changes prompt in DB                             │
  │                                                          │
  │ Request 2:                                               │
  │   prompt = DynamoDB("legal")  → "Version 2"              │
  │   agent = Agent(model=shared_model, ...)                 │
  │   agent("query") → Version 2  ✓ HOT-RELOADED            │
  │                      ✓ NO BOTO3 OVERHEAD                 │
  └──────────────────────────────────────────────────────────┘
```

This is the **closest equivalent** to EAGLE's current `build_skill_agents()` pattern.

---

## 4. Multi-Agent Prompt Loading

### Claude Agent SDK: Supervisor + AgentDefinition

```
  ┌─────────────────────────────────────────────────────────┐
  │  build_skill_agents() — called per-request              │
  │                                                         │
  │  SKILL_AGENT_REGISTRY (module-level metadata)           │
  │  ┌───────────────┬───────────────┬──────────────┐      │
  │  │ legal-counsel │ oa-intake     │ tech-trans.  │ ...  │
  │  │ desc, tools   │ desc, tools   │ desc, tools  │      │
  │  └──────┬────────┴──────┬────────┴──────┬───────┘      │
  │         │               │               │               │
  │         ▼               ▼               ▼               │
  │  resolve_skill()  resolve_skill()  resolve_skill()      │
  │  (DynamoDB)       (DynamoDB)       (DynamoDB)           │
  │         │               │               │               │
  │         ▼               ▼               ▼               │
  │  AgentDefinition  AgentDefinition  AgentDefinition      │
  │  (prompt=body)    (prompt=body)    (prompt=body)        │
  │         │               │               │               │
  │         └───────────────┼───────────────┘               │
  │                         │                               │
  │                         ▼                               │
  │              ClaudeAgentOptions(                         │
  │                agents={                                  │
  │                  "legal-counsel": AgentDef,              │
  │                  "oa-intake": AgentDef,                  │
  │                  "tech-translator": AgentDef,            │
  │                },                                        │
  │                system_prompt=supervisor_prompt,           │
  │              )                                           │
  │                         │                               │
  │                         ▼                               │
  │              query(prompt, options)                      │
  │              └── subprocess receives ALL defs as JSON    │
  │                  └── supervisor delegates via Task tool  │
  └─────────────────────────────────────────────────────────┘
```

**Key property**: ALL agent prompts are resolved and bundled into a single
`ClaudeAgentOptions` envelope. The subprocess receives everything at once.
The supervisor decides which subagent to invoke at runtime — but all prompts
were already loaded before the subprocess started.

### Strands: Agents-as-Tools Pattern

```
  ┌─────────────────────────────────────────────────────────┐
  │  Per-request construction (EAGLE-compatible pattern)    │
  │                                                         │
  │  @tool                                                  │
  │  def legal_counsel(query: str) -> str:                  │
  │      prompt = dynamodb.get("legal-counsel")  ← LAZY     │
  │      agent = Agent(                                     │
  │          model=shared_model,                            │
  │          system_prompt=prompt,                          │
  │      )                                                  │
  │      return str(agent(query))                           │
  │                                                         │
  │  @tool                                                  │
  │  def oa_intake(query: str) -> str:                      │
  │      prompt = dynamodb.get("oa-intake")      ← LAZY     │
  │      agent = Agent(                                     │
  │          model=shared_model,                            │
  │          system_prompt=prompt,                          │
  │      )                                                  │
  │      return str(agent(query))                           │
  │                                                         │
  │  supervisor = Agent(                                    │
  │      system_prompt=dynamodb.get("supervisor"),          │
  │      tools=[legal_counsel, oa_intake, ...],             │
  │  )                                                      │
  │  supervisor("user message")                             │
  │      │                                                  │
  │      ├── Model decides: call legal_counsel tool         │
  │      │   └── legal_counsel("subquery")                  │
  │      │       ├── DynamoDB fetch  ← ONLY WHEN INVOKED    │
  │      │       ├── Agent created   ← ONLY WHEN INVOKED    │
  │      │       └── Agent runs + returns                   │
  │      │                                                  │
  │      └── Model decides: call oa_intake tool             │
  │          └── (same pattern)                             │
  └─────────────────────────────────────────────────────────┘
```

**Key difference**: Subagent prompts are loaded **lazily** — only when the
supervisor actually decides to invoke that tool. In Claude Agent SDK, all
prompts are loaded eagerly (all at once, before any routing decision).

---

## 5. Side-by-Side Comparison Table

```
┌──────────────────────┬──────────────────────────┬──────────────────────────┐
│ Dimension            │ Claude Agent SDK         │ Strands Agents SDK       │
├──────────────────────┼──────────────────────────┼──────────────────────────┤
│ Agent representation │ AgentDefinition          │ Agent (live object)      │
│                      │ (data-only struct:       │ (boto3 client, tools,    │
│                      │  strings + lists)        │  state, lock, hooks)     │
├──────────────────────┼──────────────────────────┼──────────────────────────┤
│ Model connection     │ None — subprocess owns   │ Created at __init__      │
│                      │ the connection           │ (boto3 bedrock-runtime)  │
├──────────────────────┼──────────────────────────┼──────────────────────────┤
│ Prompt storage       │ String in definition     │ String or ContentBlock[] │
│                      │ (immutable after create) │ (mutable via setter)     │
├──────────────────────┼──────────────────────────┼──────────────────────────┤
│ Prompt loading time  │ Per-request (in          │ At construction          │
│                      │ build_skill_agents)      │ (or via setter before    │
│                      │                          │  each invocation)        │
├──────────────────────┼──────────────────────────┼──────────────────────────┤
│ Subagent loading     │ EAGER — all defs built   │ LAZY — subagent created  │
│                      │ before query() starts    │ only when tool invoked   │
├──────────────────────┼──────────────────────────┼──────────────────────────┤
│ Hot-reload story     │ Natural — defs rebuilt   │ Requires architecture:   │
│                      │ from DynamoDB per-request│ per-request agents OR    │
│                      │ (60s cache TTL)          │ setter-based mutation    │
├──────────────────────┼──────────────────────────┼──────────────────────────┤
│ Construction cost    │ Negligible — just        │ ~50-200ms per agent      │
│                      │ Python dict/dataclass    │ (boto3 client + tool     │
│                      │                          │  registry + hooks)       │
├──────────────────────┼──────────────────────────┼──────────────────────────┤
│ Invocation model     │ Subprocess (Node.js CLI) │ In-process (direct       │
│                      │ spawned per query()      │ boto3 converse_stream)   │
├──────────────────────┼──────────────────────────┼──────────────────────────┤
│ Subprocess overhead  │ ~200-500ms per query     │ None — in-process        │
│                      │ (Node.js startup + IPC)  │                          │
├──────────────────────┼──────────────────────────┼──────────────────────────┤
│ Multi-agent routing  │ Built-in Task tool       │ agents-as-tools, swarm,  │
│                      │ (supervisor delegates)   │ graph, or workflow       │
├──────────────────────┼──────────────────────────┼──────────────────────────┤
│ Concurrency          │ Subprocess isolation     │ Thread lock per agent    │
│                      │ (no shared state)        │ (THROW or REENTRANT)     │
├──────────────────────┼──────────────────────────┼──────────────────────────┤
│ Streaming            │ SSE via subprocess IPC   │ Async iterators or       │
│                      │ (SystemMessage,          │ callback handlers        │
│                      │  AssistantMessage,       │ (native Python async)    │
│                      │  ResultMessage)          │                          │
├──────────────────────┼──────────────────────────┼──────────────────────────┤
│ Session persistence  │ External (DynamoDB       │ Built-in SessionManager  │
│                      │ session_store.py)        │ (File, S3, or custom)    │
├──────────────────────┼──────────────────────────┼──────────────────────────┤
│ Tool hot-reload      │ Not applicable           │ load_tools_from_dir=True │
│                      │ (tools are CLI built-ins)│ (ToolWatcher thread)     │
└──────────────────────┴──────────────────────────┴──────────────────────────┘
```

---

## 6. EAGLE Migration Impact Assessment

### What EAGLE currently does (Claude Agent SDK)

```python
# sdk_agentic_service.py — simplified flow

async def sdk_query(prompt, tenant_id, user_id, tier, session_id):
    workspace_id = get_or_create_default(tenant_id, user_id)

    # 1. Build ALL subagent definitions (per-request, from DynamoDB)
    agents = build_skill_agents(tier=tier, workspace_id=workspace_id)

    # 2. Build supervisor prompt (per-request, from DynamoDB)
    system_prompt = build_supervisor_prompt(tenant_id, user_id, tier)

    # 3. Package into options envelope
    options = ClaudeAgentOptions(
        model="haiku",
        system_prompt=system_prompt,
        agents=agents,                    # ← ALL agent defs
        env=_get_bedrock_env(),
    )

    # 4. Spawn subprocess with full config
    async for msg in query(prompt, options):
        yield msg
```

### What EAGLE would look like on Strands

```python
# strands_agentic_service.py — equivalent flow

from strands import Agent, tool
from strands.models import BedrockModel

# Module-level: expensive parts created once
_model = BedrockModel(
    model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
    region_name="us-east-1",
)

# Dynamic tool factory — each subagent is a @tool that
# constructs its Agent lazily with the latest DynamoDB prompt
def _make_subagent_tool(skill_name: str, description: str, skill_tools: list):
    @tool(name=skill_name)
    def subagent_tool(query: str) -> str:
        """<dynamic description>"""
        prompt = resolve_skill_from_dynamodb(skill_name)  # hot-reload
        agent = Agent(
            model=_model,              # shared, no boto3 overhead
            system_prompt=prompt,      # fresh from DynamoDB
            tools=skill_tools,
            callback_handler=None,
        )
        return str(agent(query))
    subagent_tool.__doc__ = description
    return subagent_tool


async def strands_query(prompt, tenant_id, user_id, tier, session_id):
    workspace_id = get_or_create_default(tenant_id, user_id)

    # 1. Build subagent tools (lightweight — just wraps functions)
    subagent_tools = []
    for name, meta in SKILL_AGENT_REGISTRY.items():
        subagent_tools.append(
            _make_subagent_tool(name, meta["description"], meta["tools"])
        )

    # 2. Build supervisor with subagent tools
    supervisor_prompt = resolve_supervisor_from_dynamodb(workspace_id)
    supervisor = Agent(
        model=_model,                  # shared
        system_prompt=supervisor_prompt,
        tools=subagent_tools,
        callback_handler=None,
    )

    # 3. Invoke directly (no subprocess)
    async for event in supervisor.stream_async(prompt):
        yield event
```

### What you keep, what you lose, what you gain

```
KEEP (port directly)
━━━━━━━━━━━━━━━━━━━━
  ✓ plugin_store.py           — DynamoDB PLUGIN# CRUD + 60s cache
  ✓ wspc_store.py             — Workspace prompt overrides
  ✓ skill_store.py            — Tenant custom skills
  ✓ eagle_skill_constants.py  — Bootstrap seeder
  ✓ SKILL_AGENT_REGISTRY      — Module-level metadata
  ✓ 4-layer prompt resolution — wspc → plugin → bundled
  ✓ Tier-based tool gating    — basic/advanced/premium
  ✓ Multi-tenant isolation    — tenant_id/user_id scoping

LOSE
━━━━
  ✗ AgentDefinition class     — replaced by Agent + @tool pattern
  ✗ ClaudeAgentOptions        — replaced by Agent constructor
  ✗ query() subprocess        — replaced by in-process agent()
  ✗ _get_bedrock_env()        — no longer needed (boto3 native)
  ✗ SSE message types         — new event format from Strands
  ✗ resume: session_id        — replaced by SessionManager

GAIN
━━━━
  + No subprocess overhead    — ~200-500ms saved per query
  + In-process debugging      — Python stack traces, no IPC
  + Native async streaming    — stream_async() + async iterators
  + Built-in session manager  — S3SessionManager or DynamoDB custom
  + Tool hot-reload           — ToolWatcher for dev mode
  + Swarm/Graph patterns      — if needed for complex workflows
  + AgentState                — mutable per-invocation state dict
  + Hooks system              — BeforeInvocation, AfterInvocation, etc.
  + Prompt caching            — ContentBlock cache_point support
  + Lazy subagent loading     — only pay for agents actually invoked
```

---

## 8. Agent-to-Agent Handoff

Claude Agent SDK and Strands take fundamentally different approaches to how agents
hand off work to each other. Claude Agent SDK has **one pattern** (supervisor delegation).
Strands has **four patterns**, each with different context-sharing and control-flow semantics.

### Claude Agent SDK: Task-Tool Delegation

```
  ┌────────────────────────────────────────────────────────────────┐
  │  SUPERVISOR (Node.js subprocess)                               │
  │  system_prompt: "You are the EAGLE supervisor..."              │
  │  allowed_tools: [Task]                                         │
  │                                                                │
  │  User: "Is this sole-source justification valid?"              │
  │  │                                                             │
  │  ├── Supervisor LLM decides: delegate to legal-counsel         │
  │  │   └── Task(agent="legal-counsel",                           │
  │  │          prompt="Evaluate sole-source justification...")     │
  │  │                                                             │
  │  │   ┌─────────────────────────────────────────┐               │
  │  │   │ SUBAGENT: legal-counsel                 │               │
  │  │   │ ┌─ FRESH context window (no history)    │               │
  │  │   │ ├─ system_prompt = SKILL.md body        │               │
  │  │   │ ├─ tools = tier-gated [Read, Glob, ...]│               │
  │  │   │ └─ prompt = "Evaluate sole-source..."   │               │
  │  │   │                                         │               │
  │  │   │ Runs to completion → returns result     │               │
  │  │   └──────────────────┬──────────────────────┘               │
  │  │                      │                                      │
  │  │   result text ◄──────┘                                      │
  │  │                                                             │
  │  ├── Supervisor sees result, may delegate again                │
  │  │   └── Task(agent="market-intelligence", ...)                │
  │  │       └── (same fresh-context pattern)                      │
  │  │                                                             │
  │  └── Supervisor synthesizes all results → final answer         │
  └────────────────────────────────────────────────────────────────┘
```

**Key properties**:
- **One-way delegation**: Supervisor calls subagent, waits, gets result. Subagent
  cannot call back or hand off to siblings.
- **Complete context isolation**: Each subagent gets a fresh context window. No
  conversation history from the supervisor or other subagents.
- **Supervisor retains control**: After a subagent returns, the supervisor decides
  what to do next. There is no autonomous handoff between subagents.
- **No shared state**: Subagents communicate only through the text result returned
  to the supervisor. No shared memory, no state dict, no knowledge base.

### Strands: Four Multi-Agent Patterns

#### Pattern 1: Agents-as-Tools (closest to Claude Agent SDK)

```
  ┌────────────────────────────────────────────────────────────────┐
  │  SUPERVISOR Agent                                              │
  │  tools: [legal_counsel, market_intel, oa_intake]               │
  │                                                                │
  │  User: "Is this sole-source justification valid?"              │
  │  │                                                             │
  │  ├── LLM decides: call legal_counsel(query="Evaluate...")      │
  │  │                                                             │
  │  │   @tool                                                     │
  │  │   def legal_counsel(query: str) -> str:                     │
  │  │       agent = Agent(system_prompt=..., tools=[...])         │
  │  │       return str(agent(query))                              │
  │  │                ▲                                            │
  │  │   ┌────────────┘                                            │
  │  │   │ SUBAGENT runs in-process                                │
  │  │   │ ├─ Own conversation history (isolated)                  │
  │  │   │ ├─ Own system prompt                                    │
  │  │   │ ├─ Only sees the query string                           │
  │  │   │ └─ Returns result as string                             │
  │  │   └──────────────────────────────────────────               │
  │  │                                                             │
  │  ├── LLM sees result, may call another tool                    │
  │  └── Synthesizes → final answer                                │
  └────────────────────────────────────────────────────────────────┘

  CONTEXT ISOLATION: Complete — subagent sees ONLY the query string.
  CONTROL FLOW:     Supervisor retains control throughout.
  SHARED STATE:     None (unless ToolContext.invocation_state used).
```

**Mapping to EAGLE**: This is the direct equivalent of the current Claude Agent SDK
supervisor pattern. Each `@tool`-wrapped agent replaces an `AgentDefinition`.

#### Pattern 2: Swarm (autonomous agent handoff)

```
  ┌────────────────────────────────────────────────────────────────┐
  │  SWARM                                                         │
  │  agents: [legal, market, tech, intake]                         │
  │  entry_point: intake                                           │
  │  max_handoffs: 20                                              │
  │                                                                │
  │  User: "Evaluate this acquisition for IT modernization"        │
  │  │                                                             │
  │  ▼                                                             │
  │  ┌──────────────┐  handoff_to_agent("market",                  │
  │  │ INTAKE agent │  msg="Need market data for IT services",     │
  │  │              │  context={"acq_type": "IT modernization"})   │
  │  │ Analyzes     │──────────────────────┐                       │
  │  │ request      │                      │                       │
  │  └──────────────┘                      ▼                       │
  │                                 ┌──────────────┐               │
  │     ┌───────────────────────────│ MARKET agent │               │
  │     │ handoff_to_agent("legal", │              │               │
  │     │ msg="Need FAR review",    │ Researches   │               │
  │     │ context={"findings":...}) │ market data  │               │
  │     ▼                           └──────────────┘               │
  │  ┌──────────────┐                                              │
  │  │ LEGAL agent  │                                              │
  │  │              │──▶ end_turn (no more handoffs)               │
  │  │ Reviews FAR  │   → SwarmResult returned                     │
  │  │ compliance   │                                              │
  │  └──────────────┘                                              │
  └────────────────────────────────────────────────────────────────┘

  What each agent RECEIVES on handoff:
  ┌──────────────────────────────────────────────────────────┐
  │ Handoff Message: Need FAR review for IT modernization    │
  │                  acquisition — market data attached.      │
  │                                                          │
  │ User Request: Evaluate this acquisition for IT...        │
  │                                                          │
  │ Previous agents: intake -> market                        │
  │                                                          │
  │ Shared knowledge from previous agents:                   │
  │   - intake: {"acq_type": "IT modernization"}             │
  │   - market: {"findings": "3 vendors identified..."}      │
  │                                                          │
  │ Other agents available for collaboration:                │
  │   Agent: market — Market research specialist             │
  │   Agent: tech   — Technical evaluation specialist        │
  │   Agent: intake — Acquisition intake specialist          │
  └──────────────────────────────────────────────────────────┘

  CONTEXT ISOLATION: Partial — each agent has own LLM conversation
                     but sees curated summary of prior agents' work
                     via SharedContext.
  CONTROL FLOW:     Full transfer — original agent STOPS, target
                     agent STARTS. No return to sender.
  SHARED STATE:     SharedContext (write-once knowledge base) +
                     invocation_state (programmatic, not in prompt).
```

**Key mechanism**: `handoff_to_agent` is a **built-in tool auto-injected** by the
Swarm into every agent's tool set. The agent doesn't need to know about it in advance.

**Safety bounds**:

```
  max_handoffs:  20    (total transfers before forced stop)
  max_iterations: 20   (total event loop cycles across all agents)
  execution_timeout: 900s  (15 min wall clock)
  node_timeout: 300s       (5 min per agent)
  repetitive_handoff_detection: ping-pong guard (optional)
```

#### Pattern 3: Graph (deterministic routing)

```
  ┌────────────────────────────────────────────────────────────────┐
  │  GRAPH                                                         │
  │                                                                │
  │  ┌──────────┐     ┌──────────┐     ┌──────────┐               │
  │  │ RESEARCH │────▶│ ANALYSIS │────▶│ REPORT   │               │
  │  │ agent    │     │ agent    │     │ agent    │               │
  │  └──────────┘     └──────────┘     └──────────┘               │
  │       │                                  ▲                     │
  │       │         ┌──────────┐             │                     │
  │       └────────▶│ LEGAL    │─────────────┘                     │
  │   (parallel)    │ agent    │   (fan-in: both must              │
  │                 └──────────┘    complete before REPORT)         │
  │                                                                │
  │  Each node receives:                                           │
  │  ┌──────────────────────────────────────────────────┐          │
  │  │ Original Task: [user's request]                  │          │
  │  │                                                  │          │
  │  │ Inputs from previous nodes:                      │          │
  │  │                                                  │          │
  │  │ From research:                                   │          │
  │  │  - Research Agent: [full result text]             │          │
  │  │ From legal:                                      │          │
  │  │  - Legal Agent: [full result text]               │          │
  │  └──────────────────────────────────────────────────┘          │
  │                                                                │
  │  Edges can be conditional:                                     │
  │    def only_if_compliant(state: GraphState) -> bool:           │
  │        return "compliant" in state.results["legal"].text       │
  │                                                                │
  │  Supports: parallel fan-out, fan-in, conditional edges,        │
  │           cycles with loop detection, nested graphs/swarms     │
  └────────────────────────────────────────────────────────────────┘

  CONTEXT ISOLATION: Low — nodes share full execution context.
                     Each node sees all prior nodes' complete results.
  CONTROL FLOW:     Deterministic — edges define the execution order.
                     No autonomous agent decisions about routing.
  SHARED STATE:     GraphState (all completed results) +
                     invocation_state (programmatic).
```

#### Pattern 4: Workflow (deterministic DAG, no cycles)

Similar to Graph but strictly acyclic. Each task receives a curated summary of
its dependencies' results (not the full history). Best for repeatable pipelines
like: intake → compliance-check → document-generation → review.

### Handoff Comparison Matrix

```
┌──────────────────┬───────────────┬───────────────┬───────────────┬───────────────┐
│                  │ Claude SDK    │ Strands       │ Strands       │ Strands       │
│ Dimension        │ Task Tool     │ Agents-as-    │ Swarm         │ Graph         │
│                  │               │ Tools         │               │               │
├──────────────────┼───────────────┼───────────────┼───────────────┼───────────────┤
│ Control flow     │ Supervisor    │ Supervisor    │ Full transfer │ Edge-defined  │
│                  │ retains       │ retains       │ (no return)   │ (deterministic│
├──────────────────┼───────────────┼───────────────┼───────────────┼───────────────┤
│ Context shared   │ None — fresh  │ Query string  │ Curated       │ All prior     │
│ with subagent    │ context only  │ only          │ summary +     │ node results  │
│                  │               │               │ SharedContext  │               │
├──────────────────┼───────────────┼───────────────┼───────────────┼───────────────┤
│ Subagent can     │ No            │ No            │ Yes (handoff  │ No (edges     │
│ route to peers?  │               │               │ to any agent) │ are static)   │
├──────────────────┼───────────────┼───────────────┼───────────────┼───────────────┤
│ Parallel agents  │ No — serial   │ No — serial   │ No — serial   │ Yes — fan-out │
│                  │ delegation    │ tool calls    │ handoffs      │ on edges      │
├──────────────────┼───────────────┼───────────────┼───────────────┼───────────────┤
│ Who decides      │ Supervisor    │ Supervisor    │ Each agent    │ Developer     │
│ routing?         │ LLM           │ LLM           │ autonomously  │ (build-time)  │
├──────────────────┼───────────────┼───────────────┼───────────────┼───────────────┤
│ Session history  │ Not persisted │ Not persisted │ Open issue    │ Open issue    │
│ persistence      │ per subagent  │ per subagent  │ (#867)        │ (#867)        │
├──────────────────┼───────────────┼───────────────┼───────────────┼───────────────┤
│ Best for EAGLE?  │ Current       │ Direct port   │ Future: auto- │ Future: fixed │
│                  │ architecture  │ of current    │ routing flows │ pipelines     │
│                  │               │ pattern       │               │ (doc gen)     │
└──────────────────┴───────────────┴───────────────┴───────────────┴───────────────┘
```

### EAGLE Mapping: Which Handoff Pattern For What?

```
  CURRENT (Claude SDK — Task tool):
    Supervisor ──Task──▶ legal-counsel    ──result──▶ Supervisor
               ──Task──▶ market-intel     ──result──▶ Supervisor
               ──Task──▶ oa-intake        ──result──▶ Supervisor
    (All serial, supervisor-controlled, fresh context each time)

  STRANDS EQUIVALENT — Agents-as-Tools:
    Supervisor ──tool──▶ legal_counsel()  ──return──▶ Supervisor
               ──tool──▶ market_intel()   ──return──▶ Supervisor
               ──tool──▶ oa_intake()      ──return──▶ Supervisor
    (Identical flow, but in-process, no subprocess)

  STRANDS UPGRADE — Swarm (for complex multi-step acquisitions):
    intake ──handoff──▶ market ──handoff──▶ legal ──handoff──▶ tech
    (Agents autonomously decide when to hand off — less supervisor overhead)

  STRANDS UPGRADE — Graph (for document generation pipeline):
    ┌─────────┐     ┌───────────┐     ┌──────────┐     ┌────────┐
    │ intake  │────▶│ compliance│────▶│ doc-gen  │────▶│ review │
    └─────────┘     └───────────┘     └──────────┘     └────────┘
    (Fixed pipeline, parallel where possible, deterministic)
```

---

## 9. Agent Skills: A New Primitive

### What "skills" mean in each ecosystem

The concept of "skills" exists in both ecosystems but means different things:

```
  EAGLE (Claude Agent SDK):                    Strands/AgentSkills.io:

  eagle-plugin/                                my-skills/
  ├── skills/                                  ├── pdf-processing/
  │   ├── oa-intake/                           │   ├── SKILL.md          ← Same format!
  │   │   └── SKILL.md  ← YAML + markdown     │   ├── scripts/
  │   ├── document-generator/                  │   │   └── extract.py
  │   │   └── SKILL.md                         │   └── references/
  │   └── compliance/                          │       └── api-docs.md
  │       └── SKILL.md                         └── web-research/
  └── agents/                                      └── SKILL.md
      ├── supervisor/agent.md
      └── legal-counsel/agent.md

  Loaded: at startup → DynamoDB                Loaded: at startup → system prompt
  Resolved: per-request → AgentDefinition      Resolved: on-demand → prompt injection
  Execution: subprocess subagent               Execution: in-process agent or prompt
```

**Key insight**: EAGLE's `SKILL.md` format is already nearly identical to the
[AgentSkills.io specification](https://agentskills.io/specification). Both use
YAML frontmatter + markdown body. The main difference is in how they're loaded
and executed at runtime.

### AgentSkills.io: The Open Standard

AgentSkills.io (created by Anthropic) defines a portable format for packaging
agent capabilities. Strands adopts this standard through the
[`agent-skills-sdk`](https://pypi.org/project/agent-skills-sdk/) package
and the [`sample-strands-agents-agentskills`](https://github.com/aws-samples/sample-strands-agents-agentskills)
AWS sample.

**SKILL.md format** (AgentSkills.io spec):

```yaml
---
name: oa-intake
description: >
  Guide users through the NCI Office of Acquisitions intake process.
  Use when a user wants to start a new acquisition.
license: Apache-2.0
allowed-tools: Read Bash(python3:*)
metadata:
  author: eagle-team
  version: "1.0"
---

# OA Intake Skill

## Overview
This skill collects acquisition requirements and determines the pathway...

## Step-by-Step Instructions
1. Ask for the acquisition description
2. Determine estimated dollar value
3. Classify acquisition type (simplified, sealed bid, negotiated)
...
```

### Progressive Disclosure: Three-Phase Loading

Skills use a progressive disclosure pattern to minimize token cost:

```
  ┌──────────────────────────────────────────────────────────────┐
  │  PHASE 1 — Metadata (at agent construction)                  │
  │                                                              │
  │  discover_skills("./skills")                                 │
  │  ├── Walk directories, parse YAML frontmatter only           │
  │  └── Return: [{name, description}, ...]                      │
  │                                                              │
  │  generate_skills_prompt(skills)                              │
  │  └── "Available skills:                                      │
  │       - oa-intake: Guide users through acquisition intake    │
  │       - document-generator: Generate acquisition documents   │
  │       - compliance: Check FAR/DFARS compliance"              │
  │                                                              │
  │  Token cost: ~100 tokens per skill (name + description)      │
  │                                                              │
  │  Injected into supervisor's system_prompt at construction    │
  └──────────────────────────────────────────────────────────────┘
                          │
                          │ Agent decides to use "oa-intake" skill
                          ▼
  ┌──────────────────────────────────────────────────────────────┐
  │  PHASE 2 — Instructions (on activation)                      │
  │                                                              │
  │  Agent calls: skill(skill_name="oa-intake")                  │
  │  └── Loads full SKILL.md body into context                   │
  │      (~2,000-5,000 tokens)                                   │
  │                                                              │
  │  Agent now has the complete instructions, examples,          │
  │  step-by-step procedures for the intake skill.               │
  └──────────────────────────────────────────────────────────────┘
                          │
                          │ Agent needs a script or reference doc
                          ▼
  ┌──────────────────────────────────────────────────────────────┐
  │  PHASE 3 — Resources (on demand)                             │
  │                                                              │
  │  Agent reads: scripts/intake_classifier.py                   │
  │  Agent reads: references/far-thresholds.md                   │
  │                                                              │
  │  Individual files loaded only when the agent decides it      │
  │  needs them. Variable token cost.                            │
  └──────────────────────────────────────────────────────────────┘

  TOTAL TOKEN SAVINGS vs. loading everything upfront:
  ┌────────────────────────────┬────────────────┬────────────────┐
  │ Strategy                   │ 16 skills      │ 1 skill active │
  ├────────────────────────────┼────────────────┼────────────────┤
  │ Load all upfront           │ ~36,884 tokens │ ~36,884 tokens │
  │ Progressive disclosure     │  ~1,600 tokens │  ~3,282 tokens │
  │ Savings                    │                │  91% reduction  │
  └────────────────────────────┴────────────────┴────────────────┘
```

### Three Integration Patterns in Strands

```
  PATTERN 1 — File-Based (most flexible)
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Agent has file_read tool → reads SKILL.md directly when needed

  Supervisor: "I need to do an intake. Let me read the oa-intake skill."
      └── file_read("skills/oa-intake/SKILL.md")
          └── Returns full markdown → agent follows instructions


  PATTERN 2 — Tool-Based (structured control)
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Agent has skill() tool → activates a skill by name

  Supervisor: "I need to do an intake."
      └── skill(skill_name="oa-intake")
          └── Returns SKILL.md body → injected into context

  create_skill_tool(skills, "./skills")  ← generates the tool


  PATTERN 3 — Agent-as-Tool / Meta-Tool (complete isolation)
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Each skill spawns an isolated sub-agent with SKILL.md as system prompt

  Supervisor: "I need to do an intake."
      └── use_skill(skill_name="oa-intake", task="Classify this acquisition")
          ├── Spawns: Agent(system_prompt=SKILL.md_body, tools=[...])
          ├── Sub-agent runs in isolation (own context window)
          └── Returns result to supervisor

  create_skill_agent_tool(skills, "./skills", tools=[...])
```

**Pattern 3 is the closest match** to EAGLE's current architecture — each skill
runs in an isolated subagent, just like `AgentDefinition` provides today.

### Skill vs Tool: Key Distinction

```
┌───────────────────┬──────────────────────────┬──────────────────────────┐
│ Dimension         │ Strands Tool (@tool)     │ Agent Skill (SKILL.md)   │
├───────────────────┼──────────────────────────┼──────────────────────────┤
│ Nature            │ Executable Python code   │ Prompt template +        │
│                   │                          │ resources (scripts, docs)│
├───────────────────┼──────────────────────────┼──────────────────────────┤
│ What it IS        │ A function the LLM calls │ Domain expertise the LLM │
│                   │                          │ absorbs into its context │
├───────────────────┼──────────────────────────┼──────────────────────────┤
│ Registration      │ Agent(tools=[my_tool])   │ discover_skills() +      │
│                   │                          │ system prompt injection  │
├───────────────────┼──────────────────────────┼──────────────────────────┤
│ Execution         │ Direct function call     │ Agent follows markdown   │
│                   │ → returns result         │ instructions, may call   │
│                   │                          │ scripts from resources   │
├───────────────────┼──────────────────────────┼──────────────────────────┤
│ Context cost      │ ~50 tokens (tool spec    │ ~100 tokens (metadata)   │
│ when idle         │ always in context)       │ full body loaded on-     │
│                   │                          │ demand (~2-5k tokens)    │
├───────────────────┼──────────────────────────┼──────────────────────────┤
│ Hot-reload        │ ToolWatcher (directory)  │ No built-in —            │
│                   │                          │ re-call discover_skills()│
├───────────────────┼──────────────────────────┼──────────────────────────┤
│ EAGLE equivalent  │ tier-gated tools:        │ eagle-plugin/skills/     │
│                   │ Read, Glob, Grep, Bash   │ and eagle-plugin/agents/ │
└───────────────────┴──────────────────────────┴──────────────────────────┘
```

### EAGLE Compatibility Assessment

EAGLE's current skill format is **95% compatible** with AgentSkills.io:

```
  EAGLE SKILL.md                          AgentSkills.io SKILL.md
  ─────────────                           ─────────────────────────
  ---                                     ---
  name: oa-intake              ✓ SAME     name: oa-intake
  type: skill                  ✗ EXTRA    (not in spec)
  description: Guide users...  ✓ SAME     description: Guide users...
  triggers:                    ✗ EXTRA    (not in spec)
    - "intake"
  tools:                       ≈ SIMILAR  allowed-tools: Read Bash(*)
    - Read
    - Bash
  model: haiku                 ✗ EXTRA    (not in spec)
  ---                                     license: Apache-2.0
                                          metadata:
                                            author: eagle-team
                                            version: "1.0"
                                          ---

  # OA Intake                  ✓ SAME     # OA Intake
  ## Overview                  ✓ SAME     ## Overview
  ...                                     ...
```

**Migration path**: Add `license`, `allowed-tools`, and `metadata` fields to EAGLE's
SKILL.md files. Remove `type`, `triggers`, and `model` (handle these in the registry
layer instead). The markdown body requires zero changes.

### Skills Hot-Reload: Neither SDK Does It Natively

```
  Claude Agent SDK (EAGLE today):
    SKILL.md files → DynamoDB PLUGIN# (seeded at startup)
    → plugin_store.py resolves per-request (60s cache)
    → Prompt injected into AgentDefinition
    ✓ HOT-RELOAD via DynamoDB + cache TTL

  Strands + AgentSkills:
    SKILL.md files → discover_skills() at startup
    → generate_skills_prompt() builds metadata string
    → Injected into system_prompt at Agent construction
    ✗ NO HOT-RELOAD unless you re-discover + rebuild agent

  EAGLE on Strands (recommended hybrid):
    SKILL.md files → DynamoDB PLUGIN# (keep existing infra)
    → Per-request: resolve from DynamoDB (60s cache)
    → Inject into Agent or @tool-wrapped subagent
    ✓ HOT-RELOAD via existing DynamoDB layer
```

The conclusion is the same as Section 3: **your DynamoDB prompt infrastructure
is the hot-reload mechanism**, not the SDK. Carry it forward to any framework.

---

## 10. Recommendation

For EAGLE's specific requirements (multi-tenant, hot-reloadable prompts, supervisor
pattern), the migration path is:

1. **Keep your DynamoDB prompt infrastructure** (`plugin_store.py`, `wspc_store.py`).
   Neither SDK gives you hot-reload for free — your existing 4-layer resolution
   chain is the thing that makes it work. AgentSkills.io's `discover_skills()` has
   no built-in reload mechanism.

2. **If migrating to Strands**: Use the **hybrid pattern** (Option C from Section 3) —
   shared `BedrockModel` at module level, per-request `Agent` construction with
   fresh prompts from DynamoDB. Wrap subagents as `@tool` functions for lazy loading.

3. **Start with agents-as-tools** (Pattern 1 from Section 8). It's the direct port
   of your current supervisor→subagent architecture. Later, consider Swarm for
   complex multi-step acquisitions where agents need to autonomously hand off, or
   Graph for deterministic pipelines like document generation.

4. **Adopt AgentSkills.io format** for your `eagle-plugin/` SKILL.md files. Your
   current format is 95% compatible. Adding `license`, `allowed-tools`, and `metadata`
   fields gives you portability across any framework that supports the standard.

5. **Use Pattern 3 (agent-as-tool/meta-tool)** for skill execution. This preserves
   the context isolation that `AgentDefinition` provides today — each skill runs in
   its own Agent with its own context window.

6. **The subprocess tax is your main pain point today**. Strands eliminates it entirely
   by running in-process. If you're seeing ~200-500ms overhead per query from the
   Node.js CLI subprocess, Strands gives that back.

7. **Don't adopt AgentCore for prompt management**. AgentCore Memory is for
   conversational context, not prompt/config storage. Your DynamoDB single-table
   design already serves this role better for your multi-tenant model.

---

## Sources

### Claude Agent SDK / EAGLE
- `server/app/sdk_agentic_service.py` — Supervisor orchestration, `build_skill_agents()`
- `server/eagle_skill_constants.py` — Auto-discovery loader, DynamoDB seeder
- `server/app/plugin_store.py` — DynamoDB PLUGIN# CRUD with 60s TTL cache
- `eagle-plugin/` — Agent and skill definitions (YAML frontmatter + markdown)

### Strands Agents SDK
- [Strands Agents SDK Documentation](https://strandsagents.com/latest/)
- [Strands GitHub: sdk-python](https://github.com/strands-agents/sdk-python)
- [Strands System Prompts Guide](https://strandsagents.com/latest/documentation/docs/user-guide/concepts/agents/prompts/)
- [Strands Multi-Agent Patterns](https://strandsagents.com/latest/documentation/docs/user-guide/concepts/multi-agent/multi-agent-patterns/)
- [Strands Agents as Tools](https://strandsagents.com/latest/documentation/docs/user-guide/concepts/multi-agent/agents-as-tools/)
- [Strands Swarm Documentation](https://strandsagents.com/latest/documentation/docs/user-guide/concepts/multi-agent/swarm/)
- [Strands Graph Documentation](https://strandsagents.com/latest/documentation/docs/user-guide/concepts/multi-agent/graph/)
- [Strands Bedrock Provider](https://strandsagents.com/latest/documentation/docs/user-guide/concepts/model-providers/amazon-bedrock/)
- [Strands Async Streaming](https://strandsagents.com/latest/documentation/docs/user-guide/concepts/streaming/async-iterators/)
- [Strands Session Management](https://strandsagents.com/latest/documentation/docs/user-guide/concepts/agents/session-management/)
- [Strands Tool Watcher / Hot Reload](https://strandsagents.com/latest/documentation/docs/api-reference/python/tools/watcher/)
- [Strands Swarm API Reference](https://strandsagents.com/latest/documentation/docs/api-reference/python/multiagent/swarm/)
- [Issue #344: Loss of Temporary System Prompt Override](https://github.com/strands-agents/sdk-python/issues/344)
- [Issue #867: Multi-Agent Session Manager](https://github.com/strands-agents/sdk-python/issues/867)
- [AWS Blog: Strands Technical Deep Dive](https://aws.amazon.com/blogs/machine-learning/strands-agents-sdk-a-technical-deep-dive-into-agent-architectures-and-observability/)
- [AWS Blog: Strands 1.0 Announcement](https://aws.amazon.com/blogs/opensource/introducing-strands-agents-1-0-production-ready-multi-agent-orchestration-made-simple/)

### Agent Skills
- [AgentSkills.io Specification](https://agentskills.io/specification)
- [AgentSkills GitHub (Anthropic)](https://github.com/agentskills/agentskills)
- [agent-skills-sdk on PyPI](https://pypi.org/project/agent-skills-sdk/)
- [AWS Sample: Agent Skills for Strands](https://github.com/aws-samples/sample-strands-agents-agentskills)
- [Anthropic Blog: Equipping Agents with Agent Skills](https://claude.com/blog/equipping-agents-for-the-real-world-with-agent-skills)
- [Strands Agent SOPs](https://github.com/strands-agents/agent-sop)
- [AWS Blog: Introducing Strands Agent SOPs](https://aws.amazon.com/blogs/opensource/introducing-strands-agent-sops-natural-language-workflows-for-ai-agents/)

### Infrastructure
- [Amazon Bedrock AgentCore](https://aws.amazon.com/bedrock/agentcore/)
