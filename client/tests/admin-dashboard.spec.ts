import { test, expect } from '@playwright/test';

test.describe('Admin Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/admin/');
  });

  test('displays dashboard overview', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Admin Dashboard', level: 1 })).toBeVisible();
    await expect(page.getByText('System overview and management')).toBeVisible();
  });

  test('displays metrics cards', async ({ page }) => {
    // Stats are now API-driven — labels are static, values may show loading or data
    await expect(page.getByText('Active Packages')).toBeVisible();
    await expect(page.getByText('Total Value')).toBeVisible();
    await expect(page.getByText('Documents Generated')).toBeVisible();
    await expect(page.getByText('Active Users')).toBeVisible();
  });

  test('displays Quick Actions section', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Quick Actions', level: 3 })).toBeVisible();

    // Quick actions no longer show item counts — just labels
    await expect(page.getByRole('link', { name: /Manage Users/ })).toBeVisible();
    await expect(page.getByRole('link', { name: /Document Templates/ })).toBeVisible();
    await expect(page.getByRole('link', { name: /Agent Skills/ })).toBeVisible();
    await expect(page.getByRole('link', { name: /Workspaces/ })).toBeVisible();
    await expect(page.getByRole('link', { name: /Test Results/ })).toBeVisible();
  });

  test('displays Recent Activity section with empty state', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Recent Activity', level: 3 })).toBeVisible();
    // Now shows empty state since mock audit logs were removed
    await expect(page.getByText('Activity log coming soon')).toBeVisible();
  });

  test('displays System Health section', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'System Health', level: 3 })).toBeVisible();

    await expect(page.getByText('AI Services')).toBeVisible();
    await expect(page.getByText('Database')).toBeVisible();
    await expect(page.getByText('Backend')).toBeVisible();
  });

  test('quick actions navigate correctly', async ({ page }) => {
    await page.getByRole('link', { name: /Manage Users/ }).click();
    await expect(page).toHaveURL(/\/admin\/users/);
  });
});
