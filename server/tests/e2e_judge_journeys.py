"""
E2E Judge journey definitions.

Each journey is an async function that navigates the EAGLE app and captures
screenshots at meaningful steps. Journeys run against the deployed ALB URL
using authenticated Playwright sessions.

Journey functions accept a Playwright Page and ScreenshotCapture instance,
and return a list of screenshot metadata dicts.
"""

import asyncio
import time
from typing import Any

# ---------------------------------------------------------------------------
# Journey registry — maps name to (function, description)
# ---------------------------------------------------------------------------
JOURNEY_REGISTRY: dict[str, dict] = {}


def journey(name: str, description: str):
    """Decorator to register a journey function."""
    def decorator(func):
        JOURNEY_REGISTRY[name] = {
            "function": func,
            "description": description,
            "name": name,
        }
        return func
    return decorator


async def wait_with_interval_screenshots(
    page,
    capture,
    journey_name: str,
    step_prefix: str,
    condition_fn,
    timeout_ms: int = 120_000,
    interval_ms: int = 30_000,
    description_base: str = "Waiting for response",
) -> list[dict]:
    """Wait for a condition while capturing screenshots at fixed intervals.

    Takes a screenshot every `interval_ms` milliseconds (default 30s) until
    `condition_fn()` returns True or `timeout_ms` is exceeded.

    Args:
        page: Playwright Page.
        capture: ScreenshotCapture instance.
        journey_name: Journey name for screenshot paths.
        step_prefix: Base step name (e.g. "04"). Interval shots append _a, _b, etc.
        condition_fn: Async callable returning True when done waiting.
        timeout_ms: Total timeout in ms.
        interval_ms: Screenshot interval in ms (default 30000 = 30s).
        description_base: Human description prefix for interval screenshots.

    Returns:
        List of screenshot metadata dicts captured during the wait.
    """
    screenshots = []
    start = time.monotonic()
    interval_idx = 0
    suffixes = "abcdefghijklmnopqrstuvwxyz"

    while True:
        elapsed_ms = (time.monotonic() - start) * 1000
        if elapsed_ms >= timeout_ms:
            break

        try:
            done = await condition_fn()
            if done:
                break
        except Exception:
            pass

        # Wait in small chunks, check condition between chunks
        remaining = min(interval_ms, timeout_ms - elapsed_ms)
        check_interval = 2000  # check every 2s
        waited = 0
        while waited < remaining:
            await page.wait_for_timeout(min(check_interval, remaining - waited))
            waited += check_interval
            try:
                done = await condition_fn()
                if done:
                    return screenshots
            except Exception:
                pass

        # Take interval screenshot
        if interval_idx < len(suffixes):
            suffix = suffixes[interval_idx]
        else:
            suffix = str(interval_idx)
        elapsed_sec = int((time.monotonic() - start))
        step_name = f"{step_prefix}_{suffix}_interval_{elapsed_sec}s"
        s = await capture.take(
            page, journey_name, step_name,
            f"{description_base} — {elapsed_sec}s elapsed",
        )
        screenshots.append(s)
        interval_idx += 1

    return screenshots


# ---------------------------------------------------------------------------
# Login Journey
# ---------------------------------------------------------------------------
@journey("login", "Login page load and authentication flow")
async def journey_login(page, capture, base_url: str) -> list[dict]:
    """Captures the login page and post-auth redirect."""
    screenshots = []

    # Step 1: Navigate to root (may redirect to login or home)
    await page.goto(base_url, wait_until="domcontentloaded")
    await page.wait_for_timeout(2000)
    s = await capture.take(page, "login", "01_initial_load", "Initial page after navigation — login page or home redirect")
    screenshots.append(s)

    # Step 2: If on login page, capture form
    if "/login" in page.url:
        s = await capture.take(page, "login", "02_login_form", "Cognito login form with email and password fields")
        screenshots.append(s)
    else:
        # Already authenticated (dev mode or cached session)
        s = await capture.take(page, "login", "02_authenticated", "Already authenticated — redirected past login")
        screenshots.append(s)

    # Step 3: Navigate to home to confirm auth works
    await page.goto(f"{base_url}/", wait_until="domcontentloaded")
    await page.wait_for_timeout(2000)
    s = await capture.take(page, "login", "03_post_auth_home", "Home page after successful authentication")
    screenshots.append(s)

    return screenshots


