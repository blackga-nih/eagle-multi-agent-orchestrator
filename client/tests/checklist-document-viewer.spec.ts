import { test, expect } from '@playwright/test';

/**
 * Checklist Document Viewer
 *
 * Tests that completed checklist items are clickable, open a document viewer
 * modal with rendered content, and that the panel auto-refreshes package state
 * after streaming completes.
 *
 * Uses synthetic page.route() mocks — no backend needed.
 */

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

const MOCK_PACKAGE_ID = 'PKG-VIEW-001';

const MOCK_CHECKLIST = {
  required: ['sow', 'igce', 'market_research', 'acquisition_plan'],
  completed: ['sow', 'igce'],
  missing: ['market_research', 'acquisition_plan'],
  complete: false,
};

const MOCK_PACKAGES = [
  {
    package_id: MOCK_PACKAGE_ID,
    title: 'Cloud Migration Services',
    status: 'drafting',
    requirement_type: 'services',
    estimated_value: '750000',
    created_at: '2026-03-20T10:00:00Z',
  },
];

const MOCK_DOCUMENT_SOW = {
  document_id: 'DOC-SOW-001',
  doc_type: 'sow',
  title: 'Statement of Work — Cloud Migration',
  version: 2,
  status: 'draft',
  file_type: 'md',
  content:
    '# Statement of Work\n\n## 1. Background\n\nThe agency requires cloud migration services.\n\n## 2. Scope\n\nMigrate on-premise infrastructure to AWS GovCloud.\n\n## 3. Period of Performance\n\n12 months from date of award.',
  s3_key: `eagle/dev-tenant/${MOCK_PACKAGE_ID}/sow/v2/sow.md`,
  word_count: 42,
  created_at: '2026-03-28T14:00:00Z',
};

const MOCK_DOCUMENT_IGCE = {
  document_id: 'DOC-IGCE-001',
  doc_type: 'igce',
  title: 'IGCE — Cloud Migration',
  version: 1,
  status: 'final',
  file_type: 'md',
  content:
    '# Independent Government Cost Estimate\n\n| Line Item | Quantity | Unit Price | Total |\n|-----------|----------|------------|-------|\n| Cloud Infrastructure | 12 months | $50,000 | $600,000 |\n| Migration Labor | 1 | $150,000 | $150,000 |',
  s3_key: `eagle/dev-tenant/${MOCK_PACKAGE_ID}/igce/v1/igce.md`,
  word_count: 35,
  created_at: '2026-03-29T09:00:00Z',
};

const MOCK_DOCUMENT_NO_CONTENT = {
  document_id: 'DOC-MR-001',
  doc_type: 'market_research',
  title: 'Market Research Report',
  version: 1,
  status: 'pending',
  file_type: 'docx',
  s3_key: `eagle/dev-tenant/${MOCK_PACKAGE_ID}/market_research/v1/mrr.docx`,
  word_count: 0,
  created_at: '2026-03-30T10:00:00Z',
};

