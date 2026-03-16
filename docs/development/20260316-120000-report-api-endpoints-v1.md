# EAGLE API Endpoints Report

**Generated:** 2026-03-16
**Version:** v1
**Source files:** `server/app/main.py`, `server/app/streaming_routes.py`, `server/app/routes/*.py`

---

## Chat

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| POST | `/api/chat` | Send message to EAGLE agent (REST, synchronous response with cost tracking) | Cognito JWT |
| POST | `/api/chat/stream` | Send message to EAGLE agent (SSE streaming response via Strands SDK) | Cognito JWT |
| WS | `/ws/chat` | Real-time streaming chat via WebSocket with full tool dispatch | Cognito JWT (via message) |

**Request format (REST + SSE):** `{ "message": string, "session_id"?: string, "package_id"?: string }`
**Response format (REST):** `{ "response": string, "session_id": string, "usage": {...}, "model": string, "tools_called": [...], "response_time_ms": int, "cost_usd": float }`
**SSE events:** `text`, `tool_use`, `tool_result`, `metadata`, `bedrock_trace`, `reasoning`, `complete`, `error`

---

## Health

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| GET | `/api/health` | Service health check (agents, tools, service status, knowledge base) | None |
| GET | `/api/health/ready` | Readiness probe (DynamoDB + Bedrock reachability check) | None |

**Note:** `/api/health` is registered in both `streaming_routes.py` and `misc.py`. The streaming router version takes precedence (included first in `main.py`).

---

## Sessions

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| GET | `/api/sessions` | List sessions for the current user (supports `?limit=` query param) | Cognito JWT |
| POST | `/api/sessions` | Create a new session (optional `?title=` query param) | Cognito JWT |
| GET | `/api/sessions/{session_id}` | Get session details | Cognito JWT |
| PATCH | `/api/sessions/{session_id}` | Update session title, status, or metadata | Cognito JWT |
| DELETE | `/api/sessions/{session_id}` | Delete a session | Cognito JWT |
| GET | `/api/sessions/{session_id}/messages` | Get messages for a session (supports `?limit=`) | Cognito JWT |
| DELETE | `/api/sessions/{session_id}/messages` | Clear all messages without deleting the session | Cognito JWT |
| GET | `/api/sessions/{session_id}/summary` | Lightweight session overview (title, count, tools used) | Cognito JWT |
| GET | `/api/sessions/{session_id}/documents` | Extract document tool_results from persisted audit_logs | Cognito JWT |
| GET | `/api/sessions/{session_id}/audit-logs` | Return all persisted SSE audit events for a session | Cognito JWT |

---

## Documents

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| GET | `/api/documents` | List documents in S3 for the current user | Cognito JWT |
| GET | `/api/documents/presign` | Generate a presigned URL for an S3 document (`?key=`) | Cognito JWT |
| GET | `/api/documents/{doc_key:path}` | Get document content from S3 (tenant-scoped access check) | Cognito JWT |
| PUT | `/api/documents/{doc_key:path}` | Update document content in S3 (versioned for package docs) | Cognito JWT |
| POST | `/api/documents/export` | Export content to DOCX, PDF, or Markdown | Cognito JWT |
| GET | `/api/documents/export/{session_id}` | Export an entire session conversation (supports `?format=`) | Cognito JWT |
| POST | `/api/documents/upload` | Upload a document to user's S3 workspace (PDF, Word, text, Markdown; 25 MB max) | Cognito JWT |

**Export request:** `{ "content": string, "title"?: string, "format"?: "docx" | "pdf" | "md" }`
**Update request:** `{ "content": string, "change_source"?: "user_edit" | "ai_edit" }`

---

