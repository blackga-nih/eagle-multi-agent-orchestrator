---
description: Send a test message in EAGLE chat, verify exactly one complete response, detect streaming issues
argument-hint: [url]
---

# EAGLE Chat Streaming Test

Send a single test message in the EAGLE chat and verify that exactly one coherent EAGLE response appears, streaming completes cleanly, and the UI returns to ready state.

## Variables

| Variable | Value | Description |
| -------- | ----- | ----------- |
| SKILL | `claude-bowser` | Uses your real Chrome |
| MODE | `headed` | Visible browser |
| URL | `{PROMPT}` or `http://localhost:3000` | Base URL |

If {PROMPT} contains a URL use it, otherwise default to `http://localhost:3000`.

## Workflow

### Phase 1: Load Chat Page

1. Navigate to `{URL}/chat`
2. Wait up to 10 seconds for the page to finish loading
3. Take a screenshot — save as `chat-initial.png`
4. Verify the chat interface loaded. Look for:
   - A text input box (placeholder text: "Message EAGLE..." or similar)
   - The EAGLE Chat header
   - A backend status indicator (green "Multi-Agent Online" or similar)
5. If the page shows "Backend Offline" in the status indicator, report **FAIL — Backend not running** and stop
6. If you see a login form instead of the chat, navigate to `{URL}` first and attempt to proceed (dev mode should auto-authenticate)

### Phase 2: Clear Any Existing Messages

7. Check if there are any existing messages in the chat area
8. If there are existing messages, look for a "New Chat" or session selector button in the sidebar and click it to start fresh
   - If no such button exists, proceed with existing state (note it in the report)

### Phase 3: Send Test Message

9. Click the chat input box to focus it
10. Type the message: `Hello, are you the EAGLE acquisition assistant? Please respond briefly.`
11. Take a screenshot before sending — save as `chat-before-send.png`
12. Press Enter or click the Send button
13. Note the exact time the message was sent

### Phase 4: Wait for Response and Monitor Streaming

14. Watch for the streaming indicator. You should see:
    - The status badge change to "Streaming..." or similar pulsing indicator
    - The input box become disabled / placeholder changes to "Waiting for response..."
15. Wait up to 45 seconds for the response to complete
16. Look for the streaming indicator to disappear (return to "Ready" state)
17. Take a screenshot during streaming (if visible) — save as `chat-streaming.png`

### Phase 5: Validate Response

18. Take a final screenshot — save as `chat-response.png`
19. Count the number of assistant message bubbles in the chat area (NOT counting the user's message)
20. Check for:
    - **Message count**: There should be exactly 1 assistant response bubble (not 0, not 2+)
    - **Empty messages**: No blank/empty message bubbles should be visible
    - **Content**: The response should contain coherent text acknowledging it is the EAGLE acquisition assistant
    - **Streaming complete**: The status indicator should show "Ready" (not "Streaming...")
    - **Input enabled**: The chat input box should be re-enabled and no longer disabled

### Phase 6: Report Results

Report **PASS** or **FAIL** for each check:

| Check | Expected | Actual | Result |
|-------|----------|--------|--------|
| Page loaded | Chat UI visible | | |
| Backend status | Online/connected | | |
| Message sent | User message appeared | | |
| Streaming started | Streaming indicator appeared | | |
| Streaming completed | Returned to Ready state | | |
| Response count | Exactly 1 assistant message | | |
| Empty messages | None | | |
| Response content | Coherent EAGLE response | | |
| Input re-enabled | Yes | | |

**Overall result**: PASS only if ALL checks pass.

If any check fails, include:
- The actual number of assistant messages found
- The content of any unexpected messages (empty or duplicate)
- Whether the streaming indicator got stuck
- Any error messages visible in the UI
- Console errors (if accessible)
