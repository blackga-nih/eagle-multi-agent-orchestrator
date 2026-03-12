import { test, expect } from '@playwright/test';
import path from 'path';
import fs from 'fs';

const OUT_DIR = 'C:/Users/blackga/Desktop/eagle/sm_eagle/server/screenshots-tool-cards';

test('Tool card chevron validation: all tool cards should have chevron (tool_result)', async ({ page }) => {
  test.setTimeout(180_000); // 3 min

  // Ensure output dir exists
  fs.mkdirSync(OUT_DIR, { recursive: true });

  // ── Capture SSE events from /api/invoke ───────────────────────────
  const sseLines: string[] = [];
  const toolUseEvents: string[] = [];
  const toolResultEvents: string[] = [];

  // Intercept the /api/invoke response to capture raw SSE data
  page.on('response', async (response) => {
    const url = response.url();
    if (!url.includes('/api/invoke')) return;

    const ct = response.headers()['content-type'] || '';
    if (!ct.includes('text/event-stream') && !ct.includes('application/json')) return;

    try {
      const body = await response.text();
      sseLines.push(`--- /api/invoke response (${response.status()}) ---`);
      sseLines.push(body);

      // Parse SSE lines for tool_use and tool_result
      for (const line of body.split('\n')) {
        if (!line.startsWith('data: ')) continue;
        const data = line.slice(6).trim();
        if (!data) continue;
        try {
          const evt = JSON.parse(data);
          if (evt.type === 'tool_use') {
            toolUseEvents.push(data);
          }
          if (evt.type === 'tool_result') {
            toolResultEvents.push(data);
          }
        } catch { /* not JSON */ }
      }
    } catch { /* response body unavailable */ }
  });

  // Also capture raw request/response for debugging
  const allRequests: string[] = [];
  page.on('request', (req) => {
    if (req.url().includes('/api/invoke')) {
      allRequests.push(`${req.method()} ${req.url()}`);
      try {
        allRequests.push(`  Body: ${req.postData()?.slice(0, 500)}`);
      } catch { /* */ }
    }
  });

  const consoleErrors: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });

  // ── STEP 1: Navigate to /chat fresh ───────────────────────────────
  console.log('=== STEP 1: Navigating to http://localhost:3000/chat ===');
  await page.goto('http://localhost:3000/chat', { waitUntil: 'domcontentloaded', timeout: 30_000 });
  await page.waitForTimeout(3_000);

  // Take initial screenshot
  await page.screenshot({ path: path.join(OUT_DIR, 'step1-initial.png'), fullPage: true });

  // ── STEP 2: Already on fresh /chat — no need to click New Chat ────
  console.log('=== STEP 2: Already on fresh /chat page ===');

  // ── STEP 3: Send the test message ─────────────────────────────────
  console.log('=== STEP 3: Sending message ===');
  const query = 'What are the NCI thresholds for simplified acquisitions under $250K?';

  // Find input
  const inputCandidates = [
    page.locator('textarea').first(),
    page.getByPlaceholder(/ask/i),
    page.locator('input[type="text"]').first(),
  ];

  let chatInput: any = null;
  for (const c of inputCandidates) {
    if (await c.isVisible({ timeout: 3_000 }).catch(() => false)) {
      chatInput = c;
      break;
    }
  }

  if (!chatInput) {
    console.log('ERROR: No chat input found');
    await page.screenshot({ path: path.join(OUT_DIR, 'ERROR-no-input.png'), fullPage: true });
    return;
  }

  await chatInput.fill(query);
  await page.screenshot({ path: path.join(OUT_DIR, 'step3-message-typed.png'), fullPage: true });
  await chatInput.press('Enter');
  console.log(`Message sent: "${query}"`);

  // ── STEP 4: Wait for full response (up to 2 minutes) ─────────────
  console.log('=== STEP 4: Waiting for response (up to 120s) ===');

  // Poll for completion — check for green status dots or streaming to stop
  let responseComplete = false;
  const startTime = Date.now();
  const maxWait = 120_000;

  while (Date.now() - startTime < maxWait) {
    await page.waitForTimeout(5_000);

    // Check if streaming has ended (no more typing indicator / pulsing dots)
    const typingIndicator = page.locator('.animate-pulse, .typing-dot');
    const stillTyping = await typingIndicator.count() > 0;

    // Check for assistant response
    const bodyText = await page.locator('body').innerText().catch(() => '');
    const hasResponse = bodyText.toLowerCase().includes('threshold') ||
                        bodyText.toLowerCase().includes('simplified acquisition') ||
                        bodyText.toLowerCase().includes('far') ||
                        bodyText.toLowerCase().includes('micro-purchase');

    const elapsed = Math.round((Date.now() - startTime) / 1000);
    console.log(`  ${elapsed}s elapsed — typing: ${stillTyping}, hasResponse: ${hasResponse}, toolUseSSE: ${toolUseEvents.length}, toolResultSSE: ${toolResultEvents.length}`);

    // Take periodic screenshots
    if (elapsed % 30 === 0 || (hasResponse && !stillTyping)) {
      await page.screenshot({ path: path.join(OUT_DIR, `step4-progress-${elapsed}s.png`), fullPage: true });
    }

    if (hasResponse && !stillTyping) {
      responseComplete = true;
      console.log(`  Response complete after ${elapsed}s`);
      break;
    }
  }

  if (!responseComplete) {
    console.log('WARNING: Response did not complete within 2 minutes');
  }

  // Wait a bit more for UI to settle
  await page.waitForTimeout(3_000);

  // ── STEP 5: Capture final screenshot of tool cards ────────────────
  console.log('=== STEP 5: Capturing tool card screenshots ===');
  await page.screenshot({ path: path.join(OUT_DIR, 'step5-final-response.png'), fullPage: true });

  // ── STEP 6: Analyze tool cards in the DOM ─────────────────────────
  console.log('=== STEP 6: Analyzing tool cards ===');

  // Tool cards use the rounded-lg border structure from tool-use-display.tsx
  // Each card has a button with icon, label, status dot, and optionally a chevron
  const toolCards = page.locator('.my-1.rounded-lg.border');
  const toolCardCount = await toolCards.count();
  console.log(`Found ${toolCardCount} tool cards in DOM`);

  // Check each tool card for chevron
  const cardResults: Array<{ label: string; hasChevron: boolean; statusColor: string }> = [];

  for (let i = 0; i < toolCardCount; i++) {
    const card = toolCards.nth(i);
    const cardText = await card.innerText().catch(() => '');
    const hasChevron = cardText.includes('\u25BE'); // ▾ character

    // Check status dot color
    const greenDot = await card.locator('.bg-green-500').count();
    const blueDot = await card.locator('.bg-blue-400').count();
    const redDot = await card.locator('.bg-red-400').count();
    const statusColor = greenDot > 0 ? 'green' : blueDot > 0 ? 'blue' : redDot > 0 ? 'red' : 'unknown';

    const label = cardText.split('\n')[0]?.trim() || `Card ${i}`;
    cardResults.push({ label, hasChevron, statusColor });
  }

  // Also try a broader selector — tool cards may not all match .my-1.rounded-lg.border exactly
  // Look for any element containing the chevron character
  const allChevrons = await page.locator('text=▾').count();
  console.log(`Total chevron (▾) characters found on page: ${allChevrons}`);

  // ── STEP 7: Take zoomed screenshots of tool cards ─────────────────
  console.log('=== STEP 7: Tool card detail screenshots ===');
  if (toolCardCount > 0) {
    // Scroll to first tool card and screenshot
    await toolCards.first().scrollIntoViewIfNeeded();
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(OUT_DIR, 'step7-tool-cards-zoomed.png'), fullPage: false });

    // Try to get a bounding box shot of just the tool cards area
    try {
      const firstCard = toolCards.first();
      const lastCard = toolCards.nth(Math.min(toolCardCount - 1, 9));
      const firstBox = await firstCard.boundingBox();
      const lastBox = await lastCard.boundingBox();
      if (firstBox && lastBox) {
        const clipRegion = {
          x: Math.max(0, firstBox.x - 20),
          y: Math.max(0, firstBox.y - 20),
          width: Math.max(firstBox.width, lastBox.width) + 40,
          height: (lastBox.y + lastBox.height) - firstBox.y + 40,
        };
        await page.screenshot({
          path: path.join(OUT_DIR, 'step7-tool-cards-clipped.png'),
          clip: clipRegion,
        });
      }
    } catch {
      console.log('Could not capture clipped screenshot');
    }
  }

  // ── STEP 8: Save SSE dump ─────────────────────────────────────────
  console.log('=== STEP 8: Saving SSE dump ===');
  const sseDump = [
    '=== SSE RAW DUMP ===',
    `Captured at: ${new Date().toISOString()}`,
    `Query: ${query}`,
    '',
    '=== REQUESTS ===',
    ...allRequests,
    '',
    '=== RAW SSE RESPONSE ===',
    ...sseLines,
    '',
    `=== TOOL_USE EVENTS (${toolUseEvents.length}) ===`,
    ...toolUseEvents.map((e, i) => `[${i}] ${e}`),
    '',
    `=== TOOL_RESULT EVENTS (${toolResultEvents.length}) ===`,
    ...toolResultEvents.map((e, i) => `[${i}] ${e}`),
    '',
    '=== CONSOLE ERRORS ===',
    ...consoleErrors,
  ].join('\n');

  fs.writeFileSync(path.join(OUT_DIR, 'sse-raw-3.txt'), sseDump, 'utf-8');
  console.log(`SSE dump saved to ${path.join(OUT_DIR, 'sse-raw-3.txt')}`);

  // ── FINAL REPORT ──────────────────────────────────────────────────
  console.log('\n');
  console.log('================================================================');
  console.log('  TOOL CARD CHEVRON VALIDATION REPORT');
  console.log('================================================================');
  console.log(`  Tool cards found:           ${toolCardCount}`);
  console.log(`  SSE tool_use events:        ${toolUseEvents.length}`);
  console.log(`  SSE tool_result events:     ${toolResultEvents.length}`);
  console.log(`  Chevrons on page:           ${allChevrons}`);
  console.log(`  Response complete:          ${responseComplete ? 'YES' : 'NO'}`);
  console.log('');
  console.log('  Per-card results:');
  let allHaveChevron = true;
  for (const cr of cardResults) {
    const check = cr.hasChevron ? 'YES' : 'NO';
    if (!cr.hasChevron) allHaveChevron = false;
    console.log(`    ${cr.hasChevron ? '[OK]' : '[!!]'} ${cr.label} — chevron: ${check}, status: ${cr.statusColor}`);
  }
  console.log('');
  console.log(`  ALL tool cards have chevron: ${allHaveChevron ? 'YES' : 'NO'}`);
  console.log(`  tool_use == tool_result:     ${toolUseEvents.length === toolResultEvents.length ? 'YES' : 'NO'} (${toolUseEvents.length} vs ${toolResultEvents.length})`);
  console.log('================================================================');

  // Assertion: every tool card should have a chevron
  if (toolCardCount > 0) {
    for (const cr of cardResults) {
      expect(cr.hasChevron, `Tool card "${cr.label}" should have a chevron (▾) indicating tool_result was received`).toBe(true);
    }
    expect(toolUseEvents.length).toBeGreaterThan(0);
    expect(toolResultEvents.length).toBe(toolUseEvents.length);
  }
});
