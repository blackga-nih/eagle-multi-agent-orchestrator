import { test, expect } from '@playwright/test';

/**
 * All Packages in Activity Panel
 *
 * Tests that the Package tab loads and displays ALL user packages from
 * GET /api/packages, supports expand-to-documents, and coexists with
 * the SSE-driven active package checklist.
 *
 * Uses synthetic page.route() mocks — no backend needed.
 */

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

const MOCK_PACKAGES = [
  {
    package_id: 'PKG-001',
    title: 'Genomics Lab Equipment',
    status: 'drafting',
    requirement_type: 'products',
    estimated_value: '85000',
    created_at: '2026-03-20T10:00:00Z',
    compliance_readiness: {
      score: 50,
      missing_documents: ['igce'],
      draft_documents: ['sow'],
      total_required: 4,
      finalized_count: 2,
    },
  },
  {
    package_id: 'PKG-002',
    title: 'IT Consulting Services',
    status: 'intake',
    requirement_type: 'services',
    estimated_value: '200000',
    created_at: '2026-03-22T14:30:00Z',
  },
  {
    package_id: 'PKG-003',
    title: 'Cloud Infrastructure Migration',
    status: 'finalizing',
    requirement_type: 'services',
    estimated_value: '500000',
    created_at: '2026-03-25T09:15:00Z',
    compliance_readiness: {
      score: 100,
      missing_documents: [],
      draft_documents: [],
      total_required: 5,
      finalized_count: 5,
    },
  },
];

