---
description: Test EAGLE MCP tool integration — weather queries invoke OpenWeatherMap via the MCP layer, tool results appear in the chat response, WebSocket/MCP connection has no console errors. Requires premium/admin user (mcp_server_access=true).
argument-hint: [url]
---

# EAGLE MCP Tools Test

Tests the OpenWeatherMap MCP integration by sending weather-related queries through the
EAGLE chat as a premium user.  Validates that the MCP layer connects, the weather tool
is invoked, and results surface in the chat response.  Also tests that MCP errors are
handled gracefully (missing API key → fallback response, not a crash).

## Variables

| Variable | Value | Description |
| -------- | ----- | ----------- |
| SKILL | `agent-browser` | Headless, Linux-compatible |
| MODE | `headless` | No Chrome DevTools required |
| URL | `{PROMPT}` or `http://localhost:3000` | Base URL |
| ADMIN_EMAIL | `admin@example.com` | Premium tier — mcp_server_access=true |
| ADMIN_PASS | `EagleAdmin2024!` | Admin user password |

If {PROMPT} contains a URL use it, otherwise default to `http://localhost:3000`.

---

## Pre-flight: Ensure Premium Auth

1. Navigate to `{URL}/login`
2. Wait up to 10 seconds for the page to load
3. If already on a non-login page (already authenticated), skip to Phase 1
4. Fill email with `admin@example.com` and password with `EagleAdmin2024!`
5. Click "Sign in" and wait up to 10 seconds for redirect
6. If still on `/login`, report **FAIL — Admin login required for MCP test** and stop
7. Take a screenshot — save as `mcp-preflight.png`

---

## Phase 1: Confirm MCP Access Enabled for This User

8. Navigate to `{URL}/api/subscription/status`
9. Wait up to 5 seconds for JSON response
10. Verify `"mcp_server_access": true` in the response
11. If false, skip MCP tool invocation tests and report **SKIP — MCP requires premium tier**

---

## Phase 2: Weather Query — Direct MCP Invocation

### Phase 2a: Basic Weather Query

12. Navigate to `{URL}/chat`
13. Click "New Chat" in the sidebar and wait for welcome screen
14. Click the textarea and type exactly:
    `What is the current weather in Bethesda, Maryland? I need to plan an outdoor equipment delivery to NIH campus.`
15. Press Enter and wait up to 60 seconds for EAGLE to respond
16. Take a screenshot after the response appears — save as `mcp-weather-basic.png`
17. Verify the response is non-empty and not an error message
18. Check for ONE of the following outcomes:
    - **MCP live data**: response contains weather data (temperature, conditions, humidity, or forecast language)
    - **MCP graceful fallback**: response says the weather service is unavailable/not configured but still provides acquisition guidance
    - **General acquisition guidance**: EAGLE acknowledges the weather context and advises on the outdoor delivery without live data
19. Verify the response does NOT contain an unhandled exception, stack trace, or "500 Internal Server Error"

### Phase 2b: Weather Context for Acquisition Planning

20. Click "New Chat" — wait for welcome screen
21. Click the textarea and type exactly:
    `For our CT scanner delivery to Building 37, what weather conditions should we watch for in Maryland in January? Are there any contract clauses that address weather delays?`
22. Press Enter and wait up to 60 seconds for EAGLE to respond
23. Take a screenshot — save as `mcp-weather-acquisition.png`
24. Verify the response:
    - Is substantive (not just "I don't know")
    - References Maryland weather, winter conditions, or weather-related acquisition language
    - OR gracefully explains MCP weather data is unavailable and pivots to relevant FAR/DFARS clauses about delays

### Phase 2c: Weather Forecast Query

25. Click "New Chat" — wait for welcome screen
26. Type exactly: `Get a 5-day weather forecast for Rockville, MD. We have a vendor demo scheduled outdoors.`
27. Press Enter and wait up to 60 seconds for EAGLE to respond
28. Take a screenshot — save as `mcp-weather-forecast.png`
29. Verify one of:
    - Response contains forecast data (days, temperatures, conditions)
    - Response provides a graceful fallback ("weather service not available") with relevant acquisition guidance about contingency planning

---

## Phase 3: MCP Error Resilience

### Phase 3a: Invalid Location Query

30. Click "New Chat" — wait for welcome screen
31. Type: `What is the weather in XYZNONEXISTENTPLACE99999?`
32. Press Enter and wait up to 45 seconds for EAGLE to respond
33. Take a screenshot — save as `mcp-invalid-location.png`
34. Verify:
    - EAGLE responds without crashing (no 500 or unhandled error)
    - Response either says the location was not found OR gracefully redirects the conversation
    - The chat UI remains functional (textarea is re-enabled after response)

### Phase 3b: Non-Weather Query After MCP Query

35. In the same session (or new chat), type: `What FAR clause covers force majeure and weather delays?`
36. Press Enter and wait up to 45 seconds for a response
37. Take a screenshot — save as `mcp-non-weather-after.png`
38. Verify:
    - EAGLE responds normally with FAR-related content (not stuck in weather mode)
    - Response mentions force majeure, FAR 52.249, weather delays, or excusable delay
    - Confirms MCP weather queries don't permanently alter the agent's routing

---

## Phase 4: Console Error Check

39. Check browser console for errors related to MCP or WebSocket:
    - No `WebSocket connection failed` errors
    - No `MCP tool invocation error` in logs
    - No `OPENWEATHER_API_KEY not set` at error severity (warnings are OK)
40. Take a final screenshot — save as `mcp-console-check.png`

---

## Phase 5: Report Results

Report **PASS** or **FAIL** for each check:

| Check | Expected | Actual | Result |
|-------|----------|--------|--------|
| Admin auth succeeded | Redirected to chat | | |
| mcp_server_access=true for premium | API returns true | | |
| Basic weather query responds | Non-empty, non-crash response | | |
| Weather response content | Live data OR graceful fallback | | |
| Acquisition-context weather query | References weather or delay clauses | | |
| Forecast query handled | Forecast or graceful fallback | | |
| Invalid location: no crash | Handled gracefully, chat functional | | |
| Non-weather query after MCP | Normal FAR response, not stuck | | |
| No critical console errors | No WebSocket/MCP crash logs | | |

**Overall result**: PASS only if ALL 9 checks pass.
SKIP is acceptable for MCP invocation checks if `mcp_server_access=false` for the test user.

If any check fails, include:
- Whether `OPENWEATHER_API_KEY` appears to be set (live data returned vs. demo response)
- The exact error message or response content
- Whether the fallback path worked correctly
- Any WebSocket or MCP connection errors from the console
