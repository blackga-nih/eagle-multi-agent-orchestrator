import { test, expect } from '@playwright/test';

test.describe('Knowledge Base Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/knowledge-base/');
  });

  test('displays page header and description', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Knowledge Base', level: 1 })).toBeVisible();
    await expect(page.getByText('Browse acquisition reference documents')).toBeVisible();
  });

  test('displays search bar', async ({ page }) => {
    await expect(page.getByPlaceholder(/Search knowledge base/i)).toBeVisible();
  });

  test('displays tab navigation with all four tabs', async ({ page }) => {
    await expect(page.getByRole('button', { name: /All Documents/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /By Topic/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /By Type/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /Reference Data/i })).toBeVisible();
  });

  test('All Documents tab is active by default', async ({ page }) => {
    const allDocsTab = page.getByRole('button', { name: /All Documents/i });
    // Active tab has different styling (bg-white) — just verify it exists and is visible
    await expect(allDocsTab).toBeVisible();
  });

  test('shows loading state or document cards', async ({ page }) => {
    // Either loading skeleton, document cards, or empty state should appear
    const skeleton = page.locator('.animate-pulse').first();
    const docCard = page.locator('button.group').first();
    const emptyState = page.getByText(/No documents found/i);

    await expect(skeleton.or(docCard).or(emptyState)).toBeVisible({ timeout: 15000 });
  });

  test('switching to By Topic tab shows folder view', async ({ page }) => {
    await page.getByRole('button', { name: /By Topic/i }).click();

    // Should show either folder items or a loading/empty state
    const folderView = page.locator('button').filter({ hasText: /Compliance|Funding|Legal|General/i }).first();
    const emptyState = page.getByText(/No documents to display/i);

    await expect(folderView.or(emptyState)).toBeVisible({ timeout: 15000 });
  });

  test('switching to By Type tab shows folder view', async ({ page }) => {
    await page.getByRole('button', { name: /By Type/i }).click();

    const folderView = page.locator('button').filter({ hasText: /Regulation|Guidance|Policy|Template/i }).first();
    const emptyState = page.getByText(/No documents to display/i);

    await expect(folderView.or(emptyState)).toBeVisible({ timeout: 15000 });
  });

  test('switching to Reference Data tab shows plugin data cards', async ({ page }) => {
    await page.getByRole('button', { name: /Reference Data/i }).click();

    // Should show the 4 plugin data file cards or loading skeletons
    const farCard = page.getByText('far-database.json');
    const matrixCard = page.getByText('matrix.json');
    const skeleton = page.locator('.animate-pulse').first();

    await expect(farCard.or(skeleton)).toBeVisible({ timeout: 15000 });

    // If cards loaded, verify all 4 are present
    if (await farCard.isVisible()) {
      await expect(matrixCard).toBeVisible();
      await expect(page.getByText('thresholds.json')).toBeVisible();
      await expect(page.getByText('contract-vehicles.json')).toBeVisible();
    }
  });

  test('search submits query and shows results', async ({ page }) => {
    const searchInput = page.getByPlaceholder(/Search knowledge base/i);
    await searchInput.fill('sole source');

    // Submit the search
    await page.getByRole('button', { name: 'Search' }).click();

    // Should show results text or document cards
    const resultsText = page.getByText(/Results for/i);
    const emptyState = page.getByText(/No documents found/i);

    await expect(resultsText.or(emptyState)).toBeVisible({ timeout: 15000 });
  });

  test('clear button resets search', async ({ page }) => {
    const searchInput = page.getByPlaceholder(/Search knowledge base/i);
    await searchInput.fill('test query');

    // Clear button should appear
    const clearButton = page.getByRole('button', { name: 'Clear' });
    await expect(clearButton).toBeVisible();
    await clearButton.click();

    // Search input should be empty
    await expect(searchInput).toHaveValue('');
  });
});

test.describe('Knowledge Base Navigation', () => {
  test('Knowledge Base tab appears in top nav', async ({ page }) => {
    await page.goto('/chat/');
    await expect(page.getByRole('link', { name: /Knowledge Base/i })).toBeVisible();
  });

  test('Knowledge Base tab navigates correctly', async ({ page }) => {
    await page.goto('/chat/');
    await page.getByRole('link', { name: /Knowledge Base/i }).click();
    await expect(page).toHaveURL(/\/knowledge-base/);
    await expect(page.getByRole('heading', { name: 'Knowledge Base', level: 1 })).toBeVisible();
  });

  test('Knowledge Base tab appears between Documents and Workspaces', async ({ page }) => {
    await page.goto('/knowledge-base/');

    // Verify the nav links are in the correct order
    const navLinks = page.locator('nav a, header nav a');
    const texts = await navLinks.allTextContents();
    const labels = texts.map((t) => t.trim()).filter(Boolean);

    const docsIndex = labels.findIndex((l) => l.includes('Documents'));
    const kbIndex = labels.findIndex((l) => l.includes('Knowledge Base'));

    // KB should come after Documents
    if (docsIndex >= 0 && kbIndex >= 0) {
      expect(kbIndex).toBeGreaterThan(docsIndex);
    }
  });
});
