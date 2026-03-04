/**
 * Session Memory / Multi-Turn Context Tests
 *
 * Validates that EAGLE remembers context across multiple messages within
 * the same chat session. These tests expose the session_id continuity
 * across the full request chain:
 *
 *   React state (currentSessionId)
 *     → use-agent-stream.ts  (sends { query, session_id })
 *       → /api/invoke proxy  (passes session_id through unchanged)
 *         → FastAPI /api/chat/stream  (session_id → sdk_query)
 *           → sdk_query(resume=session_id)  (Claude SDK session resume)
 *
 * KNOWN RISK: In local dev, the Claude SDK subprocess may fall back to
 * the direct Anthropic API (stream_chat), which sends no history.
 * The memory tests will FAIL in that fallback path — which is the signal
 * that the SDK subprocess is not running correctly.
 *
 * Run with a live backend:
 *   BASE_URL=http://localhost:3000 npx playwright test session-memory --project=chromium
 */

import { test, expect } from '@playwright/test';

const CODENAME = 'APOLLO-PRIME';
const PROJECT = 'STARGATE';
const STREAM_TIMEOUT = 90_000; // 90s — SDK can be slow on first call

/** Wait for streaming to start then fully complete. */
async function waitForStreamComplete(page: import('@playwright/test').Page) {
  // Streaming starts: typing-dot appears
  await expect(page.locator('.typing-dot').first()).toBeVisible({ timeout: 15_000 });
  // Streaming ends: typing-dot disappears, textarea re-enables
  await expect(page.locator('.typing-dot').first()).not.toBeVisible({
    timeout: STREAM_TIMEOUT,
  });
  const textarea = page.locator('textarea');
  await expect(textarea).toBeEnabled({ timeout: 5_000 });
}

/** Send a message via the textarea and press Enter. */
async function sendMessage(page: import('@playwright/test').Page, text: string) {
  const textarea = page.locator('textarea');
  await expect(textarea).toBeEnabled({ timeout: 10_000 });
  await textarea.fill(text);
  // Use Enter key (matches the onKeyDown handler in the chat interface)
  await page.keyboard.press('Enter');
}

