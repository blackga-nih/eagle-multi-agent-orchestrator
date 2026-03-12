# Plan: State Snapshots via AfterToolCallEvent Hook

## Task Description
Wire `AfterToolCallEvent` so the supervisor captures an `eagle_state` snapshot after
every tool call (subagent or otherwise). This gives us a state timeline within a single
`sdk_query()` invocation — visible in CloudWatch, Langfuse, and the trace story extractor.
Separately, use the supervisor's system prompt + `AfterModelCallEvent` to ensure
`update_state` is called before the final synthesis response.

## Objective
When you look at a trace story, every tool call should be bracketed:
  → BEFORE: state snapshot (phase, docs_required, docs_completed)
  → TOOL CALL executes (subagent or update_state)
  → AFTER: state snapshot (delta shows what changed)

The final supervisor turn (synthesis) should always be preceded by an `update_state`
call that captures the current phase transition.

---

## Available Strands Hook Events

All hooks are registered in `EagleHookProvider.register_hooks()` in
`server/app/strands_agentic_service.py`.

| Event | Fires | Writable fields | Current use |
|-------|-------|-----------------|-------------|
| `BeforeInvocationEvent` | Before agent loop starts | — | — |
| `AfterInvocationEvent` | After agent loop ends | — | State flush to DynamoDB |
| `BeforeModelCallEvent` | Before each LLM call | — | — |
| `AfterModelCallEvent` | After each LLM call | — | — |
| `BeforeToolCallEvent` | Before each tool call | `cancel_tool`, `selected_tool`, `tool_use` | Doc gating + `tool.started` telemetry |
| `AfterToolCallEvent` | After each tool call | `result` | (nothing yet) |
| `MessageAddedEvent` | When any message added | — | — |
| `AgentInitializedEvent` | When Agent() is created | — | — |

### AfterToolCallEvent fields
```python
@dataclass
class AfterToolCallEvent(HookEvent):
    selected_tool: Optional[AgentTool]  # the tool that ran
    tool_use: ToolUse                   # {toolUseId, name, input}
    invocation_state: dict[str, Any]   # kwargs passed to tool (includes agent.state)
    result: ToolResult                  # writable — can modify the result
    exception: Optional[Exception]     # set if tool raised
    cancel_message: str | None
```

### AfterModelCallEvent fields
```python
@dataclass
class AfterModelCallEvent(HookEvent):
    class ModelStopResponse:
        message: Message       # the generated message (text + tool_use blocks)
        stop_reason: StopReason  # "end_turn" | "tool_use" | "max_tokens"

    stop_response: Optional[ModelStopResponse]  # None if model failed
    exception: Optional[Exception]
```

---

## The Pattern: State Snapshots Around Tool Calls

### Problem
Currently `eagle_state` is only flushed in `AfterInvocationEvent` — once at the
end of the whole `sdk_query()` call. We have no visibility into how state evolved
during the turn (before/after each subagent call).

### Solution
Register `AfterToolCallEvent` in `EagleHookProvider`. After every tool call:
1. Read `invocation_state` — it contains the live `agent.state` dict
2. Compute a delta vs the previous snapshot
3. Emit `tool.completed` to CloudWatch with the state delta

```python
# In EagleHookProvider.register_hooks():
registry.add_callback(AfterToolCallEvent, self._on_after_tool_call)

def _on_after_tool_call(self, event: AfterToolCallEvent) -> None:
    tool_name = event.tool_use.get("name", "")
    tool_use_id = event.tool_use.get("toolUseId", "")

    # Read live state from invocation_state
    raw_state = event.invocation_state.get("agent", {})
    if hasattr(raw_state, "state"):
        raw_state = raw_state.state  # Agent instance → .state dict
    current = normalize(raw_state) if isinstance(raw_state, dict) else {}

    # Compute delta vs previous snapshot
    prev = self._last_state_snapshot or {}
    delta = {
        k: {"before": prev.get(k), "after": current.get(k)}
        for k in ("phase", "required_documents", "completed_documents", "turn_count")
        if prev.get(k) != current.get(k)
    }
    self._last_state_snapshot = dict(current)

    try:
        from .telemetry.cloudwatch_emitter import emit_tool_completed
        emit_tool_completed(
            tenant_id=self.tenant_id,
            user_id=self.user_id,
            session_id=self.session_id or "",
            tool_name=tool_name,
            tool_use_id=tool_use_id,
            state_delta=delta,
            success=event.exception is None,
        )
    except Exception:
        pass
```