# ---------------------------------------------------------------------------
# Home Journey
# ---------------------------------------------------------------------------
@journey("home", "Home page feature cards and navigation elements")
async def journey_home(page, capture, base_url: str) -> list[dict]:
    """Captures the home/landing page layout and feature cards."""
    screenshots = []

    await page.goto(f"{base_url}/", wait_until="domcontentloaded")
    await page.wait_for_timeout(2000)
    s = await capture.take(page, "home", "01_home_page", "EAGLE home page with welcome message and feature cards")
    screenshots.append(s)

    # Capture sidebar
    sidebar = page.locator("nav, [role='navigation'], aside").first
    if await sidebar.count() > 0:
        s = await capture.take(page, "home", "02_sidebar", "Sidebar navigation with session list and navigation links")
        screenshots.append(s)

    # Try clicking a feature card to verify navigation
    feature_cards = page.locator("[data-testid*='card'], .feature-card, a[href*='/chat']")
    if await feature_cards.count() > 0:
        await feature_cards.first.click()
        await page.wait_for_timeout(2000)
        s = await capture.take(page, "home", "03_card_navigation", "Page after clicking first feature card")
        screenshots.append(s)

    # Navigate back
    await page.goto(f"{base_url}/", wait_until="domcontentloaded")
    await page.wait_for_timeout(1000)
    s = await capture.take(page, "home", "04_return_home", "Home page after return navigation")
    screenshots.append(s)

    return screenshots


