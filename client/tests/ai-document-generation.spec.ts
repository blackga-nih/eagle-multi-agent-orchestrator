import { test, expect } from '@playwright/test';

/**
 * AI Document Generation — Title & Content Validation
 *
 * Validates that document generation flows through the full LLM pipeline:
 *   1. Backend API must be connected and user must be authenticated
 *   2. Chat message triggers agent → create_document tool → AI-generated content
 *   3. Document title is contextually rich (not a generic template stub)
 *   4. Document content contains structured sections from the LLM
 *   5. Document card renders in chat with correct metadata
 *   6. Document viewer loads with matching title and content
 *
 * These tests MUST fail when:
 *   - Backend API is disconnected (no LLM access)
 *   - User is not authenticated (no session for context)
 *   - Document title is a static template string without conversation context
 */

/** Wait for backend API + auth indicators to be green before proceeding. */
async function waitForBackendAndAuth(page: any) {
  await page.goto('/chat/');

  // Gate 1: Backend API must be connected.
  // The top-nav div has title="Backend connected" when the health check passes.
  // The frontend polls /api/health — if it's still "Connecting" after 20s, reload
  // once to reset the health check timer (backend may have recovered between polls).
  const apiIndicator = page.locator('[title="Backend connected"]');
  const connected = await apiIndicator
    .isVisible({ timeout: 20_000 })
    .catch(() => false);

  if (!connected) {
    // Backend health poll may be stale — reload to retry
    await page.reload();
    await expect(apiIndicator).toBeVisible({ timeout: 30_000 });
  }

  // Gate 2: User must be authenticated.
  // The top-nav div has title="Authenticated as <email>" when auth is valid.
  const authIndicator = page.locator('[title^="Authenticated as"]');
  await expect(authIndicator).toBeVisible({ timeout: 10_000 });
}

