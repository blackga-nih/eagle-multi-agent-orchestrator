---
description: Test the Ctrl+J feedback modal — open, select type, submit comment, close
argument-hint: [url]
---

# EAGLE Feedback Modal Test

Test the Ctrl+J feedback modal: open via keyboard shortcut, select feedback type pills, enter a comment, submit feedback, and verify success state and modal reset behavior.

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
3. Take a screenshot — save as `feedback-initial.png`
4. Verify the chat interface loaded. Look for:
   - A text input box (placeholder text: "Message EAGLE..." or similar)
   - The EAGLE Chat header
5. If the page shows a login form instead of the chat, navigate to `{URL}` first and attempt to proceed (dev mode should auto-authenticate)

### Phase 2: Open Feedback Modal

6. Press `Control+j` to open the feedback modal
7. Wait up to 3 seconds for the modal to appear
8. Take a screenshot — save as `feedback-open.png`
9. Verify the feedback modal appeared:
   - A modal overlay is visible
   - The title "Send Feedback" is displayed
   - A textarea with placeholder "Tell us more..." is present
   - A "Cancel" button and a "Submit" button are in the footer

### Phase 3: Verify Feedback Types

10. Look for the "Type" label followed by feedback type pill buttons
11. Verify these 4 feedback types are visible as pill-shaped buttons:
    - Helpful
    - Inaccurate
    - Incomplete
    - Too verbose
12. Verify all pills are in their default unselected state (white background, gray border)
13. Take a screenshot — save as `feedback-types.png`

### Phase 4: Select Feedback Type

14. Click the "Helpful" pill button
15. Wait 1 second for the UI to update
16. Take a screenshot — save as `feedback-helpful-selected.png`
17. Verify the "Helpful" pill is now highlighted (blue background, white text, blue border)
18. Verify the other pills remain unselected (white background)

### Phase 5: Toggle Feedback Type

19. Click the "Helpful" pill again to deselect it
20. Wait 1 second
21. Verify the "Helpful" pill returns to its unselected state (white background)
22. Click the "Inaccurate" pill button
23. Wait 1 second
24. Take a screenshot — save as `feedback-inaccurate-selected.png`
25. Verify the "Inaccurate" pill is now highlighted (blue background, white text)
26. Verify "Helpful" remains unselected

### Phase 6: Enter Comment

27. Click the textarea (placeholder "Tell us more...")
28. Type `Great acquisition guidance!`
29. Take a screenshot — save as `feedback-comment.png`
30. Verify the text appears in the textarea
31. Verify the "Submit" button is now enabled (not grayed out / disabled)

### Phase 7: Submit Feedback

32. Click the "Submit" button
33. Wait up to 5 seconds for the submission to complete
34. Take a screenshot — save as `feedback-submitted.png`
35. Verify the success state:
    - A green check mark icon is visible (emerald circle with check)
    - The text "Thanks!" is displayed
    - The Cancel/Submit footer buttons are no longer visible
36. Wait up to 2 seconds — the modal should auto-close after showing the success state

### Phase 8: Close Modal

37. Take a screenshot — save as `feedback-closed.png`
38. Verify the modal has closed automatically after the success state
39. If the modal is still open, click the X button or press `Escape` to close it
40. Verify the modal overlay is no longer visible

### Phase 9: Reopen After Submit

41. Press `Control+j` to reopen the feedback modal
42. Wait up to 3 seconds for the modal to appear
43. Take a screenshot — save as `feedback-reopen.png`
44. Verify the modal opens in a fresh state:
    - The textarea is empty (no previous comment text)
    - No feedback type pill is selected (all in default state)
    - The "Submit" button is present (not stuck in success/thanks state)
    - The title still reads "Send Feedback"
45. Close the modal by pressing `Escape`

### Phase 10: Cancel Without Submitting

46. Press `Control+j` to open the feedback modal again
47. Wait up to 3 seconds for the modal to appear
48. Click the textarea and type `This will not be submitted`
49. Click the "Incomplete" pill to select it
50. Take a screenshot — save as `feedback-cancel.png`
51. Click the "Cancel" button in the footer
52. Wait 1 second
53. Take a screenshot — save as `feedback-cancelled.png`
54. Verify the modal has closed
55. Press `Control+j` to reopen and verify the form is reset (empty textarea, no type selected)
56. Take a screenshot — save as `feedback-reset-after-cancel.png`
57. Close the modal by pressing `Escape`

### Phase 11: Report Results

Report **PASS** or **FAIL** for each check:

| Check | Expected | Actual | Result |
|-------|----------|--------|--------|
| Page loaded | Chat UI visible | | |
| Modal opens on Ctrl+J | Modal with "Send Feedback" title appears | | |
| 4 feedback types visible | Helpful, Inaccurate, Incomplete, Too verbose pills | | |
| Select type highlights pill | Blue background on selected pill | | |
| Toggle deselects type | Clicking selected pill returns to default | | |
| Comment textarea works | Typed text appears in field | | |
| Submit succeeds | Green check + "Thanks!" shown | | |
| Modal auto-closes after submit | Modal disappears after success state | | |
| Reopen shows fresh state | Empty form, no stuck success state | | |
| Cancel closes modal | Modal closes without submitting | | |
| Form resets after cancel | Reopened modal has empty fields | | |

**Overall result**: PASS only if ALL checks pass.

If any check fails, include:
- Whether the modal appeared at all on Ctrl+J
- Which feedback type pills were missing
- Whether the submit request returned an error
- Whether the success state displayed correctly
- Whether the form reset properly after close/cancel
- Any console errors (if accessible)