---

## The Pattern: Enforce update_state Before Final Response

### Problem
After the three subagent calls complete, the supervisor synthesizes directly without
calling `update_state`. This means the phase transition and checklist state are not
captured as an explicit event before the user sees the response.

### Solution A — Prompt Engineering (simplest, preferred)
Add a rule to the supervisor system prompt:

```
State Push Rules — MANDATORY:
After completing all requested analyses and BEFORE writing your final synthesis:
  call update_state(state_type="phase_change", phase="analysis_complete",
                    previous="intake", package_id=<active_id>)
This MUST happen before the synthesis text block. The frontend checklist depends on it.
```

The supervisor already has `update_state` in its tool list. This is the lowest-friction
approach and visible in the trace as an extra TOOL span between the last subagent and
the synthesis GENE.

### Solution B — AfterModelCallEvent Guard (enforced, more complex)
`AfterModelCallEvent` fires after every LLM call with `stop_reason`. When
`stop_reason == "end_turn"` the model is about to give the final text response
(no more tool calls). We can check if `update_state` was called this turn:

```python
registry.add_callback(AfterModelCallEvent, self._on_after_model_call)

def _on_after_model_call(self, event: AfterModelCallEvent) -> None:
    sr = event.stop_response
    if not sr or sr.stop_reason != "end_turn":
        return
    # Check if update_state was called this invocation
    if not self._update_state_called_this_turn:
        logger.warning(
            "eagle.state_not_updated_before_final_response session=%s",
            self.session_id
        )
        try:
            from .telemetry.cloudwatch_emitter import emit_warning
            emit_warning(
                tenant_id=self.tenant_id,
                session_id=self.session_id or "",
                message="update_state not called before final response",
            )
        except Exception:
            pass
    self._update_state_called_this_turn = False  # reset for next turn
```

Track calls in `BeforeToolCallEvent`:
```python
if tool_name == "update_state":
    self._update_state_called_this_turn = True
```

Note: this pattern DETECTS the missing call and emits a warning but does not
block the response. To actually inject an `update_state` call you would need
to use `BeforeModelCallEvent` to add a system message — this is overly complex
and fragile. Prompt engineering (Solution A) is preferred.

---

## How This Appears in the Trace Story

With these hooks, the UC-01 multi-skill chain trace story becomes:

```
SUPERVISOR TURN 1
  USER PROMPT: "New acquisition..."
  LLM → text: "I'll execute all three analyses. Step 1:"
  LLM → tool_use: oa_intake(query="...")
  [AfterToolCallEvent] state delta: {} (no change yet)
  SUBAGENT oa_intake → classification analysis

SUPERVISOR TURN 2
  LLM (sees oa_intake result) → text: "Step 2:"
  LLM → tool_use: market_intelligence(query="...")
  [AfterToolCallEvent] state delta: {phase: {before: "intake", after: "market_research"}}
  SUBAGENT market_intelligence → market analysis

SUPERVISOR TURN 3
  LLM (sees market result) → text: "Step 3:"
  LLM → tool_use: legal_counsel(query="...")
  [AfterToolCallEvent] state delta: {}
  SUBAGENT legal_counsel → risk assessment

  LLM → tool_use: update_state(state_type="phase_change", phase="analysis_complete")
  [AfterToolCallEvent] state delta: {phase: {before: "market_research", after: "analysis_complete"}}
                                     docs_required: {before: [], after: ["SOW", "IGCE"]}

SUPERVISOR TURN 4 (synthesis — stop_reason="end_turn")
  LLM → text: "## SYNTHESIS: INTEGRATED FINDINGS..."
  [AfterModelCallEvent] stop_reason=end_turn, update_state_called=True ✓
```

---

## Relevant Files

- `server/app/strands_agentic_service.py` — `EagleHookProvider`, `register_hooks()`,
  `_on_before_tool_call()`, `_on_after_invocation()`
- `server/app/eagle_state.py` — `normalize()`, `apply_event()`, `to_trace_attrs()`
- `server/app/telemetry/cloudwatch_emitter.py` — add `emit_tool_completed()`,
  `emit_warning()` functions
