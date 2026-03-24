---
type: expert-file
file-type: skill
domain: playground
tags: [playground, trace, langfuse, visualization, eval, agents]
description: "Generate an interactive HTML trace viewer from a Langfuse trace ID or recent eval run. Produces a spatial conversation-flow visualization showing agent reasoning, tool dispatch, and results."
---

# Trace Viewer Playground

> Generate an interactive HTML visualization of a Langfuse trace — spatial conversation flow showing multi-agent orchestration, LLM reasoning, tool dispatch, and results.

## When to Use

- User provides a Langfuse trace ID or URL
- User asks to visualize an eval run, agent trace, or tool chain
- After running `/experts:eval:maintenance` and wanting to inspect a specific trace
- Debugging agent behavior — seeing what each agent thought and did

## Prerequisites

Langfuse credentials in `server/.env`:
- `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`, `LANGFUSE_PROJECT_ID`

## Instructions

### Step 1: Fetch Trace Data

Extract the trace ID from the user's input (URL or raw ID). Then fetch:

```python
import asyncio, json, os, base64, httpx
from dotenv import load_dotenv; load_dotenv('server/.env')

pub = os.getenv('LANGFUSE_PUBLIC_KEY')
sec = os.getenv('LANGFUSE_SECRET_KEY')
host = os.getenv('LANGFUSE_HOST', 'https://us.cloud.langfuse.com')
auth = 'Basic ' + base64.b64encode(f'{pub}:{sec}'.encode()).decode()

async def fetch(trace_id):
    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1. Get trace metadata
        trace = (await client.get(f'{host}/api/public/traces/{trace_id}', headers={'Authorization': auth})).json()

        # 2. Get all observations (generations, tools, spans, agents)
        obs = (await client.get(f'{host}/api/public/observations',
            params={'traceId': trace_id, 'limit': 100},
            headers={'Authorization': auth})).json().get('data', [])
        obs.sort(key=lambda x: x.get('startTime', ''))

        return trace, obs
```

### Step 2: Parse Observations

Categorize each observation and extract:

| Field | Source |
|-------|--------|
| Type | `obs.type` — AGENT, GENERATION, TOOL, SPAN |
| Name | `obs.name` |
| Duration | `endTime - startTime` (ms) |
| Cost | `obs.calculatedTotalCost` |
| Parent | `obs.parentObservationId` — determines nesting |
| Agent identity | Infer from parent chain (supervisor vs subagent) |
| LLM reasoning | `obs.output.message` — array of text + tool_use blocks |
| Tool input/output | `obs.input` / `obs.output` for TOOL type |
| Status | `obs.level` or `obs.statusMessage` for errors |
| Token usage | `obs.usage` — `{input, output, total}` |

**Key parsing for GENERATION output:**
```python
out = obs.get('output', {})
# Format: {"finish_reason": "tool_use"|"end_turn", "message": [...]}
message = out.get('message', '')
# message is a JSON string: [{"text": "..."}, {"toolUse": {"name": "...", "input": {...}}}]
if isinstance(message, str):
    blocks = json.loads(message)
    for block in blocks:
        if 'text' in block:   # LLM reasoning text
            reasoning = block['text']
        if 'toolUse' in block: # Tool dispatch decision
            tool_name = block['toolUse']['name']
            tool_input = block['toolUse']['input']
```

### Step 3: Identify Agent Hierarchy

Build the agent tree from parent observation IDs:

1. Find all AGENT-type observations — these are the agent nodes
2. For each non-AGENT observation, walk `parentObservationId` up to find its owning AGENT
3. Group observations by agent — this gives you the "conversation" for each agent
4. Identify which TOOL observations are subagent dispatchers (they have child AGENT observations)

### Step 4: Generate HTML

Use the template structure below. Write to a file named `langfuse-trace-{short_id}.html` in the project root.

After writing, open in browser:
```bash
start "" "langfuse-trace-{short_id}.html"   # Windows
open "langfuse-trace-{short_id}.html"       # macOS
```

## HTML Template Structure

The visualization is a **vertical conversation flow** with these sections:

### Header
- Logo + trace metadata pills (duration, cost, trace ID)
- **Agent pills**: One pill per agent, color-coded
- **Skill/Tool pills**: One pill per unique tool invoked
- **Model/Token/Stats pills**: Model name, token counts, generation count, tool success/error counts
- **User input banner**: The original user message with avatar, timestamp, trace ID

### Conversation Flow (main body)
A vertical spine with numbered phase markers. Each phase is an agent action:

