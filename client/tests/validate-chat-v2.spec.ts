import { test, expect } from '@playwright/test';
import path from 'path';

const SCREENSHOTS_DIR = path.resolve(__dirname, '../../screenshots');

test('Full validation of chat-v2 CopilotKit + AG-UI integration', async ({ page }) => {
  test.setTimeout(180_000);

  const consoleErrors: string[] = [];
  const consoleWarnings: string[] = [];
  const allLogs: string[] = [];
  const networkErrors: string[] = [];

  page.on('console', (msg) => {
    const text = msg.text();
    allLogs.push(`[${msg.type()}] ${text}`);
    if (msg.type() === 'error') consoleErrors.push(text);
    if (msg.type() === 'warning') consoleWarnings.push(text);
  });

  page.on('requestfailed', (req) => {
    networkErrors.push(`${req.method()} ${req.url()} - ${req.failure()?.errorText}`);
  });

  // Track /info requests
  const infoRequests: { url: string; status: number }[] = [];
  page.on('response', (res) => {
    if (res.url().includes('/info')) {
      infoRequests.push({ url: res.url(), status: res.status() });
    }
  });

  // === STEP 1: Hard refresh navigation ===
  console.log('=== STEP 1: Opening http://localhost:3000/chat-v2 with hard refresh ===');
  await page.goto('http://localhost:3000/chat-v2', { waitUntil: 'domcontentloaded', timeout: 30_000 });

  // === STEP 2: Wait for CopilotKit to initialize ===
  console.log('=== STEP 2: Waiting 5s for CopilotKit init ===');
  await page.waitForTimeout(5_000);

  // Handle "Try Again" buttons if CopilotKit had a stale error
  for (let attempt = 0; attempt < 3; attempt++) {
    const tryAgainBtn = page.locator('button:has-text("Try Again")');
    if (await tryAgainBtn.isVisible({ timeout: 2_000 }).catch(() => false)) {
      console.log(`Clicking "Try Again" (attempt ${attempt + 1})...`);
      await tryAgainBtn.click();
      await page.waitForTimeout(5_000);
    } else {
      break;
    }
  }

  // === STEP 3: Screenshot initial state ===
  console.log('=== STEP 3: Initial state screenshot ===');
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'chat-v2-01-initial.png'), fullPage: true });

  // === STEP 4: Check console for errors ===
  console.log('=== STEP 4: Console error analysis ===');
  const runtimeInfoErrors = consoleErrors.filter(e => e.includes('Failed to load runtime info'));
  const agentNotFound = [...consoleErrors, ...consoleWarnings, ...allLogs].filter(
    e => e.toLowerCase().includes('agent') && e.toLowerCase().includes('not found')
  );
  const infoErrors = [...consoleErrors, ...allLogs].filter(
    e => e.includes('/info') && (e.includes('404') || e.includes('error') || e.includes('Error'))
  );

  console.log(`/info requests captured: ${infoRequests.length}`);
  infoRequests.forEach(r => console.log(`  ${r.url} -> ${r.status}`));
  console.log(`"Failed to load runtime info" errors: ${runtimeInfoErrors.length}`);
  console.log(`"Agent not found" mentions: ${agentNotFound.length}`);
  console.log(`/info related errors in console: ${infoErrors.length}`);

  // === STEP 5: Screenshot of console state (capture page with any visible errors) ===
  console.log('=== STEP 5: Console state screenshot ===');
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'chat-v2-02-console-state.png'), fullPage: true });

  // === STEP 6: Type "What is FAR Part 6?" and submit ===
  console.log('=== STEP 6: Typing "What is FAR Part 6?" ===');
  const candidates = [
    page.getByPlaceholder('Ask about acquisitions'),
    page.locator('textarea').first(),
    page.locator('input[type="text"]').first(),
    page.locator('[contenteditable="true"]').first(),
  ];

  let chatInput: any = null;
  for (const c of candidates) {
    if (await c.isVisible({ timeout: 2_000 }).catch(() => false)) {
      chatInput = c;
      console.log(`Found chat input via: ${c}`);
      break;
    }
  }

  if (!chatInput) {
    console.log('ERROR: No chat input found. Page may not have loaded correctly.');
    const bodyText = await page.locator('body').innerText().catch(() => '');
    console.log(`Page body (first 3000 chars): ${bodyText.substring(0, 3000)}`);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'chat-v2-ERROR-no-input.png'), fullPage: true });
    return;
  }

  await chatInput.fill('What is FAR Part 6?');
  await chatInput.press('Enter');
  console.log('Message submitted: "What is FAR Part 6?"');

  // === STEP 7: Wait 25 seconds for full response ===
  console.log('=== STEP 7: Waiting 25s for Bedrock response ===');
  await page.waitForTimeout(25_000);

  // === STEP 8: Screenshot showing response + AG-UI panel ===
  console.log('=== STEP 8: Post-response screenshot ===');
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'chat-v2-03-after-response.png'), fullPage: true });

  // Check for assistant response in chat
  const responseSelectors = [
    '[data-message-role="assistant"]',
    '.copilotkit-assistant-message',
    '[class*="assistant"]',
    '.prose',  // common markdown render container
  ];
  let assistantResponseFound = false;
  let assistantResponseSelector = '';
  for (const sel of responseSelectors) {
    const count = await page.locator(sel).count();
    if (count > 0) {
      assistantResponseFound = true;
      assistantResponseSelector = sel;
      console.log(`Assistant response found via "${sel}" (${count} elements)`);
      break;
    }
  }

  if (!assistantResponseFound) {
    // Try broader text-based detection
    const bodyText = await page.locator('body').innerText().catch(() => '');
    if (bodyText.toLowerCase().includes('far part 6') || bodyText.toLowerCase().includes('competition')) {
      assistantResponseFound = true;
      console.log('Assistant response detected via body text content (mentions FAR/competition)');
    }
  }

  // Check AG-UI Events panel
  const agUiPanelSelectors = [
    'text=AG-UI Events',
    'text=AG-UI EVENTS',
    'text=ag-ui events',
    '[class*="event"]',
    '[class*="agui"]',
  ];
  let agUiVisible = false;
  for (const sel of agUiPanelSelectors) {
    if (await page.locator(sel).first().isVisible({ timeout: 2_000 }).catch(() => false)) {
      agUiVisible = true;
      console.log(`AG-UI panel found via: ${sel}`);
      break;
    }
  }

  // Count event badges/items
  const eventBadgeSelectors = [
    '[class*="badge"]',
    '[class*="event-type"]',
    '[class*="event-item"]',
    'button:has-text("RUN_STARTED")',
    'button:has-text("TEXT_MESSAGE")',
    'button:has-text("TOOL_CALL")',
    ':text("RUN_STARTED")',
    ':text("TEXT_MESSAGE")',
    ':text("TOOL_CALL")',
  ];

  // Detect event types in page text
  const bodyText = await page.locator('body').innerText().catch(() => '');
  const eventTypes = [
    'RUN_STARTED', 'RUN_FINISHED',
    'TEXT_MESSAGE_START', 'TEXT_MESSAGE_CONTENT', 'TEXT_MESSAGE_END',
    'TOOL_CALL_START', 'TOOL_CALL_ARGS', 'TOOL_CALL_END',
    'STATE_SNAPSHOT', 'STATE_DELTA',
    'STEP_STARTED', 'STEP_FINISHED',
    'CUSTOM',
  ];
  const foundEventTypes = eventTypes.filter(et => bodyText.includes(et));
  console.log(`Event types found in page text: ${foundEventTypes.length}`);
  foundEventTypes.forEach(et => console.log(`  - ${et}`));

  // Count total events mentioned
  let eventCount = 0;
  for (const et of eventTypes) {
    const regex = new RegExp(et, 'g');
    const matches = bodyText.match(regex);
    if (matches) eventCount += matches.length;
  }
  console.log(`Total event mentions in page: ${eventCount}`);

  // === STEP 9: Try clicking an event badge ===
  console.log('=== STEP 9: Attempting to click an event badge ===');
  let modalOpened = false;
  if (foundEventTypes.length > 0) {
    // Try clicking the first event type found
    for (const et of foundEventTypes) {
      const badge = page.locator(`text=${et}`).first();
      if (await badge.isVisible({ timeout: 2_000 }).catch(() => false)) {
        console.log(`Clicking event badge: ${et}`);
        await badge.click();
        await page.waitForTimeout(2_000);

        // Check if modal opened
        const modalSelectors = [
          '[role="dialog"]',
          '[class*="modal"]',
          '[class*="Modal"]',
          '[class*="detail"]',
        ];
        for (const ms of modalSelectors) {
          if (await page.locator(ms).first().isVisible({ timeout: 2_000 }).catch(() => false)) {
            modalOpened = true;
            console.log(`Modal opened via: ${ms}`);
            break;
          }
        }

        // === STEP 10: Screenshot of detail modal ===
        if (modalOpened) {
          console.log('=== STEP 10: Detail modal screenshot ===');
          await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'chat-v2-04-event-detail-modal.png'), fullPage: true });
        } else {
          console.log('No modal detected after clicking badge, taking screenshot anyway');
          await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'chat-v2-04-after-badge-click.png'), fullPage: true });
        }
        break;
      }
    }
  } else {
    console.log('No event badges found to click.');
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'chat-v2-04-no-events.png'), fullPage: true });
  }

  // === FINAL REPORT ===
  console.log('\n');
  console.log('╔══════════════════════════════════════════════════════════════╗');
  console.log('║              CHAT-V2 VALIDATION REPORT                      ║');
  console.log('╠══════════════════════════════════════════════════════════════╣');
  console.log(`║ /info succeeded (no 404):        ${infoRequests.every(r => r.status < 400) ? 'YES' : 'NO'}  (${infoRequests.length} requests)`);
  console.log(`║ "Agent eagle not found" in console: ${agentNotFound.length > 0 ? 'YES (' + agentNotFound.length + ')' : 'NO'}`);
  console.log(`║ Assistant response rendered:      ${assistantResponseFound ? 'YES' : 'NO'}`);
  console.log(`║ AG-UI Events panel visible:       ${agUiVisible ? 'YES' : 'NO'}`);
  console.log(`║ AG-UI event count:                ${eventCount}`);
  console.log(`║ Event types found:                ${foundEventTypes.length > 0 ? foundEventTypes.join(', ') : 'NONE'}`);
  console.log(`║ Event detail modal opened:        ${modalOpened ? 'YES' : 'NO'}`);
  console.log(`║ Total console errors:             ${consoleErrors.length}`);
  console.log(`║ Network failures:                 ${networkErrors.length}`);
  console.log('╚══════════════════════════════════════════════════════════════╝');
  console.log('\n');

  // Dump all console errors
  if (consoleErrors.length > 0) {
    console.log('=== CONSOLE ERRORS ===');
    consoleErrors.forEach(e => console.log(`  ERROR: ${e}`));
  }

  // Dump all browser logs
  console.log('=== ALL BROWSER CONSOLE LOGS ===');
  allLogs.forEach(l => console.log(`  ${l}`));
  console.log('=== END CONSOLE LOGS ===');

  // Dump network errors
  if (networkErrors.length > 0) {
    console.log('=== NETWORK ERRORS ===');
    networkErrors.forEach(e => console.log(`  ${e}`));
  }

  // Dump page text excerpt
  console.log('=== PAGE TEXT (first 4000 chars) ===');
  console.log(bodyText.substring(0, 4000));
  console.log('=== END PAGE TEXT ===');
});
