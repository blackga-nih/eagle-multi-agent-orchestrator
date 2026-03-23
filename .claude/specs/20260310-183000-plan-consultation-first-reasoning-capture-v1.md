# Plan: Consultation-First Conversation Flow with AI Reasoning Capture

## Task Description
Redesign the EAGLE conversation flow to prioritize consultation over document generation. Users should have a productive, guided consultation — short questions, expert recommendations, minimal reading — while EAGLE silently records every AI reasoning step, tool justification, and compliance determination as structured JSON. When the user is ready, EAGLE generates documents with an appendix of AI reasoning and decision rationale. This extends across supervisor prompting, tool dispatch, progressive disclosure, and the streaming protocol.

## Objective
When complete:
1. Users experience a concise, form-like consultation where EAGLE recommends and they confirm — not walls of text
2. Every tool call emits a `reasoning` JSON field capturing why it was invoked and what it concluded
3. Reasoning is accumulated per-session and attached as an appendix to generated documents
4. The supervisor prompt enforces consultation-first, documents-later sequencing
5. The frontend can display reasoning in the activity panel (agent logs or dedicated tab)

## Problem Statement
Ryan's feedback: *"Users don't want to read a lot of text — they want to fill out their form but have a productive consultation with AI. When ready, they move on to documents."*

Current gaps:
- Supervisor prompt says "DO THE WORK" and generates documents immediately — often before consultation is complete
- No structured reasoning capture — agent decisions are invisible
- No appendix mechanism for AI justifications in generated documents
- `StreamEventType.REASONING` exists in `stream_protocol.py` but is **never emitted**
- `ChatTraceCollector` tracks tokens/tools but not reasoning content
- oa-intake skill says "document the rationale" (line 65) but no code implements it
- Compliance matrix results (the core decision engine) are used ephemerally — not persisted

## Solution Approach

### Three Pillars

1. **Consultation-First Flow** — Modify supervisor prompt + oa-intake skill to enforce: gather → recommend → confirm → generate. Keep responses under 3 sentences. Use structured questions, not open-ended exploration.

2. **Reasoning Capture** *(use `/experts:sse:plan` for SSE wiring)* — Add a `reasoning` field to every tool result. Emit `StreamEventType.REASONING` SSE events (infrastructure exists but is unused — see SSE expertise Part 1). Accumulate reasoning entries in a session-scoped `ReasoningLog`. Persist to DynamoDB alongside the package. The SSE pipeline already supports this event type via `MultiAgentStreamWriter.write_reasoning(queue, content)` — we just need to call it.

3. **Document Appendix** *(use `/experts:sse:plan` for emission flow)* — When `create_document` fires, inject the accumulated reasoning log as "Appendix: AI Decision Rationale". The tool result emission must follow the existing SSE patterns: factory tools push via `result_queue` + `loop.call_soon_threadsafe()` (Pattern A/C in SSE expertise Part 2), `stream_generator()` routes them as TOOL_RESULT events. The reasoning appendix data rides alongside the document content in the same `tool_result` payload.

### SSE Expert Reference

Pillars 2 and 3 depend heavily on the SSE streaming pipeline. Before implementing, run `/experts:sse:question` to validate assumptions and `/experts:sse:plan` to design the exact emission points. Key SSE expertise sections to consult:

| SSE Expertise Section | Relevance |
|---|---|
| **Part 1: Stream Protocol** | `StreamEventType.REASONING` enum, `write_reasoning()` method, `StreamEvent.reasoning` field — all exist but are never called |
| **Part 2: Backend Streaming Pipeline** | `result_queue` + `_drain_tool_results()` + `_emit_tool_result()` — reasoning must follow same factory tool emission pattern |
| **Part 3: Streaming Routes** | `stream_generator()` chunk routing — need new `elif chunk_type == "reasoning"` branch |
| **Part 5: Frontend SSE Consumer** | `processEventData()` in `use-agent-stream.ts` — need new `case 'reasoning'` handler |
| **Part 8: Patterns** | Must use `loop.call_soon_threadsafe()` bridge for sync Strands thread → async event loop |

