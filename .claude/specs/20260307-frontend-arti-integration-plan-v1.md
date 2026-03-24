# Frontend Plan: Integrate ARTI (Research Optimizer) as EAGLE Frontend

> **Date**: 2026-03-07
> **Status**: Draft
> **Branch**: `feat/arti-frontend`

---

## Overview

Replace the current EAGLE Next.js frontend with NCI's **Research Optimizer** (ARTI) — a buildless SolidJS application — while keeping the EAGLE FastAPI + Strands SDK backend. ARTI becomes the presentation layer; EAGLE remains the AI orchestration engine.

### Why ARTI?

| ARTI Advantage | EAGLE Gap It Fills |
|---|---|
| Buildless SolidJS — zero build step, CDN imports | Next.js requires full build pipeline |
| IndexedDB + HNSW — privacy-first local storage | Only localStorage today |
| Mature chat UI (V1 + V2) with conversation management | Single-session chat, no history CRUD |
| Multi-model selector (Bedrock + Gemini) | Hardcoded to single Bedrock model |
| Admin dashboard with usage/budgets/analytics | Minimal admin pages |
| Built-in tools (search, textract, translate) | Tools only via Strands backend |
| PostgreSQL conversation persistence | DynamoDB sessions (no full conversation store) |
| OAuth/OIDC + session cookies | Cognito JWT (keep or adapt) |

---

## Architecture Decision: Integration Strategy

### Option A: ARTI as Full Frontend (Replace Next.js)

ARTI's Express server serves the SolidJS client and proxies API calls to EAGLE's FastAPI backend. ARTI's Gateway and CMS services run alongside or are replaced.

```
Browser → ARTI Express (443) → EAGLE FastAPI (8000)
                              → ARTI Gateway (3001) [optional, for multi-model]
                              → ARTI CMS (3002) [conversation CRUD]
                              → PostgreSQL
```

**Pros**: Full ARTI experience, conversation management, multi-model, admin UX
**Cons**: Two backend stacks (Express + FastAPI), dual infra

### Option B: ARTI Client Only (Swap SolidJS into Next.js)

Extract ARTI's SolidJS components and embed them in the existing Next.js shell via `@aspect-build/solidjs-in-react` or iframe isolation.

**Pros**: Keep Next.js deployment, gradual migration
**Cons**: Framework impedance mismatch, complex bundling, loses buildless advantage

### Option C: Hybrid — ARTI Frontend + Adapter Layer (Recommended)

Run ARTI's full stack (Express + SolidJS) as the frontend. Add a thin **adapter layer** in ARTI's Express server that maps ARTI API calls to EAGLE FastAPI endpoints. Phase out ARTI's Gateway in favor of EAGLE's Strands-based inference.

```
Browser (SolidJS)
  ↓
ARTI Express Server (port 443 / 3000)
  ├── /api/v1/session → local session store (PostgreSQL)
  ├── /api/v1/model   → EAGLE FastAPI /api/chat/stream (adapter)
  ├── /api/v1/tools/* → EAGLE FastAPI /api/tools/* (passthrough)
  ├── /api/v1/conversations/* → ARTI CMS (keep for now)
  └── static files    → SolidJS client
  ↓
EAGLE FastAPI (port 8000)
  ├── /api/chat/stream → Strands Agent SSE
  ├── /api/documents   → S3 document CRUD
  ├── /api/tools       → Tool registry
  └── /api/health      → Health check
```

**Pros**: Best of both, incremental, keeps ARTI UX + EAGLE AI
**Cons**: Adapter complexity, two servers in dev

---

## Recommended: Option C — Detailed Plan

### Phase 1: Foundation (Week 1)

#### 1.1 Repository Setup

```bash
# Add ARTI as a subtree or submodule in sm_eagle
git subtree add --prefix=arti-client \
  git@github.com:CBIIT/nci-webtools-ctri-arti.git greg-dev --squash
```

**New directory structure**:
```
sm_eagle/
├── arti-client/          ← ARTI repo (Express + SolidJS + Gateway + CMS)
│   ├── client/           ← SolidJS frontend
│   ├── server/           ← Express edge server
│   ├── gateway/          ← AI inference (replace with adapter)
│   ├── cms/              ← Conversation management (keep)
│   ├── database/         ← Drizzle ORM + PostgreSQL
│   └── docker-compose.yml
├── client/               ← Current Next.js (keep during migration)
├── server/               ← EAGLE FastAPI backend (keep)
└── infrastructure/       ← CDK stacks (update for ARTI)
```

#### 1.2 Docker Compose Integration

Create a unified `docker-compose.dev.yml`:

