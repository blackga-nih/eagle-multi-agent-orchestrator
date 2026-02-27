---
description: Test EAGLE document generation and download — trigger doc creation via chat, verify /documents list, open viewer, download as Word
argument-hint: [url]
---

# EAGLE Document Generation + Download Test

Test the full document lifecycle: ask EAGLE to generate a SOW via chat, verify the document appears in /documents, open the document viewer, use the chat sidebar to refine it, and download as Word.

## Variables

| Variable | Value | Description |
| -------- | ----- | ----------- |
| SKILL | `claude-bowser` | Uses your real Chrome |
| MODE | `headed` | Visible browser |
| URL | `{PROMPT}` or `http://localhost:3000` | Base URL |

If {PROMPT} contains a URL use it, otherwise default to `http://localhost:3000`.

## Workflow

### Phase 1: Load Chat and Start Fresh

1. Navigate to `{URL}/chat`
2. Wait up to 10 seconds for the page to load
3. If a login page appears, report **FAIL — Not authenticated** and stop
4. Click "New Chat" in the sidebar to start a clean session
5. Wait for the welcome screen ("Welcome to EAGLE") to appear
6. Take a screenshot — save as `doc-initial.png`

### Phase 2: Request Document Generation via Chat

7. Click the chat textarea to focus it
8. Type the following message exactly:
   `Generate a Statement of Work for procuring a CT scanner at NCI. The estimated value is $500,000.`
9. Take a screenshot before sending — save as `doc-before-send.png`
10. Press Enter to send
11. Verify the user message appears in a right-aligned bubble
12. Verify the textarea becomes disabled ("Waiting for response…")

### Phase 3: Wait for Document Generation Response

13. Wait up to 60 seconds for EAGLE to respond (document generation may take longer than a chat response)
14. Watch for the EAGLE response bubble to appear
15. Wait until the textarea becomes re-enabled
16. Take a screenshot — save as `doc-response.png`
17. Look for one of the following in or below the EAGLE response:
    - A document card/attachment below the message (shows doc type, title, view button)
    - Inline text confirming a document was created (e.g., "I've generated a Statement of Work")
    - A clickable link or button to view the document

### Phase 4: Navigate to Documents Page

18. Navigate to `{URL}/documents`
19. Wait up to 5 seconds for the page to load
20. Take a screenshot — save as `doc-list.png`
21. Verify the documents page loaded. Look for:
    - A list or grid of documents
    - At minimum 1 document entry (the SOW just generated)
    - Document entries show: title, document type badge, status, timestamp
22. If the list is empty, check if the session saved correctly — try refreshing the page once

### Phase 5: Open Document Viewer

23. Click on the most recent document in the list (the SOW generated in Phase 2)
24. Wait up to 5 seconds for the document viewer to load
25. Take a screenshot — save as `doc-viewer.png`
26. Verify the document viewer loaded with:
    - **Left panel** (~65% width): document title, document type label, View/Edit toggle, Download button, document content (markdown)
    - **Right panel** (~35% width): "Document Assistant" chat header, chat messages, textarea input
27. Verify the document content is not empty — it should contain SOW sections (e.g., Overview, Scope, Requirements, Deliverables, or similar government acquisition language)
28. If a yellow/amber "template hydration" banner appears (placeholders remain), note it but continue

### Phase 6: Use Document Chat to Refine

29. Click the textarea in the **right panel** (Document Assistant chat)
30. Type: `Add an implementation timeline section with key milestones.`
31. Press Enter to send
32. Wait up to 45 seconds for the document assistant to respond
33. Take a screenshot during/after response — save as `doc-refined.png`
34. Verify:
    - The right panel shows the assistant response
    - The left panel document content updates (may show a green "Updated" badge briefly)
    - The document now has more content than before

### Phase 7: Download Document as Word

35. Find the Download button in the left panel header area
36. Take a screenshot showing the Download button — save as `doc-download-ready.png`
37. Click the Download button
38. If a dropdown appears with format options (Word .docx, PDF .pdf), click "Download as Word" or ".docx"
39. Wait up to 10 seconds for the download to initiate
40. Verify a file download starts in the browser (browser download bar or notification)
41. Take a screenshot — save as `doc-downloaded.png`
42. Note the downloaded filename (should be `{Document Title}.docx`)

### Phase 8: Report Results

Report **PASS** or **FAIL** for each check:

| Check | Expected | Actual | Result |
|-------|----------|--------|--------|
| Chat page loaded | Welcome screen visible | | |
| Document request sent | User message bubble + textarea disabled | | |
| EAGLE response received | Response with doc confirmation or doc card | | |
| Documents page accessible | /documents loads with list | | |
| Generated doc in list | SOW entry visible with title + type badge | | |
| Document viewer loads | Left panel (content) + right panel (chat) | | |
| Document content present | Non-empty SOW markdown content | | |
| Document refinement works | Chat request updates document content | | |
| Download initiated | File download starts in browser | | |
| Downloaded filename | Ends in .docx with meaningful title | | |

**Overall result**: PASS only if ALL checks pass.

If any check fails, include:
- Whether the document card appeared in the chat response
- Whether /documents showed the doc or was empty
- Whether the viewer showed blank content
- Whether the download button was found and clickable
- Any error messages or console errors
