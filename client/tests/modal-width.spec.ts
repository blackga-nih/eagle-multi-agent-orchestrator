import { test, expect } from '@playwright/test';

test.describe('Modal minimum width — 80% of viewport', () => {

  test('Command palette (Ctrl+K) spans at least 80% viewport width', async ({ page }) => {
    await page.goto('/chat/', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1500);

    await page.keyboard.press('Control+k');

    const modal = page.locator('[data-testid="modal-command-palette"]');
    await expect(modal).toBeVisible({ timeout: 3000 });

    const box = await modal.boundingBox();
    expect(box).not.toBeNull();

    const viewport = page.viewportSize();
    expect(viewport).not.toBeNull();

    const minWidth = viewport!.width * 0.8;
    expect(box!.width).toBeGreaterThanOrEqual(minWidth - 1); // -1 for sub-pixel rounding
  });

  test('Feedback modal (Ctrl+J) spans at least 80% viewport width', async ({ page }) => {
    await page.goto('/chat/', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1500);

    await page.keyboard.press('Control+j');

    const modal = page.locator('[data-testid="modal-content"]');
    await expect(modal).toBeVisible({ timeout: 3000 });

    const box = await modal.boundingBox();
    expect(box).not.toBeNull();

    const viewport = page.viewportSize();
    expect(viewport).not.toBeNull();

    const minWidth = viewport!.width * 0.8;
    expect(box!.width).toBeGreaterThanOrEqual(minWidth - 1);
  });
});
