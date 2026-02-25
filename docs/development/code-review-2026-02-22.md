# EAGLE Code Review — February 2026

**Duration**: 30 minutes
**Audience**: Engineering team
**Stack**: Next.js + FastAPI + CDK + Claude SDK (Anthropic Bedrock)

---

## Agenda

| Segment | Topic | Time |
|---------|-------|------|
| 1 | System Overview | 5 min |
| 2 | Architecture Decisions | 8 min |
| 3 | Key Implementation Patterns | 10 min |
| 4 | Testing & Validation | 4 min |
| 5 | Open Discussion | 3 min |

---

## 1. System Overview (5 min)

**What EAGLE is**: A multi-tenant AI acquisition assistant for the NCI Office of Acquisitions. It guides CORs, program staff, and contracting officers through the federal acquisition lifecycle.

**Users**: Government acquisition professionals working with FAR, DFARS, and HHSAR.

**Core value**: AI-assisted generation of acquisition documents (SOW, IGCE, AP, market research) with compliance checking — streamed in real-time, tracked per-tenant.

### High-Level Stack

```
Browser (Next.js App Router)
  └─ SSE streaming ──► FastAPI (Python)
                           └─ Anthropic SDK ──► AWS Bedrock (Claude)
                           └─ DynamoDB (single-table multi-tenant)
                           └─ S3 (document storage)
                           └─ Cognito (JWT auth)

Infrastructure: AWS CDK → ECS Fargate + ALB
Agents & Skills: eagle-plugin/ (auto-discovered at runtime)
```

### Tenant Context in Every Request

Session ID carries the full tenant context:
```
{tenant_id}-{tier}-{user_id}-{session_id}
```

Subscription tier (`basic` / `advanced` / `premium`) gates both tool access and per-request cost budgets.

---

## 2. Architecture Decisions (8 min)

### 2a. DynamoDB Single-Table Design

All state lives in one table, differentiated by key prefixes:

| Prefix | Purpose |
|--------|---------|
| `SESSION#` | Session metadata |
| `MSG#` | Chat messages |
| `USAGE#` | Token metrics |
| `COST#` | Cost attribution |
| `SUB#` | Subscription state |

**Composite key structure**:
```
PK: SESSION#{tenant_id}#{user_id}#{session_id}
SK: {timestamp}#{message_id}
```

**Benefit**: Strong tenant isolation at the query layer — no cross-tenant reads possible.
**Trade-off**: Custom key decomposition logic required everywhere; no ORM convenience.
**Discussion point**: The in-memory cache (`_session_cache`) avoids repeated DynamoDB reads for hot sessions but becomes a stale-data risk in multi-instance deployments (no Redis or distributed invalidation).

---

### 2b. Two Parallel Orchestration Modes

There are currently two orchestration paths in the backend:

| Mode | File | Status |
|------|------|--------|
| Anthropic SDK (prompt injection) | `agentic_service.py` | **Active/default** |
| Claude Agent SDK (subagent delegation) | `sdk_agentic_service.py` | Implemented, not default |

**How the SDK mode works** (target architecture):
```
Supervisor Agent
  ├── Task("oa-intake", ...) → AgentDefinition with isolated context
  ├── Task("legal-counsel", ...) → AgentDefinition
  ├── Task("market-intelligence", ...) → AgentDefinition
  └── Task("document-generator", ...) → AgentDefinition
```

**Why this matters**: Each subagent gets a fresh context window. The current mode injects all skill prompts into a single system prompt, which bloats context and risks cross-skill interference.
**Discussion point**: What's the migration plan to make `sdk_agentic_service.py` the default? What's blocking it?

---

### 2c. Plugin Auto-Discovery

All agent and skill definitions live in `eagle-plugin/` — not in server code. The server auto-discovers them at startup via `eagle_skill_constants.py`:

```
eagle-plugin/
├── agents/
│   ├── supervisor/agent.md       ← YAML frontmatter + system prompt
│   ├── legal-counsel/agent.md
│   └── ...
└── skills/
    ├── oa-intake/SKILL.md
    ├── document-generator/SKILL.md
    └── ...
```

**Frontmatter format**:
```yaml
---
name: "oa-intake"
type: "skill"
triggers: ["intake", "start"]
tools: ["knowledge-retrieval", "compliance"]
---
[Markdown system prompt body]
```

