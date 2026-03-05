---
description: Test EAGLE chat edge cases — empty message send blocked, whitespace guard, send button disabled state, streaming lock prevents double-submit, Shift+Enter inserts newline, very long message (2000+ chars) handled without crash, rapid send attempts blocked during streaming
argument-hint: [url]
---

# EAGLE Chat Edge Cases Test

Tests defensive behaviors in the chat input: guards against empty/whitespace sends,
streaming-state double-submit, Shift+Enter newline insertion, and very long messages.
All guards are implemented in `simple-chat-interface.tsx` and validated here end-to-end.

## Variables

| Variable | Value | Description |
| -------- | ----- | ----------- |
| SKILL | `agent-browser` | Headless, Linux-compatible |
| MODE | `headless` | No Chrome DevTools required |
| URL | `{PROMPT}` or `http://localhost:3000` | Base URL |

If {PROMPT} contains a URL use it, otherwise default to `http://localhost:3000`.

---

## Pre-flight

1. Navigate to `{URL}/chat`
2. Wait up to 10 seconds for the page to load
3. If a login page appears, report **FAIL — Not authenticated** and stop
4. Click "New Chat" in the sidebar to start a clean session
5. Wait for the welcome screen to appear
6. Take a screenshot — save as `edge-preflight.png`

---

## Part 1: Empty and Whitespace Message Guards

### Phase 1: Send Button Disabled on Empty Input

7. Click the chat textarea to focus it — do NOT type anything
8. Look at the Send button (dark blue rounded button to the right of the textarea)
9. Take a screenshot — save as `edge-empty-send-btn.png`
10. Verify the Send button is **visually disabled** (opacity reduced, appears dimmed / greyed out)
11. Attempt to click the Send button anyway
12. Wait 2 seconds
13. Take a screenshot — save as `edge-empty-click-attempt.png`
14. Verify:
    - No message bubble appeared in the chat
    - The welcome screen is still showing (or chat is unchanged)
    - No "loading" or streaming indicator appeared

### Phase 2: Whitespace-Only Input is Blocked

15. Click the textarea and type 5 spaces (just spaces, no real text)
16. Take a screenshot — save as `edge-whitespace-input.png`
17. Verify the Send button is still **disabled** (whitespace-only should not enable send)
18. Attempt to press Enter
19. Wait 2 seconds
20. Take a screenshot — save as `edge-whitespace-enter.png`
21. Verify no message was sent (no bubble appeared, welcome screen unchanged)
22. Clear the textarea (select all and delete)

### Phase 3: Valid Input Enables Send Button

23. Type: `Hello EAGLE`
24. Take a screenshot — save as `edge-valid-input.png`
25. Verify the Send button is now **enabled** (full opacity, not dimmed)
26. Clear the textarea again (select all and delete)
27. Verify the Send button returns to **disabled** state after clearing

---

## Part 2: Streaming Lock — No Double-Submit

### Phase 4: Textarea Disabled During Streaming

28. Type: `What is FAR Part 15? Please give a detailed answer.`
29. Press Enter to send
30. **Immediately** (within 1 second of pressing Enter) take a screenshot — save as `edge-streaming-lock.png`
31. Verify while streaming is in progress:
    - The textarea shows "Waiting for response…" placeholder (or is visibly disabled/greyed)
    - The Send button is **disabled** (opacity-30 or visibly dimmed)
32. Attempt to click the textarea and type more text during streaming
33. Wait 1 second
34. Take a screenshot — save as `edge-streaming-type-attempt.png`
35. Verify typing was blocked (textarea is in disabled state)

### Phase 5: No Double-Submit via Enter Key During Streaming

36. While still streaming (or start a new session and repeat the send):
    - Type a message and press Enter to send
    - Immediately press Enter again (attempting a second send)
    - Wait up to 45 seconds for the first response to complete
37. Take a screenshot after streaming completes — save as `edge-no-double-submit.png`
38. Verify:
    - Exactly **1** EAGLE response bubble appeared (not 2)
    - No empty message bubbles visible
    - No duplicate user message bubble

### Phase 6: Textarea Re-Enables After Streaming

39. After the FAR Part 15 response completes (textarea re-enabled)
40. Take a screenshot — save as `edge-streaming-complete.png`
41. Verify:
    - The textarea placeholder returns to "Ask EAGLE about acquisitions…" or similar
    - The Send button is active (enabled if text was typed, disabled if empty)
    - The chat is ready for the next message

