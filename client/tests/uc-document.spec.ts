import { test, expect } from '@playwright/test';

/**
 * UC: Document Generation Workflow
 *
 * Simulates a contracting officer requesting a Statement of Work.
 * Verifies the agent returns structured document content with
 * SOW sections (scope, deliverables, objectives, requirements).
 */
test.describe('UC: Document Generation Workflow', () => {
  test('SOW request → structured document content returned', async ({ page }) => {
    test.slow(); // 90s budget for agent streaming

    await page.goto('/chat/');
    await page.getByRole('button', { name: 'New Chat' }).click();
    await expect(page.getByRole('heading', { name: /Welcome to EAGLE/i })).toBeVisible();

    // Click the Generate SOW quick action — fills textarea with an IT services scenario
    await page.getByRole('button', { name: /Generate SOW/i }).click();
    await expect(page.getByRole('button', { name: '➤' })).toBeEnabled();
    await page.getByRole('button', { name: '➤' }).click();

    // Agent responds with SOW content
    await expect(page.locator('main').getByText('🦅 EAGLE')).toHaveCount(1, { timeout: 60000 });

    // Response should include SOW structural elements
    await expect(page.locator('main')).toContainText(
      /statement of work|scope|deliverable|objective|requirement|performance|contract/i
    );
  });
});
