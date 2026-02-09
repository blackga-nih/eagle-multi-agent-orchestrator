# Multi-Tenant Agent Trace Visualization Frontend

> Integration plan: Use Claude Agent SDK as the single orchestration layer (routed through Bedrock), port orchestrator_3_stream trace visualization into the multi-tenant app.

## Problem

The multi-tenant agent app (`sample-multi-tenant-agent-core-app`) has a vanilla HTML/JS frontend with no real-time trace visibility. Bedrock traces ARE captured (`enableTrace=True`) and parsed in `agentic_service.py`, but they're stored as flat DynamoDB metrics and only accessible via analytics API calls after the fact. Users cannot see reasoning chains, tool calls, or planning steps as they happen.

The orchestrator_3_stream app has a proven real-time trace visualization architecture (Vue 3 + Pinia + WebSocket) that displays thinking blocks, tool use blocks, and agent logs in a 3-column layout.

## Decision: Option C - Claude SDK as Orchestration Layer

### Why Not an Adapter (Option A)

An adapter that translates Bedrock Agent API traces (`orchestrationTrace` dicts) into orchestrator event types would require maintaining two parallel trace formats with different granularity. The Bedrock Agent API (`invoke_agent`) and Claude SDK (`query()`) produce fundamentally different trace structures, and mapping between them is lossy custom glue.

### Why Not OTEL as Primary (Option B)

OTEL solves **ops observability** (latency, error rates, cost anomalies across tenants). The trace visualization we need is **user-facing** (show the user what the agent is thinking/doing in real-time). OTEL spans are not chat events - you'd still need a translator from spans to UI events. OTEL is valuable as a complementary ops layer, not the primary trace transport.

### Why Option C

The orchestrator_3_stream already integrates with Claude Agent SDK. The Claude SDK already routes through Bedrock when `CLAUDE_CODE_USE_BEDROCK=1` (uses `bedrock-runtime` Layer 1 for model inference). We validated this works - subagent traces return with `toolu_bdrk_` prefixes confirming Bedrock backend.

This means:
- **One trace format** - SDK produces typed messages (ThinkingBlock, ToolUseBlock, TextBlock, ResultMessage) regardless of whether Bedrock or Anthropic API is the backend
- **One message processing loop** - The orchestrator's `async for message in query(...)` loop already handles every message type
- **One frontend** - The Vue components already render these event types
- **All multi-tenant features preserved** - Auth, tiers, rate limits, cost tracking are application-level code, not Bedrock Agent API features

## Bedrock API Layer Distinction

```
Layer 1: bedrock-runtime (invoke_model / converse)
  Raw model calls. What Claude SDK uses via CLAUDE_CODE_USE_BEDROCK=1.
  Billing, compliance, VPC endpoints, IAM, CloudWatch - all apply.

Layer 2: bedrock-agent-runtime (invoke_agent)
  Pre-built agents with action groups, KBs, guardrails.
  What the multi-tenant app uses today. Being REPLACED by SDK.

Layer 3: bedrock-agentcore (invoke_agent_runtime)
  Full production runtime with microVM isolation.
  Not relevant to this integration.
```

## Feature Migration Map

### Application-Level Features (UNCHANGED)

These features are FastAPI application code. They do not depend on which AI API is used.

| Feature | File | Status |
|---|---|---|
| Cognito JWT auth | `app/auth.py` | No change |
| Tenant isolation (403 on mismatch) | `app/main.py` | No change |
| Subscription tiers (basic/advanced/premium) | `app/subscription_service.py` | No change |
| Daily/monthly rate limits | `app/subscription_service.py` | No change |
| DynamoDB session tracking | `app/dynamodb_store.py` | No change |
| Cost attribution per tenant/user/service | `app/cost_attribution.py` | Update pricing constants |
| Admin cost reports | `app/admin_cost_service.py` | No change |
| MCP tools gated by tier | `app/weather_mcp_service.py` | No change (tier check is app code) |

### AI-Layer Features (MIGRATED to SDK equivalents)

