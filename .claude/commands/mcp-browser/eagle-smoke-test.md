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

### Phase 10: Sidebar Session List (hoquemi)

57. Navigate to {URL}/chat (if not already there)
58. Verify the sidebar shows a list of past conversation sessions — look for:
    - Session titles with `MessageSquare` icons
    - Relative timestamps ("Today", or date) and message counts
    - The current/active session highlighted with a blue background (`bg-blue-50`)
    - "New Chat" button at the top of the sidebar
    - "Acquisition Packages" and "Documents" links in a Resources section at the bottom
59. Take a screenshot of the sidebar
60. Report: PASS or FAIL

### Phase 11: Sidebar Session Rename (hoquemi)

61. Hover over a session row in the sidebar — verify a pencil/edit icon appears
62. Click the pencil icon — verify:
    - The title text becomes an editable input field
    - The current title is pre-filled and selected
63. Type a new name: "Smoke Test Renamed Session"
64. Press Enter to save
65. Verify the title updates to "Smoke Test Renamed Session"
66. Take a screenshot showing the renamed session
67. Report: PASS or FAIL

### Phase 12: Sidebar New Chat & Switch (hoquemi)

68. Click "New Chat" in the sidebar
69. Verify:
    - A new blank chat session loads (welcome screen or empty chat)
    - The previous session still appears in the sidebar list
70. Click back on the previous session ("Smoke Test Renamed Session") in the sidebar
71. Verify:
    - The previous conversation loads with all messages intact
    - The switched-to session is now highlighted in blue
72. Take a screenshot
73. Report: PASS or FAIL

### Phase 13: Session Persistence on Reload (hoquemi)

74. Note the current session title and message count
75. Reload the page (navigate to {URL}/chat again or use browser reload)
76. Verify:
    - The sidebar still shows the same sessions after reload
    - The previously active session is still accessible
    - Click into it — messages should still be present
77. Take a screenshot
78. Report: PASS or FAIL

### Phase 14: Document Checklist Panel (hoquemi)

79. Navigate to {URL}/chat and open a session that has had a conversation (or start a new one and send a message)
80. Look for the Document Checklist panel on the right side of the chat — verify:
    - Up to 6 document rows: SOW, IGCE, Market Research, Acquisition Plan, Funding Doc, Justification
    - Each row has a status icon: Clock (pending), spinning Loader (in-progress), or green CheckCircle (completed)
    - Rows have colored backgrounds: gray (pending), blue (in-progress), green (completed)
81. Click a pending or in-progress document row
82. Verify a modal opens showing:
    - A "Template" badge in the header
    - "Preview:" prefix in the title
    - Template content for that document type
83. Close the modal by clicking the X button
84. Take a screenshot of the checklist panel
85. Report: PASS or FAIL (note: checklist may not appear if no acquisition data in the session — report as SKIP in that case)

### Phase 15: Backend API Endpoints

86. Use the browser console or navigate to verify these backend API endpoints:
    - `{URL}/api/tools` — should return a JSON array of available tools
    - `{URL}/api/sessions` — should return a JSON array of sessions (may be empty)
    - `{URL}/api/prompts` — should return agent/skill metadata
87. For each endpoint, verify:
    - HTTP 200 response (no 500 errors)
    - Valid JSON in the response body
88. Report: PASS or FAIL with status codes

### Phase 16: Backend Health Check

89. Use evaluate_script to fetch the health endpoint:
    ```javascript
    async () => {
      const resp = await fetch('/api/health');
      return { status: resp.status, body: await resp.json() };
    }
    ```
90. Verify the response contains:
    - `"status": "healthy"`
    - `"service"` field present
    - `"version"` field present
91. Report: PASS or FAIL with response data

### Phase 17: Summary Report

92. Compile the results:

```
# EAGLE Smoke Test Report

**URL:** {URL}
**Date:** {current date and time}
**Auth Mode:** Dev Mode / Cognito

## Results

| #  | Test                       | Status  | Notes                          |
|----|----------------------------|---------|--------------------------------|
| 1  | Login Page                 | ✅/❌   | {details}                      |
| 2  | Home Page                  | ✅/❌   | {details}                      |
| 3  | Chat Page Load             | ✅/❌   | {details}                      |
| 4  | Chat Send/Receive          | ✅/❌   | {response preview}             |
| 5  | Quick Action Button        | ✅/❌   | {details}                      |
| 6  | Session Persistence        | ✅/❌   | {details}                      |
| 7  | Documents Page             | ✅/❌   | {details}                      |
| 8  | Workflows Page             | ✅/❌   | {details}                      |
| 9  | Admin Dashboard            | ✅/❌   | {details}                      |
| 10 | Admin: Test Results        | ✅/❌   | {details}                      |
| 11 | Admin: Eval Viewer         | ✅/❌   | {details}                      |
| 12 | Admin: Users               | ✅/❌   | {details}                      |
| 13 | Admin: Templates           | ✅/❌   | {details}                      |
| 14 | Admin: Skills              | ✅/❌   | {details}                      |
| 15 | Sidebar Session List       | ✅/❌   | {session count, highlights}    |
| 16 | Sidebar Rename             | ✅/❌   | {rename result}                |
| 17 | Sidebar New Chat & Switch  | ✅/❌   | {switch result}                |
| 18 | Session Reload Persistence | ✅/❌   | {survives reload?}             |
| 19 | Document Checklist Panel   | ✅/❌/⏭️ | {doc rows, status icons}       |
| 20 | API: /api/sessions         | ✅/❌   | {status code}                  |
| 21 | API: /api/prompts          | ✅/❌   | {status code}                  |
| 22 | Backend Health             | ✅/❌   | {health response}              |

**Overall:** ✅ ALL PASSED / ❌ {N} FAILED

## Screenshots
(list screenshot paths if saved)

## Issues Found
(only if failures occurred — describe each issue)
```

65. STOP — report the summary to the user
