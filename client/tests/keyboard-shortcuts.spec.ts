import { test, expect } from '@playwright/test';

test.describe('Keyboard Shortcuts', () => {

  // ─── Command Palette (Ctrl+K) ────────────────────────────────────────

  test.describe('Command Palette — Ctrl+K', () => {
    test('Ctrl+K opens the command palette', async ({ page }) => {
      await page.goto('/chat/');
      // Palette should not be visible initially
      await expect(page.locator('.fixed.inset-0').locator('input[placeholder="Search commands..."]')).not.toBeVisible();

      await page.keyboard.press('Control+k');

      // Palette overlay appears with the search input
      const searchInput = page.locator('input[placeholder="Search commands..."]');
      await expect(searchInput).toBeVisible({ timeout: 3000 });
    });

    test('command palette shows search input', async ({ page }) => {
      await page.goto('/chat/');
      await page.keyboard.press('Control+k');

      const searchInput = page.locator('input[placeholder="Search commands..."]');
      await expect(searchInput).toBeVisible();
      await expect(searchInput).toBeFocused();
    });

    test('command palette lists command categories', async ({ page }) => {
      await page.goto('/chat/');
      await page.keyboard.press('Control+k');

      // The palette groups commands under category headings:
      // Documents, Compliance, Research, Workflow, Admin, Info
      await expect(page.getByText('Documents', { exact: true })).toBeVisible();
      await expect(page.getByText('Compliance', { exact: true })).toBeVisible();
      await expect(page.getByText('Research', { exact: true })).toBeVisible();
    });

    test('Escape closes the command palette', async ({ page }) => {
      await page.goto('/chat/');
      await page.keyboard.press('Control+k');
      await expect(page.locator('input[placeholder="Search commands..."]')).toBeVisible();

      await page.keyboard.press('Escape');

      // Palette should disappear (the component returns null when not open)
      await expect(page.locator('input[placeholder="Search commands..."]')).not.toBeVisible();
    });

    test('Ctrl+K toggles the command palette closed', async ({ page }) => {
      await page.goto('/chat/');

      // Open
      await page.keyboard.press('Control+k');
      await expect(page.locator('input[placeholder="Search commands..."]')).toBeVisible();

      // Close via same shortcut
      await page.keyboard.press('Control+k');
      await expect(page.locator('input[placeholder="Search commands..."]')).not.toBeVisible();
    });

    test('command palette search filters commands', async ({ page }) => {
      await page.goto('/chat/');
      await page.keyboard.press('Control+k');

      const searchInput = page.locator('input[placeholder="Search commands..."]');
      await searchInput.fill('SOW');

      // Should show the SOW command and hide unrelated ones
      await expect(page.getByText('/document:SOW')).toBeVisible();
    });
  });

  // ─── Feedback Modal (Ctrl+J) ─────────────────────────────────────────

  test.describe('Feedback Modal — Ctrl+J', () => {
    test('Ctrl+J opens the feedback modal', async ({ page }) => {
      await page.goto('/chat/');
      await page.keyboard.press('Control+j');

      // Modal title "Send Feedback" should appear
      await expect(page.getByText('Send Feedback')).toBeVisible({ timeout: 3000 });
    });

    test('feedback modal shows type option pills', async ({ page }) => {
      await page.goto('/chat/');
      await page.keyboard.press('Control+j');

      // Four feedback type pills
      await expect(page.getByRole('button', { name: 'Helpful' })).toBeVisible();
      await expect(page.getByRole('button', { name: 'Inaccurate' })).toBeVisible();
      await expect(page.getByRole('button', { name: 'Incomplete' })).toBeVisible();
      await expect(page.getByRole('button', { name: 'Too verbose' })).toBeVisible();
    });

    test('feedback modal shows comment textarea', async ({ page }) => {
      await page.goto('/chat/');
      await page.keyboard.press('Control+j');

      const textarea = page.locator('textarea[placeholder="Tell us more..."]');
      await expect(textarea).toBeVisible();
    });

    test('Escape closes the feedback modal', async ({ page }) => {
      await page.goto('/chat/');
      await page.keyboard.press('Control+j');
      await expect(page.getByText('Send Feedback')).toBeVisible();

      await page.keyboard.press('Escape');

      await expect(page.getByText('Send Feedback')).not.toBeVisible();
    });

    test('Cancel button closes the feedback modal', async ({ page }) => {
      await page.goto('/chat/');
      await page.keyboard.press('Control+j');
      await expect(page.getByText('Send Feedback')).toBeVisible();

      await page.getByRole('button', { name: 'Cancel' }).click();

      await expect(page.getByText('Send Feedback')).not.toBeVisible();
    });

    test('Ctrl+J toggles the feedback modal closed', async ({ page }) => {
      await page.goto('/chat/');

      // Open
      await page.keyboard.press('Control+j');
      await expect(page.getByText('Send Feedback')).toBeVisible();

      // Close via same shortcut
      await page.keyboard.press('Control+j');
      await expect(page.getByText('Send Feedback')).not.toBeVisible();
    });

    test('feedback type pills toggle selection', async ({ page }) => {
      await page.goto('/chat/');
      await page.keyboard.press('Control+j');

      const helpfulBtn = page.getByRole('button', { name: 'Helpful' });
      await helpfulBtn.click();
      // Selected pill gets blue background
      await expect(helpfulBtn).toHaveClass(/bg-blue-600/);

      // Click again to deselect
      await helpfulBtn.click();
      await expect(helpfulBtn).not.toHaveClass(/bg-blue-600/);
    });
  });
});
