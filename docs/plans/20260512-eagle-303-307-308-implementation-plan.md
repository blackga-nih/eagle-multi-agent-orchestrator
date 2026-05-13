# EAGLE-303, EAGLE-307, EAGLE-308 Implementation Plan

Date: 2026-05-12

## Scope

This plan covers three unresolved demo-script UI/output issues:

- EAGLE-303: Text in a markdown table displays with literal double asterisks around the text.
- EAGLE-307: Response text is cut off or visually crowded by the Web Search chip.
- EAGLE-308: Sources Summary is repeated after follow-up responses and document counts keep increasing across "Yes" / "Approve" follow-ups.

The goal is not just to close the Jira tickets. The fix should make the demo output stable: no raw markdown emphasis markers in tables, no chip/text collision, and no repeated source-summary card for follow-up turns that are continuing the same package workflow.

## Current Findings

### EAGLE-303

Jira status: `To Do`

Ticket text: "Text in the table has double * around the text."

Current code evidence:

- `client/components/chat-simple/simple-message-list.tsx` renders assistant responses with `ReactMarkdown` and `remarkGfm`.
- `client/components/chat-simple/simple-message-list.tsx` includes table component overrides, but it does not sanitize table cell content beyond normal markdown parsing.
- `client/components/ui/markdown-renderer.tsx` has `sanitizeTables`, but that function only removes malformed/empty table rows and separator issues. It does not normalize escaped emphasis markers, double-wrapped emphasis, or model-emitted literal `**...**` in table cells.

Likely root cause:

The renderer can correctly render valid markdown bold in GFM tables. The issue probably happens when the model produces malformed table content, escaped asterisks, nested emphasis, or content that is treated as plain text in a table-like block. Because the current table sanitizer is limited, the UI has no defense against raw emphasis markers in table cells.

### EAGLE-307

Jira status: `To Do`

Ticket text: "Text got cut off by Web search cube."

Current code evidence:

- `client/components/chat-simple/simple-message-list.tsx` interleaves text, tool chips, state-change cards, and thinking chips into shared chip rows.
- Tool chips render through `client/components/chat-simple/tool-use-display.tsx`.
- `ToolUseDisplay` uses an inline-flex rounded chip with `whitespace-nowrap` on the label.
- `StateChangeCard` uses `max-w-xs` and truncated text.
- `WebSearchPanel` uses `line-clamp-3` and truncates answer preview to 200 characters, which is fine inside the modal/panel, but the reported issue is about the visible Web Search chip crowding or cutting off adjacent response text.
- Commit `a8ab7e4` widened the chat layout from `max-w-3xl` to `max-w-5xl`, but that is not a targeted fix for chip/text layout.

Likely root cause:

Inline tool chips are being placed too close to streamed text, especially when a tool event lands at the same or near-same `textSnapshotLength` as response text. The chip row is visually compact, but Web Search still takes horizontal space and may overlap/crowd text depending on viewport width and stream ordering. Widening the chat column reduces the probability but does not fix the layout contract.

### EAGLE-308

Jira status: `To Do`

Ticket text:

- Display Sources Summary once after the original prompt.
- Do not display it again for follow-up questions/responses to the original response.
- Source Summary counts increased from 11 docs to 14 docs to 18 docs across original prompt, "Yes", and "Approve".

Current code evidence:

- `server/app/strands_agentic_service.py` emits a `sources_summary` state update at the end of every turn where `kb_depth.fetch_count > 0`.
- `client/lib/chat-stream-manager.ts` stores every `sources_summary` event as a state-change entry for the current streaming message.
- `client/components/chat-simple/simple-message-list.tsx` renders every message's state changes, including `sources_summary`.
- `client/components/chat-simple/activity-panel.tsx` deduplicates individual source rows across the side panel, but that does not suppress repeated inline Sources Summary cards across follow-up messages.

Likely root cause:

`sources_summary` is turn-scoped, not workflow-scoped. Follow-up turns that perform KB reads emit another summary, and the inline chat shows each one. The backend also appears to aggregate per-turn KB depth in a way that can make counts increase during package approval follow-ups, which conflicts with the intended demo behavior.

## Desired Behavior

### EAGLE-303 Acceptance Criteria

- Markdown tables should not show literal `**` around ordinary emphasized table cell text.
- Valid bold markdown inside tables should still render as bold.
- Code spans containing asterisks should remain unchanged.
- Non-table prose should not be broadly rewritten unless needed.
- Add a regression test with a table containing common problematic patterns.

### EAGLE-307 Acceptance Criteria

- The Web Search chip must never obscure, overlap, or cut off response text.
- Tool chips should render on their own row with predictable spacing from text before and after.
- On narrow viewports, chips should wrap or truncate internally without affecting adjacent text.
- Add a frontend regression test covering a message with interleaved Web Search chip and adjacent text.

### EAGLE-308 Acceptance Criteria

