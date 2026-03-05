---
description: Test the admin templates page — list templates, filter by type, create custom template
argument-hint: [url]
---

# EAGLE Admin Templates Test

Test the admin templates page with premium/admin credentials: template list loads with doc type badges, search filtering works, source badges distinguish bundled vs custom, and new custom template creation succeeds.

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

### Phase 2: Navigate to Templates

8. Navigate to `{URL}/admin/templates`
9. Wait up to 10 seconds for the page to load
10. Take a screenshot — save as `admin-templates.png`
11. Verify the templates page loaded. If redirected to `/` or `/login`, report **FAIL — Admin access denied** and stop
12. Verify the page contains:
    - A page heading with "Document Templates"
    - A search input field
    - A "New Template" button (with Plus icon)

### Phase 3: Verify Template List

13. Look for template cards in the list
14. Verify at least one template card is visible
15. Verify each template card shows:
    - Template name or display name
    - A doc type badge with color coding (e.g., blue for SOW, green for IGCE, purple for Market Research, amber for Acquisition Plan)
    - A version indicator (e.g., "v1")
    - A date (updated at)
16. Take a screenshot — save as `admin-templates-list.png`

### Phase 4: Verify Source Badges

17. Look for source badges on template cards
18. Verify at least one card shows a "Bundled" source badge (with Package icon)
19. Note whether any "Custom" source badges are present (may not exist yet)
20. Verify the doc type badges use distinct colors for different types:
    - SOW: blue badge
    - IGCE: green badge
    - Market Research: purple badge
    - Acquisition Plan: amber badge
21. Take a screenshot — save as `admin-templates-badges.png`

### Phase 5: Search Templates

22. Find the search input field
23. Type `sow` into the search input
24. Wait up to 2 seconds for the filter to apply
25. Take a screenshot — save as `admin-templates-search.png`
26. Verify the template list filters (shows fewer cards matching "sow" in name or doc type)
27. Clear the search field
28. Wait up to 2 seconds for the full list to restore

### Phase 6: Create Custom Template

29. Click the "New Template" button (Plus icon)
30. Wait up to 3 seconds for the modal to open
31. Take a screenshot — save as `admin-templates-new-modal.png`
32. Verify the modal shows:
    - A doc type selector/dropdown
    - A display name input field
    - A template body textarea
    - A "Create" or "Save" button
    - A cancel/close button
33. Select a doc type (choose "sow" or the first available option)
34. Fill the display name field with `Test SOW Template`
35. Fill the template body textarea with `# Statement of Work\n\nThis is an automated test template.`
36. Click the "Create" button
37. Wait up to 5 seconds for the modal to close and list to refresh

### Phase 7: Verify Custom Template

38. Take a screenshot — save as `admin-templates-created.png`
39. Verify the template list now includes "Test SOW Template"
40. Verify "Test SOW Template" shows a "Custom" source badge
41. Verify "Test SOW Template" shows the correct doc type badge (SOW, blue)
42. Verify "Test SOW Template" shows version "v1"

### Phase 8: Report Results

Report **PASS** or **FAIL** for each check:

| Check | Expected | Actual | Result |
|-------|----------|--------|--------|
| Admin login succeeds | Redirected to chat, Premium tier shown | | |
| Templates page loads | /admin/templates loads with heading | | |
| Template cards visible | At least one card with name and doc type | | |
| Doc type badges colored | Distinct colors for SOW, IGCE, etc. | | |
| Source badges present | "Bundled" badge with Package icon | | |
| Version indicators shown | Version number on each card | | |
| Search filters templates | Fewer cards shown after typing "sow" | | |
| New Template modal opens | Modal with doc type/name/body fields | | |
| Custom template created | "Test SOW Template" appears in list | | |
| Custom badge shown | "Custom" source badge on new template | | |

**Overall result**: PASS only if ALL checks pass.

If any check fails, include:
- Whether admin access was granted (or redirected to /login or /)
- Whether the template list loaded or showed an error
- Whether doc type badges were color-coded correctly
- Whether the create modal fields were present
- Whether the custom template appeared with correct badges
- Any console errors