## Packages (Acquisition Packages)

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| GET | `/api/packages` | List acquisition packages for current tenant (optional `?status=`) | Cognito JWT |
| POST | `/api/packages` | Create a new acquisition package (auto-determines FAR pathway) | Cognito JWT |
| GET | `/api/packages/{package_id}` | Get an acquisition package by ID | Cognito JWT |
| PUT | `/api/packages/{package_id}` | Update an acquisition package | Cognito JWT |
| GET | `/api/packages/{package_id}/checklist` | Get document checklist (required, completed, missing) | Cognito JWT |
| POST | `/api/packages/{package_id}/submit` | Submit package for review (drafting -> review) | Cognito JWT |
| POST | `/api/packages/{package_id}/approve` | Approve a package (review -> approved) | Cognito JWT |
| POST | `/api/packages/resolve-context` | Resolve/persist active package context for a session | Cognito JWT |

### Package Documents

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| GET | `/api/packages/{package_id}/documents` | List all documents for a package (latest version per type) | Cognito JWT |
| POST | `/api/packages/{package_id}/documents` | Save a generated document for a package | Cognito JWT |
| GET | `/api/packages/{package_id}/documents/{doc_type}` | Get a specific document (optional `?version=`) | Cognito JWT |
| GET | `/api/packages/{package_id}/documents/{doc_type}/history` | Return version history for a document type | Cognito JWT |
| POST | `/api/packages/{package_id}/documents/{doc_type}/finalize` | Mark a document version as final | Cognito JWT |
| GET | `/api/packages/{package_id}/documents/{doc_type}/versions/{version}/download-url` | Presigned download URL for a specific version | Cognito JWT |
| POST | `/api/packages/{package_id}/documents/{doc_type}/versions/{version}/promote-final` | Promote a specific version to final status | Cognito JWT |

### Approval Chains

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| GET | `/api/packages/{package_id}/approvals` | Get approval chain status for a package | Cognito JWT |
| POST | `/api/packages/{package_id}/approvals` | Create the FAR-driven approval chain | Cognito JWT |
| POST | `/api/packages/{package_id}/approvals/{step}/decision` | Record approval decision (approved/rejected/returned) | Cognito JWT |

---

## Skills (User-Created)

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| GET | `/api/skills` | List user-created skills (active bundled + tenant items) | Cognito JWT |
| POST | `/api/skills` | Create a new user skill (status=draft) | Cognito JWT |
| GET | `/api/skills/{skill_id}` | Get a skill by ID | Cognito JWT |
| PUT | `/api/skills/{skill_id}` | Update a draft skill | Cognito JWT |
| POST | `/api/skills/{skill_id}/submit` | Submit skill for review (draft -> review) | Cognito JWT |
| POST | `/api/skills/{skill_id}/publish` | Approve and activate a skill (review -> active) | Cognito JWT |
| DELETE | `/api/skills/{skill_id}` | Delete a skill (only draft or disabled) | Cognito JWT |

---

## Templates

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| GET | `/api/templates` | List available templates for current tenant (optional `?doc_type=`) | Cognito JWT |
| GET | `/api/templates/{doc_type}` | Get resolved template with 4-layer fallback | Cognito JWT |
| POST | `/api/templates/{doc_type}` | Create or update a user/tenant template override | Cognito JWT |
| DELETE | `/api/templates/{doc_type}` | Delete the current user's template override | Cognito JWT |

---

## Workspaces

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| GET | `/api/workspace` | List all workspaces for the current user | Cognito JWT |
| POST | `/api/workspace` | Create a new workspace | Cognito JWT |
| GET | `/api/workspace/active` | Get active workspace (auto-provisions Default if none exists) | Cognito JWT |
| GET | `/api/workspace/{workspace_id}` | Get a workspace by ID | Cognito JWT |
| PUT | `/api/workspace/{workspace_id}/activate` | Switch active workspace | Cognito JWT |
| DELETE | `/api/workspace/{workspace_id}` | Delete a non-default workspace and all its overrides | Cognito JWT |

### Workspace Overrides

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| GET | `/api/workspace/{workspace_id}/overrides` | List all overrides in a workspace (optional `?entity_type=`) | Cognito JWT |
| PUT | `/api/workspace/{workspace_id}/overrides/{entity_type}/{name}` | Set an override for agent, skill, template, or config | Cognito JWT |
| DELETE | `/api/workspace/{workspace_id}/overrides/{entity_type}/{name}` | Delete a specific override | Cognito JWT |
| DELETE | `/api/workspace/{workspace_id}/overrides` | Reset all overrides in a workspace | Cognito JWT |

