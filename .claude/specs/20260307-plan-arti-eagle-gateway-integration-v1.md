# Implementation Plan: EAGLE Tools in ARTI Gateway

> **Date**: 2026-03-07
> **Status**: Ready for handoff to `nci-webtools-ctri-arti` repo
> **Target branch**: `feat/eagle-gateway` in ARTI repo
> **Source content**: `sm_eagle/eagle-plugin/` + `sm_eagle/server/app/agentic_service.py`

---

## Summary

Wire EAGLE's acquisition-specialist capabilities (system prompt, 10 tools, skill content) into ARTI's existing Gateway + Chat V2 architecture. **No new frameworks.** EAGLE content loads as a CMS agent with server-side tool handlers. ARTI's existing client-side agentic loop (`runAgent` in `hooks.js`) orchestrates tool dispatch.

---

## Architecture

```
ARTI Chat V2 (SolidJS)
  │
  │  POST /api/v1/model  { model, messages, system, tools, stream: true }
  │
  ├── ARTI Server (Express)
  │     └── /model route → gateway.invoke()
  │
  ├── ARTI Gateway (inference.js)
  │     └── bedrock.converseStream() with EAGLE system prompt + tool specs
  │
  │  ← NDJSON stream (text_delta, tool_use, tool_result, metadata)
  │
  ├── Client agentic loop (hooks.js runAgent)
  │     └── stopReason === "tool_use" → execute tool
  │           ├── Client tools: search, code, editor, think → run in browser
  │           └── EAGLE tools: s3_document_ops, create_document, etc.
  │                 → POST /api/v1/tools/eagle/{toolName} (new server route)
  │                 → server calls EAGLE FastAPI or executes locally
  │
  └── Re-query model with tool results → loop until end_turn
```

### Key Design Decision

ARTI's agentic loop runs **on the client** (`hooks.js` → `runAgent`). EAGLE's tools need **server-side execution** (AWS S3, DynamoDB, Bedrock). So EAGLE tools are registered as client tool definitions that POST to a new server endpoint for execution.

---

## Phase 1: EAGLE Agent in CMS (Seed Data)

Register EAGLE as an agent in ARTI's database so users can select it from the agent/model picker.

### 1.1 Agent Seed Record

**File**: `database/data/agents.csv` — add row:

| id | userID | modelID | name | description | promptID |
|----|--------|---------|------|-------------|----------|
| 10 | 1 | (claude-sonnet-4-6 ID) | EAGLE Acquisition Assistant | NCI acquisition intake, document generation, FAR/DFARS compliance | (new prompt ID) |

### 1.2 Prompt Seed Record

**File**: `database/data/prompts.csv` — add row with the EAGLE supervisor system prompt.

**Content source**: Concatenate from two sources:
1. `sm_eagle/eagle-plugin/agents/supervisor/agent.md` (body after frontmatter)
2. `sm_eagle/server/app/agentic_service.py` lines 31–121 (the SYSTEM_PROMPT constant with intake workflow, thresholds, specialist lenses)

The combined prompt (~3KB) becomes the `content` field of the prompt record.

### 1.3 Tool Seed Records

**File**: `database/data/tools.csv` — add 10 rows:

| name | type | description | endpoint | transportType |
|------|------|-------------|----------|---------------|
| s3_document_ops | server | Read/write/list documents in S3 | /api/v1/tools/eagle/s3_document_ops | http |
| dynamodb_intake | server | CRUD intake records | /api/v1/tools/eagle/dynamodb_intake | http |
| search_far | server | Search FAR/DFARS regulations | /api/v1/tools/eagle/search_far | http |
| create_document | server | Generate acquisition documents (SOW, IGCE, AP, J&A, etc.) | /api/v1/tools/eagle/create_document | http |
| get_intake_status | server | Show document completion status | /api/v1/tools/eagle/get_intake_status | http |
| intake_workflow | server | Manage 4-stage intake workflow | /api/v1/tools/eagle/intake_workflow | http |
| query_compliance_matrix | server | Query NCI/NIH compliance decision tree | /api/v1/tools/eagle/query_compliance_matrix | http |
| cloudwatch_logs | server | Search application logs | /api/v1/tools/eagle/cloudwatch_logs | http |
| knowledge_search | server | Search knowledge base by topic/type | /api/v1/tools/eagle/knowledge_search | http |
| knowledge_fetch | server | Fetch document content from S3 | /api/v1/tools/eagle/knowledge_fetch | http |

