import { test, expect } from '@playwright/test';
import path from 'path';
import fs from 'fs';

const SCREENSHOTS_DIR = path.resolve(__dirname, '../../screenshots');

// Must match server/app/strands_agentic_service.py _GREETING_RESPONSES
const GREETING_RESPONSES = [
  'Hey! What are you working on today?',
  'Hi there! What can I help you with?',
  'Hey! Got an acquisition question or need to start something?',
];

/** SSE event shape emitted by the backend. */
interface SSEEvent {
  type?: string;
  data?: string;
  text?: string;
  agent_id?: string;
  timestamp?: string;
  tool_use?: { name?: string; input?: unknown; tool_use_id?: string };
  tool_result?: { name?: string; result?: unknown };
  usage?: { fast_path?: boolean; trivial?: boolean };
  tools_called?: unknown[];
  [key: string]: unknown;
}

/** Shared helpers */
async function findChatInput(page: any) {
  const candidates = [
    page.getByPlaceholder('Ask about acquisitions'),
    page.getByPlaceholder(/ask/i),
    page.locator('textarea').first(),
    page.locator('input[type="text"]').first(),
    page.locator('[contenteditable="true"]').first(),
  ];
  for (const c of candidates) {
    if (await c.isVisible({ timeout: 2_000 }).catch(() => false)) return c;
  }
  return null;
}

async function captureSSE(page: any): Promise<SSEEvent[]> {
  const events: SSEEvent[] = [];
  page.on('response', async (response: any) => {
    if (!response.url().includes('/api/invoke') && !response.url().includes('/api/chat')) return;
    try {
      const body = await response.text();
      for (const line of body.split('\n')) {
        if (!line.startsWith('data: ')) continue;
        try { events.push(JSON.parse(line.slice(6).trim())); } catch { /* */ }
      }
    } catch { /* */ }
  });
  return events;
}

async function sendMessage(page: any, chatInput: any, message: string) {
  await chatInput.fill(message);
  const sendBtn = page.locator('button[type="submit"], button[aria-label*="send" i], button:has-text("Send")').first();
  if (await sendBtn.isVisible({ timeout: 2_000 }).catch(() => false)) {
    await sendBtn.click();
  } else {
    await chatInput.press('Enter');
  }
}

async function waitForResponse(page: any, opts: { maxWait?: number; pollInterval?: number; keywords?: string[] } = {}): Promise<string> {
  const { maxWait = 60_000, pollInterval = 2_000, keywords = [] } = opts;
  let responseText = '';
  let lastLen = 0;
  let stableCount = 0;
  const start = Date.now();

  while (Date.now() - start < maxWait) {
    await page.waitForTimeout(pollInterval);
    const selectors = [
      '[data-message-role="assistant"]',
      '.copilotkit-assistant-message',
      '[class*="assistant"]',
      '.prose',
      '.markdown',
    ];
    for (const sel of selectors) {
      const els = page.locator(sel);
      if ((await els.count()) > 0) {
        responseText = await els.last().innerText().catch(() => '');
        if (responseText) break;
      }
    }
    if (!responseText) {
      const body = await page.locator('body').innerText().catch(() => '');
      for (const kw of keywords) {
        if (body.toLowerCase().includes(kw.toLowerCase())) { responseText = body; break; }
      }
    }
    if (responseText.length > 0) {
      if (responseText.length === lastLen) { stableCount++; if (stableCount >= 2) break; }
      else stableCount = 0;
      lastLen = responseText.length;
    }
  }
  return responseText;
}

// ────────────────────────────────────────────────────────────────────
// Tests
// ────────────────────────────────────────────────────────────────────

