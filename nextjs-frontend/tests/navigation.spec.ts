import { test, expect } from '@playwright/test';

test.describe('Navigation', () => {
  test('home page loads successfully', async ({ page }) => {
    await page.goto('/');

    // Check page title
    await expect(page).toHaveTitle(/EAGLE/);

    // Check main heading
    await expect(page.getByRole('heading', { name: 'EAGLE', level: 1 })).toBeVisible();

    // Check navigation links exist
    await expect(page.getByRole('link', { name: 'Intake' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Workflows' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Documents' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Admin' })).toBeVisible();
  });

  test('navigates to Workflows page', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('link', { name: 'Workflows' }).click();

    await expect(page).toHaveURL(/\/workflows/);
    await expect(page.getByRole('heading', { name: 'Workflows', level: 1 })).toBeVisible();
  });

  test('navigates to Documents page', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('link', { name: 'Documents' }).click();

    await expect(page).toHaveURL(/\/documents/);
    await expect(page.getByRole('heading', { name: 'Documents', level: 1 })).toBeVisible();
  });

  test('navigates to Admin Dashboard', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('link', { name: 'Admin' }).click();

    await expect(page).toHaveURL(/\/admin/);
    await expect(page.getByRole('heading', { name: 'Admin Dashboard', level: 1 })).toBeVisible();
  });
});
