---
description: Test the admin skills page — list bundled skills, create custom skill, view tabs
argument-hint: [url]
---

# EAGLE Admin Skills Test

Test the admin skills page with premium/admin credentials: tabs switch between Skills and Agent Prompts, bundled skills display with version badges, search filters work, and custom skill creation succeeds.

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

### Phase 2: Navigate to Skills

8. Navigate to `{URL}/admin/skills`
9. Wait up to 10 seconds for the page to load
10. Take a screenshot — save as `admin-skills.png`
11. Verify the skills page loaded. If redirected to `/` or `/login`, report **FAIL — Admin access denied** and stop
12. Verify the page contains:
    - A page heading with "Agent Skills & Prompts" or similar title
    - A search input field
    - Tab controls for "Skills" and "Agent Prompts"

### Phase 3: Verify Tabs

13. Verify the "Skills" tab is active by default (highlighted or selected state)
14. Verify the "Skills" tab shows a badge count (number of total skills)
15. Click the "Agent Prompts" tab
16. Wait up to 3 seconds for the tab content to switch
17. Take a screenshot — save as `admin-skills-prompts-tab.png`
18. Verify the Agent Prompts tab content is visible (agent prompt cards)
19. Click the "Skills" tab to return to the skills view
20. Wait up to 3 seconds for the tab content to switch

### Phase 4: Verify Bundled Skills

21. Look for a "Bundled Skills" section on the Skills tab
22. Verify at least one bundled skill card is visible
23. Verify each bundled skill card shows:
    - Skill name
    - A version badge (e.g., "v1")
    - A description
    - A Package icon indicator for bundled source
24. Take a screenshot — save as `admin-skills-bundled.png`

### Phase 5: Search Skills

25. Find the search input field
26. Type `document` into the search input
27. Wait up to 2 seconds for the filter to apply
28. Take a screenshot — save as `admin-skills-search.png`
29. Verify the skill list filters (shows fewer cards than before or highlights matching skills)
30. Clear the search field
31. Wait up to 2 seconds for the full list to restore

### Phase 6: Create Custom Skill

32. Click the "New Skill" button (Plus icon)
33. Wait up to 3 seconds for the modal to open
34. Take a screenshot — save as `admin-skills-new-modal.png`
35. Verify the modal shows:
    - A name input field
    - A display name input field
    - A description input field
    - An instructions/prompt body textarea
    - A visibility selector
    - A "Create" or "Save" button
    - A cancel/close button
36. Fill the name field with `test-skill`
37. Fill the display name field with `Test Skill`
38. Fill the description field with `Automated test skill for browser testing`
39. Fill the instructions/prompt body textarea with `You are a test skill. Respond with confirmation.`
40. Click the "Create" button
41. Wait up to 5 seconds for the modal to close and list to refresh

### Phase 7: Verify Custom Skill

42. Take a screenshot — save as `admin-skills-created.png`
43. Look for a "Custom Skills" section on the Skills tab
44. Verify "Test Skill" appears in the custom skills section
45. Verify "Test Skill" shows a "Draft" status badge (amber/yellow indicator)
46. Verify "Test Skill" shows the description "Automated test skill for browser testing"

### Phase 8: View Agent Prompts Tab

47. Click the "Agent Prompts" tab
48. Wait up to 3 seconds for the tab content to load
49. Take a screenshot — save as `admin-skills-agent-prompts.png`
50. Verify at least one agent prompt card is visible
51. Verify each agent prompt card shows:
    - Agent name
    - A version indicator
    - A Brain icon or similar indicator
52. Click on the first agent prompt card to open its detail view
53. Wait up to 3 seconds for the detail modal/panel to open
54. Take a screenshot — save as `admin-skills-agent-prompt-detail.png`
55. Verify the detail view shows the agent prompt content (text area or code block)
56. Close the detail view (click cancel or X)

### Phase 9: Report Results

Report **PASS** or **FAIL** for each check:

| Check | Expected | Actual | Result |
|-------|----------|--------|--------|
| Admin login succeeds | Redirected to chat, Premium tier shown | | |
| Skills page loads | /admin/skills loads with heading | | |
| Skills and Agent Prompts tabs visible | Two tabs with badge counts | | |
| Tab switching works | Content changes when clicking tabs | | |
| Bundled skills visible | At least one skill card with version badge | | |
| Search filters skills | Fewer cards shown after typing "document" | | |
| New Skill modal opens | Modal with name/description/instructions fields | | |
| Custom skill created | "Test Skill" appears in Custom Skills section | | |
| Custom skill shows Draft badge | Amber/yellow "Draft" status indicator | | |
| Agent Prompts tab shows cards | At least one agent prompt card visible | | |
| Agent prompt detail opens | Prompt content visible in detail view | | |

**Overall result**: PASS only if ALL checks pass.

If any check fails, include:
- Whether admin access was granted (or redirected to /login or /)
- Whether the skills list loaded or showed an error
- Whether tabs switched correctly
- Whether the create modal fields were present
- Whether the custom skill appeared with Draft status
- Any console errors
