---
description: Test the admin workspaces page — list, create, activate, view overrides
argument-hint: [url]
---

# EAGLE Admin Workspaces Test

Test the admin workspaces page with premium/admin credentials: workspace list loads, new workspace can be created, activation works, and overrides panel opens.

## Variables

| Variable | Value | Description |
| -------- | ----- | ----------- |
| SKILL | `claude-bowser` | Uses your real Chrome |
| MODE | `headed` | Visible browser |
| URL | `{PROMPT}` or `http://localhost:3000` | Base URL |
| ADMIN_EMAIL | `admin@example.com` | Admin test account |
| ADMIN_PASSWORD | `EagleAdmin2024!` | Admin test password |

If {PROMPT} contains a URL use it, otherwise default to `http://localhost:3000`.

## Workflow

### Phase 1: Ensure Admin Authentication

1. Navigate to `{URL}/login`
2. Wait up to 5 seconds for the page to load
3. If already redirected away (already authenticated), go to Phase 2
4. If the login page is shown:
   - Fill the email field with `admin@example.com`
   - Fill the password field with `EagleAdmin2024!`
   - Click "Sign in"
   - Wait up to 10 seconds for redirect
5. Take a screenshot — save as `admin-login.png`
6. Verify the user is now on `/` or `/chat` (not `/login`)
7. Verify the sidebar shows "Premium" tier badge or "admin" user identifier

### Phase 2: Navigate to Workspaces

8. Navigate to `{URL}/admin/workspaces`
9. Wait up to 10 seconds for the page to load
10. Take a screenshot — save as `admin-workspaces.png`
11. Verify the workspaces page loaded. If redirected to `/` or `/login`, report **FAIL — Admin access denied** and stop
12. Verify the page contains:
    - A page heading with "Workspaces"
    - A "New Workspace" button (with Plus icon)

### Phase 3: Verify Default Workspace

13. Look for workspace cards in the list
14. Verify at least one workspace card is visible
15. Check for a "Default" workspace card
16. Verify the default workspace shows an active badge (green indicator or "Active" text)
17. Verify each workspace card shows:
    - Workspace name
    - Visibility indicator (private/tenant/public icon)
    - A description or placeholder text
18. Take a screenshot — save as `admin-workspaces-default.png`

### Phase 4: Create New Workspace

19. Click the "New Workspace" button
20. Wait up to 3 seconds for the modal to open
21. Take a screenshot — save as `admin-workspaces-new-modal.png`
22. Verify the modal shows:
    - A name input field
    - A description input field
    - A visibility selector (private/tenant/public)
    - A "Create" or "Save" button
    - A cancel/close button
23. Fill the name field with `Test Workspace`
24. Fill the description field with `Automated test workspace`
25. Select visibility (leave as default "private" or select it)
26. Click the "Create" button
27. Wait up to 5 seconds for the modal to close and list to refresh

### Phase 5: Verify New Workspace

28. Take a screenshot — save as `admin-workspaces-created.png`
29. Verify the workspace list now includes "Test Workspace"
30. Verify "Test Workspace" shows the correct visibility icon (private/lock)
31. Verify "Test Workspace" shows a description of "Automated test workspace"

### Phase 6: Activate Workspace

32. Find the activate button on "Test Workspace" (CheckCircle2 icon or "Activate" text)
33. Click the activate button
34. Wait up to 3 seconds for the list to refresh
35. Take a screenshot — save as `admin-workspaces-activated.png`
36. Verify "Test Workspace" now shows the active badge
37. Verify the previously active workspace no longer shows the active badge

### Phase 7: View Overrides

38. Find the expand/chevron button on "Test Workspace" to view overrides
39. Click the expand button (ChevronDown icon)
40. Wait up to 3 seconds for the overrides panel to open
41. Take a screenshot — save as `admin-workspaces-overrides.png`
42. Verify the overrides section is visible (may show an empty list or override entries)
43. Click the collapse button (ChevronUp icon) to close the overrides panel

### Phase 8: Cleanup

44. Find the delete button (Trash2 icon) on "Test Workspace"
45. Click the delete button
46. Wait up to 3 seconds for the list to refresh
47. Take a screenshot — save as `admin-workspaces-deleted.png`
48. Verify "Test Workspace" is no longer in the list

### Phase 9: Report Results

Report **PASS** or **FAIL** for each check:

| Check | Expected | Actual | Result |
|-------|----------|--------|--------|
| Admin login succeeds | Redirected to chat, Premium tier shown | | |
| Workspaces page loads | /admin/workspaces loads with heading | | |
| New Workspace button visible | Plus icon button present | | |
| Default workspace visible | At least one workspace with active badge | | |
| Workspace cards show details | Name, visibility icon, description | | |
| Create modal opens | Modal with name/description/visibility fields | | |
| New workspace created | "Test Workspace" appears in list | | |
| Activate workspace works | Active badge moves to Test Workspace | | |
| Overrides panel opens | Expand button reveals overrides section | | |
| Delete workspace works | Test Workspace removed from list | | |

**Overall result**: PASS only if ALL checks pass.

If any check fails, include:
- Whether admin access was granted (or redirected to /login or /)
- Whether the workspace list loaded or showed an error
- Whether the create modal fields were present
- Whether activation changed the active badge
- Any console errors
