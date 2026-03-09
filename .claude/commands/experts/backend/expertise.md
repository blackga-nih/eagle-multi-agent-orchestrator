---
type: expert-file
parent: "[[backend/_index]]"
file-type: expertise
human_reviewed: false
tags: [expert-file, mental-model, backend, agentic-service, eagle, aws, s3, dynamodb, cloudwatch]
last_updated: 2026-03-09T00:00:00
---

# Backend Expertise (Complete Mental Model)

> **Sources**: server/app/*.py, server/eagle_skill_constants.py, infrastructure/cdk-eagle/lib/*.ts

---

## Part 1: Architecture Overview

### File Layout

```
server/app/
├── main.py                  # FastAPI app (v4.0.0), CORS, ~80+ endpoints
├── strands_agentic_service.py  # PRIMARY orchestrator — Strands SDK supervisor + subagents (BedrockModel)
├── agentic_service.py       # TOOL_DISPATCH registry + handler implementations (used by both legacy and Strands paths)
├── streaming_routes.py      # SSE streaming router — calls strands_agentic_service.sdk_query_streaming()
├── sdk_agentic_service.py   # REPLACED by strands_agentic_service.py (still present, not deleted)
├── eagle_tools_mcp.py       # MCP wrapper layer — present but NOT used by current Strands path
├── session_store.py         # Unified DynamoDB session/message/usage store (eagle table)
├── cognito_auth.py          # Cognito JWT auth, UserContext, DEV_MODE fallback
├── auth.py                  # Legacy auth (get_current_user) — still active, imported by admin_auth.py
├── document_export.py       # DOCX/PDF/Markdown export
├── admin_service.py         # Dashboard stats, rate limiting, cost tracking
├── admin_auth.py            # Admin group auth (imports from auth.py — NOT yet migrated to cognito_auth)
├── admin_cost_service.py    # 4-level cost reports (tenant, user, service, comprehensive)
├── subscription_service.py  # Tier-based limits (SubscriptionTier enum)
├── cost_attribution.py      # Per-tenant/user cost attribution
├── stream_protocol.py       # SSE event format (MultiAgentStreamWriter)
├── models.py                # Pydantic models (ChatMessage, TenantContext, etc.)
├── runtime_context.py       # Runtime context utilities
├── gateway_client.py        # API gateway client (still present, not archived)
├── mcp_agent_integration.py # MCP agent integration (still present, not archived)
├── weather_mcp_service.py   # Weather MCP compatibility (still present, not archived)
├── bedrock_service.py       # Bedrock-specific service
├── plugin_store.py          # DynamoDB PLUGIN# entity hot-reload store
├── workspace_store.py       # Per-user workspace CRUD (Default workspace auto-provision)
├── wspc_store.py            # Workspace override resolution (4-layer chain)
├── prompt_store.py          # Tenant prompt overrides (PROMPT# in eagle table)
├── config_store.py          # Tenant config key-value store
├── template_store.py        # Acquisition document templates
├── skill_store.py           # User-created SKILL# items (publish/review lifecycle)
├── package_store.py         # Acquisition package CRUD + workflow (submit/approve/close)
├── document_store.py        # Package document versioning + finalization
├── approval_store.py        # Approval chain + decision recording
├── pref_store.py            # User preferences
├── audit_store.py           # Audit event writer
├── compliance_matrix.py     # NCI/NIH compliance decision tree (execute_operation())
├── health_checks.py         # Health check helpers (check_knowledge_base_health)
├── package_context_service.py # Package context resolution for chat
└── tools/
    ├── __init__.py
    └── knowledge_tools.py   # knowledge_search / knowledge_fetch implementations + tool schemas
server/
├── eagle_skill_constants.py # Auto-discovery: walks eagle-plugin/, exports AGENTS, SKILLS, PLUGIN_CONTENTS
├── config.py                # App configuration
├── run.py                   # Uvicorn runner
├── requirements.txt         # Python dependencies
└── start_dev.sh             # Dev startup script
```

### Tech Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Framework | FastAPI 4.0.0 | REST + WebSocket + SSE |
| LLM SDK | Strands Agents SDK | `from strands import Agent, tool` — boto3-native BedrockModel |
| AWS SDK | `boto3` | S3, DynamoDB, CloudWatch, Cognito, STS |
| Runtime | Python 3.11+ | `str | None` union syntax used |
| Async | `asyncio` | `sdk_query()` and `sdk_query_streaming()` are async generators; Strands Agent() is sync, bridged via `asyncio.to_thread` or `stream_async()` |
| Auth | Cognito JWT | `cognito_auth.py` with DEV_MODE fallback; `auth.py` still active for legacy admin routes |
| Persistence | DynamoDB `eagle` table | Single-table design via `session_store.py` |
| Logging | `logging` | Logger: `eagle.strands_agent`, `eagle.sessions`, `eagle.knowledge_tools` |

### Entry Points

| Function | File | Purpose |
|----------|------|---------|
| `sdk_query()` | strands_agentic_service.py:1269 | PRIMARY async generator — supervisor + skill subagents via Strands, returns AssistantMessage/ResultMessage adapters |
| `sdk_query_streaming()` | strands_agentic_service.py:1433 | PRIMARY streaming — yields `{"type":"text","data":...}` dict chunks via `Agent.stream_async()` |
| `sdk_query_single_skill()` | strands_agentic_service.py:1684 | Direct single-skill Agent call (no supervisor) |
| `execute_tool()` | agentic_service.py:2569 | Synchronous tool dispatch — called by test suite and `_make_service_tool()` |
| `stream_generator()` | streaming_routes.py:39 | SSE generator — calls `sdk_query_streaming()`, emits SSE events to frontend |
| `api_chat()` | main.py:191 | REST chat endpoint — calls `sdk_query()` via streaming_routes |
| `websocket_chat()` | main.py:718 | WebSocket streaming chat |
| `api_list_sessions()` | main.py:298 | Session CRUD endpoints |
| `api_export_document()` | main.py:445 | Document export (DOCX/PDF/MD) |
| `api_list_documents()` | main.py:508 | S3 document browser |

### Configuration

```python
# strands_agentic_service.py — Strands/Bedrock model selection
# Auto-selects based on AWS account: Sonnet 4.6 for NCI (695681773636), Haiku 4.5 otherwise
_NCI_ACCOUNT = "695681773636"
_SONNET = "us.anthropic.claude-sonnet-4-6"
_HAIKU = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

def _default_model() -> str:
    env_model = os.getenv("EAGLE_BEDROCK_MODEL_ID")
    if env_model:
        return env_model
    try:
        account = boto3.client("sts").get_caller_identity()["Account"]
        return _SONNET if account == _NCI_ACCOUNT else _HAIKU
    except Exception:
        return _HAIKU

MODEL = _default_model()  # used by BedrockModel at import time

# main.py feature flags
USE_PERSISTENT_SESSIONS = os.getenv("USE_PERSISTENT_SESSIONS", "true").lower() == "true"
REQUIRE_AUTH = os.getenv("REQUIRE_AUTH", "false").lower() == "true"
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
  ANTHROPIC_API_KEY        → Secrets Manager
  EAGLE_BEDROCK_MODEL_ID   → override model (e.g. "us.anthropic.claude-haiku-4-5-20251001-v1:0")
  EAGLE_TABLE              → "eagle" (DynamoDB)
  S3_BUCKET                → "nci-documents"
  METADATA_TABLE           → "eagle-document-metadata-dev" (knowledge base index)
  DOCUMENT_BUCKET          → "eagle-documents-695681773636-dev" (knowledge base content)
  AWS_REGION               → "us-east-1"
  LOG_GROUP                → "/eagle/app"
  USE_PERSISTENT_SESSIONS  → "true"
  REQUIRE_AUTH             → "false" (dev) / "true" (prod)
```

---

## Part 2: Tool Dispatch System

### TOOL_DISPATCH (agentic_service.py line ~2548)

```python
TOOL_DISPATCH = {
    "s3_document_ops":         _exec_s3_document_ops,
    "dynamodb_intake":         _exec_dynamodb_intake,
    "cloudwatch_logs":         _exec_cloudwatch_logs,
    "search_far":              _exec_search_far,
    "create_document":         _exec_create_document,
    "get_intake_status":       _exec_get_intake_status,
    "intake_workflow":         _exec_intake_workflow,
    "query_compliance_matrix": _exec_query_compliance_matrix,
    # Knowledge base tools
    "knowledge_search":        exec_knowledge_search,   # from tools/knowledge_tools.py
    "knowledge_fetch":         exec_knowledge_fetch,    # from tools/knowledge_tools.py
    "manage_skills":           _exec_manage_skills,
    "manage_prompts":          _exec_manage_prompts,
    "manage_templates":        _exec_manage_templates,
}
```

### TOOLS_NEEDING_SESSION (agentic_service.py line ~2566)

```python
TOOLS_NEEDING_SESSION = {"s3_document_ops", "create_document", "get_intake_status"}
```

These tools receive `session_id` as a third argument to enable per-user S3 prefix scoping.

### execute_tool() Flow (line ~2569)

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

| Handler | Signature | Notes |
|---------|-----------|-------|
| `_exec_s3_document_ops` | `(params, tenant_id, session_id)` | Session-scoped |
| `_exec_dynamodb_intake` | `(params, tenant_id)` | |
| `_exec_cloudwatch_logs` | `(params, tenant_id)` | |
| `_exec_search_far` | `(params, tenant_id)` | No AWS dependency |
| `_exec_create_document` | `(params, tenant_id, session_id)` | Session-scoped |
| `_exec_get_intake_status` | `(params, tenant_id, session_id)` | Session-scoped |
| `_exec_intake_workflow` | `(params, tenant_id)` | Stateless |
| `_exec_query_compliance_matrix` | `(params, tenant_id)` | From compliance_matrix.py |
| `exec_knowledge_search` | `(params, tenant_id, session_id=None)` | From tools/knowledge_tools.py |
| `exec_knowledge_fetch` | `(params, tenant_id, session_id=None)` | From tools/knowledge_tools.py |
| `_exec_manage_skills` | `(params, tenant_id)` | |
| `_exec_manage_prompts` | `(params, tenant_id)` | |
| `_exec_manage_templates` | `(params, tenant_id)` | |

### _make_service_tool() — Strands Tool Factory (strands_agentic_service.py line ~932)

In the Strands path, `_make_service_tool()` is used instead of MCP. It:
1. Looks up the handler from `TOOL_DISPATCH`
2. Closes over `tenant_id`, `user_id`, `scoped_session_id`, `package_context`, `result_queue`, `loop`
3. Builds a composite `scoped_session_id = f"{tenant_id}#advanced#{user_id}#{session_id or ''}"` so legacy handlers get proper per-user S3 scoping
4. Emits `tool_result` events to `result_queue` for frontend observability
5. Returns a `@tool`-decorated function suitable for `Agent(tools=[...])`

**`_SERVICE_TOOL_DEFS`** (line ~1010): maps tool names to description strings for the 10 service tools wired into the supervisor:
`s3_document_ops`, `dynamodb_intake`, `create_document`, `get_intake_status`, `intake_workflow`, `search_far`, `knowledge_search`, `knowledge_fetch`, `manage_skills`, `manage_prompts`, `manage_templates`

**`_build_service_tools()`** (line ~1063): builds all service tools + adds 4 factory tools:
- `_make_compliance_matrix_tool()` → `query_compliance_matrix`
- `_make_list_skills_tool()` → `list_skills`
- `_make_load_skill_tool()` → `load_skill`
- `_make_load_data_tool()` → `load_data`

---

## Part 3: Strands Agentic Service (strands_agentic_service.py) — PRIMARY

### Architecture

```
sdk_query() / sdk_query_streaming()
  |-- _maybe_fast_path_document_generation()  → short-circuit for "generate X document" prompts
  |-- workspace_store.get_or_create_default() → resolve workspace_id
  |-- build_skill_tools()     → list of @tool-wrapped subagent functions
  |-- _build_service_tools()  → list of @tool-wrapped AWS + data tools
  |-- build_supervisor_prompt() → supervisor system prompt with subagent list + KB/document rules
  |-- Agent(model=_model, system_prompt, tools=skill_tools+service_tools, messages=history)
  |-- agent(prompt)  [sdk_query — sync, returns AgentResult]
  |-- supervisor.stream_async(prompt)  [sdk_query_streaming — yields events]
```

### Model Selection

```python
# strands_agentic_service.py — auto-selects by AWS account
_NCI_ACCOUNT = "695681773636"
_SONNET = "us.anthropic.claude-sonnet-4-6"
_HAIKU = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

# Override via env var:
EAGLE_BEDROCK_MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
```

A single `_model = BedrockModel(model_id=MODEL, region_name=...)` is created at import time and reused across all requests (no per-request boto3 overhead).

### Tier-Gated Tool Access (TIER_TOOLS)

```python
# strands_agentic_service.py
TIER_TOOLS = {
    "basic":    [],
    "advanced": ["Read", "Glob", "Grep"],
    "premium":  ["Read", "Glob", "Grep", "Bash"],
}
```

Note: In the Strands path, tool access is managed by which `@tool` functions are passed to `Agent(tools=[...])`. `TIER_TOOLS` is preserved for compatibility but Strands subagents do not use CLI tools like Read/Glob/Grep. All service tools are available to all tiers in the Strands path.

### Tier Budgets

```python
TIER_BUDGETS = {
    "basic": 0.10,
    "advanced": 0.25,
    "premium": 0.75,
}
```

### Tool Emission Pattern (Observability)

All 3 tool wrapper types emit `tool_result` events via `result_queue`:

1. **`_make_subagent_tool()`** (line ~678): Subagent @tools call `loop.call_soon_threadsafe(result_queue.put_nowait, {...})` with `{"type":"tool_result","name":safe_name,"result":{"report":truncated}}`.

2. **`_make_service_tool()`** (line ~932): Service @tools emit via `loop.call_soon_threadsafe(result_queue.put_nowait, {"type":"tool_result","name":tool_name,"result":emit_result})`. Large content fields truncated to 2000 chars for non-document tools.

3. **Factory tools** (`_make_list_skills_tool`, `_make_load_skill_tool`, `_make_load_data_tool`, `_make_compliance_matrix_tool`) (lines ~758–924): Use shared `_emit_tool_result()` helper which parses the JSON result and truncates large content fields before pushing to `result_queue`.

`result_queue` is drained between stream events in `sdk_query_streaming()` via `_drain_tool_results()`.

### Fast-Path Document Generation

`_maybe_fast_path_document_generation()` (line ~227) and `_should_use_fast_document_path()` (line ~202) intercept explicit "generate X document" prompts before spawning the full supervisor/subagent loop:
- Detects doc type from prompt via `_DOC_TYPE_HINTS`
- Skips fast path if blocker phrases present ("what is", "how do i", "explain") or slow-path hints ("research", "far", "policy")
- Calls `_exec_create_document` directly via `asyncio.to_thread`
- `sdk_query_streaming()` yields `tool_use` + `tool_result` + `text` + `complete` events for the fast path

`_ensure_create_document_for_direct_request()` (line ~264) is a reconciliation step that runs AFTER the agent loop — if the model produced inline draft content without calling `create_document`, this forces the call.

### Workspace Resolution (4-Layer Chain)

1. `wspc_store.resolve_skill(tenant_id, user_id, workspace_id, name)` — workspace override
2. Fall back to `PLUGIN_CONTENTS[skill_key]["body"]` — bundled eagle-plugin/ content
3. `skill_store.list_active_skills(tenant_id)` — user-created SKILL# items (merged after bundled)
4. Supervisor prompt resolved via `wspc_store.resolve_agent(tenant_id, user_id, workspace_id, "supervisor")`

### Supervisor Prompt Structure (build_supervisor_prompt)

The supervisor prompt includes:
- Tenant/user/tier context header
- Base supervisor agent content (from workspace chain or bundled AGENTS["supervisor"])
- Active specialists list (one line per skill/agent)
- Progressive Disclosure rules (4 layers: hints → list_skills → load_skill → load_data)
- KB Retrieval Rules (knowledge_search before knowledge_fetch; prefer KB over search_far)
- Document Output Rules (must call create_document; don't inline docs)
- FAST vs DEEP routing guidance

### SKILL_AGENT_REGISTRY

Built at module load from `eagle_skill_constants.AGENTS + SKILLS`, filtered by `plugin.json` active lists. Supervisor agent is excluded. Falls back to bundled `plugin.json` when `plugin_store` DynamoDB is unavailable.

**Important**: `_load_plugin_config()` (line ~601) ALWAYS loads bundled `eagle-plugin/plugin.json` first (which has the `data` index), then overlays DynamoDB manifest fields (version/agent_count/skill_count). The DynamoDB manifest does NOT contain the `data` index — `load_data()` would fail with "available: []" if only DynamoDB was used.

### Adapter Message Types

`strands_agentic_service.py` defines lightweight dataclass adapters that match the Claude SDK interface expected by `streaming_routes.py` and `main.py`:
- `TextBlock(type, text)` — text content
- `ToolUseBlock(type, name, input)` — tool use block
- `AssistantMessage(content=[...])` — container for content blocks
- `ResultMessage(result, usage)` — final result with usage metrics

### sdk_query_streaming() Event Protocol

Yields `dict` chunks consumed by `stream_generator()` in `streaming_routes.py`:

| Chunk type | Keys | Trigger |
|-----------|------|---------|
| `text` | `data: str` | Streamed text delta from Bedrock ConverseStream |
| `tool_use` | `name, input, tool_use_id` | Tool invocation start |
| `tool_result` | `name, result` | Drained from result_queue (factory tools) |
| `complete` | `text, tools_called, usage` | End of stream |
| `error` | `error: str` | Exception during stream |
| `_keepalive` | (internal) | Injected by streaming_routes when timeout exceeded |

---

## Part 4: AWS Tool Handlers (agentic_service.py)

### _exec_s3_document_ops (line ~384)

**Actions**: `read`, `write`, `list`

| Action | Required Params | Returns |
|--------|----------------|---------|
| `read` | `key` | `{content, key, metadata}` |
| `write` | `key`, `content` | `{message, key, size}` |
| `list` | (optional: `prefix`) | `{documents: [{key, size, last_modified}], count}` |

- **Bucket**: `nci-documents`
- **Key prefix**: `eagle/{tenant}/{user}/` (from `_get_user_prefix()`)
- **Full key**: `{prefix}{params.key}`

### _exec_dynamodb_intake (line ~471)

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

### _exec_cloudwatch_logs (line ~589)

**Actions**: `get_stream`, `recent`, `search`

| Action | Required Params | Returns |
|--------|----------------|---------|
| `get_stream` | `stream_name` | `{events: [...], count}` |
| `recent` | (optional: `limit`) | `{streams: [...], count}` |
| `search` | `pattern` | `{matches: [...], count}` |

- **Log group**: `/eagle/test-runs`
- Read-only operations; no write/delete actions

### _exec_search_far (line ~708)

**Params**: `query` (search text), optional `parts` (FAR parts to search)

- Returns matching FAR clauses with relevance
- Uses embedded FAR reference data
- No AWS resource dependency

### _exec_create_document (line ~1027)

**Params**: `doc_type`, `title`, `data` (dict of document-specific fields)

- Dispatches to `_generate_{doc_type}()` function
- Saves generated markdown to S3: `eagle/{tenant}/{user}/documents/{doc_type}_{timestamp}.md`
- Returns `{message, doc_type, s3_key, content_preview, word_count}`

### _exec_get_intake_status (line ~1828)

**Params**: (none required)

- Scans S3 prefix `eagle/{tenant}/{user}/documents/` for existing docs
- Tracks 10 document types: 5 always required + 5 conditional
- Returns `{status: {type: "complete"|"pending"}, summary: {complete, pending, total}}`

### _exec_intake_workflow (line ~1955)

**Actions**: `start`, `advance`, `status`

| Action | Params | Returns |
|--------|--------|---------|
| `start` | `requirement_description` | `{workflow_id, stage, next_actions, progress_bar}` |
| `advance` | `workflow_id`, `completed_actions` | `{stage, next_actions, progress_bar}` |
| `status` | `workflow_id` | `{stage, progress, completed_documents}` |

### exec_knowledge_search (tools/knowledge_tools.py)

**Params**: `topic`, `document_type`, `agent`, `authority_level`, `keywords`, `limit`

- DynamoDB Scan on `METADATA_TABLE` (`eagle-document-metadata-dev`)
- Returns `{results: [...summary fields...], count}`
- Each result includes `s3_key` for passing to `knowledge_fetch`

### exec_knowledge_fetch (tools/knowledge_tools.py)

**Params**: `s3_key` (required) OR `document_id`

- S3 GetObject from `DOCUMENT_BUCKET` (`eagle-documents-695681773636-dev`)
- Returns `{document_id, content, truncated, content_length}`
- Content truncated to 50KB maximum
- REQUIRES an s3_key from a prior knowledge_search result — do NOT call without one

---

## Part 5: Tenant Scoping

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

### Composite Session ID (Strands path)

The Strands path builds a composite session ID before calling legacy handlers:
```python
scoped_session_id = f"{tenant_id}#advanced#{user_id}#{session_id or ''}"
```
`_extract_tenant_id()` and `_extract_user_id()` parse this format to return the real tenant and user rather than "demo-tenant"/"demo-user".

### S3 Key Patterns

| Pattern | Example |
|---------|---------|
| User prefix | `eagle/demo-tenant/demo-user/` |
| Document key | `eagle/demo-tenant/demo-user/documents/sow_20260209T120000.md` |
| Custom key | `eagle/demo-tenant/demo-user/{params.key}` |

### DynamoDB Key Patterns

| Key | Format | Example |
|-----|--------|---------|
| PK (Partition) | `INTAKE#{tenant_id}` | `INTAKE#demo-tenant` |
| SK (Sort) | `INTAKE#{item_id}` | `INTAKE#a1b2c3d4e5f6` |

### WebSocket Session Scoping

- Session IDs starting with `ws-` use the session ID as user_id
- This gives each WebSocket connection its own S3 namespace
- Non-ws sessions share the `demo-user` namespace

---

## Part 6: Document Generation

### 10 Document Types

| Type | Generator Function | Line | Key Content |
|------|-------------------|------|-------------|
| `sow` | `_generate_sow()` | ~1086 | Statement of Work with objectives, deliverables, period of performance |
| `igce` | `_generate_igce()` | ~1173 | Independent Government Cost Estimate with line items, totals |
| `market_research` | `_generate_market_research()` | ~1250 | Market analysis, vendor capabilities, pricing benchmarks |
| `justification` | `_generate_justification()` | ~1313 | Justification & Approval for sole source (FAR 6.302) |
| `acquisition_plan` | `_generate_acquisition_plan()` | ~1381 | Streamlined 5-section acquisition plan |
| `eval_criteria` | `_generate_eval_criteria()` | ~1481 | Technical evaluation factors and rating scale |
| `security_checklist` | `_generate_security_checklist()` | ~1546 | IT security checklist (FISMA, FedRAMP) |
| `section_508` | `_generate_section_508()` | ~1610 | Section 508 accessibility compliance statement |
| `cor_certification` | `_generate_cor_certification()` | ~1681 | COR nominee certification with FAC-COR level |
| `contract_type_justification` | `_generate_contract_type_justification()` | ~1754 | Contract type D&F elements |

### Generator Pattern

All generators follow the same signature and pattern:

```python
def _generate_{doc_type}(title: str, data: dict) -> str:
    """Generate a {document name} document."""
    # Extract fields from data dict with defaults
    field = data.get("field_name", "default value")
    # Build markdown string with headers, sections, FAR references
    content = f"# {title}\n\n..."
    # Return markdown string
    return content
```

### S3 Save Pattern (in _exec_create_document)

```python
timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
s3_key = f"{prefix}documents/{doc_type}_{timestamp}.md"
_get_s3().put_object(Bucket="nci-documents", Key=s3_key, Body=content.encode())
```

---

## Part 7: Progressive Disclosure @tools

The supervisor has 4 lightweight @tools that give on-demand access to skill metadata and plugin data WITHOUT spawning subagents or bloating the system prompt.

| Layer | Tool | When to Use |
|-------|------|-------------|
| 1 | System prompt hints | Already have short descriptions — no tool call needed |
| 2 | `list_skills()` | Discover available skills, agents, and data file names |
| 3 | `load_skill(name)` | Read full skill instructions/workflows to follow yourself |
| 4 | `load_data(name, section?)` | Fetch reference data (thresholds, vehicles, doc rules) |

**`list_skills`**: Returns `{skills, agents, data}` from `SKILLS`, `AGENTS`, and `_load_plugin_config()["data"]`.

**`load_skill`**: Returns `PLUGIN_CONTENTS[name]["body"]` — the full SKILL.md or agent.md content.

**`load_data`**: Reads from `eagle-plugin/data/{name}.json`. The `data` index is in `plugin.json` — `_load_plugin_config()` MUST include it (fixed bug: was returning only DynamoDB manifest which lacks the `data` key).

**`query_compliance_matrix`**: Calls `compliance_matrix.execute_operation(parsed_params)`. Params are passed as a JSON string.

All 4 tools are factory functions so they close over `result_queue`/`loop` for tool_result observability.

---

## Part 8: SYSTEM_PROMPT (strands_agentic_service.py — Primary Path)

### Supervisor Prompt Sections (build_supervisor_prompt)

| Section | Content |
|---------|---------|
| Tenant context | `Tenant: {id} | User: {id} | Tier: {tier}` |
| Base prompt | From wspc_store/AGENTS["supervisor"]["body"] |
| Active specialists | One line per skill: `- {name}: {description}` |
| Progressive Disclosure | 4-layer system: hints → list_skills → load_skill → load_data |
| KB Retrieval Rules | knowledge_search → knowledge_fetch → Sources section |
| Document Output Rules | MUST call create_document; no inline doc bodies |
| FAST vs DEEP routing | FAST: load_data/query_compliance/search_far/KB; DEEP: specialists only for complex analysis |

### Five Phases (Legacy Path — agentic_service.py SYSTEM_PROMPT)

Note: The Strands path uses `build_supervisor_prompt()`. The legacy `SYSTEM_PROMPT` in `agentic_service.py` is only used by the WebSocket path and direct `stream_chat()` callers.

| Phase | Name | Actions |
|-------|------|---------|
| 1 | Minimal Intake | Collect requirement description, cost range, timeline |
| 2 | Clarifying Questions | Product vs service, vendor knowledge, funding, urgency |
| 3 | Pathway Determination | Micro-purchase / Simplified / Negotiated; contract type; set-asides |
| 4 | Document Requirements | Identify and generate required documents by acquisition type |
| 5 | Summary & Handoff | Determination table, document checklist, next steps |

---

## Part 9: Session Store (session_store.py)

### Unified `eagle` Table Access

All DynamoDB operations go through `session_store.py`, which implements the unified single-table design:

| Operation | PK | SK | Notes |
|-----------|----|----|-------|
| `create_session()` | `SESSION#{tenant}#{user}` | `SESSION#{session_id}` | Auto-generates UUID if not provided |
| `get_session()` | `SESSION#{tenant}#{user}` | `SESSION#{session_id}` | Returns None if not found |
| `list_sessions()` | `SESSION#{tenant}#{user}` | `begins_with(SESSION#)` | Sorted by created_at desc |
| `add_message()` | `SESSION#{tenant}#{user}` | `MSG#{session_id}#{msg_id}` | msg_id is auto-incremented |
| `get_messages()` | `SESSION#{tenant}#{user}` | `begins_with(MSG#{session_id}#)` | Sorted by SK |
| `record_usage()` | `USAGE#{tenant}` | `USAGE#{date}#{session}#{ts}` | Token counts, cost, model |

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

## Part 10: Authentication

### Two Auth Systems (Both Active)

**cognito_auth.py** (new/primary — used by main.py EAGLE endpoints):
```python
@dataclass
class UserContext:
    user_id: str
    tenant_id: str
    email: str
    tier: str  # "free", "pro", "enterprise"
    groups: List[str]

# main.py uses:
from .cognito_auth import UserContext, extract_user_context, DEV_MODE, DEV_USER_ID, DEV_TENANT_ID
```

**auth.py** (legacy — still active, used by admin_auth.py and legacy routes):
```python
async def get_current_user(credentials) -> Dict:
    # Returns dict with user_id, tenant_id, subscription_tier, cognito:groups
    # DEV_MODE returns dev-user / dev-tenant with PREMIUM tier

# admin_auth.py imports:
from app.auth import get_current_user  # NOT from cognito_auth
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

## Part 11: main.py Route Groups (~80+ endpoints)

| Group | Prefix | Count | Key Files Used |
|-------|--------|-------|----------------|
| Chat (SDK) | `/api/chat` | 1 | strands_agentic_service.py |
| Sessions | `/api/sessions` | 6 | session_store.py |
| Documents | `/api/documents` | 4 | document_export.py, S3 |
| Admin (EAGLE) | `/api/admin` | 12 | admin_service.py, admin_cost_service.py |
| User | `/api/user` | 3 | session_store.py |
| Tenants | `/api/tenants` | 6 | cost_attribution.py, session_store.py |
| WebSocket | `/ws/chat` | 1 | strands_agentic_service.py |
| Health | `/api/health` | 1 | — |
| MCP Weather | `/api/mcp/weather` | 2 | weather_mcp_service.py |
| Plugin Admin | `/api/admin/plugin` | 5 | plugin_store.py |
| Workspace | `/api/workspace` | 8 | workspace_store.py, wspc_store.py |
| Prompt Admin | `/api/admin/prompts` | 3 | prompt_store.py |
| Config | `/api/admin/config` | 4 | config_store.py |
| Templates | `/api/templates` | 4 | template_store.py |
| Skills | `/api/skills` | 8 | skill_store.py |
| Packages | `/api/packages` | 12 | package_store.py, document_store.py, approval_store.py |
| Preferences | `/api/user/preferences` | 3 | pref_store.py |
| Streaming (SSE) | `/stream/...` | mounted via include_router | streaming_routes.py |

The streaming router is wired at main.py:1121: `streaming_router = create_streaming_router(subscription_service); app.include_router(streaming_router)`

`streaming_routes.py` imports from `strands_agentic_service` (not `sdk_agentic_service`):
```python
from .strands_agentic_service import sdk_query, sdk_query_streaming, MODEL, EAGLE_TOOLS
```

---

## Part 12: CDK Integration Points

### EagleCoreStack → Backend

| Resource | CDK Reference | Backend Usage |
|----------|---------------|---------------|
| DynamoDB `eagle` | `Table.fromTableName()` (imported) | `session_store.py`, `agentic_service.py` |
| DynamoDB `eagle-document-metadata-dev` | Created by Storage stack | `tools/knowledge_tools.py` — knowledge_search |
| S3 `nci-documents` | `Bucket.fromBucketName()` (imported) | `agentic_service.py` s3_document_ops, create_document |
| S3 `eagle-documents-695681773636-dev` | Created by Storage stack | `tools/knowledge_tools.py` — knowledge_fetch |
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

## Part 13: Known Issues and Patterns

### Patterns That Work

- Lazy singleton AWS clients (`_get_s3()`, etc.) avoid repeated initialization
- `TOOLS_NEEDING_SESSION` set cleanly separates user-scoped vs. tenant-scoped handlers
- `json.dumps(result, indent=2, default=str)` handles datetime + Decimal serialization
- Document generators use `data.get("field", "default")` for graceful degradation
- `_get_user_prefix()` centralizes S3 path construction
- Composite `scoped_session_id = f"{tenant_id}#advanced#{user_id}#{session_id}"` gives legacy handlers the real tenant/user context without changing handler signatures
- Single shared `_model = BedrockModel(...)` at import time — no per-request boto3 overhead
- Factory tool pattern (`_make_service_tool`, `_make_list_skills_tool`, etc.) closes over `result_queue`/`loop` — all tool handlers automatically emit `tool_result` events for frontend observability
- `_maybe_fast_path_document_generation()` + `_ensure_create_document_for_direct_request()` dual-safety: fast path for explicit "generate" requests, reconciliation step for missed tool calls
- `_load_plugin_config()` loads bundled `plugin.json` first (has full `data` index), then overlays DynamoDB manifest — prevents `load_data()` from returning "available: []"
- `knowledge_fetch` description says "REQUIRES an s3_key from a prior knowledge_search result" — prevents hallucinated calls
- `_emit_tool_result()` shared helper truncates large content fields (content/text/body keys) to 2000 chars before pushing to result_queue — prevents SSE bloat
- Unified `eagle` DynamoDB table with PK/SK patterns handles sessions, messages, usage, costs in one table
- Write-through cache in session_store.py gives fast reads without stale data
- `DEV_MODE` flag in cognito_auth.py lets backend run without Cognito — essential for local dev
- CDK `fromTableName()` / `fromBucketName()` pattern — import existing resources without recreating them
- Internal ALB for backend keeps API not internet-accessible — frontend ALB is the only public entry point
- Dockerfile copies `eagle-plugin/` to `../eagle-plugin/` so `eagle_skill_constants.py` can walk it at runtime
- Workspace 4-layer prompt resolution enables hot-reloadable agent prompts without ECS redeploy

### Patterns to Avoid

- Don't add AWS client initialization outside lazy singletons (cold start cost)
- Don't hardcode `"demo-tenant"` in handlers — always use `_extract_tenant_id()`
- Don't skip `default=str` in `json.dumps()` — DynamoDB returns Decimal types
- Don't add new tools without updating BOTH `TOOL_DISPATCH` in `agentic_service.py` AND `_SERVICE_TOOL_DEFS` in `strands_agentic_service.py` (the Strands path skips TOOL_DISPATCH registration for tools not in _make_service_tool)
- Don't assume `admin_auth.py` uses `cognito_auth.py` — it still imports from `auth.py` (legacy `get_current_user`)
- Don't create a `server/legacy/` directory expecting archived files there — `auth.py`, `gateway_client.py`, `mcp_agent_integration.py`, `weather_mcp_service.py` are still in `server/app/` and some are still imported
- Don't call `_load_plugin_config()` expecting only DynamoDB results — DynamoDB manifest only has version/agent_count/skill_count, NOT the `data` index
- Don't call `knowledge_fetch` without an `s3_key` from a prior `knowledge_search` — the tool returns an error, but the model may still hallucinate keys
- Don't add new progressive disclosure factory tools without closing over `result_queue`/`loop` — otherwise tool results won't be emitted and won't appear in the frontend activity panel
- Don't test document generation with empty `data` dicts — generators produce minimal stubs
- Don't call `_get_s3()` at module level — fails if AWS creds aren't configured at import time
- Don't hardcode `"nci-documents"` bucket name — use `os.getenv("S3_BUCKET", "nci-documents")` for CDK flexibility
- Don't delete AWS resources without confirming new CDK stacks have images pushed and running tasks
- Don't expect `sdk_agentic_service.py` to be the active orchestrator — it has been replaced by `strands_agentic_service.py`; `streaming_routes.py` imports from `strands_agentic_service`
- Don't open test files without `encoding="utf-8"` on Windows — cp1252 chokes on UTF-8 chars in main.py and other files with Unicode content

### Common Issues

- **`load_data` returns "available: []"**: `_load_plugin_config()` returned only DynamoDB manifest (fixed: always load bundled `plugin.json` first). Check `eagle-plugin/plugin.json` has `"data": {...}` key.
- **Missing TOOL_DISPATCH entry**: Tool name in `_SERVICE_TOOL_DEFS` but not in `TOOL_DISPATCH` → `_make_service_tool()` raises `ValueError("No handler for tool: {name}")`
- **Missing _SERVICE_TOOL_DEFS entry**: Tool registered in `TOOL_DISPATCH` but not wired into supervisor via `_build_service_tools()` → model can't call it
- **Session scoping mismatch**: Tool added to `TOOLS_NEEDING_SESSION` but handler signature only takes `(params, tenant_id)`
- **DynamoDB Decimal**: `json.dumps()` without `default=str` raises `TypeError` on Decimal values
- **S3 prefix trailing slash**: `_get_user_prefix()` always ends with `/` — don't add another
- **admin_auth.py import error**: If `auth.py` is ever removed, `admin_auth.py` will break — it imports `get_current_user` from `app.auth`
- **Tool result not showing in frontend**: Factory tool doesn't close over `result_queue`/`loop` → result never pushed to queue → no `tool_result` SSE event
- **AWS credentials not configured**: All tool handlers fail with ClientError
- **S3 bucket "nci-documents" doesn't exist**: s3_document_ops and create_document fail
- **DynamoDB table "eagle" doesn't exist**: dynamodb_intake and session_store fail
- **METADATA_TABLE / DOCUMENT_BUCKET not set**: knowledge_search/knowledge_fetch fail silently with default names
- **`MSYS_NO_PATHCONV=1` required** on MINGW64/Git Bash when running AWS CLI with `/aws/...` paths
- **Versioned S3 buckets** can't be deleted with `aws s3 rb --force` on MINGW — use Python boto3 `bucket.object_versions.delete()`
- **Windows cp1252 encoding**: `open(file).read()` chokes on UTF-8 chars in Python source files — always use `open(file, encoding="utf-8").read()`

### Adding a New Tool Handler

Checklist for adding a new tool to the Strands path:

1. **Define handler function** in `agentic_service.py`: `def _exec_new_tool(params, tenant_id)` or `(params, tenant_id, session_id)`
2. **Add to `TOOL_DISPATCH`** (`agentic_service.py` line ~2548): `"new_tool": _exec_new_tool,`
3. **Add to `TOOLS_NEEDING_SESSION`** (line ~2566) if it needs per-user scoping
4. **Add to `_SERVICE_TOOL_DEFS`** (`strands_agentic_service.py` line ~1010): `"new_tool": "description string"`
   - This wires the tool into `_build_service_tools()` → supervisor's `Agent(tools=[...])`
5. **Add to `EAGLE_TOOLS`** (strands_agentic_service.py line ~318): Anthropic tool_use schema for health/status endpoints
6. **Update `SYSTEM_PROMPT` / `build_supervisor_prompt()`** if the tool needs usage guidance
7. **Validate**: `python -c "import py_compile; py_compile.compile('server/app/agentic_service.py', doraise=True)"`

### stream_chat() Tool-Use Loop (Legacy Path — WebSocket)

```
stream_chat(messages, on_text, on_tool_use, on_tool_result, session_id)
  |-- MAX_TOOL_ITERATIONS = 10
  |-- Loop:
  |     |-- Send messages to Claude with EAGLE_TOOLS
  |     |-- Stream response (text deltas + tool_use blocks)
  |     |-- If stop_reason == "tool_use":
  |     |     |-- For each tool_use block:
  |     |     |     |-- execute_tool(name, input, session_id)
  |     |     |     |-- Append tool_result to messages
  |     |     |-- Continue loop
  |     |-- Else: break (end_turn or max_tokens)
  |-- Return {text, usage, model, tools_called}
```

Note: `api_chat()` REST endpoint and `stream_generator()` SSE use `sdk_query()` / `sdk_query_streaming()` (Strands path). The `stream_chat()` legacy path is used by WebSocket endpoint only.

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
- Workspace 4-layer prompt resolution enables hot-reloadable agent prompts without ECS redeploy (discovered: 2026-02-25, component: wspc_store)
- `_load_plugin_config()` must load bundled `plugin.json` first, then overlay DynamoDB — DynamoDB PLUGIN#manifest only stores version/agent_count/skill_count, NOT the `data` index needed by `load_data()` (discovered: 2026-03-09, component: strands_agentic_service)
- Factory tool pattern (`_make_service_tool`, `_make_list_skills_tool`, etc.) closing over `result_queue`/`loop` gives automatic tool_result observability without changing handler signatures (discovered: 2026-03-09, component: strands_agentic_service)
- `_emit_tool_result()` shared helper centralizes truncation and queue push for all factory tools — add new factory tools using this helper rather than inlining the queue push (discovered: 2026-03-09, component: strands_agentic_service)
- Composite session_id `f"{tenant_id}#advanced#{user_id}#{session_id}"` lets Strands path pass real user context to legacy handlers without changing their signatures (discovered: 2026-03-09, component: strands_agentic_service)
- `_maybe_fast_path_document_generation()` + `_ensure_create_document_for_direct_request()` dual-safety ensures `create_document` is always called for document requests — prevents both slow multi-tool loops and missed tool calls (discovered: 2026-03-09, component: strands_agentic_service)
- Single shared `BedrockModel` at import time (not per-request) — accounts for no per-request boto3 overhead in Strands (discovered: 2026-03-09, component: strands_agentic_service)
- `stream_async()` replaces two-queue architecture: SDK bridges sync→async internally; `result_queue` is still used by factory tools for tool_result events that aren't naturally yielded by the stream (discovered: 2026-03-09, component: strands_agentic_service)

### patterns_to_avoid

- Don't test document generation with empty `data` dicts — generators produce minimal stubs
- Don't assume DynamoDB items have all fields — use `.get()` with defaults
- Don't call `_get_s3()` at module level — fails if AWS creds aren't configured at import time
- Don't create S3 clients inline per request (as in main.py `api_list_documents`) — use the lazy singleton from agentic_service.py instead (discovered: 2026-02-16, component: main.py)
- Don't hardcode `"nci-documents"` bucket name — use `os.getenv("S3_BUCKET", "nci-documents")` for CDK flexibility (discovered: 2026-02-16, component: cdk-eagle)
- Don't delete AWS resources (CF stacks, Lightsail, ECS) without confirming the new CDK stacks have images pushed and running tasks (discovered: 2026-02-16, component: aws-cleanup)
- Don't expect `server/legacy/` to exist — `auth.py`, `gateway_client.py`, `mcp_agent_integration.py`, `weather_mcp_service.py` remain in `server/app/` (verified 2026-02-25)
- Don't assume `admin_auth.py` was migrated to `cognito_auth` — it still imports `get_current_user` from `app.auth` (verified 2026-02-25)
- Don't add a tool only to `TOOL_DISPATCH` — also add to `_SERVICE_TOOL_DEFS` or the tool won't be wired into the Strands supervisor (discovered: 2026-03-09, component: strands_agentic_service)
- Don't call `_load_plugin_config()` and expect `data` key from DynamoDB — DynamoDB manifest only has version/agent_count/skill_count (discovered: 2026-03-09, component: strands_agentic_service)
- Don't open Python/text files on Windows without `encoding="utf-8"` — cp1252 raises UnicodeDecodeError on UTF-8 source files (discovered: 2026-03-09, component: test_chat_endpoints.py)
- Don't assume `sdk_agentic_service.py` is the active orchestrator — `streaming_routes.py` imports from `strands_agentic_service` (verified 2026-03-09)

### common_issues

- AWS credentials not configured → all tool handlers fail with ClientError
- S3 bucket "nci-documents" doesn't exist → s3_document_ops and create_document fail
- DynamoDB table "eagle" doesn't exist → dynamodb_intake and session_store fail
- CloudWatch log group "/eagle/test-runs" doesn't exist → cloudwatch_logs returns empty
- ECS services show desiredCount=1 but runningCount=0 → no Docker images pushed to ECR yet (discovered: 2026-02-16, component: compute-stack)
- `MSYS_NO_PATHCONV=1` required on MINGW64/Git Bash when running AWS CLI with `/aws/...` paths — otherwise Git Bash converts them to `C:/Program Files/Git/aws/...` (discovered: 2026-02-16, component: aws-cli)
- Cognito pools with custom domains require `delete-user-pool-domain` before `delete-user-pool` (discovered: 2026-02-16, component: cognito)
- Versioned S3 buckets can't be deleted with `aws s3 rb --force` on MINGW — use Python boto3 with `bucket.object_versions.delete()` instead (discovered: 2026-02-16, component: s3)
- `load_data` tool returns `{"error": "No data file named 'matrix'", "available": []}` → `_load_plugin_config()` was returning only DynamoDB manifest (missing `data` key) — fixed: always load bundled `plugin.json` first (discovered: 2026-03-09, component: strands_agentic_service)
- `tool_result` events missing from SSE stream → factory tool not using `_emit_tool_result()` or not closing over `result_queue`/`loop` (discovered: 2026-03-09, component: strands_agentic_service)
- `knowledge_fetch` called without `s3_key` → returns `{"error": "s3_key or document_id required"}` — always call `knowledge_search` first and pass the returned `s3_key` (discovered: 2026-03-09, component: knowledge_tools)
- `open(file).read()` on Windows with Python source files → UnicodeDecodeError (cp1252 vs UTF-8) — use `open(file, encoding="utf-8").read()` (discovered: 2026-03-09, component: test_chat_endpoints.py)

### tips

- Use `execute_tool()` for testing — it's synchronous and returns JSON strings
- The `search_far` tool has no AWS dependency — good for offline testing
- `intake_workflow` is stateless — workflow state is tracked in the response, not persisted
- Check `EAGLE_TOOLS` list in `strands_agentic_service.py` for the exact parameter schemas (used by health/status endpoints)
- Check `_SERVICE_TOOL_DEFS` in `strands_agentic_service.py` for what the supervisor can call
- Backend health check is at `/api/health` (not `/health`) — confirm ALB target group health path matches (discovered: 2026-02-25, verified from main.py)
- `main.py` version is 4.0.0 — reflects the merged multi-tenant + EAGLE architecture
- `session_store.py` uses `boto3.resource("dynamodb")` (high-level) while `agentic_service.py` uses `boto3.client("dynamodb")` (low-level) — both access the same `eagle` table
- Old infrastructure (Lightsail, old ECS clusters, old CF stacks) was cleaned up 2026-02-16 — ~$51-63/mo savings
- Two model env vars: `EAGLE_BEDROCK_MODEL_ID` (strands, overrides auto-selection) vs `ANTHROPIC_MODEL` (legacy agentic_service.py only) — set `EAGLE_BEDROCK_MODEL_ID` for the Strands path
- `api_chat()` REST endpoint uses `sdk_query()` (Strands path) — tool calls go through `_make_service_tool()` which calls `TOOL_DISPATCH` handlers directly with real tenant/user context
- `stream_generator()` in `streaming_routes.py` injects keepalive SSE comments every 20s to prevent ALB idle timeout (raised to 300s); keepalive chunks are `{"type": "_keepalive"}` internally
- `strands_agentic_service.py` docstring for `sdk_query_streaming()` correctly says "Uses Agent.stream_async()" — `result_queue` is still used by factory tools, not for streaming text
- `knowledge_search` DynamoDB scan is efficient for ~200 docs — no secondary indexes needed at current scale
- `DOCUMENT_BUCKET` and `METADATA_TABLE` have separate env vars from `S3_BUCKET`/`EAGLE_TABLE` — the knowledge base uses dedicated resources