### 1.4 Agent-Tool Links

**File**: `database/data/agent-tools.csv` — link all 10 tools to agent ID 10.

---

## Phase 2: Server-Side Tool Execution Route

### 2.1 New Route: `/api/v1/tools/eagle/:toolName`

**New file**: `server/services/routes/eagle-tools.js`

```javascript
import { routeHandler, createHttpError } from "../../shared/utils.js";
import { requireRole } from "../middleware.js";

// Option A: Proxy to EAGLE FastAPI backend
const EAGLE_BACKEND_URL = process.env.EAGLE_BACKEND_URL || "http://localhost:8000";

// Option B: Direct AWS SDK calls (no EAGLE backend dependency)
import { S3Client, GetObjectCommand, PutObjectCommand, ListObjectsV2Command } from "@aws-sdk/client-s3";
import { DynamoDBClient } from "@aws-sdk/client-dynamodb";

export default function eagleToolsRouter(api) {
  // Proxy mode: forward tool calls to EAGLE FastAPI
  api.post("/tools/eagle/:toolName", requireRole(), async (req, res, next) => {
    const { toolName } = req.params;
    const { input, sessionId } = req.body;
    const user = req.session.user;

    try {
      const response = await fetch(`${EAGLE_BACKEND_URL}/api/tools/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tool_name: toolName,
          tool_input: input,
          session_id: sessionId || `${user.id}-basic-${user.id}-${crypto.randomUUID()}`,
        }),
      });

      if (!response.ok) {
        const error = await response.text();
        return res.status(response.status).json({ error });
      }

      const result = await response.json();
      res.json(result);
    } catch (error) {
      // Fallback: return error as tool result (don't break the agentic loop)
      res.json({
        error: `Tool ${toolName} unavailable: ${error.message}`,
        fallback: true,
      });
    }
  });
}
```

### 2.2 Mount Route

**File**: `server/services/api.js` — add:

```javascript
import eagleToolsRouter from "./routes/eagle-tools.js";
// ...
eagleToolsRouter(api);
```

### 2.3 EAGLE Backend Endpoint (if needed)

If EAGLE FastAPI doesn't already expose `/api/tools/execute`, add a thin endpoint:

**File**: `sm_eagle/server/app/main.py` — add route:

```python
@app.post("/api/tools/execute")
async def execute_tool_endpoint(request: Request):
    body = await request.json()
    from .agentic_service import execute_tool
    result = execute_tool(
        tool_name=body["tool_name"],
        tool_input=body["tool_input"],
        session_id=body.get("session_id"),
    )
    return JSONResponse(content=json.loads(result))
```

---

## Phase 3: Client-Side Tool Wiring

### 3.1 EAGLE Tool Definitions

**New file**: `client/pages/tools/chat-v2/eagle-tools.js`

```javascript
/**
 * EAGLE acquisition tools for ARTI Chat V2.
 *
 * Each tool defines a toolSpec (Anthropic format) and an fn that
 * POSTs to the server-side execution endpoint.
 */