const MOCK_DOCUMENTS_LIST = [
  {
    document_id: MOCK_DOCUMENT_SOW.document_id,
    doc_type: 'sow',
    title: MOCK_DOCUMENT_SOW.title,
    version: 2,
    status: 'draft',
    file_type: 'md',
  },
  {
    document_id: MOCK_DOCUMENT_IGCE.document_id,
    doc_type: 'igce',
    title: MOCK_DOCUMENT_IGCE.title,
    version: 1,
    status: 'final',
    file_type: 'md',
  },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function buildSSE(events: Array<Record<string, unknown>>): string {
  return events.map((e) => `data: ${JSON.stringify(e)}`).join('\n\n') + '\n\n';
}

/** SSE events that simulate a package creation + checklist update. */
function buildPackageSSE() {
  return [
    {
      type: 'text',
      agent_id: 'eagle',
      agent_name: 'EAGLE',
      content: 'Creating your acquisition package...',
      timestamp: '2026-01-01T00:00:01Z',
    },
    {
      type: 'metadata',
      metadata: {
        state_type: 'checklist_update',
        package_id: MOCK_PACKAGE_ID,
        phase: 'drafting',
        checklist: MOCK_CHECKLIST,
        progress_pct: 50,
      },
      timestamp: '2026-01-01T00:00:02Z',
    },
    {
      type: 'complete',
      agent_id: 'eagle',
      agent_name: 'EAGLE',
      metadata: {},
      timestamp: '2026-01-01T00:00:03Z',
    },
  ];
}

/** Set up all route mocks. */
async function setupRoutes(
  page: import('@playwright/test').Page,
  options?: {
    sseEvents?: Array<Record<string, unknown>>;
    contextPackage?: Record<string, unknown> | null;
  },
) {
  // Mock GET /api/packages
  await page.route('**/api/packages', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_PACKAGES),
      });
    } else {
      await route.continue();
    }
  });

  // Mock GET /api/packages/{id}/documents (list)
  await page.route(/\/api\/packages\/([^/]+)\/documents$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_DOCUMENTS_LIST),
    });
  });

  // Mock GET /api/packages/{id}/documents/{docType} (single document)
  await page.route(/\/api\/packages\/([^/]+)\/documents\/([^/?]+)/, async (route) => {
    const url = route.request().url();
    const match = url.match(/\/documents\/([^/?]+)/);
    const docType = match?.[1] ?? '';

    const docMap: Record<string, unknown> = {
      sow: MOCK_DOCUMENT_SOW,
      igce: MOCK_DOCUMENT_IGCE,
      market_research: MOCK_DOCUMENT_NO_CONTENT,
    };

    const doc = docMap[docType];
    if (doc) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(doc),
      });
    } else {
      await route.fulfill({ status: 404, body: 'Not found' });
    }
  });

  // Mock GET /api/packages/{id}/export/zip
  await page.route(/\/api\/packages\/([^/]+)\/export\/zip/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/zip',
      body: Buffer.from('PK mock zip'),
    });
  });

  // Mock session context endpoint
  const contextPkg = options?.contextPackage !== undefined ? options.contextPackage : null;
  await page.route('**/api/sessions/*/context', async (route) => {
    const body = contextPkg
      ? { package: contextPkg }
      : {};
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });
  });

  // Mock SSE endpoint
  const sseEvents = options?.sseEvents ?? buildPackageSSE();
  await page.route('**/api/invoke', async (route) => {
    await route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
      body: buildSSE(sseEvents),
    });
  });

  // Mock title generation
  await page.route('**/api/sessions/generate-title', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ title: 'Cloud Migration' }),
    });
  });
}

