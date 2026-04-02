import { test, expect } from '@playwright/test';

test.describe('Feedback modal', () => {
  test('Ctrl+J opens feedback modal', async ({ page }) => {
    await page.goto('/chat', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(2000);
    await page.keyboard.press('Control+j');
    await expect(page.locator('text=Send Feedback')).toBeVisible({ timeout: 3000 });
  });

  test('modal shows Type and Area pill rows', async ({ page }) => {
    await page.goto('/chat', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(2000);
    await page.keyboard.press('Control+j');
    await expect(page.locator('text=Send Feedback')).toBeVisible({ timeout: 3000 });

    // Type pills
    await expect(page.locator('label:has-text("Type")')).toBeVisible();
    await expect(page.locator('button:has-text("Helpful")')).toBeVisible();
    await expect(page.locator('button:has-text("Inaccurate")')).toBeVisible();
    await expect(page.locator('button:has-text("Incomplete")')).toBeVisible();
    await expect(page.locator('button:has-text("Too verbose")')).toBeVisible();

    // Area pills
    await expect(page.locator('label:has-text("Area")')).toBeVisible();
    await expect(page.locator('button:has-text("Network")')).toBeVisible();
    await expect(page.locator('button:has-text("Documents")')).toBeVisible();
    await expect(page.locator('button:has-text("Knowledge Base")')).toBeVisible();
    await expect(page.locator('button:has-text("Auth")')).toBeVisible();
    await expect(page.locator('button:has-text("Streaming")')).toBeVisible();
    await expect(page.locator('button:has-text("UI/Display")')).toBeVisible();
    await expect(page.locator('button:has-text("Performance")')).toBeVisible();
    await expect(page.locator('button:has-text("Tools")')).toBeVisible();
  });

  test('area pills toggle on click', async ({ page }) => {
    await page.goto('/chat', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(2000);
    await page.keyboard.press('Control+j');
    await expect(page.locator('text=Send Feedback')).toBeVisible({ timeout: 3000 });

    const networkBtn = page.locator('button:has-text("Network")');
    // Click to select — should get amber background
    await networkBtn.click();
    await expect(networkBtn).toHaveClass(/bg-amber-600/);

    // Click again to deselect — should revert
    await networkBtn.click();
    await expect(networkBtn).toHaveClass(/bg-white/);
  });

  test('screenshot section is present', async ({ page }) => {
    await page.goto('/chat', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(2000);
    await page.keyboard.press('Control+j');
    await expect(page.locator('text=Send Feedback')).toBeVisible({ timeout: 3000 });

    // Screenshot label should be visible
    await expect(page.locator('label:has-text("Screenshot")')).toBeVisible();

    // Should show either the captured preview image or the Capture button
    const captureBtn = page.locator('button:has-text("Capture")');
    const previewImg = page.locator('img[alt="Screenshot preview"]');
    const hasCapture = await captureBtn.isVisible({ timeout: 3000 }).catch(() => false);
    const hasPreview = await previewImg.isVisible({ timeout: 3000 }).catch(() => false);
    expect(hasCapture || hasPreview).toBeTruthy();
  });

  test('submitting feedback shows success or auth error', async ({ page }) => {
    await page.goto('/chat', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(2000);
    await page.keyboard.press('Control+j');

    // Fill in feedback
    const textarea = page.locator('textarea').first();
    await textarea.fill('Test feedback from Playwright');

    // Select a feedback type
    const typeBtn = page.locator('button:has-text("Inaccurate")');
    if (await typeBtn.isVisible({ timeout: 1000 }).catch(() => false)) {
      await typeBtn.click();
    }

    // Select an area
    const areaBtn = page.locator('button:has-text("Network")');
    if (await areaBtn.isVisible({ timeout: 1000 }).catch(() => false)) {
      await areaBtn.click();
    }

    // Submit
    const submitBtn = page.locator('button:has-text("Submit")');
    await submitBtn.click();

    // Should see either success message or auth error (both are valid)
    const result = page.locator('text=Thanks!, text=Session expired').first();
    await expect(result).toBeVisible({ timeout: 10_000 });
  });
});