| Bedrock Agent API Feature | Claude SDK Equivalent | Notes |
|---|---|---|
| `sessionAttributes` (tenant context) | `system_prompt` with tenant context | Same effect - model sees tenant/user/tier |
| `promptSessionAttributes` (per-message) | Included in `system_prompt` or message | More flexible - can change per query |
| Session memory across turns | `ClaudeSDKClient` maintains conversation | Inspectable and modifiable |
| Action Groups (pre-defined tools) | `@tool` decorator + MCP servers | Defined in code, not AWS console |
| Knowledge Base integration | MCP tool calling Bedrock KB API | Explicit rather than opaque |
| Guardrails (content filtering) | SDK hooks (`PreToolUse` can block/modify) | Code-level control |
| `enableTrace=True` trace capture | SDK message types (typed, structured) | ThinkingBlock, ToolUseBlock, etc. |
| Token usage from `modelInvocationOutput` | `ResultMessage.usage` | `input_tokens`, `output_tokens`, `total_cost_usd` |

### Capabilities GAINED (not available in Bedrock Agent API)

| Capability | SDK Feature |
|---|---|
| Subagent orchestration with parallel execution | `AgentDefinition` in `agents={}` |
| Hook system (intercept/modify tool calls) | `PreToolUse`, `PostToolUse`, `SubagentStart/Stop`, `Stop` |
| Per-query budget limits | `max_budget_usd` on `ClaudeAgentOptions` |
| Model selection per subagent | `model` field on `AgentDefinition` |
| Typed trace messages | `ThinkingBlock`, `ToolUseBlock` vs untyped dicts |

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  FRONTEND (Vue 3 + Pinia + TypeScript)                         │
│  Ported from orchestrator_3_stream                             │
│                                                                │
│  ┌────────────┐  ┌──────────────────┐  ┌───────────────────┐  │
│  │  Sidebar   │  │    Chat Panel    │  │   Trace Stream    │  │
│  │            │  │                  │  │                   │  │
│  │ Tenant:    │  │  ThinkingBubble  │  │ [THINKING] ...    │  │
│  │  acme-corp │  │  ToolUseBubble   │  │ [TOOL_USE] ...    │  │
│  │ Tier:      │  │  Text messages   │  │ [SUBAGENT] ...    │  │
│  │  premium   │  │  Streaming       │  │ [AGENT_LOG] ...   │  │
│  │ Tokens:    │  │                  │  │                   │  │
│  │ Cost:      │  │                  │  │                   │  │
│  │ Sessions:  │  │                  │  │                   │  │
│  │ Rate limit │  │                  │  │                   │  │
│  └────────────┘  └──────────────────┘  └───────────────────┘  │
│                                                                │
│  Pinia Store (agentStore.ts)                                   │
│  - chatMessages[], eventStreamEntries[]                        │
│  - tenantId, userId, sessionId, subscriptionTier               │
│  - isTyping, inputTokens, outputTokens, totalCost              │
│                                                                │
│  WebSocket client: ws://host/ws/{tenant_id}/{session_id}       │
│  Auth: JWT token as query param                                │
└────────────────────────────┬───────────────────────────────────┘
                             │
                             │ WebSocket (JSON events)
                             │ Same schema as orchestrator_3_stream:
                             │   chat_stream, orchestrator_chat,
                             │   thinking_block, tool_use_block,
                             │   orchestrator_updated, agent_log
                             │
