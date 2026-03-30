import { test, expect } from '@playwright/test';

test.describe('Workflows Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/workflows/');
  });

  test('displays page header and structure', async ({ page }) => {
    await expect(
      page.getByRole('heading', { name: 'Acquisition Packages', level: 1 }),
    ).toBeVisible();
    await expect(page.getByRole('button', { name: 'New Package' })).toBeVisible();
    await expect(page.getByPlaceholder('Search acquisition packages...')).toBeVisible();
  });

  test('displays filter tabs', async ({ page }) => {
    // Filter tabs exist — counts may be 0 if no packages
    await expect(page.getByRole('button', { name: /All/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /In Progress/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /Pending Review/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /Completed/ })).toBeVisible();
  });

  test('shows packages or empty state', async ({ page }) => {
    // Wait for loading to complete — either packages appear or empty state shows
    await page.waitForTimeout(2000);

    const hasPackages = (await page.getByRole('heading', { level: 3 }).count()) > 0;
    const hasEmptyState = await page
      .getByText('No acquisition packages yet')
      .isVisible()
      .catch(() => false);

    // Must show one or the other
    expect(hasPackages || hasEmptyState).toBe(true);
  });

  test('filter tabs are clickable', async ({ page }) => {
    await page.getByRole('button', { name: /In Progress/ }).click();
    await expect(page).toHaveURL(/\/workflows/);

    await page.getByRole('button', { name: /Completed/ }).click();
    await expect(page).toHaveURL(/\/workflows/);
  });
});