- `scripts/extract_trace_story.py` — add `state_delta` to `AfterToolCallEvent`
  TOOL spans in the story output

---

## Step by Step Tasks

### 1. Add `_update_state_called_this_turn` tracking flag to EagleHookProvider
- In `__init__`, add `self._update_state_called_this_turn = False`
- In `__init__`, add `self._last_state_snapshot: dict = {}`

### 2. Register AfterToolCallEvent and AfterModelCallEvent
In `register_hooks()`:
```python
from strands.hooks.events import (
    AfterInvocationEvent, AfterModelCallEvent, AfterToolCallEvent, BeforeToolCallEvent
)
registry.add_callback(AfterToolCallEvent, self._on_after_tool_call)
registry.add_callback(AfterModelCallEvent, self._on_after_model_call)
```

### 3. Implement _on_after_tool_call
- Read `event.invocation_state` for the live agent state
- Compute delta vs `self._last_state_snapshot`
- Emit `tool.completed` CloudWatch event with state_delta
- Set `self._update_state_called_this_turn = True` if `tool_name == "update_state"`

### 4. Implement _on_after_model_call
- Check `stop_reason == "end_turn"`
- If `not self._update_state_called_this_turn`: emit warning to CloudWatch
- Reset `self._update_state_called_this_turn = False`

### 5. Add update_state instruction to supervisor prompt
In `sdk_query()` supervisor `system_prompt`, add to the State Push Rules section:
```
After completing all requested analyses and BEFORE writing your final synthesis,
call update_state with the current phase transition.
```

### 6. Add emit_tool_completed to cloudwatch_emitter.py
```python
def emit_tool_completed(tenant_id, user_id, session_id, tool_name,
                        tool_use_id, state_delta, success):
    ...
```

### 7. Update extract_trace_story.py
- After each TOOL span in the story, include `state_delta` from the CloudWatch
  event (or show it as a note if not available)

### 8. Validate with test 36 + new test 37
- Test 36 already validates the 4-turn structure
- Test 37: run test 15, then validate CloudWatch `tool.completed` events exist
  for each of the 3 subagent calls

---

## Acceptance Criteria
- [ ] `AfterToolCallEvent` fires and emits `tool.completed` to CloudWatch for each tool
- [ ] `state_delta` is non-empty for at least one tool call in UC-01
- [ ] `AfterModelCallEvent` logs warning when `update_state` not called before `end_turn`
- [ ] Supervisor prompt updated to call `update_state` before synthesis
- [ ] Test 37 validates CloudWatch `tool.completed` events presence

## Validation Commands
```bash
# Run test 15 (multi-skill chain) to generate a new trace
python tests/test_strands_eval.py --tests 15

# Run test 36 to validate trace story structure
python tests/test_strands_eval.py --tests 36

# Check CloudWatch for tool.completed events
python -c "
import boto3, json
cw = boto3.client('logs', region_name='us-east-1')
resp = cw.filter_log_events(
    logGroupName='/eagle/app',
    filterPattern='tool.completed',
    limit=10
)
for e in resp['events']:
    print(json.loads(e['message']))
"
```

## Notes

**Why Solution A (prompt) over Solution B (hook) for enforcement:**
Injecting tool calls via hooks requires modifying the agent's message history mid-turn,
which is fragile and can cause the model to loop or produce unexpected behavior.
The `AfterModelCallEvent` detection approach (Solution B) is a good OBSERVABILITY tool
— it tells you when the pattern wasn't followed — but the actual correction should
come from the system prompt.

**`invocation_state` contents:** The dict passed to `AfterToolCallEvent.invocation_state`
contains the keyword args that were passed to the tool function. For `@tool`-decorated
Strands tools that receive `agent_state`, the live state is accessible here. However,
for subagent tools (which are `@tool`-wrapped `Agent()` calls), the state in
`invocation_state` reflects the SUPERVISOR's state, not the subagent's state.

**State vs. subagent output:** The `update_state` tool modifies `supervisor.state`
directly (via `agent_state` kwarg). Subagent calls return text results but do NOT
modify the supervisor's state — that's why the explicit `update_state` call is needed
as a bridge between "subagent returned analysis" and "supervisor state reflects the findings."
