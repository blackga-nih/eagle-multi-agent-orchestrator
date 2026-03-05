---
description: Test EAGLE session management and slash command skill invocation — new conversations isolate correctly, sessions persist and switch, slash picker works, commands route to the right skill
argument-hint: [url]
---

# EAGLE Session Memory + Skill Invocation Test

Tests three distinct behaviors:
1. **New conversation** — "New Chat" creates an isolated session with no bleed from previous
2. **Session memory** — messages persist per-session in localStorage; switching sessions shows the right history; reload restores state
3. **Skill invocation** — `/` triggers the slash command picker, keyboard nav selects commands, sending a command gets a skill-appropriate EAGLE response

## Variables

| Variable | Value | Description |
| -------- | ----- | ----------- |
| SKILL | `claude-bowser` | Uses your real Chrome |
| MODE | `headed` | Visible browser |
| URL | `{PROMPT}` or `http://localhost:3000` | Base URL |

If {PROMPT} contains a URL use it, otherwise default to `http://localhost:3000`.

---

## Part 1: New Conversation Isolation

### Phase 1: Seed a First Session

1. Navigate to `{URL}/chat`
2. Wait up to 10 seconds for the page to load
3. If a login page appears, report **FAIL — Not authenticated** and stop
4. Click "New Chat" in the sidebar to ensure a clean start
5. Wait for the welcome screen to appear
6. Click the chat textarea and type: `Remember this: my acquisition is for a CT scanner.`
7. Press Enter and wait up to 45 seconds for EAGLE to respond
8. Verify a response bubble appears
9. Take a screenshot — save as `session-seed.png`
10. Note the **Session A** ID shown in the sidebar (session title or timestamp)

### Phase 2: Create a New Conversation

11. Click "New Chat" in the sidebar
12. Wait for the welcome screen to appear
13. Take a screenshot — save as `session-new.png`
14. Verify:
    - The message list is **empty** (welcome screen shown, no prior messages visible)
    - The textarea placeholder is "Ask EAGLE about acquisitions…" (not disabled)
    - The sidebar shows **Session A** as a separate entry with "• 2 msgs" (or similar count)
    - The current session shows **0 msgs** or no count yet
15. Confirm no messages from Session A leaked into this new session

### Phase 3: Send a Message in Session B

16. Type: `This is a fresh session. What is FAR Part 13?`
17. Press Enter and wait up to 45 seconds for a response
18. Verify EAGLE responds about FAR Part 13 (simplified acquisition procedures)
19. Take a screenshot — save as `session-b-response.png`
20. Note this is **Session B** — the sidebar now shows 2 sessions

---

## Part 2: Session Memory and Switching

### Phase 4: Switch Back to Session A

21. In the sidebar, click on **Session A** (the CT scanner session from Phase 1)
22. Wait up to 3 seconds for the session to load
23. Take a screenshot — save as `session-switch-a.png`
24. Verify:
    - The message list shows the CT scanner messages (user message + EAGLE response)
    - Session B's FAR Part 13 messages are **not** visible
    - The sidebar highlights Session A as the active session

### Phase 5: Switch Back to Session B

25. Click on **Session B** in the sidebar (the FAR Part 13 session)
26. Wait up to 3 seconds for the session to load
27. Take a screenshot — save as `session-switch-b.png`
28. Verify:
    - FAR Part 13 messages are present
    - CT scanner messages are **not** visible
    - Both sessions are intact with correct message counts

### Phase 6: Reload and Verify Persistence

29. Hard reload the page (`Ctrl+Shift+R` or navigate to `{URL}/chat`)
30. Wait up to 5 seconds for the page to load
31. Take a screenshot — save as `session-reload.png`
32. Verify:
    - Both sessions (Session A and Session B) are still listed in the sidebar
    - The previously active session's messages are still shown
    - Message counts in the sidebar match what was there before reload
    - No sessions were lost

### Phase 7: Verify Session A Still Intact After Reload

33. Click on Session A in the sidebar
34. Verify the CT scanner message and EAGLE response are still present
35. Take a screenshot — save as `session-a-after-reload.png`