**Phase pattern:**
```
[timestamp] [numbered dot]
  ┌─ Agent Bubble (collapsible) ─────────────────────┐
  │  Avatar | Name | Role | Stats (dur, cost, LLM#)  │
  │                                                    │
  │  🟣 Thinking · Cycle N                             │
  │  ┌─ reason-text ─────────────────────────────────┐ │
  │  │ Actual LLM output text with key terms         │ │
  │  │ highlighted. Shows the agent's reasoning.     │ │
  │  └───────────────────────────────────────────────┘ │
  │  ↳ Decision: dispatch tool_a and tool_b            │
  │                                                    │
  │  ║ parallel tools @ Ns                             │
  │  ║ [tool_a 1.2s] [tool_b 3.4s] [tool_c ERR]       │
  │                                                    │
  │  Tool Results: summary of what came back           │
  │                                                    │
  │  ✓ Final Summary · Cycle N                         │
  │  ┌─ reason-text (final output) ──────────────────┐ │
  │  │ The agent's synthesized final response        │ │
  │  └───────────────────────────────────────────────┘ │
  │                                                    │
  │  ┌─ output-bubble ──────────────────────────────┐  │
  │  │ ✔ Result returned to parent agent            │  │
  │  └──────────────────────────────────────────────┘  │
  └────────────────────────────────────────────────────┘

  ── connector: "what happened next" ──
```

**Connectors** between phases show the transition (e.g., "intake complete, supervisor resumes @ 77s").

### Footer
- Summary stat cards (agents, LLM generations, tools OK, tool errors, cost, duration)
- Pie chart (LLM thinking % vs tool execution % vs overhead %)
- Issues section (errors with root cause)

## Color System

| Element | Color Variable | Hex |
|---------|---------------|-----|
| Supervisor agent | `--blue` | #4da6ff |
| Intake subagent | `--cyan` | #22d3ee |
| Legal subagent | `--orange` | #ffa94d |
| Other subagents | Assign from: `--pink` (#f472b6), `--gold` (#fbbf24) |
| LLM generation | `--purple` | #b48eff |
| Tool success | `--green` | #42d77d |
| Tool error | `--red` | #ff6b6b |
| Span/overhead | `--border` | #232d3d |
| Background | `--bg` | #0a0e14 |
| Surface | `--surface` | #131820 |

## CSS Class Reference

| Class | Purpose |
|-------|---------|
| `.bubble .sup/.int/.leg` | Agent conversation bubble with left border color |
| `.bh` | Bubble header (clickable, collapses body) |
| `.bb` | Bubble body (collapsible content) |
| `.reason` | LLM thinking block (icon + body) |
| `.reason-icon.think` | Purple thinking indicator |
| `.reason-icon.done` | Green completion indicator |
| `.reason-text` | Styled quote block for LLM output text |
| `.reason-text .highlight` | Key terms in bright white |
| `.dispatch` | Tool dispatch decision line (↳ prefix) |
| `.par` | Parallel tool bracket (line + body) |
| `.par-line` | Colored vertical line for parallel group |
| `.tc` | Tool chip (name + duration badge) |
| `.tc.err` | Error tool chip (red border + tag) |
| `.tool-result` | Summary of tool return values |
| `.out-bubble` | Result bubble returned to parent agent |
| `.conn` | Connector between phases |
| `.phase` | Phase wrapper with dot marker + timestamp |

## JavaScript

Minimal — only two behaviors:

```javascript
// 1. Collapse/expand agent bubbles
function toggle(hdr) {
  const body = hdr.nextElementSibling;
  const chev = hdr.querySelector('.chev');
  if (body && body.classList.contains('bb')) {
    const open = body.style.display !== 'none';
    body.style.display = open ? 'none' : '';
    if (chev) chev.classList.toggle('open', !open);
  }
}

// 2. Tooltip on tool chips
const tip = document.createElement('div');
tip.className = 'tip';
document.body.appendChild(tip);
document.querySelectorAll('.tc').forEach(c => {
  c.addEventListener('mouseenter', e => { /* show */ });
  c.addEventListener('mousemove', e => { /* position */ });
  c.addEventListener('mouseleave', () => tip.classList.remove('show'));
});
```

## Adapting for Different Traces

The template handles any Strands multi-agent trace:

1. **Single agent (no subagents)**: One continuous conversation flow, no nesting
2. **2-level (supervisor + 1 subagent)**: Two agent bubbles connected by a dispatch
3. **3-level (supervisor + N subagents)**: Multiple nested bubbles. Assign colors from the palette
4. **Parallel subagents**: If supervisor dispatches 2+ subagent tools simultaneously, show them side-by-side or sequential with a "parallel dispatch" connector
5. **No tool calls**: Just show thinking blocks with reasoning text
6. **Many tool calls**: Group parallel calls under bracket, sequential calls as individual chips

## Known Patterns

| Pattern | Visualization |
|---------|--------------|
| `finish_reason: tool_use` | Show reasoning text + dispatch decision + tool chips |
| `finish_reason: end_turn` | Show reasoning text as final summary (green icon) |
| `knowledge_search` RecursionError | Red error chip + fallback note in tool-result |
| `web_fetch` HTTP 403 | Red error chip, note alternative sources used |
| Parent AGENT with null output | Wrapper trace — show as the top-level container |
| Long generation (>30s) | Add duration bar showing relative length |

## Example Invocation

```
/experts:playground:trace-viewer fcec82525616e3ff999d82f90d3425f2
```

Or with a Langfuse URL:
```
/experts:playground:trace-viewer https://us.cloud.langfuse.com/project/xxx/traces/yyy
```

## Reference Implementation

See `langfuse-trace-viewer.html` in the project root for a complete working example built from trace `fcec8252`.
