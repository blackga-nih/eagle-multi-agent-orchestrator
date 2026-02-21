import { test, expect } from '@playwright/test';

/**
 * UC: FAR/DFARS Search Workflow
 *
 * Simulates a contracting officer searching federal acquisition regulations.
 * Verifies the agent returns a regulation reference with FAR part citations
 * and threshold/procedure details.
 */
test.describe('UC: FAR/DFARS Search Workflow', () => {
  test('FAR query → regulation reference with citation', async ({ page }) => {
    test.slow(); // 90s budget for agent streaming

    await page.goto('/chat/');
    await page.getByRole('button', { name: 'New Chat' }).click();
    await expect(page.getByRole('heading', { name: /Welcome to EAGLE/i })).toBeVisible();

    // Click the Search FAR quick action — fills textarea with simplified acquisition query
    await page.getByRole('button', { name: /Search FAR/i }).click();
    await expect(page.getByRole('button', { name: '➤' })).toBeEnabled();
    await page.getByRole('button', { name: '➤' }).click();

    // Agent responds with FAR reference
    await expect(page.locator('main').getByText('🦅 EAGLE')).toHaveCount(1, { timeout: 60000 });

    // Response should include FAR citation and regulation content
    await expect(page.locator('main')).toContainText(
      /FAR|Part \d+|simplified acquisition|threshold|federal acquisition|regulation|DFARS/i
    );
  });
});