┌────────────────────────────┴───────────────────────────────────┐
│  BACKEND (FastAPI)                                             │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │  WebSocket Endpoint: /ws/{tenant_id}/{session_id}        │ │
│  │                                                          │ │
│  │  1. Validate JWT (from query param or first message)     │ │
│  │  2. Verify tenant_id matches JWT claims                  │ │
│  │  3. Check subscription tier limits                       │ │
│  │  4. Register connection with websocket_manager            │ │
│  │  5. Listen for chat messages from client                 │ │
│  └──────────────────────────┬───────────────────────────────┘ │
│                              │                                 │
│                              │ user message                    │
│                              ▼                                 │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │  SDK Orchestrator Service (new - replaces agentic_svc)   │ │
│  │                                                          │ │
│  │  options = ClaudeAgentOptions(                            │ │
│  │    model="haiku",                                        │ │
│  │    env={"CLAUDE_CODE_USE_BEDROCK": "1",                  │ │
│  │         "AWS_REGION": "us-east-1"},                      │ │
│  │    system_prompt=f"""                                    │ │
│  │      Tenant: {tenant_id}                                 │ │
│  │      Tier: {subscription_tier}                           │ │
│  │      User: {user_id}                                     │ │
│  │    """,                                                  │ │
│  │    agents={...},          # subagents per use case       │ │
│  │    allowed_tools=[...],   # gated by subscription tier   │ │
│  │    mcp_servers={...},     # KB search, weather, etc.     │ │
│  │    max_budget_usd=TIER_BUDGETS[tier],                    │ │
│  │    permission_mode="bypassPermissions",                  │ │
│  │  )                                                       │ │
│  │                                                          │ │
│  │  async for message in query(prompt, options):            │ │
│  │    ├─ SystemMessage ──────► broadcast chat_stream        │ │
│  │    ├─ AssistantMessage                                   │ │
│  │    │   ├─ TextBlock ──────► broadcast orchestrator_chat  │ │
│  │    │   ├─ ThinkingBlock ──► broadcast thinking_block     │ │
│  │    │   └─ ToolUseBlock ───► broadcast tool_use_block     │ │
│  │    └─ ResultMessage ──────► broadcast orchestrator_upd   │ │
│  │                              + record cost attribution   │ │
│  │                              + increment tier usage      │ │
│  └──────────────────────────────────────────────────────────┘ │
│                              │                                 │
│                              │ SDK calls Bedrock Layer 1       │
│                              ▼                                 │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │  AWS Bedrock (bedrock-runtime)                           │ │
│  │  Model inference via IAM credentials                     │ │
│  │  Billing, CloudWatch, VPC endpoints all apply            │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                │
│  EXISTING APP-LAYER SERVICES (unchanged):                      │
│  ┌──────────┐ ┌──────────┐ ┌───────────┐ ┌───────────────┐   │
│  │ auth.py  │ │ subscrip │ │ dynamodb  │ │ cost_attrib   │   │
│  │ Cognito  │ │ tion_svc │ │ _store    │ │ ution_svc     │   │
│  │ JWT      │ │ tier     │ │ sessions  │ │ per-tenant    │   │
│  │ verify   │ │ limits   │ │ usage     │ │ per-user      │   │
│  └──────────┘ └──────────┘ └───────────┘ └───────────────┘   │
└────────────────────────────────────────────────────────────────┘
```

## Implementation Plan

### Phase 1: SDK Orchestrator Service (Backend)

Replace `agentic_service.py` (Bedrock Agent API) with an SDK-based orchestrator that produces the same message types the orchestrator_3_stream already processes.

**Files to create/modify:**

1. **`app/websocket_manager.py`** (new) - Tenant-scoped connection manager
   - Port from orchestrator_3_stream's `websocket_manager.py`
   - Add tenant isolation: connections keyed by `(tenant_id, session_id)`
   - `connect(websocket, tenant_id, user_id, session_id)` - Register
   - `disconnect(websocket)` - Remove
   - `broadcast_to_session(tenant_id, session_id, event)` - Scoped broadcast
   - Same event types as orchestrator: `chat_stream`, `thinking_block`, `tool_use_block`, `orchestrator_chat`, `orchestrator_updated`, `agent_log`

2. **`app/sdk_orchestrator.py`** (new) - Claude SDK message processing loop
   - Port message processing logic from orchestrator_3_stream's `orchestrator_service.py` (lines 598-912)
   - Build `ClaudeAgentOptions` with tenant context in `system_prompt`
   - Gate `allowed_tools` by subscription tier
   - Set `max_budget_usd` per tier (basic=$0.05, advanced=$0.15, premium=$0.50)
   - Process SDK messages and broadcast via `websocket_manager`
   - On `ResultMessage`: record cost attribution, increment tier usage in DynamoDB

3. **`app/sdk_tools.py`** (new) - Custom tools via `@tool` decorator
   - Port weather tools from `weather_mcp_service.py` as SDK tools
   - Add inventory/product tools (from test suite)
   - Create MCP server via `create_sdk_mcp_server()` for tool groups

4. **`app/sdk_agents.py`** (new) - Subagent definitions
   - Define `AgentDefinition` instances for specialized tasks
   - Example agents: knowledge-search, product-lookup, cost-analyzer
   - Each gets appropriate `tools` and `model` settings

5. **`app/main.py`** (modify) - Add WebSocket endpoint
   ```python
   @app.websocket("/ws/{tenant_id}/{session_id}")
   async def websocket_endpoint(websocket: WebSocket, tenant_id: str, session_id: str):
       # 1. Accept connection
       # 2. Validate JWT from query param ?token=...
       # 3. Verify tenant_id matches JWT claims
       # 4. Check subscription tier limits
       # 5. Register with websocket_manager
       # 6. Listen loop:
       #    - Receive message from client
       #    - Call sdk_orchestrator.process_message(message, tenant_context)
       #    - SDK orchestrator broadcasts events via websocket_manager
   ```

6. **`requirements.txt`** (modify) - Add `claude-agent-sdk>=0.1.29`, `websockets`

### Phase 2: Vue Frontend

Port orchestrator_3_stream Vue components with multi-tenant additions.

**Directory structure:**
```
frontend-vue/
├── src/
│   ├── App.vue
│   ├── main.ts
│   ├── stores/
│   │   └── agentStore.ts              # From orchestratorStore.ts
│   ├── services/
│   │   ├── chatService.ts             # WebSocket client
│   │   └── authService.ts             # Cognito JWT management
│   ├── components/
│   │   ├── chat/
│   │   │   ├── ChatPanel.vue          # From OrchestratorChat.vue
│   │   │   ├── ThinkingBubble.vue     # Direct port
│   │   │   └── ToolUseBubble.vue      # Direct port
│   │   ├── traces/
│   │   │   ├── TraceStream.vue        # From EventStream.vue
│   │   │   ├── TraceRow.vue           # From AgentLogRow.vue
│   │   │   └── ToolUseRow.vue         # From AgentToolUseBlockRow.vue
│   │   ├── layout/
│   │   │   ├── AppHeader.vue          # Tenant + tier badge
│   │   │   └── ThreeColumnLayout.vue
│   │   ├── sidebar/
│   │   │   ├── TenantInfo.vue         # Tenant, tier, tokens, cost
│   │   │   ├── SessionSwitcher.vue    # Active sessions list
│   │   │   └── RateLimitBar.vue       # Daily/monthly usage bars
│   │   └── auth/
│   │       └── CognitoLogin.vue       # Port from existing index.html
│   └── types/
│       └── events.ts                  # Event type definitions
├── package.json
├── vite.config.ts
└── tsconfig.json
```

**Components: port mapping**

| Orchestrator Component | New Component | Modifications |
|---|---|---|
| `OrchestratorChat.vue` | `ChatPanel.vue` | Add tenant header, tier badge |
| `ThinkingBubble.vue` | `ThinkingBubble.vue` | Direct port (no changes) |
| `ToolUseBubble.vue` | `ToolUseBubble.vue` | Direct port (no changes) |
| `EventStream.vue` | `TraceStream.vue` | Add subagent trace display |
| `AgentLogRow.vue` | `TraceRow.vue` | Add subagent context indicator |
| `AgentToolUseBlockRow.vue` | `ToolUseRow.vue` | Direct port |
| (new) | `TenantInfo.vue` | Tenant/tier/cost sidebar |
| (new) | `SessionSwitcher.vue` | Session list with create/switch |
| (new) | `RateLimitBar.vue` | Usage vs limit progress bars |
| (new) | `CognitoLogin.vue` | Port from vanilla JS index.html |

**Pinia store (`agentStore.ts`) - adapted from `orchestratorStore.ts`:**

State additions beyond orchestrator:
```typescript
// Multi-tenant state
tenantId: string
userId: string
sessionId: string
subscriptionTier: 'basic' | 'advanced' | 'premium'