## Relevant Files

### Supervisor & Agent Prompts
- **`eagle-plugin/agents/supervisor/agent.md`** — Main orchestrator prompt. Currently biased toward immediate document generation. Needs consultation-first sequencing.
- **`eagle-plugin/skills/oa-intake/SKILL.md`** — Intake consultation flow. Already has good Phase 1-5 structure. Needs: shorter responses, explicit reasoning capture, no premature doc gen.
- **`eagle-plugin/skills/document-generator/SKILL.md`** — Document generation skill. Needs: accept reasoning log as input, include appendix section.

### Backend — Tool Dispatch & Reasoning
- **`server/app/strands_agentic_service.py`** — Tool factories, supervisor assembly, progressive disclosure. Add reasoning capture to tool result handling.
- **`server/app/agentic_service.py`** — `TOOL_DISPATCH` handlers. Add `reasoning` field to return dicts for `create_document`, `query_compliance_matrix`, `search_far`, `dynamodb_intake`.
- **`server/app/stream_protocol.py`** — `StreamEventType.REASONING` exists but unused. Wire it into the streaming flow.
- **`server/app/streaming_routes.py`** — Emit REASONING SSE events when tools return reasoning.

### Backend — Storage
- **`server/app/session_store.py`** — Add reasoning log persistence per session.
- **`server/app/package_store.py`** — Add `reasoning_log` field to package records. Add `_UPDATABLE_FIELDS` entry.

### Frontend
- **`client/components/chat-simple/agent-logs.tsx`** — Show reasoning entries in agent logs tab.
- **`client/hooks/use-agent-stream.ts`** — Handle `reasoning` SSE event type.

### New Files
- **`server/app/reasoning_store.py`** — Session-scoped reasoning log accumulator + DynamoDB persistence.
- **`server/tests/test_reasoning_capture.py`** — Unit tests for reasoning accumulation and appendix generation.

## Implementation Phases

### Phase 1: Reasoning Infrastructure (Backend)
Build the reasoning data model, storage, and accumulator. No prompt changes yet.

### Phase 2: Tool Reasoning Emission (Backend) — `/experts:sse:plan`
Add `reasoning` field to tool results. Wire into the SSE streaming pipeline following existing patterns from SSE expertise Part 2 (result_queue emission) and Part 3 (stream_generator routing). Activate the unused `StreamEventType.REASONING` and `write_reasoning()` in `stream_protocol.py`.

**SSE wiring checklist:**
1. Tool handlers in `agentic_service.py` → add `reasoning` key to result dicts
2. Factory tools in `strands_agentic_service.py` → reasoning data flows through `result_queue` via `_emit_tool_result()` (no new emission pattern needed)
3. `stream_generator()` in `streaming_routes.py` → extract reasoning from `tool_result` chunks, call `writer.write_reasoning()`, accumulate in `ReasoningLog`
4. Verify: reasoning events follow the same `loop.call_soon_threadsafe()` bridge pattern (SSE expertise Part 2, "All patterns use...")

### Phase 3: Consultation-First Prompting (Prompts)
Modify supervisor and oa-intake prompts for consultation-first flow.

### Phase 4: Document Appendix (Backend + SSE) — `/experts:sse:plan`
Inject accumulated reasoning into generated documents. The appendix content is included in the `create_document` tool result payload, which flows through the standard SSE tool_result emission chain (SSE expertise Part 2, Pattern A: service tools → `TOOL_DISPATCH` → `_emit_tool_result()` → `result_queue`).

**SSE wiring checklist:**
1. `_handle_create_document()` → load `ReasoningLog`, append as markdown, include in result
2. Result emission follows Pattern A — no new SSE plumbing needed
3. Frontend `tool_result` handler already renders document cards — appendix is part of the content
4. Reasoning log reference is passed through `session_id` context (already available in tool dispatch)

### Phase 5: Frontend + Validation — `/experts:sse:question`
Wire `reasoning` SSE events into the UI. Consult SSE expertise Part 4 (frontend types) and Part 5 (`processEventData()` routing). Add `case 'reasoning'` to the event switch. End-to-end testing.