**Benefit**: Adding or modifying a skill requires no server code changes — edit the markdown, restart.
**Note**: The frontmatter parser is a custom regex/state-machine implementation with no external YAML dependency. It works for this use case but doesn't support complex YAML (anchors, multi-line blocks).

---

### 2d. Cognito Auth + Tier Gating

The JWT from Cognito carries `custom:tenant_id` and `custom:tier`. Every request extracts these claims and enforces access controls:

```python
TIER_TOOLS = {
    "basic":    [],
    "advanced": ["Read", "Glob", "Grep"],
    "premium":  ["Read", "Glob", "Grep", "Bash"],
}

TIER_BUDGETS = {
    "basic":    $0.10 per request,
    "advanced": $0.25 per request,
    "premium":  $0.75 per request,
}
```

JWKS validation is cached in-memory for 1 hour to avoid repeated Cognito calls. Dev mode (`DEV_MODE=true`) bypasses validation entirely for local testing.

---

## 3. Key Implementation Patterns (10 min)

### 3a. SSE Streaming with Tool Tracing

Real-time streaming uses Server-Sent Events (SSE). The backend maps Bedrock Agent callbacks to a custom event protocol:

```
FastAPI /api/invoke (SSE)
  ├── on_text(delta)          → data: {"type":"TEXT","text":"..."}
  ├── on_tool_use(name,input) → data: {"type":"TOOL_USE","tool_name":"..."}
  ├── on_tool_result(name,r)  → data: {"type":"TOOL_RESULT","result":{...}}
  └── on_complete()           → data: {"type":"COMPLETE"}
```

The frontend's `use-agent-stream.ts` hook parses these events and:
- Appends text tokens to the message in real time
- Displays tool invocations in an expandable audit log
- Extracts document metadata from `TOOL_RESULT` events to update the document list UI without a separate API call

**Discussion point**: The event protocol is currently stringly-typed (JSON string comparison). A Zod schema on the frontend for stream event validation would catch protocol drift earlier.

---

### 3b. Cost Attribution at Inference Time

Costs are tracked per `(tenant_id, user_id, metric_type, timestamp)`:

```python
bedrock_pricing = {
    "anthropic.claude-3-haiku": {
        "input_tokens":  Decimal("0.00025"),  # $0.25 / 1K tokens
        "output_tokens": Decimal("0.00125"),  # $1.25 / 1K tokens
    }
}
```

`Decimal` is used (not `float`) to avoid floating-point rounding errors in financial calculations. Cost rollups aggregate across sessions and surface in the admin dashboard.

**Discussion point**: Pricing is hardcoded in `cost_attribution.py`. When Bedrock pricing changes (e.g., new models added), this needs a manual update. Consider pulling from a config file or SSM Parameter Store.

---

### 3c. Lambda Metadata Extraction

When a document is uploaded to S3, a CDK-provisioned Lambda fires automatically:

```typescript
// infrastructure/cdk-eagle/lib/storage-stack.ts
this.documentBucket.addEventNotification(
  s3.EventType.OBJECT_CREATED,
  new s3n.LambdaDestination(this.metadataExtractorFn)
);
```

The Lambda extracts: document type, topic, primary agent, creation context — and writes to DynamoDB. This enables filtering in the document browser without querying S3 directly.

**Discussion point**: The Lambda function code is in `lambda/metadata-extractor/`. Is it covered by the eval suite or only validated manually?

---

### 3d. Multi-Agent Hook Observability

The Claude Agent SDK exposes lifecycle hooks used for observability and control:

```python
# Hooks observed in sdk_agentic_service.py / tests
PreToolUse     → log/block before tool fires
PostToolUse    → capture tool output, cost attribution
Stop           → record session end
SubagentStart  → log which skill is delegated
SubagentStop   → capture subagent result, latency
```

**Benefit**: Full audit trail of every tool call and subagent invocation, emitted to CloudWatch. This is essential for compliance in a government acquisition context.

---

### 3e. Document Templates in Public Dir

The frontend serves acquisition document templates statically from `client/public/templates/`:

- SOW (Statement of Work)
- IGCE (Independent Government Cost Estimate)
- AP (Acquisition Plan)
- Market Research Report

These feed the `document-generator` skill, which populates them based on intake data and AI output. The `document_export.py` backend module handles PDF and Word rendering.