// Rate limit state (from GET /api/tenants/{id}/subscription)
dailyUsage: number
dailyLimit: number
monthlyUsage: number
monthlyLimit: number

// Session management
sessions: TenantSession[]
```

Event handlers (same as orchestrator - no changes needed):
```typescript
onMessage(event) {
  switch(event.type) {
    case 'chat_stream':          // Streaming text chunks
    case 'orchestrator_chat':    // Complete messages
    case 'thinking_block':       // SDK ThinkingBlock → display
    case 'tool_use_block':       // SDK ToolUseBlock → display
    case 'orchestrator_updated': // ResultMessage tokens/cost
    case 'agent_log':            // Subagent activity
  }
}
```

### Phase 3: Multi-Tenant UI Features

Features specific to multi-tenant context (not in orchestrator):

1. **Tenant-scoped WebSocket rooms** - Backend broadcasts only to connections matching `(tenant_id, session_id)`
2. **Tier-aware tool display** - Basic tier sees no MCP tools in trace; advanced/premium see full tool traces
3. **Cost ticker** - Real-time cost from `ResultMessage.total_cost_usd`, accumulated per session
4. **Session switcher** - REST call to `GET /api/tenants/{id}/sessions`, create via `POST /api/sessions`
5. **Rate limit bars** - REST call to `GET /api/tenants/{id}/subscription`, progress bar UI
6. **Admin trace view** - Admin JWT (Cognito group) can connect to any tenant's WebSocket (read-only)

### Phase 4: OTEL Observability (Optional, Ops-Layer)

Add OTEL instrumentation for ops dashboards. Complementary to user-facing traces.

```
SDK message loop
  │
  ├──► WebSocket broadcast (user-facing trace UI)
  │
  └──► OTEL span export (ops dashboards)
       │
       ├─ gen_ai.chat.completions span
       │   attrs: model, tenant_id, tier, input_tokens, output_tokens
       │
       ├─ tool_call span (child)
       │   attrs: tool_name, duration_ms
       │
       └─ subagent span (child)
           attrs: agent_name, model, parent_tool_use_id