## Step by Step Tasks

### 1. Create ReasoningStore — Session-Scoped Reasoning Accumulator

Create **`server/app/reasoning_store.py`**:

- Define `ReasoningEntry` dataclass:
  ```python
  @dataclass
  class ReasoningEntry:
      timestamp: str          # ISO 8601
      event_type: str         # "tool_call", "compliance_check", "recommendation", "user_confirmation"
      tool_name: str          # e.g. "query_compliance_matrix", "search_far"
      reasoning: str          # Why this action was taken
      determination: str      # What was decided
      data: dict              # Supporting data (compliance result, search results, etc.)
      confidence: str         # "high", "medium", "low"
  ```

- Define `ReasoningLog` class:
  ```python
  class ReasoningLog:
      def __init__(self, session_id: str, tenant_id: str, user_id: str):
          self.session_id = session_id
          self.entries: list[ReasoningEntry] = []

      def add(self, event_type, tool_name, reasoning, determination, data=None, confidence="high"):
          """Append a reasoning entry."""

      def to_appendix_markdown(self) -> str:
          """Render as markdown appendix for document inclusion."""

      def to_json(self) -> list[dict]:
          """Serialize for DynamoDB/SSE."""

      def save(self):
          """Persist to DynamoDB as REASONING#{session_id}."""

      @classmethod
      def load(cls, session_id, tenant_id, user_id) -> "ReasoningLog":
          """Load from DynamoDB."""
  ```

- DynamoDB entity layout:
  ```
  PK: SESSION#{session_id}
  SK: REASONING#{session_id}
  reasoning_entries: JSON string of entries list
  updated_at: ISO timestamp
  ```

### 2. Add Reasoning Field to Tool Results

In **`server/app/agentic_service.py`**, modify key tool handlers to include a `reasoning` key:

- **`_handle_query_compliance_matrix()`** — Already returns structured compliance data. Add:
  ```python
  result["reasoning"] = {
      "action": "compliance_determination",
      "basis": f"Contract value ${value:,.0f} triggers {method} acquisition pathway",
      "documents_required": result["documents_required"],
      "key_thresholds": result.get("thresholds_triggered", []),
      "determination": f"{method} acquisition via {result.get('contract_type', 'TBD')}",
  }
  ```

- **`_handle_search_far()`** — Add:
  ```python
  result["reasoning"] = {
      "action": "regulatory_lookup",
      "query": query,
      "sections_found": len(results),
      "determination": f"Found {len(results)} relevant FAR sections for '{query}'",
  }
  ```

- **`_handle_create_document()`** — Add:
  ```python
  result["reasoning"] = {
      "action": "document_generation",
      "doc_type": doc_type,
      "basis": f"Generated {doc_type} based on intake context and compliance requirements",
      "inputs_used": list(content.keys()) if content else [],
  }
  ```

- **`_handle_dynamodb_intake()`** — Add reasoning for intake state changes.

### 3. Capture Reasoning in Stream Generator — SSE Pipeline Wiring

> **SSE Expert reference:** Part 3 (streaming_routes.py), Part 2 (result_queue emission patterns)
> Run `/experts:sse:question "How does stream_generator route tool_result chunks?"` if unsure.

In **`server/app/streaming_routes.py`** `stream_generator()`:

- Import and instantiate `ReasoningLog` at request entry:
  ```python
  from .reasoning_store import ReasoningLog
  reasoning_log = ReasoningLog(session_id or "", tenant_id, user_id)
  ```

