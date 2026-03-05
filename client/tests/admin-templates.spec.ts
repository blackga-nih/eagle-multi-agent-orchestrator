import { test, expect } from '@playwright/test';

test.describe('Admin Templates Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/admin/templates/');
  });

  test('displays page header', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Document Templates' })).toBeVisible();
    await expect(page.getByText('Manage reusable document templates and overrides')).toBeVisible();
  });

  test('displays breadcrumb navigation', async ({ page }) => {
    await expect(page.getByRole('link', { name: 'Admin' })).toBeVisible();
    await expect(page.getByText('Templates').first()).toBeVisible();
  });

  test('has New Template button', async ({ page }) => {
    await expect(page.getByRole('button', { name: /New Template/ })).toBeVisible();
  });

  test('has Refresh button', async ({ page }) => {
    await expect(page.getByRole('button', { name: /Refresh/ })).toBeVisible();
  });

  test('has search input', async ({ page }) => {
    await expect(page.getByPlaceholder('Search templates...')).toBeVisible();
  });

  test('shows loading state or template cards', async ({ page }) => {
    const loading = page.getByText('Loading templates...');
    const cards = page.getByRole('heading', { level: 3 });
    const empty = page.getByText('No templates found.');

    await expect(loading.or(cards.first()).or(empty)).toBeVisible();
  });

  test('template cards show document type badges', async ({ page }) => {
    await page.waitForSelector('text=Loading templates...', { state: 'hidden' }).catch(() => {});

    const cards = page.getByRole('heading', { level: 3 });
    const count = await cards.count();
    if (count > 0) {
      // Document type labels from the page source
      const docTypes = page.getByText('Statement of Work')
        .or(page.getByText('Cost Estimate (IGCE)'))
        .or(page.getByText('Market Research'))
        .or(page.getByText('Acquisition Plan'))
        .or(page.getByText('Justification'))
        .or(page.getByText('Funding Document'));
      await expect(docTypes.first()).toBeVisible();
    }
  });

  test('template cards show source badge (Bundled or Custom)', async ({ page }) => {
    await page.waitForSelector('text=Loading templates...', { state: 'hidden' }).catch(() => {});

    const cards = page.getByRole('heading', { level: 3 });
    const count = await cards.count();
    if (count > 0) {
      const sourceBadge = page.getByText('Bundled', { exact: true })
        .or(page.getByText('Custom', { exact: true }));
      await expect(sourceBadge.first()).toBeVisible();
    }
  });

  test('template cards show name', async ({ page }) => {
    await page.waitForSelector('text=Loading templates...', { state: 'hidden' }).catch(() => {});

    const cards = page.getByRole('heading', { level: 3 });
    const count = await cards.count();
    if (count > 0) {
      await expect(cards.first()).toBeVisible();
    }
  });

  test('breadcrumb navigates back to admin dashboard', async ({ page }) => {
    await page.getByRole('link', { name: 'Admin' }).click();
    await expect(page).toHaveURL(/\/admin/);
  });
});