```

OTEL is good for:
- Latency percentiles (p50/p95/p99) per tenant/tier
- Error rates across tenants
- Token usage aggregation and cost anomaly detection
- SLA monitoring per subscription tier
- Cross-service distributed tracing (FastAPI → SDK → Bedrock)

OTEL is NOT for:
- Real-time "thinking" display in chat
- Tool call visualization in the chat UI
- Streaming text to users

**Files:**
- `app/otel_instrumentation.py` (new) - Span creation from SDK messages
- Configure exporter: CloudWatch (AWS-native) or Jaeger/Tempo (self-hosted)

## Tenant Context Injection

**Today (Bedrock Agent API - Layer 2):**
```python
session_state = {
    "sessionAttributes": {
        "tenant_id": "acme-corp",
        "user_id": "user-001",
        "subscription_tier": "premium"
    },
    "promptSessionAttributes": {
        "tenant_context": "acme-corp premium user"
    }
}
response = bedrock_agent_runtime.invoke_agent(
    agentId=AGENT_ID,
    sessionState=session_state,
    enableTrace=True,
    ...
)
```

**Option C (Claude SDK → Bedrock Layer 1):**
```python
options = ClaudeAgentOptions(
    model="haiku",
    env={"CLAUDE_CODE_USE_BEDROCK": "1", "AWS_REGION": "us-east-1"},
    system_prompt=f"""
        You are an AI assistant for tenant '{tenant_id}'.
        Subscription tier: {subscription_tier}.
        Current user: {user_id}.
        Session: {session_id}.
        Respond according to {subscription_tier} tier guidelines.
    """,
    agents={
        "product-lookup": AgentDefinition(
            description="Look up products in the catalog",
            tools=["mcp__inventory__lookup_product"],
            model="haiku",
        ),
        "knowledge-search": AgentDefinition(
            description="Search knowledge bases",
            tools=["mcp__kb__search"],
            model="haiku",
        ),
    },
    allowed_tools=TIER_TOOLS[subscription_tier],
    permission_mode="bypassPermissions",
    max_turns=10,
    max_budget_usd=TIER_BUDGETS[subscription_tier],
)

async for message in query(prompt=user_message, options=options):
    # Typed messages - same as orchestrator_3_stream handles
    await process_and_broadcast(message, tenant_id, session_id)
```

## Session Management

Bedrock Agent API maintains session memory server-side. The SDK supports stateless multi-turn via `resume`:

### Stateless `query(resume=session_id)` (Recommended)

The SDK's `query()` function accepts a `resume` parameter that restores a previous session's full context from disk. This makes the server completely stateless between turns - no subprocess pool, no connection management, no eviction timers. Same pattern as ChatGPT.

```python
# First turn: create new session
session_id = None