```yaml
services:
  eagle-backend:
    build: ./server
    ports: ["8000:8000"]
    environment:
      - AWS_PROFILE=eagle

  arti-server:
    build: ./arti-client
    ports: ["3000:443"]
    environment:
      - EAGLE_BACKEND_URL=http://eagle-backend:8000
      - DATABASE_URL=postgres://...
      - NODE_ENV=development
    depends_on: [eagle-backend, postgres]

  postgres:
    image: postgres:16
    ports: ["5432:5432"]
    volumes: [pgdata:/var/lib/postgresql/data]
```

---

### Phase 2: API Adapter Layer (Week 1–2)

The critical integration: map ARTI's `/api/v1/model` streaming protocol to EAGLE's `/api/chat/stream` SSE protocol.

#### 2.1 Streaming Protocol Translation

**ARTI sends** (POST `/api/v1/model`):
```json
{
  "model": "us.anthropic.claude-sonnet-4-6",
  "messages": [{"role": "user", "content": [{"text": "..."}]}],
  "system": "You are EAGLE...",
  "tools": [...],
  "stream": true
}
```

**EAGLE expects** (POST `/api/chat/stream`):
```json
{
  "message": "user query text",
  "session_id": "uuid"
}
```

**ARTI receives** (newline-delimited JSON):
```
{"type":"text_delta","delta":"Hello"}
{"type":"tool_use","id":"...","name":"search",...}
{"metadata":{"usage":{...}}}
```

**EAGLE returns** (SSE `data:` lines):
```
data: {"type":"text","agent_id":"supervisor","content":"Hello"}
data: {"type":"tool_use","agent_id":"specialist","tool_use":{"name":"search",...}}
data: {"type":"complete","metadata":{"usage":{...}}}
```

#### 2.2 Adapter Implementation

**New file**: `arti-client/server/services/clients/eagle-adapter.js`

```javascript
/**
 * Adapter that translates ARTI's model invocation requests
 * to EAGLE FastAPI's SSE streaming protocol.
 */
export function createEagleAdapter(eagleUrl) {
  return {
    async invoke({ messages, model, tools, stream, ...params }, res) {
      // Extract the latest user message
      const lastUserMsg = messages.findLast(m => m.role === 'user');
      const query = extractTextContent(lastUserMsg);

      // Build EAGLE request
      const eagleBody = {
        message: query,
        session_id: params.sessionId || crypto.randomUUID(),
      };

      // Stream from EAGLE
      const upstream = await fetch(`${eagleUrl}/api/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(eagleBody),
      });

      // Translate SSE → ARTI newline-delimited JSON
      const reader = upstream.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const event = JSON.parse(line.slice(6));
          const artiEvent = translateEvent(event);
          if (artiEvent) {
            res.write(JSON.stringify(artiEvent) + '\n');
          }
        }
      }

      res.end();
    }
  };
}

