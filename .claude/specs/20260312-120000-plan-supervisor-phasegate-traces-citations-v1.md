# Plan: Supervisor Phase-Gate, Traces Tab, Subagent Citations

## Task Description

Three interrelated improvements to stop the 3-agent blast pattern, surface Langfuse trace stories in the UI, and show subagent citations inline in tool cards.

## Objective

1. Supervisor stops after `oa_intake` and waits for user direction — no more simultaneous multi-agent firing unless explicitly requested
2. A Traces tab in the activity panel fetches `/api/traces/story` and renders the turn-by-turn Langfuse story
3. Subagent tool cards display which KB documents/FAR sections were cited inside the expanded panel

## Problem Statement

- **3-agent blast**: Supervisor fires `oa_intake` + `market_intelligence` + `legal_counsel` in one turn even on conversational prompts. `oa_intake` should be a consultation gate — classify first, then user decides what's next.
- **Missing traces**: `/api/traces/story` endpoint exists and works but nothing in the frontend calls it. The Langfuse trace JSON is only visible in eval output files.
- **Blind tool cards**: Subagent cards (`oa_intake`, `market_intelligence`, etc.) expand to show a markdown report but give no indication of which KB documents or FAR sections the subagent read to produce it.

## Solution Approach

1. **agent.md phase-gate** — add an explicit ORCHESTRATION PROTOCOL section with turn-by-turn rules:
   - Turn 1 of any new acquisition: `query_compliance_matrix` (silent) + `oa_intake` → present brief → STOP
   - Subsequent turns: one specialist per turn, driven by user's next question
   - Full-blast exception: only when user says "run full analysis", "do everything", "complete package"
   - `query_compliance_matrix` as a silent background call at the start of any turn where `package_id` is known

