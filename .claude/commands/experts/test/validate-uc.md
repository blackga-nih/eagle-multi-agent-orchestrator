---
description: "Validate a use case end-to-end with agent-browser — send the UC scenario, verify specialist routing, tool calls, response quality, and take screenshots"
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Agent
argument-hint: [UC number/description and optional URL, e.g. "UC-02 micro-purchase" or "intake CT scanner http://localhost:3000"]
---

# Test Expert - Validate Use Case (agent-browser)

> Run a use case through the live EAGLE UI with agent-browser, verify every step visually, and produce a validation report with screenshots.

## Purpose

Unlike `use-case-builder` (which scaffolds test files across 4 suites), this command **executes** a use case against the running app using `agent-browser`. It validates:
- Chat UI loads and accepts input
- The UC scenario prompt triggers the correct specialist(s)
- Tool calls appear in the activity panel and/or chat
- Tool results render as formatted content (not raw JSON)
- The final response is acquisition-relevant and complete
- Session persists after the exchange

## Variables

- `UC`: $ARGUMENTS (UC number/description, optionally followed by a URL)
- `URL`: Extract URL from $ARGUMENTS if present, otherwise `http://localhost:3000`

## Instructions

- **CRITICAL**: This is a live validation — the backend MUST be running.
- Parse `$ARGUMENTS` for a UC identifier and optional URL.
- If no UC is provided, STOP and ask the user which use case to validate.

---

## Workflow

### Phase 0: Resolve the Use Case

1. Identify the UC from `$ARGUMENTS`:
   - If it's a UC number (e.g., `UC-02`), look up the scenario in:
     ```
     .claude/specs/uc-test-registry.md
     ```
   - If it's a description (e.g., "intake CT scanner"), use it directly as the prompt.

2. Determine the **expected behavior**:
   - Which specialist agent(s) should be invoked?
   - Which tools should be called?
   - What keywords should appear in the response?
   - Should documents be generated?

3. Determine the URL (default `http://localhost:3000`).

---

### Phase 1: Verify Backend is Running

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/api/health
```

If not 200, report **FAIL — Backend not running** and stop.

---

### Phase 2: Open Chat and Prepare

```bash
agent-browser open {URL}/chat
agent-browser wait --load networkidle
agent-browser screenshot screenshots/uc-validate-initial.png
```

1. Verify the chat interface loaded (input box, header, sidebar).
2. Click "New Chat" if existing messages are present — start fresh.
3. Snapshot interactive elements:
   ```bash
   agent-browser snapshot -i
   ```

---

### Phase 3: Send the UC Scenario

1. Construct the prompt based on the UC. Examples:

   | UC | Prompt |
   |----|--------|
   | UC-01 Intake | "I need to start a new acquisition for a CT scanner, estimated value $250,000, needed within 6 months." |
   | UC-02 Micro-purchase | "I need to buy lab supplies under $10,000. What's the fastest procurement method?" |
   | UC-03 SOW generation | "Generate a Statement of Work for a 12-month IT support services contract valued at $500,000." |
   | UC-04 FAR search | "What are the competition requirements under FAR Part 6 for a sole-source justification?" |
   | UC-05 Cost estimate | "Create an Independent Government Cost Estimate for a $2M bioinformatics platform." |
   | Custom | Use the description from $ARGUMENTS directly |

2. Send the message:
   ```bash
   agent-browser fill @{input-ref} "{prompt}"
   agent-browser screenshot screenshots/uc-validate-before-send.png
   agent-browser click @{send-ref}
   ```

---

### Phase 4: Monitor Streaming

1. Wait for streaming to start:
   ```bash
   agent-browser wait 2000
   agent-browser screenshot screenshots/uc-validate-streaming.png
   ```

2. Check for activity panel updates:
   ```bash
   agent-browser snapshot -i
   ```
   - Look for tool use cards (thinking, specialist delegation, search_far, etc.)
   - Look for agent log entries in the Activity tab

3. Wait for response to complete (up to 60 seconds):
   ```bash
   agent-browser wait 60000
   ```
   Or poll for the input to become re-enabled:
   ```bash
   agent-browser wait --text "Message EAGLE"
   ```

4. Take a screenshot after completion:
   ```bash
   agent-browser screenshot screenshots/uc-validate-response.png
   ```

---

### Phase 5: Validate Response Quality

1. **Message count**: Exactly 1 assistant response (no duplicates, no empty bubbles)
   ```bash
   agent-browser eval "document.querySelectorAll('[class*=\"assistant\"]').length"
   ```

2. **Content check**: Response contains UC-relevant keywords
   ```bash
   agent-browser get text ".msg-bubble"
   ```
   Verify the response mentions expected terms (acquisition, FAR, contract type, etc.).

3. **Tool cards in chat**: If tools were called, verify tool use cards rendered
   ```bash
   agent-browser get count "[data-tool-card]"
   ```

4. **Tool result quality**: Open a tool card accordion and verify content is formatted (not raw JSON)
   ```bash
   agent-browser snapshot -s "[data-tool-card]" -i
   ```

5. **No errors**: Check for error banners or red text
   ```bash
   agent-browser get count ".text-red-500"
   agent-browser get count "[role='alert']"
   ```

6. **Input re-enabled**: Chat input accepts new messages
   ```bash
   agent-browser is enabled @{input-ref}
   ```

---

### Phase 6: Validate Activity Panel (if visible)

1. Check the Activity panel tab:
   ```bash
   agent-browser snapshot -s "[data-panel='activity']" -i
   ```

2. Verify:
   - Agent log entries show specialist routing (e.g., "Delegated to far_specialist")
   - Tool use entries show tool names and status (pending → done)
   - Telemetry shows token counts and duration

3. Screenshot the activity panel:
   ```bash
   agent-browser screenshot screenshots/uc-validate-activity.png
   ```

---

### Phase 7: Session Persistence Check

1. Note the session in the sidebar.
2. Reload the page:
   ```bash
   agent-browser reload
   agent-browser wait --load networkidle
   ```
3. Verify messages survive reload:
   ```bash
   agent-browser screenshot screenshots/uc-validate-reload.png
   ```

---

### Phase 8: Follow-up (Optional)

If the UC involves multi-turn interaction:

1. Send a follow-up message related to the UC scenario.
2. Verify EAGLE remembers context from the first message.
3. Screenshot:
   ```bash
   agent-browser screenshot screenshots/uc-validate-followup.png
   ```

---

### Phase 9: Cleanup

```bash
agent-browser close
```

---

## Report Format

```markdown
## UC Validation Report: {UC identifier}