---

## Part 3: Shift+Enter Inserts Newline (No Submit)

### Phase 7: Shift+Enter Behavior

42. Click "New Chat" — wait for welcome screen
43. Click the textarea and type: `Line one of my message`
44. Press Shift+Enter (hold Shift, press Enter)
45. Take a screenshot immediately — save as `edge-shift-enter.png`
46. Verify:
    - The message was **not sent** (no user bubble appeared)
    - The textarea now contains two lines (cursor moved to a new line)
    - OR the cursor is on a new line in the textarea
47. Type: `Line two of my message`
48. Take a screenshot — save as `edge-multiline-input.png`
49. Verify the textarea shows both lines of text
50. Press Enter (without Shift) to send
51. Wait up to 45 seconds for EAGLE to respond
52. Take a screenshot — save as `edge-multiline-sent.png`
53. Verify the user bubble contains both lines (multi-line message was sent as one message)

---

## Part 4: Very Long Message (2000+ Characters)

### Phase 8: Long Message Handling

54. Click "New Chat" — wait for welcome screen
55. Click the textarea and paste or type a message of at least 2000 characters:
    Use the following (copy exactly — it is 2100+ characters):
    ```
    I need detailed acquisition guidance for the following complex procurement scenario. We are acquiring a next-generation genomics sequencing platform for the NCI Cancer Genomics Research Laboratory. The system must include: (1) A high-throughput short-read sequencer capable of producing 1.5 terabases per run with Q30 scores above 85%, (2) A long-read sequencer for structural variant detection with read lengths exceeding 100 kilobases, (3) A fully integrated data management system with automated pipeline execution, quality control reporting, and integration with NIH HPC clusters via SFTP and REST API, (4) Installation, qualification, and validation services including IQ/OQ/PQ documentation suitable for CAP/CLIA accreditation, (5) A 5-year preventive maintenance and service agreement with guaranteed 4-hour on-site response time, (6) Comprehensive training for 12 laboratory staff members, and (7) Regulatory compliance with 21 CFR Part 11, FISMA Moderate, and NIH IT security requirements. The estimated total value is $3.2 million over 5 years. The procurement team is considering a sole-source justification under FAR 6.302-1, but we are concerned about protest risk given that competing vendors have comparable systems. We need EAGLE to help us determine the appropriate acquisition strategy, draft the J&A, identify evaluation factors, and estimate the IGCE. What should our first steps be?
    ```
56. Take a screenshot — save as `edge-long-message-input.png`
57. Verify:
    - The message appears in the textarea without truncation
    - The Send button is enabled (long message is valid content)
    - The UI has not crashed or frozen
58. Press Enter to send
59. Wait up to 90 seconds for EAGLE to respond (long messages may take longer)
60. Take a screenshot — save as `edge-long-message-response.png`
61. Verify:
    - The user message bubble shows the full (or appropriately truncated) message
    - EAGLE provides a substantive response (not an error or empty message)
    - The UI is still functional after handling the long message
    - No JavaScript errors or blank page

---

## Part 5: Report Results

Report **PASS** or **FAIL** for each check:

| Check | Expected | Actual | Result |
|-------|----------|--------|--------|
| Empty input: send button disabled | Button visually dimmed | | |
| Empty input: click blocked | No message sent on click | | |
| Whitespace only: blocked | Disabled button, Enter ignored | | |
| Valid input: button enables | Button becomes active | | |
| Clear input: button re-disables | Button returns to dimmed state | | |
| Streaming: textarea disabled | Shows "Waiting…" placeholder | | |
| Streaming: send button disabled | Button dimmed during response | | |
| No double-submit via Enter | Exactly 1 EAGLE bubble after rapid Enter | | |
| Textarea re-enables after stream | Returns to "Ask EAGLE…" placeholder | | |
| Shift+Enter inserts newline | No send triggered, 2nd line in textarea | | |
| Multi-line message sends as one | Both lines in user bubble | | |
| Long message (2000+): no crash | Message sent, UI functional | | |
| Long message: substantive response | EAGLE responds appropriately | | |

**Overall result**: PASS only if ALL 13 checks pass.

If any check fails, include:
- Which specific guard failed (empty/whitespace/streaming/Shift+Enter/long)
- Whether any unexpected messages appeared in the chat
- Whether the textarea or send button was in an unexpected state
- Any console errors (JavaScript exceptions, network errors)
