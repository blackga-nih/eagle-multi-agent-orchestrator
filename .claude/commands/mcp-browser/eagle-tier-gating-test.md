---
description: Test EAGLE subscription tier gating — basic user sees Standard tier label with mcp_server_access=false, premium/admin user sees Premium label with full feature access, subscription status endpoint validates tier limits
argument-hint: [url]
---

# EAGLE Tier Gating Test

Validates that subscription tier is correctly reflected in the UI and enforced
at the backend.  Tests two distinct users: a standard-tier user and a premium/admin
user.  Covers tier label display, MCP access flag, session limits, and the
`/api/subscription/status` endpoint.

## Variables

| Variable | Value | Description |
| -------- | ----- | ----------- |
| SKILL | `agent-browser` | Headless, Linux-compatible |
| MODE | `headless` | No Chrome DevTools required |
| URL | `{PROMPT}` or `http://localhost:3000` | Base URL |
| STANDARD_EMAIL | `testuser@example.com` | Basic/standard tier account |
| STANDARD_PASS | `EagleTest2024!` | Standard user password |
| ADMIN_EMAIL | `admin@example.com` | Premium tier + admin account |
| ADMIN_PASS | `EagleAdmin2024!` | Admin user password |

If {PROMPT} contains a URL use it, otherwise default to `http://localhost:3000`.

---

## Part 1: Standard User — Tier Label and Feature Access

### Phase 1: Log in as Standard User

1. Navigate to `{URL}/login`
2. Wait up to 10 seconds for the page to load
3. Fill email with `testuser@example.com` and password with `EagleTest2024!`
4. Click "Sign in" and wait up to 10 seconds for redirect
5. If still on `/login`, report **FAIL — Standard user login failed** and stop
6. Take a screenshot — save as `tier-standard-login.png`

### Phase 2: Verify Standard Tier Label in Sidebar

7. Navigate to `{URL}/chat` and wait for the chat UI to load
8. Look in the sidebar for the user's tier label
9. Take a screenshot — save as `tier-standard-sidebar.png`
10. Verify:
    - The sidebar shows a tier indicator — it should **not** say "Premium"
    - Acceptable labels: "Standard", "Basic", "Free", "standard", or similar
    - The label is **not** "Premium" or "premium"

### Phase 3: Check Subscription Status via API

11. Navigate to `{URL}/api/subscription/status` directly
12. Wait up to 5 seconds for the JSON response
13. Take a screenshot — save as `tier-standard-api.png`
14. Verify the JSON response contains:
    - `"mcp_server_access": false` (basic tier cannot use MCP tools)
    - Daily message limit: `daily_messages` value is present (expect ≤ 200 for basic)
    - `"tier"` or `"subscription_tier"` field shows non-premium value
15. Note the `daily_messages` limit for comparison with the premium user check

### Phase 4: Standard User Cannot Use MCP Weather Tool

16. Navigate back to `{URL}/chat`
17. Click "New Chat" and wait for the welcome screen
18. Click the textarea and type: `What is the current weather in Bethesda, Maryland? I need to know for an outdoor equipment delivery.`
19. Press Enter and wait up to 45 seconds for EAGLE to respond
20. Take a screenshot — save as `tier-standard-mcp-attempt.png`
21. Verify one of the following (both are acceptable outcomes):
    - EAGLE responds but **without live weather data** (e.g., says it can't access weather, or gives general guidance without real temperature/conditions)
    - EAGLE responds with an upgrade message referencing tier limitations
    - EAGLE responds with a generic non-weather answer about the acquisition
22. Verify the response does **not** contain specific live weather data like current temperature in degrees or real-time conditions (which would indicate MCP was called)

---

## Part 2: Premium User — Full Feature Access

### Phase 5: Log Out and Log in as Premium User

23. Navigate to `{URL}/login` (this implicitly logs out, or look for a sign out button)
24. If the page shows the chat (still logged in as standard), look for a sign out / logout option in the sidebar or user menu and click it
25. If already on the login page, proceed
26. Fill email with `admin@example.com` and password with `EagleAdmin2024!`
27. Click "Sign in" and wait up to 10 seconds for redirect
28. If still on `/login`, report **FAIL — Admin user login failed** and stop
29. Take a screenshot — save as `tier-premium-login.png`

### Phase 6: Verify Premium Tier Label

30. Navigate to `{URL}/chat` and wait for the chat UI to load
31. Look in the sidebar for the tier label
32. Take a screenshot — save as `tier-premium-sidebar.png`
33. Verify:
    - The sidebar shows "Premium", "premium", or "Admin" tier indicator
    - The label is different from what was shown for the standard user

### Phase 7: Check Subscription Status — Premium Limits

34. Navigate to `{URL}/api/subscription/status`
35. Wait up to 5 seconds for the JSON response
36. Take a screenshot — save as `tier-premium-api.png`
37. Verify the JSON response contains:
    - `"mcp_server_access": true` (premium tier can use MCP tools)
    - Daily message limit is **higher** than the standard user's limit
    - `"tier"` or `"subscription_tier"` shows premium value

### Phase 8: Verify Admin Dashboard Access

38. Navigate to `{URL}/admin`
39. Wait up to 10 seconds for the page to load
40. Take a screenshot — save as `tier-premium-admin.png`
41. Verify the admin dashboard loads (not redirected to `/login` or `/`)
42. Verify stat cards are visible (Active Workflows, Total Value, etc.)

---

## Part 3: Report Results

Report **PASS** or **FAIL** for each check:

| Check | Expected | Actual | Result |
|-------|----------|--------|--------|
| Standard login succeeds | Redirected to chat | | |
| Standard tier label not "Premium" | "Standard", "Basic", or similar | | |
| Standard mcp_server_access=false | API returns false for MCP access | | |
| Standard daily limit ≤ 200 | Lower message limit than premium | | |
| Standard MCP weather: no live data | Response without real-time weather | | |
| Premium login succeeds | Redirected to chat | | |
| Premium tier label shows "Premium" | "Premium" or "Admin" in sidebar | | |
| Premium mcp_server_access=true | API returns true for MCP access | | |
| Premium daily limit higher | More messages/day than standard | | |
| Premium admin dashboard accessible | /admin loads with stat cards | | |

**Overall result**: PASS only if ALL 10 checks pass.

If any check fails, include:
- The exact tier label shown in the sidebar for each user
- The full JSON response from `/api/subscription/status`
- Whether the weather query returned live data or a gate message
- Any console errors related to auth or tier checking
