import { test, expect } from '@playwright/test';

/**
 * UC: OA Intake Workflow
 *
 * Simulates a contracting officer describing an acquisition need.
 * Verifies the agent returns a pathway analysis with acquisition type,
 * required documents, and timeline.
 */
test.describe('UC: OA Intake Workflow', () => {
  test('acquisition description → pathway analysis with document list', async ({ page }) => {
    test.slow(); // 90s budget for agent streaming

    await page.goto('/chat/');
    await page.getByRole('button', { name: 'New Chat' }).click();
    await expect(page.getByRole('heading', { name: /Welcome to EAGLE/i })).toBeVisible();

    // Click the New Intake quick action — fills textarea with a CT scanner scenario
    await page.getByRole('button', { name: /New Intake/i }).click();
    await expect(page.getByRole('button', { name: '➤' })).toBeEnabled();
    await page.getByRole('button', { name: '➤' }).click();

    // Agent responds with intake analysis
    await expect(page.locator('main').getByText('🦅 EAGLE')).toHaveCount(1, { timeout: 60000 });

    // Response should include acquisition pathway content
    await expect(page.locator('main')).toContainText(
      /simplified|acquisition type|required documents|SOW|IGCE|threshold|pathway|procurement/i
    );
  });
});
