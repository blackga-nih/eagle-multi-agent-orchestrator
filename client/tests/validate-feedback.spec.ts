import { test, expect } from '@playwright/test';

test.describe('Feedback modal', () => {
  test('Ctrl+J opens feedback modal', async ({ page }) => {
    await page.goto('/chat', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(2000);
    await page.keyboard.press('Control+j');
    await expect(page.locator('text=Send Feedback')).toBeVisible({ timeout: 3000 });
  });

  test('submitting feedback shows success or auth error', async ({ page }) => {
    await page.goto('/chat', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(2000);
    await page.keyboard.press('Control+j');

    // Fill in feedback
    const textarea = page.locator('textarea').first();
    await textarea.fill('Test feedback from Playwright');

    // Select a feedback type if available
    const typeBtn = page.locator('button:has-text("Bug")');
    if (await typeBtn.isVisible({ timeout: 1000 }).catch(() => false)) {
      await typeBtn.click();
    }

    // Submit
    const submitBtn = page.locator('button:has-text("Submit")');
    await submitBtn.click();

    // Should see either success message or auth error (both are valid)
    const result = page.locator('text=Thanks!, text=Session expired').first();
    await expect(result).toBeVisible({ timeout: 10_000 });
  });
});
