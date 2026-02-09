import { test, expect } from '@playwright/test';

test.describe('Workflows Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/workflows/');
  });

  test('displays workflow list', async ({ page }) => {
    // Check page header
    await expect(page.getByRole('heading', { name: 'Workflows', level: 1 })).toBeVisible();

    // Check filter tabs exist (actual button names include counts)
    await expect(page.getByRole('button', { name: /All \d+/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /In Progress \d+/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /Pending Review \d+/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /Completed \d+/ })).toBeVisible();
  });

  test('displays workflow cards with correct structure', async ({ page }) => {
    // Check that at least one workflow card is displayed
    const workflowHeadings = page.getByRole('heading', { level: 3 });
    await expect(workflowHeadings.first()).toBeVisible();

    // Check workflow card contains expected status badge (check individual text)
    await expect(page.getByText('IN PROGRESS').first()).toBeVisible();
  });

  test('filter tabs work correctly', async ({ page }) => {
    // Click "In Progress" filter
    await page.getByRole('button', { name: /In Progress \d+/ }).click();

    // Should still be on workflows page
    await expect(page).toHaveURL(/\/workflows/);
  });

  test('has New Workflow button', async ({ page }) => {
    await expect(page.getByRole('button', { name: 'New Workflow' })).toBeVisible();
  });

  test('search input is available', async ({ page }) => {
    await expect(page.getByPlaceholder('Search workflows...')).toBeVisible();
  });
});
