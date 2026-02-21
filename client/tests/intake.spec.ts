import { test, expect } from '@playwright/test';

test.describe('Home Page & Backend Connectivity', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('home page renders hero section', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'EAGLE' }).first()).toBeVisible();
    await expect(page.getByRole('heading', { name: 'AI-Powered Acquisition Assistant' })).toBeVisible();
  });

  test('home page description mentions NCI', async ({ page }) => {
    await expect(page.getByText(/NCI Office of Acquisitions/)).toBeVisible();
  });

  test('footer shows NCI and Claude branding', async ({ page }) => {
    await expect(page.getByText(/National Cancer Institute/)).toBeVisible();
  });

  test('backend tools endpoint returns data', async ({ request }) => {
    // /api/tools is called by the frontend on every page load
    const resp = await request.get('http://localhost:8000/api/tools');
    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();
    expect(body).toHaveProperty('tools');
  });

  test('backend health reports healthy', async ({ request }) => {
    const resp = await request.get('http://localhost:8000/api/health');
    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();
    expect(body.status).toBe('healthy');
  });
});
