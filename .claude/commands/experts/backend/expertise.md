---
type: expert-file
parent: "[[backend/_index]]"
file-type: expertise
human_reviewed: false
tags: [expert-file, mental-model, backend, agentic-service, eagle, aws, s3, dynamodb, cloudwatch]
last_updated: 2026-03-04T00:00:00
---

# Backend Expertise (Complete Mental Model)

> **Sources**: server/app/*.py, server/eagle_skill_constants.py, infrastructure/cdk-eagle/lib/*.ts

---

## Part 1: Architecture Overview

### File Layout

```
server/app/
├── main.py                  # FastAPI app (v4.0.0), CORS, ~80+ endpoints, 1855+ lines
├── agentic_service.py       # 2358 lines — tool dispatch, handlers, stream_chat (LEGACY orchestrator)
├── sdk_agentic_service.py   # SDK-based service — SKILL_AGENT_REGISTRY, sdk_query() (PRIMARY orchestrator)
├── eagle_tools_mcp.py       # NEW — wraps execute_tool() as local MCP server (7 EAGLE business tools)
├── session_store.py         # Unified DynamoDB session/message/usage store (eagle table)
├── cognito_auth.py          # Cognito JWT auth, UserContext, DEV_MODE fallback
├── auth.py                  # Legacy auth (get_current_user) — still active, imported by main.py + admin_auth.py
├── document_export.py       # DOCX/PDF/Markdown export
├── admin_service.py         # Dashboard stats, rate limiting, cost tracking
├── admin_auth.py            # Admin group auth (imports from auth.py — NOT yet migrated to cognito_auth)
├── admin_cost_service.py    # 4-level cost reports (tenant, user, service, comprehensive)
├── subscription_service.py  # Tier-based limits (SubscriptionTier enum)
├── cost_attribution.py      # Per-tenant/user cost attribution
├── streaming_routes.py      # SSE streaming router (mounted via include_router at line 1121)
├── models.py                # Pydantic models (ChatMessage, TenantContext, etc.)
├── stream_protocol.py       # Stream protocol definitions
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
├── feedback_store.py        # Feedback submissions (FEEDBACK# entity, 7-year TTL, auto-type detection)
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
| LLM SDK | `anthropic` Python SDK | Direct API or Bedrock |
| Agent SDK | `claude_agent_sdk` | query(), AgentDefinition, ClaudeAgentOptions |
| AWS SDK | `boto3` | S3, DynamoDB, CloudWatch, Cognito |
| Runtime | Python 3.11+ | `str | None` union syntax used |
| Async | `asyncio` | `stream_chat()` and `sdk_query()` are async generators |
| Auth | Cognito JWT | `cognito_auth.py` with DEV_MODE fallback; `auth.py` still active for legacy routes |
| Persistence | DynamoDB `eagle` table | Single-table design via `session_store.py` |
| Logging | `logging` | Logger: `eagle.agent`, `eagle.sessions`, `eagle.sdk_agent`, `eagle.tools_mcp` |
| MCP | `create_sdk_mcp_server` | Local MCP via `eagle_tools_mcp.py` for SDK subagents |

### Entry Points

| Function | File | Purpose |
|----------|------|---------|
| `execute_tool()` | agentic_service.py:2181 | Synchronous tool dispatch — called by test suite, chat, and eagle_tools_mcp |
| `stream_chat()` | agentic_service.py:~2221 | Async streaming chat with tool-use loop (legacy path) |
| `get_client()` | agentic_service.py:~2206 | Create Anthropic/AnthropicBedrock client |
| `sdk_query()` | sdk_agentic_service.py:274 | PRIMARY: async generator — supervisor + skill subagents via Claude SDK |
| `create_eagle_mcp_server()` | eagle_tools_mcp.py:122 | Factory: returns local MCP server wrapping all 7 execute_tool() handlers |
| `api_chat()` | main.py:191 | REST chat — now calls sdk_query() (not stream_chat()) |
| `websocket_chat()` | main.py:718 | WebSocket streaming chat |
| `api_list_sessions()` | main.py:298 | Session CRUD endpoints |
| `api_export_document()` | main.py:445 | Document export (DOCX/PDF/MD) |
| `api_list_documents()` | main.py:508 | S3 document browser |
| `api_submit_feedback()` | main.py:~1182 | POST /api/feedback — system action, no AI, direct DDB write |

### Configuration

```python
# agentic_service.py (legacy orchestrator config)
_USE_BEDROCK = os.getenv("USE_BEDROCK", "false").lower() == "true"
_BEDROCK_REGION = os.getenv("AWS_REGION", "us-east-1")
MODEL = os.getenv("ANTHROPIC_MODEL", "us.anthropic.claude-haiku-4-5-20251001-v1:0" if _USE_BEDROCK else "claude-haiku-4-5-20251001")

# sdk_agentic_service.py (SDK orchestrator config)
MODEL = os.getenv("EAGLE_SDK_MODEL", "haiku")  # separate env var from legacy MODEL

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
  ANTHROPIC_API_KEY  → Secrets Manager
  EAGLE_TABLE        → "eagle" (DynamoDB)
  S3_BUCKET          → "nci-documents"
  AWS_REGION         → "us-east-1"
  LOG_GROUP          → "/eagle/app"
  EAGLE_SDK_MODEL    → model alias for sdk_agentic_service (e.g. "haiku")
  USE_PERSISTENT_SESSIONS → "true"
  REQUIRE_AUTH       → "false" (dev) / "true" (prod)
  EAGLE_TELEMETRY_LOG_GROUP → "/eagle/telemetry" (used by feedback CW log fetch)
```

---

## Part 2: Tool Dispatch System

### TOOL_DISPATCH (agentic_service.py line 2167)

```python
TOOL_DISPATCH = {
    "s3_document_ops":  _exec_s3_document_ops,
    "dynamodb_intake":  _exec_dynamodb_intake,
    "cloudwatch_logs":  _exec_cloudwatch_logs,
    "search_far":       _exec_search_far,
    "create_document":  _exec_create_document,
    "get_intake_status": _exec_get_intake_status,
    "intake_workflow":  _exec_intake_workflow,
}
```

### TOOLS_NEEDING_SESSION (agentic_service.py line 2178)

```python
TOOLS_NEEDING_SESSION = {"s3_document_ops", "create_document", "get_intake_status"}
```

These tools receive `session_id` as a third argument to enable per-user S3 prefix scoping.

### execute_tool() Flow (line 2181)

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

### eagle_tools_mcp.py — MCP Wrapper Layer

`create_eagle_mcp_server(tenant_id, session_id)` wraps all 7 TOOL_DISPATCH handlers as a local MCP server:

```python
# eagle_tools_mcp.py
from claude_agent_sdk import create_sdk_mcp_server, tool

def create_eagle_mcp_server(tenant_id="demo-tenant", session_id=None):
    # Closes over _tenant_id and _session_id
    # Registers 7 @tool-decorated async functions, each calling _execute_tool()
    return create_sdk_mcp_server("eagle-tools", tools=[...])
```

Each tool function converts typed input dataclasses to dicts then calls `_execute_tool(tool_name, tool_input, session_id)`.

The MCP server is wired into `sdk_query()` via:
```python
mcp_servers = {"eagle-tools": create_eagle_mcp_server(tenant_id=tenant_id, session_id=_mcp_session_id)}
options = ClaudeAgentOptions(..., mcp_servers=mcp_servers)
```

---

## Part 3: SDK Agentic Service (sdk_agentic_service.py) — PRIMARY

### Architecture

```
sdk_query()
  |-- build_skill_agents()   → dict of name→AgentDefinition (from eagle-plugin/)
  |-- build_supervisor_prompt() → supervisor system prompt with subagent list
  |-- create_eagle_mcp_server() → local MCP with 7 EAGLE business tools
  |-- ClaudeAgentOptions(model, system_prompt, allowed_tools=["Task"],
  |       agents=agents, mcp_servers=mcp_servers, max_turns, max_budget_usd)
  |-- query(prompt, options) → async generator of SDK message objects
```

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

The MCP tool names (`s3_document_ops`, `create_document`, etc.) now appear directly in `TIER_TOOLS` — subagents reference MCP tools by the same name as TOOL_DISPATCH keys.

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

## Part 4: AWS Tool Handlers

### _exec_s3_document_ops (agentic_service.py line 384)

**Actions**: `read`, `write`, `list`

| Action | Required Params | Returns |
|--------|----------------|---------|
| `read` | `key` | `{content, key, metadata}` |
| `write` | `key`, `content` | `{message, key, size}` |
| `list` | (optional: `prefix`) | `{documents: [{key, size, last_modified}], count}` |

- **Bucket**: `nci-documents`
- **Key prefix**: `eagle/{tenant}/{user}/` (from `_get_user_prefix()`)
- **Full key**: `{prefix}{params.key}`

### _exec_dynamodb_intake (line 471)

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

### _exec_cloudwatch_logs (line 589)

**Actions**: `get_stream`, `recent`, `search`

| Action | Required Params | Returns |
|--------|----------------|---------|
| `get_stream` | `stream_name` | `{events: [...], count}` |
| `recent` | (optional: `limit`) | `{streams: [...], count}` |
| `search` | `pattern` | `{matches: [...], count}` |

- **Log group**: `/eagle/test-runs`
- Read-only operations; no write/delete actions

### _exec_search_far (line 708)

**Params**: `query` (search text), optional `parts` (FAR parts to search)

- Returns matching FAR clauses with relevance
- Uses embedded FAR reference data
- No AWS resource dependency

### _exec_create_document (line 1027)

**Params**: `doc_type`, `title`, `data` (dict of document-specific fields)

- Dispatches to `_generate_{doc_type}()` function
- Saves generated markdown to S3: `eagle/{tenant}/{user}/documents/{doc_type}_{timestamp}.md`
- Returns `{message, doc_type, s3_key, content_preview, word_count}`

### _exec_get_intake_status (line 1828)

**Params**: (none required)

- Scans S3 prefix `eagle/{tenant}/{user}/documents/` for existing docs
- Tracks 10 document types: 5 always required + 5 conditional
- Returns `{status: {type: "complete"|"pending"}, summary: {complete, pending, total}}`

**Always required**: sow, igce, market_research, acquisition_plan, cor_certification
**Conditional**: justification, eval_criteria, security_checklist, section_508, contract_type_justification

### _exec_intake_workflow (line 1955)

**Actions**: `start`, `advance`, `status`

| Action | Params | Returns |
|--------|--------|---------|
| `start` | `requirement_description` | `{workflow_id, stage, next_actions, progress_bar}` |
| `advance` | `workflow_id`, `completed_actions` | `{stage, next_actions, progress_bar}` |
| `status` | `workflow_id` | `{stage, progress, completed_documents}` |

- 4-stage workflow: Requirements Gathering -> Compliance Check -> Document Generation -> Review & Submit

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
| `sow` | `_generate_sow()` | 1086 | Statement of Work with objectives, deliverables, period of performance |
| `igce` | `_generate_igce()` | 1173 | Independent Government Cost Estimate with line items, totals |
| `market_research` | `_generate_market_research()` | 1250 | Market analysis, vendor capabilities, pricing benchmarks |
| `justification` | `_generate_justification()` | 1313 | Justification & Approval for sole source (FAR 6.302) |
| `acquisition_plan` | `_generate_acquisition_plan()` | 1381 | Streamlined 5-section acquisition plan |
| `eval_criteria` | `_generate_eval_criteria()` | 1481 | Technical evaluation factors and rating scale |
| `security_checklist` | `_generate_security_checklist()` | 1546 | IT security checklist (FISMA, FedRAMP) |
| `section_508` | `_generate_section_508()` | 1610 | Section 508 accessibility compliance statement |
| `cor_certification` | `_generate_cor_certification()` | 1681 | COR nominee certification with FAC-COR level |
| `contract_type_justification` | `_generate_contract_type_justification()` | 1754 | Contract type D&F elements |

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

### Document Data Fields

Each generator accepts different fields in the `data` dict. Common patterns:
- `title` is always the first positional argument
- `data.get("field", "default")` for optional fields
- Generators produce self-contained markdown with FAR references
- Word counts typically 200-800 words depending on type

---

## Part 7: SYSTEM_PROMPT (agentic_service.py — Legacy Path)

### Structure (7 Sections, ~4800 chars)

| Section | Content |
|---------|---------|
| 1. Identity & Mission | EAGLE is NCI OA intake assistant, knows FAR/DFARS/HHSAR |
| 2. Intake Philosophy | "Trish" pattern — start minimal, ask smart follow-ups |
| 3. Five-Phase Workflow | Minimal Intake -> Clarifying -> Pathway -> Documents -> Summary |
| 4. Key Thresholds | MPT $15K, SAT $250K, Cost Data $750K, 8(a) $4M/$7M, Davis-Bacon $25K |
| 5. Specialist Lenses | Legal, Tech Translator, Market Intelligence, Public Interest |
| 6. Document Types | Lists all 10 types with brief descriptions |
| 7. Tool Usage | Guidance on when to use workflow vs. direct tool calls |

### Five Phases

| Phase | Name | Actions |
|-------|------|---------|
| 1 | Minimal Intake | Collect requirement description, cost range, timeline |
| 2 | Clarifying Questions | Product vs service, vendor knowledge, funding, urgency |
| 3 | Pathway Determination | Micro-purchase / Simplified / Negotiated; contract type; set-asides |
| 4 | Document Requirements | Identify and generate required documents by acquisition type |
| 5 | Summary & Handoff | Determination table, document checklist, next steps |

Note: The SDK path (`sdk_agentic_service.py`) uses `build_supervisor_prompt()` instead, which injects tenant context + subagent list into the supervisor's system prompt dynamically.

---

## Part 8: Known Issues and Patterns

### Patterns That Work

- Lazy singleton AWS clients (`_get_s3()`, etc.) avoid repeated initialization
- `TOOLS_NEEDING_SESSION` set cleanly separates user-scoped vs. tenant-scoped handlers
- `json.dumps(result, indent=2, default=str)` handles datetime serialization
- Document generators use `data.get("field", "default")` for graceful degradation
- `_get_user_prefix()` centralizes S3 path construction
- `eagle_tools_mcp.py` factory pattern lets `sdk_query()` inject tenant/session into all MCP tools via closure
- `TIER_TOOLS` gating in sdk_agentic_service lets different subscription tiers get different tool access without code branching
- Workspace 4-layer resolution (workspace override → PLUGIN# → bundled file) allows hot-reload without redeploy
- Non-fatal helper pattern: wrap AWS calls in `try/except Exception` returning a safe default (`[]`, `{}`, `""`) so the primary operation never fails due to supplementary data fetch (e.g. `_fetch_cloudwatch_logs_for_session` in main.py)
- `json.dumps(obj, default=str)` on conversation snapshots/CW log events silently handles non-serialisable types (Decimal, datetime) before storing to DynamoDB
- Lazy DDB singleton in store modules (`_dynamodb = None` / `_get_dynamodb()`) follows `audit_store.py` pattern — safe for both cold start and long-running processes
- `_TYPE_KEYWORDS` dict + `_detect_feedback_type()` gives zero-shot classification of free-text feedback into `bug`, `suggestion`, `praise`, `incorrect_info`, `general` without calling the LLM

### Patterns to Avoid

- Don't add AWS client initialization outside lazy singletons (cold start cost)
- Don't hardcode `"demo-tenant"` in handlers — always use `_extract_tenant_id()`
- Don't skip `default=str` in `json.dumps()` — DynamoDB returns Decimal types
- Don't add new tools without updating both `TOOL_DISPATCH` and `EAGLE_TOOLS` (legacy path) AND `TIER_TOOLS` (SDK path)
- Don't assume `admin_auth.py` uses `cognito_auth.py` — it still imports from `auth.py` (legacy `get_current_user`)
- Don't create a `server/legacy/` directory expecting archived files there — `auth.py`, `gateway_client.py`, `mcp_agent_integration.py`, `weather_mcp_service.py` are still in `server/app/` and some are still imported
- Don't omit `Request` from the fastapi import when using it as an endpoint parameter — `Request` is not imported by default with the other fastapi symbols; it must be explicitly listed: `from fastapi import FastAPI, Request, ...`

### Common Issues

- **Missing EAGLE_TOOLS entry**: Tool is dispatchable but Claude doesn't know about it (never called via legacy path)
- **Missing TOOL_DISPATCH entry**: Tool schema defined but `execute_tool()` returns "Unknown tool"
- **Missing TIER_TOOLS entry**: Tool registered in TOOL_DISPATCH and eagle_tools_mcp but SDK subagents have no permission to call it
- **Session scoping mismatch**: Tool added to `TOOLS_NEEDING_SESSION` but handler signature only takes `(params, tenant_id)`
- **DynamoDB Decimal**: `json.dumps()` without `default=str` raises `TypeError` on Decimal values
- **S3 prefix trailing slash**: `_get_user_prefix()` always ends with `/` — don't add another
- **admin_auth.py import error**: If `auth.py` is ever removed, `admin_auth.py` will break — it imports `get_current_user` from `app.auth`
- **`Request` import missing**: Using `request: Request` in an endpoint signature without adding `Request` to the `from fastapi import ...` line raises `NameError` at startup

### Adding a New Tool Handler

Checklist for adding a new tool:

1. **Define handler function**: `def _exec_new_tool(params, tenant_id)` or `(params, tenant_id, session_id)`
2. **Add to TOOL_DISPATCH** (agentic_service.py line 2167): `"new_tool": _exec_new_tool,`
3. **Add to TOOLS_NEEDING_SESSION** (line 2178) if it needs per-user scoping
4. **Add to EAGLE_TOOLS** (line 173): Anthropic tool_use schema with name, description, input_schema (legacy path)
5. **Add to eagle_tools_mcp.py**: new `@tool`-decorated async function + add to `tools=[...]` list in `create_sdk_mcp_server()` call
6. **Add to TIER_TOOLS** in sdk_agentic_service.py for appropriate tiers
7. **Update SYSTEM_PROMPT** if the tool needs usage guidance (legacy path) or supervisor prompt (SDK path)
8. **Validate**: `python -c "import py_compile; py_compile.compile('server/app/agentic_service.py', doraise=True)"`

### Adding a New Store Module

Follow the `audit_store.py` / `feedback_store.py` pattern:

```python
# Lazy DDB singletons — never initialize at module level
_dynamodb = None
_table = None

def _get_dynamodb():
    global _dynamodb
    if _dynamodb is None:
        region = os.environ.get("AWS_REGION", "us-east-1")
        _dynamodb = boto3.resource("dynamodb", region_name=region)
    return _dynamodb

def _get_table():
    global _table
    if _table is None:
        table_name = os.environ.get("TABLE_NAME", "eagle")
        _table = _get_dynamodb().Table(table_name)
    return _table
```

Then import in `main.py` as `from . import my_store` and call `my_store.write_*()` or `my_store.list_*()` from endpoints.

### Adding a "System Action" Endpoint (No AI, Direct DDB Write)

Pattern for endpoints like `POST /api/feedback` that validate input and write directly to DynamoDB without calling the LLM:

```python
@app.post("/api/feedback")
async def api_submit_feedback(
    request: Request,                            # requires Request in fastapi import
    user: UserContext = Depends(get_user_from_header),
):
    body = await request.json()
    field = body.get("field", "").strip()

    if not field:
        raise HTTPException(status_code=400, detail="field is required")

    # Optional: fetch supplementary AWS data non-fatally
    extra_data = _fetch_something_nonfatal(body.get("session_id", ""))

    my_store.write_record(
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        ...
        extra=json.dumps(extra_data, default=str),   # default=str handles Decimal/datetime
    )
    return {"status": "ok", "message": "Recorded. Thank you!"}
```

### Non-Fatal AWS Helper Pattern

Use this pattern for supplementary data fetches (e.g. CloudWatch logs attached to feedback) where failure must not block the primary operation:

```python
def _fetch_something_nonfatal(identifier: str) -> list:
    """Return data for identifier, or [] on any error (non-fatal)."""
    if not identifier:
        return []
    try:
        client = boto3.client("logs", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        response = client.filter_log_events(
            logGroupName=os.environ.get("MY_LOG_GROUP", "/eagle/telemetry"),
            filterPattern=identifier,
            limit=50,
        )
        return response.get("events", [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("fetch failed (non-fatal): %s", exc)
        return []
```

Key points:
- Catch bare `Exception` (not just `ClientError`) — covers network timeouts, missing log groups, etc.
- Use `# noqa: BLE001` to suppress ruff's "blind exception" lint warning when broad catch is intentional
- Log at `WARNING` level, not `ERROR` — it is expected to fail in dev/offline environments
- Return a typed empty collection (`[]`, `{}`) so callers don't need None checks

### stream_chat() Tool-Use Loop (Legacy Path)

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

Note: `api_chat()` in main.py now uses `sdk_query()` (SDK path), not `stream_chat()`. The `stream_chat()` path is used by WebSocket endpoint and direct callers.

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

### Feedback Store (feedback_store.py) — DDB Entity Layout

| Attribute | Value | Notes |
|-----------|-------|-------|
| `PK` | `FEEDBACK#{tenant_id}` | Partition by tenant |
| `SK` | `FEEDBACK#{ISO_timestamp}#{feedback_id}` | Sortable by time; UUID suffix ensures uniqueness |
| `GSI1PK` | `TENANT#{tenant_id}` | Cross-entity GSI for tenant queries |
| `GSI1SK` | `FEEDBACK#{created_at}` | Time-sorted within GSI |
| `feedback_type` | `bug` / `suggestion` / `praise` / `incorrect_info` / `general` | Auto-detected via `_TYPE_KEYWORDS` |
| `ttl` | Unix epoch 7 years from write | DynamoDB TTL attribute |

Public API:
- `write_feedback(tenant_id, user_id, tier, session_id, feedback_text, conversation_snapshot, cloudwatch_logs) -> dict`
- `list_feedback(tenant_id, limit=50) -> list[dict]`  — newest first, query on PK with `ScanIndexForward=False`

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

## Part 11: main.py Route Groups (~80+ endpoints, 1855+ lines)

| Group | Prefix | Count | Key Files Used |
|-------|--------|-------|----------------|
| Chat (SDK) | `/api/chat` | 1 | sdk_agentic_service.py |
| Sessions | `/api/sessions` | 6 | session_store.py |
| Documents | `/api/documents` | 4 | document_export.py, S3 |
| Admin (EAGLE) | `/api/admin` | 12 | admin_service.py, admin_cost_service.py |
| User | `/api/user` | 3 | session_store.py |
| Tenants | `/api/tenants` | 6 | cost_attribution.py, session_store.py |
| WebSocket | `/ws/chat` | 1 | sdk_agentic_service.py |
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
| Feedback | `/api/feedback` | 1 | feedback_store.py — system action, no AI |
| Streaming (SSE) | `/stream/...` | mounted via include_router | streaming_routes.py |

The streaming router is wired at main.py:1121: `streaming_router = create_streaming_router(subscription_service); app.include_router(streaming_router)`

---

## Part 12: CDK Integration Points

### EagleCoreStack → Backend

| Resource | CDK Reference | Backend Usage |
|----------|---------------|---------------|
| DynamoDB `eagle` | `Table.fromTableName()` (imported) | `session_store.py`, `agentic_service.py` |
| S3 `nci-documents` | `Bucket.fromBucketName()` (imported) | `agentic_service.py` s3_document_ops, create_document |
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

### EagleCiCdStack → Backend

| Resource | Purpose |
|----------|---------|
| OIDC Provider | GitHub Actions federation |
| Deploy Role | `eagle-github-actions-dev` — ECR push + ECS deploy |

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
- `eagle_tools_mcp.py` closure pattern captures tenant_id + session_id at factory time — all 7 MCP tool handlers are automatically scoped without passing context on each call (discovered: 2026-02-25, component: eagle_tools_mcp)
- `TIER_TOOLS` in sdk_agentic_service.py uses the same tool names as TOOL_DISPATCH keys — MCP tool names must match exactly (discovered: 2026-02-25, component: sdk_agentic_service)
- `sdk_query()` wraps `create_eagle_mcp_server()` in try/except — MCP unavailability is non-fatal, subagents degrade gracefully without business tools (discovered: 2026-02-25, component: sdk_agentic_service)
- Workspace 4-layer prompt resolution enables hot-reloadable agent prompts without ECS redeploy (discovered: 2026-02-25, component: wspc_store)
- Non-fatal supplementary fetch pattern (`try/except Exception` returning `[]`) lets feedback submission succeed even when CloudWatch is unreachable (discovered: 2026-03-04, component: main.py)
- `_TYPE_KEYWORDS` keyword-match classification avoids LLM call for feedback type tagging — deterministic, zero-latency (discovered: 2026-03-04, component: feedback_store)
- `feedback_store.py` lazy DDB singleton matches `audit_store.py` pattern exactly — easy to replicate for any new store module (discovered: 2026-03-04, component: feedback_store)
- `json.dumps(obj, default=str)` on conversation_snapshot before DDB write silently handles mixed types (Decimal, datetime, UUID) that boto3 cannot marshal directly (discovered: 2026-03-04, component: main.py)

### patterns_to_avoid
- Don't test document generation with empty `data` dicts — generators produce minimal stubs
- Don't assume DynamoDB items have all fields — use `.get()` with defaults
- Don't call `_get_s3()` at module level — fails if AWS creds aren't configured at import time
- Don't create S3 clients inline per request (as in main.py `api_list_documents`) — use the lazy singleton from agentic_service.py instead (discovered: 2026-02-16, component: main.py)
- Don't hardcode `"nci-documents"` bucket name — use `os.getenv("S3_BUCKET", "nci-documents")` for CDK flexibility (discovered: 2026-02-16, component: cdk-eagle)
- Don't delete AWS resources (CF stacks, Lightsail, ECS) without confirming the new CDK stacks have images pushed and running tasks (discovered: 2026-02-16, component: aws-cleanup)
- Don't expect `server/legacy/` to exist — `auth.py`, `gateway_client.py`, `mcp_agent_integration.py`, `weather_mcp_service.py` remain in `server/app/` (verified 2026-02-25)
- Don't assume `admin_auth.py` was migrated to `cognito_auth` — it still imports `get_current_user` from `app.auth` (verified 2026-02-25)
- Don't add a new MCP tool only to `eagle_tools_mcp.py` without also adding to TOOL_DISPATCH — the MCP layer delegates to `execute_tool()` which uses TOOL_DISPATCH
- Don't omit `Request` from the `from fastapi import ...` line — it is not auto-imported with `FastAPI`, `HTTPException`, etc.; missing it causes `NameError` at startup (discovered: 2026-03-04, component: main.py)

### common_issues
- AWS credentials not configured → all tool handlers fail with ClientError
- S3 bucket "nci-documents" doesn't exist → s3_document_ops and create_document fail
- DynamoDB table "eagle" doesn't exist → dynamodb_intake and session_store fail
- CloudWatch log group "/eagle/test-runs" doesn't exist → cloudwatch_logs returns empty
- ECS services show desiredCount=1 but runningCount=0 → no Docker images pushed to ECR yet (discovered: 2026-02-16, component: compute-stack)
- `MSYS_NO_PATHCONV=1` required on MINGW64/Git Bash when running AWS CLI with `/aws/...` paths — otherwise Git Bash converts them to `C:/Program Files/Git/aws/...` (discovered: 2026-02-16, component: aws-cli)
- Cognito pools with custom domains require `delete-user-pool-domain` before `delete-user-pool` (discovered: 2026-02-16, component: cognito)
- Versioned S3 buckets can't be deleted with `aws s3 rb --force` on MINGW — use Python boto3 with `bucket.object_versions.delete()` instead (discovered: 2026-02-16, component: s3)
- `claude_agent_sdk` import error at startup → `eagle_tools_mcp.py` import fails → `sdk_query()` catches this and runs without MCP (non-fatal) (discovered: 2026-02-25, component: eagle_tools_mcp)
- `feedback_store.py` DDB query uses `FEEDBACK#{tenant_id}` PK — in dev mode `DEV_TENANT_ID=dev-tenant` so the PK is `FEEDBACK#dev-tenant`, not `FEEDBACK#nci` (discovered: 2026-03-04, component: feedback_store)
- CloudWatch `filter_log_events` on `/eagle/telemetry` will raise `ResourceNotFoundException` if the log group hasn't been created yet — this is handled by the non-fatal pattern (returns `[]`) (discovered: 2026-03-04, component: main.py)

### tips
- Use `execute_tool()` for testing — it's synchronous and returns JSON strings
- The `search_far` tool has no AWS dependency — good for offline testing
- `intake_workflow` is stateless — workflow state is tracked in the response, not persisted
- Check `EAGLE_TOOLS` list for the exact parameter schemas Claude sees (legacy path)
- Check `TIER_TOOLS` for what SDK subagents can call (SDK path)
- Backend health check is at `/api/health` (not `/health`) — confirm ALB target group health path matches (discovered: 2026-02-25, verified from main.py line 1129)
- `main.py` version is 4.0.0 — reflects the merged multi-tenant + EAGLE architecture (discovered: 2026-02-16)
- `session_store.py` uses `boto3.resource("dynamodb")` (high-level) while `agentic_service.py` uses `boto3.client("dynamodb")` (low-level) — both access the same `eagle` table (discovered: 2026-02-16)
- Old infrastructure (Lightsail, old ECS clusters, old CF stacks) was cleaned up 2026-02-16 — ~$51-63/mo savings. See `.claude/specs/aws-resource-cleanup.md` for full inventory (discovered: 2026-02-16)
- Browser smoke test command at `.claude/commands/bowser/eagle-smoke-test.md` — tests login, home, chat, documents, workflows, admin, and backend health (discovered: 2026-02-17, component: bowser)
- Frontend auth-context.tsx auto-detects dev mode when `NEXT_PUBLIC_COGNITO_USER_POOL_ID` is empty — provides mock `dev-user` / `dev-tenant` without real Cognito (discovered: 2026-02-17, component: auth)
- Two separate MODEL env vars: `ANTHROPIC_MODEL` (agentic_service.py legacy) vs `EAGLE_SDK_MODEL` (sdk_agentic_service.py) — set both when changing models (discovered: 2026-02-25)
- `api_chat()` REST endpoint now uses `sdk_query()`, not the legacy `stream_chat()` — tool calls go through MCP layer, not directly through TOOL_DISPATCH (discovered: 2026-02-25)
- `feedback_store.list_feedback()` uses `ScanIndexForward=False` on the PK query — newest records come first without a secondary sort step (discovered: 2026-03-04, component: feedback_store)
- `_fetch_cloudwatch_logs_for_session` reads `EAGLE_TELEMETRY_LOG_GROUP` env var (default `/eagle/telemetry`), not `/eagle/app` — set this env var in CDK task definition if telemetry goes to a different log group (discovered: 2026-03-04, component: main.py)