async for message in query(prompt=user_message, options=options):
    # Capture session_id from init SystemMessage
    if hasattr(message, 'subtype') and message.subtype == 'init':
        session_id = message.session_id  # e.g. "abc123"
    await process_and_broadcast(message, tenant_id, session_id)

# Store session_id in DynamoDB for the tenant
await store.save_session_id(tenant_id, user_id, session_id)

# Subsequent turns: resume existing session
options_with_resume = ClaudeAgentOptions(
    **base_options,
    resume=session_id,  # SDK loads full context from disk
)

async for message in query(prompt=follow_up_message, options=options_with_resume):
    await process_and_broadcast(message, tenant_id, session_id)
```

**How it works internally:**
1. SDK saves session transcripts to `~/.claude/projects/<session_id>.jsonl`
2. On `resume=session_id`, SDK reads the JSONL and reconstructs full conversation
3. New messages are appended to the same JSONL
4. Server is stateless - no subprocess pool, no connection management

**CRITICAL: `system_prompt` is NOT preserved across resume.** The `system_prompt` is part of `ClaudeAgentOptions`, not the conversation transcript. On each resumed query, you MUST re-provide the system_prompt with tenant context. This is actually a security benefit for multi-tenant - tenant context is always explicitly set, never relied on from memory.

**Multi-tenant session mapping:**
```
DynamoDB: tenant-sessions
  PK: tenant_id#user_id
  SK: session_id
  Attrs: sdk_session_id, created_at, last_activity, message_count
```

**Session branching** (premium tier feature):
```python
# Fork creates a new session from existing conversation
options_fork = ClaudeAgentOptions(
    **base_options,
    resume=session_id,
    fork_session=True,  # Creates new branch
)
```

**Known limitation (Issue #109):** No programmatic API to read historical messages from a resumed session. Workaround: maintain a DynamoDB message mirror (see Plan D incremental adoption).

## Three-Column Layout

```
+-------------------+-------------------------+--------------------+
|   Tenant Info     |      Chat Panel         |   Trace Stream     |
|                   |                         |                    |
| Tenant: acme-corp | [User] What products    | [THINKING] I need  |
| Tier: premium     |   do you have?          |   to look up the   |
| User: user-001    |                         |   product catalog  |
|                   | [Agent] Let me look     |   to find...       |
| Tokens            |   that up for you.      |                    |
|  In:  1,247       |                         | [TOOL_USE]         |
|  Out: 412         |   [ThinkingBubble]      |   lookup_product   |
| Cost: $0.0024     |   I need to search...   |   {name: "widget"} |
|                   |                         |                    |
| ─── Rate Limits ──|   [ToolUseBubble]       | [SUBAGENT]         |
| Daily:  ████░ 12  |   lookup_product        |   product-lookup   |
|         /1000     |   {name: "widget pro"}  |   started (haiku)  |
| Monthly:████░ 45  |                         |                    |
|         /25000    |   I found Widget Pro    | [AGENT_LOG]        |
|                   |   at $29.99 with 150    |   product-lookup   |
| ─── Sessions ─────|   units in stock.       |   completed        |
|  > abc123 (now)   |                         |   3 tool calls     |
|    def456         |                         |                    |
|    ghi789         |                         | [UPDATED]          |
|  [+ New Session]  | [_______________] Send  |   +150 in / +42 out|
+-------------------+-------------------------+--------------------+
```

## File Dependency Order

```
Phase 1 (Backend - SDK Orchestrator):
  1. requirements.txt              (add claude-agent-sdk, websockets)
  2. app/websocket_manager.py      (no deps - port from orchestrator)
  3. app/sdk_tools.py              (no deps - @tool definitions)
  4. app/sdk_agents.py             (depends on sdk_tools)
  5. app/sdk_orchestrator.py       (depends on websocket_manager, sdk_tools, sdk_agents)
  6. app/main.py                   (modify: add WS endpoint, wire sdk_orchestrator)