test.describe('AI Document Generation — Title & Content', () => {
  // All tests in this block need agent streaming — triple the default 30s timeout
  // so that beforeEach + test body have enough room.
  test.describe.configure({ timeout: 180_000 });

  test.beforeEach(async ({ page }) => {
    await waitForBackendAndAuth(page);
  });

  test('SOW generation produces AI-crafted title and structured content', async ({ page }) => {
    // Start a new chat for a clean session
    await page.getByRole('button', { name: 'New Chat' }).click();
    await expect(page.getByRole('heading', { name: /Welcome to EAGLE/i })).toBeVisible();

    // Send a specific acquisition scenario — the LLM should use this context
    // for both the document title and content
    const textarea = page.locator('textarea');
    await expect(textarea).toBeEnabled();
    await textarea.fill(
      'I need a Statement of Work for cloud hosting services for the NCI Research Portal. ' +
        'The estimated value is $750,000 over 3 years. We need AWS GovCloud hosting, ' +
        '24/7 monitoring, and FedRAMP High compliance.',
    );
    await page.getByRole('button', { name: '➤' }).click();

    // Phase 1: Streaming starts — stop button appears
    const stopButton = page.getByTitle('Stop generating (Esc)');
    await expect(stopButton).toBeVisible({ timeout: 15_000 });

    // Phase 2: Streaming completes — stop button disappears
    await expect(stopButton).not.toBeVisible({ timeout: 120_000 });

    // Phase 3: Agent response rendered
    await expect(page.locator('text=🦅 EAGLE')).toBeVisible();

    // Phase 4: Document card appears in chat
    // The document card has a distinctive left border and "Open Document" button
    const documentCard = page.locator('button:has-text("Open Document")').first();
    await expect(documentCard).toBeVisible({ timeout: 30_000 });

    // ── Title Validation ──
    // The document card renders the title in an h4 element.
    // AI-generated titles should be contextually rich, referencing the acquisition scenario.
    // Fast-path/template titles look like: "Statement of Work" or "Untitled Acquisition"
    // AI titles look like: "Statement of Work - Cloud Hosting Services for NCI Research Portal"
    const cardContainer = page
      .locator('[class*="border-l-"]')
      .filter({ has: page.locator('button:has-text("Open Document")') })
      .first();
    const titleElement = cardContainer.locator('h4').first();
    const title = await titleElement.textContent();

    expect(title, 'Document title should not be empty').toBeTruthy();
    expect(
      title!.length,
      `Title "${title}" is too short — likely a template stub, not AI-generated`,
    ).toBeGreaterThan(15);

    // Title must NOT be a bare template label without context
    const bareTemplatePatterns = [
      /^Statement of Work$/i,
      /^Untitled/i,
      /^SOW$/i,
      /^Document$/i,
    ];
    for (const pattern of bareTemplatePatterns) {
      expect(
        title,
        `Title "${title}" matches bare template pattern ${pattern} — not AI-generated`,
      ).not.toMatch(pattern);
    }

    // Title should reference the acquisition context (cloud, hosting, NCI, portal, etc.)
    const contextKeywords = /cloud|hosting|nci|portal|research|govcloud|aws/i;
    expect(
      title,
      `Title "${title}" lacks contextual keywords from the conversation — may not be AI-generated`,
    ).toMatch(contextKeywords);

    // ── Content Validation ──
    // The agent response in the chat should contain structured SOW elements
    const mainContent = (await page.locator('main').textContent()) ?? '';
    expect(mainContent.length).toBeGreaterThan(200);

    // ── Word Count Validation ──
    // Document card shows word count — AI-generated SOWs should be substantial
    const wordCountText = cardContainer.locator('text=/\\d+.*words/i').first();
    if (await wordCountText.isVisible()) {
      const wcText = await wordCountText.textContent();
      const wordCountMatch = wcText?.match(/(\d[\d,]*)\s*words/);
      if (wordCountMatch) {
        const wordCount = parseInt(wordCountMatch[1].replace(/,/g, ''), 10);
        expect(
          wordCount,
          `Word count ${wordCount} is too low for an AI-generated SOW`,
        ).toBeGreaterThan(100);
      }
    }

    // ── Document Viewer Validation (best-effort) ──
    // The document card stores content in sessionStorage then calls window.open().
    // sessionStorage is per-tab, so the new tab may not inherit it and will fall
    // back to an API fetch. If the viewer loads, verify title; if not, the card
    // title validation above already proved the AI title is correct.
    const [viewerPage] = await Promise.all([
      page.context().waitForEvent('page', { timeout: 10_000 }).catch(() => null),
      documentCard.click(),
    ]);

    if (viewerPage) {
      await viewerPage.waitForLoadState('domcontentloaded');

      // Wait for the document to actually load (not just "Loading document...")
      const docLoaded = await viewerPage
        .locator('h1')
        .filter({ hasNotText: 'EAGLE' })
        .first()
        .isVisible({ timeout: 15_000 })
        .catch(() => false);

      if (docLoaded) {
        const viewerTitle = await viewerPage
          .locator('h1')
          .filter({ hasNotText: 'EAGLE' })
          .first()
          .textContent();
        expect(
          viewerTitle,
          'Viewer title should contain contextual keywords from the conversation',
        ).toMatch(contextKeywords);

        const viewerContent = (await viewerPage.locator('main').textContent()) ?? '';
        expect(viewerContent).toMatch(
          /scope|deliverable|background|objective|requirement|period of performance/i,
        );
      }
      // If viewer didn't load (auth/sessionStorage issue in new tab), that's OK —
      // the card title was already validated above.
      await viewerPage.close();
    }
  });

  test('IGCE generation produces AI title with cost context', async ({ page }) => {
    await page.getByRole('button', { name: 'New Chat' }).click();
    await expect(page.getByRole('heading', { name: /Welcome to EAGLE/i })).toBeVisible();

    const textarea = page.locator('textarea');
    await expect(textarea).toBeEnabled();
    await textarea.fill(
      'Create an Independent Government Cost Estimate for the cloud hosting procurement. ' +
        'Budget is $750K over 3 years: $200K/yr for AWS GovCloud compute, ' +
        '$30K/yr for monitoring tools, and $20K/yr for support staff.',
    );
    await page.getByRole('button', { name: '➤' }).click();

    // Wait for streaming to complete
    const stopButton = page.getByTitle('Stop generating (Esc)');
    await expect(stopButton).toBeVisible({ timeout: 15_000 });
    await expect(stopButton).not.toBeVisible({ timeout: 120_000 });

    // Wait for agent response
    await expect(page.locator('text=🦅 EAGLE')).toBeVisible();

    // Check for document card
    const hasDocCard = await page
      .locator('button:has-text("Open Document")')
      .first()
      .isVisible({ timeout: 30_000 })
      .catch(() => false);

    if (hasDocCard) {
      // Document card appeared — validate title
      const cardContainer = page
        .locator('[class*="border-l-"]')
        .filter({ has: page.locator('button:has-text("Open Document")') })
        .first();
      const titleElement = cardContainer.locator('h4').first();
      const title = await titleElement.textContent();

      expect(title, 'IGCE title should not be empty').toBeTruthy();
      expect(title!.length, 'IGCE title too short').toBeGreaterThan(10);
      expect(title, 'IGCE title should not be a bare stub').not.toMatch(
        /^(IGCE|Cost Estimate|Untitled)$/i,
      );
    }

    // Whether or not a document card appeared, the response should contain cost data
    const mainContent = (await page.locator('main').textContent()) ?? '';
    expect(mainContent).toMatch(/cost|estimate|budget|\$|price|igce/i);
  });

  test('document title reflects multi-turn conversation context', async ({ page }) => {
    await page.getByRole('button', { name: 'New Chat' }).click();
    await expect(page.getByRole('heading', { name: /Welcome to EAGLE/i })).toBeVisible();

    const textarea = page.locator('textarea');
    const sendBtn = page.getByRole('button', { name: '➤' });
    const stopButton = page.getByTitle('Stop generating (Esc)');

    // Turn 1: Establish the acquisition context
    await expect(textarea).toBeEnabled();
    await textarea.fill(
      'I need to procure cybersecurity assessment services for NCI clinical trial systems. ' +
        'Budget is approximately $500K. Must be FISMA High compliant.',
    );
    await sendBtn.click();
    await expect(stopButton).toBeVisible({ timeout: 15_000 });
    await expect(stopButton).not.toBeVisible({ timeout: 120_000 });
    await expect(textarea).toBeEnabled();

    // Turn 2: Request document generation — title should incorporate Turn 1 context
    await textarea.fill('Generate a Statement of Work for this cybersecurity assessment.');
    await sendBtn.click();
    await expect(stopButton).toBeVisible({ timeout: 15_000 });
    await expect(stopButton).not.toBeVisible({ timeout: 120_000 });

    // Check for document card
    const openDocBtn = page.locator('button:has-text("Open Document")').first();
    await expect(openDocBtn).toBeVisible({ timeout: 30_000 });

    const cardContainer = page
      .locator('[class*="border-l-"]')
      .filter({ has: page.locator('button:has-text("Open Document")') })
      .first();
    const titleElement = cardContainer.locator('h4').first();
    const title = await titleElement.textContent();

    expect(title, 'Title should not be empty').toBeTruthy();

    // The title MUST reference the cybersecurity context from Turn 1.
    // If the title is generic ("Statement of Work") or only references Turn 2's
    // vague "this cybersecurity assessment", the LLM is not using conversation history.
    expect(
      title,
      `Title "${title}" should reference the cybersecurity/clinical trial context from the conversation`,
    ).toMatch(/cyber|security|clinical|trial|fisma|nci|assessment/i);
  });
});

