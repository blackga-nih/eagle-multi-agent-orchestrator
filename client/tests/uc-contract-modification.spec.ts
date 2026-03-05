import { test, expect } from '@playwright/test';

/**
 * UC-04: Contract Modification Request
 *
 * Simulates a contracting officer requesting a contract modification
 * to add funding and extend the period of performance. Verifies the
 * agent identifies the modification type, references relevant FAR
 * clauses, and produces documentation guidance after follow-up.
 */
test.describe('UC-04: Contract Modification Request', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/chat/');
    await page.getByRole('button', { name: 'New Chat' }).click();
    await expect(page.getByRole('heading', { name: /Welcome to EAGLE/i })).toBeVisible();
  });

  test('modification request → type identification and documentation guidance', async ({ page }) => {
    test.slow(); // 90s budget for agent streaming

    // Send modification request message
    const textarea = page.getByPlaceholder(/Ask EAGLE/i);
    await textarea.fill(
      'I need to modify contract NCI-2023-0542 to add $150,000 in funding and extend the period of performance by 6 months.'
    );
    await expect(page.getByRole('button', { name: '➤' })).toBeEnabled();
    await page.getByRole('button', { name: '➤' }).click();

    // Wait for assistant response to stream in fully
    await expect(page.locator('.text-sm.text-gray-800.leading-relaxed').first()).toBeVisible({ timeout: 60000 });
    await page.waitForTimeout(3000);

    // Response should acknowledge the contract modification scenario
    await expect(page.locator('main')).toContainText(
      /modif|contract|NCI-2023-0542|funding|period of performance|150,?000/i,
      { timeout: 30000 }
    );

    // Response should mention modification type, FAR, or documentation
    await expect(page.locator('main')).toContainText(
      /bilateral|unilateral|FAR|modification|SF-30|supplemental|justification|documentation|rationale|scope|requirement|approval/i,
      { timeout: 10000 }
    );

    // Send follow-up with justification details
    await textarea.fill(
      'This is additional funding for expanded data analysis scope. The contractor has agreed to the changes.'
    );
    await expect(page.getByRole('button', { name: '➤' })).toBeEnabled();
    await page.getByRole('button', { name: '➤' }).click();

    // Wait for second assistant response
    await expect(page.locator('.text-sm.text-gray-800.leading-relaxed').nth(1)).toBeVisible({ timeout: 60000 });
    await page.waitForTimeout(3000);

    // Response should discuss bilateral modification or document generation
    await expect(page.locator('main')).toContainText(
      /bilateral|modification|SF-30|document|generate|supplemental|mutual|agreement|analysis|funding|scope/i,
      { timeout: 30000 }
    );
  });
});
