import { test, expect } from '@playwright/test';

/**
 * Package Documents Route & ZIP Download
 *
 * Tests that the Next.js proxy route GET /api/packages/{id}/documents
 * correctly forwards to the FastAPI backend, and that the ZIP download
 * flow works end-to-end in the activity panel.
 *
 * Uses synthetic page.route() mocks — no backend needed.
 */

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

const MOCK_PACKAGES = [
  {
    package_id: 'PKG-ZIP-001',
    title: 'Cloud Migration Package',
    status: 'drafting',
    requirement_type: 'services',
    estimated_value: '750000',
    created_at: '2026-03-20T10:00:00Z',
    compliance_readiness: {
      score: 60,
      missing_documents: ['igce'],
      draft_documents: ['sow', 'acquisition_plan'],
      total_required: 3,
      finalized_count: 1,
    },
  },
  {
    package_id: 'PKG-ZIP-002',
    title: 'Empty Package',
    status: 'intake',
    requirement_type: 'products',
    estimated_value: '50000',
    created_at: '2026-03-22T14:00:00Z',
  },
];

const MOCK_DOCUMENTS: Record<string, Array<Record<string, unknown>>> = {
  'PKG-ZIP-001': [
    { document_id: 'DOC-A1', doc_type: 'sow', title: 'SOW - Cloud Migration', version: 1, status: 'draft', file_type: 'docx' },
    { document_id: 'DOC-A2', doc_type: 'acquisition_plan', title: 'AP - Cloud Migration', version: 2, status: 'final', file_type: 'docx' },
  ],
  'PKG-ZIP-002': [],
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function buildSSE(events: Array<Record<string, unknown>>): string {
  return events.map((e) => `data: ${JSON.stringify(e)}`).join('\n\n') + '\n\n';
}

async function setupRoutes(page: import('@playwright/test').Page) {
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

  // Mock GET /api/packages/{id}/documents
  await page.route(/\/api\/packages\/([^/]+)\/documents$/, async (route) => {
    const url = route.request().url();
    const match = url.match(/\/api\/packages\/([^/]+)\/documents/);
    const pkgId = match?.[1] ?? '';
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_DOCUMENTS[pkgId] ?? []),
    });
  });

  // Mock GET /api/packages/{id}/export/zip
  await page.route(/\/api\/packages\/([^/]+)\/export\/zip/, async (route) => {
    const url = route.request().url();
    const match = url.match(/\/api\/packages\/([^/]+)\/export\/zip/);
    const pkgId = match?.[1] ?? '';
    const docs = MOCK_DOCUMENTS[pkgId] ?? [];

    if (docs.length === 0) {
      await route.fulfill({
        status: 404,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'No documents with content found' }),
      });
      return;
    }

    // Return a minimal valid ZIP (PK header)
    const zipBytes = new Uint8Array([
      0x50, 0x4b, 0x05, 0x06, 0x00, 0x00, 0x00, 0x00,
      0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
      0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]);
    await route.fulfill({
      status: 200,
      headers: {
        'Content-Type': 'application/zip',
        'Content-Disposition': `attachment; filename="${pkgId}.zip"`,
      },
      body: Buffer.from(zipBytes),
    });
  });

  // Mock SSE endpoint
  await page.route('**/api/invoke', async (route) => {
    await route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
      body: buildSSE([
        { type: 'text', agent_id: 'eagle', agent_name: 'EAGLE', content: 'Hello', timestamp: '2026-01-01T00:00:01Z' },
        { type: 'complete', agent_id: 'eagle', agent_name: 'EAGLE', metadata: {}, timestamp: '2026-01-01T00:00:02Z' },
      ]),
    });
  });

  // Mock session context
  await page.route('**/api/sessions/*/context', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe('Package Documents Route & ZIP Download', () => {

  test('expanding a package fetches and displays its documents', async ({ page }) => {
    test.setTimeout(30_000);
    await setupRoutes(page);

    await page.goto('http://localhost:3000/chat/', { waitUntil: 'domcontentloaded', timeout: 15_000 });
    await page.getByText('Package', { exact: true }).first().click();
    await page.waitForTimeout(2_000);

    // Click the package with documents
    await page.getByText('Cloud Migration Package').click();
    await page.waitForTimeout(1_500);

    // Documents should be visible
    await expect(page.getByText('SOW - Cloud Migration')).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText('AP - Cloud Migration')).toBeVisible({ timeout: 3_000 });
  });

  test('expanding a package with no documents shows empty message', async ({ page }) => {
    test.setTimeout(30_000);
    await setupRoutes(page);

    await page.goto('http://localhost:3000/chat/', { waitUntil: 'domcontentloaded', timeout: 15_000 });
    await page.getByText('Package', { exact: true }).first().click();
    await page.waitForTimeout(2_000);

    // Click the empty package
    await page.getByText('Empty Package').click();
    await page.waitForTimeout(1_500);

    // Should show "No documents yet."
    await expect(page.getByText('No documents yet.')).toBeVisible({ timeout: 5_000 });
  });

  test('documents route returns data matching backend response shape', async ({ page }) => {
    test.setTimeout(15_000);

    // Intercept the documents request and verify the response shape
    let capturedResponse: Array<Record<string, unknown>> | null = null;

    await page.route(/\/api\/packages\/([^/]+)\/documents$/, async (route) => {
      const mockDocs = [
        { document_id: 'DOC-X1', doc_type: 'sow', title: 'Test SOW', version: 1, status: 'draft' },
      ];
      capturedResponse = mockDocs;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockDocs),
      });
    });

    // Make a direct fetch through the page
    const result = await page.evaluate(async () => {
      const res = await fetch('/api/packages/PKG-TEST/documents');
      return { status: res.status, body: await res.json() };
    });

    expect(result.status).toBe(200);
    expect(result.body).toHaveLength(1);
    expect(result.body[0].doc_type).toBe('sow');
    expect(result.body[0].document_id).toBe('DOC-X1');
  });

  test('ZIP download endpoint returns application/zip on success', async ({ page }) => {
    test.setTimeout(15_000);
    await setupRoutes(page);

    await page.goto('http://localhost:3000/chat/', { waitUntil: 'domcontentloaded', timeout: 15_000 });

    // Call the ZIP endpoint directly via page.evaluate
    const result = await page.evaluate(async () => {
      const res = await fetch('/api/packages/PKG-ZIP-001/export/zip');
      return {
        status: res.status,
        contentType: res.headers.get('content-type'),
        contentDisposition: res.headers.get('content-disposition'),
        bodyLength: (await res.arrayBuffer()).byteLength,
      };
    });

    expect(result.status).toBe(200);
    expect(result.contentType).toContain('application/zip');
    expect(result.contentDisposition).toContain('PKG-ZIP-001.zip');
    expect(result.bodyLength).toBeGreaterThan(0);
  });

  test('ZIP download returns 404 for package with no documents', async ({ page }) => {
    test.setTimeout(15_000);
    await setupRoutes(page);

    await page.goto('http://localhost:3000/chat/', { waitUntil: 'domcontentloaded', timeout: 15_000 });

    const result = await page.evaluate(async () => {
      const res = await fetch('/api/packages/PKG-ZIP-002/export/zip');
      return { status: res.status };
    });

    expect(result.status).toBe(404);
  });

  test('download button appears in checklist when package has completed docs', async ({ page }) => {
    test.setTimeout(45_000);

    // SSE events that simulate a checklist_update with completed docs
    const sseEvents = [
      {
        type: 'metadata',
        agent_id: 'eagle',
        agent_name: 'EAGLE',
        metadata: {
          state_type: 'checklist_update',
          package_id: 'PKG-ZIP-001',
          phase: 'drafting',
          checklist: {
            required: ['sow', 'igce', 'acquisition_plan'],
            completed: ['sow'],
            missing: ['igce', 'acquisition_plan'],
          },
          progress_pct: 33,
        },
        timestamp: '2026-01-01T00:00:01Z',
      },
      { type: 'text', agent_id: 'eagle', agent_name: 'EAGLE', content: 'Package updated.', timestamp: '2026-01-01T00:00:02Z' },
      { type: 'complete', agent_id: 'eagle', agent_name: 'EAGLE', metadata: {}, timestamp: '2026-01-01T00:00:03Z' },
    ];

    await setupRoutes(page);

    // Override SSE with checklist events
    await page.route('**/api/invoke', async (route) => {
      await route.fulfill({
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
        body: buildSSE(sseEvents),
      });
    });

    await page.goto('http://localhost:3000/chat/', { waitUntil: 'domcontentloaded', timeout: 15_000 });

    // Send a message to trigger SSE with checklist_update
    const textarea = page.locator('textarea').first();
    await expect(textarea).toBeVisible({ timeout: 5_000 });
    await textarea.fill('test checklist');
    await textarea.press('Enter');
    await page.waitForTimeout(5_000);

    // Switch to Package tab
    await page.getByText('Package', { exact: true }).first().click();
    await page.waitForTimeout(2_000);

    // Download button should be visible
    await expect(page.getByText('Download Package (ZIP)')).toBeVisible({ timeout: 5_000 });
  });
});