- First response shows `## Sources` with templates filtered out.
- Follow-up turns with no new sources show NO sources section at all.
- Follow-up turns that fetch new sources show `## Additional Sources` with only the new ones.
- Template files (`approved/templates/*`) are never shown in the sources section.
- Agent files, FAR guidance, checklists, and other reference docs remain visible.
- Track `surfaced_source_keys` per session to compute what's "new."
- Add tests for incremental source tracking and template filtering.

## Implementation Plan

## 1. Fix EAGLE-303: Normalize Table Cell Emphasis

Primary files:

- `client/components/ui/markdown-renderer.tsx`
- `client/components/chat-simple/simple-message-list.tsx`
- New or existing frontend tests under `client/tests`

Steps:

1. Create a shared markdown normalization helper.
   - Move table sanitation out of `markdown-renderer.tsx` into a reusable helper, for example `client/lib/markdown-normalization.ts`.
   - Use this helper in both `MarkdownRenderer` and the chat message renderer.
   - This avoids fixing document preview markdown while leaving chat markdown unfixed.

2. Extend table sanitation to normalize table-cell emphasis safely.
   - Only operate on GFM pipe-table blocks.
   - Split rows into cells while preserving escaped pipes as much as practical.
   - For each non-code cell, normalize common raw emphasis problems:
     - `\\**text\\**` -> `**text**`
     - `****text****` -> `**text**`
     - plain visible wrapper markers caused by doubled output -> convert to valid markdown or strip if it cannot be parsed reliably.
   - Do not alter inline code spans, fenced code blocks, or JSON/code-like values.

3. Ensure chat uses the same sanitizer.
   - In `simple-message-list.tsx`, pass message content through the helper before `ReactMarkdown`.
   - Keep `remarkGfm` enabled.

4. Add regression tests.
   - Add a frontend test for a rendered table cell containing `**Critical**`.
   - Add a case for escaped asterisks that previously rendered literally.
   - Assert visible text does not include raw `**Critical**`.
   - Assert valid bold text still appears as visible text and is inside a `strong` element where feasible.

5. Manual validation.
   - Reproduce the original demo response shape with a table.
   - Confirm the table is still a table, not a paragraph.
   - Confirm raw asterisks are not visible around normal cell text.

## 2. Fix EAGLE-307: Make Tool Chips Layout-Safe

Primary files:

- `client/components/chat-simple/simple-message-list.tsx`
- `client/components/chat-simple/tool-use-display.tsx`
- `client/components/chat-simple/state-change-card.tsx`
- `client/tests/tool-result-panels.spec.ts` or a focused new Playwright spec

Steps:

1. Strengthen the interleaving layout contract.
   - Ensure text slices and chip rows are always block-level siblings.
   - Add vertical spacing before and after chip groups so a chip cannot visually sit on top of text.
   - Keep `flushChips()` behavior, but review same-snapshot events and force chip rows to stand alone around Web Search.

2. Make tool chips shrink safely.
   - Add `max-w-full min-w-0` to the chip button.
   - Replace unbounded `whitespace-nowrap` behavior with a constrained label span.
   - Keep the label readable, but allow ellipsis inside the chip instead of forcing the chip to occupy too much horizontal space.

3. Treat Web Search as a compact chip by default.
   - The visible chip should show icon + `Web Search` + status only.
   - Query details should live in the modal, not the inline row.
   - Keep any long query or URL out of the visible chip row.

4. Review state-change card sizing.
   - `StateChangeCard` currently uses `max-w-xs` and multiple truncated spans.
   - Keep it compact, but add `min-w-0` and make summary truncation local to the card.
   - Confirm state cards and tool chips wrap as units.

5. Add a visual/layout regression test.
   - Build a test fixture or use Playwright to create a chat message with text before and after a Web Search chip.
   - Assert the text bounding box does not overlap the Web Search chip bounding box.
   - Run at desktop and a narrow/mobile viewport.

6. Manual validation.
   - Run the demo prompt that triggers Web Search.
   - Check streamed state and final state.
   - Confirm no text is hidden, overlapped, or visually cut off near the Web Search chip.

## 3. Fix EAGLE-308: Clean Up Response Sources Section

Primary files:

- `server/app/strands_agentic_service.py`:
  - `_append_kb_sources()` (~line 676) — builds the `## Sources` markdown section
  - End-of-turn logic (~line 8579) — calls `_append_kb_sources()`
- `server/app/session_store.py` or session context — track surfaced keys per session
- Existing source-summary tests under `server/tests/test_knowledge_search_serialization.py`

### Problem

The `## Sources` bullet list appended to assistant responses has two issues:

1. **Includes templates** — Files from `approved/templates/` (e.g., IGCE xlsx, SOW docx) are document generation tooling, not research sources. They clutter the sources list.

2. **Repeats on every turn** — Follow-up responses ("Yes", "Approve") re-list ALL sources, making the list grow repetitively even when no new research was done.

### Desired Behavior

| Turn | Sources Section |
|------|-----------------|
| First response | `## Sources` with filtered list (no templates) |
| Follow-up with NO new sources | No sources section at all |
| Follow-up WITH new sources | `## Additional Sources` with only the new ones |

