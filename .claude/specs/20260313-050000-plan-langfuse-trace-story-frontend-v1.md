# Plan: Langfuse Trace Story Frontend Viewer

## Task Description
Add a Langfuse trace story viewer to the EAGLE frontend. The backend proxies the Langfuse API to build a hierarchical conversation trace (supervisor turns → subagent invocations → token counts), and a new "Traces" tab in the activity panel renders it as an interactive timeline.

## Objective
Users can view the full conversational trace of any session — supervisor LLM turns, subagent delegations, tool calls, response previews, and token usage — directly in the EAGLE frontend, powered by Langfuse OTEL data.

## Problem Statement
Langfuse captures the richest observability data (full conversation traces with nested supervisor → subagent hierarchy) via OTEL auto-instrumentation. This data is only accessible via the Langfuse dashboard or the eval test script (test 36). CloudWatch captures flat operational events but not the conversational chain. Users need the trace story in-app.

## Solution Approach
1. **Backend route** `GET /api/traces/story?session_id={id}` proxies the Langfuse API, walks the observation hierarchy, and returns a structured story JSON.
2. **Frontend component** `langfuse-traces.tsx` renders the story as expandable turn cards with nested subagent details.
3. **Activity panel** gets a 6th "Traces" tab alongside Documents, Notifications, Agent Logs, CloudWatch, Bedrock.

## Relevant Files

### Existing Files
- `server/tests/test_strands_eval.py` (lines 3006-3197) — **reference implementation** for Langfuse API story extraction (test_36_langfuse_trace_story)
- `client/components/chat-simple/activity-panel.tsx` — add 6th tab here
- `client/components/chat-simple/cloudwatch-logs.tsx` — **pattern reference** for API fetch + rendering style
- `client/components/chat-simple/trace-detail-modal.tsx` — reuse for raw JSON drill-down
- `client/hooks/use-agent-stream.ts` — provides session_id context
- `client/types/stream.ts` — type definitions
- `server/app/routes/_deps.py` — shared route dependencies (auth, user context)
- `server/app/main.py` — register new router

### New Files
- `server/app/routes/traces.py` — backend Langfuse proxy route
- `client/components/chat-simple/langfuse-traces.tsx` — trace story viewer component

## Implementation Phases

### Phase 1: Backend Route
Create the `/api/traces/story` endpoint that calls Langfuse API and builds the story JSON.

### Phase 2: Frontend Component
Build the trace story viewer component matching the existing activity panel style.

### Phase 3: Integration
Wire the new tab into activity-panel.tsx and register the backend route.

## Step by Step Tasks

### 1. Create Backend Route (`server/app/routes/traces.py`)

- Create `server/app/routes/traces.py` with a FastAPI router
- Implement `GET /api/traces/story` that:
  - Accepts `session_id` query param (required)
  - Reads `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` from env
  - Returns 503 if Langfuse credentials not configured
  - Calls Langfuse API: `GET /api/public/traces?sessionId={id}&limit=5`
  - Takes the most recent trace
  - Calls `GET /api/public/observations?traceId={id}&limit=100`
  - Walks the observation hierarchy (same algorithm as test 36):
    - Find root AGEN (supervisor)
    - Walk SPAN cycles → GENE (LLM calls) → TOOL spans → nested AGEN (subagents)
    - Extract: response blocks, tool calls, token counts, latency, reasoning presence
  - Returns JSON:
    ```json
    {
      "trace_id": "...",
      "session_id": "...",
      "timestamp": "ISO-8601",
      "total_observations": 21,
      "supervisor_turns": 4,
      "story": [
        {
          "turn": 1,
          "input_tokens": 9593,
          "output_tokens": 806,
          "tool_calls": ["oa_intake"],
          "has_reasoning": false,
          "subagents": [
            {
              "name": "oa_intake",
              "input_tokens": 1300,
              "output_tokens": 6504,
              "response_preview": "first 200 chars..."
            }
          ]
        }
      ]
    }
    ```
- Use `httpx` (already in requirements) or `urllib.request` for the Langfuse API calls
- Error handling: 404 if no traces found, 502 if Langfuse API fails, 503 if not configured

### 2. Register Route in `server/app/main.py`

- Import traces router: `from .routes.traces import router as traces_router`
- Add: `app.include_router(traces_router)`

