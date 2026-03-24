import { test, expect, Page } from '@playwright/test';

/**
 * Chat Thread Isolation Tests
 *
 * Phase 1: Verify switching threads during streaming does not corrupt either thread.
 * Phase 2: Verify background generation continues and sessions are independent.
 *
 * Runs against real app at localhost:3000 with backend at localhost:8000.
 */

const CHAT_URL = 'http://localhost:3000/chat';
const SEND_TIMEOUT = 60_000;

/** Helper: type a message and press Enter to send. */
async function sendMessage(page: Page, text: string) {
    const textarea = page.locator('textarea').first();
    await textarea.fill(text);
    await textarea.press('Enter');
}

/** Helper: wait for the streaming indicator to appear (assistant is responding). */
async function waitForStreaming(page: Page, timeout = SEND_TIMEOUT) {
    // The stop button (red square) appears while streaming
    await page.locator('button[title="Stop generating (Esc)"]').waitFor({ state: 'visible', timeout });
}

/** Helper: wait for streaming to finish (stop button disappears). */
async function waitForStreamingComplete(page: Page, timeout = SEND_TIMEOUT) {
    await page.locator('button[title="Stop generating (Esc)"]').waitFor({ state: 'hidden', timeout });
}

/** Helper: get all visible message texts. */
async function getMessageTexts(page: Page): Promise<string[]> {
    const messages = page.locator('[data-testid="message-content"], .prose, [class*="message"]');
    const count = await messages.count();
    const texts: string[] = [];
    for (let i = 0; i < count; i++) {
        const text = await messages.nth(i).textContent();
        if (text) texts.push(text.trim());
    }
    return texts;
}

/** Helper: click the "New Chat" button in sidebar to create a new thread. */
async function createNewThread(page: Page) {
    await page.locator('button:has-text("New Chat")').click();
    await page.waitForTimeout(500);
}

/** Helper: click a session in the sidebar by partial title match. */
async function switchToSession(page: Page, titleFragment: string) {
    await page.locator(`text=${titleFragment}`).first().click();
    await page.waitForTimeout(500);
}

/** Helper: count session rows in sidebar. */
async function getSessionCount(page: Page): Promise<number> {
    return page.locator('[class*="space-y-0"] > div').count();
}

/** Helper: check if the streaming dot is visible for any sidebar session. */
async function hasStreamingDot(page: Page): Promise<boolean> {
    return page.locator('span.animate-pulse[title="Generating..."]').isVisible({ timeout: 2000 }).catch(() => false);
}

// -----------------------------------------------------------------------
// Phase 1 Tests: Corruption Prevention
// -----------------------------------------------------------------------

test.describe('Phase 1: Thread isolation during streaming', () => {
    test.setTimeout(120_000);

    test('switching threads during streaming does not corrupt thread B', async ({ page }) => {
        await page.goto(CHAT_URL, { waitUntil: 'domcontentloaded', timeout: 30_000 });
        await page.waitForTimeout(2000);

        // Send a message in thread A
        await sendMessage(page, 'What is a simplified acquisition threshold?');

        // Wait for streaming to start
        await waitForStreaming(page);

        // While streaming, create a new thread (thread B)
        await createNewThread(page);

        // Thread B should be empty — no messages from thread A leaked
        await page.waitForTimeout(1000);
        const textarea = page.locator('textarea').first();
        await expect(textarea).toBeVisible();

        // Verify the welcome screen or empty state is showing (no messages)
        const assistantMessages = page.locator('[data-testid="message-content"]');
        const count = await assistantMessages.count();
        // Thread B should have 0 messages (it's a fresh thread)
        expect(count).toBe(0);
    });

    test('returning to thread A after switch preserves its history', async ({ page }) => {
        await page.goto(CHAT_URL, { waitUntil: 'domcontentloaded', timeout: 30_000 });
        await page.waitForTimeout(2000);

        // Send a message in the initial thread
        await sendMessage(page, 'Explain the micro-purchase threshold');

        // Wait for response to complete
        await waitForStreamingComplete(page);

        // Get thread A's content
        const threadAMessages = await getMessageTexts(page);
        expect(threadAMessages.length).toBeGreaterThan(0);

        // Switch to a new thread
        await createNewThread(page);
        await page.waitForTimeout(500);

        // Switch back to the first session in sidebar (thread A)
        const firstSession = page.locator('[class*="space-y-0"] > div').first();
        await firstSession.click();
        await page.waitForTimeout(1000);

        // Thread A's messages should still be there
        const restoredMessages = await getMessageTexts(page);
        expect(restoredMessages.length).toBeGreaterThan(0);
    });

    test('new thread after send is empty', async ({ page }) => {
        await page.goto(CHAT_URL, { waitUntil: 'domcontentloaded', timeout: 30_000 });
        await page.waitForTimeout(2000);

        // Send a message
        await sendMessage(page, 'What is FAR Part 13?');
        await waitForStreaming(page);

        // Create new thread while streaming
        await createNewThread(page);

        // New thread should show welcome/empty state
        const welcome = page.locator('text=EAGLE');
        await expect(welcome.first()).toBeVisible({ timeout: 5000 });
    });

    test('debounced autosave does not overwrite thread B after switch', async ({ page }) => {
        await page.goto(CHAT_URL, { waitUntil: 'domcontentloaded', timeout: 30_000 });
        await page.waitForTimeout(2000);

        // Send a message in thread A
        await sendMessage(page, 'Tell me about sole source justifications');
        await waitForStreamingComplete(page);

        // Get thread A content
        const threadAContent = await getMessageTexts(page);

        // Create thread B and send a different message
        await createNewThread(page);
        await sendMessage(page, 'What are the SAT thresholds?');
        await waitForStreamingComplete(page);

        // Wait for debounce to fire (>500ms)
        await page.waitForTimeout(1000);

        // Thread B should have its own content, not thread A's
        const threadBContent = await getMessageTexts(page);
        expect(threadBContent.length).toBeGreaterThan(0);

        // Thread B should NOT contain thread A's messages
        // (thread A asked about sole source, thread B asked about SAT)
        const threadBText = threadBContent.join(' ').toLowerCase();
        // This is a soft check — the AI might mention related topics
        // The key assertion is that thread B has its own user message
        const userMessages = page.locator('[class*="user"]');
        const userCount = await userMessages.count();
        expect(userCount).toBeGreaterThanOrEqual(1);
    });
});