2. **`trace-story.tsx`** — new component matching the CloudWatch pattern:
   - Fetches `GET /api/traces/story?session_id={sessionId}` on mount + refresh
   - Shows supervisor turns (turn #, tokens, tool calls) with expandable subagent breakdowns
   - Handles 503 (Langfuse not configured) with a friendly "connect Langfuse" message
   - Wired as a 6th tab in `activity-panel.tsx` with `GitBranch` icon

3. **Citations in SSE tool_result** — when a subagent returns, parse the `report` field for cited document titles and FAR references. Emit them as a `citations` array on the `tool_result` SSE event. Render as small chips inside the expanded tool card panel.

## Relevant Files

- `eagle-plugin/agents/supervisor/agent.md` — supervisor system prompt, add ORCHESTRATION PROTOCOL section
- `client/components/chat-simple/activity-panel.tsx` — add Traces tab (6th tab)
- `client/components/chat-simple/cloudwatch-logs.tsx` — reference pattern for new component
- `server/app/streaming_routes.py` — where `tool_result` SSE events are emitted, add citations extraction
- `server/app/strands_agentic_service.py` — where subagent results are captured
- `client/components/chat-simple/tool-use-display.tsx` — render citations chips in expanded panel
- `client/hooks/use-agent-stream.ts` — check `tool_result` event shape (citations field)
- `server/app/routes/traces.py` — existing `/api/traces/story` endpoint (no changes needed)

### New Files

- `client/components/chat-simple/trace-story.tsx` — Langfuse trace story viewer component

## Implementation Phases

### Phase 1: Foundation
Fix the supervisor orchestration (pure prompt change, no code).

### Phase 2: Core Implementation
Build the trace-story component and wire it into the activity panel.

### Phase 3: Integration & Polish
Add citations extraction to the SSE pipeline and render in tool cards.

## Step by Step Tasks

IMPORTANT: Execute every step in order, top to bottom.

### 1. Add ORCHESTRATION PROTOCOL to supervisor agent.md

In `eagle-plugin/agents/supervisor/agent.md`, add a new `## ORCHESTRATION PROTOCOL` section after `## IDENTITY & ROUTING`:

```markdown
## ORCHESTRATION PROTOCOL

### Standard Turn Sequence (default for all new acquisitions)

**Turn 1 — Gate turn:**
1. Call `query_compliance_matrix` silently (no preamble to user)
2. Call `oa_intake` with the acquisition details
3. Present a CONSULTATIVE BRIEF from intake findings
4. End with ONE question: "Want me to check the market next, or go straight to drafting the SOW?"
5. STOP. Do not call market_intelligence or legal_counsel yet.

**Turn 2+ — User-directed:**
- Route to exactly ONE specialist based on what the user asks for
- After each specialist: present brief → ask ONE follow-up → STOP
- Only call `update_state` after a tool that changes workflow phase

### Full-Analysis Exception
ONLY blast multiple specialists in one turn if user explicitly says:
- "run full analysis" / "do everything" / "complete package" / "run all three"
- "I need the full acquisition package"
In that case: `oa_intake` → `market_intelligence` → `legal_counsel` → synthesize

### Silent Background Calls (not announced to user)
- `query_compliance_matrix`: call at start of any turn where package_id is known in state
- `get_package_checklist`: call before any document generation turn
These are informational — never mention them in your response unless they surface a blocking issue.
```

### 2. Create `trace-story.tsx` component

Create `client/components/chat-simple/trace-story.tsx` following the `cloudwatch-logs.tsx` pattern exactly:

```typescript
'use client';

import { useState, useEffect, useCallback } from 'react';
import { GitBranch, RefreshCw, ChevronDown, ChevronRight, Cpu, MessageSquare, BarChart2, AlertCircle } from 'lucide-react';
import TraceDetailModal from './trace-detail-modal';

interface SubagentStory {
  name: string;
  input_tokens: number;
  output_tokens: number;
  response_preview: string;
}

interface TurnStory {
  turn: number;
  input_tokens: number;
  output_tokens: number;
  tool_calls: string[];
  has_reasoning: boolean;
  response_preview: string;
  subagents: SubagentStory[];
}

interface TraceStory {
  trace_id: string;
  session_id: string;
  timestamp: string;
  total_observations: number;
  supervisor_turns: number;
  total_tokens: {
    supervisor: { input: number; output: number };
    subagents: { input: number; output: number };
    combined: { input: number; output: number };
  };
  story: TurnStory[];
}

interface TraceStoryProps {
  sessionId?: string;
}

// TurnCard sub-component — expandable supervisor turn
function TurnCard({ turn }: { turn: TurnStory }) {
  const [open, setOpen] = useState(false);
  const hasSubagents = turn.subagents.length > 0;

  return (
    <div className="rounded-lg border border-gray-200 bg-white overflow-hidden">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center gap-2 px-3 py-2.5 text-left hover:bg-gray-50 transition"
      >
        {open ? <ChevronDown className="w-3.5 h-3.5 text-gray-400 shrink-0" /> : <ChevronRight className="w-3.5 h-3.5 text-gray-400 shrink-0" />}
        <span className="text-[10px] font-bold text-gray-500 uppercase shrink-0">Turn {turn.turn}</span>
        {turn.tool_calls.length > 0 && (
          <div className="flex gap-1 flex-wrap flex-1 min-w-0">
            {turn.tool_calls.map((name, i) => (
              <span key={i} className="px-1.5 py-0.5 rounded bg-violet-100 text-violet-700 text-[8px] font-bold uppercase">
                {name}
              </span>
            ))}
          </div>
        )}
        {!turn.tool_calls.length && (
          <span className="text-[10px] text-gray-400 flex-1 truncate">{turn.response_preview.slice(0, 50)}</span>
        )}
        <span className="text-[9px] text-gray-400 shrink-0 font-mono">
          {turn.input_tokens.toLocaleString()}↑ {turn.output_tokens.toLocaleString()}↓
        </span>
      </button>

      {open && (
        <div className="border-t border-gray-100 px-3 py-2 space-y-2">
          {turn.response_preview && (
            <p className="text-[10px] text-gray-600 leading-relaxed">{turn.response_preview}</p>
          )}
          {hasSubagents && (
            <div className="space-y-1">
              <span className="text-[9px] font-bold text-gray-400 uppercase tracking-wider">Subagents</span>
              {turn.subagents.map((sub, i) => (
                <div key={i} className="flex items-start gap-2 rounded bg-gray-50 px-2 py-1.5">
                  <Cpu className="w-3 h-3 text-violet-500 shrink-0 mt-0.5" />
                  <div className="min-w-0 flex-1">
                    <p className="text-[10px] font-semibold text-gray-700">{sub.name}</p>
                    <p className="text-[9px] text-gray-500 line-clamp-2 mt-0.5">{sub.response_preview}</p>
                  </div>
                  <span className="text-[9px] text-gray-400 font-mono shrink-0">
                    {sub.input_tokens.toLocaleString()}↑ {sub.output_tokens.toLocaleString()}↓
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function TraceStory({ sessionId }: TraceStoryProps) {
  const [story, setStory] = useState<TraceStory | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastFetched, setLastFetched] = useState<Date | null>(null);

  const fetchStory = useCallback(async () => {
    if (!sessionId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/traces/story?session_id=${encodeURIComponent(sessionId)}`);
      if (res.status === 503) {
        setError('langfuse_not_configured');
        return;
      }
      if (res.status === 404) {
        setError('no_traces');
        return;
      }
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`${res.status}: ${text}`);
      }
      const data: TraceStory = await res.json();
      setStory(data);
      setLastFetched(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch trace');
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => { fetchStory(); }, [fetchStory]);

  if (!sessionId) {
    return (
      <div className="flex flex-col items-center justify-center h-48 text-center px-4">
        <div className="w-10 h-10 rounded-full bg-gray-100 flex items-center justify-center mb-3">
          <GitBranch className="w-5 h-5 text-gray-400" />
        </div>
        <p className="text-sm text-gray-500">No session selected.</p>
        <p className="text-xs text-gray-400 mt-1">Start a conversation to see traces.</p>
      </div>
    );
  }

  if (error === 'langfuse_not_configured') {
    return (
      <div className="flex flex-col items-center justify-center h-48 text-center px-4">
        <div className="w-10 h-10 rounded-full bg-amber-100 flex items-center justify-center mb-3">
          <GitBranch className="w-5 h-5 text-amber-500" />
        </div>
        <p className="text-sm text-gray-700 font-medium">Langfuse not configured</p>
        <p className="text-xs text-gray-400 mt-1">Set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY in server environment.</p>
      </div>
    );
  }

  if (error === 'no_traces') {
    return (
      <div className="flex flex-col items-center justify-center h-48 text-center px-4">
        <GitBranch className="w-5 h-5 text-gray-300 mb-2" />
        <p className="text-sm text-gray-500">No traces yet for this session.</p>
        <p className="text-xs text-gray-400 mt-1">Traces appear after the first agent response.</p>
      </div>
    );
  }

  return (
    <>
      {/* Toolbar */}
      <div className="flex items-center justify-between mb-3">
        <div className="text-[10px] text-gray-500 space-x-2">
          {story && (
            <>
              <span>{story.supervisor_turns} turns</span>
              <span>·</span>
              <span>{story.total_tokens.combined.input.toLocaleString()} in / {story.total_tokens.combined.output.toLocaleString()} out tokens</span>
            </>
          )}
          {lastFetched && <span>· {lastFetched.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>}
        </div>
        <button
          onClick={fetchStory}
          disabled={loading}
          className="flex items-center gap-1 text-[10px] text-blue-600 hover:text-blue-800 disabled:opacity-50 transition"
        >
          <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {error && !['langfuse_not_configured', 'no_traces'].includes(error) && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs mb-3">
          <AlertCircle className="w-3.5 h-3.5 shrink-0" />
          {error}
        </div>
      )}

      {loading && !story && (
        <div className="space-y-2">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-10 rounded-lg bg-gray-100 animate-pulse" />
          ))}
        </div>
      )}

      {story && (
        <div className="space-y-1.5">
          {/* Token summary bar */}
          <div className="flex items-center gap-3 px-3 py-2 rounded-lg bg-gray-50 border border-gray-200 mb-2">
            <BarChart2 className="w-3.5 h-3.5 text-gray-400 shrink-0" />
            <div className="flex gap-4 text-[9px] font-mono text-gray-500">
              <span>supervisor: {story.total_tokens.supervisor.input.toLocaleString()}↑ {story.total_tokens.supervisor.output.toLocaleString()}↓</span>
              <span>subagents: {story.total_tokens.subagents.input.toLocaleString()}↑ {story.total_tokens.subagents.output.toLocaleString()}↓</span>
            </div>
          </div>
          {story.story.map(turn => (
            <TurnCard key={turn.turn} turn={turn} />
          ))}
        </div>
      )}
    </>
  );
}
```

### 3. Wire Traces tab into activity-panel.tsx

In `activity-panel.tsx`:
- Add import: `import TraceStory from './trace-story';`
- Add `GitBranch` to lucide-react imports
- Add to `TABS` array: `{ id: 'traces', label: 'Traces', icon: GitBranch }`
- Extend `TabId` type to include `'traces'`
- Add to content section: `{activeTab === 'traces' && <TraceStory sessionId={sessionId} />}`

### 4. Add citations extraction to streaming_routes.py

In `server/app/streaming_routes.py`, in the section where `tool_result` SSE events are emitted for subagent calls, add a `_extract_citations()` helper:

```python
import re