# ---------------------------------------------------------------------------
# Chat Journey
# ---------------------------------------------------------------------------
@journey("chat", "Full chat interaction: send message, agent streaming, response, tool cards")
async def journey_chat(page, capture, base_url: str) -> list[dict]:
    """Captures a full chat interaction lifecycle.

    Screenshot strategy:
    - Before each user message send (pre-send snapshot)
    - During streaming waits: every 30 seconds
    - After response completes
    """
    screenshots = []

    # Step 1: Navigate to chat
    await page.goto(f"{base_url}/chat/", wait_until="domcontentloaded")
    await page.wait_for_timeout(2000)
    s = await capture.take(page, "chat", "01_chat_page", "EAGLE chat page with sidebar, input area, and quick action buttons")
    screenshots.append(s)

    # Step 2: Click New Chat if available
    try:
        new_chat = page.get_by_role("button", name="New Chat")
        await new_chat.click(timeout=5000)
        await page.wait_for_timeout(1000)
    except Exception:
        pass

    s = await capture.take(page, "chat", "02_new_chat", "Fresh chat session with welcome screen or empty chat")
    screenshots.append(s)

    # Step 3: Type first message — screenshot BEFORE send
    textarea = page.locator("textarea")
    await textarea.wait_for(state="visible", timeout=10000)
    await textarea.fill("Hello, I need help with a simple acquisition under $10,000")
    s = await capture.take(page, "chat", "03_pre_send_1", "Chat input with first user message typed — about to send")
    screenshots.append(s)

    # Send the message
    send_btn = page.locator("button:has-text('➤')")
    await send_btn.click()

    # Step 4: Capture initial streaming state
    await page.wait_for_timeout(3000)
    s = await capture.take(page, "chat", "04_streaming_start", "Chat during agent streaming — typing indicator or partial response visible")
    screenshots.append(s)

    # Step 5: Wait for response with 30-second interval screenshots
    async def response_complete():
        return await textarea.is_enabled()

    interval_shots = await wait_with_interval_screenshots(
        page, capture,
        journey_name="chat",
        step_prefix="05",
        condition_fn=response_complete,
        timeout_ms=120_000,
        interval_ms=30_000,
        description_base="Agent streaming response to first message",
    )
    screenshots.extend(interval_shots)

    # Step 6: Response complete
    await page.wait_for_timeout(2000)
    s = await capture.take(page, "chat", "06_response_1_complete", "Chat with completed EAGLE agent response to first message")
    screenshots.append(s)

    # Step 7: Scroll to see full response
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await page.wait_for_timeout(1000)
    s = await capture.take(page, "chat", "07_response_1_scrolled", "Full first response scrolled into view")
    screenshots.append(s)

    # Step 8: Check for tool cards if visible
    tool_cards = page.locator("[data-testid*='tool'], .tool-card, .tool-use-card")
    if await tool_cards.count() > 0:
        s = await capture.take(page, "chat", "08_tool_cards", "Tool use cards displayed in agent response")
        screenshots.append(s)

    # Step 9: Send a follow-up message — screenshot BEFORE send
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await textarea.wait_for(state="visible", timeout=10000)
    await textarea.fill("What forms do I need to fill out for a micro-purchase?")
    s = await capture.take(page, "chat", "09_pre_send_2", "Chat input with follow-up message typed — about to send")
    screenshots.append(s)

    await send_btn.click()

    # Step 10: Capture initial streaming for follow-up
    await page.wait_for_timeout(3000)
    s = await capture.take(page, "chat", "10_streaming_2_start", "Streaming response to follow-up message")
    screenshots.append(s)

    # Step 11: Wait for second response with 30-second interval screenshots
    interval_shots_2 = await wait_with_interval_screenshots(
        page, capture,
        journey_name="chat",
        step_prefix="11",
        condition_fn=response_complete,
        timeout_ms=120_000,
        interval_ms=30_000,
        description_base="Agent streaming response to follow-up message",
    )
    screenshots.extend(interval_shots_2)

    # Step 12: Second response complete
    await page.wait_for_timeout(2000)
    s = await capture.take(page, "chat", "12_response_2_complete", "Chat with completed second agent response")
    screenshots.append(s)

    # Step 13: Full conversation view
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await page.wait_for_timeout(1000)
    s = await capture.take(page, "chat", "13_full_conversation", "Full multi-turn conversation scrolled to bottom")
    screenshots.append(s)

    return screenshots


