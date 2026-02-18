---
description: Log into the EAGLE frontend and run a comprehensive smoke test across all pages and features
argument-hint: [url] [headed]
---

# EAGLE Frontend Smoke Test

Log into the EAGLE frontend application and verify all major pages load correctly, the backend API responds, chat works end-to-end, session persistence works, and key features function properly.

## Variables

| Variable | Value           | Description                                              |
| -------- | --------------- | -------------------------------------------------------- |
| SKILL    | `claude-bowser` | Uses your real Chrome for browser automation             |
| MODE     | `headed`        | Visible browser (default)                                |
| URL      | `{PROMPT}` or `http://localhost:3000` | Base URL of the EAGLE frontend |

If {PROMPT} contains a URL, use that. Otherwise default to `http://localhost:3000`.

## Workflow

### Phase 1: Login

1. Navigate to {URL}/login
2. Verify the login page loads — look for:
   - The EAGLE logo (blue "E" in a rounded box)
   - "Sign in to your account" heading
   - Email and Password input fields
   - "Sign in" button
   - "National Cancer Institute — Office of Acquisitions" footer text
3. Take a screenshot of the login page
4. **Dev mode check**: If the page auto-redirects to the home page (no Cognito configured = dev mode), skip login form and go to Phase 2
5. If login form is present:
   - Enter email: `dev@example.com` in the email field
   - Enter password: `Password123!` in the password field
   - Click "Sign in"
   - Wait for redirect to home page (up to 10 seconds)
   - If login fails with an error banner, report the error and try navigating directly to {URL}/ (dev mode may auto-authenticate)

### Phase 2: Home Page Verification

6. Verify the home page loads — look for:
   - "EAGLE" branding in the header
   - Four feature cards: "Chat", "Document Templates", "Acquisition Packages", "Admin"
   - Each card should have an icon, title, description, and be clickable
7. Take a screenshot of the home page
8. Report: PASS or FAIL with details

### Phase 3: Chat Page Test

9. Click the "Chat" card or navigate to {URL}/chat
10. Verify the chat page loads — look for:
    - A sidebar navigation panel
    - A chat input area / message box
    - The EAGLE header
    - Quick action buttons (New Intake, Generate SOW, Search FAR, Cost Estimate, Small Business)
11. Take a screenshot of the chat page
12. Type a test message: "Hello, can you confirm you are the EAGLE acquisition assistant?"
13. Wait for a response (up to 30 seconds)
14. Verify:
    - A response appears from the assistant
    - No error messages displayed
    - The response mentions EAGLE, NCI, or acquisitions
15. Take a screenshot showing the conversation
16. Report: PASS or FAIL with response preview

### Phase 4: Quick Action Buttons

17. Click the "New Intake" quick action button (or type the equivalent command)
18. Wait for a response (up to 30 seconds)
19. Verify:
    - The assistant responds with an intake-related prompt (asking about acquisition needs, requirements, etc.)
    - No error messages
20. Take a screenshot
21. Report: PASS or FAIL

### Phase 5: Session Persistence

22. Note the current session name in the sidebar (it should show the conversation we just had)
23. Click "New Chat" to start a fresh session
24. Verify the welcome screen appears ("Welcome to EAGLE")
25. Click back on the previous session in the sidebar
26. Verify:
    - The previous conversation loads with all messages intact
    - Both the user message and assistant response are visible
    - The message timestamps are present
27. Take a screenshot showing the restored session
28. Report: PASS or FAIL

### Phase 6: Documents Page Test

29. Navigate to {URL}/documents
30. Verify the documents page loads — look for:
    - "Documents" heading
    - Status filter tabs (All Documents, Not Started, In Progress, Draft, Approved)
    - Document cards with title, status badge, type, date, and version
    - Search bar and filter controls
    - "Templates" and "New Document" buttons
31. Click the "Templates" button
32. Verify templates view loads (or a modal/page appears) — no crash
33. Navigate back to {URL}/documents if needed
34. Take a screenshot
35. Report: PASS or FAIL

### Phase 7: Workflows Page Test

36. Navigate to {URL}/workflows
37. Verify the workflows page loads — look for:
    - "Acquisition Packages" heading
    - Status filter tabs (All, In Progress, Pending Review, Approved, Completed)
    - Package cards with title, ID, status, description, acquisition type, value, and date
    - "New Package" button, search bar, filter and sort controls
