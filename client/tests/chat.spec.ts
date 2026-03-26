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

    // Phase 1: streaming started — stop button appears (reliable indicator).
    // The initial "Connecting..." phase uses a blue dot, not .typing-dot,
    // so we use the stop button as the ground-truth streaming signal.
    const stopButton = page.getByTitle('Stop generating (Esc)');
    await expect(stopButton).toBeVisible({ timeout: 15000 });

    // Phase 2: streaming finished — stop button disappears (isStreaming → false).
    await expect(stopButton).not.toBeVisible({ timeout: 90000 });

    // Phase 3: textarea re-enabled — confirms isStreaming fully cleared in React state
    await expect(textarea).toBeEnabled();

    // Phase 4: agent message label visible — '🦅 EAGLE' now belongs to a real message,
    // not the typing indicator (which is gone)
    await expect(page.locator('text=🦅 EAGLE')).toBeVisible();

    // Phase 5: main content has substantive text from the agent response
    const mainText = await page.locator('main').textContent() ?? '';
    expect(mainText.length).toBeGreaterThan(100);
  });

  // Requires running backend — sends a message, waits for streaming to start,
  // clicks the stop button, and verifies the UI recovers cleanly.
  test('stop generating button cancels streaming', async ({ page }) => {
    test.slow();
    await page.goto('/chat/');
    await page.getByRole('button', { name: 'New Chat' }).click();

    const textarea = page.locator('textarea');
    await expect(textarea).toBeEnabled();

    // Send a long-running prompt to ensure streaming lasts long enough to click stop
    await textarea.fill('Write a detailed 2000-word acquisition plan for a $5M IT services contract');
    await page.getByRole('button', { name: '➤' }).click();

    // Wait for streaming to start — stop button appears (textarea disables, send button hides).
    // Note: the initial "Connecting..." phase shows a blue dot, not .typing-dot.
    // The stop button is the reliable streaming indicator.
    const stopButton = page.getByTitle('Stop generating (Esc)');
    await expect(stopButton).toBeVisible({ timeout: 15000 });
    await expect(textarea).toBeDisabled();

    // The send button (➤) should NOT be visible while streaming
    await expect(page.getByRole('button', { name: '➤' })).not.toBeVisible();

    // Click stop
    await stopButton.click();

    // After abort, status transitions: streaming → stopping → idle.
    // The stop button stays visible during 'stopping' until the fetch completes.
    await expect(stopButton).not.toBeVisible({ timeout: 15000 });
    await expect(page.getByRole('button', { name: '➤' })).toBeVisible();

    // Textarea should be re-enabled for new input
    await expect(textarea).toBeEnabled();

    // User should be able to type again after stopping
    await textarea.fill('Follow-up question');
    await expect(page.getByRole('button', { name: '➤' })).toBeEnabled();
  });

  // Keyboard shortcut: Escape should also stop generation
  test('escape key stops generation', async ({ page }) => {
    test.slow();
    await page.goto('/chat/');
    await page.getByRole('button', { name: 'New Chat' }).click();

    const textarea = page.locator('textarea');
    await expect(textarea).toBeEnabled();

    await textarea.fill('Explain every FAR part in detail');
    await page.getByRole('button', { name: '➤' }).click();

    // Wait for streaming to start — stop button visible
    const stopButton = page.getByTitle('Stop generating (Esc)');
    await expect(stopButton).toBeVisible({ timeout: 15000 });

    // Press Escape to stop
    await page.keyboard.press('Escape');

    // Wait for full abort cleanup (stopping → idle)
    await expect(stopButton).not.toBeVisible({ timeout: 15000 });
    await expect(textarea).toBeEnabled();
  });
});