# ---------------------------------------------------------------------------
# Admin Journey
# ---------------------------------------------------------------------------
@journey("admin", "Admin dashboard and sub-pages (skills, templates, traces)")
async def journey_admin(page, capture, base_url: str) -> list[dict]:
    """Captures the admin dashboard and key sub-pages."""
    screenshots = []

    # Main dashboard
    await page.goto(f"{base_url}/admin", wait_until="domcontentloaded")
    await page.wait_for_timeout(2000)
    s = await capture.take(page, "admin", "01_dashboard", "Admin dashboard with stats cards and navigation")
    screenshots.append(s)

    # Sub-pages to visit
    sub_pages = [
        ("skills", "/admin/skills", "Skills management page with agent/skill list"),
        ("templates", "/admin/templates", "Document templates management page"),
        ("traces", "/admin/traces", "Trace viewer with recent agent traces"),
        ("tests", "/admin/tests", "Test results page with run history"),
        ("costs", "/admin/costs", "Cost tracking dashboard"),
    ]

    for name, path, description in sub_pages:
        try:
            await page.goto(f"{base_url}{path}", wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            s = await capture.take(page, "admin", f"0{sub_pages.index((name, path, description)) + 2}_{name}", description)
            screenshots.append(s)
        except Exception as e:
            print(f"  [journey:admin] Skipping {name}: {e}")

    return screenshots


# ---------------------------------------------------------------------------
# Documents Journey
# ---------------------------------------------------------------------------
@journey("documents", "Document list, template view, and document detail")
async def journey_documents(page, capture, base_url: str) -> list[dict]:
    """Captures the documents section of the app."""
    screenshots = []

    await page.goto(f"{base_url}/documents", wait_until="domcontentloaded")
    await page.wait_for_timeout(2000)
    s = await capture.take(page, "documents", "01_documents_list", "Documents listing page with document cards or table")
    screenshots.append(s)

    # Try clicking first document if any exist
    doc_items = page.locator("[data-testid*='document'], .document-card, tr[data-testid]")
    if await doc_items.count() > 0:
        await doc_items.first.click()
        await page.wait_for_timeout(2000)
        s = await capture.take(page, "documents", "02_document_detail", "Single document detail view")
        screenshots.append(s)

        # Go back
        await page.go_back()
        await page.wait_for_timeout(1000)

    # Check templates page
    await page.goto(f"{base_url}/templates", wait_until="domcontentloaded")
    await page.wait_for_timeout(2000)
    s = await capture.take(page, "documents", "03_templates", "Document templates listing")
    screenshots.append(s)

    return screenshots


# ---------------------------------------------------------------------------
# Responsive Journey
# ---------------------------------------------------------------------------
@journey("responsive", "Key pages at mobile (375px) and tablet (768px) viewports")
async def journey_responsive(page, capture, base_url: str) -> list[dict]:
    """Captures key pages at multiple viewport sizes."""
    screenshots = []

    viewports = [
        ("mobile", 375, 812),
        ("tablet", 768, 1024),
    ]

    pages_to_test = [
        ("/", "Home page"),
        ("/chat/", "Chat page"),
        ("/admin", "Admin dashboard"),
    ]

    for vp_name, width, height in viewports:
        await page.set_viewport_size({"width": width, "height": height})

        for path, desc in pages_to_test:
            page_slug = path.strip("/").replace("/", "-") or "home"
            step_name = f"{vp_name}_{page_slug}"

            try:
                await page.goto(f"{base_url}{path}", wait_until="domcontentloaded")
                await page.wait_for_timeout(2000)
                s = await capture.take(
                    page, "responsive", step_name,
                    f"{desc} at {vp_name} viewport ({width}x{height})",
                )
                screenshots.append(s)
            except Exception as e:
                print(f"  [journey:responsive] Skipping {step_name}: {e}")

    # Reset viewport
    await page.set_viewport_size({"width": 1440, "height": 900})
    return screenshots


# ---------------------------------------------------------------------------
# Acquisition Package Journey (UC-1 Full Lifecycle)
# ---------------------------------------------------------------------------
@journey("acquisition_package", "Full acquisition package lifecycle: intake → doc generation → checklist → revision → finalize → export")
async def journey_acquisition_package(page, capture, base_url: str) -> list[dict]:
    """End-to-end acquisition package journey covering UC-1 from the demo script.

    Steps:
    1. Start new chat, send intake message ($750K cloud hosting)
    2. Answer clarifying questions
    3. Request SOW generation
    4. Request remaining docs (IGCE, MR, AP)
    5. Navigate to /workflows — check package card + document checklist
    6. Back to chat — request SOW revision (Section 508 + FedRAMP)
    7. Ask to finalize the package
    8. Navigate to /workflows — verify updated package status
    """
    screenshots = []

    # -----------------------------------------------------------------------
    # Phase 1: Intake
    # -----------------------------------------------------------------------

    # Step 1: Navigate to chat, start new session
    await page.goto(f"{base_url}/chat/", wait_until="domcontentloaded")
    await page.wait_for_timeout(2000)
    s = await capture.take(page, "acquisition_package", "01_chat_ready",
                           "Chat page ready for new acquisition intake")
    screenshots.append(s)

    # Click New Chat if available
    try:
        new_chat = page.get_by_role("button", name="New Chat")
        await new_chat.click(timeout=5000)
        await page.wait_for_timeout(1000)
    except Exception:
        pass

    # Step 2: Send intake message
    textarea = page.locator("textarea")
    await textarea.wait_for(state="visible", timeout=10000)
    await textarea.fill(
        "I need to procure cloud hosting services for our research data platform. "
        "Estimated value around $750,000."
    )
    s = await capture.take(page, "acquisition_package", "02_pre_send_intake",
                           "Chat input with $750K cloud hosting intake message — about to send")
    screenshots.append(s)

    send_btn = page.locator("button:has-text('➤')")
    await send_btn.click()

    # Step 3: Wait for EAGLE to respond with clarifying questions
    await page.wait_for_timeout(3000)
    s = await capture.take(page, "acquisition_package", "03_intake_streaming",
                           "Agent streaming initial intake response — clarifying questions expected")
    screenshots.append(s)

    async def textarea_enabled():
        return await textarea.is_enabled()

    interval_shots = await wait_with_interval_screenshots(
        page, capture,
        journey_name="acquisition_package",
        step_prefix="04",
        condition_fn=textarea_enabled,
        timeout_ms=120_000,
        interval_ms=30_000,
        description_base="Waiting for intake response with clarifying questions",
    )
    screenshots.extend(interval_shots)

    await page.wait_for_timeout(2000)
    s = await capture.take(page, "acquisition_package", "05_intake_response",
                           "EAGLE response with clarifying questions about the acquisition")
    screenshots.append(s)

    # Step 4: Answer clarifying questions
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await textarea.wait_for(state="visible", timeout=10000)
    await textarea.fill(
        "3-year base period plus 2 option years, starting October 2026. "
        "No existing vehicles -- new standalone contract. We need FedRAMP High "
        "for PII and genomics research data. Full and open competition preferred. "
        "Fixed-price."
    )
    s = await capture.take(page, "acquisition_package", "06_pre_send_details",
                           "Chat input with acquisition details — about to send")
    screenshots.append(s)

    await send_btn.click()
    await page.wait_for_timeout(3000)

    interval_shots = await wait_with_interval_screenshots(
        page, capture,
        journey_name="acquisition_package",
        step_prefix="07",
        condition_fn=textarea_enabled,
        timeout_ms=120_000,
        interval_ms=30_000,
        description_base="Waiting for compliance analysis response",
    )
    screenshots.extend(interval_shots)

    await page.wait_for_timeout(2000)
    s = await capture.take(page, "acquisition_package", "08_compliance_response",
                           "EAGLE compliance analysis — pathway, thresholds, required documents identified")
    screenshots.append(s)

    # Scroll to see full compliance response
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await page.wait_for_timeout(1000)
    s = await capture.take(page, "acquisition_package", "09_compliance_scrolled",
                           "Full compliance response scrolled — document checklist visible")
    screenshots.append(s)

    # -----------------------------------------------------------------------
    # Phase 2: Document Generation
    # -----------------------------------------------------------------------

    # Step 5: Request SOW generation
    await textarea.wait_for(state="visible", timeout=10000)
    await textarea.fill("Generate the Statement of Work for this cloud hosting acquisition.")
    s = await capture.take(page, "acquisition_package", "10_pre_send_sow",
                           "Chat input requesting SOW generation — about to send")
    screenshots.append(s)

    await send_btn.click()
    await page.wait_for_timeout(3000)
    s = await capture.take(page, "acquisition_package", "11_sow_streaming",
                           "Agent streaming — SOW generation in progress, tool cards may be visible")
    screenshots.append(s)

    interval_shots = await wait_with_interval_screenshots(
        page, capture,
        journey_name="acquisition_package",
        step_prefix="12",
        condition_fn=textarea_enabled,
        timeout_ms=180_000,  # Doc generation can take longer
        interval_ms=30_000,
        description_base="Waiting for SOW generation",
    )
    screenshots.extend(interval_shots)

    await page.wait_for_timeout(2000)
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    s = await capture.take(page, "acquisition_package", "13_sow_complete",
                           "SOW generation complete — tool result card with document link visible")
    screenshots.append(s)

    # Check for tool cards (create_document)
    tool_cards = page.locator("[data-testid*='tool'], .tool-card, .tool-use-card")
    if await tool_cards.count() > 0:
        s = await capture.take(page, "acquisition_package", "14_sow_tool_cards",
                               "Tool use cards showing create_document call for SOW")
        screenshots.append(s)

    # Step 6: Request remaining documents
    await textarea.wait_for(state="visible", timeout=10000)
    await textarea.fill("Now generate the IGCE, Market Research Report, and Acquisition Plan.")
    s = await capture.take(page, "acquisition_package", "15_pre_send_remaining",
                           "Chat input requesting IGCE, MR, AP generation — about to send")
    screenshots.append(s)

    await send_btn.click()
    await page.wait_for_timeout(3000)

    interval_shots = await wait_with_interval_screenshots(
        page, capture,
        journey_name="acquisition_package",
        step_prefix="16",
        condition_fn=textarea_enabled,
        timeout_ms=300_000,  # 3 docs at once — up to 5 min
        interval_ms=30_000,
        description_base="Waiting for IGCE + MR + AP generation",
    )
    screenshots.extend(interval_shots)

    await page.wait_for_timeout(2000)
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    s = await capture.take(page, "acquisition_package", "17_all_docs_complete",
                           "All 4 documents generated — multiple tool result cards visible")
    screenshots.append(s)

    # -----------------------------------------------------------------------
    # Phase 3: Document Checklist Check
    # -----------------------------------------------------------------------

    # Step 7: Check the Documents tab in activity panel (right side)
    docs_tab = page.locator("button:has-text('Documents'), [data-testid*='documents-tab']")
    if await docs_tab.count() > 0:
        try:
            await docs_tab.first.click()
            await page.wait_for_timeout(2000)
            s = await capture.take(page, "acquisition_package", "18_checklist_panel",
                                   "Document checklist panel showing generated documents with status indicators")
            screenshots.append(s)
        except Exception:
            pass

    # Step 8: Navigate to /workflows to see the package card
    await page.goto(f"{base_url}/workflows", wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)
    s = await capture.take(page, "acquisition_package", "19_workflows_page",
                           "Workflows/Packages page showing acquisition package card with progress")
    screenshots.append(s)

    # Try to click on the package card to open detail modal
    package_cards = page.locator(".cursor-pointer:has-text('cloud'), .cursor-pointer:has-text('Cloud'), .cursor-pointer:has-text('hosting')")
    if await package_cards.count() > 0:
        await package_cards.first.click()
        await page.wait_for_timeout(2000)
        s = await capture.take(page, "acquisition_package", "20_package_detail",
                               "Package detail modal with document checklist — completed/pending status for each doc")
        screenshots.append(s)

        # Close modal
        close_btn = page.locator("button:has-text('Close')")
        if await close_btn.count() > 0:
            await close_btn.first.click()
            await page.wait_for_timeout(500)

    # -----------------------------------------------------------------------
    # Phase 4: Document Revision
    # -----------------------------------------------------------------------

    # Step 9: Go back to chat and request SOW revision
    await page.goto(f"{base_url}/chat/", wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)

    # Scroll to bottom to find the conversation
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await page.wait_for_timeout(1000)

    await textarea.wait_for(state="visible", timeout=10000)
    await textarea.fill(
        "The SOW needs a Section 508 accessibility requirement added under the "
        "technical requirements. Also add FedRAMP High authorization as a mandatory "
        "contractor qualification. Please regenerate it."
    )
    s = await capture.take(page, "acquisition_package", "21_pre_send_revision",
                           "Chat input requesting SOW revision with 508 + FedRAMP — about to send")
    screenshots.append(s)

    await send_btn.click()
    await page.wait_for_timeout(3000)

    interval_shots = await wait_with_interval_screenshots(
        page, capture,
        journey_name="acquisition_package",
        step_prefix="22",
        condition_fn=textarea_enabled,
        timeout_ms=180_000,
        interval_ms=30_000,
        description_base="Waiting for SOW v2 revision",
    )
    screenshots.extend(interval_shots)

    await page.wait_for_timeout(2000)
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    s = await capture.take(page, "acquisition_package", "23_sow_v2_complete",
                           "SOW v2 generated — revision complete with Section 508 and FedRAMP additions")
    screenshots.append(s)

    # -----------------------------------------------------------------------
    # Phase 5: Finalize Package
    # -----------------------------------------------------------------------

    # Step 10: Ask EAGLE to finalize the package
    await textarea.wait_for(state="visible", timeout=10000)
    await textarea.fill("Finalize the acquisition package. All documents are ready for review.")
    s = await capture.take(page, "acquisition_package", "24_pre_send_finalize",
                           "Chat input requesting package finalization — about to send")
    screenshots.append(s)

    await send_btn.click()
    await page.wait_for_timeout(3000)

    interval_shots = await wait_with_interval_screenshots(
        page, capture,
        journey_name="acquisition_package",
        step_prefix="25",
        condition_fn=textarea_enabled,
        timeout_ms=120_000,
        interval_ms=30_000,
        description_base="Waiting for finalize package response",
    )
    screenshots.extend(interval_shots)

    await page.wait_for_timeout(2000)
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    s = await capture.take(page, "acquisition_package", "26_finalize_response",
                           "Package finalization response — status updated, compliance validated")
    screenshots.append(s)

    # -----------------------------------------------------------------------
    # Phase 6: Export / Final Check
    # -----------------------------------------------------------------------

    # Step 11: Ask about exporting the package
    await textarea.wait_for(state="visible", timeout=10000)
    await textarea.fill("Export the complete acquisition package as a ZIP file.")
    s = await capture.take(page, "acquisition_package", "27_pre_send_export",
                           "Chat input requesting package export as ZIP — about to send")
    screenshots.append(s)

    await send_btn.click()
    await page.wait_for_timeout(3000)

    interval_shots = await wait_with_interval_screenshots(
        page, capture,
        journey_name="acquisition_package",
        step_prefix="28",
        condition_fn=textarea_enabled,
        timeout_ms=120_000,
        interval_ms=30_000,
        description_base="Waiting for export response",
    )
    screenshots.extend(interval_shots)

    await page.wait_for_timeout(2000)
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    s = await capture.take(page, "acquisition_package", "29_export_response",
                           "Export response — ZIP download link or instructions for package export")
    screenshots.append(s)

    # Step 12: Final check on workflows page
    await page.goto(f"{base_url}/workflows", wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)
    s = await capture.take(page, "acquisition_package", "30_final_workflows",
                           "Final workflows page — package status updated after finalization + export")
    screenshots.append(s)

    # Try opening the package detail one more time to see final state
    if await package_cards.count() > 0:
        try:
            await package_cards.first.click()
            await page.wait_for_timeout(2000)
            s = await capture.take(page, "acquisition_package", "31_final_package_detail",
                                   "Final package detail — all documents completed, package status finalized/exported")
            screenshots.append(s)
        except Exception:
            pass

    # Step 13: Full conversation screenshot
    await page.goto(f"{base_url}/chat/", wait_until="domcontentloaded")
    await page.wait_for_timeout(2000)
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    s = await capture.take(page, "acquisition_package", "32_full_conversation",
                           "Full multi-turn acquisition conversation — all 7 exchanges visible")
    screenshots.append(s)

    return screenshots


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
def list_journeys() -> list[str]:
    """Return names of all registered journeys."""
    return list(JOURNEY_REGISTRY.keys())


def get_journey(name: str) -> dict:
    """Get a journey definition by name."""
    return JOURNEY_REGISTRY[name]