Phase 2 (Frontend - Vue):
  7.  frontend-vue/package.json + vite.config.ts + tsconfig.json
  8.  frontend-vue/src/types/events.ts
  9.  frontend-vue/src/services/authService.ts
  10. frontend-vue/src/services/chatService.ts
  11. frontend-vue/src/stores/agentStore.ts
  12. frontend-vue/src/components/chat/       (ChatPanel, ThinkingBubble, ToolUseBubble)
  13. frontend-vue/src/components/traces/     (TraceStream, TraceRow, ToolUseRow)
  14. frontend-vue/src/components/sidebar/    (TenantInfo, SessionSwitcher, RateLimitBar)
  15. frontend-vue/src/components/auth/       (CognitoLogin)
  16. frontend-vue/src/components/layout/     (AppHeader, ThreeColumnLayout)
  17. frontend-vue/src/App.vue + main.ts

Phase 3 (Multi-Tenant UI):
  18. Admin trace view (read-only WS for admin JWT)
  19. Tier-gated tool display

Phase 4 (OTEL - Optional):
  20. app/otel_instrumentation.py
  21. OTEL collector configuration
```

## SDK Message Structure (Validated)

From diagnostic testing against Bedrock (2026-02-04):

```
SystemMessage
  .data: dict  → {"session_id": "uuid", "type": "system", "subtype": "init", "tools": [...]}
  .subtype: "init"

AssistantMessage
  .content: list[TextBlock | ToolUseBlock | ThinkingBlock]
  .model: "claude-haiku-4-5-20251001"
  .parent_tool_use_id: str | None  (set inside subagent context)
  .error: None | str

UserMessage (tool results)
  .content: list[ToolResultBlock]
  .parent_tool_use_id: str | None
  .uuid: str

ResultMessage
  .session_id: str  (same as SystemMessage.data.session_id)
  .result: str  (final response text)
  .total_cost_usd: float  (e.g., 0.001646)
  .usage: dict  (NOT an object)
    {"input_tokens": 3, "cache_creation_input_tokens": 0,
     "cache_read_input_tokens": 14327, "output_tokens": 42, ...}
  .duration_ms: int
  .num_turns: int
  .subtype: "success"

Block Types (identified by class name, NOT by .type attribute):
  TextBlock     → .text: str
  ToolUseBlock  → .name: str, .id: str ("toolu_bdrk_..." on Bedrock), .input: dict
  ToolResultBlock → .tool_use_id: str, .content: str, .is_error: bool
  ThinkingBlock → .thinking: str (or .text: str)
```

**Frontend event mapping:**
```
SystemMessage/init      → capture session_id
AssistantMessage
  TextBlock             → broadcast "orchestrator_chat"
  ThinkingBlock         → broadcast "thinking_block"
  ToolUseBlock          → broadcast "tool_use_block"
  ToolUseBlock(Task)    → broadcast "agent_log" (subagent start)
UserMessage
  ToolResultBlock       → broadcast "tool_use_block" (result)
ResultMessage           → broadcast "orchestrator_updated" + record cost
```

## Validation Strategy

1. **SDK on Bedrock**: Run `test_claude_agent_sdk.py` Test 1 (subagents) - confirm `toolu_bdrk_` prefix in traces
2. **WebSocket**: Connect via wscat with JWT, send message, verify events arrive scoped to tenant
3. **Trace display**: Send chat message in Vue UI, observe ThinkingBubble and ToolUseBubble render in real-time
4. **Multi-tenant isolation**: Two browser tabs with different tenant JWTs, verify no cross-tenant event leakage
5. **Rate limits**: Hit daily limit on basic tier, verify 429 response and UI indicator
6. **Cost tracking**: Send multiple messages, verify cost ticker increments match `ResultMessage.total_cost_usd`
7. **Session persistence**: Send message, refresh page, reconnect - verify conversation history loads

## Success Criteria

- Real-time trace display as SDK messages stream (ThinkingBlock, ToolUseBlock visible immediately)
- Subagent traces display with agent name and parent context
- Token/cost counter updates live from `ResultMessage.usage`
- All existing multi-tenant features work (auth, tiers, limits, cost attribution)
- Tenant isolation: no cross-tenant trace or message visibility
- Subscription tier correctly gates tool access and budget limits
- Session state maintained across page refreshes via `query(resume=session_id)`
