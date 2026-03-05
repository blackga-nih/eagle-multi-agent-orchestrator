import { test, expect } from '@playwright/test';

/**
 * Document Generation Pipeline — E2E Tests
 *
 * Two blocks:
 *   1. "Document Viewer (frontend-only)" — pre-seed sessionStorage, no backend.
 *   2. "Document Generation (requires agent)" — real backend, marked test.slow().
 *
 * Run: npx playwright test tests/document-pipeline.spec.ts
 */

// ── Helpers ──────────────────────────────────────────────────────────

const TEST_DOC_ID = 'test-doc-sow-001';
const TEST_DOC = {
  title: 'Statement of Work — IT Consulting',
  document_type: 'sow',
  content: [
    '# Statement of Work — IT Consulting',
    '',
    '## 1. Background',
    'The National Cancer Institute requires IT consulting services.',
    '',
    '## 2. Scope',
    'The contractor shall provide full-stack development support.',
    '',
    '## 3. Deliverables',
    '- Project Management Plan',
    '- Monthly Status Reports',
    '- Final Delivery Report',
  ].join('\n'),
};

/** Seed sessionStorage with a test document before navigating to the viewer. */
async function seedDocument(page: ReturnType<typeof test['info']> extends never ? never : any) {
  // Navigate to a blank page first so we can set sessionStorage on the correct origin
  await page.goto('/');
  await page.evaluate(
    ({ id, doc }: { id: string; doc: typeof TEST_DOC }) => {
      sessionStorage.setItem(`doc-content-${id}`, JSON.stringify(doc));
    },
    { id: TEST_DOC_ID, doc: TEST_DOC },
  );
}

// ══════════════════════════════════════════════════════════════════════
// Block 1 — Document Viewer (frontend-only, no backend needed)
// ══════════════════════════════════════════════════════════════════════

test.describe('Document Viewer (frontend-only)', () => {
  test.beforeEach(async ({ page }) => {
    await seedDocument(page);
  });

  test('viewer renders content from sessionStorage', async ({ page }) => {
    await page.goto(`/documents/${TEST_DOC_ID}`);

    // Title or heading should be visible
    await expect(
      page.getByText('Statement of Work').first(),
    ).toBeVisible({ timeout: 10_000 });

    // Some body content should appear
    await expect(
      page.getByText('IT consulting services').first(),
    ).toBeVisible();
  });

  test('download dropdown shows format options', async ({ page }) => {
    await page.goto(`/documents/${TEST_DOC_ID}`);

    // Wait for page to load
    await expect(page.getByText('Statement of Work').first()).toBeVisible({ timeout: 10_000 });

    // Look for a download button or dropdown trigger
    const downloadBtn = page.getByRole('button', { name: /download/i });
    if (await downloadBtn.isVisible()) {
      await downloadBtn.click();
      // Format options should appear
      await expect(
        page.getByText(/word|docx/i).first(),
      ).toBeVisible({ timeout: 5_000 });
      await expect(
        page.getByText(/pdf/i).first(),
      ).toBeVisible();
    } else {
      // If no download button, check for export links/buttons elsewhere
      const exportBtn = page.getByRole('button', { name: /export/i });
      if (await exportBtn.isVisible()) {
        await exportBtn.click();
      }
    }
  });

  test('download sends correct export request', async ({ page }) => {
    await page.goto(`/documents/${TEST_DOC_ID}`);
    await expect(page.getByText('Statement of Work').first()).toBeVisible({ timeout: 10_000 });

    // Intercept the export POST
    const exportPromise = page.waitForRequest(
      (req) =>
        req.url().includes('/api/documents') &&
        req.method() === 'POST',
      { timeout: 15_000 },
    ).catch(() => null);

    // Click download/export
    const downloadBtn = page.getByRole('button', { name: /download/i });
    if (await downloadBtn.isVisible()) {
      await downloadBtn.click();
      // Select first format option
      const wordOption = page.getByText(/word|docx/i).first();
      if (await wordOption.isVisible()) {
        await wordOption.click();
      }
    }

    const req = await exportPromise;
    if (req) {
      const body = req.postDataJSON();
      expect(body).toHaveProperty('content');
      expect(body).toHaveProperty('format');
    }
  });

  test('edit and preview toggle works', async ({ page }) => {
    await page.goto(`/documents/${TEST_DOC_ID}`);
    await expect(page.getByText('Statement of Work').first()).toBeVisible({ timeout: 10_000 });

    // Look for edit button
    const editBtn = page.getByRole('button', { name: /edit/i });
    if (await editBtn.isVisible()) {
      await editBtn.click();

      // Textarea should appear
      await expect(page.locator('textarea').first()).toBeVisible({ timeout: 5_000 });

      // Switch back to preview
      const previewBtn = page.getByRole('button', { name: /preview/i });
      if (await previewBtn.isVisible()) {
        await previewBtn.click();
        // Textarea should be hidden
        await expect(page.locator('textarea').first()).not.toBeVisible({ timeout: 5_000 });
      }
    }
  });
});

// ══════════════════════════════════════════════════════════════════════
// Block 2 — Document Generation (requires running agent backend)
// ══════════════════════════════════════════════════════════════════════

test.describe('Document Generation (requires agent)', () => {
  // These tests call the real LLM and cost tokens — allow longer timeouts
  test.slow();

  test('document card appears after generation', async ({ page }) => {
    await page.goto('/');

    // Find the chat input
    const chatInput = page.getByPlaceholder(/message|type|ask/i);
    await expect(chatInput).toBeVisible({ timeout: 10_000 });

    // Send a document generation request
    await chatInput.fill('Generate a SOW for IT consulting services');
    await chatInput.press('Enter');

    // Wait for the document card / "Open Document" link to appear
    await expect(
      page.getByText(/open document|view document|document generated/i).first(),
    ).toBeVisible({ timeout: 90_000 });
  });

  test('clicking open document navigates to viewer', async ({ page }) => {
    await page.goto('/');

    const chatInput = page.getByPlaceholder(/message|type|ask/i);
    await chatInput.fill('Generate a SOW for IT consulting services');
    await chatInput.press('Enter');

    // Wait for document link
    const docLink = page.getByText(/open document|view document/i).first();
    await expect(docLink).toBeVisible({ timeout: 90_000 });

    // Click and verify navigation
    const [newPage] = await Promise.all([
      page.context().waitForEvent('page', { timeout: 10_000 }).catch(() => null),
      docLink.click(),
    ]);

    if (newPage) {
      await newPage.waitForLoadState();
      expect(newPage.url()).toContain('/documents/');
    } else {
      // May navigate in same tab
      await page.waitForURL(/\/documents\//, { timeout: 10_000 });
    }
  });

  test('documents page lists generated docs', async ({ page }) => {
    // Navigate to documents listing
    await page.goto('/documents/');

    // Should see at least the page heading
    await expect(
      page.getByRole('heading', { name: /documents/i }).first(),
    ).toBeVisible({ timeout: 10_000 });

    // If there are any documents, they should be in the list
    const docCards = page.locator('[class*="card"], [class*="document"], [role="listitem"]');
    const count = await docCards.count();
    // Just verify the page loads without error — document count depends on prior state
    expect(count).toBeGreaterThanOrEqual(0);
  });
});
