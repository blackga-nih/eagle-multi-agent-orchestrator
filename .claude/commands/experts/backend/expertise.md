---
type: expert-file
parent: "[[backend/_index]]"
file-type: expertise
human_reviewed: false
tags: [expert-file, mental-model, backend, agentic-service, eagle, aws, s3, dynamodb, cloudwatch]
last_updated: 2026-03-16T00:00:00
---

# Backend Expertise (Complete Mental Model)

> **Sources**: server/app/*.py, server/app/routes/*.py, server/app/stores/*.py, server/eagle_skill_constants.py, infrastructure/cdk-eagle/lib/*.ts

---

## Part 1: Architecture Overview

### File Layout

```
server/app/
├── main.py                  # FastAPI app (v4.0.0), CORS, router registration, telemetry middleware
├── strands_agentic_service.py # PRIMARY orchestrator — Strands Agents SDK, supervisor + subagents (BedrockModel)
├── eagle_state.py           # Unified agent state schema (13 fields), normalize(), apply_event(), stamp()
├── streaming_routes.py      # SSE streaming router — stream_generator(), create_streaming_router()
├── stream_protocol.py       # MultiAgentStreamWriter — write_text/tool_use/metadata/reasoning/complete/error
├── cognito_auth.py          # Cognito JWT auth, UserContext, DEV_MODE fallback
├── auth.py                  # Legacy auth (get_current_user) — still active, imported by admin_auth.py + _deps.py
├── models.py                # Pydantic models (ChatMessage, TenantContext, etc.)
├── package_context_service.py # PackageContext resolution — resolve_context(), set_active_package()
├── health_checks.py         # check_knowledge_base_health() — knowledge base + document bucket checks
├── document_export.py       # DOCX/PDF/Markdown export
├── admin_service.py         # Dashboard stats, rate limiting, cost tracking
├── admin_auth.py            # Admin group auth (imports from auth.py — NOT yet migrated to cognito_auth)
├── admin_cost_service.py    # 4-level cost reports (tenant, user, service, comprehensive)
├── subscription_service.py  # Tier-based limits (SubscriptionTier enum)
├── cost_attribution.py      # Per-tenant/user cost attribution
├── eagle_skill_constants.py # (server/) Auto-discovery: walks eagle-plugin/, exports AGENTS, SKILLS, PLUGIN_CONTENTS
│
├── routes/                  # Extracted route modules (split from monolithic main.py)
│   ├── _deps.py             # Shared deps: get_user_from_header, get_session_context, USE_PERSISTENT_SESSIONS,
│   │                        #   S3_BUCKET, TELEMETRY_LOG, API_REQUEST_LOG, log_telemetry, log_api_request
│   ├── chat.py              # POST /api/chat — REST chat endpoint; exposes SESSIONS in-memory fallback dict
│   ├── sessions.py          # Session CRUD + sub-routes: /messages /summary /documents /audit-logs /clear
│   ├── documents.py         # Document export and S3 browser endpoints
│   ├── admin.py             # /api/admin/* — dashboard, costs, rate limits
│   ├── packages.py          # /api/packages/* — package CRUD, workflow, approval chain
│   ├── workspaces.py        # /api/workspace/* — workspace CRUD + wspc_store resolution
│   ├── tenants.py           # /api/tenants/* — tenant costs, usage
│   ├── user.py              # /api/user/* — user preferences
│   ├── templates.py         # /api/templates/* — acquisition document templates
│   ├── skills.py            # /api/skills/* — user-created SKILL# items
│   ├── misc.py              # /api/telemetry, /api/tools, /ws/chat WebSocket, /api/health,
│   │                        #   /api/admin/request-log
│   └── traces.py            # /api/traces/* — Langfuse trace story + session list proxy
│
├── stores/                  # DynamoDB store modules (renamed from flat server/app/*.py)
│   ├── __init__.py
│   ├── session_store.py     # Unified DynamoDB session/message/usage store (eagle table)
│   ├── approval_store.py    # Approval chain + decision recording
│   ├── audit_store.py       # Audit event writer
│   ├── config_store.py      # Tenant config key-value store
│   ├── document_store.py    # Package document versioning + finalization
│   ├── feedback_store.py    # User feedback store
│   ├── package_store.py     # Acquisition package CRUD + workflow (submit/approve/close) + get_package_checklist()
│   ├── plugin_store.py      # DynamoDB PLUGIN# entity hot-reload store
│   ├── pref_store.py        # User preferences
│   ├── prompt_store.py      # Tenant prompt overrides (PROMPT# in eagle table)
│   ├── reasoning_store.py   # ReasoningLog — per-turn reasoning accumulation + DynamoDB save
│   ├── skill_store.py       # User-created SKILL# items (publish/review lifecycle)
│   ├── template_store.py    # Acquisition document templates
│   ├── test_result_store.py # Test result persistence
│   ├── workspace_config_store.py # Workspace config overrides
│   └── workspace_store.py   # Per-user workspace CRUD (Default workspace auto-provision)
│
├── agentcore/               # AgentCore integration modules
│   └── observability.py     # record_metric() — CloudWatch EMF metric emission
│
├── telemetry/
│   └── log_context.py       # configure_logging(), set_log_context() — structured logging context
│
└── tools/                   # Reusable tool modules
    ├── knowledge_tools.py   # KNOWLEDGE_FETCH_TOOL, KNOWLEDGE_SEARCH_TOOL (Strands @tool)
    └── contract_matrix.py   # query_contract_matrix() — compliance matrix lookup
```

### Tech Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Framework | FastAPI 4.0.0 | REST + WebSocket + SSE |
| LLM SDK | Strands Agents SDK | BedrockModel (boto3-native), supervisor + subagents |
| LLM Fallback | `anthropic` Python SDK | Direct API fallback when Strands/Bedrock unavailable |
| AWS SDK | `boto3` | S3, DynamoDB, CloudWatch, Cognito, Bedrock Runtime |
| Runtime | Python 3.11+ | `str | None` union syntax used |
| Async | `asyncio` | `sdk_query_streaming()` is an async generator; stream_generator() yields SSE |
| Auth | Cognito JWT | `cognito_auth.py` with DEV_MODE fallback; `auth.py` still active for legacy routes |
| Persistence | DynamoDB `eagle` table | Single-table design via `stores/session_store.py` |
| Tracing | Langfuse OTEL | `StrandsTelemetry().setup_otlp_exporter()` — silent no-op if no LANGFUSE_PUBLIC_KEY |
| Logging | `logging` | Logger: `eagle`, `eagle.strands_agent`, `eagle.state`, `eagle.traces` |
| Metrics | CloudWatch EMF | `agentcore/observability.py` — `record_metric()` emits EMF metrics |

### Entry Points

| Function | File | Purpose |
|----------|------|---------|
| `sdk_query_streaming()` | strands_agentic_service.py | PRIMARY: async generator — supervisor + specialist subagents via Strands SDK |
| `sdk_query()` | strands_agentic_service.py | Non-streaming variant (used by WebSocket endpoint) |
| `stream_generator()` | streaming_routes.py | SSE event generator; consumes sdk_query_streaming(), persists to DynamoDB |
| `create_streaming_router()` | streaming_routes.py | Factory: returns APIRouter with /api/chat/stream + /api/health + /api/health/ready |
| `api_chat()` | routes/chat.py | REST chat — calls sdk_query() |
| `websocket_chat()` | routes/misc.py | WebSocket streaming chat |

### Configuration

```python
# strands_agentic_service.py (PRIMARY orchestrator)
MODEL = os.getenv("EAGLE_SDK_MODEL", "haiku")  # model alias used with BedrockModel

# main.py feature flags (via _deps.py)
USE_PERSISTENT_SESSIONS = os.getenv("USE_PERSISTENT_SESSIONS", "true").lower() == "true"
REQUIRE_AUTH = os.getenv("REQUIRE_AUTH", "false").lower() == "true"

# Langfuse OTEL (main.py _setup_langfuse())
LANGFUSE_PUBLIC_KEY  # if absent → silent no-op
LANGFUSE_SECRET_KEY
LANGFUSE_OTEL_ENDPOINT  # default: https://us.cloud.langfuse.com/api/public/otel
LANGFUSE_HOST           # default: https://us.cloud.langfuse.com
```

### Deployment (ECS Fargate via CDK)

```
Dockerfile.backend: python:3.11-slim
  COPY server/requirements.txt → pip install
  COPY server/app/, run.py, config.py, eagle_skill_constants.py
  COPY eagle-plugin/ → ../eagle-plugin/
  EXPOSE 8000
  CMD: uvicorn app.main:app --host 0.0.0.0 --port 8000

ECS Service (EagleComputeStack):
  CPU: 0.5 vCPU | Memory: 1024 MiB
  Port: 8000
  ALB: Internal (not internet-facing)
  Health: /api/health (30s interval)
  Scaling: 1-3 tasks, target tracking

Environment Variables (from CDK):
  ANTHROPIC_API_KEY  → Secrets Manager
  EAGLE_TABLE        → "eagle" (DynamoDB)
  S3_BUCKET          → "nci-documents"
  AWS_REGION         → "us-east-1"
  LOG_GROUP          → "/eagle/app"
  EAGLE_SDK_MODEL    → model alias for strands_agentic_service (e.g. "haiku")
  USE_PERSISTENT_SESSIONS → "true"
  REQUIRE_AUTH       → "false" (dev) / "true" (prod)
  LANGFUSE_PUBLIC_KEY  → (optional) Langfuse OTEL tracing
  LANGFUSE_SECRET_KEY  → (optional)
```

---

## Part 2: Tool Dispatch System

### TOOL_DISPATCH (strands_agentic_service.py)

The `TOOL_DISPATCH` dict is the authoritative registry mapping tool names to handler functions. It is used by `execute_tool()` which is the synchronous dispatch entry point for both the test suite and direct callers.

```python
TOOL_DISPATCH = {
    "s3_document_ops":  _exec_s3_document_ops,
    "dynamodb_intake":  _exec_dynamodb_intake,
    "cloudwatch_logs":  _exec_cloudwatch_logs,
    "search_far":       _exec_search_far,
    "create_document":  _exec_create_document,
    "get_intake_status": _exec_get_intake_status,
    "intake_workflow":  _exec_intake_workflow,
    "query_compliance_matrix": _exec_query_compliance_matrix,
    "manage_skills":    _exec_manage_skills,
    "manage_prompts":   _exec_manage_prompts,
    "manage_templates": _exec_manage_templates,
    "workspace_memory": _exec_workspace_memory,
    "web_search":       _exec_web_search,
    "browse_url":       _exec_browse_url,
    "code_execute":     _exec_code_execute,
}
```

### TOOLS_NEEDING_SESSION

```python
TOOLS_NEEDING_SESSION = {"s3_document_ops", "create_document", "get_intake_status", "workspace_memory"}
```

These tools receive `session_id` as a third argument to enable per-user S3 prefix scoping.

### execute_tool() Flow

```
execute_tool(tool_name, tool_input, session_id)
  |-- tenant_id = _extract_tenant_id(session_id)
  |-- handler = TOOL_DISPATCH.get(tool_name)
  |-- if tool_name in TOOLS_NEEDING_SESSION:
  |       result = handler(tool_input, tenant_id, session_id)
  |   else:
  |       result = handler(tool_input, tenant_id)
  |-- return json.dumps(result, indent=2, default=str)
  |
  |-- On exception: return JSON error with tool name + suggestion
  |-- On unknown tool: return JSON {"error": "Unknown tool: {name}"}
```

### Handler Signatures

| Handler | Signature |
|---------|-----------|
| `_exec_s3_document_ops` | `(params, tenant_id, session_id)` |
| `_exec_dynamodb_intake` | `(params, tenant_id)` |
| `_exec_cloudwatch_logs` | `(params, tenant_id)` |
| `_exec_search_far` | `(params, tenant_id)` |
| `_exec_create_document` | `(params, tenant_id, session_id)` |
| `_exec_get_intake_status` | `(params, tenant_id, session_id)` |
| `_exec_intake_workflow` | `(params, tenant_id)` |

### EAGLE_TOOLS List

`EAGLE_TOOLS` in `strands_agentic_service.py` is the Anthropic/Strands tool_use schema list used for the supervisor and legacy chat endpoints. Each entry has `name`, `description`, `input_schema`. The `update_state` tool is included here and is the mechanism by which the supervisor pushes SSE metadata events to the frontend.

---

## Part 3: Strands Agentic Service (strands_agentic_service.py) — PRIMARY

### Architecture

```
sdk_query_streaming() / sdk_query()
  |-- _build_supervisor()   → Agent() with BedrockModel, specialist @tool subagents
  |-- build_skill_agents()  → list of @tool-wrapped Agent() from eagle-plugin/
  |-- build_supervisor_prompt() → supervisor system prompt with subagent list + state push rules
  |-- EagleSSEHookProvider  → AfterInvocationEvent flushes agent_state to DynamoDB
  |-- result_queue (asyncio.Queue) → update_state tool pushes metadata events here
  |-- Agent()(prompt) → sync call in thread → adapter yields chunks to SSE generator
```

### EagleSSEHookProvider

`EagleSSEHookProvider(HookProvider)` in `strands_agentic_service.py` registers:
- `AfterInvocationEvent` — persists `agent.state` to DynamoDB via `session_store.update_session()` after every supervisor turn
- `AfterModelCallEvent` / `AfterToolCallEvent` / `BeforeToolCallEvent` — telemetry hooks for tool timing

Parameters: `tenant_id`, `user_id`, `session_id` — defaults so call sites that omit them degrade gracefully.

### Tier-Gated Tool Access (TIER_TOOLS)

```python
TIER_TOOLS = {
    "basic":    [],
    "advanced": ["Read", "Glob", "Grep", "s3_document_ops", "create_document"],
    "premium":  ["Read", "Glob", "Grep", "Bash", "s3_document_ops",
                 "dynamodb_intake", "cloudwatch_logs", "create_document",
                 "get_intake_status", "intake_workflow", "search_far"],
}
```

### Tier Budgets

```python
TIER_BUDGETS = {
    "basic": 0.10,
    "advanced": 0.25,
    "premium": 0.75,
}
```

### Workspace Resolution (4-Layer Chain)

1. `wspc_store.resolve_skill(tenant_id, user_id, workspace_id, name)` — workspace override
2. Fall back to `PLUGIN_CONTENTS[skill_key]["body"]` — bundled eagle-plugin/ content
3. `skill_store.list_active_skills(tenant_id)` — user-created SKILL# items (override bundled when same name)
4. Supervisor prompt resolved via `wspc_store.resolve_agent(tenant_id, user_id, workspace_id, "supervisor")`

### SKILL_AGENT_REGISTRY

Built at module load from `eagle_skill_constants.AGENTS + SKILLS`, filtered by `plugin.json` active lists. Supervisor agent is excluded (it orchestrates, not a subagent). Falls back to DynamoDB `PLUGIN#manifest` when available, else bundled `plugin.json`.

---

## Part 4: Eagle State (eagle_state.py)

### Schema (13 Fields)

`eagle_state.py` is the single source of truth for the supervisor agent_state schema. All fields are defined in `_DEFAULTS`:

```python
_DEFAULTS: dict = {
    "schema_version": "1.0",
    "phase": "intake",             # intake | analysis | drafting | review | complete
    "previous_phase": None,
    "package_id": None,            # PKG-YYYY-NNNN
    "required_documents": [],      # ["sow", "igce", "market_research", ...]
    "completed_documents": [],     # subset of required that are done
    "document_versions": {},       # {doc_type: {document_id, version, s3_key}}
    "compliance_alerts": [],       # [{severity, items: [{name, note}]}]
    "validation_results": [],      # [{doc_type, action, reason, far_citation}]
    "turn_count": 0,
    "last_updated": None,          # ISO-8601
    "session_id": None,
    "specialist_summaries": {},    # {skill_name: truncated_text[:3000]} — persists across turns
}
```

### Key Functions

| Function | Signature | Purpose |
|----------|-----------|---------|
| `normalize(state)` | `dict|None → dict` | Fill missing keys from `_DEFAULTS`. Never mutates input. Unknown keys preserved. |
| `apply_event(state, state_type, params)` | `dict, str, dict → dict` | Pure — returns new normalized state with event applied. Single dispatch table for all state transitions. |
| `stamp(state)` | `dict → dict` | Return state with `last_updated` set to UTC ISO-8601. Pure. |
| `to_trace_attrs(state, *, tenant_id, user_id, tier, session_id)` | `dict → dict` | Build OTEL/Langfuse span attributes. Includes `session.id` for Langfuse session grouping. |
| `to_cw_payload(state)` | `dict → dict` | Build CloudWatch data payload for `agent.state_flush` events. |

### apply_event() State Machine

`apply_event()` is the canonical handler for each `state_type`. Callers should always use this — never mutate state directly:

| `state_type` | What it does |
|-------------|--------------|
| `phase_change` | Sets `previous_phase = phase`, updates `phase`, optionally updates `package_id` |
| `document_ready` | Appends `doc_type` to `completed_documents` (dedup), writes `document_versions[doc_type]`, optionally updates `package_id` |
| `checklist_update` | Replaces `required_documents` and `completed_documents` from `params.checklist`, optionally updates `package_id` |
| `compliance_alert` | Appends `{severity, items}` to `compliance_alerts` |
| `document_validation` | Appends `{doc_type, action, reason, far_citation}` to `validation_results` |
| unknown | Logs warning, returns state unchanged |

### How update_state Tool Calls apply_event()

The `update_state` Strands `@tool` in `strands_agentic_service.py` (built by `_make_update_state_tool()`):
1. Parses the JSON `params` string
2. Builds a `payload` dict with `state_type` + type-specific fields (auto-fetches checklist from `package_store` when `package_id` is present)
3. Calls `apply_event(current_state, state_type, parsed)` and merges the result into `agent.state` (in-place via `dict.update`)
4. Pushes `{"type": "metadata", "content": payload}` to `result_queue` (asyncio.Queue) so the SSE generator can yield it to the frontend
5. Returns `{"ok": True, "state_type": state_type, "pushed": True}`

The supervisor prompt instructs the model when to call `update_state` (mandatory after `create_document`, `query_compliance_matrix`, phase transitions, and compliance findings).

---

## Part 5: SSE Streaming Pipeline (streaming_routes.py)

### stream_generator() Flow

```
stream_generator(message, tenant_id, user_id, tier, subscription_service, session_id, messages, package_context)
  |
  |-- Persist user message to DynamoDB (add_message)
  |-- yield initial text SSE (connection handshake)
  |-- _sdk_with_keepalive() wraps sdk_query_streaming():
  |     - yields {"type": "_keepalive"} every KEEPALIVE_INTERVAL=20s
  |     - ALB idle timeout raised to 300s; keepalive keeps connection alive
  |
  |-- For each chunk from sdk_query_streaming():
  |     chunk_type == "_keepalive"    → yield ": keepalive\n\n" (SSE comment)
  |     chunk_type == "text"          → full_response_parts.append(); write_text(); yield SSE
  |     chunk_type == "tool_use"      → write_tool_use(); _capture() event; yield SSE
  |     chunk_type == "metadata"      → write_metadata(content); _capture() event; yield SSE
  |     chunk_type == "bedrock_trace" → write_bedrock_trace(); yield SSE
  |     chunk_type == "tool_result"   → write_tool_result(); _extract_citations() on result.report;
  |                                     record_metric("eagle.tool_duration_ms"); yield SSE
  |                                     If "reasoning" key in result: write_reasoning(); yield SSE
  |     chunk_type == "complete"      → persist assistant message + collected_events as audit_logs;
  |                                     if package_context: force checklist refresh metadata event;
  |                                     write_complete(); record_metric("eagle.total_duration_ms"); yield SSE
  |     chunk_type == "error"         → write_error(); yield SSE
  |
  |-- Fallback COMPLETE if generator exhausts without complete event
```

### metadata SSE Events with state_type

When `chunk_type == "metadata"`, the content dict may carry a `state_type` field. This is the mechanism by which `update_state` tool calls reach the frontend:

```python
# strands_agentic_service.py update_state tool pushes to result_queue:
{"type": "metadata", "content": {"state_type": "checklist_update", "package_id": "...", "checklist": {...}}}

# streaming_routes.py forwards it:
await writer.write_metadata(sse_queue, _meta_content)  # _meta_content = chunk["content"]

# MultiAgentStreamWriter.write_metadata emits SSE event type "metadata"
# Frontend onMetadata callback reads state_type and calls apply_event() to update PackageState
```

The special-case `state_type == "checklist_update"` metadata event is also emitted directly by `stream_generator` at the end of each turn when in package mode (force-refresh from `get_package_checklist`).

### _extract_citations()

Extracts FAR/DFARS/NIH/NCI/OMB references and markdown section headers from subagent report text. Returns up to 12 citation strings appended to `tool_result` as `"citations": [...]` so the frontend can render them as chips.

### Audit Log Persistence

All non-text SSE events are captured in `collected_events` list via `_capture()`. On completion, they are persisted to DynamoDB as `metadata={"audit_logs": collected_events}` on the assistant message. The session sub-routes (`/audit-logs`, `/documents`, `/summary`) read back from this stored metadata.

### MultiAgentStreamWriter SSE Methods

| Method | SSE event type emitted |
|--------|----------------------|
| `write_text(queue, content)` | `text` |
| `write_reasoning(queue, reasoning)` | `reasoning` |
| `write_tool_use(queue, name, input, tool_use_id)` | `tool_use` |
| `write_tool_result(queue, tool_name, result)` | `tool_result` |
| `write_metadata(queue, metadata)` | `metadata` |
| `write_handoff(queue, target_agent_id, reason)` | `handoff` |
| `write_complete(queue, metadata)` | `complete` |
| `write_error(queue, error_message)` | `error` |
| `write_bedrock_trace(queue, trace_data)` | `bedrock_trace` |

---

## Part 6: Routes Directory (server/app/routes/)

### _deps.py — Shared Dependencies

All route modules import shared state from `_deps.py`:

```python
# Feature flags
USE_PERSISTENT_SESSIONS = os.getenv("USE_PERSISTENT_SESSIONS", "true").lower() == "true"
REQUIRE_AUTH = os.getenv("REQUIRE_AUTH", "false").lower() == "true"
S3_BUCKET = os.getenv("S3_BUCKET", "eagle-documents-dev")

# Ring buffers (in-memory)
TELEMETRY_LOG: deque  # maxlen=500
API_REQUEST_LOG: deque  # maxlen=1000

# Auth helpers
async def get_user_from_header(authorization: Optional[str] = Header(None)) -> UserContext
def get_session_context(user: UserContext, session_id: Optional[str] = None) -> tuple[tenant_id, user_id, sid]

# Logging
def log_telemetry(entry: dict)  # appends to TELEMETRY_LOG + logs JSON
def log_api_request(method, path, status, duration_ms, tenant_id)  # appends to API_REQUEST_LOG
```

`_deps.py` also re-exports `get_current_user` (from `auth.py`) and `get_admin_user`, `verify_tenant_admin` (from `admin_auth.py`) for use by route modules.

### sessions.py — Session Sub-Routes

All session endpoints use `Depends(get_user_from_header)` for auth and `get_session_context(user)` for tenant/user extraction.

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/sessions` | GET | List sessions for current user |
| `/api/sessions` | POST | Create new session |
| `/api/sessions/{session_id}` | GET | Get session details |
| `/api/sessions/{session_id}` | PATCH | Update title/status/metadata |
| `/api/sessions/{session_id}` | DELETE | Delete session |
| `/api/sessions/{session_id}/messages` | GET | Get messages (limit param) |
| `/api/sessions/{session_id}/messages` | DELETE | Clear all messages (batch delete MSG# items) |
| `/api/sessions/{session_id}/summary` | GET | Title, message count, last_active, tools_used (extracted from audit_logs) |
| `/api/sessions/{session_id}/documents` | GET | Documents from audit_logs tool_results (create_document/generate_document) |
| `/api/sessions/{session_id}/audit-logs` | GET | All persisted SSE audit events across all turns |

The `/messages` DELETE endpoint directly accesses DynamoDB via `_get_table()` for batch delete of `MSG#{session_id}#` SK-prefixed items.

The `/summary` endpoint extracts `tools_used` by walking `msg.metadata.audit_logs` for `type == "tool_use"` events.

The `/documents` endpoint extracts document records from `msg.metadata.audit_logs` where `type == "tool_result"` and `name in ("create_document", "generate_document")`.

### misc.py — Telemetry, WebSocket, Health

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/telemetry` | GET | Recent TELEMETRY_LOG entries with summary stats |
| `/api/tools` | GET | EAGLE_TOOLS list with names, descriptions, parameter schemas |
| `/ws/chat` | WebSocket | Real-time streaming chat; iterates `sdk_query()` async generator |
| `/api/admin/request-log` | GET | API_REQUEST_LOG entries with per-route stats |
| `/api/health` | GET | Health check (knowledge base + services) |

### traces.py — Langfuse Trace Proxy

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/traces/story` | GET | Fetch Langfuse trace by `session_id`, build supervisor→subagent story with token counts |
| `/api/traces/sessions` | GET | List recent Langfuse sessions |

`_build_story()` walks the Langfuse observation hierarchy (AGEN → SPAN execute_event_loop_cycle → GENE chat + TOOL spans → nested AGEN subagent). Returns per-turn breakdown: input/output tokens, tool_calls, subagent details, internal tool calls, response previews.

---

## Part 7: AWS Tool Handlers

### _exec_s3_document_ops

**Actions**: `read`, `write`, `list`

| Action | Required Params | Returns |
|--------|----------------|---------|
| `read` | `key` | `{content, key, metadata}` |
| `write` | `key`, `content` | `{message, key, size}` |
| `list` | (optional: `prefix`) | `{documents: [{key, size, last_modified}], count}` |

- **Bucket**: `nci-documents`
- **Key prefix**: `eagle/{tenant}/{user}/` (from `_get_user_prefix()`)
- **Full key**: `{prefix}{params.key}`

### _exec_dynamodb_intake

**Actions**: `create`, `read`, `update`, `list`

| Action | Required Params | Returns |
|--------|----------------|---------|
| `create` | `item_data` | `{message, item_id, pk, sk}` |
| `read` | `item_id` | `{item: {fields...}}` |
| `update` | `item_id`, `updates` | `{message, item_id}` |
| `list` | (optional) | `{items: [...], count}` |

- **Table**: `eagle`
- **Key schema**: `PK=INTAKE#{tenant_id}`, `SK=INTAKE#{item_id}`
- `item_id` auto-generated via `uuid.uuid4().hex[:12]` on create
- Timestamps: `created_at`, `updated_at` auto-set

### _exec_cloudwatch_logs

**Actions**: `get_stream`, `recent`, `search`

| Action | Required Params | Returns |
|--------|----------------|---------|
| `get_stream` | `stream_name` | `{events: [...], count}` |
| `recent` | (optional: `limit`) | `{streams: [...], count}` |
| `search` | `pattern` | `{matches: [...], count}` |

- **Log group**: `/eagle/test-runs`
- Read-only operations; no write/delete actions

### _exec_search_far

**Params**: `query` (search text), optional `parts` (FAR parts to search)

- Returns matching FAR clauses with relevance
- Uses embedded FAR reference data
- No AWS resource dependency

### _exec_create_document

**Params**: `doc_type`, `title`, `data` (dict of document-specific fields)

- Dispatches to `_generate_{doc_type}()` function
- Saves generated markdown to S3: `eagle/{tenant}/{user}/documents/{doc_type}_{timestamp}.md`
- Returns `{message, doc_type, s3_key, content_preview, word_count}`

### _exec_get_intake_status

**Params**: (none required)

- Scans S3 prefix `eagle/{tenant}/{user}/documents/` for existing docs
- Tracks 10 document types: 5 always required + 5 conditional
- Returns `{status: {type: "complete"|"pending"}, summary: {complete, pending, total}}`

**Always required**: sow, igce, market_research, acquisition_plan, cor_certification
**Conditional**: justification, eval_criteria, security_checklist, section_508, contract_type_justification

### _exec_intake_workflow

**Actions**: `start`, `advance`, `status`

| Action | Params | Returns |
|--------|--------|---------|
| `start` | `requirement_description` | `{workflow_id, stage, next_actions, progress_bar}` |
| `advance` | `workflow_id`, `completed_actions` | `{stage, next_actions, progress_bar}` |
| `status` | `workflow_id` | `{stage, progress, completed_documents}` |

- 4-stage workflow: Requirements Gathering -> Compliance Check -> Document Generation -> Review & Submit

---

## Part 8: Tenant Scoping

### Extract Functions

```python
_extract_tenant_id(session_id) -> str
    # Always returns "demo-tenant" (placeholder for production auth)

_extract_user_id(session_id) -> str
    # Returns "demo-user" for non "ws-" session IDs
    # Returns session_id itself for "ws-*" WebSocket sessions

_get_user_prefix(session_id) -> str
    # Returns "eagle/{tenant}/{user}/"
```

### S3 Key Patterns

| Pattern | Example |
|---------|---------|
| User prefix | `eagle/demo-tenant/demo-user/` |
| Document key | `eagle/demo-tenant/demo-user/documents/sow_20260209T120000.md` |
| Custom key | `eagle/demo-tenant/demo-user/{params.key}` |

### DynamoDB Key Patterns

| Key | Format | Example |
|-----|--------|---------|
| Session PK | `SESSION#{tenant_id}#{user_id}` | `SESSION#demo-tenant#demo-user` |
| Session SK | `SESSION#{session_id}` | `SESSION#abc123` |
| Message SK | `MSG#{session_id}#{msg_id}` | `MSG#abc123#001` |
| Usage PK | `USAGE#{tenant_id}` | `USAGE#demo-tenant` |
| Intake PK | `INTAKE#{tenant_id}` | `INTAKE#demo-tenant` |
| Intake SK | `INTAKE#{item_id}` | `INTAKE#a1b2c3d4e5f6` |

### WebSocket Session Scoping

- Session IDs starting with `ws-` use the session ID as user_id
- This gives each WebSocket connection its own S3 namespace
- Non-ws sessions share the `demo-user` namespace

---

## Part 9: Document Generation

### 10 Document Types

| Type | Generator Function | Key Content |
|------|--------------------|-------------|
| `sow` | `_generate_sow()` | Statement of Work with objectives, deliverables, period of performance |
| `igce` | `_generate_igce()` | Independent Government Cost Estimate with line items, totals |
| `market_research` | `_generate_market_research()` | Market analysis, vendor capabilities, pricing benchmarks |
| `justification` | `_generate_justification()` | Justification & Approval for sole source (FAR 6.302) |
| `acquisition_plan` | `_generate_acquisition_plan()` | Streamlined 5-section acquisition plan |
| `eval_criteria` | `_generate_eval_criteria()` | Technical evaluation factors and rating scale |
| `security_checklist` | `_generate_security_checklist()` | IT security checklist (FISMA, FedRAMP) |
| `section_508` | `_generate_section_508()` | Section 508 accessibility compliance statement |
| `cor_certification` | `_generate_cor_certification()` | COR nominee certification with FAC-COR level |
| `contract_type_justification` | `_generate_contract_type_justification()` | Contract type D&F elements |

### Generator Pattern

```python
def _generate_{doc_type}(title: str, data: dict) -> str:
    field = data.get("field_name", "default value")
    content = f"# {title}\n\n..."
    return content
```

### S3 Save Pattern (in _exec_create_document)

```python
timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
s3_key = f"{prefix}documents/{doc_type}_{timestamp}.md"
_get_s3().put_object(Bucket="nci-documents", Key=s3_key, Body=content.encode())
```

---

## Part 10: Session Store (stores/session_store.py)

### Unified `eagle` Table Access

| Operation | PK | SK | Notes |
|-----------|----|----|-------|
| `create_session()` | `SESSION#{tenant}#{user}` | `SESSION#{session_id}` | Auto-generates UUID if not provided |
| `get_session()` | `SESSION#{tenant}#{user}` | `SESSION#{session_id}` | Returns None if not found |
| `list_sessions()` | `SESSION#{tenant}#{user}` | `begins_with(SESSION#)` | Sorted by created_at desc |
| `add_message()` | `SESSION#{tenant}#{user}` | `MSG#{session_id}#{msg_id}` | msg_id is auto-incremented |
| `get_messages()` | `SESSION#{tenant}#{user}` | `begins_with(MSG#{session_id}#)` | Sorted by SK |
| `get_messages_for_anthropic()` | — | — | Returns `[{"role": ..., "content": ...}]` for SDK prompt |
| `update_session()` | `SESSION#{tenant}#{user}` | `SESSION#{session_id}` | Partial update; used by EagleSSEHookProvider to persist agent_state |
| `record_usage()` | `USAGE#{tenant}` | `USAGE#{date}#{session}#{ts}` | Token counts, cost, model |
| `_get_table()` | — | — | Lazy singleton DynamoDB Table resource |

### Caching

- In-memory cache with 5-minute TTL per session
- Write-through: updates DynamoDB + cache simultaneously
- `_invalidate_cache()` on delete operations

### Configuration

```python
TABLE_NAME = os.getenv("EAGLE_SESSIONS_TABLE", "eagle")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
SESSION_TTL_DAYS = int(os.getenv("SESSION_TTL_DAYS", "30"))
```

---

## Part 11: Authentication

### Two Auth Systems (Both Active)

**cognito_auth.py** (new/primary — used by main.py EAGLE endpoints and _deps.py):
```python
@dataclass
class UserContext:
    user_id: str
    tenant_id: str
    email: str
    tier: str  # "free", "pro", "enterprise"
    groups: List[str]

    @classmethod
    def dev_user(cls) -> "UserContext": ...
    @classmethod
    def anonymous(cls) -> "UserContext": ...
    def to_dict(self) -> dict: ...
```

**auth.py** (legacy — still active, used by admin_auth.py and re-exported from _deps.py):
```python
async def get_current_user(credentials) -> Dict:
    # Returns dict with user_id, tenant_id, subscription_tier, cognito:groups
    # DEV_MODE returns dev-user / dev-tenant with PREMIUM tier
```

### Auth Flow (cognito_auth.py path)

1. Client sends `Authorization: Bearer <JWT>` header
2. `extract_user_context(token)` decodes JWT (Cognito)
3. Falls back to `DEV_MODE` if `DEV_MODE=true` env var set
4. Dev mode returns `UserContext(user_id="dev-user", tenant_id="dev-tenant")`

### Feature Flags

- `REQUIRE_AUTH=false` → anonymous access allowed (dev)
- `REQUIRE_AUTH=true` → 401 if no valid JWT (production)
- `DEV_MODE=true` → bypass Cognito, use dev user context (both auth systems)

---

## Part 12: main.py Route Registration

`main.py` is now a thin orchestrator. All routes are extracted to `server/app/routes/`. The file:
1. Loads `.env` from project root
2. Configures Langfuse OTEL via `_setup_langfuse()`
3. Creates FastAPI app + CORS middleware
4. Registers `api_request_telemetry` HTTP middleware (records `eagle.api_duration_ms` metric, calls `log_api_request`)
5. Initializes `SubscriptionService`
6. Registers all routers:

```python
# SSE streaming (streaming_routes.py factory pattern)
streaming_router = create_streaming_router(subscription_service)
app.include_router(streaming_router)

# Extracted route modules (all from routes/)
app.include_router(chat_router)       # routes/chat.py
app.include_router(sessions_router)   # routes/sessions.py
app.include_router(documents_router)  # routes/documents.py
app.include_router(admin_router)      # routes/admin.py
app.include_router(packages_router)   # routes/packages.py
app.include_router(workspaces_router) # routes/workspaces.py
app.include_router(tenants_router)    # routes/tenants.py
app.include_router(user_router)       # routes/user.py
app.include_router(templates_router)  # routes/templates.py
app.include_router(skills_router)     # routes/skills.py
app.include_router(misc_router)       # routes/misc.py
app.include_router(traces_router)     # routes/traces.py
```

---

## Part 13: CDK Integration Points

### EagleCoreStack → Backend

| Resource | CDK Reference | Backend Usage |
|----------|---------------|---------------|
| DynamoDB `eagle` | `Table.fromTableName()` (imported) | `stores/session_store.py`, tool handlers |
| S3 `nci-documents` | `Bucket.fromBucketName()` (imported) | s3_document_ops, create_document |
| Cognito `eagle-users-dev` | Created by Core stack | `cognito_auth.py` JWT validation |
| IAM `eagle-app-role-dev` | Created by Core stack | ECS task role with DDB/S3/CW permissions |
| CloudWatch `/eagle/app` | Created by Core stack | Application logging |

### EagleComputeStack → Backend

| Resource | CDK Config | Notes |
|----------|-----------|-------|
| ECR `eagle-backend-dev` | Image repository | Docker push target |
| ECS Service | 0.5 vCPU / 1024 MiB | Fargate task definition |
| ALB (internal) | Port 8000, /api/health | Not internet-accessible |
| Auto-scaling | 1-3 tasks | CPU target tracking |

---

## Learnings

### patterns_that_work
- Tool dispatch via dict lookup is fast and easily extensible
- Lazy AWS client singletons work well for Lambda-style cold starts
- Generating markdown documents with embedded FAR references gives Claude useful context
- `_get_user_prefix()` as a single source of truth for S3 paths prevents scoping bugs
- Unified `eagle` DynamoDB table with PK/SK patterns handles sessions, messages, usage, costs in one table (discovered: 2026-02-16, component: session_store)
- Write-through cache in session_store.py gives fast reads without stale data (discovered: 2026-02-16, component: session_store)
- `DEV_MODE` flag in cognito_auth.py lets backend run without Cognito configured — essential for local dev and testing (discovered: 2026-02-16, component: cognito_auth)
- CDK `fromTableName()` / `fromBucketName()` pattern — import existing resources into stacks without recreating them (discovered: 2026-02-16, component: cdk-eagle)
- Internal ALB for backend keeps API not internet-accessible — frontend ALB is the only public entry point (discovered: 2026-02-16, component: compute-stack)
- Dockerfile copies `eagle-plugin/` to `../eagle-plugin/` so `eagle_skill_constants.py` can walk it at runtime (discovered: 2026-02-16, component: docker)
- `TIER_TOOLS` in strands_agentic_service.py uses the same tool names as TOOL_DISPATCH keys — tool names must match exactly (discovered: 2026-02-25, component: strands_agentic_service)
- Workspace 4-layer prompt resolution enables hot-reloadable agent prompts without ECS redeploy (discovered: 2026-02-25, component: wspc_store)
- `eagle_state.py` `normalize()` fills missing keys from `_DEFAULTS` — adding a new state field never breaks old state dicts read from DynamoDB (discovered: 2026-03-16, component: eagle_state)
- `apply_event()` is pure — it never mutates inputs; `update_state` tool merges result via `current_state.update(new_state)` (discovered: 2026-03-16, component: eagle_state)
- `update_state` tool pushes SSE metadata events via `result_queue` — the queue bridges the sync Strands Agent() call to the async SSE generator without thread-safety issues (discovered: 2026-03-16, component: strands_agentic_service + streaming_routes)
- `specialist_summaries` in eagle_state persists subagent report text across turns — supervisor can reference prior specialist outputs without re-invoking subagents (discovered: 2026-03-16, component: eagle_state)
- Audit log persistence pattern: `collected_events` list in `stream_generator` captures all non-text SSE events; stored as `metadata.audit_logs` on assistant DynamoDB message; session sub-routes read it back for `/audit-logs`, `/documents`, `/summary` endpoints (discovered: 2026-03-16, component: streaming_routes + sessions.py)
- `_extract_citations()` regex on subagent report text extracts FAR/DFARS references and section headers — zero dependency, fast, appended to tool_result for frontend chip rendering (discovered: 2026-03-16, component: streaming_routes)
- Routes split into `server/app/routes/` with shared `_deps.py` — `get_user_from_header` and `get_session_context` centralize auth extraction for all route modules (discovered: 2026-03-16, component: routes)
- Stores moved to `server/app/stores/` — imports now use `from ..stores.session_store import ...` pattern from route modules (discovered: 2026-03-16, component: stores)
- `EagleSSEHookProvider` AfterInvocationEvent persists `agent.state` to DynamoDB after every supervisor turn — state survives connection resets and multi-turn sessions (discovered: 2026-03-16, component: strands_agentic_service)
- Langfuse `_setup_langfuse()` in main.py is a silent no-op when keys absent — safe for local dev and CI (discovered: 2026-03-16, component: main.py)
- `_sdk_with_keepalive()` in stream_generator keeps ALB connection alive during long Strands Agent calls; pending task is preserved across keepalive timeouts so no chunks are lost (discovered: 2026-03-16, component: streaming_routes)

### patterns_to_avoid
- Don't test document generation with empty `data` dicts — generators produce minimal stubs
- Don't assume DynamoDB items have all fields — use `.get()` with defaults
- Don't call `_get_s3()` at module level — fails if AWS creds aren't configured at import time
- Don't create S3 clients inline per request — use the lazy singleton from strands_agentic_service.py instead (discovered: 2026-02-16, component: main.py)
- Don't hardcode `"nci-documents"` bucket name — use `os.getenv("S3_BUCKET", "nci-documents")` for CDK flexibility (discovered: 2026-02-16, component: cdk-eagle)
- Don't delete AWS resources (CF stacks, Lightsail, ECS) without confirming the new CDK stacks have images pushed and running tasks (discovered: 2026-02-16, component: aws-cleanup)
- Don't assume `admin_auth.py` was migrated to `cognito_auth` — it still imports `get_current_user` from `app.auth` (verified 2026-02-25)
- Don't add a new tool only to `TOOL_DISPATCH` — also add to `EAGLE_TOOLS` (schema), `TIER_TOOLS` (tier gating), and the supervisor prompt (usage guidance)
- Don't import stores using the old flat path (`from .session_store import ...`) — stores have moved to `server/app/stores/`; use `from .stores.session_store import ...` or `from ..stores.session_store import ...` depending on caller location (discovered: 2026-03-16, component: stores)
- Don't mutate `eagle_state` dicts directly — always go through `apply_event()` so the state machine logic stays in one place (discovered: 2026-03-16, component: eagle_state)
- Don't add a new `state_type` to `update_state` tool schema without also adding a handler branch in both `apply_event()` (eagle_state.py) and the `_make_update_state_tool()` function (strands_agentic_service.py) (discovered: 2026-03-16, component: eagle_state + strands_agentic_service)

### common_issues
- AWS credentials not configured → all tool handlers fail with ClientError
- S3 bucket "nci-documents" doesn't exist → s3_document_ops and create_document fail
- DynamoDB table "eagle" doesn't exist → dynamodb_intake and session_store fail
- CloudWatch log group "/eagle/test-runs" doesn't exist → cloudwatch_logs returns empty
- ECS services show desiredCount=1 but runningCount=0 → no Docker images pushed to ECR yet (discovered: 2026-02-16, component: compute-stack)
- `MSYS_NO_PATHCONV=1` required on MINGW64/Git Bash when running AWS CLI with `/aws/...` paths — otherwise Git Bash converts them to `C:/Program Files/Git/aws/...` (discovered: 2026-02-16, component: aws-cli)
- Cognito pools with custom domains require `delete-user-pool-domain` before `delete-user-pool` (discovered: 2026-02-16, component: cognito)
- Versioned S3 buckets can't be deleted with `aws s3 rb --force` on MINGW — use Python boto3 with `bucket.object_versions.delete()` instead (discovered: 2026-02-16, component: s3)
- `update_state` tool returns `{"error": "Unknown state_type: ..."}` when passed a `state_type` not in the enum — check both `apply_event()` and `_make_update_state_tool()` (discovered: 2026-03-16, component: eagle_state)
- `from .session_store import ...` ImportError after stores/ refactor — old flat import paths no longer work; update to `from .stores.session_store import ...` (discovered: 2026-03-16, component: stores)
- `collected_events` audit_log missing from DynamoDB message if connection drops before `complete` chunk — fallback COMPLETE block persists what was collected but may be partial (discovered: 2026-03-16, component: streaming_routes)

### tips
- Use `execute_tool()` for testing — it's synchronous and returns JSON strings
- The `search_far` tool has no AWS dependency — good for offline testing
- `intake_workflow` is stateless — workflow state is tracked in the response, not persisted
- Check `EAGLE_TOOLS` list for the exact parameter schemas Claude sees
- Check `TIER_TOOLS` for what SDK subagents can call
- Backend health check is at `/api/health` (not `/health`) — confirm ALB target group health path matches (discovered: 2026-02-25, verified from misc.py)
- `main.py` version is 4.0.0 — reflects the merged multi-tenant + EAGLE architecture (discovered: 2026-02-16)
- `stores/session_store.py` uses `boto3.resource("dynamodb")` (high-level) — both tool handlers and stores access the same `eagle` table (discovered: 2026-02-16)
- Two separate MODEL env vars: `ANTHROPIC_MODEL` (legacy) vs `EAGLE_SDK_MODEL` (strands_agentic_service.py) — set both when changing models (discovered: 2026-02-25)
- `api_chat()` REST endpoint in routes/chat.py uses `sdk_query()`, not legacy `stream_chat()` (discovered: 2026-02-25)
- `/api/sessions/{session_id}/audit-logs` is the debug endpoint for replaying what SSE events were emitted in a session — useful for diagnosing state push failures (discovered: 2026-03-16, component: sessions.py)
- `to_trace_attrs()` includes `"session.id": session_id` — Langfuse uses this to group supervisor and subagent OTEL traces into a single Session view (discovered: 2026-03-16, component: eagle_state)
- `_build_story()` in traces.py decodes the Langfuse AGEN → SPAN → GENE → TOOL hierarchy; the Strands SDK OTEL span structure is: invoke_agent (AGEN) → execute_event_loop_cycle (SPAN) → chat (GENE) + skill_name (TOOL) → invoke_agent (nested AGEN for subagent) (discovered: 2026-03-16, component: traces.py)