test.describe('Greeting Fast-Path', () => {

  test('trivial "hi" returns instant casual response', async ({ page }) => {
    test.setTimeout(60_000);
    fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });

    const sseEvents = await captureSSE(page);

    await page.goto('http://localhost:3000/chat', { waitUntil: 'domcontentloaded', timeout: 30_000 });
    await page.waitForTimeout(3_000);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'greeting-fast-path-initial.png'), fullPage: true });

    const chatInput = await findChatInput(page);
    expect(chatInput, 'Chat input must be found').not.toBeNull();

    const t0 = Date.now();
    await sendMessage(page, chatInput, 'hi');
    const responseText = await waitForResponse(page, { maxWait: 15_000, pollInterval: 500, keywords: GREETING_RESPONSES.map(r => r.substring(0, 20)) });
    const elapsed = Date.now() - t0;

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'greeting-fast-path-hi-response.png'), fullPage: true });

    // ── Assertions ──
    // Response matches one of the canned greetings
    const matchesGreeting = GREETING_RESPONSES.some(r => responseText.includes(r));
    console.log(`  Response text: "${responseText.substring(0, 200)}"`);
    console.log(`  Matches greeting: ${matchesGreeting}`);
    console.log(`  Elapsed: ${elapsed}ms`);

    // SSE assertions
    const toolUseEvents = sseEvents.filter(e => e.type === 'tool_use');
    const completeEvents = sseEvents.filter(e => e.type === 'complete');
    // Note: stream_generator's write_complete() doesn't forward usage from the
    // SDK chunk, so fast_path flag may not appear in the SSE complete event.
    const fastPathFlag = completeEvents.some(e => e.usage?.fast_path === true);

    console.log(`  SSE events: ${sseEvents.length}`);
    console.log(`  tool_use events: ${toolUseEvents.length}`);
    console.log(`  complete events: ${completeEvents.length}`);
    console.log(`  fast_path flag: ${fastPathFlag}`);

    // ── Report ──
    console.log('\n================================================================');
    console.log('     GREETING FAST-PATH: "hi"');
    console.log('================================================================');
    console.log(`  Response matches greeting:  ${matchesGreeting ? 'PASS' : 'FAIL'}`);
    console.log(`  Timing < 5s:                ${elapsed < 5000 ? 'PASS' : 'WARN'} (${elapsed}ms)`);
    console.log(`  Zero tool_use events:       ${toolUseEvents.length === 0 ? 'PASS' : 'FAIL'} (${toolUseEvents.length})`);
    console.log(`  fast_path flag in complete:  ${fastPathFlag ? 'PASS' : 'INFO (not forwarded by stream_generator)'}`);
    console.log('================================================================');

    expect(matchesGreeting, 'Response must match one of _GREETING_RESPONSES').toBe(true);
    expect(toolUseEvents.length, 'Fast-path should have zero tool_use events').toBe(0);
    // Timing is a soft check — CI can be slow, page interaction adds latency
    if (elapsed >= 5000) {
      console.warn(`WARN: Greeting took ${elapsed}ms (expected < 5000ms) — may be CI latency`);
    }
  });

  test('trivial "hello" returns instant casual response', async ({ page }) => {
    test.setTimeout(60_000);
    fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });

    const sseEvents = await captureSSE(page);

    await page.goto('http://localhost:3000/chat', { waitUntil: 'domcontentloaded', timeout: 30_000 });
    await page.waitForTimeout(3_000);

    const chatInput = await findChatInput(page);
    expect(chatInput, 'Chat input must be found').not.toBeNull();

    const t0 = Date.now();
    await sendMessage(page, chatInput, 'hello');
    const responseText = await waitForResponse(page, { maxWait: 15_000, pollInterval: 500, keywords: GREETING_RESPONSES.map(r => r.substring(0, 20)) });
    const elapsed = Date.now() - t0;

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'greeting-fast-path-hello-response.png'), fullPage: true });

    const matchesGreeting = GREETING_RESPONSES.some(r => responseText.includes(r));
    const toolUseEvents = sseEvents.filter(e => e.type === 'tool_use');

    console.log('\n================================================================');
    console.log('     GREETING FAST-PATH: "hello"');
    console.log('================================================================');
    console.log(`  Response matches greeting:  ${matchesGreeting ? 'PASS' : 'FAIL'}`);
    console.log(`  Timing < 2s:                ${elapsed < 2000 ? 'PASS' : 'WARN'} (${elapsed}ms)`);
    console.log(`  Zero tool_use events:       ${toolUseEvents.length === 0 ? 'PASS' : 'FAIL'} (${toolUseEvents.length})`);
    console.log('================================================================');

    expect(matchesGreeting, 'Response must match one of _GREETING_RESPONSES').toBe(true);
    expect(toolUseEvents.length, 'Fast-path should have zero tool_use events').toBe(0);
  });

  test('non-trivial "hi what is FAR part 6" skips fast-path', async ({ page }) => {
    test.setTimeout(180_000);
    fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });

    const sseEvents = await captureSSE(page);

    await page.goto('http://localhost:3000/chat', { waitUntil: 'domcontentloaded', timeout: 30_000 });
    await page.waitForTimeout(3_000);

    const chatInput = await findChatInput(page);
    expect(chatInput, 'Chat input must be found').not.toBeNull();

    const t0 = Date.now();
    await sendMessage(page, chatInput, 'hi what is FAR part 6');
    const responseText = await waitForResponse(page, { maxWait: 120_000, pollInterval: 5_000, keywords: ['far', 'competition', 'full and open'] });
    const elapsed = Date.now() - t0;

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'greeting-fast-path-non-trivial-response.png'), fullPage: true });

    const matchesGreeting = GREETING_RESPONSES.some(r => responseText.includes(r));
    const completeEvents = sseEvents.filter(e => e.type === 'complete');
    const fastPathFlag = completeEvents.some(e => e.usage?.fast_path === true);

    console.log('\n================================================================');
    console.log('     GREETING FAST-PATH: non-trivial skip');
    console.log('================================================================');
    console.log(`  Does NOT match greeting:    ${!matchesGreeting ? 'PASS' : 'FAIL'}`);
    console.log(`  Substantive response:       ${responseText.length > 100 ? 'PASS' : 'FAIL'} (${responseText.length} chars)`);
    console.log(`  fast_path flag absent:       ${!fastPathFlag ? 'PASS' : 'FAIL'}`);
    console.log(`  Elapsed:                    ${elapsed}ms`);
    console.log('================================================================');

    expect(matchesGreeting, 'Non-trivial prompt must NOT match a canned greeting').toBe(false);
    expect(responseText.length, 'Response should be substantive').toBeGreaterThan(50);
    // fast_path flag is not forwarded through stream_generator, so this is informational
    if (fastPathFlag) {
      console.warn('UNEXPECTED: fast_path flag is true for non-trivial prompt');
    }
  });

});
