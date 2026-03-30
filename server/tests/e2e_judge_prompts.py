"""
Judge prompt templates for vision-based UI evaluation.

Each prompt tells the Sonnet vision model what to evaluate in a screenshot
and how to return structured JSON results.
"""

# ---------------------------------------------------------------------------
# General UI evaluation prompt (used when no page-specific prompt matches)
# ---------------------------------------------------------------------------
GENERAL_UI_PROMPT = """You are a QA judge evaluating a screenshot of the EAGLE NCI Acquisition Assistant web application.

Evaluate the following criteria:

1. LAYOUT: Is the page structure correct? No overlapping elements, proper spacing, no content overflows?
2. CONTENT: Does visible text look real and appropriate? No placeholder text, no "undefined", no raw JSON or stack traces?
3. FUNCTIONALITY: Are interactive elements (buttons, inputs, dropdowns) visible and properly styled? Do they look clickable/usable?
4. BRANDING: Does the page match expected EAGLE/NCI styling? Blue theme, consistent colors, proper header/sidebar?
5. ACCESSIBILITY: Sufficient contrast, readable font sizes (not too small), proper visual hierarchy?
6. ERRORS: Any visible error states, blank white screens, 404 pages, JS error overlays, or loading spinners stuck indefinitely?

Expected page context: {page_description}
Test step: {step_description}

Return ONLY valid JSON with this exact structure (no markdown, no explanation outside the JSON):
{{"verdict": "pass"|"fail"|"warning", "confidence": 0.0-1.0, "reasoning": "brief explanation", "ui_quality_score": 1-10, "issues": ["issue1", "issue2"]}}

Scoring guide:
- "pass" (score 7-10): Page looks correct and functional. Minor cosmetic issues are OK.
- "warning" (score 4-6): Something looks off but the page is usable. Missing elements, odd spacing, etc.
- "fail" (score 1-3): Page is broken, blank, shows errors, or is clearly wrong for the expected context."""