---

## User

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| GET | `/api/user/me` | Get current user info from JWT claims | Cognito JWT |
| GET | `/api/user/usage` | Get usage summary for current user (optional `?days=`) | Cognito JWT |
| GET | `/api/user/preferences` | Get user preferences (merged with defaults) | Cognito JWT |
| PUT | `/api/user/preferences` | Update user preferences (partial update) | Cognito JWT |
| DELETE | `/api/user/preferences` | Reset all preferences to system defaults | Cognito JWT |

---

## Feedback

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| POST | `/api/feedback` | Submit user feedback with conversation snapshot and CloudWatch logs | Cognito JWT |
| GET | `/api/feedback` | List feedback for the current tenant (optional `?limit=`) | Cognito JWT |

---

## Tenant

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| GET | `/api/tenants/{tenant_id}/usage` | Get usage metrics for authenticated tenant | Cognito JWT (tenant match) |
| GET | `/api/tenants/{tenant_id}/costs` | Get cost attribution for tenant (optional `?days=`) | Cognito JWT (tenant match) |
| GET | `/api/tenants/{tenant_id}/users/{user_id}/costs` | Get cost attribution for a specific user | Cognito JWT (tenant + user match) |
| GET | `/api/tenants/{tenant_id}/subscription` | Get subscription tier info and usage limits | Cognito JWT (tenant match) |
| GET | `/api/tenants/{tenant_id}/sessions` | Get all sessions for authenticated tenant | Cognito JWT (tenant match) |
| GET | `/api/tenants/{tenant_id}/analytics` | Get enhanced analytics with trace data | Cognito JWT (tenant match) |

---

## Admin

### Dashboard & Analytics

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| GET | `/api/admin/dashboard` | Get admin dashboard statistics (optional `?days=`) | Cognito JWT |
| GET | `/api/admin/users` | Get top users by usage (optional `?days=`, `?limit=`) | Cognito JWT |
| GET | `/api/admin/users/{target_user_id}` | Get stats for a specific user | Cognito JWT |
| GET | `/api/admin/tools` | Get tool usage analytics | Cognito JWT |
| GET | `/api/admin/rate-limit` | Check current rate limit status | Cognito JWT |
| GET | `/api/admin/request-log` | Recent HTTP request history from ring buffer (optional `?limit=`, `?path_filter=`) | None |
| GET | `/api/admin/my-tenants` | Get tenants where current user has admin access | Admin JWT |

### Cost Reports

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| GET | `/api/admin/cost-report` | Generate comprehensive cost report (optional `?tenant_id=`, `?days=`) | Admin JWT |
| GET | `/api/admin/tier-costs/{tier}` | Get cost breakdown by subscription tier | Admin JWT |
| GET | `/api/admin/tenants/{tenant_id}/overall-cost` | Overall tenant cost breakdown | Admin JWT (tenant admin) |
| GET | `/api/admin/tenants/{tenant_id}/per-user-cost` | Per-user cost breakdown within tenant | Admin JWT (tenant admin) |
| GET | `/api/admin/tenants/{tenant_id}/service-wise-cost` | Service-wise consumption cost for tenant | Admin JWT (tenant admin) |
| GET | `/api/admin/tenants/{tenant_id}/users/{user_id}/service-cost` | Per-user service-wise cost | Admin JWT (tenant admin) |
| GET | `/api/admin/tenants/{tenant_id}/comprehensive-report` | All 4 cost breakdowns combined | Admin JWT (tenant admin) |

### Knowledge Base Reviews

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| GET | `/api/admin/kb-reviews` | List KB review records (optional `?status=`) | Cognito JWT |
| POST | `/api/admin/kb-review/{review_id}/approve` | Approve a KB review (applies diff to matrix.json) | Cognito JWT |
| POST | `/api/admin/kb-review/{review_id}/reject` | Reject a KB review (moves doc to rejected/) | Cognito JWT |

