import { test, expect } from '@playwright/test';
import path from 'path';
import fs from 'fs';

const SCREENSHOTS_DIR = path.resolve(__dirname, '../../screenshots');
const PROMPT = 'What is the simplified acquisition threshold and what procurement methods can I use below it?';

test('UC: Simple Acquisition - Simplified Acquisition Threshold', async ({ page }) => {
  test.setTimeout(180_000);
  fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });

  const consoleErrors: string[] = [];
  const allLogs: string[] = [];
  const networkErrors: string[] = [];

  // ── SSE capture (added for stream validation) ──────────────────────
  interface SSEEvent {
    type?: string;
    agent_id?: string;
    agent_name?: string;
    timestamp?: string;
    tool_use?: { name?: string; input?: unknown; tool_use_id?: string };
    tool_result?: { name?: string; result?: unknown };
    [key: string]: unknown;
  }
  const sseEvents: SSEEvent[] = [];

  page.on('response', async (response) => {
    if (!response.url().includes('/api/invoke')) return;
    try {
      const body = await response.text();
      for (const line of body.split('\n')) {
        if (!line.startsWith('data: ')) continue;
        try { sseEvents.push(JSON.parse(line.slice(6).trim())); } catch { /* */ }
      }
    } catch { /* */ }
  });

  page.on('console', (msg) => {
    const text = msg.text();
    allLogs.push(`[${msg.type()}] ${text}`);
    if (msg.type() === 'error') consoleErrors.push(text);
  });

  page.on('requestfailed', (req) => {
    networkErrors.push(`${req.method()} ${req.url()} - ${req.failure()?.errorText}`);
  });

  // === STEP 1: Open chat page ===
  console.log('=== STEP 1: Opening http://localhost:3000/chat ===');
  await page.goto('http://localhost:3000/chat', { waitUntil: 'domcontentloaded', timeout: 30_000 });
  await page.waitForTimeout(3_000);
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'uc-validate-sa-initial.png'), fullPage: true });
  console.log('Screenshot: uc-validate-sa-initial.png');

  // === STEP 2: Start a new chat ===
  console.log('=== STEP 2: Looking for New Chat button ===');
  const newChatBtn = page.locator('button:has-text("New Chat"), button:has-text("new chat"), [aria-label*="new chat" i], [aria-label*="New Chat"]').first();
  if (await newChatBtn.isVisible({ timeout: 3_000 }).catch(() => false)) {
    console.log('Clicking New Chat button');
    await newChatBtn.click();
    await page.waitForTimeout(2_000);
  } else {
    console.log('No New Chat button found or no existing messages - proceeding');
  }

  // Find input field
  const candidates = [
    page.getByPlaceholder('Ask about acquisitions'),
    page.getByPlaceholder(/ask/i),
    page.locator('textarea').first(),
    page.locator('input[type="text"]').first(),
    page.locator('[contenteditable="true"]').first(),
  ];

  let chatInput: any = null;
  for (const c of candidates) {
    if (await c.isVisible({ timeout: 2_000 }).catch(() => false)) {
      chatInput = c;
      console.log(`Found chat input`);
      break;
    }
  }

  expect(chatInput, 'Chat input field must be found').not.toBeNull();

  // === STEP 3: Send the message ===
  console.log('=== STEP 3: Sending message ===');
  await chatInput.fill(PROMPT);
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'uc-validate-sa-before-send.png'), fullPage: true });
  console.log('Screenshot: uc-validate-sa-before-send.png');

  // Submit
  const sendBtn = page.locator('button[type="submit"], button[aria-label*="send" i], button:has-text("Send")').first();
  if (await sendBtn.isVisible({ timeout: 2_000 }).catch(() => false)) {
    await sendBtn.click();
  } else {
    await chatInput.press('Enter');
  }
  console.log('Message submitted');

  // === STEP 4: Monitor streaming ===
  console.log('=== STEP 4: Monitoring response ===');
  await page.waitForTimeout(2_000);
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'uc-validate-sa-streaming.png'), fullPage: true });
  console.log('Screenshot: uc-validate-sa-streaming.png');

  // Poll for response completion - up to 120s
  let responseText = '';
  let lastResponseLength = 0;
  let stableCount = 0;
  const maxWait = 120_000;
  const pollInterval = 10_000;
  const startTime = Date.now();

  while (Date.now() - startTime < maxWait) {
    await page.waitForTimeout(pollInterval);
    const bodyText = await page.locator('body').innerText().catch(() => '');

    // Look for assistant response text
    const responseSelectors = [
      '[data-message-role="assistant"]',
      '.copilotkit-assistant-message',
      '[class*="assistant"]',
      '.prose',
      '.markdown',
    ];

    let found = false;
    for (const sel of responseSelectors) {
      const els = page.locator(sel);
      const count = await els.count();
      if (count > 0) {
        responseText = await els.last().innerText().catch(() => '');
        found = true;
        break;
      }
    }

    if (!found) {
      // Fallback: check body for keywords
      if (bodyText.toLowerCase().includes('simplified acquisition') || bodyText.toLowerCase().includes('far part 13')) {
        responseText = bodyText;
        found = true;
      }
    }

    if (found && responseText.length > 0) {
      if (responseText.length === lastResponseLength) {
        stableCount++;
        if (stableCount >= 2) {
          console.log(`Response stabilized after ${Math.round((Date.now() - startTime) / 1000)}s`);
          break;
        }
      } else {
        stableCount = 0;
      }
      lastResponseLength = responseText.length;
    }

    console.log(`Polling... ${Math.round((Date.now() - startTime) / 1000)}s elapsed, response length: ${responseText.length}`);
  }

  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'uc-validate-sa-response.png'), fullPage: true });
  console.log('Screenshot: uc-validate-sa-response.png');

  // If responseText is still empty, grab full body
  if (!responseText) {
    responseText = await page.locator('body').innerText().catch(() => '');
  }

  // === STEP 5: Validate response ===
  console.log('=== STEP 5: Validating response ===');

  const checks = {
    assistantResponse: responseText.length > 100,
    mentionsSAT: /\$?350[,.]?000/.test(responseText),
    mentionsMicroPurchase: /micro.?purchase|15[,.]?000/i.test(responseText),
    mentionsFAR: /FAR/i.test(responseText),
    noErrors: true, // checked below
    inputReEnabled: false, // checked below
  };

  // Check for error banners
  const errorIndicators = await page.locator('[role="alert"], .error, [class*="error"], [class*="Error"]').count();
  const bodyText = await page.locator('body').innerText().catch(() => '');
  const hasErrorText = /something went wrong|error occurred|failed to/i.test(bodyText);
  checks.noErrors = errorIndicators === 0 && !hasErrorText;

  // Check input re-enabled
  if (chatInput) {
    const disabled = await chatInput.isDisabled().catch(() => true);
    checks.inputReEnabled = !disabled;
  }

  console.log('--- Validation Results ---');
  for (const [key, val] of Object.entries(checks)) {
    console.log(`  ${val ? 'PASS' : 'FAIL'}: ${key}`);
  }

  // === STEP 6: SSE validation + tool card rendering ===
  console.log('=== STEP 6: SSE validation + tool card rendering ===');

  // 6a. SSE pairing — tool_use:tool_result 1:1
  const toolUseEvents = sseEvents.filter((e) => e.type === 'tool_use');
  const toolResultEvents = sseEvents.filter((e) => e.type === 'tool_result');
  const toolUseNames = toolUseEvents.map((e) => e.tool_use?.name).filter(Boolean) as string[];
  const toolResultNames = toolResultEvents.map((e) => e.tool_result?.name).filter(Boolean) as string[];

  console.log(`  SSE tool_use events:   ${toolUseEvents.length} [${toolUseNames.join(', ')}]`);
  console.log(`  SSE tool_result events: ${toolResultEvents.length} [${toolResultNames.join(', ')}]`);

  const pairingOk = toolUseNames.length === toolResultNames.length;
  const emptyNameLeaks = toolResultEvents.filter((e) => !e.tool_result?.name).length;
  console.log(`  Pairing match: ${pairingOk ? 'PASS' : 'FAIL'} (${toolUseNames.length} use vs ${toolResultNames.length} result)`);
  console.log(`  Empty-name leaks: ${emptyNameLeaks}`);

  // 6b. Schema spot-check — at least 1 tool_use has agent_id + timestamp
  let schemaSpotOk = false;
  if (toolUseEvents.length > 0) {
    const sample = toolUseEvents[0];
    schemaSpotOk = !!(sample.agent_id && sample.timestamp && sample.tool_use?.name);
    console.log(`  Schema spot-check (tool_use[0]): ${schemaSpotOk ? 'PASS' : 'FAIL'} — agent_id=${!!sample.agent_id}, timestamp=${!!sample.timestamp}, name=${sample.tool_use?.name}`);
  }
  if (toolResultEvents.length > 0) {
    const sample = toolResultEvents[0];
    const hasResult = sample.tool_result?.result !== undefined;
    console.log(`  Schema spot-check (tool_result[0]): ${hasResult ? 'PASS' : 'FAIL'} — name=${sample.tool_result?.name}, has result=${hasResult}`);
  }

  // 6c. Tool card rendering — use actual DOM selector from tool-use-display.tsx
  const toolCards = page.locator('.my-1.rounded-lg.border');
  const cardCount = await toolCards.count();
  console.log(`  Tool cards in DOM: ${cardCount}`);

  const cardDetails: Array<{ label: string; hasChevron: boolean; expandable: boolean }> = [];
  const renderingErrors: string[] = [];

  for (let i = 0; i < cardCount; i++) {
    const card = toolCards.nth(i);
    const cardText = await card.innerText().catch(() => '');
    const label = cardText.split('\n')[0]?.trim() || `Card ${i}`;
    const hasChevron = cardText.includes('\u25BE'); // ▾

    let expandable = false;
    if (hasChevron) {
      const button = card.locator('button').first();
      await button.click();
      await page.waitForTimeout(500);
      const expandedPanel = card.locator('.overflow-auto, .whitespace-pre-wrap, .prose');
      expandable = (await expandedPanel.count()) > 0;

      if (expandable) {
        const panelText = await expandedPanel.first().innerText().catch(() => '');
        // Content should NOT be raw SSE JSON
        if (panelText.includes('"agent_id"') && panelText.includes('"timestamp"')) {
          renderingErrors.push(`Card "${label}": raw SSE JSON leak in expanded content`);
        }
      }
      // Collapse back
      await button.click();
      await page.waitForTimeout(300);
    }

    cardDetails.push({ label, hasChevron, expandable });
    console.log(`  Card[${i}]: "${label}" — chevron: ${hasChevron}, expandable: ${expandable}`);
  }

  // Screenshot with one card expanded
  if (cardCount > 0) {
    const firstExpandable = cardDetails.findIndex((c) => c.hasChevron);
    if (firstExpandable >= 0) {
      await toolCards.nth(firstExpandable).locator('button').first().click();
      await page.waitForTimeout(500);
      await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'uc-validate-sa-tools-expanded.png'), fullPage: true });
      console.log('Screenshot: uc-validate-sa-tools-expanded.png');
      await toolCards.nth(firstExpandable).locator('button').first().click();
    }
  }
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'uc-validate-sa-tools.png'), fullPage: true });

  const cardsWithChevron = cardDetails.filter((c) => c.hasChevron).length;
  console.log(`  Cards with chevron: ${cardsWithChevron}/${cardCount}`);
  if (renderingErrors.length > 0) {
    console.log(`  Rendering errors: ${renderingErrors.join('; ')}`);
  }

  // === STEP 7: Session persistence ===
  console.log('=== STEP 7: Testing session persistence ===');
  await page.reload({ waitUntil: 'domcontentloaded', timeout: 30_000 });
  await page.waitForTimeout(5_000);

  const afterReloadBody = await page.locator('body').innerText().catch(() => '');
  const messagesPersistedUser = afterReloadBody.includes('simplified acquisition threshold');
  const messagesPersistedAssistant = /\$?350[,.]?000/.test(afterReloadBody) || /FAR/i.test(afterReloadBody);

  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'uc-validate-sa-reload.png'), fullPage: true });
  console.log('Screenshot: uc-validate-sa-reload.png');
  console.log(`Session persistence - user message survived: ${messagesPersistedUser}`);
  console.log(`Session persistence - assistant response survived: ${messagesPersistedAssistant}`);

  // === FINAL REPORT ===
  console.log('\n');
  console.log('================================================================');
  console.log('     UC VALIDATION REPORT: Simple Acquisition (SAT)');
  console.log('================================================================');
  console.log(`  Assistant response present:    ${checks.assistantResponse ? 'PASS' : 'FAIL'}`);
  console.log(`  Mentions $350,000 (SAT):       ${checks.mentionsSAT ? 'PASS' : 'FAIL'}`);
  console.log(`  Mentions micro-purchase/$15k:   ${checks.mentionsMicroPurchase ? 'PASS' : 'FAIL'}`);
  console.log(`  Mentions FAR:                  ${checks.mentionsFAR ? 'PASS' : 'FAIL'}`);
  console.log(`  No error messages:             ${checks.noErrors ? 'PASS' : 'FAIL'}`);
  console.log(`  Input re-enabled:              ${checks.inputReEnabled ? 'PASS' : 'FAIL'}`);
  console.log('  ── SSE Pipeline ──');
  console.log(`  SSE events captured:           ${sseEvents.length}`);
  console.log(`  tool_use:tool_result pairing:  ${pairingOk ? 'PASS' : 'FAIL'} (${toolUseNames.length}:${toolResultNames.length})`);
  console.log(`  Empty-name leaks:              ${emptyNameLeaks === 0 ? 'PASS' : 'FAIL'} (${emptyNameLeaks})`);
  console.log(`  Schema spot-check:             ${schemaSpotOk ? 'PASS' : 'N/A'}`);
  console.log('  ── Tool Cards ──');
  console.log(`  Tool cards in DOM:             ${cardCount}`);
  console.log(`  Cards with chevron:            ${cardsWithChevron}/${cardCount}`);
  console.log(`  Rendering errors:              ${renderingErrors.length}`);
  console.log('  ── Session ──');
  console.log(`  Session persistence (user):    ${messagesPersistedUser ? 'PASS' : 'FAIL'}`);
  console.log(`  Session persistence (asst):    ${messagesPersistedAssistant ? 'PASS' : 'FAIL'}`);
  console.log(`  Console errors:                ${consoleErrors.length}`);
  console.log(`  Network failures:              ${networkErrors.length}`);
  console.log('================================================================');

  const allPassed = checks.assistantResponse && checks.mentionsSAT && checks.mentionsMicroPurchase
    && checks.mentionsFAR && checks.noErrors && checks.inputReEnabled
    && pairingOk && emptyNameLeaks === 0 && renderingErrors.length === 0;
  console.log(`  OVERALL VERDICT:               ${allPassed ? 'PASS' : 'FAIL'}`);
  console.log('================================================================');

  // Log response excerpt
  console.log('\n=== RESPONSE EXCERPT (first 2000 chars) ===');
  console.log(responseText.substring(0, 2000));
  console.log('=== END RESPONSE EXCERPT ===');

  if (consoleErrors.length > 0) {
    console.log('\n=== CONSOLE ERRORS ===');
    consoleErrors.slice(0, 20).forEach(e => console.log(`  ${e.substring(0, 200)}`));
  }

  // Assert core checks
  expect(checks.assistantResponse, 'Assistant response must be present').toBeTruthy();
  expect(checks.mentionsFAR, 'Response must mention FAR').toBeTruthy();

  // Assert SSE pipeline checks
  expect(sseEvents.length, 'Should capture SSE events').toBeGreaterThan(0);
  expect(pairingOk, `tool_use:tool_result pairing mismatch (${toolUseNames.length} vs ${toolResultNames.length})`).toBe(true);
  expect(emptyNameLeaks, 'No empty-name tool_result events should leak through').toBe(0);
  expect(renderingErrors, `Rendering errors: ${renderingErrors.join('; ')}`).toHaveLength(0);
});