async function callEagleTool(name, input) {
  const response = await fetch(`/api/v1/tools/eagle/${name}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ input }),
  });
  return response.json();
}

export const EAGLE_TOOLS = [
  {
    fn: (input) => callEagleTool("s3_document_ops", input),
    toolSpec: {
      name: "s3_document_ops",
      description: "Read, write, or list documents in the tenant's S3 document store.",
      inputSchema: {
        json: {
          type: "object",
          properties: {
            operation: { type: "string", enum: ["read", "write", "list"] },
            key: { type: "string", description: "S3 object key (for read/write)" },
            content: { type: "string", description: "Content to write (for write)" },
            prefix: { type: "string", description: "Prefix filter (for list)" },
          },
          required: ["operation"],
        },
      },
    },
  },
  {
    fn: (input) => callEagleTool("create_document", input),
    toolSpec: {
      name: "create_document",
      description: "Generate acquisition documents: SOW, IGCE, Market Research, J&A, Acquisition Plan, Evaluation Criteria, Security Checklist, Section 508, COR Certification, Contract Type Justification.",
      inputSchema: {
        json: {
          type: "object",
          properties: {
            document_type: {
              type: "string",
              enum: ["sow", "igce", "market_research", "justification", "acquisition_plan",
                     "eval_criteria", "security_checklist", "section_508",
                     "cor_certification", "contract_type_justification"],
            },
            title: { type: "string" },
            context: { type: "string", description: "Acquisition context and requirements" },
          },
          required: ["document_type"],
        },
      },
    },
  },
  {
    fn: (input) => callEagleTool("search_far", input),
    toolSpec: {
      name: "search_far",
      description: "Search Federal Acquisition Regulation (FAR), DFARS, and HHSAR clauses by topic, part number, or keyword.",
      inputSchema: {
        json: {
          type: "object",
          properties: {
            query: { type: "string", description: "Search query" },
            regulation: { type: "string", enum: ["far", "dfars", "hhsar"], description: "Which regulation to search" },
            part: { type: "string", description: "Optional part number filter" },
          },
          required: ["query"],
        },
      },
    },
  },
  {
    fn: (input) => callEagleTool("intake_workflow", input),
    toolSpec: {
      name: "intake_workflow",
      description: "Manage the 4-stage acquisition intake workflow: start, advance, status, complete, or reset.",
      inputSchema: {
        json: {
          type: "object",
          properties: {
            action: { type: "string", enum: ["start", "advance", "status", "complete", "reset"] },
            data: { type: "object", description: "Workflow data to save" },
          },
          required: ["action"],
        },
      },
    },
  },
  {
    fn: (input) => callEagleTool("dynamodb_intake", input),
    toolSpec: {
      name: "dynamodb_intake",
      description: "Create, read, update, or list acquisition intake records.",
      inputSchema: {
        json: {
          type: "object",
          properties: {
            operation: { type: "string", enum: ["create", "read", "update", "list"] },
            item_id: { type: "string" },
            data: { type: "object" },
          },
          required: ["operation"],
        },
      },
    },
  },
  {
    fn: (input) => callEagleTool("get_intake_status", input),
    toolSpec: {
      name: "get_intake_status",
      description: "Show the current intake status including completed documents and next steps.",
      inputSchema: {
        json: { type: "object", properties: {} },
      },
    },
  },
  {
    fn: (input) => callEagleTool("query_compliance_matrix", input),
    toolSpec: {
      name: "query_compliance_matrix",
      description: "Query the NCI/NIH compliance requirements decision tree for contract types and thresholds.",
      inputSchema: {
        json: {
          type: "object",
          properties: {
            query: { type: "string", description: "Compliance question" },
            contract_type: { type: "string" },
            threshold: { type: "number" },
          },
          required: ["query"],
        },
      },
    },
  },
  {
    fn: (input) => callEagleTool("knowledge_search", input),
    toolSpec: {
      name: "knowledge_search",
      description: "Search the EAGLE knowledge base by topic, document type, or keywords.",
      inputSchema: {
        json: {
          type: "object",
          properties: {
            topic: { type: "string" },
            document_type: { type: "string", enum: ["regulation", "guidance", "policy", "template", "memo", "checklist", "reference"] },
            keywords: { type: "array", items: { type: "string" } },
            limit: { type: "integer", default: 10 },
          },
        },
      },
    },
  },
  {
    fn: (input) => callEagleTool("knowledge_fetch", input),
    toolSpec: {
      name: "knowledge_fetch",
      description: "Fetch full document content from the knowledge base by S3 key or document ID.",
      inputSchema: {
        json: {
          type: "object",
          properties: {
            s3_key: { type: "string" },
            document_id: { type: "string" },
          },
        },
      },
    },
  },
  {
    fn: (input) => callEagleTool("cloudwatch_logs", input),
    toolSpec: {
      name: "cloudwatch_logs",
      description: "Search application logs by user, session, or time range.",
      inputSchema: {
        json: {
          type: "object",
          properties: {
            action: { type: "string", enum: ["search", "recent", "get_stream"] },
            query: { type: "string" },
            limit: { type: "integer", default: 20 },
          },
          required: ["action"],
        },
      },
    },
  },
];
```

### 3.2 Merge Tools in hooks.js

**File**: `client/pages/tools/chat-v2/hooks.js` — modify TOOLS export:

```javascript
import { EAGLE_TOOLS } from "./eagle-tools.js";

// Existing ARTI tools
export const TOOLS = [
  // ... existing: search, browse, code, editor, think, data, docxTemplate
].filter((t) => t.toolSpec);

// Combined tools (used when EAGLE agent is selected)
export const ALL_TOOLS = [...TOOLS, ...EAGLE_TOOLS];
```

### 3.3 Agent-Aware Tool Selection

**File**: `client/pages/tools/chat-v2/hooks.js` — in `sendMessage()`:

```javascript
// When the selected agent has EAGLE tools linked, use ALL_TOOLS
const agentTools = record.tools?.length
  ? ALL_TOOLS.filter((t) => record.tools.includes(t.toolSpec.name))
  : tools;  // Default ARTI tools for non-EAGLE agents
```

This way, when the user selects the "EAGLE Acquisition Assistant" agent from the CMS, all 10 EAGLE tools are available. Other agents get only ARTI's default tools.

---

## Phase 4: Skill Content as Memory Files

ARTI's Chat V2 has a **memory system** that injects localStorage files into the system prompt via `{{memory}}` template. Use this to load EAGLE skill content on demand.

### 4.1 Preload Skill Content

**New file**: `client/pages/tools/chat-v2/eagle-skills.js`

```javascript
/**
 * Preload EAGLE skill markdown into localStorage
 * so the {{memory}} template injects them into the system prompt.
 */

const EAGLE_SKILLS = {
  "eagle-oa-intake": "/eagle-plugin/skills/oa-intake/SKILL.md",
  "eagle-document-generator": "/eagle-plugin/skills/document-generator/SKILL.md",
  "eagle-compliance": "/eagle-plugin/skills/compliance/SKILL.md",
  "eagle-knowledge-retrieval": "/eagle-plugin/skills/knowledge-retrieval/SKILL.md",
  "eagle-tech-review": "/eagle-plugin/skills/tech-review/SKILL.md",
};

export async function loadEagleSkills(baseUrl = "") {
  for (const [key, path] of Object.entries(EAGLE_SKILLS)) {
    try {
      const response = await fetch(`${baseUrl}${path}`);
      if (response.ok) {
        const content = await response.text();
        // Strip YAML frontmatter
        const body = content.replace(/^---[\s\S]*?---\n/, "");
        localStorage.setItem("file:" + key, body);
      }
    } catch (e) {
      console.warn(`Failed to load skill ${key}:`, e);
    }
  }
}
```

### 4.2 Serve Skill Files

**File**: `server/services/api.js` — add static mount:

```javascript
// Serve EAGLE plugin content (read-only)
api.use("/eagle-plugin", express.static(
  path.resolve(process.env.EAGLE_PLUGIN_PATH || "../sm_eagle/eagle-plugin"),
  { maxAge: "1h" }
));
```

### 4.3 Load on Agent Selection

In the Chat V2 page, when EAGLE agent is selected, call `loadEagleSkills()`:

```javascript
// In ChatApp component, watch for agent change
createEffect(() => {
  if (agent.name === "EAGLE Acquisition Assistant") {
    loadEagleSkills();
  }
});
```

---

## Phase 5: Environment & Config

### 5.1 New Environment Variables

**File**: `server/.env`

```env
# EAGLE backend (for tool execution proxy)
EAGLE_BACKEND_URL=http://localhost:8000

# EAGLE plugin content path (for serving skill files)
EAGLE_PLUGIN_PATH=../sm_eagle/eagle-plugin
```

### 5.2 Docker Compose (Dev)

**File**: `docker-compose.yml` — add EAGLE backend:

```yaml
services:
  server:
    environment:
      - EAGLE_BACKEND_URL=http://eagle-backend:8000
      - EAGLE_PLUGIN_PATH=/app/eagle-plugin
    volumes:
      - ../sm_eagle/eagle-plugin:/app/eagle-plugin:ro

  eagle-backend:
    build: ../sm_eagle/server
    ports: ["8000:8000"]
    environment:
      - AWS_PROFILE=eagle
```

---

## Files Summary

### ARTI Repo Changes

| File | Action | Description |
|------|--------|-------------|
| `database/data/agents.csv` | Modify | Add EAGLE agent record |
| `database/data/prompts.csv` | Modify | Add EAGLE supervisor prompt |
| `database/data/tools.csv` | Modify | Add 10 EAGLE tool records |
| `database/data/agent-tools.csv` | Modify | Link tools to EAGLE agent |
| `server/services/routes/eagle-tools.js` | **New** | Server-side tool execution endpoint |
| `server/services/api.js` | Modify | Mount eagle-tools route + static skill files |
| `client/pages/tools/chat-v2/eagle-tools.js` | **New** | 10 EAGLE tool definitions (client-side) |
| `client/pages/tools/chat-v2/eagle-skills.js` | **New** | Skill content preloader |
| `client/pages/tools/chat-v2/hooks.js` | Modify | Import EAGLE_TOOLS, agent-aware tool selection |
| `server/.env` | Modify | Add EAGLE_BACKEND_URL, EAGLE_PLUGIN_PATH |
| `docker-compose.yml` | Modify | Add eagle-backend service |

### EAGLE Repo Changes

| File | Action | Description |
|------|--------|-------------|
| `server/app/main.py` | Modify | Add `/api/tools/execute` endpoint (if not exists) |

---

## Test Plan

### Test 1: Basic Chat (No Tools)
1. Start ARTI + EAGLE backend
2. Select "EAGLE Acquisition Assistant" agent in Chat V2
3. Ask: "What can you help me with?"
4. **Expected**: Supervisor prompt responds with acquisition capabilities
5. **Validates**: System prompt loaded correctly

### Test 2: Tool Execution
1. Ask: "Search FAR clauses about simplified acquisition threshold"
2. **Expected**: Model calls `search_far` tool → client posts to `/api/v1/tools/eagle/search_far` → server proxies to EAGLE backend → result rendered
3. **Validates**: Full tool loop (client → server → EAGLE → back)

### Test 3: Document Generation
1. Ask: "Generate a Statement of Work for cloud hosting services"
2. **Expected**: Model calls `create_document` with `document_type: "sow"` → document generated → result shown in chat
3. **Validates**: create_document tool, S3 integration

### Test 4: Multi-Turn Intake
1. Ask: "I need to purchase laboratory equipment worth $50,000"
2. Follow the intake workflow prompts
3. **Expected**: Model calls `intake_workflow` with `action: "start"`, then asks clarifying questions, advances stages
4. **Validates**: Stateful workflow, DynamoDB persistence

### Test 5: Skill Content Loading
1. Select EAGLE agent
2. Check localStorage for `file:eagle-oa-intake` key
3. Ask a question that triggers the oa-intake skill
4. **Expected**: Skill content appears in system prompt via `{{memory}}` template
5. **Validates**: Skill loading, memory injection

### Test 6: Non-EAGLE Agent (No Regression)
1. Switch to default ARTI agent
2. Ask a general question
3. **Expected**: Normal ARTI behavior, no EAGLE tools shown
4. **Validates**: Agent-aware tool selection

---

## Scaling Notes

- ARTI Gateway uses direct `bedrock.converseStream()` — **no subprocess, no SDK overhead**
- Each user request = one HTTP request to Bedrock (stateless)
- Tool execution proxies to EAGLE FastAPI (can be load-balanced)
- Concurrent users limited only by Bedrock quotas and EAGLE backend capacity
- Skill content cached in localStorage (loaded once per session)

---

## Future Enhancements

1. **Direct AWS SDK tools**: Replace EAGLE FastAPI proxy with direct S3/DynamoDB calls in `eagle-tools.js` server route (removes EAGLE backend dependency)
2. **Document download UI**: Add document card component for `create_document` results (link to S3 presigned URL)
3. **Intake progress panel**: Sidebar showing workflow stage and completion %
4. **API Skills integration**: Use Anthropic's `container.skills` for document generation (docx/xlsx/pdf) when available on Bedrock
