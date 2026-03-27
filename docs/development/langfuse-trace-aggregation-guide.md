# EAGLE Langfuse Trace Aggregation Guide

How EAGLE traces are structured in Langfuse, what makes a properly formatted trace, and how to fix improperly formatted ones.

---

## Proper Trace (Strands OTEL — `6486d34e`)

**Source:** Strands Agents SDK's built-in OpenTelemetry instrumentation, exported to Langfuse via OTEL endpoint.

### Trace-level fields

| Field | Value | How set |
|-------|-------|---------|
| `name` | `invoke_agent Strands Agents` | Auto by Strands OTEL |
| `userId` | `dev-user` | `langfuse.user.id` OTEL attribute |
| `sessionId` | `55d01b49-...` | `langfuse.session.id` OTEL attribute |
| `version` | `1.28.0` | Strands SDK version |
| `input` | Bedrock message format (`[{"role":"user","content":"[{\"text\":...}]"}]`) | Auto |
| `output` | `{"message":"...","finish_reason":"end_turn"}` | Auto |
| `metadata.attributes` | Rich EAGLE context: `eagle.tenant_id`, `eagle.user_id`, `eagle.tier`, `eagle.session_id`, `eagle.phase`, `system_prompt`, token usage | Set by `strands_agentic_service.py` OTEL resource attributes |

### Observation hierarchy (27 observations, 4 types)

```
AGENT "invoke_agent Strands Agents"     <- root, 1 per trace
  +-- SPAN "execute_event_loop_cycle"   <- 1 per supervisor loop iteration (9 cycles)
       |-- GENERATION "chat"            <- Bedrock ConverseStream call (1 per cycle)
       +-- TOOL "query_contract_matrix" <- tool execution (0-1 per cycle)
```

### Key characteristics

- **Hierarchical** -- parent/child relationships via `parentObservationId`
- **Cost tracking works** -- `costDetails` populated with input/output costs, `totalCost: $0.41`
- **Token counts accurate** -- per-generation `usageDetails` with input/output/total + cache tokens
- **Model resolved** -- `internalModelId` populated, pricing tier linked
- **Tool calls visible** -- 8 TOOL observations (subagent delegations, data lookups, state updates)
- **Multi-turn agent loop** -- 9 event loop cycles visible as sequential SPANs under the root AGENT

---

## Improper Trace 1 (Research Optimizer — `f411a89b`)

**Source:** Custom SDK (not Strands OTEL). Uses Langfuse Python SDK directly.

| Issue | Detail |
|-------|--------|
| **No hierarchy** | 2 GENERATION observations, both with `parentObservationId: null` -- flat, no nesting |
| **No AGENT root** | Missing root AGENT span that wraps the full request |
| **No SPAN observations** | No event loop cycles tracked |
| **No TOOL observations** | Tool calls (load_skill, etc.) not instrumented |
| **Cost = $0** | `costDetails: {}`, `totalCost: 0` -- model not recognized for pricing |
| **No `internalModelId`** | Model string `us.anthropic.claude-sonnet-4-6` not mapped to a pricing tier |
| **Metadata is minimal** | `{"stream":true,"thoughtBudget":0,"toolCount":15,"app":"research-optimizer"}` -- missing EAGLE context |
| **Input double-escaped** | Message JSON is double-stringified -- hard to parse |
| **No `version`** | `null` -- can't track SDK version |
| **Output = null** | Final assistant response not captured |

## Improper Trace 2 (Research Optimizer — `b12f27ba`)

Same problems as Trace 1, plus:

| Issue | Detail |
|-------|--------|
| **Name = "model-inference"** | Generic, not descriptive |
| **sessionId = null** | No session linking -- can't track multi-turn conversations |
| **Only 1 observation** | Single GENERATION -- no agent/tool/span structure at all |
| **Input token count: 35** | Suspiciously low -- likely only counting user message, not system prompt |

---

## How to Produce Properly Formatted Traces

### 1. Use OpenTelemetry export (preferred) or Langfuse SDK with hierarchical spans

```
Trace
  +-- AGENT span (root) -- name: "invoke_agent {agent_name}"
       +-- SPAN per reasoning cycle -- name: "execute_event_loop_cycle"
            |-- GENERATION per LLM call -- name: "chat", model: full model ID
            +-- TOOL per tool execution -- name: tool function name
```

### 2. Required trace-level fields

- `name`: `"invoke_agent {agent_name}"` (not generic like "model-inference")
- `userId`: actual user ID (not "1")
- `sessionId`: conversation session ID (MUST be set for multi-turn tracking)
- `version`: SDK version string
- `input`: user message (properly serialized once, not double-escaped)
- `output`: final assistant response with finish_reason

### 3. Required metadata attributes

Set as OTEL resource/span attributes or Langfuse metadata:

```json
{
  "eagle.tenant_id": "...",
  "eagle.user_id": "...",
  "eagle.tier": "basic|advanced|premium",
  "eagle.session_id": "...",
  "eagle.phase": "intake|analysis|document",
  "gen_ai.request.model": "us.anthropic.claude-sonnet-4-20250514-v1:0",
  "gen_ai.usage.input_tokens": 131185,
  "gen_ai.usage.output_tokens": 1078,
  "gen_ai.agent.tools": "[\"tool1\", \"tool2\"]",
  "system_prompt": "..."
}
```

### 4. Observation requirements

- Every GENERATION must have `parentObservationId` pointing to its parent SPAN/AGENT
- Every GENERATION must include `usageDetails` with `input`, `output`, `total` token counts
- Use the **full Bedrock model ID** (e.g., `us.anthropic.claude-sonnet-4-20250514-v1:0`) not the alias (`claude-sonnet-4-6`) -- Langfuse needs the canonical ID for cost calculation
- TOOL observations must be siblings of their corresponding GENERATION under the same SPAN

---

## Fix Checklist for Improper Traces

- [ ] Add AGENT root observation
- [ ] Add SPAN observations per reasoning cycle
- [ ] Add TOOL observations for tool executions
- [ ] Set `parentObservationId` on all observations
- [ ] Use canonical Bedrock model ID (not alias) so costs resolve
- [ ] Set `sessionId` on traces for multi-turn tracking
- [ ] Set `userId` to actual user, not "1"
- [ ] Capture `output` on the trace
- [ ] Include EAGLE metadata attributes
- [ ] Fix double-escaping of input JSON

---

## EAGLE Trace Pipeline (how it works)

```
User message
  -> POST /api/chat/stream (FastAPI)
    -> strands_agentic_service.sdk_query_streaming()
      -> Strands Agent (BedrockModel) with OTEL instrumentation
        -> OTEL spans auto-emitted per: agent invoke, event loop cycle, chat call, tool call
          -> OTEL exporter sends to Langfuse OTEL endpoint
            -> Langfuse aggregates spans into a single trace with hierarchy
```

**Key file:** `server/app/strands_agentic_service.py` sets up the OTEL exporter with EAGLE-specific attributes (`eagle.tenant_id`, `eagle.user_id`, etc.) before creating the Strands Agent. The Strands SDK then auto-instruments all downstream calls.

**Langfuse OTEL endpoint:** Configured via `LANGFUSE_OTEL_ENDPOINT` env var (defaults to `https://us.cloud.langfuse.com/api/public/otel`). Auth is via `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` as Basic auth on the OTEL exporter.