38. Click into the first workflow/package to verify detail view loads
39. Take a screenshot of the detail view (or the list if click doesn't navigate)
40. Navigate back to {URL}/workflows if needed
41. Report: PASS or FAIL

### Phase 8: Admin Dashboard Test

42. Navigate to {URL}/admin
43. Verify the admin dashboard loads — look for:
    - Dashboard statistics cards (Active Workflows, Total Value, Documents Generated, Avg Completion Time)
    - Quick Actions section with links (Test Results, Eval Viewer, Manage Users, Document Templates, Agent Skills)
    - Recent Activity feed
    - System Health section (AI Services, Database, API Rate Limit)
44. Take a screenshot of the admin dashboard
45. Report: PASS or FAIL

### Phase 9: Admin Sub-Pages

46. Click "Test Results" (or navigate to {URL}/admin/tests)
47. Verify the page loads without errors — take a screenshot
48. Navigate to {URL}/admin/eval
49. Verify the eval viewer loads without errors — take a screenshot
50. Navigate to {URL}/admin/users
51. Verify the users page loads without errors — take a screenshot
52. Navigate to {URL}/admin/templates
53. Verify the templates page loads without errors — take a screenshot
54. Navigate to {URL}/admin/skills
55. Verify the skills page loads without errors — take a screenshot
56. Report: PASS or FAIL for each sub-page (count any that error as failures)

### Phase 10: Backend API Endpoints

57. Use the browser console or navigate to verify these backend API endpoints:
    - `{URL}/api/tools` — should return a JSON array of available tools
    - `{URL}/api/sessions` — should return a JSON array of sessions (may be empty)
    - `{URL}/api/prompts` — should return agent/skill metadata
58. For each endpoint, verify:
    - HTTP 200 response (no 500 errors)
    - Valid JSON in the response body
59. Report: PASS or FAIL with status codes

### Phase 11: Backend Health Check

60. Navigate to {URL}/api/health (or use evaluate_script to fetch it)
61. Verify the response contains:
    - `"status": "healthy"`
    - `"service": "eagle-backend"`
    - `"version"` field present
62. If the browser shows "Internal Server Error" due to trailing-slash rewrite, use evaluate_script to fetch directly:
    ```javascript
    async () => {
      const resp = await fetch('/api/health');
      return { status: resp.status, body: await resp.json() };
    }
    ```
63. Report: PASS or FAIL with response data

### Phase 12: Summary Report

64. Compile the results:

```
# EAGLE Smoke Test Report

**URL:** {URL}
**Date:** {current date and time}
**Auth Mode:** Dev Mode / Cognito

## Results

| #  | Test                    | Status  | Notes                          |
|----|-------------------------|---------|--------------------------------|
| 1  | Login Page              | ✅/❌   | {details}                      |
| 2  | Home Page               | ✅/❌   | {details}                      |
| 3  | Chat Page Load          | ✅/❌   | {details}                      |
| 4  | Chat Send/Receive       | ✅/❌   | {response preview}             |
| 5  | Quick Action Button     | ✅/❌   | {details}                      |
| 6  | Session Persistence     | ✅/❌   | {details}                      |
| 7  | Documents Page          | ✅/❌   | {details}                      |
| 8  | Workflows Page          | ✅/❌   | {details}                      |
| 9  | Admin Dashboard         | ✅/❌   | {details}                      |
| 10 | Admin: Test Results     | ✅/❌   | {details}                      |
| 11 | Admin: Eval Viewer      | ✅/❌   | {details}                      |
| 12 | Admin: Users            | ✅/❌   | {details}                      |
| 13 | Admin: Templates        | ✅/❌   | {details}                      |
| 14 | Admin: Skills           | ✅/❌   | {details}                      |
| 15 | API: /api/tools         | ✅/❌   | {status code, tool count}      |
| 16 | API: /api/sessions      | ✅/❌   | {status code}                  |
| 17 | API: /api/prompts       | ✅/❌   | {status code}                  |
| 18 | Backend Health          | ✅/❌   | {health response}              |

**Overall:** ✅ ALL PASSED / ❌ {N} FAILED

## Screenshots
(list screenshot paths if saved)

## Issues Found
(only if failures occurred — describe each issue)
```

65. STOP — report the summary to the user
