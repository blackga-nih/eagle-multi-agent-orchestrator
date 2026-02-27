---
description: Test the EAGLE OA intake journey — quick action buttons, chat-driven acquisition intake, session persistence
argument-hint: [url]
---

# EAGLE OA Intake Journey Test

Test the full Office of Acquisitions intake flow: quick action buttons pre-fill the textarea, intake message is sent, EAGLE responds with acquisition questions, session is saved and persists on reload.

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
2. Wait up to 10 seconds for the page to load
3. Take a screenshot — save as `intake-initial.png`
4. Verify the chat page loaded. Look for:
   - The welcome screen ("Welcome to EAGLE") OR an existing chat session
   - 5 quick action buttons at the top (🆕 New Intake, 📄 Generate SOW, 📚 Search FAR, 💰 Cost Estimate, 🏢 Small Business)
   - The chat textarea input at the bottom
5. If a login page appears, report **FAIL — Not authenticated** and stop
6. If there are existing messages, click "New Chat" in the sidebar to start fresh

### Phase 2: Verify Quick Action Buttons

7. Confirm all 5 quick action buttons are visible and clickable:
   - `🆕 New Intake`
   - `📄 Generate SOW`
   - `📚 Search FAR`
   - `💰 Cost Estimate`
   - `🏢 Small Business`
8. Take a screenshot — save as `intake-quick-actions.png`

### Phase 3: Trigger Intake via Quick Action

9. Click the `🆕 New Intake` button
10. Verify the textarea is now pre-filled with an intake prompt (should contain text about starting an acquisition intake for a CT scanner)
11. Take a screenshot — save as `intake-prefilled.png`
12. Verify the Send button is now enabled (not greyed out)

### Phase 4: Send the Intake Message

13. Press Enter or click the Send button to submit the intake message
14. Verify the user message appears in a bubble on the right side of the chat
15. Verify the textarea clears and becomes disabled with placeholder "Waiting for response…"
16. Take a screenshot during streaming — save as `intake-streaming.png`

### Phase 5: Wait for EAGLE Response

17. Wait up to 45 seconds for EAGLE to respond
18. Watch for the 🦅 EAGLE response bubble to appear on the left side
19. Wait until the input textarea becomes re-enabled ("Ask EAGLE about acquisitions..." placeholder returns)
20. Take a screenshot — save as `intake-response.png`

### Phase 6: Validate Intake Response

21. Count the number of EAGLE (assistant) message bubbles — expect exactly 1
22. Read the response content. It should:
   - Acknowledge the acquisition request (CT scanner or medical equipment)
   - Ask follow-up questions OR provide guidance about the intake process
   - Reference acquisition concepts (contract type, estimated value, timeline, etc.)
   - NOT be empty or contain only an error message
23. Verify no empty/blank message bubbles exist
24. Verify the sidebar session list updated (shows this session with message count ≥ 2)

### Phase 7: Test a Follow-up Message

25. Click the textarea to focus it
26. Type: `The estimated value is $250,000 and we need it within 6 months.`
27. Press Enter to send
28. Wait up to 45 seconds for the second EAGLE response
29. Take a screenshot — save as `intake-followup.png`
30. Verify a second EAGLE response bubble appears with relevant acquisition guidance

### Phase 8: Test Session Persistence

31. Note the current session ID (visible in sidebar or URL)
32. Reload the page (`Ctrl+R` or navigate to `{URL}/chat`)
33. Wait up to 5 seconds for the page to reload
34. Take a screenshot — save as `intake-reload.png`
35. Verify the previous messages are still visible (session auto-saved to localStorage)
36. Verify both user messages and both EAGLE responses are present

### Phase 9: Report Results

Report **PASS** or **FAIL** for each check:

| Check | Expected | Actual | Result |
|-------|----------|--------|--------|
| Chat page loaded | Welcome screen or chat UI visible | | |
| 5 quick action buttons | All present and clickable | | |
| New Intake pre-fills textarea | CT scanner intake text appears | | |
| Message sent | User bubble appears, textarea disabled | | |
| Streaming indicator | Textarea shows "Waiting for response…" | | |
| EAGLE response received | Exactly 1 response bubble, not empty | | |
| Response content | Acquisition-relevant, asks follow-up | | |
| Input re-enabled | Textarea accepts input after response | | |
| Follow-up sent + responded | Second exchange completes | | |
| Session persists on reload | Messages visible after page reload | | |

**Overall result**: PASS only if ALL checks pass.

If any check fails, include:
- How many EAGLE bubbles appeared (0, 1, or N)
- Whether streaming ever started (textarea disabled?)
- Content of any unexpected/empty messages
- Whether session reloaded correctly
- Any console errors