- On `tool_result` chunks that contain a `reasoning` field, capture it AND emit a REASONING SSE event.
  **Important:** The reasoning data arrives inside the `tool_result` chunk (not as a separate chunk type),
  because factory tools push results via `result_queue` (SSE expertise Part 2, Pattern A/C).
  We extract reasoning from the result, accumulate it, and emit a separate REASONING event:

  ```python
  elif chunk_type == "tool_result":
      tr_name = chunk.get("name", "")
      if not tr_name:
          logger.debug("Skipping empty-name tool_result")
          continue
      result_data = chunk.get("result", {})

      # Standard tool_result emission (existing behavior)
      await writer.write_tool_result(sse_queue, tr_name, result_data)
      yield await sse_queue.get()

      # NEW: Extract and emit reasoning if present
      if isinstance(result_data, dict) and "reasoning" in result_data:
          reasoning_data = result_data["reasoning"]
          reasoning_log.add(
              event_type="tool_call",
              tool_name=tr_name,
              reasoning=reasoning_data.get("basis", ""),
              determination=reasoning_data.get("determination", ""),
              data=reasoning_data,
              confidence=reasoning_data.get("confidence", "high"),
          )
          # Emit REASONING SSE event (uses existing write_reasoning from stream_protocol.py)
          # This is a SEPARATE event from the tool_result — frontend handles both
          await writer.write_reasoning(sse_queue, json.dumps(reasoning_data))
          yield await sse_queue.get()
  ```

  **SSE wire format for reasoning event:**
  ```
  data: {"type":"reasoning","agent_id":"eagle","agent_name":"EAGLE Acquisition Assistant","reasoning":"{\"action\":\"compliance_determination\",\"basis\":\"$85K → simplified\",\"determination\":\"FAR 13.5\"}","timestamp":"2026-03-10T18:30:00+00:00"}
  ```

- On `complete`, persist the reasoning log (fire-and-forget):
  ```python
  # After persisting assistant message, before write_complete:
  if reasoning_log.entries:
      try:
          await asyncio.to_thread(reasoning_log.save)
      except Exception:
          logger.debug("reasoning_log save failed (non-fatal)")
  ```

- **No changes needed to `_drain_tool_results()` or `result_queue` plumbing** — reasoning flows
  as part of the existing tool_result payload. Extraction happens in `stream_generator()`, not
  in the Strands agent thread.

### 4. Modify Supervisor Prompt — Consultation-First Sequencing

In **`eagle-plugin/agents/supervisor/agent.md`**, add a new section after "CORE PHILOSOPHY":

```markdown
---

CONSULTATION-FIRST FLOW

Phase 1 — UNDERSTAND (consultation)
- Ask 2-3 short questions per turn. Never more.
- Each question fits on one line.
- Give a recommendation with each question: "I'd suggest X — does that work?"
- Capture their answer. Move to the next question.
- Do NOT generate documents during this phase.
- Call query_compliance_matrix after each substantive answer.

Phase 2 — CONFIRM (summary)
- When you have enough context, present a 5-line summary:
  "Here's what I have:
  - Requirement: [X]
  - Value: [$Y] → [FAR Part]
  - Timeline: [Z]
  - Documents needed: [list]
  Ready to generate the package?"
- Wait for user confirmation before proceeding.

Phase 3 — GENERATE (documents)
- Only after user confirms, generate documents.
- Generate one document at a time. Show a brief preview.
- Ask: "Good? Next document?" before continuing.
- Include AI reasoning appendix in each document.

CRITICAL: Do NOT skip Phase 1. The user's first message is the start of a
consultation, not a document request, unless they explicitly say "generate" or
"create" or "draft."

EXCEPTION: If user provides a complete quote/SOW/document attachment, skip to
Phase 2 (you already have the context).
```

### 5. Modify Supervisor Prompt — Response Length Rules

Replace the existing "COMMUNICATION EXAMPLES" section emphasis with:

```markdown
---

RESPONSE LENGTH RULES

- Maximum 3 sentences per response during consultation.
- Questions are one line each, max 2-3 per turn.
- Recommendations are one sentence: "I'd go with X because Y."
- Summaries are bulleted, max 8 lines.
- Only documents can be long.
- If your response is more than 5 lines and isn't a document, it's too long. Cut it.

FORMAT FOR CONSULTATION TURNS:
[1-sentence acknowledgment of what they said]
[1-sentence recommendation or determination]
[1-2 questions for next needed info]

EXAMPLE:
"Got it — $85K for bioinformatics services puts you in simplified acquisition (FAR 13.5).
I'd recommend a performance-based SOW with firm-fixed-price.
Is this IT/software? And do you have a preferred timeline?"
```