**URL:** {URL}
**Date:** {date}
**Scenario:** {prompt sent}

### Expected Behavior

| Aspect | Expected |
|--------|----------|
| Specialist(s) | {agent names} |
| Tools called | {tool names} |
| Response keywords | {keywords} |
| Documents generated | {yes/no} |

### Validation Results

| # | Check | Expected | Actual | Status |
|---|-------|----------|--------|--------|
| 1 | Chat page loaded | UI visible | | PASS/FAIL |
| 2 | Message sent | User bubble appears | | PASS/FAIL |
| 3 | Streaming started | Indicator visible | | PASS/FAIL |
| 4 | Response received | 1 assistant message | | PASS/FAIL |
| 5 | Response quality | UC-relevant content | | PASS/FAIL |
| 6 | Tool cards in chat | Visible (if tools called) | | PASS/FAIL/N/A |
| 7 | Tool results formatted | Not raw JSON | | PASS/FAIL/N/A |
| 8 | Activity panel | Agent logs + tool entries | | PASS/FAIL/N/A |
| 9 | No errors | No red text or alerts | | PASS/FAIL |
| 10 | Input re-enabled | Accepts new input | | PASS/FAIL |
| 11 | Session persists | Messages survive reload | | PASS/FAIL |

**Overall:** PASS / FAIL ({N}/11 checks passed)

### Screenshots

| Step | File |
|------|------|
| Initial | screenshots/uc-validate-initial.png |
| Before send | screenshots/uc-validate-before-send.png |
| Streaming | screenshots/uc-validate-streaming.png |
| Response | screenshots/uc-validate-response.png |
| Activity | screenshots/uc-validate-activity.png |
| Reload | screenshots/uc-validate-reload.png |

### Issues Found
{list any failures with details}
```

---

## Instructions

1. **Backend must be running** — this is live validation, not mocked
2. **Always start with New Chat** — isolate the UC from previous conversations
3. **Screenshot every phase** — visual evidence is the point
4. **Wait generously** — LLM responses can take 30-60s
5. **Check tool rendering** — raw JSON in tool results = FAIL
6. **Close browser when done** — `agent-browser close`