def _extract_citations(report: str) -> list[str]:
    """Extract document titles and FAR references from a subagent markdown report.

    Looks for:
    - FAR Part references: "FAR Part 15", "FAR 15.304", "DFARS 252.xxx"
    - Bold titles: **Title Here**
    - Section headers: ### Title
    - Numbered sections that look like document names
    """
    citations = []
    seen = set()

    # FAR/DFARS references
    for m in re.finditer(r'(?:FAR|DFARS)\s+(?:Part\s+)?\d+(?:\.\d+)?(?:-\d+)?', report):
        ref = m.group(0).strip()
        if ref not in seen:
            seen.add(ref)
            citations.append(ref)

    # Bold text that looks like document titles (##/### headings)
    for m in re.finditer(r'^#{1,3}\s+(.+)$', report, re.MULTILINE):
        title = m.group(1).strip().lstrip('#').strip()
        if len(title) > 4 and len(title) < 80 and title not in seen:
            seen.add(title)
            citations.append(title)

    return citations[:12]  # cap at 12 to avoid overwhelming UI
```

When building the `tool_result` event data for subagent tools, call `_extract_citations(result.get("report", ""))` and include `"citations": citations` in the emitted event dict.

### 5. Render citations chips in tool-use-display.tsx

In the collapsible result panel section of `ToolUseDisplay` (the `expanded && ...` block), before showing `reportText`, add:

```tsx
{/* Citations chips — FAR refs and doc titles extracted from report */}
{result?.citations && Array.isArray(result.citations) && result.citations.length > 0 && (
  <div className="flex items-center gap-1 flex-wrap mb-2 pb-2 border-b border-gray-100">
    <span className="text-[9px] text-gray-400 font-medium uppercase tracking-wider shrink-0">Cited</span>
    {(result.citations as string[]).map((c, i) => (
      <span key={i} className="inline-flex items-center px-1.5 py-0.5 rounded border border-gray-200 bg-gray-50 text-[9px] text-gray-600 font-mono">
        {c}
      </span>
    ))}
  </div>
)}
```

Also update `ClientToolResult` type (in `@/lib/client-tools`) to include `citations?: string[]`.

### 6. Validate

```bash
# TypeScript check
cd client && npx tsc --noEmit