### 6. Add Reasoning Instruction to All Tool Schemas

In **`server/app/strands_agentic_service.py`**, modify the supervisor system prompt assembly (`build_supervisor_prompt()` or the tool instruction section) to include:

```markdown
REASONING REQUIREMENT FOR ALL TOOL CALLS:

Before calling any tool, state your reasoning in 1 sentence in the tool input.
After receiving a tool result, log the determination.

This reasoning is automatically captured and included in document appendices.
Users never see it inline — it's recorded silently for the audit trail.
```

### 7. Modify create_document to Include Reasoning Appendix

In **`server/app/agentic_service.py`**, in `_handle_create_document()`:

- Accept optional `reasoning_log` parameter
- Before returning the generated document content, append:

```python
def _append_reasoning_to_document(content: str, reasoning_entries: list[dict]) -> str:
    """Append AI reasoning appendix to generated document markdown."""
    if not reasoning_entries:
        return content

    appendix = "\n\n---\n\n## Appendix: AI Decision Rationale\n\n"
    appendix += "*This appendix documents the AI-assisted analysis and reasoning "
    appendix += "that informed this document. All determinations were made based on "
    appendix += "applicable FAR/HHSAR regulations and NCI acquisition policies.*\n\n"

    for i, entry in enumerate(reasoning_entries, 1):
        ts = entry.get("timestamp", "")
        time_str = ts[11:19] if len(ts) > 19 else ts  # HH:MM:SS
        appendix += f"### {i}. {entry.get('event_type', 'Analysis')} — {entry.get('tool_name', '')}\n"
        appendix += f"**Time:** {time_str}  \n"
        appendix += f"**Action:** {entry.get('reasoning', 'N/A')}  \n"
        appendix += f"**Determination:** {entry.get('determination', 'N/A')}  \n"
        if entry.get("confidence"):
            appendix += f"**Confidence:** {entry['confidence']}  \n"
        appendix += "\n"

    return content + appendix
```

- In the create_document handler, load the reasoning log for the session and append:

```python
# After generating document content:
try:
    from .reasoning_store import ReasoningLog
    log = ReasoningLog.load(session_id, tenant_id, user_id)
    if log and log.entries:
        content = _append_reasoning_to_document(content, log.to_json())
except Exception:
    pass  # Non-fatal — document still generated without appendix
```

### 8. Wire REASONING SSE Events into Frontend

In **`client/hooks/use-agent-stream.ts`**:

- Add handling for `reasoning` event type in the SSE parser:
  ```typescript
  case 'reasoning': {
    // Add to agent logs as a reasoning entry
    const reasoningData = parsed.reasoning || parsed.content;
    addLog({
      type: 'reasoning',
      agent: parsed.agent_name || 'eagle',
      content: reasoningData,
      timestamp: parsed.timestamp,
    });
    break;
  }
  ```

In **`client/components/chat-simple/agent-logs.tsx`**:

- Add rendering for `reasoning` log entries with a distinct visual style (light purple background, brain icon).

### 9. Modify oa-intake Skill for Shorter Responses

In **`eagle-plugin/skills/oa-intake/SKILL.md`**, add after the Philosophy section:

```markdown
## Response Format Rules

EVERY response during intake MUST follow this format:
1. One-line acknowledgment (what you understood)
2. One-line recommendation (what you'd suggest)
3. 1-2 questions (what you need next)

MAXIMUM: 4 lines per response during Phases 1-3.
NEVER explain regulations during intake unless user asks "why."
NEVER list options — recommend one and justify briefly.

WRONG: "There are several acquisition pathways we could consider. For services
in this value range, you could use simplified acquisition procedures under
FAR Part 13.5, which allows for streamlined documentation..."

RIGHT: "$85K services → simplified acquisition (FAR 13.5). Two questions:
Is this IT? When do you need it?"
```

