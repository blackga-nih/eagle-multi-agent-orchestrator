---
description: Test the EAGLE admin dashboard — stat cards, system health, user management table, cost tracking, requires admin login
argument-hint: [url]
---

# EAGLE Admin Dashboard Test

Test the admin dashboard with premium/admin credentials: stat cards load, system health shows, user management table is functional, and cost tracking data renders.

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

### Phase 2: Navigate to Admin Dashboard

8. Navigate to `{URL}/admin`
9. Wait up to 10 seconds for the page to load
10. Take a screenshot — save as `admin-dashboard.png`
11. Verify the admin dashboard loaded. If redirected to `/` or `/login`, report **FAIL — Admin access denied** and stop
12. Verify the dashboard contains:
    - A page title or heading indicating this is the admin area
    - Stat cards (expect 4: Active Workflows, Total Value, Documents Generated, Avg. Completion Time)

### Phase 3: Verify Stat Cards

13. Verify 4 stat cards are visible with:
    - **Active Workflows**: a number + change indicator (e.g., "+2 this week")
    - **Total Value**: a currency amount + change
    - **Documents Generated**: a count + change
    - **Avg. Completion Time**: a duration + change
14. Verify the numbers are not "0" or "N/A" (should show placeholder data at minimum)
15. Take a screenshot — save as `admin-stat-cards.png`

### Phase 4: Verify System Health Panel

16. Look for a "System Health" section on the dashboard
17. Verify it shows status indicators for:
    - AI Services (should be green/operational)
    - Database (should be green/connected)
    - API Rate Limit (any status)
18. Take a screenshot — save as `admin-system-health.png`

### Phase 5: Navigate to User Management

19. Find the "Manage Users" quick action or navigate to `{URL}/admin/users`
20. Wait up to 5 seconds for the page to load
21. Take a screenshot — save as `admin-users.png`
22. Verify the users page loaded with:
    - A table or list of users
    - Column headers (User, Role, Division, Last Active, Actions)
    - At least 1 user row visible
23. Test the search: type `test` into the search input
24. Wait 1 second for filter to apply
25. Take a screenshot — save as `admin-users-search.png`
26. Verify the table filters (shows fewer rows or highlights matching users)
27. Clear the search field

### Phase 6: Test User Edit Modal

28. Find the edit icon (pencil) on any user row and click it
29. Wait up to 3 seconds for the modal to open
30. Take a screenshot — save as `admin-user-edit.png`
31. Verify the edit modal shows:
    - User name / display name field
    - Role dropdown or selector
    - Email field
    - A "Save Changes" or "Update" button
    - A cancel/close button
32. Close the modal without saving (click cancel or X)

### Phase 7: Navigate to Cost Dashboard

33. Navigate to `{URL}/admin/costs`
34. Wait up to 5 seconds for the page to load
35. Take a screenshot — save as `admin-costs.png`
36. Verify the costs page loaded with:
    - Date range selector (7d, 30d, 90d buttons)
    - Summary cards (Total Cost, Avg Cost Per Request, Total Tokens, Active Users)
    - A usage details table
37. Click the "30d" date range button
38. Wait up to 3 seconds for data to refresh
39. Take a screenshot — save as `admin-costs-30d.png`
40. Verify the summary cards update (values may change with different date range)
41. Find the "Refresh" button and click it
42. Verify a spinner appears briefly during the refresh

### Phase 8: Verify Sub-Navigation

43. Navigate back to `{URL}/admin`
44. Find the Quick Actions section on the dashboard
45. Verify these links/buttons are present and navigable:
    - Test Results → `/admin/tests`
    - Document Templates → `/admin/templates`
    - Agent Skills → `/admin/skills`
46. Click "Test Results" and verify the page loads without error
47. Take a screenshot — save as `admin-test-results.png`
48. Navigate back to `{URL}/admin`

### Phase 9: Report Results

Report **PASS** or **FAIL** for each check:

| Check | Expected | Actual | Result |
|-------|----------|--------|--------|
| Admin login succeeds | Redirected to chat, Premium tier shown | | |
| Admin dashboard accessible | /admin loads (not redirected away) | | |
| 4 stat cards visible | All cards with numbers + change indicators | | |
| System health panel | AI Services + Database status shown | | |
| Users page loads | Table with user rows + column headers | | |
| User search filters table | Fewer rows shown after searching | | |
| Edit modal opens | Modal with name/role/email fields | | |
| Costs page loads | Date selector + summary cards + table | | |
| Date range selector works | 30d updates summary values | | |
| Refresh button works | Spinner visible on click | | |
| Sub-nav links work | Test Results page loads | | |

**Overall result**: PASS only if ALL checks pass.

If any check fails, include:
- Whether admin access was granted (or redirected to /login or /)
- Which stat cards were missing or showed 0/N/A
- Whether the users table was empty
- Whether the cost table loaded data or showed an error
- Any console errors