function translateEvent(eagleEvent) {
  switch (eagleEvent.type) {
    case 'text':
      return {
        type: 'text_delta',
        delta: eagleEvent.content,
        agent_id: eagleEvent.agent_id,
        agent_name: eagleEvent.agent_name,
      };
    case 'tool_use':
      return {
        type: 'tool_use',
        id: eagleEvent.tool_use?.tool_use_id,
        name: eagleEvent.tool_use?.name,
        input: eagleEvent.tool_use?.input,
      };
    case 'tool_result':
      return {
        type: 'tool_result',
        id: eagleEvent.tool_result?.tool_use_id,
        name: eagleEvent.tool_result?.name,
        content: eagleEvent.tool_result?.result,
      };
    case 'complete':
      return {
        type: 'metadata',
        metadata: {
          usage: eagleEvent.metadata?.usage,
          duration_ms: eagleEvent.metadata?.duration_ms,
        },
      };
    case 'error':
      return { type: 'error', message: eagleEvent.content };
    default:
      return null;
  }
}
```

#### 2.3 Route Wiring

**Modify**: `arti-client/server/services/clients/gateway.js`

```javascript
// Add EAGLE mode alongside monolith/HTTP modes
if (process.env.EAGLE_BACKEND_URL) {
  const { createEagleAdapter } = await import('./eagle-adapter.js');
  return createEagleAdapter(process.env.EAGLE_BACKEND_URL);
}
```

---

### Phase 3: Auth Bridge (Week 2)

Two options:

#### Option 3A: Keep ARTI's OAuth (Simpler)

ARTI already supports configurable OIDC. Point it at Cognito's OIDC endpoints:

```env
# .env for ARTI server
OAUTH_AUTHORIZATION_URL=https://eagle-auth.auth.us-east-1.amazoncognito.com/oauth2/authorize
OAUTH_TOKEN_URL=https://eagle-auth.auth.us-east-1.amazoncognito.com/oauth2/token
OAUTH_CLIENT_ID=<cognito-app-client-id>
OAUTH_CLIENT_SECRET=<cognito-app-client-secret>
OAUTH_CALLBACK_URL=https://localhost:3000/api/v1/login
OAUTH_SCOPE=openid email profile
```

Cognito supports standard OIDC, so ARTI's OAuth middleware works as-is. Map Cognito claims to ARTI's user model:

| Cognito Claim | ARTI Field |
|---|---|
| `email` | `email` |
| `given_name` | `firstName` |
| `family_name` | `lastName` |
| `custom:tenant_id` | (extend ARTI User model) |
| `custom:tier` | (extend ARTI User model) |

#### Option 3B: Forward Cognito JWT to EAGLE (More Integrated)

Pass Cognito JWT from ARTI's session to EAGLE FastAPI in the `Authorization` header. EAGLE already validates JWTs. This gives EAGLE tenant/tier context.

**Recommended**: Use **both** — ARTI manages session cookies for its own UX, AND forwards the Cognito JWT to EAGLE for backend auth.

---

### Phase 4: Feature Mapping (Week 2–3)

Map EAGLE-specific features into ARTI's UI.

#### 4.1 Slash Commands → ARTI Chat Config

ARTI's chat supports configurable tools and prompts via the CMS. Register EAGLE's slash commands as ARTI "tools":

```javascript
// Seed data for ARTI's tools table
const eagleTools = [
  { name: 'Document: SOW', type: 'prompt', description: 'Draft a Statement of Work', endpoint: null, customConfig: { prompt: '/document:sow' } },
  { name: 'Document: IGCE', type: 'prompt', description: 'Draft an IGCE', endpoint: null, customConfig: { prompt: '/document:igce' } },
  { name: 'Compliance: FAR', type: 'prompt', description: 'Search FAR clauses', endpoint: null, customConfig: { prompt: '/compliance:far' } },
  // ... all 18 slash commands
];
```

#### 4.2 Document Cards → ARTI Tool Rendering

ARTI already renders tool results via `chat-tools/` components. Add an EAGLE document card renderer:

**New file**: `arti-client/client/components/chat-tools/eagle-document-tool.js`

```javascript
// Renders create_document tool results as downloadable document cards
// Mirrors EAGLE's document-card.tsx behavior
export function EagleDocumentTool({ result }) {
  const { document_type, title, s3_key, status, word_count } = result;
  // ... render card with download link to /api/documents/{s3_key}
}
```

#### 4.3 Activity Panel → ARTI Sidebar

ARTI's chat has a sidebar for conversation history. Extend it with EAGLE's activity panel tabs:

| EAGLE Tab | ARTI Integration |
|---|---|
| Documents | New sidebar section showing generated docs |
| Activity | Map to ARTI's existing conversation metadata |
| Agent Logs | New component rendering multi-agent stream events |

#### 4.4 Admin Pages

ARTI has admin pages for users and usage. Extend with EAGLE-specific pages:

| EAGLE Admin Page | Integration Approach |
|---|---|
| `/admin/agents` | Use ARTI's existing agent management |
| `/admin/skills` | New page, proxy to EAGLE `/api/admin/plugin/skills` |
| `/admin/templates` | New page, proxy to EAGLE `/api/templates` |
| `/admin/tests` | New page, proxy to EAGLE `/api/admin/traces` |
| `/admin/workspaces` | New page, proxy to EAGLE `/api/workspace` |
| `/admin/subscription` | New page or extend ARTI's usage page |

---

### Phase 5: Tool Integration (Week 3)

#### 5.1 ARTI Tools That Map to EAGLE

| ARTI Tool | EAGLE Equivalent | Action |
|---|---|---|
| Web Search (Brave) | `web_search` (Strands tool) | Route through EAGLE |
| Textract | `document_ingest` (Strands tool) | Route through EAGLE |
| Translate | Keep ARTI's (AWS Translate direct) | No change |
| Code execution | `code` (client-side tool) | Already in EAGLE |
| Editor | `editor` (client-side tool) | Already in EAGLE |

#### 5.2 EAGLE Tools New to ARTI

| EAGLE Tool | ARTI Component Needed |
|---|---|
| `create_document` | `eagle-document-tool.js` (new) |
| `search_far_dfars` | `search-tool.js` (reuse existing) |
| `intake_form` | Custom form component (new) |
| `think` | `reasoning-tool.js` (reuse existing) |

---

### Phase 6: Infrastructure (Week 3–4)

#### 6.1 CDK Changes

Add ARTI as a second ECS service alongside EAGLE backend:

```typescript
// infrastructure/cdk-eagle/lib/compute-stack.ts — new service
const artiService = new ecs.FargateService(this, 'ArtiService', {
  cluster,
  taskDefinition: artiTask, // Express + CMS + PostgreSQL sidecar
  desiredCount: 1,
});

