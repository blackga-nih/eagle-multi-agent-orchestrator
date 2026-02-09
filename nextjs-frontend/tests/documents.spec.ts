import { test, expect } from '@playwright/test';

test.describe('Documents Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/documents/');
  });

  test('displays documents list', async ({ page }) => {
    // Check page header
    await expect(page.getByRole('heading', { name: 'Documents', level: 1 })).toBeVisible();
    await expect(page.getByText('Create and manage acquisition documents')).toBeVisible();

    // Check action buttons
    await expect(page.getByRole('button', { name: 'Templates' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'New Document' })).toBeVisible();
  });

  test('displays document filter tabs', async ({ page }) => {
    // Check filter tabs
    await expect(page.getByRole('button', { name: /All Documents/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /Not Started/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /In Progress/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /Draft/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /Approved/ })).toBeVisible();
  });

  test('displays document cards', async ({ page }) => {
    // Check that document cards are displayed
    const documentHeadings = page.getByRole('heading', { level: 3 });
    await expect(documentHeadings.first()).toBeVisible();

    // Check for status badges (check individual text)
    await expect(page.getByText('IN PROGRESS').first()).toBeVisible();
  });

  test('has search functionality', async ({ page }) => {
    await expect(page.getByPlaceholder('Search documents...')).toBeVisible();
  });

  test('has filter by type dropdown', async ({ page }) => {
    await expect(page.getByRole('button', { name: 'Filter by Type' })).toBeVisible();
  });

  test('document cards show version info', async ({ page }) => {
    // Check that version numbers are displayed
    const versionText = page.locator('text=/v\\d+/');
    await expect(versionText.first()).toBeVisible();
  });
});
