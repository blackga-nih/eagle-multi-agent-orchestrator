import { test, expect } from '@playwright/test';

test.describe('Documents Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/documents/');
  });

  test('displays page header and actions', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Documents', level: 1 })).toBeVisible();
    await expect(page.getByText('Create and manage acquisition documents')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Templates' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'New Document' })).toBeVisible();
  });

  test('displays document filter tabs', async ({ page }) => {
    await expect(page.getByRole('button', { name: /All Documents/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /Not Started/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /In Progress/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /Draft/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /Approved/ })).toBeVisible();
  });

  test('shows documents or empty state', async ({ page }) => {
    // Wait for loading to complete
    await page.waitForTimeout(2000);

    const hasDocuments = await page.getByRole('heading', { level: 3 }).count() > 0;
    const hasEmptyState = await page.getByText(/No documents/i).isVisible().catch(() => false);

    // Must show documents or empty state
    expect(hasDocuments || hasEmptyState).toBe(true);
  });

  test('has search functionality', async ({ page }) => {
    await expect(page.getByPlaceholder('Search documents...')).toBeVisible();
  });

  test('has filter by type dropdown', async ({ page }) => {
    await expect(page.getByRole('button', { name: 'Filter by Type' })).toBeVisible();
  });
});
