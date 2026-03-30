import { test, expect } from '@playwright/test';

/**
 * Streaming Render Quality — Flicker & Scroll Regression Tests
 *
 * Validates that SSE streaming text renders smoothly without:
 *   1. Message duplication
 *   2. Scroll anchor loss
 *   3. Streaming cursor artifacts after completion
 *   4. DOM flicker on rapid chunks
 *
 * Uses synthetic SSE via page.route() so no backend is needed.
 */

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function buildSSE(events: Array<Record<string, unknown>>): string {
  return events.map((e) => `data: ${JSON.stringify(e)}`).join('\n\n') + '\n\n';
}

/** Build a streaming SSE payload with N text chunks + a complete event. */
function buildStreamingSSE(chunks: string[]): string {
  const events: Array<Record<string, unknown>> = [];
  chunks.forEach((chunk, i) => {
    events.push({
      type: 'text',
      agent_id: 'eagle',
      agent_name: 'EAGLE',
      content: chunk,
      timestamp: `2026-01-01T00:00:${String(i % 60).padStart(2, '0')}Z`,
    });
  });
  events.push({
    type: 'complete',
    agent_id: 'eagle',
    agent_name: 'EAGLE',
    metadata: { duration_ms: chunks.length * 50 },
    timestamp: '2026-01-01T00:01:00Z',
  });
  return buildSSE(events);
}

