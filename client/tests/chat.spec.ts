import { test, expect } from '@playwright/test';

test.describe('Chat Page', () => {
  test('chat page loads with correct structure', async ({ page }) => {
    await page.goto('/chat/');
    await expect(page.getByPlaceholder(/Ask EAGLE/i)).toBeVisible();
    await expect(page.getByRole('button', { name: 'New Chat' })).toBeVisible();
    await expect(page.getByRole('button', { name: /New Intake/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /Generate SOW/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /Search FAR/i })).toBeVisible();
  });

  test('new chat shows welcome screen', async ({ page }) => {
    await page.goto('/chat/');
    await page.getByRole('button', { name: 'New Chat' }).click();
    await expect(page.getByRole('heading', { name: /Welcome to EAGLE/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /Acquisition Intake/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /Document Generation/i })).toBeVisible();
  });

  test('submit button enables when text is typed', async ({ page }) => {
    await page.goto('/chat/');
    await page.getByRole('button', { name: 'New Chat' }).click();
    const input = page.getByPlaceholder(/Ask EAGLE/i);
    await expect(input).toBeVisible();
    await input.fill('test');
    await expect(page.getByRole('button', { name: '➤' })).toBeEnabled();
  });

  // Requires running backend + agent — included in `just e2e full`
  // test.slow() triples the 30s default to 90s for agent streaming
  test('agent responds to a message', async ({ page }) => {
    test.slow();
    await page.goto('/chat/');
    await page.getByRole('button', { name: 'New Chat' }).click();
    // Blank new session — welcome screen, no agent messages yet
    await expect(page.locator('main').getByText('🦅 EAGLE')).toHaveCount(0, { timeout: 5000 });
    const input = page.getByPlaceholder(/Ask EAGLE/i);
    await input.fill('Hello');
    await page.getByRole('button', { name: '➤' }).click();
    // Wait for the first agent response header to appear
    await expect(page.locator('main').getByText('🦅 EAGLE')).toHaveCount(1, { timeout: 60000 });
  });
});