/** Send a chat message to trigger SSE and populate the checklist. */
async function triggerPackageSSE(page: import('@playwright/test').Page) {
  await page.goto('/chat/');
  await page.getByRole('button', { name: 'New Chat' }).click();

  const textarea = page.locator('textarea');
  await expect(textarea).toBeEnabled({ timeout: 5000 });

  await textarea.fill('I need cloud migration services for $750,000');
  await page.getByRole('button', { name: '\u27A4' }).click();

  // Wait for streaming to complete — textarea re-enabled
  await expect(textarea).toBeEnabled({ timeout: 15000 });

  // Checklist should now be populated via SSE metadata
  await expect(
    page.getByText('Acquisition Package').first(),
  ).toBeVisible({ timeout: 5000 });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe('Checklist Document Viewer', () => {
  // ─── Clickable Checklist Items ───────────────────────────────────────

  test.describe('Clickable Checklist Items', () => {
    test('completed items are clickable, incomplete items are not', async ({ page }) => {
      await setupRoutes(page);
      await triggerPackageSSE(page);

      // Completed items (SOW, IGCE) should be clickable (role=button)
      const sowItem = page.locator('li[role="button"]', {
        hasText: 'Statement of Work',
      });
      await expect(sowItem).toBeVisible();

      const igceItem = page.locator('li[role="button"]', {
        hasText: 'Independent Government Cost Estimate',
      });
      await expect(igceItem).toBeVisible();

      // Incomplete items should NOT have role=button
      const mrItem = page.locator('li', {
        hasText: 'Market Research',
      });
      await expect(mrItem).toBeVisible();
      await expect(mrItem).not.toHaveAttribute('role', 'button');
    });

    test('completed items show eye icon', async ({ page }) => {
      await setupRoutes(page);
      await triggerPackageSSE(page);

      // Completed items should contain an SVG eye icon
      const sowItem = page.locator('li[role="button"]', {
        hasText: 'Statement of Work',
      });
      await expect(sowItem.locator('svg').last()).toBeVisible();
    });

    test('completed items show blue text, not strikethrough', async ({ page }) => {
      await setupRoutes(page);
      await triggerPackageSSE(page);

      const sowText = page.locator('li[role="button"]', {
        hasText: 'Statement of Work',
      }).locator('span').nth(1);

      // Should have the navy blue class, not line-through
      await expect(sowText).toHaveClass(/text-\[#003366\]/);
      await expect(sowText).not.toHaveClass(/line-through/);
    });
  });

  // ─── Document Viewer Modal ───────────────────────────────────────────

  test.describe('Document Viewer Modal', () => {
    test('clicking completed item opens document viewer modal', async ({ page }) => {
      await setupRoutes(page);
      await triggerPackageSSE(page);

      // Click the SOW checklist item
      const sowItem = page.locator('li[role="button"]', {
        hasText: 'Statement of Work',
      });
      await sowItem.click();

      // Modal should appear with the document title
      const modal = page.locator('[data-testid="modal-content"]');
      await expect(modal).toBeVisible({ timeout: 5000 });

      // Modal title should show the doc label
      await expect(
        modal.getByText('Statement of Work (SOW)'),
      ).toBeVisible();
    });

    test('document viewer renders markdown content', async ({ page }) => {
      await setupRoutes(page);
      await triggerPackageSSE(page);

      // Open SOW viewer
      await page
        .locator('li[role="button"]', { hasText: 'Statement of Work' })
        .click();

      const modal = page.locator('[data-testid="modal-content"]');
      await expect(modal).toBeVisible({ timeout: 5000 });

      // Wait for content to load and check rendered headings
      await expect(modal.locator('h1', { hasText: 'Statement of Work' })).toBeVisible({
        timeout: 5000,
      });
      await expect(modal.getByText('Background')).toBeVisible();
      await expect(modal.getByText('cloud migration services')).toBeVisible();
    });

    test('document viewer shows metadata in footer', async ({ page }) => {
      await setupRoutes(page);
      await triggerPackageSSE(page);

      // Open SOW viewer
      await page
        .locator('li[role="button"]', { hasText: 'Statement of Work' })
        .click();

      const modal = page.locator('[data-testid="modal-content"]');
      await expect(modal).toBeVisible({ timeout: 5000 });

      // Footer should show version and word count
      const footer = modal.locator('..').locator('div').filter({ hasText: /v2/ });
      await expect(footer.first()).toBeVisible({ timeout: 5000 });
    });

    test('document viewer has download and open full viewer buttons', async ({ page }) => {
      await setupRoutes(page);
      await triggerPackageSSE(page);

      // Open SOW viewer
      await page
        .locator('li[role="button"]', { hasText: 'Statement of Work' })
        .click();

      // Wait for modal content to load (not just spinner)
      await expect(
        page.locator('[data-testid="modal-content"]').locator('h1', { hasText: 'Statement of Work' }),
      ).toBeVisible({ timeout: 5000 });

      // Buttons should be visible in the footer area
      await expect(page.getByRole('button', { name: 'Download' })).toBeVisible();
      await expect(page.getByRole('button', { name: 'Open Full Viewer' })).toBeVisible();
    });

    test('modal closes on close button click', async ({ page }) => {
      await setupRoutes(page);
      await triggerPackageSSE(page);

      // Open SOW viewer
      await page
        .locator('li[role="button"]', { hasText: 'Statement of Work' })
        .click();

      const modal = page.locator('[data-testid="modal-content"]');
      await expect(modal).toBeVisible({ timeout: 5000 });

      // Close via the X button in the modal header
      await modal.locator('button').first().click();

      await expect(modal).not.toBeVisible({ timeout: 3000 });
    });

    test('modal closes on Escape key', async ({ page }) => {
      await setupRoutes(page);
      await triggerPackageSSE(page);

      // Open SOW viewer
      await page
        .locator('li[role="button"]', { hasText: 'Statement of Work' })
        .click();

      const modal = page.locator('[data-testid="modal-content"]');
      await expect(modal).toBeVisible({ timeout: 5000 });

      await page.keyboard.press('Escape');

      await expect(modal).not.toBeVisible({ timeout: 3000 });
    });

    test('can open different documents sequentially', async ({ page }) => {
      await setupRoutes(page);
      await triggerPackageSSE(page);

      // Open SOW
      await page
        .locator('li[role="button"]', { hasText: 'Statement of Work' })
        .click();

      let modal = page.locator('[data-testid="modal-content"]');
      await expect(modal).toBeVisible({ timeout: 5000 });
      await expect(
        modal.locator('h1', { hasText: 'Statement of Work' }),
      ).toBeVisible({ timeout: 5000 });

      // Close it
      await page.keyboard.press('Escape');
      await expect(modal).not.toBeVisible({ timeout: 3000 });

      // Open IGCE
      await page
        .locator('li[role="button"]', { hasText: 'Independent Government Cost Estimate' })
        .click();

      modal = page.locator('[data-testid="modal-content"]');
      await expect(modal).toBeVisible({ timeout: 5000 });
      await expect(
        modal.locator('h1', { hasText: 'Independent Government Cost Estimate' }),
      ).toBeVisible({ timeout: 5000 });

      // Should show table content
      await expect(modal.getByText('Cloud Infrastructure')).toBeVisible();
    });

    test('modal shows 80vw width', async ({ page }) => {
      await setupRoutes(page);
      await triggerPackageSSE(page);

      // Open SOW viewer
      await page
        .locator('li[role="button"]', { hasText: 'Statement of Work' })
        .click();

      const modal = page.locator('[data-testid="modal-content"]');
      await expect(modal).toBeVisible({ timeout: 5000 });

      const box = await modal.boundingBox();
      expect(box).not.toBeNull();

      const viewport = page.viewportSize();
      expect(viewport).not.toBeNull();

      const expectedWidth = viewport!.width * 0.8;
      expect(box!.width).toBeGreaterThanOrEqual(expectedWidth - 2);
    });
  });

  // ─── Session Restore Sync ─────────────────────────────────────────────

  test.describe('Session Restore Sync', () => {
    test('checklist populates from session context on load', async ({ page }) => {
      await setupRoutes(page, {
        contextPackage: {
          package_id: MOCK_PACKAGE_ID,
          status: 'drafting',
          checklist: MOCK_CHECKLIST,
        },
        sseEvents: [
          {
            type: 'text',
            agent_id: 'eagle',
            agent_name: 'EAGLE',
            content: 'Hello',
            timestamp: '2026-01-01T00:00:01Z',
          },
          {
            type: 'complete',
            agent_id: 'eagle',
            agent_name: 'EAGLE',
            metadata: {},
            timestamp: '2026-01-01T00:00:02Z',
          },
        ],
      });

      await page.goto('/chat/');

      // Wait for session context to load and populate the checklist
      // The Package tab should show checklist items from context restore
      await expect(
        page.getByText('Acquisition Package').first(),
      ).toBeVisible({ timeout: 8000 });

      // Progress should show 2/4 (50%)
      await expect(page.getByText('2/4')).toBeVisible({ timeout: 5000 });
    });
  });

  // ─── Post-Stream Auto-Refresh ──────────────────────────────────────────

  test.describe('Post-Stream Auto-Refresh', () => {
    test('checklist updates after streaming completes', async ({ page }) => {
      // Set up SSE with checklist that has 2/4 completed initially
      const sseEvents = [
        {
          type: 'text',
          agent_id: 'eagle',
          agent_name: 'EAGLE',
          content: 'Generating your documents...',
          timestamp: '2026-01-01T00:00:01Z',
        },
        {
          type: 'metadata',
          metadata: {
            state_type: 'checklist_update',
            package_id: MOCK_PACKAGE_ID,
            phase: 'drafting',
            checklist: {
              required: ['sow', 'igce', 'market_research', 'acquisition_plan'],
              completed: ['sow'],
              missing: ['igce', 'market_research', 'acquisition_plan'],
              complete: false,
            },
            progress_pct: 25,
          },
          timestamp: '2026-01-01T00:00:02Z',
        },
        {
          type: 'complete',
          agent_id: 'eagle',
          agent_name: 'EAGLE',
          metadata: {},
          timestamp: '2026-01-01T00:00:03Z',
        },
      ];

      // After streaming completes, the post-stream refresh fetches /context
      // which returns an updated checklist with 3/4 completed
      await setupRoutes(page, {
        sseEvents,
        contextPackage: {
          package_id: MOCK_PACKAGE_ID,
          status: 'drafting',
          checklist: {
            required: ['sow', 'igce', 'market_research', 'acquisition_plan'],
            completed: ['sow', 'igce', 'market_research'],
            missing: ['acquisition_plan'],
            complete: false,
          },
        },
      });

      await page.goto('/chat/');
      await page.getByRole('button', { name: 'New Chat' }).click();

      const textarea = page.locator('textarea');
      await expect(textarea).toBeEnabled({ timeout: 5000 });

      await textarea.fill('Generate documents for my acquisition');
      await page.getByRole('button', { name: '\u27A4' }).click();

      // Wait for streaming to complete
      await expect(textarea).toBeEnabled({ timeout: 15000 });

      // After post-stream refresh, checklist should show 3/4
      // (the /context mock returns 3 completed)
      await expect(page.getByText('3/4')).toBeVisible({ timeout: 8000 });
    });
  });
});