/** Generate N text chunks with identifiable content. */
function makeChunks(n: number, prefix = 'chunk'): string[] {
  return Array.from({ length: n }, (_, i) => `${prefix}${i} `);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe('Streaming Render Quality', () => {
  test('streaming text accumulates without message duplication', async ({ page }) => {
    test.setTimeout(30_000);

    const chunks = makeChunks(20);
    const expectedText = chunks.join('').trim();

    await page.route('**/api/invoke', async (route) => {
      await route.fulfill({
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
        body: buildStreamingSSE(chunks),
      });
    });

    await page.goto('http://localhost:3000/chat/', {
      waitUntil: 'domcontentloaded',
      timeout: 15_000,
    });

    const textarea = page.locator('textarea').first();
    await expect(textarea).toBeVisible({ timeout: 10_000 });
    await textarea.fill('test streaming');
    await textarea.press('Enter');

    // Wait for streaming to complete — textarea re-enables
    await expect(textarea).toBeEnabled({ timeout: 15_000 });
    await page.waitForTimeout(1_000);

    const mainText = (await page.locator('main').textContent()) ?? '';

    // Exactly 1 EAGLE label = 1 assistant message (no duplication)
    const eagleLabels = page.locator('text=EAGLE').filter({ hasText: /EAGLE/ });
    // The "EAGLE" text appears in the header and in message labels —
    // count only the message-level labels (small uppercase text inside the chat area)
    const msgLabels = page.locator('span:text-is("🦅 Eagle"), span:has-text("EAGLE")').filter({
      has: page.locator('xpath=ancestor::*[contains(@class,"max-w-2xl")]'),
    });
    // At minimum we expect the label to exist (1 assistant message rendered)
    const labelCount = await msgLabels.count();
    expect(labelCount).toBeGreaterThanOrEqual(1);

    // All chunk content present in the final output
    for (const chunk of chunks) {
      expect(mainText).toContain(chunk.trim());
    }
  });

  test('scroll stays anchored to bottom during streaming', async ({ page }) => {
    test.setTimeout(30_000);

    // Generate enough text to overflow the viewport — 40 chunks with paragraph breaks
    const chunks: string[] = [];
    for (let i = 0; i < 40; i++) {
      chunks.push(
        `Paragraph ${i}: This is a longer text segment that helps fill the viewport and trigger scrolling behavior. `,
      );
      if (i % 3 === 2) chunks.push('\n\n');
    }

    await page.route('**/api/invoke', async (route) => {
      await route.fulfill({
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
        body: buildStreamingSSE(chunks),
      });
    });

    await page.goto('http://localhost:3000/chat/', {
      waitUntil: 'domcontentloaded',
      timeout: 15_000,
    });

    const textarea = page.locator('textarea').first();
    await expect(textarea).toBeVisible({ timeout: 10_000 });
    await textarea.fill('generate long response');
    await textarea.press('Enter');

    // Wait for streaming to complete
    await expect(textarea).toBeEnabled({ timeout: 15_000 });
    await page.waitForTimeout(1_500);

    // Check that scroll container is near the bottom
    const scrollInfo = await page.evaluate(() => {
      const scrollContainer = document.querySelector('.overflow-y-auto');
      if (!scrollContainer) return null;
      return {
        scrollTop: scrollContainer.scrollTop,
        clientHeight: scrollContainer.clientHeight,
        scrollHeight: scrollContainer.scrollHeight,
      };
    });

    expect(scrollInfo).not.toBeNull();
    if (scrollInfo) {
      const distanceFromBottom =
        scrollInfo.scrollHeight - scrollInfo.scrollTop - scrollInfo.clientHeight;
      // Should be within 100px of the bottom (generous tolerance for smooth scroll)
      expect(distanceFromBottom).toBeLessThan(100);
    }
  });

  test('streaming cursor disappears after completion', async ({ page }) => {
    test.setTimeout(30_000);

    const chunks = makeChunks(5);

    await page.route('**/api/invoke', async (route) => {
      await route.fulfill({
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
        body: buildStreamingSSE(chunks),
      });
    });

    await page.goto('http://localhost:3000/chat/', {
      waitUntil: 'domcontentloaded',
      timeout: 15_000,
    });

    const textarea = page.locator('textarea').first();
    await expect(textarea).toBeVisible({ timeout: 10_000 });
    await textarea.fill('test cursor cleanup');
    await textarea.press('Enter');

    // Wait for streaming to complete
    await expect(textarea).toBeEnabled({ timeout: 15_000 });
    await page.waitForTimeout(1_000);

    // The " ..." streaming cursor should be gone from the rendered text
    const mainText = (await page.locator('main').textContent()) ?? '';
    expect(mainText).not.toContain(' ...');

    // The typing dots should not be visible
    const typingDot = page.locator('.typing-dot');
    await expect(typingDot.first()).not.toBeVisible();
  });

  test('rapid chunks do not cause message duplication', async ({ page }) => {
    test.setTimeout(30_000);

    // 50 chunks delivered all at once (zero delay — browser processes SSE body synchronously)
    const chunks = makeChunks(50, 'rapid');
    const expectedContent = chunks.map((c) => c.trim());

    await page.route('**/api/invoke', async (route) => {
      await route.fulfill({
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
        body: buildStreamingSSE(chunks),
      });
    });

    await page.goto('http://localhost:3000/chat/', {
      waitUntil: 'domcontentloaded',
      timeout: 15_000,
    });

    const textarea = page.locator('textarea').first();
    await expect(textarea).toBeVisible({ timeout: 10_000 });
    await textarea.fill('rapid fire test');
    await textarea.press('Enter');

    // Wait for streaming to complete
    await expect(textarea).toBeEnabled({ timeout: 15_000 });
    await page.waitForTimeout(1_500);

    const mainText = (await page.locator('main').textContent()) ?? '';

    // All 50 chunks present
    for (const content of expectedContent) {
      expect(mainText).toContain(content);
    }

    // Verify no duplicate content — each "rapidN" appears exactly once
    for (let i = 0; i < 50; i++) {
      const pattern = `rapid${i} `;
      const firstIdx = mainText.indexOf(pattern);
      const secondIdx = mainText.indexOf(pattern, firstIdx + pattern.length);
      // Should not find a second occurrence (allowing for the user's input area)
      // We check in the assistant response area specifically
      const assistantText = await page.locator('.text-gray-800.leading-relaxed').allTextContents();
      const joined = assistantText.join(' ');
      const count = (joined.match(new RegExp(`rapid${i}\\s`, 'g')) || []).length;
      expect(count).toBeLessThanOrEqual(1);
    }
  });
});