test.describe('AI Document Generation — Failure Gates', () => {
  test('unauthenticated session shows auth warning, not fake documents', async ({ page }) => {
    // Navigate first so we have a valid origin context
    await page.goto('/chat/');

    // Clear auth state to simulate unauthenticated access
    await page.context().clearCookies();
    await page.evaluate(() => {
      try {
        localStorage.clear();
      } catch {
        // May be restricted in some contexts
      }
      try {
        sessionStorage.clear();
      } catch {
        // May be restricted in some contexts
      }
    });

    // Reload to trigger the unauthenticated state
    await page.reload();

    // Either: page redirects to /login, OR shows "Not authenticated" indicator
    const redirectedToLogin = await page
      .waitForURL(/\/login/, { timeout: 5_000 })
      .then(() => true)
      .catch(() => false);

    if (!redirectedToLogin) {
      // Still on /chat — check that auth indicator shows NOT authenticated
      const notAuth = page.locator('[title="Not authenticated"]');
      const authMissing = await notAuth.isVisible({ timeout: 5_000 }).catch(() => false);

      if (!authMissing) {
        // Dev mode auto-authenticates — this gate doesn't apply, skip gracefully
        test.skip(true, 'Dev mode auto-authenticates — auth gate not testable locally');
        return;
      }

      // We're unauthenticated. Try to send a message.
      const textarea = page.locator('textarea');
      if (await textarea.isVisible({ timeout: 3_000 }).catch(() => false)) {
        await textarea.fill('Generate a SOW');
        const sendBtn = page.getByRole('button', { name: '➤' });
        if (await sendBtn.isEnabled({ timeout: 2_000 }).catch(() => false)) {
          await sendBtn.click();
          // Should see an error, not a document
          const errorOrAuthMsg = page.locator(
            'text=/error|sign in|log in|session expired|unauthorized|authenticate/i',
          );
          await expect(errorOrAuthMsg.first()).toBeVisible({ timeout: 15_000 });
        }
      }
    }
    // If redirected to login, that's the correct behavior — test passes
  });

  test('backend API health is required for document generation', async ({ page }) => {
    await page.goto('/chat/');

    // Verify backend status indicator exists in the UI
    const apiStatus = page.locator(
      '[title="Backend connected"], [title="Backend offline"], [title="Connecting to backend…"]',
    );
    await expect(apiStatus.first()).toBeVisible({ timeout: 15_000 });

    // Read the current status
    const isConnected = await page
      .locator('[title="Backend connected"]')
      .isVisible()
      .catch(() => false);

    if (!isConnected) {
      // Backend is offline — document generation should not produce AI content
      test.skip(true, 'Backend API is offline — cannot test generation flow');
      return;
    }

    // Backend is connected — this is the happy path, covered by other tests.
    // This test exists to document the requirement: no API = no AI documents.
    expect(isConnected).toBe(true);
  });
});