# Python lint
cd server && python -m ruff check app/streaming_routes.py

# Spot-check trace endpoint locally (with server running)
curl "http://localhost:8000/api/traces/story?session_id=test" -v
# Expect 503 if LANGFUSE keys not set, not a 500
```

## Testing Strategy

- After agent.md change: send "I need to buy a $500K cloud migration service" → verify supervisor only calls `query_compliance_matrix` + `oa_intake` on Turn 1, then stops with a question
- After traces tab: open activity panel → Traces tab → should show "No session selected" initially, "Langfuse not configured" after sending a message (unless keys are set)
- After citations: expand an `oa_intake` tool card → should see FAR Part citations in the header of the expanded panel

## Acceptance Criteria

- [ ] Supervisor sends only `oa_intake` (+ compliance matrix) on a new acquisition prompt, then asks a follow-up question and stops
- [ ] Traces tab renders in activity panel (6th tab with GitBranch icon)
- [ ] Traces tab shows 503/Langfuse-not-configured empty state gracefully
- [ ] `tool_result` SSE events for subagent calls include `citations` array when report contains FAR refs
- [ ] Expanded subagent tool cards show citation chips before report text
- [ ] TypeScript compiles clean, ruff passes

## Validation Commands

```bash
cd client && npx tsc --noEmit
cd server && python -m ruff check app/streaming_routes.py app/strands_agentic_service.py
```

## Notes

- The `query_compliance_matrix` silent call instruction in agent.md should use the word "silently" specifically — the model respects that and doesn't preamble it
- Citations regex is intentionally broad — FAR Part 15 / FAR 15.304 / DFARS 252.227-7013 all match
- The `/api/traces/story` endpoint already proxies Langfuse — no backend changes needed for the Traces tab itself
- `TraceDetailModal` is imported by cloudwatch-logs and bedrock-logs but not needed for the trace story tab (the TurnCard inline expansion is sufficient)
- Phase-gating only applies to the supervisor — subagents don't need orchestration rules
