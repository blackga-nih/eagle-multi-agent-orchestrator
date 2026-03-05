---
description: Test the Ctrl+K command palette — open, search, select commands, close with Escape
argument-hint: [url]
---

# EAGLE Command Palette Test

Test the Ctrl+K command palette: open via keyboard shortcut, verify command categories and search filtering, select a command to populate chat input, and close via Escape or toggle.

## Variables

| Variable | Value | Description |
| -------- | ----- | ----------- |
| SKILL | `claude-bowser` | Uses your real Chrome |
| MODE | `headed` | Visible browser |
| URL | `{PROMPT}` or `http://localhost:3000` | Base URL |

If {PROMPT} contains a URL use it, otherwise default to `http://localhost:3000`.

## Workflow

### Phase 1: Load Chat Page

1. Navigate to `{URL}/chat`
2. Wait up to 10 seconds for the page to finish loading
3. Take a screenshot — save as `palette-initial.png`
4. Verify the chat interface loaded. Look for:
   - A text input box (placeholder text: "Message EAGLE..." or similar)
   - The EAGLE Chat header
5. If the page shows a login form instead of the chat, navigate to `{URL}` first and attempt to proceed (dev mode should auto-authenticate)

### Phase 2: Open Command Palette

6. Press `Control+k` to open the command palette
7. Wait up to 3 seconds for the overlay to appear
8. Take a screenshot — save as `palette-open.png`
9. Verify the command palette overlay appeared:
   - A fixed overlay with a semi-transparent backdrop is visible
   - A search input with placeholder "Search commands..." is present
   - An X (close) button is visible in the header
   - A footer showing "Click a command to insert it into the chat" and "Esc to close"

### Phase 3: Verify Commands Listed

10. Check that command categories are displayed as uppercase labels. Expect these categories:
    - Documents
    - Compliance
    - Research
    - Workflow
    - Admin
    - Info
11. Verify that commands appear as pill-shaped buttons with icons and text labels
12. Hover over a command pill and verify a tooltip with the command description appears
13. Take a screenshot — save as `palette-commands.png`

### Phase 4: Search Commands

14. Click the search input field to focus it
15. Type `SOW` in the search input
16. Wait 1 second for filtering to apply
17. Take a screenshot — save as `palette-search-sow.png`
18. Verify:
    - The command list is filtered — fewer commands are shown than the full list
    - At least one document-related command is visible in the results
    - Categories with no matching commands are hidden
19. If no results appear, verify the "No commands match" message is displayed

### Phase 5: Clear Search

20. Clear the search input (select all text and delete, or triple-click and press Backspace)
21. Wait 1 second for the full list to return
22. Take a screenshot — save as `palette-cleared.png`
23. Verify the full list of commands across all categories is visible again

### Phase 6: Select a Command

24. Find a command pill button (e.g., one in the Documents category) and click it
25. Take a screenshot — save as `palette-after-select.png`
26. Verify:
    - The command palette overlay has closed (no longer visible)
    - The chat input box now contains the selected command text (e.g., `/document:SOW` or similar slash command)

### Phase 7: Close with Escape

27. Press `Control+k` to reopen the command palette
28. Wait up to 3 seconds for the overlay to appear
29. Verify the palette is open (search input visible)
30. Press `Escape`
31. Take a screenshot — save as `palette-escape-close.png`
32. Verify the command palette overlay has closed completely

### Phase 8: Toggle Behavior

33. Press `Control+k` to open the palette
34. Wait up to 3 seconds for the overlay to appear
35. Verify the palette is open
36. Press `Control+k` again
37. Wait 1 second
38. Take a screenshot — save as `palette-toggle-close.png`
39. Verify the command palette has closed (Ctrl+K toggles open/close)

### Phase 9: Report Results

Report **PASS** or **FAIL** for each check:

| Check | Expected | Actual | Result |
|-------|----------|--------|--------|
| Page loaded | Chat UI visible | | |
| Palette opens on Ctrl+K | Overlay with search input appears | | |
| Categories displayed | Documents, Compliance, Research, Workflow, Admin, Info | | |
| Command pills visible | Buttons with icons and text labels | | |
| Tooltips on hover | Description shown on hover | | |
| Search filters commands | Typing "SOW" reduces visible commands | | |
| Clear search restores list | Full command list returns | | |
| Select command populates input | Palette closes, chat input has command text | | |
| Escape closes palette | Overlay removed from view | | |
| Ctrl+K toggle closes palette | Second Ctrl+K closes open palette | | |

**Overall result**: PASS only if ALL checks pass.

If any check fails, include:
- Whether the palette overlay appeared at all
- Which categories were missing or empty
- Whether search filtering worked
- Whether the selected command appeared in the chat input
- Any console errors (if accessible)