// ALB routing
listener.addTargets('ArtiTarget', {
  port: 80,
  targets: [artiService],
  conditions: [elbv2.ListenerCondition.pathPatterns(['/*'])],
  priority: 100,
});

// EAGLE backend only on /api/chat/*, /api/documents/*, etc.
listener.addTargets('EagleTarget', {
  port: 8000,
  targets: [eagleService],
  conditions: [elbv2.ListenerCondition.pathPatterns(['/api/chat/*', '/api/documents/*'])],
  priority: 10,
});
```

#### 6.2 Docker

ARTI already has a Dockerfile. Add it to EAGLE's docker-compose:

```yaml
# docker-compose.yml (dev)
services:
  arti:
    build: ./arti-client
    ports: ["3000:80"]
    env_file: ./arti-client/.env
    depends_on: [eagle-backend, postgres]

  eagle-backend:
    build: ./server
    ports: ["8000:8000"]
```

---

## Migration Path

| Phase | Duration | Deliverable |
|---|---|---|
| 1. Foundation | Week 1 | ARTI subtree added, docker-compose running both |
| 2. Adapter | Week 1–2 | ARTI chat sends queries to EAGLE, streams responses |
| 3. Auth | Week 2 | Cognito OIDC working through ARTI's OAuth |
| 4. Features | Week 2–3 | Slash commands, doc cards, activity panel |
| 5. Tools | Week 3 | EAGLE tools rendering in ARTI chat |
| 6. Infra | Week 3–4 | CDK stacks updated, single deploy |
| 7. Cutover | Week 4 | DNS switch, Next.js deprecated |

---

## Files Modified / Created

| File | Change |
|---|---|
| `arti-client/` | New subtree (ARTI repo) |
| `arti-client/server/services/clients/eagle-adapter.js` | **New** — streaming protocol translator |
| `arti-client/server/services/clients/gateway.js` | Modify — add EAGLE mode |
| `arti-client/server/.env` | Modify — add `EAGLE_BACKEND_URL`, Cognito OIDC vars |
| `arti-client/client/components/chat-tools/eagle-document-tool.js` | **New** — document card renderer |
| `arti-client/client/pages/tools/chat-v2/hooks.js` | Modify — add agent event types |
| `arti-client/database/data/tools.csv` | Modify — add EAGLE slash commands |
| `docker-compose.dev.yml` | **New** — unified dev environment |
| `infrastructure/cdk-eagle/lib/compute-stack.ts` | Modify — add ARTI ECS service |
| `.github/workflows/deploy.yml` | Modify — build + push ARTI container |

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| SolidJS ↔ EAGLE SSE protocol mismatch | Broken streaming | Adapter layer handles translation; test with both protocols |
| Two databases (PostgreSQL + DynamoDB) | Data inconsistency | ARTI owns conversations, EAGLE owns sessions/documents — clear ownership |
| Dual auth (session cookies + JWT) | Security gaps | ARTI validates session, forwards JWT to EAGLE for backend auth |
| ARTI's buildless approach + EAGLE's CDK | Deployment complexity | Separate Docker images, ALB path routing |
| Losing Next.js API routes | Feature regression | Map each Next.js route to ARTI Express equivalent |

---

## Verification

1. **Chat works**: Send message in ARTI → response streams from EAGLE Strands agent
2. **Auth works**: Login via Cognito OIDC → session cookie set → JWT forwarded
3. **Documents work**: `/document:sow` → document card renders → download works
4. **Tools work**: Tool use events render inline in ARTI chat
5. **Admin works**: ARTI admin pages show EAGLE data
6. **Dev setup**: `docker compose up` starts everything

---

## Open Questions

1. **Keep ARTI's CMS?** — ARTI's CMS provides full conversation CRUD with PostgreSQL. EAGLE uses DynamoDB for sessions. Keep both or migrate?
2. **Multi-model?** — ARTI supports model selection (Claude, Gemini, Llama). Should EAGLE's Strands backend support model switching, or lock to the supervisor's model?
3. **ConsentCrafter / Translator** — These are ARTI-specific tools. Include in EAGLE or strip?
4. **IndexedDB** — ARTI stores conversations client-side for privacy. Keep this for EAGLE's acquisition data?
5. **Gateway service** — Replace entirely with EAGLE adapter, or keep for non-EAGLE model calls?