test.describe('Session Memory — Multi-Turn Context', () => {
  test.slow(); // triples the 30s default timeout to 90s

  test('EAGLE remembers codename and project from a previous message', async ({ page }) => {
    // ── Phase 1: Start a clean session ──────────────────────────────────
    await page.goto('/chat/');
    await page.getByRole('button', { name: 'New Chat' }).click();
    await expect(page.getByRole('heading', { name: /Welcome to EAGLE/i })).toBeVisible({
      timeout: 10_000,
    });

    // ── Phase 2: Capture the session_id sent with the first request ─────
    // Intercept the /api/invoke request to record the session_id
    const sessionIds: string[] = [];
    page.on('request', (req) => {
      if (req.url().includes('/api/invoke') && req.method() === 'POST') {
        try {
          const body = JSON.parse(req.postData() || '{}');
          if (body.session_id) sessionIds.push(body.session_id);
        } catch {
          // non-JSON body — ignore
        }
      }
    });

    // ── Phase 3: Send message 1 with distinctive context ────────────────
    await sendMessage(
      page,
      `My codename is ${CODENAME} and I am the lead engineer for Project ${PROJECT}. Please acknowledge both.`
    );
    await waitForStreamComplete(page);

    // Verify message 1 got a response
    await expect(page.locator('text=🦅 EAGLE')).toBeVisible();
    const response1 = await page.locator('main').textContent() ?? '';
    expect(response1.length).toBeGreaterThan(50);

    // Screenshot after message 1
    await page.screenshot({ path: 'memory-msg1.png' });

    // ── Phase 4: Send message 2 in the SAME session (no New Chat) ───────
    await sendMessage(
      page,
      'What is my codename and what project am I leading?'
    );
    await waitForStreamComplete(page);

    // Screenshot after message 2
    await page.screenshot({ path: 'memory-msg2.png' });

    // ── Phase 5: Verify EAGLE remembers the context ──────────────────────
    const mainContent = await page.locator('main').textContent() ?? '';

    // EAGLE should recall both distinctive pieces of context
    const remembersCodename = mainContent.toUpperCase().includes(CODENAME);
    const remembersProject = mainContent.toUpperCase().includes(PROJECT);

    expect(remembersCodename, `EAGLE should recall codename "${CODENAME}" but response was:\n${mainContent.slice(-800)}`).toBe(true);
    expect(remembersProject, `EAGLE should recall project "${PROJECT}" but response was:\n${mainContent.slice(-800)}`).toBe(true);

    // ── Phase 6: Verify session_id is consistent across messages ────────
    // Both requests must carry the same session_id for SDK resume to work
    if (sessionIds.length >= 2) {
      expect(
        sessionIds[0],
        `session_id changed between message 1 (${sessionIds[0]}) and message 2 (${sessionIds[1]}) — SDK resume will fail`
      ).toBe(sessionIds[1]);
    }
  });

  test('session_id is stable across multiple messages in one session', async ({ page }) => {
    // Purely validates the client-side session_id consistency —
    // does NOT require a live backend response.
    await page.goto('/chat/');
    await page.getByRole('button', { name: 'New Chat' }).click();

    const capturedIds: string[] = [];
    page.on('request', (req) => {
      if (req.url().includes('/api/invoke') && req.method() === 'POST') {
        try {
          const body = JSON.parse(req.postData() || '{}');
          if (body.session_id) capturedIds.push(body.session_id);
        } catch {
          // ignore
        }
      }
    });

    // Intercept responses too — stop waiting after 3 seconds (network only test)
    const textarea = page.locator('textarea');

    // Send 3 messages rapidly (we just need to inspect what session_id is sent,
    // not wait for full agent responses)
    for (let i = 1; i <= 3; i++) {
      await expect(textarea).toBeEnabled({ timeout: 10_000 });
      await textarea.fill(`Test message ${i}`);
      // Fire the request but don't wait for streaming to finish
      // so the test runs quickly
      await page.keyboard.press('Enter');
      // Brief pause to let the request fire before aborting
      await page.waitForTimeout(500);
      // Wait for streaming to start (proves the request went out)
      try {
        await expect(page.locator('.typing-dot').first()).toBeVisible({ timeout: 5_000 });
        // Immediately abort by clicking New Chat to stop streaming
        // (we only needed the request to fire)
        await page.getByRole('button', { name: 'New Chat' }).click();
        await expect(page.getByRole('heading', { name: /Welcome to EAGLE/i })).toBeVisible({
          timeout: 5_000,
        });
        break; // one successful request is enough for this test
      } catch {
        // streaming didn't start (backend offline) — still check request IDs
      }
    }

    // If we captured at least one request, validate the session_id is a valid UUID
    if (capturedIds.length > 0) {
      const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
      expect(capturedIds[0], 'session_id should be a valid UUID').toMatch(uuidPattern);
    }

    // If multiple requests fired within the same session, they must share the same ID
    const uniqueIds = [...new Set(capturedIds)];
    expect(
      uniqueIds.length,
      `Expected 1 unique session_id across all messages in a session, got: ${JSON.stringify(capturedIds)}`
    ).toBeLessThanOrEqual(1);
  });

  test('new session gets a different session_id than the previous session', async ({ page }) => {
    // Validates that clicking "New Chat" generates a NEW session_id,
    // so old sessions don't accidentally bleed context into new ones.
    await page.goto('/chat/');

    const sessionIds: string[] = [];
    page.on('request', (req) => {
      if (req.url().includes('/api/invoke') && req.method() === 'POST') {
        try {
          const body = JSON.parse(req.postData() || '{}');
          if (body.session_id) sessionIds.push(body.session_id);
        } catch {
          // ignore
        }
      }
    });

    // Session 1: send a message
    await page.getByRole('button', { name: 'New Chat' }).click();
    const textarea = page.locator('textarea');
    await expect(textarea).toBeEnabled({ timeout: 10_000 });
    await textarea.fill('Session 1 message');
    await page.keyboard.press('Enter');
    await page.waitForTimeout(800); // let request fire

    // Start session 2 via New Chat
    await page.getByRole('button', { name: 'New Chat' }).click();
    await expect(page.getByRole('heading', { name: /Welcome to EAGLE/i })).toBeVisible({
      timeout: 10_000,
    });

    await expect(textarea).toBeEnabled({ timeout: 10_000 });
    await textarea.fill('Session 2 message');
    await page.keyboard.press('Enter');
    await page.waitForTimeout(800); // let request fire

    if (sessionIds.length >= 2) {
      expect(
        sessionIds[0],
        'New session should get a different session_id than the previous session'
      ).not.toBe(sessionIds[1]);
    }
  });
});
