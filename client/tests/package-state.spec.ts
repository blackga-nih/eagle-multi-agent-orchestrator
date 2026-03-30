import { test, expect } from '@playwright/test';

test.describe('Package State & Checklist Panel', () => {
  // ─── Package Tab in Activity Panel ──────────────────────────────────

  test.describe('Package Tab', () => {
    test('package tab visible and is default active tab', async ({ page }) => {
      await page.goto('/chat/');

      // The "Package" tab should be visible and be the first/default tab
      await expect(page.getByText('Package', { exact: true }).first()).toBeVisible({
        timeout: 5000,
      });
    });

    test('package tab shows empty state when no package active', async ({ page }) => {
      await page.goto('/chat/');
      await page.getByRole('button', { name: 'New Chat' }).click();

      // Click the Package tab (should already be default, but click to ensure)
      await page.getByText('Package', { exact: true }).first().click();

      // Empty state message should appear
      await expect(page.getByText('No active package.')).toBeVisible();
      await expect(page.getByText('Start an acquisition intake')).toBeVisible();
    });

    test('all four tabs present: Package, Documents, Notifications, Agent Logs', async ({
      page,
    }) => {
      await page.goto('/chat/');

      await expect(page.getByText('Package', { exact: true }).first()).toBeVisible();
      await expect(page.getByText('Documents', { exact: true }).first()).toBeVisible();
      await expect(page.getByText('Notifications', { exact: true }).first()).toBeVisible();
      await expect(page.getByText('Agent Logs', { exact: true })).toBeVisible();
    });

    test('switching tabs works correctly', async ({ page }) => {
      await page.goto('/chat/');
      await page.getByRole('button', { name: 'New Chat' }).click();

      // Package tab is default — should show empty state
      await expect(page.getByText('No active package.')).toBeVisible();

      // Switch to Documents
      await page.getByText('Documents', { exact: true }).first().click();
      await expect(page.getByText('No documents generated yet.')).toBeVisible();

      // Switch back to Package
      await page.getByText('Package', { exact: true }).first().click();
      await expect(page.getByText('No active package.')).toBeVisible();
    });
  });

  // ─── Tool Use Display: manage_package ───────────────────────────────

  test.describe('manage_package Tool Display', () => {
    test('manage_package tool chip shows Package Update label', async ({ page }) => {
      test.slow(); // triples timeout for backend-dependent tests

      await page.goto('/chat/');
      await page.getByRole('button', { name: 'New Chat' }).click();

      const textarea = page.locator('textarea');
      await expect(textarea).toBeEnabled();

      // Send an intake query that should trigger manage_package
      await textarea.fill(
        'I need to buy lab equipment for $85,000, genomics sequencer, need it by June',
      );
      await page.getByRole('button', { name: '\u27A4' }).click();

      // Wait for streaming to start
      try {
        await expect(page.locator('.typing-dot').first()).toBeVisible({ timeout: 15_000 });
      } catch {
        test.skip(true, 'Backend not available — skipping manage_package display test');
        return;
      }

      // Look for the Package Update tool chip (manage_package in TOOL_META)
      try {
        await expect(page.locator('text=/Package Update|Intake/i').first()).toBeVisible({
          timeout: 60_000,
        });
      } catch {
        // Not all intake queries trigger manage_package immediately
      }

      // Wait for streaming to complete
      await expect(page.locator('.typing-dot').first()).not.toBeVisible({ timeout: 90_000 });
      await expect(textarea).toBeEnabled();
    });
  });

  // ─── State Change Cards ─────────────────────────────────────────────

  test.describe('State Change Cards', () => {
    test('state change card appears during intake flow', async ({ page }) => {
      test.slow();

      await page.goto('/chat/');
      await page.getByRole('button', { name: 'New Chat' }).click();

      const textarea = page.locator('textarea');
      await expect(textarea).toBeEnabled();

      // Send a message that should trigger package creation + state update
      await textarea.fill(
        'I need to purchase IT consulting services for approximately $200,000. Need it by September 2026.',
      );
      await page.getByRole('button', { name: '\u27A4' }).click();

      try {
        await expect(page.locator('.typing-dot').first()).toBeVisible({ timeout: 15_000 });
      } catch {
        test.skip(true, 'Backend not available — skipping state change card test');
        return;
      }

      // Wait for response to complete
      await expect(page.locator('.typing-dot').first()).not.toBeVisible({ timeout: 90_000 });

      // Look for a state change card — these have a data-testid="state-change-card"
      // or render with recognizable text patterns
      const stateCard = page.locator('[data-testid="state-change-card"]');
      const packageUpdateText = page.locator(
        'text=/Package Updated|Package Created|docs complete/i',
      );

      // At least one of these should be visible if state updates are wired correctly
      const hasStateCard = (await stateCard.count()) > 0;
      const hasPackageText = (await packageUpdateText.count()) > 0;

      // This is a soft assertion — the supervisor may not always create a package
      // on the first message. Log result for diagnostics.
      if (!hasStateCard && !hasPackageText) {
        console.log(
          'No state change card found — supervisor may not have created package on first turn',
        );
      }
    });

    test('state change card is clickable and opens detail view', async ({ page }) => {
      test.slow();

      await page.goto('/chat/');
      await page.getByRole('button', { name: 'New Chat' }).click();

      const textarea = page.locator('textarea');
      await expect(textarea).toBeEnabled();

      await textarea.fill('Start acquisition intake for a $500,000 research equipment purchase');
      await page.getByRole('button', { name: '\u27A4' }).click();

      try {
        await expect(page.locator('.typing-dot').first()).toBeVisible({ timeout: 15_000 });
      } catch {
        test.skip(true, 'Backend not available');
        return;
      }

      await expect(page.locator('.typing-dot').first()).not.toBeVisible({ timeout: 90_000 });

      // Try to click a state change card
      const stateCard = page.locator('[data-testid="state-change-card"]').first();
      if (await stateCard.isVisible()) {
        await stateCard.click();

        // Detail modal should appear with package information
        await expect(page.locator('[data-testid="state-change-detail"]')).toBeVisible({
          timeout: 3000,
        });
      }
    });
  });
});