---

## Part 3: Slash Command Skill Invocation

### Phase 8: Open Slash Command Picker

36. Click "New Chat" to start a fresh session for slash command testing
37. Click the chat textarea to focus it
38. Type a single forward slash: `/`
39. Take a screenshot immediately — save as `session-slash-picker.png`
40. Verify the slash command picker appears as a popup **above** the textarea with:
    - `/acquisition-package` — "Start a new acquisition package"
    - `/research` — "Search regulations, policies, and knowledge base"
    - `/document` — "Generate procurement documents (SOW, IGCE, etc.)"
    - `/status` — "Check current acquisition package status"
    - `/help` — "Show available commands and capabilities"
41. Verify exactly **5** commands are listed

### Phase 9: Test Keyboard Navigation in Picker

42. Press the **Down Arrow** key once — verify the second item gets highlighted/selected
43. Press the **Down Arrow** key again — verify the third item is highlighted
44. Press the **Up Arrow** key once — verify selection moves back to the second item
45. Take a screenshot — save as `session-slash-nav.png`

### Phase 10: Select /help via Keyboard

46. Press the **Up Arrow** key until the first item (`/acquisition-package`) is highlighted, OR press **Escape** and retype `/help`
47. Type `help` after the `/` to filter — verify the picker narrows to show only `/help`
48. Press **Enter** or **Tab** to select the `/help` command
49. Verify the textarea is now filled with `/help ` (the command name followed by a space)
50. Take a screenshot — save as `session-slash-selected.png`
51. Verify the slash picker **closed** after selection

### Phase 11: Send /help and Validate Response

52. Press Enter to send the `/help` command
53. Wait up to 45 seconds for EAGLE to respond
54. Take a screenshot — save as `session-help-response.png`
55. Verify the EAGLE response:
    - Is not empty
    - Contains a list or description of available commands/capabilities
    - References acquisition-related capabilities (intake, documents, FAR/DFARS, etc.)

### Phase 12: Test /research Command

56. Click the textarea and type `/research`
57. Verify the picker appears and `/research` is visible/highlighted
58. Press Enter or Tab to select it
59. Verify textarea fills with `/research `
60. Append text: `FAR Part 15 negotiated acquisitions`
61. Full textarea should read: `/research FAR Part 15 negotiated acquisitions`
62. Take a screenshot — save as `session-research-command.png`
63. Press Enter to send
64. Wait up to 45 seconds for EAGLE to respond
65. Take a screenshot — save as `session-research-response.png`
66. Verify the response:
    - Contains content about FAR Part 15 (Contracting by Negotiation)
    - Is substantive (not just an error or empty acknowledgement)

---

## Part 4: Report Results

Report **PASS** or **FAIL** for each check:

| Check | Expected | Actual | Result |
|-------|----------|--------|--------|
| New Chat creates empty session | Welcome screen, no prior messages | | |
| Session A messages isolated | CT scanner messages not in Session B | | |
| Session B messages correct | FAR Part 13 content present | | |
| Switch to Session A | CT scanner messages load, no FAR bleed | | |
| Switch to Session B | FAR messages load, no CT bleed | | |
| Sessions survive reload | Both sessions intact after Ctrl+Shift+R | | |
| Session A intact after reload | CT scanner exchange still present | | |
| Slash picker opens on `/` | Popup with 5 commands appears | | |
| All 5 commands listed | /acquisition-package /research /document /status /help | | |
| Keyboard navigation works | Arrow keys move selection up/down | | |
| Picker closes on selection | Textarea filled, picker dismissed | | |
| /help response relevant | Lists EAGLE capabilities | | |
| /research command works | FAR Part 15 content in response | | |

**Overall result**: PASS only if ALL checks pass.

If any check fails, include:
- Whether the slash picker appeared at all
- How many commands were shown vs expected 5
- Whether sessions showed cross-contamination (wrong messages)
- Whether localStorage was readable after reload
- Any console errors relating to session storage or command routing