### 3. Create Frontend Component (`client/components/chat-simple/langfuse-traces.tsx`)

- Follow the `cloudwatch-logs.tsx` pattern exactly:
  - Props: `{ sessionId?: string }`
  - `useEffect` fetches `/api/traces/story?session_id={sessionId}` on mount and when sessionId changes
  - Loading/error/empty states matching existing panel styling
  - Refresh button in header
- Story rendering:
  - Each supervisor turn is a card (rounded-lg border, matching existing card style)
  - Card header: `Turn {n}` badge + token count badge + tool call badges + reasoning indicator
  - Card body (collapsible): subagent details
    - Each subagent: name badge (purple) + token counts + response preview (first 200 chars, collapsible to full)
  - Synthesis turn (no tool calls) gets a special "Synthesis" badge
- Summary header above cards:
  - Trace ID (truncated, copy-to-clipboard)
  - Total turns, total tokens, total subagent invocations
  - Timestamp
- Click any turn card to open `TraceDetailModal` with the raw turn JSON
- Color scheme matching existing panel:
  - Supervisor turns: blue badges
  - Subagent calls: purple badges
  - Token counts: emerald badges (matches cloudwatch-logs.tsx)
  - Reasoning: amber indicator
  - Synthesis: indigo badge

### 4. Add "Traces" Tab to Activity Panel (`activity-panel.tsx`)

- Import `LangfuseTraces` component and `Activity` icon from lucide-react
- Add to `TabId` union: `| 'traces'`
- Add to `TABS` array: `{ id: 'traces', label: 'Traces', icon: Activity }`
- Add render case: `{activeTab === 'traces' && <LangfuseTraces sessionId={sessionId} />}`
- No badge count needed (data loads on-demand, not streamed)

### 5. Frontend Proxy Route (Next.js API route)

- Check if `/api/traces/story` needs a Next.js proxy (like `/api/invoke` proxies to backend)
- If the frontend talks directly to the backend via CORS, no proxy needed
- If proxy needed: create `client/app/api/traces/story/route.ts` that forwards to backend

### 6. Validate the Implementation

- Start backend: `uvicorn app.main:app --reload --port 8000`
- Verify endpoint: `curl "http://localhost:8000/api/traces/story?session_id=nci-oa-premium-co-johnson-001-eval-015"`
- Start frontend: `npm run dev` in client/
- Open activity panel → Traces tab → verify story renders
- TypeScript check: `cd client && npx tsc --noEmit`
- Python lint: `cd server && ruff check app/routes/traces.py`

## Testing Strategy

- **Backend unit test**: Mock Langfuse API responses, verify story extraction algorithm
- **Manual E2E**: Run an eval test (test 15), then check Traces tab shows the multi-skill chain
- **Edge cases**: No Langfuse credentials (503), no traces for session (404), Langfuse API timeout (502)
- **TypeScript**: `npx tsc --noEmit` passes

## Acceptance Criteria

1. `GET /api/traces/story?session_id={id}` returns the story JSON with supervisor turns and subagent details
2. Activity panel has a 6th "Traces" tab
3. Traces tab shows supervisor turns as expandable cards with token counts and tool call badges
4. Subagent invocations are nested under their parent supervisor turn
5. Click on a turn opens TraceDetailModal with raw JSON
6. Graceful degradation: "Langfuse not configured" message when env vars missing
7. `ruff check app/routes/traces.py` passes
8. `npx tsc --noEmit` passes

## Validation Commands

- `cd server && ruff check app/routes/traces.py` — Python lint
- `cd client && npx tsc --noEmit` — TypeScript check
- `curl "http://localhost:8000/api/traces/story?session_id=nci-oa-premium-co-johnson-001-eval-015"` — API test
- `python -m pytest tests/test_strands_eval.py -k test_36 -v` — Langfuse trace story test (requires Langfuse keys)

## Notes

- The Langfuse free tier allows 50K observations/month — this endpoint just reads, doesn't write
- Response previews are truncated to 200 chars in the story JSON to avoid bloating the frontend
- The observation hierarchy follows Strands SDK OTEL auto-instrumentation pattern:
  `AGEN → SPAN (cycle) → GENE (LLM call) + TOOL → AGEN (subagent) → SPAN → GENE`
- `httpx` is preferred over `urllib.request` for async compatibility, but sync is fine since the route is not streaming
