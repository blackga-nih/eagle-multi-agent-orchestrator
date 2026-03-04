---
description: Test EAGLE multi-turn session memory — sends a message with a distinctive codename and project name, then asks a follow-up question in the same session to verify EAGLE remembers the context. Also validates that the same session_id is sent with every message in a session and that New Chat generates a new session_id.
argument-hint: [url]
---

# EAGLE Session Memory Test

Validates that EAGLE chat remembers context across multiple messages in the
same session (multi-turn memory). Also checks that the client sends a stable
`session_id` on every message in a session and generates a new one on "New Chat".

The memory chain under test:
```
React state (currentSessionId)
  → use-agent-stream sendQuery(query, currentSessionId)
    → POST /api/invoke { query, session_id }
      → Next.js route.ts proxy → POST /api/chat/stream { message, session_id }
        → sdk_query(resume=session_id) → Claude SDK session resume
```

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
3. If a login redirect occurs, report **FAIL — Not authenticated** and stop
4. Click "New Chat" in the sidebar and wait for the welcome heading
5. Take a screenshot — save as `memory-preflight.png`

---

## Part 1: Multi-Turn Memory Validation

### Phase 1: Send a distinctive first message

6. Click the textarea and type EXACTLY:
   `My codename is APOLLO-PRIME and I am the lead engineer for Project STARGATE. Please acknowledge both.`
7. Press Enter to send
8. Wait up to 90 seconds for EAGLE to respond (streaming indicator disappears, textarea re-enables)
9. Take a screenshot — save as `memory-msg1.png`
10. Verify:
    - A response bubble appeared from EAGLE
    - The response is non-empty and substantive

### Phase 2: Intercept the request (network inspection)

11. Open browser devtools → Network tab
12. Locate the POST request to `/api/invoke` (or `/api/chat/stream` if direct)
13. Inspect the request body — note the `session_id` value (UUID format)
14. Take a screenshot — save as `memory-network-msg1.png`
15. Record the session_id value: **[session_id_1]**

### Phase 3: Send follow-up in the SAME session (do NOT click New Chat)

16. Stay in the same chat session
17. Click the textarea and type EXACTLY:
    `What is my codename and what project am I leading?`
18. Press Enter to send
19. Wait up to 90 seconds for EAGLE to respond
20. Take a screenshot — save as `memory-msg2.png`

### Phase 4: Verify memory

21. Inspect the second POST request to `/api/invoke` — record **[session_id_2]**
22. Verify the following:
    - **session_id unchanged**: `session_id_1 == session_id_2` (same UUID both messages)
    - **EAGLE recalls codename**: Response contains "APOLLO-PRIME" (case-insensitive)
    - **EAGLE recalls project**: Response contains "STARGATE" (case-insensitive)

If session_id differs between messages → the client is not carrying session state → **root cause of memory failure**

If session_id is same but EAGLE still doesn't remember → the SDK `resume` is not restoring context → **backend/SDK issue**

### Phase 5: Third turn context check

23. Type: `What were my exact first two questions to you in this conversation?`
24. Press Enter, wait up to 90 seconds
25. Take a screenshot — save as `memory-msg3.png`
26. Verify EAGLE references both previous messages:
    - Mentions "APOLLO-PRIME" or codename from turn 1
    - Mentions "codename" or "project" from turn 2

---

## Part 2: Session Isolation Validation

### Phase 6: New Chat generates a new session_id

27. Click "New Chat" — wait for welcome screen
28. Type: `Session isolation test message`
29. Press Enter (don't wait for full response — just let the request fire)
30. Inspect the POST request to `/api/invoke` — record **[session_id_3]**
31. Verify: `session_id_3 != session_id_1` (new chat = new session ID)
32. Take a screenshot — save as `memory-new-session.png`

---

## Part 3: Console Error Check

33. Check browser console for errors related to:
    - `session_id undefined` or `null`
    - `resume` failures
    - DynamoDB errors
    - SDK subprocess failures ("SDK subprocess failed", "fallback")
34. Take a screenshot — save as `memory-console.png`
35. Record any errors found

---

## Part 4: Report Results

Report **PASS** or **FAIL** for each check:

| Check | Expected | Actual | Result |
|-------|----------|--------|--------|
| Message 1 gets a response | Non-empty EAGLE response | | |
| session_id_1 is a valid UUID | UUID format | | |
| session_id_2 == session_id_1 | Same ID across turns | | |
| EAGLE recalls codename (APOLLO-PRIME) | Present in response | | |
| EAGLE recalls project (STARGATE) | Present in response | | |
| Turn 3 references prior context | Mentions prior messages | | |
| session_id_3 != session_id_1 | New chat = new session | | |
| No console errors re: session/resume | Clean console | | |

**Overall result**: PASS only if ALL 8 checks pass.

If memory checks fail, include:
- Whether session_id was consistent (same UUID across messages)
- Whether the console showed "SDK subprocess failed" or "fallback" messages
- The exact text of EAGLE's response to "What is my codename and project?"
- Whether the `/api/invoke` request body contained `session_id` at all