---

## 4. Testing & Validation (4 min)

### Validation Ladder

| Level | Command | Scope |
|-------|---------|-------|
| 1 — Lint | `just lint` | `ruff check` (Python) + `tsc --noEmit` (TypeScript) |
| 2 — Unit | `just test` | `pytest server/tests/` |
| 3 — E2E | `just smoke` | Playwright against localhost:3000 |
| 4 — Infra | `just cdk-synth` | CDK compiles without errors |
| 5 — Integration | `just dev` + `just smoke` | Full stack (docker compose) |
| 6 — Eval | CloudWatch post-deploy | Production agent quality metrics |

### Backend Eval Suite

`test_eagle_sdk_eval.py` — **28 tests** covering:

| Group | Tests | What it validates |
|-------|-------|-------------------|
| SDK Patterns | 1–6 | Session, resume, context, traces, costs, subagents |
| Skill Validation | 7–15 | OA intake, legal, market, tech, doc gen, supervisor chain |
| AWS Tool Integration | 16–20 | S3 ops, DynamoDB CRUD, CloudWatch logs |
| UC Workflow | 21–27 | Micro-purchase, option exercise, modification, close-out |
| SDK Architecture | 28 | Skill → subagent orchestration end-to-end |

**Run specific tests**: `just eval-quick 1,2,3` or `just eval-aws` (tests 16–20 only).

### Frontend E2E (Playwright)

Multi-browser coverage: Chromium, Firefox, WebKit + Pixel 5 (mobile).

Key test files:
- `intake.spec.ts` — home page + backend connectivity (9 tests)
- `admin-dashboard.spec.ts` — costs, analytics, users, skills pages
- `uc-intake.spec.ts` / `uc-document.spec.ts` / `uc-far-search.spec.ts` — end-to-end use case workflows

**Discussion point**: `playwright.config.ts` points to the production ALB URL as the default `baseURL`. This means `just smoke` without `BASE_URL` set hits production. Worth making `localhost:3000` the default.

---

## 5. Open Discussion (3 min)

### Items to Discuss

1. **SDK migration gate**: `sdk_agentic_service.py` is implemented but not the default. What's the acceptance criterion to flip the switch? Is there an eval test that validates subagent orchestration end-to-end?

2. **In-memory session cache**: Works fine for single-instance dev. In multi-instance Fargate (auto-scaling), sessions served by different tasks may see stale state. Is this acceptable at current scale, or should we add ElastiCache?

3. **Hardcoded Bedrock pricing**: `cost_attribution.py` has static price constants. Plan for keeping these up to date as new models are used?

4. **Lambda metadata extractor coverage**: Is the Lambda covered by automated tests, or is validation manual after deploy?

5. **Stream event protocol validation**: The SSE event types are compared as raw strings on the frontend. Adding Zod schemas for stream events would catch backend/frontend contract drift at parse time rather than at runtime.

6. **DEV_MODE bypass scope**: `DEV_MODE=true` skips Cognito JWT validation entirely. Is there risk of this leaking into staging/prod deployments? Consider restricting to a more explicit `NEXT_PUBLIC_` env var pattern or asserting it's off in CI.

---

## Reference: Key Files

| Concern | File |
|---------|------|
| FastAPI entry point | `server/app/main.py` |
| Active orchestration | `server/app/agentic_service.py` |
| Target orchestration | `server/app/sdk_agentic_service.py` |
| Session storage | `server/app/session_store.py` |
| Auth validation | `server/app/cognito_auth.py` |
| SSE streaming | `server/app/streaming_routes.py` + `stream_protocol.py` |
| Cost attribution | `server/app/cost_attribution.py` |
| Skill auto-discovery | `server/eagle_skill_constants.py` |
| CDK storage stack | `infrastructure/cdk-eagle/lib/storage-stack.ts` |
| CDK compute stack | `infrastructure/cdk-eagle/lib/compute-stack.ts` |
| SSE hook (frontend) | `client/hooks/use-agent-stream.ts` |
| Auth context | `client/contexts/auth-context.tsx` |
| Eval suite | `server/tests/test_eagle_sdk_eval.py` |
| Task runner | `Justfile` |
| Agent/skill defs | `eagle-plugin/agents/` + `eagle-plugin/skills/` |
