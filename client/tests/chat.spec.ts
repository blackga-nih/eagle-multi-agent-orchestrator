import { test, expect } from '@playwright/test';

test.describe('Chat Page', () => {
  test('chat page loads with correct structure', async ({ page }) => {
    await page.goto('/chat/');
    await expect(page.getByPlaceholder(/Ask EAGLE/i)).toBeVisible();
    await expect(page.getByRole('button', { name: 'New Chat' })).toBeVisible();
    await expect(page.getByRole('button', { name: /New Intake/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /Generate SOW/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /Search FAR/i })).toBeVisible();
  });

  test('new chat shows welcome screen', async ({ page }) => {
    await page.goto('/chat/');
    await page.getByRole('button', { name: 'New Chat' }).click();
    await expect(page.getByRole('heading', { name: /Welcome to EAGLE/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /Acquisition Intake/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /Document Generation/i })).toBeVisible();
  });

  test('submit button enables when text is typed', async ({ page }) => {
    await page.goto('/chat/');
    await page.getByRole('button', { name: 'New Chat' }).click();
    const input = page.getByPlaceholder(/Ask EAGLE/i);
    await expect(input).toBeVisible();
    await input.fill('test');
    await expect(page.getByRole('button', { name: '➤' })).toBeEnabled();
  });

  // Requires running backend + agent — included in `just e2e full`
  // test.slow() triples the 30s default to 90s for agent streaming
  test('agent responds to a message', async ({ page }) => {
    test.slow();
    await page.goto('/chat/');
    await page.getByRole('button', { name: 'New Chat' }).click();

    const textarea = page.locator('textarea');
    await expect(textarea).toBeEnabled();

    // Send a message to the agent
    await textarea.fill('Hello');
    await page.getByRole('button', { name: '➤' }).click();

    // Phase 1: streaming started — typing indicator (bouncing dots) appears.
    // The '🦅 EAGLE' label renders on BOTH the typing indicator AND completed messages,
    // so we track .typing-dot as the ground-truth streaming signal instead.
    await expect(page.locator('.typing-dot').first()).toBeVisible({ timeout: 10000 });

    // Phase 2: streaming finished — typing indicator disappears (isStreaming → false).
    // SimpleChatInterface passes isStreaming as isTyping to SimpleMessageList,
    // which only renders .typing-dot while isTyping===true.
    await expect(page.locator('.typing-dot').first()).not.toBeVisible({ timeout: 90000 });

    // Phase 3: textarea re-enabled — confirms isStreaming fully cleared in React state
    await expect(textarea).toBeEnabled();

    // Phase 4: agent message label visible — '🦅 EAGLE' now belongs to a real message,
    // not the typing indicator (which is gone)
    await expect(page.locator('text=🦅 EAGLE')).toBeVisible();

    // Phase 5: main content has substantive text from the agent response
    const mainText = await page.locator('main').textContent() ?? '';
    expect(mainText.length).toBeGreaterThan(100);
  });
});
