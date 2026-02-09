import { test, expect } from '@playwright/test';

test.describe('Admin Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/admin/');
  });

  test('displays dashboard overview', async ({ page }) => {
    // Check page header
    await expect(page.getByRole('heading', { name: 'Admin Dashboard', level: 1 })).toBeVisible();
    await expect(page.getByText('System overview and management')).toBeVisible();
  });

  test('displays metrics cards', async ({ page }) => {
    // Check key metrics are displayed
    await expect(page.getByText('Active Workflows')).toBeVisible();
    await expect(page.getByText('Total Value')).toBeVisible();
    await expect(page.getByText('Documents Generated')).toBeVisible();
    await expect(page.getByText('Avg. Completion Time')).toBeVisible();
  });

  test('displays Quick Actions section', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Quick Actions', level: 3 })).toBeVisible();

    // Check quick action links (use exact names to avoid duplicates from sidebar)
    await expect(page.getByRole('link', { name: 'Manage Users 5 items' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Document Templates 4 items' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Agent Skills 4 items' })).toBeVisible();
  });

  test('displays Recent Activity section', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Recent Activity', level: 3 })).toBeVisible();

    // Check activity items exist (check for individual text)
    await expect(page.getByText('Created').first()).toBeVisible();
  });

  test('displays System Health section', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'System Health', level: 3 })).toBeVisible();

    // Check health status items
    await expect(page.getByText('AI Services')).toBeVisible();
    await expect(page.getByText('Database')).toBeVisible();
    await expect(page.getByText('API Rate Limit')).toBeVisible();
  });

  test('quick actions navigate correctly', async ({ page }) => {
    await page.getByRole('link', { name: /Manage Users/ }).click();
    await expect(page).toHaveURL(/\/admin\/users/);
  });
});