### 10. Add Reasoning to query_compliance_matrix Results

In **`server/app/agentic_service.py`**, in the compliance matrix handler:

- After computing the compliance result, add a `reasoning` key that summarizes the determination chain:

```python
# Build reasoning chain from the computed result
reasoning_chain = []
if result.get("method"):
    reasoning_chain.append(f"Value ${value:,.0f} → {result['method']} acquisition")
if result.get("contract_type"):
    reasoning_chain.append(f"Contract type: {result['contract_type']}")
if result.get("competition_rules"):
    reasoning_chain.append(f"Competition: {result['competition_rules']}")
if result.get("set_aside"):
    reasoning_chain.append(f"Set-aside: {result['set_aside']}")

result["reasoning"] = {
    "action": "compliance_determination",
    "basis": "; ".join(reasoning_chain),
    "determination": f"{result.get('method', 'TBD')} via {result.get('contract_type', 'TBD')}",
    "thresholds_triggered": result.get("thresholds_triggered", []),
    "documents_required": result.get("documents_required", []),
    "confidence": "high",  # Deterministic rule engine
}
```

### 11. Write Tests

Create **`server/tests/test_reasoning_capture.py`**:

```python
"""Tests for reasoning capture, accumulation, and document appendix generation."""
import json
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime


class TestReasoningLog:
    """ReasoningLog accumulator unit tests."""

    def test_add_entry(self):
        from app.reasoning_store import ReasoningLog
        log = ReasoningLog("sess-1", "tenant-1", "user-1")
        log.add(
            event_type="compliance_check",
            tool_name="query_compliance_matrix",
            reasoning="Value $85K triggers simplified acquisition",
            determination="FAR 13.5 simplified",
            data={"method": "simplified"},
        )
        assert len(log.entries) == 1
        assert log.entries[0].tool_name == "query_compliance_matrix"

    def test_to_json(self):
        from app.reasoning_store import ReasoningLog
        log = ReasoningLog("sess-1", "tenant-1", "user-1")
        log.add("tool_call", "search_far", "Looking up FAR 13.5", "Found 3 sections")
        result = log.to_json()
        assert len(result) == 1
        assert result[0]["tool_name"] == "search_far"
        assert "timestamp" in result[0]

    def test_to_appendix_markdown(self):
        from app.reasoning_store import ReasoningLog
        log = ReasoningLog("sess-1", "tenant-1", "user-1")
        log.add("compliance_check", "query_compliance_matrix",
                "$85K → simplified", "FAR 13.5", confidence="high")
        log.add("document_generation", "create_document",
                "Generating SOW from intake", "SOW v1 created", confidence="high")

        md = log.to_appendix_markdown()
        assert "AI Decision Rationale" in md
        assert "compliance_check" in md
        assert "FAR 13.5" in md
        assert "SOW v1 created" in md

    def test_empty_log_no_appendix(self):
        from app.reasoning_store import ReasoningLog
        log = ReasoningLog("sess-1", "tenant-1", "user-1")
        md = log.to_appendix_markdown()
        assert md == "" or "Appendix" not in md

    @patch("app.reasoning_store._get_table")
    def test_save_to_dynamodb(self, mock_table):
        from app.reasoning_store import ReasoningLog
        mock_tbl = MagicMock()
        mock_table.return_value = mock_tbl

        log = ReasoningLog("sess-1", "tenant-1", "user-1")
        log.add("tool_call", "search_far", "test", "test result")
        log.save()

        mock_tbl.put_item.assert_called_once()
        item = mock_tbl.put_item.call_args.kwargs["Item"]
        assert item["PK"] == "SESSION#sess-1"
        assert item["SK"] == "REASONING#sess-1"

    @patch("app.reasoning_store._get_table")
    def test_load_from_dynamodb(self, mock_table):
        from app.reasoning_store import ReasoningLog
        mock_tbl = MagicMock()
        mock_tbl.get_item.return_value = {
            "Item": {
                "PK": "SESSION#sess-1",
                "SK": "REASONING#sess-1",
                "reasoning_entries": json.dumps([{
                    "timestamp": "2026-03-10T18:00:00Z",
                    "event_type": "tool_call",
                    "tool_name": "search_far",
                    "reasoning": "test",
                    "determination": "found",
                    "data": {},
                    "confidence": "high",
                }]),
            }
        }
        mock_table.return_value = mock_tbl

        log = ReasoningLog.load("sess-1", "tenant-1", "user-1")
        assert len(log.entries) == 1


class TestToolReasoningFields:
    """Verify tool handlers include reasoning in results."""

    def test_compliance_matrix_has_reasoning(self):
        """query_compliance_matrix result should include reasoning key."""
        from app.agentic_service import _handle_query_compliance_matrix
        # Mock the actual compliance computation
        with patch("app.agentic_service._compute_compliance") as mock:
            mock.return_value = {
                "method": "simplified",
                "contract_type": "FFP",
                "documents_required": ["SOW", "IGCE"],
                "competition_rules": "full_and_open",
            }
            result = _handle_query_compliance_matrix({
                "operation": "query",
                "contract_value": 85000,
            })
            assert "reasoning" in result
            assert result["reasoning"]["action"] == "compliance_determination"

    def test_create_document_has_reasoning(self):
        """create_document result should include reasoning key."""
        with patch("app.agentic_service._generate_sow") as mock:
            mock.return_value = "# SOW\nTest content"
            result = _handle_create_document({
                "doc_type": "sow",
                "title": "Test SOW",
                "content": {"description": "test"},
            })
            assert "reasoning" in result


class TestDocumentAppendix:
    """Verify reasoning appendix is injected into documents."""

    def test_appendix_added_to_document(self):
        from app.agentic_service import _append_reasoning_to_document
        content = "# SOW\n\nTest document content."
        entries = [{
            "timestamp": "2026-03-10T18:00:00Z",
            "event_type": "compliance_check",
            "tool_name": "query_compliance_matrix",
            "reasoning": "$85K triggers simplified",
            "determination": "FAR 13.5",
            "confidence": "high",
        }]
        result = _append_reasoning_to_document(content, entries)
        assert "Appendix: AI Decision Rationale" in result
        assert "FAR 13.5" in result
        assert content in result

    def test_empty_entries_no_appendix(self):
        from app.agentic_service import _append_reasoning_to_document
        content = "# SOW\nTest."
        result = _append_reasoning_to_document(content, [])
        assert result == content
```

