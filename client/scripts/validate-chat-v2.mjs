import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';

const SCREENSHOT_DIR = 'C:/Users/blackga/Desktop/eagle/sm_eagle/screenshots';
if (!fs.existsSync(SCREENSHOT_DIR)) {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  const consoleMessages = [];
  page.on('console', (msg) => {
    const type = msg.type();
    const text = msg.text();
    consoleMessages.push({ type, text });
    if (type === 'error') {
      console.log(`[CONSOLE ERROR] ${text}`);
    }
  });

  page.on('pageerror', (err) => {
    consoleMessages.push({ type: 'pageerror', text: err.message });
    console.log(`[PAGE ERROR] ${err.message}`);
  });

  page.on('requestfailed', (request) => {
    const failure = request.failure();
    const msg = `Request failed: ${request.method()} ${request.url()} - ${failure ? failure.errorText : 'unknown'}`;
    consoleMessages.push({ type: 'requestfailed', text: msg });
    console.log(`[REQUEST FAILED] ${msg}`);
  });

  // Track /info and /copilotkit responses
  const infoResponses = [];
  page.on('response', (res) => {
    if (res.url().includes('/copilotkit') || res.url().includes('/info')) {
      infoResponses.push({ url: res.url(), status: res.status() });
    }
  });

  // === STEP 1: Navigate with hard refresh ===
  console.log('\n=== Step 1: Navigate to http://localhost:3000/chat-v2 (hard refresh) ===');
  await page.goto('http://localhost:3000/chat-v2', { waitUntil: 'networkidle', timeout: 30000 });
  console.log('Page loaded. Performing hard refresh (Ctrl+Shift+R)...');
  await page.reload({ waitUntil: 'networkidle', timeout: 30000 });
  console.log('Hard refresh done.');

  // === STEP 2: Wait 5 seconds for CopilotKit init ===
  console.log('\n=== Step 2: Wait 5s for CopilotKit init ===');
  await page.waitForTimeout(5000);

  // Handle "Try Again" if present
  for (let attempt = 0; attempt < 3; attempt++) {
    const tryAgainBtn = await page.$('button:has-text("Try Again")');
    if (tryAgainBtn && (await tryAgainBtn.isVisible())) {
      console.log(`Clicking "Try Again" (attempt ${attempt + 1})...`);
      await tryAgainBtn.click();
      await page.waitForTimeout(5000);
    } else {
      break;
    }
  }

  // === STEP 3: Screenshot initial state ===
  console.log('\n=== Step 3: Initial state screenshot ===');
  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, 'chat-v2-validate-01-initial.png'),
    fullPage: true,
  });
  console.log('Saved: chat-v2-validate-01-initial.png');

  // Check for "No user message found" error toast
  const bodyTextInitial = await page
    .locator('body')
    .innerText()
    .catch(() => '');
  const hasNoUserMsgError = bodyTextInitial.includes('No user message found');
  console.log(
    `"No user message found" error toast visible: ${hasNoUserMsgError ? 'YES (BAD)' : 'NO (GOOD)'}`,
  );

  // === STEP 4: Check browser console errors ===
  console.log('\n=== Step 4: Console error check (initial) ===');
  const initialErrors = consoleMessages.filter((m) => m.type === 'error' || m.type === 'pageerror');
  console.log(`Console errors so far: ${initialErrors.length}`);
  initialErrors.forEach((e, i) => console.log(`  [${i}] ${e.text.substring(0, 200)}`));

  // === STEP 5: Type "What is FAR Part 6?" and submit ===
  console.log('\n=== Step 5: Type "What is FAR Part 6?" and submit ===');
  const selectors = [
    'textarea',
    'input[type="text"]',
    '[contenteditable="true"]',
    '[role="textbox"]',
  ];

  let inputFound = false;
  for (const sel of selectors) {
    const el = await page.$(sel);
    if (el) {
      console.log(`Found input with selector: ${sel}`);
      await el.click();
      await el.fill('What is FAR Part 6?');
      await page.waitForTimeout(500);
      await page.keyboard.press('Enter');
      inputFound = true;
      console.log('Message submitted.');
      break;
    }
  }

  if (!inputFound) {
    console.log('WARNING: Could not find chat input!');
    const bodyText = await page
      .locator('body')
      .innerText()
      .catch(() => '');
    console.log(`Page body (first 2000 chars): ${bodyText.substring(0, 2000)}`);
  }

  // === STEP 6: Wait 30 seconds for full response ===
  console.log('\n=== Step 6: Wait 30s for Bedrock/Sonnet response to stream ===');
  await page.waitForTimeout(30000);

  // === STEP 7: Full page screenshot after response ===
  console.log('\n=== Step 7: Post-response screenshots ===');
  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, 'chat-v2-validate-02-after-response.png'),
    fullPage: true,
  });
  console.log('Saved: chat-v2-validate-02-after-response.png');

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
      const firstText = await page
        .locator(sel)
        .first()
        .innerText()
        .catch(() => '');
      console.log(`  First element text (first 300 chars): ${firstText.substring(0, 300)}`);
      break;
    }
  }

  // Fallback: check body text for FAR-related content
  const bodyTextFinal = await page
    .locator('body')
    .innerText()
    .catch(() => '');
  if (!assistantResponseFound) {
    if (
      bodyTextFinal.toLowerCase().includes('far part 6') ||
      bodyTextFinal.toLowerCase().includes('competition')
    ) {
      assistantResponseFound = true;
      console.log('Assistant response detected via body text (mentions FAR/competition).');
    }
  }

  // === STEP 8: Check AG-UI Events panel ===
  console.log('\n=== Step 8: AG-UI Events panel analysis ===');
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
  const foundEventTypes = eventTypes.filter((et) => bodyTextFinal.includes(et));
  console.log(`Distinct event types visible in page: ${foundEventTypes.length}`);
  foundEventTypes.forEach((et) => {
    const regex = new RegExp(et, 'g');
    const matches = bodyTextFinal.match(regex);
    console.log(`  - ${et}: ${matches ? matches.length : 0} occurrences`);
  });

  let totalEventMentions = 0;
  for (const et of eventTypes) {
    const regex = new RegExp(et, 'g');
    const matches = bodyTextFinal.match(regex);
    if (matches) totalEventMentions += matches.length;
  }
  console.log(`Total AG-UI event mentions in page text: ${totalEventMentions}`);

  // Check if AG-UI panel header visible
  const agUiVisible = bodyTextFinal.includes('AG-UI') || bodyTextFinal.includes('Events');

  // === STEP 9: Final screenshot ===
  console.log('\n=== Step 9: Final screenshot ===');
  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, 'chat-v2-validate-03-final.png'),
    fullPage: true,
  });
  console.log('Saved: chat-v2-validate-03-final.png');

  // === FINAL REPORT ===
  const allErrors = consoleMessages.filter((m) => m.type === 'error' || m.type === 'pageerror');
  const networkFailures = consoleMessages.filter((m) => m.type === 'requestfailed');

  console.log('\n');
  console.log('========================================================');
  console.log('         CHAT-V2 FINAL VALIDATION REPORT                ');
  console.log('========================================================');
  console.log(
    `  "No user message found" error on load:  ${hasNoUserMsgError ? 'YES (REGRESSION)' : 'NO (FIXED)'}`,
  );
  console.log(`  Chat input found:                       ${inputFound ? 'YES' : 'NO'}`);
  console.log(
    `  Assistant response rendered in chat:     ${assistantResponseFound ? 'YES' : 'NO'}`,
  );
  console.log(`  AG-UI Events panel visible:              ${agUiVisible ? 'YES' : 'NO'}`);
  console.log(`  Distinct AG-UI event types:              ${foundEventTypes.length}`);
  console.log(`  Total AG-UI event mentions:              ${totalEventMentions}`);
  console.log(`  Event types found:                       ${foundEventTypes.join(', ') || 'NONE'}`);
  console.log(`  Total console errors:                    ${allErrors.length}`);
  console.log(`  Network failures:                        ${networkFailures.length}`);
  console.log(`  /copilotkit API responses:               ${infoResponses.length}`);
  infoResponses.forEach((r) => console.log(`    ${r.status} ${r.url}`));
  console.log('========================================================');

  // Dump console errors
  if (allErrors.length > 0) {
    console.log('\n=== CONSOLE ERRORS ===');
    allErrors.forEach((e, i) => console.log(`  [${i}] ${e.text.substring(0, 300)}`));
  }

  // Dump page text excerpt
  console.log('\n=== PAGE TEXT (first 5000 chars) ===');
  console.log(bodyTextFinal.substring(0, 5000));
  console.log('=== END PAGE TEXT ===');

  await browser.close();
  console.log('\nValidation complete.');
})();