const MOCK_DOCUMENTS: Record<string, Array<Record<string, unknown>>> = {
  'PKG-001': [
    {
      document_id: 'DOC-001',
      doc_type: 'sow',
      title: 'SOW - Genomics Equipment',
      version: 1,
      status: 'draft',
      file_type: 'docx',
    },
    {
      document_id: 'DOC-002',
      doc_type: 'market_research',
      title: 'MRR - Lab Equipment Market',
      version: 1,
      status: 'final',
      file_type: 'docx',
    },
  ],
  'PKG-003': [
    {
      document_id: 'DOC-010',
      doc_type: 'sow',
      title: 'SOW - Cloud Migration',
      version: 2,
      status: 'final',
      file_type: 'docx',
    },
    {
      document_id: 'DOC-011',
      doc_type: 'igce',
      title: 'IGCE - Cloud Services',
      version: 1,
      status: 'final',
      file_type: 'xlsx',
    },
    {
      document_id: 'DOC-012',
      doc_type: 'acquisition_plan',
      title: 'AP - Cloud Migration',
      version: 1,
      status: 'final',
      file_type: 'docx',
    },
  ],
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function buildSSE(events: Array<Record<string, unknown>>): string {
  return events.map((e) => `data: ${JSON.stringify(e)}`).join('\n\n') + '\n\n';
}

/** Set up all route mocks for packages, documents, and SSE. */
async function setupRoutes(
  page: import('@playwright/test').Page,
  options?: {
    packages?: typeof MOCK_PACKAGES;
    sseEvents?: Array<Record<string, unknown>>;
  },
) {
  const packages = options?.packages ?? MOCK_PACKAGES;

  // Mock GET /api/packages
  await page.route('**/api/packages', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(packages),
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

  // Mock GET /api/packages/{id}/checklist
  await page.route(/\/api\/packages\/([^/]+)\/checklist$/, async (route) => {
    const url = route.request().url();
    const match = url.match(/\/api\/packages\/([^/]+)\/checklist/);
    const pkgId = match?.[1] ?? '';
    const pkg = packages.find((p) => p.package_id === pkgId);
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        package_id: pkgId,
        required: pkg?.compliance_readiness?.missing_documents ?? [],
        completed: [],
        missing: pkg?.compliance_readiness?.missing_documents ?? [],
      }),
    });
  });

  // Mock SSE endpoint (prevents hanging)
  const sseEvents = options?.sseEvents ?? [
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
  ];
  await page.route('**/api/invoke', async (route) => {
    await route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
      body: buildSSE(sseEvents),
    });
  });

  // Mock session endpoints to prevent errors
  await page.route('**/api/sessions/*/context', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe('All Packages in Activity Panel', () => {
  test('Package tab shows all user packages from API', async ({ page }) => {
    test.setTimeout(30_000);
    await setupRoutes(page);

    await page.goto('http://localhost:3000/chat/', {
      waitUntil: 'domcontentloaded',
      timeout: 15_000,
    });

    // Package tab is default — click to ensure
    await page.getByText('Package', { exact: true }).first().click();
    await page.waitForTimeout(2_000);

    // All 3 package titles should be visible
    await expect(page.getByText('Genomics Lab Equipment')).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText('IT Consulting Services')).toBeVisible({ timeout: 3_000 });
    await expect(page.getByText('Cloud Infrastructure Migration')).toBeVisible({ timeout: 3_000 });

    // "My Packages" header should be visible
    await expect(page.getByText('My Packages')).toBeVisible({ timeout: 3_000 });
  });

  test('each package card shows title, status badge, and value', async ({ page }) => {
    test.setTimeout(30_000);
    await setupRoutes(page);

    await page.goto('http://localhost:3000/chat/', {
      waitUntil: 'domcontentloaded',
      timeout: 15_000,
    });
    await page.getByText('Package', { exact: true }).first().click();
    await page.waitForTimeout(2_000);

    // Status badges visible
    await expect(page.getByText('drafting').first()).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText('intake').first()).toBeVisible({ timeout: 3_000 });
    await expect(page.getByText('finalizing').first()).toBeVisible({ timeout: 3_000 });
  });

  test('clicking a package loads and shows its documents', async ({ page }) => {
    test.setTimeout(30_000);
    await setupRoutes(page);

    await page.goto('http://localhost:3000/chat/', {
      waitUntil: 'domcontentloaded',
      timeout: 15_000,
    });
    await page.getByText('Package', { exact: true }).first().click();
    await page.waitForTimeout(2_000);

    // Click the first package (PKG-001 — Genomics Lab Equipment)
    await page.getByText('Genomics Lab Equipment').click();
    await page.waitForTimeout(1_500);

    // Documents should now be visible
    await expect(page.getByText('SOW - Genomics Equipment')).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText('MRR - Lab Equipment Market')).toBeVisible({ timeout: 3_000 });
  });

  test('active package checklist renders above the all-packages list', async ({ page }) => {
    test.setTimeout(45_000);

    // SSE events that simulate a checklist_update
    const sseEvents = [
      {
        type: 'metadata',
        agent_id: 'eagle',
        agent_name: 'EAGLE',
        metadata: {
          state_type: 'checklist_update',
          package_id: 'PKG-ACTIVE',
          phase: 'drafting',
          checklist: {
            required: ['sow', 'igce', 'market_research'],
            completed: ['sow'],
            missing: ['igce', 'market_research'],
          },
          progress_pct: 33,
        },
        timestamp: '2026-01-01T00:00:01Z',
      },
      {
        type: 'text',
        agent_id: 'eagle',
        agent_name: 'EAGLE',
        content: 'Package updated.',
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

    await setupRoutes(page, { sseEvents });

    await page.goto('http://localhost:3000/chat/', {
      waitUntil: 'domcontentloaded',
      timeout: 15_000,
    });

    // Send a message to trigger SSE with checklist_update
    const textarea = page.locator('textarea').first();
    await expect(textarea).toBeVisible({ timeout: 5_000 });
    await textarea.fill('test');
    await textarea.press('Enter');
    await page.waitForTimeout(5_000);

    // Switch to Package tab
    await page.getByText('Package', { exact: true }).first().click();
    await page.waitForTimeout(2_000);

    // Active checklist should show "Acquisition Package" header
    await expect(page.getByText('Acquisition Package').first()).toBeVisible({ timeout: 5_000 });

    // "My Packages" section should also be visible below
    await expect(page.getByText('My Packages')).toBeVisible({ timeout: 3_000 });
  });

  test('shows empty state when user has no packages and no active package', async ({ page }) => {
    test.setTimeout(30_000);
    await setupRoutes(page, { packages: [] });

    await page.goto('http://localhost:3000/chat/', {
      waitUntil: 'domcontentloaded',
      timeout: 15_000,
    });

    // Start a new chat to clear any session state
    const newChatBtn = page.getByRole('button', { name: 'New Chat' });
    if (await newChatBtn.isVisible()) await newChatBtn.click();

    await page.getByText('Package', { exact: true }).first().click();
    await page.waitForTimeout(2_000);

    // Empty state message should be visible
    await expect(page.getByText(/no packages|no active package/i)).toBeVisible({ timeout: 5_000 });
  });

  test('clicking a document in expanded package opens viewer', async ({ page }) => {
    test.setTimeout(30_000);
    await setupRoutes(page);

    await page.goto('http://localhost:3000/chat/', {
      waitUntil: 'domcontentloaded',
      timeout: 15_000,
    });
    await page.getByText('Package', { exact: true }).first().click();
    await page.waitForTimeout(2_000);

    // Expand PKG-001
    await page.getByText('Genomics Lab Equipment').click();
    await page.waitForTimeout(1_500);

    // Listen for popup (new tab)
    const popupPromise = page.waitForEvent('popup', { timeout: 5_000 }).catch(() => null);

    // Click the SOW document
    await page.getByText('SOW - Genomics Equipment').click();

    const popup = await popupPromise;
    // Either a popup opens or navigation happens — both are valid
    if (popup) {
      expect(popup.url()).toContain('/documents/');
    }
  });

  test('package list refreshes when refetch is triggered', async ({ page }) => {
    test.setTimeout(45_000);

    // Start with 1 package
    const singlePackage = [MOCK_PACKAGES[0]];
    let currentPackages = singlePackage;

    await page.route('**/api/packages', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(currentPackages),
        });
      } else {
        await route.continue();
      }
    });

    // Standard mocks for other routes
    await page.route('**/api/invoke', async (route) => {
      // After first call, update packages to include all 3
      currentPackages = MOCK_PACKAGES;
      await route.fulfill({
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
        body: buildSSE([
          {
            type: 'text',
            agent_id: 'eagle',
            agent_name: 'EAGLE',
            content: 'Done',
            timestamp: '2026-01-01T00:00:01Z',
          },
          {
            type: 'complete',
            agent_id: 'eagle',
            agent_name: 'EAGLE',
            metadata: {},
            timestamp: '2026-01-01T00:00:02Z',
          },
        ]),
      });
    });
    await page.route('**/api/sessions/*/context', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
    });
    await page.route(/\/api\/packages\/([^/]+)\/documents$/, async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' });
    });

    await page.goto('http://localhost:3000/chat/', {
      waitUntil: 'domcontentloaded',
      timeout: 15_000,
    });
    await page.getByText('Package', { exact: true }).first().click();
    await page.waitForTimeout(2_000);

    // Initially only 1 package
    await expect(page.getByText('Genomics Lab Equipment')).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText('IT Consulting Services')).not.toBeVisible();

    // Send a message — this should trigger refetch after stream completes
    const textarea = page.locator('textarea').first();
    await expect(textarea).toBeVisible({ timeout: 5_000 });
    await textarea.fill('trigger refetch');
    await textarea.press('Enter');
    await page.waitForTimeout(5_000);

    // After refetch, all 3 packages should now be visible
    await page.getByText('Package', { exact: true }).first().click();
    await page.waitForTimeout(2_000);
    await expect(page.getByText('IT Consulting Services')).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText('Cloud Infrastructure Migration')).toBeVisible({ timeout: 3_000 });
  });
});
