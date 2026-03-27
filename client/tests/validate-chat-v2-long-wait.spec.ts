import { test, expect } from '@playwright/test';
import path from 'path';

const SCREENSHOTS_DIR = path.resolve(__dirname, '../../screenshots');

test('chat-v2: send Hello with 60s wait for response', async ({ page }) => {
  test.setTimeout(300_000); // 5 min total timeout

  const consoleErrors: string[] = [];
  const allLogs: string[] = [];
  const networkErrors: string[] = [];

  page.on('console', (msg) => {
    const text = msg.text();
    allLogs.push(`[${msg.type()}] ${text}`);
    if (msg.type() === 'error') consoleErrors.push(text);
  });

  page.on('requestfailed', (req) => {
    networkErrors.push(`${req.method()} ${req.url()} - ${req.failure()?.errorText}`);
  });

  // === STEP 1: Hard refresh ===
  console.log('=== STEP 1: Opening http://localhost:3000/chat-v2 with hard refresh ===');
  await page.goto('http://localhost:3000/chat-v2', {
    waitUntil: 'domcontentloaded',
    timeout: 30_000,
  });

  // === STEP 2: Wait 5s for page to stabilize ===
  console.log('=== STEP 2: Waiting 5s for page to load ===');
  await page.waitForTimeout(5_000);

  // Handle "Try Again" buttons
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

  await page.screenshot({
    path: path.join(SCREENSHOTS_DIR, 'chat-v2-long-01-initial.png'),
    fullPage: true,
  });

  // === STEP 3: Type "Hello" and submit ===
  console.log('=== STEP 3: Typing "Hello" and submitting ===');
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
      console.log(`Found chat input`);
      break;
    }
  }

  if (!chatInput) {
    console.log('ERROR: No chat input found.');
    await page.screenshot({
      path: path.join(SCREENSHOTS_DIR, 'chat-v2-long-ERROR-no-input.png'),
      fullPage: true,
    });
    return;
  }

  await chatInput.fill('Hello');
  await chatInput.press('Enter');
  console.log('Message submitted: "Hello"');

  // === STEP 4: Wait 60 SECONDS for full response ===
  console.log('=== STEP 4: Waiting 60 seconds for Bedrock response ===');
  await page.waitForTimeout(60_000);

  // === STEP 5: Take final screenshot ===
  console.log('=== STEP 5: Taking final screenshot after 60s wait ===');
  await page.screenshot({
    path: path.join(SCREENSHOTS_DIR, 'chat-v2-long-02-after-60s.png'),
    fullPage: true,
  });

  // === Analysis ===
  const bodyText = await page
    .locator('body')
    .innerText()
    .catch(() => '');

  // Check for assistant response
  const responseSelectors = [
    '[data-message-role="assistant"]',
    '.copilotkit-assistant-message',
    '[class*="assistant"]',
    '.prose',
  ];
  let assistantResponseFound = false;
  for (const sel of responseSelectors) {
    const count = await page.locator(sel).count();
    if (count > 0) {
      assistantResponseFound = true;
      console.log(`Assistant response found via "${sel}" (${count} elements)`);
      break;
    }
  }

  if (!assistantResponseFound) {
    // Check body text for any substantive response
    const lowerBody = bodyText.toLowerCase();
    if (
      lowerBody.includes('hello') &&
      (lowerBody.includes('assist') ||
        lowerBody.includes('help') ||
        lowerBody.includes('welcome') ||
        lowerBody.includes('acquisition'))
    ) {
      assistantResponseFound = true;
      console.log('Assistant response detected via body text content');
    }
  }

  // Check AG-UI event types
  const eventTypes = [
    'RUN_STARTED',
    'RUN_FINISHED',
    'TEXT_MESSAGE_START',
    'TEXT_MESSAGE_CONTENT',
    'TEXT_MESSAGE_END',
    'TOOL_CALL_START',
    'TOOL_CALL_ARGS',
    'TOOL_CALL_END',
    'STATE_SNAPSHOT',
    'STATE_DELTA',
    'STEP_STARTED',
    'STEP_FINISHED',
    'CUSTOM',
  ];
  const foundEventTypes = eventTypes.filter((et) => bodyText.includes(et));

  let eventCount = 0;
  for (const et of eventTypes) {
    const regex = new RegExp(et, 'g');
    const matches = bodyText.match(regex);
    if (matches) eventCount += matches.length;
  }

  // Check for visible errors in UI
  const visibleErrors: string[] = [];
  const errorSelectors = ['[class*="error"]', '[role="alert"]', 'text=Error', 'text=error'];
  for (const sel of errorSelectors) {
    const el = page.locator(sel).first();
    if (await el.isVisible({ timeout: 1_000 }).catch(() => false)) {
      const txt = await el.innerText().catch(() => '');
      if (txt) visibleErrors.push(txt.substring(0, 200));
    }
  }

  // === FINAL REPORT ===
  console.log('\n');
  console.log('================================================================');
  console.log('  CHAT-V2 LONG-WAIT (60s) VALIDATION REPORT');
  console.log('================================================================');
  console.log(`  Assistant response rendered:      ${assistantResponseFound ? 'YES' : 'NO'}`);
  console.log(`  AG-UI event types found:          ${foundEventTypes.length}`);
  console.log(`  AG-UI event type list:            ${foundEventTypes.join(', ') || 'NONE'}`);
  console.log(`  Total event mentions in page:     ${eventCount}`);
  console.log(`  Console errors:                   ${consoleErrors.length}`);
  console.log(`  Network failures:                 ${networkErrors.length}`);
  console.log(`  Visible UI errors:                ${visibleErrors.length}`);
  console.log('================================================================');

  if (consoleErrors.length > 0) {
    console.log('\n=== CONSOLE ERRORS ===');
    consoleErrors.slice(0, 20).forEach((e) => console.log(`  ${e.substring(0, 300)}`));
  }

  if (networkErrors.length > 0) {
    console.log('\n=== NETWORK ERRORS ===');
    networkErrors.forEach((e) => console.log(`  ${e}`));
  }

  if (visibleErrors.length > 0) {
    console.log('\n=== VISIBLE UI ERRORS ===');
    visibleErrors.forEach((e) => console.log(`  ${e}`));
  }

  console.log('\n=== PAGE TEXT (first 5000 chars) ===');
  console.log(bodyText.substring(0, 5000));
  console.log('=== END PAGE TEXT ===');

  console.log('\n=== ALL BROWSER LOGS ===');
  allLogs.forEach((l) => console.log(`  ${l}`));
  console.log('=== END LOGS ===');
});
