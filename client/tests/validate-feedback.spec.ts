import { test, expect } from '@playwright/test';

test.describe('Feedback modal', () => {
  test('Ctrl+J opens feedback modal', async ({ page }) => {
    await page.goto('/chat', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(2000);
    await page.keyboard.press('Control+j');
    await expect(
      page.locator('text=What can Eagle improve on?'),
    ).toBeVisible({ timeout: 3000 });
  });

  test('modal shows refreshed type and area pills', async ({ page }) => {
    await page.goto('/chat', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(2000);
    await page.keyboard.press('Control+j');
    await expect(
      page.locator('text=What can Eagle improve on?'),
    ).toBeVisible({ timeout: 3000 });

    // Type pills (label copy was made friendlier)
    await expect(page.locator('label:has-text("How was the response?")')).toBeVisible();
    await expect(page.locator('button:has-text("Helpful")')).toBeVisible();
    await expect(page.locator('button:has-text("Inaccurate")')).toBeVisible();
    await expect(page.locator('button:has-text("Incomplete")')).toBeVisible();
    await expect(page.locator('button:has-text("Too verbose")')).toBeVisible();

    // Area pills — categories realigned to recent product surfaces
    await expect(page.locator('label:has-text("Which part of Eagle?")')).toBeVisible();
    await expect(page.locator('button:has-text("Chat & Responses")')).toBeVisible();
    await expect(page.locator('button:has-text("Documents (SOW / IGCE / AP)")')).toBeVisible();
    await expect(page.locator('button:has-text("Packages & Checklists")')).toBeVisible();
    await expect(page.locator('button:has-text("Knowledge Base & Sources")')).toBeVisible();
    await expect(page.locator('button:has-text("Compliance & Templates")')).toBeVisible();
    await expect(page.locator('button:has-text("Agent Routing")')).toBeVisible();
    await expect(page.locator('button:has-text("UI / Display")')).toBeVisible();
    await expect(page.locator('button:has-text("Performance")')).toBeVisible();
  });

  test('area pills toggle on click', async ({ page }) => {
    await page.goto('/chat', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(2000);
    await page.keyboard.press('Control+j');
    await expect(
      page.locator('text=What can Eagle improve on?'),
    ).toBeVisible({ timeout: 3000 });

    const chatBtn = page.locator('button:has-text("Chat & Responses")');
    // Click to select — should get amber background
    await chatBtn.click();
    await expect(chatBtn).toHaveClass(/bg-amber-600/);

    // Click again to deselect — should revert
    await chatBtn.click();
    await expect(chatBtn).toHaveClass(/bg-white/);
  });

  test('screenshot capture is no longer offered', async ({ page }) => {
    // The firewall blocks html2canvas; screenshot section was removed entirely
    // so users no longer see the failed-capture stub. Keep this guard so the
    // section can't sneak back in by accident.
    await page.goto('/chat', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(2000);
    await page.keyboard.press('Control+j');
    await expect(
      page.locator('text=What can Eagle improve on?'),
    ).toBeVisible({ timeout: 3000 });

    await expect(page.locator('label:has-text("Screenshot")')).toHaveCount(0);
    await expect(page.locator('button:has-text("Capture")')).toHaveCount(0);
    await expect(page.locator('img[alt="Screenshot preview"]')).toHaveCount(0);
  });

  test('textarea is auto-focused so users can start typing immediately', async ({ page }) => {
    await page.goto('/chat', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(2000);
    await page.keyboard.press('Control+j');
    await expect(
      page.locator('text=What can Eagle improve on?'),
    ).toBeVisible({ timeout: 3000 });

    const textarea = page.locator('textarea').first();
    // Auto-focus runs after a short post-mount delay; allow it to settle.
    await expect(textarea).toBeFocused({ timeout: 1000 });

    // Typing should land in the textarea without an explicit click first.
    await page.keyboard.type('hello');
    await expect(textarea).toHaveValue('hello');
  });

  test('submitting feedback shows success or auth error', async ({ page }) => {
    await page.goto('/chat', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(2000);
    await page.keyboard.press('Control+j');

    const textarea = page.locator('textarea').first();
    await textarea.fill('Test feedback from Playwright');

    const typeBtn = page.locator('button:has-text("Inaccurate")');
    if (await typeBtn.isVisible({ timeout: 1000 }).catch(() => false)) {
      await typeBtn.click();
    }

    const areaBtn = page.locator('button:has-text("Chat & Responses")');
    if (await areaBtn.isVisible({ timeout: 1000 }).catch(() => false)) {
      await areaBtn.click();
    }

    const submitBtn = page.locator('button:has-text("Send feedback")');
    await submitBtn.click();

    // Should see either success or auth error (both are valid in CI)
    const result = page.locator("text=Thanks — we're on it., text=Session expired").first();
    await expect(result).toBeVisible({ timeout: 10_000 });
  });
});