# ---------------------------------------------------------------------------
# Page-specific prompts with expected elements
# ---------------------------------------------------------------------------
PAGE_PROMPTS: dict[str, str] = {
    "login": """You are evaluating the EAGLE login page.

Expected elements:
- Login form with email and password fields
- Submit/Sign In button
- EAGLE branding or NCI logo
- Clean, centered layout

{page_description}
Step: {step_description}

Return ONLY valid JSON:
{{"verdict": "pass"|"fail"|"warning", "confidence": 0.0-1.0, "reasoning": "brief explanation", "ui_quality_score": 1-10, "issues": ["issue1"]}}""",

    "home": """You are evaluating the EAGLE home/landing page after login.

Expected elements:
- Welcome message or greeting
- Feature cards or quick action buttons (Acquisition Intake, Document Generation, etc.)
- Sidebar navigation with session list
- Header with user info or settings

{page_description}
Step: {step_description}

Return ONLY valid JSON:
{{"verdict": "pass"|"fail"|"warning", "confidence": 0.0-1.0, "reasoning": "brief explanation", "ui_quality_score": 1-10, "issues": ["issue1"]}}""",

    "chat": """You are evaluating the EAGLE chat interface.

Expected elements:
- Chat message area showing conversation history
- Text input area (textarea) at the bottom for user messages
- Send button
- Sidebar with session list
- If agent has responded: EAGLE label on agent messages, formatted text content
- If streaming: typing indicator (bouncing dots) or streaming cursor

{page_description}
Step: {step_description}

Return ONLY valid JSON:
{{"verdict": "pass"|"fail"|"warning", "confidence": 0.0-1.0, "reasoning": "brief explanation", "ui_quality_score": 1-10, "issues": ["issue1"]}}""",

    "intake": """You are evaluating the EAGLE OA intake workflow page.

Expected elements:
- Intake form fields or guided workflow steps
- Progress indicator if multi-step
- Input fields for acquisition details (description, dollar amount, timeline)
- Navigation buttons (Next, Back, Submit)

{page_description}
Step: {step_description}

Return ONLY valid JSON:
{{"verdict": "pass"|"fail"|"warning", "confidence": 0.0-1.0, "reasoning": "brief explanation", "ui_quality_score": 1-10, "issues": ["issue1"]}}""",

    "documents": """You are evaluating the EAGLE documents page.

Expected elements:
- Document list or grid view
- Document cards with titles, types, dates
- Status tabs (All Documents, Not Started, In Progress, Draft, Approved)
- Search bar and filter controls
- Document actions (view, download, edit)
- "Templates" and "+ New Document" buttons in the header

CRITICAL CHECKS — any of these MUST result in verdict "fail":

1. SIDECAR FILE LEAK: Look for document entries whose filename ends with ".content.md"
   (e.g., "foo.docx.content.md", "bar.xlsx.content.md"). These are internal sidecar
   metadata files and should NOT appear in the user-facing document list. If you see ANY
   entries with ".content.md" in the filename, FAIL and list each one in issues as
   "Sidecar file visible: <filename>".

2. TEMPLATE JARGON: If any visible document content, title, or preview shows raw template
   placeholders such as {{{{VARIABLE_NAME}}}}, {{{{placeholder}}}}, <<FIELD>>,
   or bracketed markers like "[Something - To Be Filled]", FAIL and report
   "Template jargon visible: <pattern found>".

3. DUPLICATE ENTRIES: If the same base document appears twice — once as the real file
   (e.g., "report.docx") and once as its sidecar (e.g., "report.docx.content.md") —
   FAIL with "Duplicate document entries: <base filename>".

4. 404 OR ERROR PAGES: If the screenshot shows a 404 error, "page could not be found",
   blank white screen, or error overlay, FAIL immediately.

{page_description}
Step: {step_description}

Return ONLY valid JSON:
{{"verdict": "pass"|"fail"|"warning", "confidence": 0.0-1.0, "reasoning": "brief explanation", "ui_quality_score": 1-10, "issues": ["issue1"]}}""",

    "admin": """You are evaluating the EAGLE admin dashboard.

Expected elements:
- Dashboard header with title
- Statistics cards or summary metrics
- Navigation to sub-pages (Skills, Templates, Traces, Users, Costs)
- Data tables or charts
- Admin-specific controls

{page_description}
Step: {step_description}

Return ONLY valid JSON:
{{"verdict": "pass"|"fail"|"warning", "confidence": 0.0-1.0, "reasoning": "brief explanation", "ui_quality_score": 1-10, "issues": ["issue1"]}}""",

    "responsive": """You are evaluating the EAGLE application at a non-desktop viewport size.

This is a responsive design check. Evaluate:
- Content should reflow properly for the viewport width
- No horizontal scrollbar or content cut off
- Navigation should adapt (hamburger menu on mobile, etc.)
- Text should remain readable
- Buttons/inputs should remain tappable (not too small)
- No overlapping elements

{page_description}
Step: {step_description}

Return ONLY valid JSON:
{{"verdict": "pass"|"fail"|"warning", "confidence": 0.0-1.0, "reasoning": "brief explanation", "ui_quality_score": 1-10, "issues": ["issue1"]}}""",

    "acquisition_package": """You are evaluating the EAGLE acquisition package workflow — a multi-turn conversation that involves intake, document generation, revision, finalization, and export.

Context-dependent evaluation:
- During INTAKE steps: expect clarifying questions about contract type, competition strategy, period of performance, dollar value, security requirements
- During COMPLIANCE steps: expect pathway identification (full competition, simplified, micro-purchase), FAR/DFARS threshold detection, required document list
- During DOCUMENT GENERATION steps: expect tool_use cards (create_document), download links, NCI-branded PDF references, DRAFT watermarks
- During REVISION steps: expect updated document with new requirements incorporated, version increment (v2)
- During FINALIZE steps: expect status change, compliance validation, package completeness confirmation
- During EXPORT steps: expect ZIP download link or instructions, manifest.json mention, multiple document formats (md/pdf/docx)
- During CHECKLIST steps: expect document list with completion status (completed/pending), progress indicators

The conversation should progress logically — each step builds on the previous context. Agent should not ask the user to re-enter information already provided.

{page_description}
Step: {step_description}

Return ONLY valid JSON:
{{"verdict": "pass"|"fail"|"warning", "confidence": 0.0-1.0, "reasoning": "brief explanation", "ui_quality_score": 1-10, "issues": ["issue1"]}}""",

    "workflows": """You are evaluating the EAGLE Acquisition Packages page (/workflows).

Expected elements:
- Page header: "Acquisition Packages" title
- Package cards in a grid layout, each with:
  - Title (acquisition description)
  - Status badge (in_progress, pending_review, approved, completed)
  - Progress indicator (X/Y documents generated)
  - Estimated value if available
  - Date information
- Status filter tabs (All, In Progress, Pending Review, Approved, Completed)
- Search bar for filtering packages
- "New Package" button
- If a package detail modal is open: document checklist with per-document completion status

{page_description}
Step: {step_description}

Return ONLY valid JSON:
{{"verdict": "pass"|"fail"|"warning", "confidence": 0.0-1.0, "reasoning": "brief explanation", "ui_quality_score": 1-10, "issues": ["issue1"]}}""",
}


def get_prompt(journey: str, page_description: str, step_description: str) -> str:
    """Get the appropriate judge prompt for a journey, with context filled in."""
    template = PAGE_PROMPTS.get(journey, GENERAL_UI_PROMPT)
    return template.format(
        page_description=page_description,
        step_description=step_description,
    )
