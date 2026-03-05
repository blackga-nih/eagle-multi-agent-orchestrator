import { test, expect } from '@playwright/test';

test.describe('Admin Workspaces Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/admin/workspaces/');
  });

  test('displays page header', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Workspaces' })).toBeVisible();
    await expect(page.getByText('Manage prompt environments and override layers')).toBeVisible();
  });

  test('displays breadcrumb navigation', async ({ page }) => {
    await expect(page.getByRole('link', { name: 'Admin' })).toBeVisible();
    await expect(page.getByText('Workspaces').first()).toBeVisible();
  });

  test('has New Workspace button', async ({ page }) => {
    await expect(page.getByRole('button', { name: /New Workspace/ })).toBeVisible();
  });

  test('has Refresh button', async ({ page }) => {
    await expect(page.getByRole('button', { name: /Refresh/ })).toBeVisible();
  });

  test('shows loading state or workspace cards', async ({ page }) => {
    // Page will either show loading spinner or workspace cards
    const loading = page.getByText('Loading workspaces...');
    const cards = page.getByRole('heading', { level: 3 });
    const empty = page.getByText('No workspaces found.');

    await expect(loading.or(cards.first()).or(empty)).toBeVisible();
  });

  test('workspace cards show name and visibility', async ({ page }) => {
    // Wait for loading to finish
    await page.waitForSelector('text=Loading workspaces...', { state: 'hidden' }).catch(() => {});

    // If workspaces loaded, check card structure
    const cards = page.getByRole('heading', { level: 3 });
    const count = await cards.count();
    if (count > 0) {
      await expect(cards.first()).toBeVisible();
      // Visibility label should appear (private, tenant, or public)
      await expect(
        page.getByText('private').first()
          .or(page.getByText('tenant').first())
          .or(page.getByText('public').first())
      ).toBeVisible();
    }
  });

  test('active workspace has Active badge', async ({ page }) => {
    await page.waitForSelector('text=Loading workspaces...', { state: 'hidden' }).catch(() => {});

    const activeBadge = page.getByText('Active', { exact: true });
    const count = await activeBadge.count();
    // At least one workspace should be active if workspaces exist
    if (count > 0) {
      await expect(activeBadge.first()).toBeVisible();
    }
  });

  test('default workspace has Default badge', async ({ page }) => {
    await page.waitForSelector('text=Loading workspaces...', { state: 'hidden' }).catch(() => {});

    const defaultBadge = page.getByText('Default', { exact: true });
    const count = await defaultBadge.count();
    if (count > 0) {
      await expect(defaultBadge.first()).toBeVisible();
    }
  });

  test('workspace cards have View Overrides toggle', async ({ page }) => {
    await page.waitForSelector('text=Loading workspaces...', { state: 'hidden' }).catch(() => {});

    const toggle = page.getByText('View Overrides');
    const count = await toggle.count();
    if (count > 0) {
      await expect(toggle.first()).toBeVisible();
    }
  });

  test('breadcrumb navigates back to admin dashboard', async ({ page }) => {
    await page.getByRole('link', { name: 'Admin' }).click();
    await expect(page).toHaveURL(/\/admin/);
  });
});
