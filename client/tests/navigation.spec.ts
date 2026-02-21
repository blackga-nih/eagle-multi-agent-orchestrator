import { test, expect } from '@playwright/test';

test.describe('Navigation', () => {
  test('home page loads with EAGLE branding', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveURL('/');
    await expect(page).toHaveTitle(/EAGLE/);
    await expect(page.getByRole('heading', { name: 'EAGLE' }).first()).toBeVisible();
  });

  test('header shows backend connection status', async ({ page }) => {
    await page.goto('/');
    // "Connected" status in the header confirms frontend→backend connectivity
    await expect(page.getByText('Connected')).toBeVisible();
  });

  test('home page shows all feature navigation cards', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'Chat' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Document Templates' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Acquisition Packages' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Admin' })).toBeVisible();
  });

  test('backend health endpoint is reachable', async ({ request }) => {
    const resp = await request.get('http://localhost:8000/api/health');
    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();
    expect(body.status).toBe('healthy');
  });
});