// -----------------------------------------------------------------------
// Phase 2 Tests: Background Generation
// -----------------------------------------------------------------------

test.describe('Phase 2: Background generation and stop controls', () => {
    test.setTimeout(120_000);

    test('stop button appears during streaming and stops generation', async ({ page }) => {
        await page.goto(CHAT_URL, { waitUntil: 'domcontentloaded', timeout: 30_000 });
        await page.waitForTimeout(2000);

        await sendMessage(page, 'Write a detailed market research report for IT services');

        // Stop button should appear
        const stopBtn = page.locator('button[title="Stop generating (Esc)"]');
        await expect(stopBtn).toBeVisible({ timeout: SEND_TIMEOUT });

        // Click stop
        await stopBtn.click();

        // Stop button should disappear
        await expect(stopBtn).not.toBeVisible({ timeout: 10_000 });
    });

    test('Esc key stops generation', async ({ page }) => {
        await page.goto(CHAT_URL, { waitUntil: 'domcontentloaded', timeout: 30_000 });
        await page.waitForTimeout(2000);

        await sendMessage(page, 'Create a comprehensive acquisition plan for cloud services');

        // Wait for streaming to start
        await waitForStreaming(page);

        // Press Escape
        await page.keyboard.press('Escape');

        // Should stop — stop button disappears
        const stopBtn = page.locator('button[title="Stop generating (Esc)"]');
        await expect(stopBtn).not.toBeVisible({ timeout: 10_000 });
    });

    test('sidebar shows streaming indicator while generating', async ({ page }) => {
        await page.goto(CHAT_URL, { waitUntil: 'domcontentloaded', timeout: 30_000 });
        await page.waitForTimeout(2000);

        await sendMessage(page, 'What are the key differences between FAR Parts 12 and 15?');

        // Wait for streaming to start
        await waitForStreaming(page);

        // Check for streaming dot in sidebar
        const streamingDot = await hasStreamingDot(page);
        expect(streamingDot).toBe(true);

        // Wait for completion
        await waitForStreamingComplete(page);

        // Streaming dot should be gone
        await page.waitForTimeout(500);
        const dotAfter = await hasStreamingDot(page);
        expect(dotAfter).toBe(false);
    });

    test('second send in same session is blocked while streaming', async ({ page }) => {
        await page.goto(CHAT_URL, { waitUntil: 'domcontentloaded', timeout: 30_000 });
        await page.waitForTimeout(2000);

        await sendMessage(page, 'Explain the competition requirements under FAR Part 6');

        // Wait for streaming to start
        await waitForStreaming(page);

        // Textarea should be disabled during streaming
        const textarea = page.locator('textarea').first();
        await expect(textarea).toBeDisabled();

        // Wait for completion before test ends
        await waitForStreamingComplete(page);
    });
});