### Implementation

1. **Filter template paths** from the sources list.
   ```python
   def _is_template_source(s3_key: str) -> bool:
       """Templates are doc-generation tooling, not research sources."""
       return "approved/templates/" in s3_key or "/templates/" in s3_key
   ```

2. **Track surfaced sources per session.**
   - Add `surfaced_source_keys: set[str]` to session context.
   - Persist across turns within the same session.

3. **Update `_append_kb_sources()` with incremental logic.**
   ```python
   def _append_kb_sources(
       text: str,
       kb_depth: dict,
       surfaced_keys: set[str] | None = None,
   ) -> tuple[str, set[str]]:
       """Append sources section, returning (text, keys_shown)."""
       fetched = kb_depth.get("fetched_keys", set())
       if not fetched:
           return text, set()
       
       # Filter out templates
       visible_keys = {k for k in fetched if not _is_template_source(k)}
       
       # Compute new sources (not yet surfaced this session)
       already_shown = surfaced_keys or set()
       new_keys = visible_keys - already_shown
       
       if not new_keys:
           return text, set()  # No new visible sources — no section
       
       # Use "Additional Sources" header for follow-ups
       is_followup = len(already_shown) > 0
       header = "## Additional Sources" if is_followup else "## Sources"
       
       # Build section
       ordered = sorted(new_keys)
       lines = [_format_source_line(k) for k in ordered]
       result = text.rstrip() + f"\n\n{header}\n" + "\n".join(lines) + "\n"
       
       return result, new_keys
   ```

4. **Update call site** (~line 8579).
   ```python
   # Before complete event
   final_text, newly_surfaced = _append_kb_sources(
       final_text,
       kb_depth,
       surfaced_keys=session_ctx.get("surfaced_source_keys", set()),
   )
   # Update session context for next turn
   if newly_surfaced:
       session_ctx["surfaced_source_keys"] = (
           session_ctx.get("surfaced_source_keys", set()) | newly_surfaced
       )
   ```

### What Gets Filtered

| Path Pattern | Example | Shown? | Reason |
|--------------|---------|--------|--------|
| `approved/templates/*` | `01.D_IGCE_for_Commercial_Organizations.xlsx` | No | Doc generation tooling |
| `approved/agents/*` | `00-supervisor.txt`, `03-tech.txt` | Yes | Keep for now |
| `approved/compliance-strategist/FAR-guidance/*` | `FAR_Part_16_Contract_Types...` | Yes | Actual reference |
| `approved/compliance-strategist/PMR-checklists/*` | `HHS_PMR_BPA_Checklist.txt` | Yes | Actual reference |

### Tests

5. Add backend tests.
   - Test that `approved/templates/*` paths are excluded from `## Sources`.
   - Test that agent files, FAR guidance, checklists are included.
   - Test that follow-up turns with no new sources produce no sources section.
   - Test that follow-up turns with new sources use `## Additional Sources` header.
   - Test that `surfaced_source_keys` persists across turns in same session.

6. Manual validation.
   - Run the AIP demo prompt.
   - Confirm `## Sources` does NOT include template files.
   - Confirm `## Sources` DOES include agent files, FAR guidance, checklists.
   - Reply "Yes".
   - Confirm NO sources section appears in the response.
   - Reply "Also check subcontracting plan requirements" (triggers new KB fetch).
   - Confirm `## Additional Sources` appears with ONLY the new sources.

## Suggested Work Order

1. EAGLE-307 first.
   - Lowest risk and gives immediate UI stability around chips.
   - The test can catch future overlap regressions.

2. EAGLE-308 second.
   - Highest demo impact and clearest behavior mismatch.
   - Needs careful session/workflow semantics.

3. EAGLE-303 third.
   - Requires more caution because markdown sanitation can accidentally alter valid content.
   - Keep the sanitizer narrow and table-scoped.

## Test Plan

Run targeted checks first:

```bash
cd client
npm test -- --runInBand
```

If the project uses Playwright for these UI tests:

```bash
cd client
npx playwright test client/tests/tool-result-panels.spec.ts
npx playwright test client/tests/streaming-persistence.spec.ts
```

Run backend tests for source-summary serialization:

```bash
cd server
pytest server/tests/test_knowledge_search_serialization.py
```

Run any narrower changed-file tests added for this work before broad suites.

## Completion Checklist

- EAGLE-303 has a table-specific markdown normalization fix.
- EAGLE-303 has a regression test proving raw `**` does not display in table cells.
- EAGLE-307 tool chips are layout-safe at desktop and narrow viewport widths.
- EAGLE-307 has a regression test proving Web Search chip does not overlap/cut off text.
- EAGLE-308 templates are filtered from the `## Sources` section.
- EAGLE-308 follow-up turns with no new sources show no sources section.
- EAGLE-308 follow-up turns with new sources show `## Additional Sources` with only new ones.
- EAGLE-308 has tests for incremental source tracking and template filtering.
- Jira tickets are updated with implementation notes and validation evidence after the fix is merged.
