import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';

const SCREENSHOT_DIR = 'C:/Users/blackga/Desktop/eagle/sm_eagle/screenshots';
if (!fs.existsSync(SCREENSHOT_DIR)) {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
}

function ss(name) {
  return path.join(SCREENSHOT_DIR, name);
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  const consoleMessages = [];
  page.on('console', (msg) => {
    consoleMessages.push({ type: msg.type(), text: msg.text() });
    if (msg.type() === 'error') console.log(`[CONSOLE ERROR] ${msg.text()}`);
  });
  page.on('pageerror', (err) => {
    consoleMessages.push({ type: 'pageerror', text: err.message });
    console.log(`[PAGE ERROR] ${err.message}`);
  });

  // === STEP 1: Navigate to chat ===
  console.log('\n=== Step 1: Navigate to http://localhost:3000/chat ===');
  try {
    await page.goto('http://localhost:3000/chat', { waitUntil: 'networkidle', timeout: 30000 });
  } catch (e) {
    console.log(`Navigation warning: ${e.message}`);
    // Try to continue even if networkidle times out
  }
  console.log('Page loaded.');
  await page.waitForTimeout(3000);

  // === STEP 2: Full page screenshot ===
  console.log('\n=== Step 2: Full page screenshot ===');
  await page.screenshot({ path: ss('chat-full.png'), fullPage: true });
  console.log('Saved: chat-full.png');

  // === STEP 3: Snapshot interactive elements ===
  console.log('\n=== Step 3: Interactive elements snapshot ===');
  const bodyText = await page
    .locator('body')
    .innerText()
    .catch(() => '');

  // Find all buttons
  const buttons = await page.locator('button').all();
  console.log(`Found ${buttons.length} buttons:`);
  for (let i = 0; i < buttons.length; i++) {
    const text = await buttons[i].innerText().catch(() => '');
    const ariaLabel = await buttons[i].getAttribute('aria-label').catch(() => '');
    const visible = await buttons[i].isVisible().catch(() => false);
    if (visible && (text.trim() || ariaLabel)) {
      console.log(
        `  Button[${i}]: text="${text.trim().substring(0, 60)}" aria="${ariaLabel || ''}"`,
      );
    }
  }

  // Find tabs
  const tabs = await page
    .locator('[role="tab"], [data-state="active"], [data-state="inactive"]')
    .all();
  console.log(`\nFound ${tabs.length} tab-like elements:`);
  for (const tab of tabs) {
    const text = await tab.innerText().catch(() => '');
    const visible = await tab.isVisible().catch(() => false);
    if (visible) console.log(`  Tab: "${text.trim()}"`);
  }

  // Find inputs/textareas
  const inputs = await page
    .locator('textarea, input[type="text"], [contenteditable="true"], [role="textbox"]')
    .all();
  console.log(`\nFound ${inputs.length} input elements`);

  // Look for specific text patterns
  const patterns = [
    'Current',
    'History',
    'Logs',
    'Documents',
    'Notifications',
    'Activity',
    'Checklist',
    'Summary',
  ];
  console.log('\nText pattern search in page:');
  for (const p of patterns) {
    const found = bodyText.includes(p);
    console.log(`  "${p}": ${found ? 'FOUND' : 'not found'}`);
  }

  // === STEP 4: Look for right side panel tabs ===
  console.log('\n=== Step 4: Right panel tabs ===');

  // Try to find "Current" tab
  let currentTab = await page
    .locator('button:has-text("Current"), [role="tab"]:has-text("Current")')
    .first();
  let currentTabVisible = await currentTab.isVisible().catch(() => false);
  if (currentTabVisible) {
    console.log('Found "Current" tab - clicking it');
    await currentTab.click();
    await page.waitForTimeout(1000);
    await page.screenshot({ path: ss('chat-right-panel.png'), fullPage: true });
    console.log('Saved: chat-right-panel.png');
  } else {
    console.log('"Current" tab not found. Taking screenshot of whatever right panel exists.');
    await page.screenshot({ path: ss('chat-right-panel.png'), fullPage: true });
  }

  // Try "History" tab
  let historyTab = await page
    .locator('button:has-text("History"), [role="tab"]:has-text("History")')
    .first();
  let historyTabVisible = await historyTab.isVisible().catch(() => false);
  if (historyTabVisible) {
    console.log('Found "History" tab - clicking it');
    await historyTab.click();
    await page.waitForTimeout(1000);
    await page.screenshot({ path: ss('chat-history-tab.png'), fullPage: true });
    console.log('Saved: chat-history-tab.png');
  } else {
    console.log('"History" tab not found');
  }

  // Try "Logs" tab
  let logsTab = await page
    .locator('button:has-text("Logs"), [role="tab"]:has-text("Logs")')
    .first();
  let logsTabVisible = await logsTab.isVisible().catch(() => false);
  if (logsTabVisible) {
    console.log('Found "Logs" tab - clicking it');
    await logsTab.click();
    await page.waitForTimeout(1000);
    await page.screenshot({ path: ss('chat-logs-tab.png'), fullPage: true });
    console.log('Saved: chat-logs-tab.png');
  } else {
    console.log('"Logs" tab not found');
  }

  // === STEP 5: Welcome / initial state screenshot ===
  console.log('\n=== Step 5: Welcome state ===');
  // Click back to Current tab if it exists
  if (currentTabVisible) {
    await currentTab.click().catch(() => {});
    await page.waitForTimeout(500);
  }
  await page.screenshot({ path: ss('chat-welcome.png'), fullPage: true });
  console.log('Saved: chat-welcome.png');

  // Look for suggested prompts
  const suggestElements = await page
    .locator('[class*="suggest"], [class*="prompt"], [class*="quick"], [class*="starter"]')
    .all();
  console.log(`Suggested prompt elements: ${suggestElements.length}`);
  for (const el of suggestElements) {
    const text = await el.innerText().catch(() => '');
    const visible = await el.isVisible().catch(() => false);
    if (visible && text.trim()) console.log(`  Suggestion: "${text.trim().substring(0, 80)}"`);
  }

  // === STEP 6: Send acquisition message ===
  console.log('\n=== Step 6: Send test message ===');
  const message =
    'I need to start a new acquisition for a CT scanner, estimated value $250,000, needed within 6 months.';

  const inputSelectors = [
    'textarea',
    'input[type="text"]',
    '[contenteditable="true"]',
    '[role="textbox"]',
  ];
  let inputFound = false;
  for (const sel of inputSelectors) {
    const el = await page.$(sel);
    if (el && (await el.isVisible())) {
      console.log(`Found input with selector: ${sel}`);
      await el.click();
      await el.fill(message);
      await page.waitForTimeout(500);
      await page.keyboard.press('Enter');
      inputFound = true;
      console.log('Message submitted.');
      break;
    }
  }

  if (!inputFound) {
    console.log('WARNING: Could not find chat input!');
    console.log(`Page text (first 3000 chars): ${bodyText.substring(0, 3000)}`);
  }

  // === STEP 7: Wait for response (up to 120 seconds) ===
  console.log('\n=== Step 7: Waiting for response (up to 120s) ===');

  // Take a screenshot at 15s to show streaming
  await page.waitForTimeout(15000);
  console.log('15s elapsed - checking for streaming...');
  await page.screenshot({ path: ss('chat-streaming.png'), fullPage: true });

  // Wait remaining time, checking for response completion
  let responseComplete = false;
  for (let i = 0; i < 21; i++) {
    // 21 * 5s = 105s more
    await page.waitForTimeout(5000);
    const elapsed = 15 + (i + 1) * 5;

    // Check if input is re-enabled (sign of completion)
    const textarea = await page.$('textarea');
    if (textarea) {
      const disabled = await textarea.getAttribute('disabled');
      const placeholder = await textarea.getAttribute('placeholder');
      if (!disabled && placeholder && !placeholder.toLowerCase().includes('wait')) {
        console.log(`Response appears complete at ${elapsed}s`);
        responseComplete = true;
        break;
      }
    }

    // Also check for assistant message content
    const currentBodyText = await page
      .locator('body')
      .innerText()
      .catch(() => '');
    if (currentBodyText.includes('acquisition') && currentBodyText.includes('CT') && elapsed > 20) {
      // Give a few more seconds for streaming to finish
      await page.waitForTimeout(5000);
      console.log(`Response content detected at ${elapsed + 5}s`);
      responseComplete = true;
      break;
    }

    if (i % 4 === 0) console.log(`Still waiting... ${elapsed}s elapsed`);
  }

  if (!responseComplete) {
    console.log('WARNING: Response may not have completed within 120s');
  }

  // === STEP 8: Post-response screenshots ===
  console.log('\n=== Step 8: Post-response screenshots ===');
  await page.screenshot({ path: ss('chat-response.png'), fullPage: true });
  console.log('Saved: chat-response.png');

  // Get updated body text
  const bodyTextAfter = await page
    .locator('body')
    .innerText()
    .catch(() => '');

  // === STEP 9: Check right panel after response ===
  console.log('\n=== Step 9: Right panel after response ===');
  // Click Current tab again if available
  currentTab = await page
    .locator('button:has-text("Current"), [role="tab"]:has-text("Current")')
    .first();
  currentTabVisible = await currentTab.isVisible().catch(() => false);
  if (currentTabVisible) {
    await currentTab.click();
    await page.waitForTimeout(1000);
  }
  await page.screenshot({ path: ss('chat-checklist-after.png'), fullPage: true });
  console.log('Saved: chat-checklist-after.png');

  // Look for checklist items
  const checklistPatterns = [
    'checklist',
    'SOW',
    'IGCE',
    'Acquisition Plan',
    'Market Research',
    'J&A',
    'requirement',
  ];
  console.log('\nChecklist/document pattern search after response:');
  for (const p of checklistPatterns) {
    const found = bodyTextAfter.toLowerCase().includes(p.toLowerCase());
    console.log(`  "${p}": ${found ? 'FOUND' : 'not found'}`);
  }

  // === STEP 10: Look for inline forms ===
  console.log('\n=== Step 10: Inline forms check ===');
  const formElements = await page
    .locator(
      'form, [class*="form"], [class*="inline-form"], [class*="equipment"], [class*="funding"]',
    )
    .all();
  console.log(`Form-like elements: ${formElements.length}`);
  for (const el of formElements) {
    const text = await el.innerText().catch(() => '');
    const visible = await el.isVisible().catch(() => false);
    if (visible && text.trim()) {
      console.log(`  Form: "${text.trim().substring(0, 100)}"`);
    }
  }

  if (formElements.length > 0) {
    await page.screenshot({ path: ss('chat-inline-forms.png'), fullPage: true });
    console.log('Saved: chat-inline-forms.png');
  } else {
    console.log('No inline forms detected.');
  }

  // === STEP 11: Check for acquisition summary card ===
  console.log('\n=== Step 11: Acquisition summary / card check ===');
  const summaryPatterns = [
    'summary',
    'acquisition',
    '$250',
    '250,000',
    'CT scanner',
    'equipment',
    'medical',
  ];
  console.log('Summary/card pattern search:');
  for (const p of summaryPatterns) {
    const found = bodyTextAfter.toLowerCase().includes(p.toLowerCase());
    console.log(`  "${p}": ${found ? 'FOUND' : 'not found'}`);
  }

  // === STEP 12: Check assistant response content ===
  console.log('\n=== Step 12: Assistant response analysis ===');
  const responseSelectors = [
    '[data-message-role="assistant"]',
    '.copilotkit-assistant-message',
    '[class*="assistant"]',
    '.prose',
    '[class*="message"]',
  ];
  let assistantFound = false;
  for (const sel of responseSelectors) {
    const count = await page.locator(sel).count();
    if (count > 0) {
      assistantFound = true;
      console.log(`Assistant response found via "${sel}" (${count} elements)`);
      const text = await page
        .locator(sel)
        .last()
        .innerText()
        .catch(() => '');
      console.log(`  Last element text (first 500 chars): ${text.substring(0, 500)}`);
      break;
    }
  }
  if (!assistantFound) {
    // Check body text for response content
    if (bodyTextAfter.length > bodyText.length + 100) {
      console.log('Page content grew significantly - response likely rendered.');
      const newContent = bodyTextAfter.substring(bodyText.length);
      console.log(`New content (first 500 chars): ${newContent.substring(0, 500)}`);
    } else {
      console.log('WARNING: No assistant response detected.');
    }
  }

  // === STEP 13: Check for errors ===
  console.log('\n=== Step 13: Error check ===');
  const errors = consoleMessages.filter((m) => m.type === 'error' || m.type === 'pageerror');
  console.log(`Total console errors: ${errors.length}`);
  errors.slice(0, 10).forEach((e, i) => console.log(`  [${i}] ${e.text.substring(0, 200)}`));

  // Check for visible error messages in UI
  const errorElements = await page.locator('[class*="error"], [role="alert"], .toast-error').all();
  let visibleErrors = 0;
  for (const el of errorElements) {
    const visible = await el.isVisible().catch(() => false);
    if (visible) {
      visibleErrors++;
      const text = await el.innerText().catch(() => '');
      console.log(`  Visible error element: "${text.trim().substring(0, 100)}"`);
    }
  }
  console.log(`Visible UI error elements: ${visibleErrors}`);

  // === FINAL REPORT ===
  console.log('\n');
  console.log('========================================================');
  console.log('         CHAT UI INSPECTION REPORT                      ');
  console.log('========================================================');
  console.log(`  Page loaded:                    YES`);
  console.log(`  Chat input found:               ${inputFound ? 'YES' : 'NO'}`);
  console.log(`  Message sent:                   ${inputFound ? 'YES' : 'NO'}`);
  console.log(`  Response received:              ${responseComplete ? 'YES' : 'UNKNOWN/TIMEOUT'}`);
  console.log(`  Assistant response rendered:    ${assistantFound ? 'YES' : 'CHECK SCREENSHOTS'}`);
  console.log(`  "Current" tab found:            ${currentTabVisible ? 'YES' : 'NO'}`);
  console.log(`  "History" tab found:            ${historyTabVisible ? 'YES' : 'NO'}`);
  console.log(`  "Logs" tab found:               ${logsTabVisible ? 'YES' : 'NO'}`);
  console.log(`  Inline forms found:             ${formElements.length > 0 ? 'YES' : 'NO'}`);
  console.log(`  Console errors:                 ${errors.length}`);
  console.log(`  Visible UI errors:              ${visibleErrors}`);
  console.log('========================================================');

  // Dump page text excerpt
  console.log('\n=== PAGE TEXT (first 5000 chars) ===');
  console.log(bodyTextAfter.substring(0, 5000));
  console.log('=== END PAGE TEXT ===');

  await browser.close();
  console.log('\nBrowser closed. Test complete.');
})();
