---
description: Test the chat activity panel — tabs, collapse/expand, agent logs, tool use cards during streaming
argument-hint: [url]
---

# EAGLE Activity Panel & Tool Use Display Test

Verify the chat activity panel renders correctly with all three tabs (Documents, Notifications, Agent Logs), supports collapse/expand, and that tool use cards appear with correct status indicators during streaming.

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
3. Take a screenshot — save as `activity-panel-initial.png`
4. Verify the chat interface loaded. Look for:
   - A text input box (placeholder text: "Message EAGLE..." or similar)
   - The EAGLE Chat header
   - A backend status indicator (green "Multi-Agent Online" or similar)
5. If the page shows "Backend Offline" in the status indicator, report **FAIL — Backend not running** and stop
6. If you see a login form instead of the chat, navigate to `{URL}` first and attempt to proceed (dev mode should auto-authenticate)

### Phase 2: Verify Activity Panel Visible

7. Look for the right-side activity panel adjacent to the chat message area
8. The panel should have a vertical tab bar or header with tab buttons
9. Take a screenshot — save as `activity-panel-visible.png`
10. If no panel is visible, look for a collapsed strip or toggle button (PanelRightOpen icon) on the right edge and click it to open the panel

### Phase 3: Verify Panel Tabs

11. Locate the three tab buttons in the activity panel header:
    - **Documents** (FileText icon)
    - **Notifications** (Bell icon)
    - **Agent Logs** (Terminal icon)
12. Take a screenshot — save as `activity-panel-tabs.png`
13. If any of the three tabs are missing, report **FAIL — Missing tab(s)** with details

### Phase 4: Switch Tabs

14. Click the **Documents** tab
15. Verify the Documents tab content appears. Look for either:
    - The empty state: "No documents generated yet." with subtext "Documents will appear here as they're created."
    - Or a list of document cards showing title, document type, and status
16. Take a screenshot — save as `activity-panel-documents-tab.png`

17. Click the **Notifications** tab
18. Verify the Notifications tab content appears. Look for either:
    - The empty state: "No notifications yet." or similar
    - Or a list of notification entries
19. Take a screenshot — save as `activity-panel-notifications-tab.png`

20. Click the **Agent Logs** tab
21. Verify the Agent Logs tab content appears. Look for either:
    - An empty state or placeholder text
    - Or log entries from previous interactions
22. Take a screenshot — save as `activity-panel-logs-tab.png`

### Phase 5: Collapse Panel

23. Look for a collapse button in the activity panel header — it should be a left-pointing chevron icon (PanelRightClose) or similar toggle button
24. Click the collapse button
25. Verify the panel collapses to a thin vertical strip or disappears, giving the chat area more horizontal space
26. Take a screenshot — save as `activity-panel-collapsed.png`

### Phase 6: Expand Panel

27. Look for the expand button on the collapsed strip — it should be a right-pointing chevron icon (PanelRightOpen) or similar toggle button
28. Click the expand button
29. Verify the panel returns to full width with tabs visible again
30. Take a screenshot — save as `activity-panel-expanded.png`

### Phase 7: Send Message and Watch Tool Use

31. Click the chat input box to focus it
32. Type the message: `Search FAR Part 15 for source selection`
33. Press Enter or click the Send button
34. Note the exact time the message was sent
35. Wait up to 60 seconds for the response to complete. During streaming, watch for:
    - **Tool use cards** appearing inline in the message area below the user message
    - Each tool card should show a tool name (e.g., "Searching FAR/DFARS", "Compliance Matrix", "Policy Lookup", or similar)
    - A **status indicator** on each tool card: spinning/pulsing animation while running, checkmark when done
    - The **Agent Logs** tab in the activity panel updating with new log entries during streaming
36. Take a screenshot during streaming if possible — save as `activity-panel-streaming.png`
37. Click the **Agent Logs** tab while streaming is active (if not already selected)
38. Take a screenshot showing agent log entries — save as `activity-panel-agent-logs-streaming.png`

### Phase 8: Verify Tool Use Card Details

39. After the response completes (streaming indicator returns to "Ready"), examine the tool use cards in the message area
40. For each tool card visible, check:
    - **Tool name** is displayed (human-friendly label, not raw function name)
    - **Completion status** shows a success icon (checkmark) or error icon
    - **Input summary** is shown below the tool name (e.g., query text, document type)
    - If the card has an expand/collapse chevron, click it to expand and verify details are shown
41. Take a screenshot — save as `activity-panel-tool-cards-complete.png`
42. If no tool cards appeared during the response, note this in the report (the backend may not have invoked tools for this query)

### Phase 9: Report Results

Report **PASS** or **FAIL** for each check:

| Check | Expected | Actual | Result |
|-------|----------|--------|--------|
| Page loaded | Chat UI visible | | |
| Activity panel visible | Right-side panel present | | |
| Documents tab exists | Tab button with FileText icon | | |
| Notifications tab exists | Tab button with Bell icon | | |
| Agent Logs tab exists | Tab button with Terminal icon | | |
| Documents tab content | Empty state or document list | | |
| Notifications tab content | Empty state or notification list | | |
| Agent Logs tab content | Empty state or log entries | | |
| Panel collapse | Panel collapses to strip | | |
| Panel expand | Panel returns to full width | | |
| Message sent | User message appeared | | |
| Tool cards appeared | At least one tool card during streaming | | |
| Tool card name | Human-friendly tool label shown | | |
| Tool card status | Running indicator then completion icon | | |
| Agent Logs updated | New entries during streaming | | |
| Streaming completed | Returned to Ready state | | |

**Overall result**: PASS only if ALL checks pass.

If any check fails, include:
- Which tab(s) were missing or not rendering
- Whether the collapse/expand toggle was found
- The number and names of tool cards that appeared
- Whether agent logs populated during streaming
- Any error messages visible in the UI
- Console errors (if accessible)