### 12. Validate Everything

Run validation in order:

1. **Syntax check new module:**
   ```bash
   cd server && python -c "from app.reasoning_store import ReasoningLog, ReasoningEntry; print('OK')"
   ```

2. **Lint:**
   ```bash
   cd server && ruff check app/
   ```

3. **Unit tests:**
   ```bash
   cd server && python -m pytest tests/test_reasoning_capture.py -v
   ```

4. **Existing tests still pass:**
   ```bash
   cd server && python -m pytest tests/test_new_endpoints.py tests/test_feedback_store.py -v
   ```

5. **Frontend type check:**
   ```bash
   cd client && npx tsc --noEmit
   ```

6. **Manual smoke test:**
   - Start backend + frontend
   - Open EAGLE chat, start an intake conversation
   - Verify: responses are 2-3 sentences, questions are short
   - Verify: agent logs show reasoning entries
   - Generate a document → verify appendix section exists

## Testing Strategy

| Test | Type | Validates |
|------|------|-----------|
| `test_add_entry` | Unit | ReasoningLog accumulation |
| `test_to_json` | Unit | Serialization with timestamps |
| `test_to_appendix_markdown` | Unit | Appendix rendering format |
| `test_empty_log_no_appendix` | Unit | Edge case — no entries |
| `test_save_to_dynamodb` | Unit | DynamoDB persistence (mocked) |
| `test_load_from_dynamodb` | Unit | DynamoDB load (mocked) |
| `test_compliance_matrix_has_reasoning` | Integration | Tool handler returns reasoning |
| `test_create_document_has_reasoning` | Integration | Document tool returns reasoning |
| `test_appendix_added_to_document` | Unit | Appendix injection into markdown |
| `test_empty_entries_no_appendix` | Unit | No appendix when no entries |