### Plugin Management

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| GET | `/api/admin/plugin/status` | Plugin manifest version, seed date, entity counts | Cognito JWT |
| POST | `/api/admin/plugin/sync` | Force reseed all PLUGIN# entities from bundled files | Cognito JWT |
| GET | `/api/admin/plugin/{entity_type}` | List all PLUGIN# items for a given entity type | Cognito JWT |
| GET | `/api/admin/plugin/{entity_type}/{name}` | Get a single PLUGIN# entity by type and name | Cognito JWT |
| PUT | `/api/admin/plugin/{entity_type}/{name}` | Update a PLUGIN# entity (writes audit entry) | Cognito JWT |

### Prompt Overrides

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| GET | `/api/admin/prompts` | List all tenant-level prompt overrides | Cognito JWT |
| PUT | `/api/admin/prompts/{agent_name}` | Set a tenant-level prompt override for an agent | Cognito JWT |
| DELETE | `/api/admin/prompts/{agent_name}` | Delete a tenant prompt override (reverts to canonical) | Cognito JWT |

### Runtime Config

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| GET | `/api/admin/config` | Return all CONFIG# runtime feature flags | Cognito JWT |
| PUT | `/api/admin/config/{key}` | Set a CONFIG# runtime value | Cognito JWT |
| DELETE | `/api/admin/config/{key}` | Delete a CONFIG# key (reverts to default) | Cognito JWT |

### Cache & Sync

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| POST | `/api/admin/reload` | Force-flush all in-process caches (plugin, prompt, config, template) | Cognito JWT |

### Test Runs

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| GET | `/api/admin/test-runs` | List recent test runs from DynamoDB (optional `?limit=`) | None |
| GET | `/api/admin/test-runs/{run_id}` | Get individual test results for a specific run | None |

---

## Traces (Langfuse)

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| GET | `/api/traces/story` | Build conversation story from Langfuse trace (`?session_id=` required) | None |
| GET | `/api/traces/sessions` | List recent Langfuse sessions with trace counts (optional `?limit=`) | None |

**Requires:** `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` environment variables.

---

## Telemetry

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| GET | `/api/telemetry` | Return recent telemetry entries with summary stats (optional `?limit=`) | None |

---

## Tools

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| GET | `/api/tools` | List available EAGLE tools with descriptions and parameter schemas | None |

---

## MCP (Weather)

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| GET | `/api/mcp/weather/tools` | Get available weather MCP tools for subscription tier | Cognito JWT |
| POST | `/api/mcp/weather/{tool_name}` | Execute a weather MCP tool (tier-gated) | Cognito JWT |

---

## Endpoint Count Summary

| Domain | Endpoints |
|--------|-----------|
| Chat | 3 (REST + SSE + WebSocket) |
| Health | 2 |
| Sessions | 10 |
| Documents | 7 |
| Packages | 18 (CRUD + documents + approvals) |
| Skills | 7 |
| Templates | 4 |
| Workspaces | 10 |
| User | 5 |
| Feedback | 2 |
| Tenant | 6 |
| Admin | 23 |
| Traces | 2 |
| Telemetry | 1 |
| Tools | 1 |
| MCP | 2 |
| **Total** | **103** |

---

## Authentication Patterns

1. **Cognito JWT** (`get_user_from_header`): Most endpoints. Extracts `UserContext` from `Authorization` header. In `DEV_MODE`, falls back to dev user.
2. **Admin JWT** (`get_admin_user`): Admin cost and tenant management endpoints. Requires Cognito group membership (`{tenant_id}-admins`).
3. **Tenant Admin** (`verify_tenant_admin`): Cost report endpoints scoped to a specific tenant. Validates the caller is admin for that tenant.
4. **Tenant Match** (`get_current_user`): Tenant endpoints verify `tenant_id` from path matches the JWT claim.
5. **None**: Health, tools, telemetry, traces, test-runs, and request-log endpoints are unauthenticated.