**Edge cases covered:**
- Empty reasoning log → no appendix added
- Tool handler failure → reasoning capture is non-fatal
- Session without reasoning → documents still generate normally
- Very long reasoning entries → truncated in appendix

## Acceptance Criteria

- [ ] Supervisor prompt enforces Phase 1 (consultation) → Phase 2 (confirm) → Phase 3 (generate)
- [ ] Responses during consultation are max 3 sentences + 2 questions
- [ ] `query_compliance_matrix` result includes `reasoning` field
- [ ] `create_document` result includes `reasoning` field
- [ ] `search_far` result includes `reasoning` field
- [ ] `ReasoningLog` accumulates entries per session
- [ ] `ReasoningLog.save()` persists to DynamoDB as `REASONING#{session_id}`
- [ ] `ReasoningLog.to_appendix_markdown()` produces formatted appendix
- [ ] Generated documents include "Appendix: AI Decision Rationale" when reasoning exists
- [ ] `StreamEventType.REASONING` events are emitted via SSE
- [ ] Frontend agent logs display reasoning entries
- [ ] All unit tests pass
- [ ] `ruff check app/` passes
- [ ] `npx tsc --noEmit` passes
- [ ] Existing tests (feedback, endpoints) still pass

## Validation Commands

```bash
# L1 — Lint
cd server && ruff check app/

# L1 — Import check
cd server && python -c "from app.reasoning_store import ReasoningLog, ReasoningEntry; print('OK')"

# L1 — TypeScript
cd client && npx tsc --noEmit

# L2 — Reasoning tests
cd server && python -m pytest tests/test_reasoning_capture.py -v

# L2 — Existing tests unbroken
cd server && python -m pytest tests/test_new_endpoints.py tests/test_feedback_store.py -v

# L3 — E2E (manual)
# 1. Start backend: cd server && uvicorn app.main:app --reload --port 8000
# 2. Start frontend: cd client && npm run dev
# 3. Open http://localhost:3000/chat
# 4. Send: "I need to buy a microscope for about $85K"
# 5. Verify: response is 2-3 sentences with 1-2 questions
# 6. Continue consultation, then request document generation
# 7. Verify: document includes AI reasoning appendix
# 8. Check agent logs tab for reasoning entries
```

## Notes

### Relationship to CloudWatch Plan
This plan complements `20260310-180000-plan-cloudwatch-telemetry-wiring-v1.md`. The reasoning events emitted here can also be pushed to CloudWatch via `emit_telemetry_event()` for observability. The two plans can be built independently — reasoning capture works without CloudWatch, and CloudWatch works without reasoning capture.

### Prompt Change Risk
Modifying the supervisor prompt changes agent behavior globally. To mitigate:
- Make changes additive (new sections, not replacing existing ones)
- Test with 3-5 representative scenarios before merging
- The existing "DEFAULT TO ACTION" section should be softened, not removed — it's good for document-first users who explicitly say "generate"

### Progressive Disclosure Integration
The 4-layer progressive disclosure system (list_skills → load_skill → load_data → query_compliance_matrix) already supports consultation-first flow. The reasoning capture adds a 5th dimension: every layer's output gets a reasoning annotation.

### Existing REASONING Infrastructure
`StreamEventType.REASONING` and `write_reasoning()` already exist in `stream_protocol.py`. We're activating unused infrastructure, not building new streaming plumbing.

### DynamoDB Cost
Reasoning entries are ~500 bytes each. A typical intake consultation produces 5-15 entries. At 1000 sessions/month, that's ~7.5MB/month — negligible DynamoDB cost.

### Backward Compatibility
- Documents generated without reasoning log → no appendix (graceful degradation)
- Old sessions without reasoning entries → load returns empty log
- Frontend without reasoning handler → events are ignored (SSE parser skips unknown types)
