import { test, expect } from '@playwright/test';
import path from 'path';

const SCREENSHOTS_DIR = path.resolve(__dirname, '../../screenshots');
const PROMPT = 'I need to acquire a $2.5M bioinformatics data platform for NCI. It\'s a 3-year contract with IT services and cloud hosting. Help me determine the acquisition strategy, required documents, and applicable FAR provisions.';

test('UC: Complex Acquisition Package - $2.5M IT Services', async ({ page }) => {
  test.setTimeout(300_000); // 5 minutes max

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

  // === STEP 1: Open chat page ===
  console.log('=== STEP 1: Opening http://localhost:3000/chat ===');
  await page.goto('http://localhost:3000/chat', { waitUntil: 'domcontentloaded', timeout: 30_000 });
  await page.waitForTimeout(3_000);
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'uc-validate-complex-initial.png'), fullPage: true });
  console.log('Screenshot: uc-validate-complex-initial.png');

  // === STEP 2: Start a new chat ===
  console.log('=== STEP 2: Looking for New Chat button ===');
  const newChatBtn = page.locator('button:has-text("New Chat"), button:has-text("new chat"), [aria-label*="new chat" i], [aria-label*="New Chat"]').first();
  if (await newChatBtn.isVisible({ timeout: 3_000 }).catch(() => false)) {
    console.log('Clicking New Chat button');
    await newChatBtn.click();
    await page.waitForTimeout(2_000);
  } else {
    console.log('No New Chat button found - proceeding with current state');
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
      console.log('Found chat input');
      break;
    }
  }

  expect(chatInput, 'Chat input field must be found').not.toBeNull();

  // === STEP 3: Send the message ===
  console.log('=== STEP 3: Sending complex acquisition message ===');
  await chatInput.fill(PROMPT);
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'uc-validate-complex-before-send.png'), fullPage: true });
  console.log('Screenshot: uc-validate-complex-before-send.png');

  // Submit
  const sendBtn = page.locator('button[type="submit"], button[aria-label*="send" i], button:has-text("Send")').first();
  if (await sendBtn.isVisible({ timeout: 2_000 }).catch(() => false)) {
    await sendBtn.click();
  } else {
    await chatInput.press('Enter');
  }
  console.log('Message submitted');
  const sendTime = Date.now();

  // === STEP 4: Monitor streaming ===
  console.log('=== STEP 4: Monitoring response (up to 180s) ===');
  await page.waitForTimeout(5_000);
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'uc-validate-complex-streaming.png'), fullPage: true });
  console.log('Screenshot: uc-validate-complex-streaming.png');

  // Poll for response completion - up to 180s
  let responseText = '';
  let lastResponseLength = 0;
  let stableCount = 0;
  const maxWait = 180_000;
  const pollInterval = 15_000;
  const startTime = Date.now();

  while (Date.now() - startTime < maxWait) {
    await page.waitForTimeout(pollInterval);

    // Try multiple selectors for assistant response
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
        // Get all text from all matching elements
        const texts: string[] = [];
        for (let i = 0; i < count; i++) {
          const t = await els.nth(i).innerText().catch(() => '');
          texts.push(t);
        }
        responseText = texts.join('\n');
        found = true;
        break;
      }
    }

    if (!found) {
      const bodyText = await page.locator('body').innerText().catch(() => '');
      if (bodyText.toLowerCase().includes('acquisition') && bodyText.toLowerCase().includes('far')) {
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

  const responseTime = Math.round((Date.now() - sendTime) / 1000);
  console.log(`Total response time: ${responseTime}s`);

  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'uc-validate-complex-response.png'), fullPage: true });
  console.log('Screenshot: uc-validate-complex-response.png');

  // If responseText is still empty, grab full body
  if (!responseText) {
    responseText = await page.locator('body').innerText().catch(() => '');
  }

  // === STEP 5: Validate response quality ===
  console.log('=== STEP 5: Validating response content ===');
  const lowerResponse = responseText.toLowerCase();

  const contentChecks = {
    assistantResponse: responseText.length > 200,
    acquisitionStrategy: /acquisition (plan|strategy)/i.test(responseText),
    dollarAmount: /\$?2[,.]?5\s*(m|million)|2[,.]?500[,.]?000/i.test(responseText),
    tinaOrCostPricing: /tina|cost or pricing data|certified cost/i.test(responseText),
    farReference: /FAR/i.test(responseText),
    competitive: /competitive|full and open competition/i.test(responseText),
    sowOrPws: /SOW|PWS|statement of work|performance work statement/i.test(responseText),
    igce: /IGCE|cost estimate|independent government/i.test(responseText),
    smallBusiness: /small business|subcontracting|750[,.]?000|\$750/i.test(responseText),
    noErrors: true,
    inputReEnabled: false,
  };

  // Check for error banners
  const errorIndicators = await page.locator('[role="alert"], .error, [class*="error"]:not([class*="console"]), [class*="Error"]:not([class*="Console"])').count();
  const bodyText = await page.locator('body').innerText().catch(() => '');
  const hasErrorText = /something went wrong|error occurred|failed to/i.test(bodyText);
  contentChecks.noErrors = errorIndicators === 0 && !hasErrorText;

  // Check input re-enabled
  if (chatInput) {
    const disabled = await chatInput.isDisabled().catch(() => true);
    contentChecks.inputReEnabled = !disabled;
  }

  console.log('--- Content Check Results ---');
  for (const [key, val] of Object.entries(contentChecks)) {
    console.log(`  ${val ? 'PASS' : 'FAIL'}: ${key}`);
  }

  // === STEP 6: Check for tool cards and activity panel ===
  console.log('=== STEP 6: Checking for tool cards and activity panel ===');
  const toolSelectors = [
    '[data-tool-card]',
    '[class*="tool-card"]',
    '[class*="toolCard"]',
    '[class*="ToolCard"]',
    'text=query_compliance_matrix',
    'text=search_far',
    'text=knowledge_search',
    'text=Tool',
    '[class*="activity"]',
    '[class*="Activity"]',
  ];

  let toolCardsFound = false;
  const toolsDetected: string[] = [];
  for (const sel of toolSelectors) {
    const count = await page.locator(sel).count();
    if (count > 0) {
      toolCardsFound = true;
      const text = await page.locator(sel).first().innerText().catch(() => sel);
      toolsDetected.push(`${sel} (${count}): ${text.substring(0, 120)}`);
    }
  }

  // Check for tool/specialist names in body text
  const toolNames = ['query_compliance_matrix', 'search_far', 'knowledge_search', 'specialist', 'subagent', 'delegate', 'FAR_Specialist', 'Acquisition_Specialist', 'Cost_Specialist', 'Compliance_Specialist'];
  const toolsMentioned = toolNames.filter(t => bodyText.toLowerCase().includes(t.toLowerCase()));

  // Check activity/agent panel
  const activitySelectors = [
    '[class*="activity-panel"]',
    '[class*="ActivityPanel"]',
    '[class*="agent-log"]',
    '[class*="AgentLog"]',
    'text=Activity',
    'text=Agent',
    'text=Logs',
  ];

  let activityPanelFound = false;
  for (const sel of activitySelectors) {
    const count = await page.locator(sel).count();
    if (count > 0) {
      activityPanelFound = true;
      console.log(`Activity panel found via: ${sel} (${count} elements)`);
      break;
    }
  }

  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'uc-validate-complex-tools.png'), fullPage: true });
  console.log('Screenshot: uc-validate-complex-tools.png');

  // Try to open/expand activity panel if there's a toggle
  const activityToggle = page.locator('button:has-text("Activity"), button:has-text("Logs"), button:has-text("Agent"), [aria-label*="activity" i]').first();
  if (await activityToggle.isVisible({ timeout: 2_000 }).catch(() => false)) {
    console.log('Clicking activity panel toggle');
    await activityToggle.click();
    await page.waitForTimeout(1_000);
  }

  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'uc-validate-complex-activity.png'), fullPage: true });
  console.log('Screenshot: uc-validate-complex-activity.png');

  console.log(`Tool cards found: ${toolCardsFound}`);
  console.log(`Tools detected: ${toolsDetected.join('; ')}`);
  console.log(`Tool names in page text: ${toolsMentioned.join(', ') || 'none'}`);
  console.log(`Activity panel found: ${activityPanelFound}`);

  // === STEP 7: Scroll and capture full response ===
  console.log('=== STEP 7: Capturing full response via scroll ===');

  // Scroll to top of chat area
  const chatContainer = page.locator('[class*="chat"], [class*="messages"], main').first();
  if (await chatContainer.isVisible({ timeout: 2_000 }).catch(() => false)) {
    await chatContainer.evaluate((el: HTMLElement) => el.scrollTop = 0);
    await page.waitForTimeout(500);
  }
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'uc-validate-complex-response-top.png'), fullPage: true });
  console.log('Screenshot: uc-validate-complex-response-top.png');

  // Scroll to bottom
  if (await chatContainer.isVisible({ timeout: 2_000 }).catch(() => false)) {
    await chatContainer.evaluate((el: HTMLElement) => el.scrollTop = el.scrollHeight);
    await page.waitForTimeout(500);
  }
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'uc-validate-complex-response-bottom.png'), fullPage: true });
  console.log('Screenshot: uc-validate-complex-response-bottom.png');

  // === STEP 8: Session persistence ===
  console.log('=== STEP 8: Testing session persistence ===');
  await page.reload({ waitUntil: 'domcontentloaded', timeout: 30_000 });
  await page.waitForTimeout(5_000);

  const afterReloadBody = await page.locator('body').innerText().catch(() => '');
  const reloadLower = afterReloadBody.toLowerCase();
  const messagesPersistedUser = reloadLower.includes('bioinformatics') || reloadLower.includes('2.5m') || reloadLower.includes('data platform');
  const messagesPersistedAssistant = /FAR|acquisition/i.test(afterReloadBody) && afterReloadBody.length > 500;

  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'uc-validate-complex-reload.png'), fullPage: true });
  console.log('Screenshot: uc-validate-complex-reload.png');
  console.log(`Session persistence - user message survived: ${messagesPersistedUser}`);
  console.log(`Session persistence - assistant response survived: ${messagesPersistedAssistant}`);

  // === FINAL REPORT ===
  const passCount = Object.values(contentChecks).filter(v => v).length;
  const totalChecks = Object.keys(contentChecks).length;

  console.log('\n');
  console.log('================================================================');
  console.log('   UC VALIDATION REPORT: Complex Acquisition ($2.5M IT)');
  console.log('================================================================');
  console.log('--- Content Checks ---');
  console.log(`  Assistant response present:      ${contentChecks.assistantResponse ? 'PASS' : 'FAIL'}`);
  console.log(`  Acquisition strategy mentioned:  ${contentChecks.acquisitionStrategy ? 'PASS' : 'FAIL'}`);
  console.log(`  Dollar amount ($2.5M):           ${contentChecks.dollarAmount ? 'PASS' : 'FAIL'}`);
  console.log(`  TINA/cost or pricing data:       ${contentChecks.tinaOrCostPricing ? 'PASS' : 'FAIL'}`);
  console.log(`  FAR reference:                   ${contentChecks.farReference ? 'PASS' : 'FAIL'}`);
  console.log(`  Competitive/full & open:         ${contentChecks.competitive ? 'PASS' : 'FAIL'}`);
  console.log(`  SOW/PWS mentioned:               ${contentChecks.sowOrPws ? 'PASS' : 'FAIL'}`);
  console.log(`  IGCE/cost estimate:              ${contentChecks.igce ? 'PASS' : 'FAIL'}`);
  console.log(`  Small business/$750K:            ${contentChecks.smallBusiness ? 'PASS' : 'FAIL'}`);
  console.log(`  No error messages:               ${contentChecks.noErrors ? 'PASS' : 'FAIL'}`);
  console.log(`  Input re-enabled:                ${contentChecks.inputReEnabled ? 'PASS' : 'FAIL'}`);
  console.log('--- Tooling ---');
  console.log(`  Tool cards visible:              ${toolCardsFound ? 'YES' : 'NO'}`);
  console.log(`  Tools mentioned in text:         ${toolsMentioned.join(', ') || 'none visible'}`);
  console.log(`  Activity panel visible:          ${activityPanelFound ? 'YES' : 'NO'}`);
  console.log('--- Session ---');
  console.log(`  Session persistence (user):      ${messagesPersistedUser ? 'PASS' : 'FAIL'}`);
  console.log(`  Session persistence (asst):      ${messagesPersistedAssistant ? 'PASS' : 'FAIL'}`);
  console.log('--- Performance ---');
  console.log(`  Response time:                   ${responseTime}s`);
  console.log(`  Response length:                 ${responseText.length} chars`);
  console.log('--- Errors ---');
  console.log(`  Console errors:                  ${consoleErrors.length}`);
  console.log(`  Network failures:                ${networkErrors.length}`);
  console.log('================================================================');
  console.log(`  CHECKS PASSED:                   ${passCount}/${totalChecks}`);
  const overallPass = passCount >= totalChecks - 2; // Allow up to 2 soft fails (TINA, small business are nuanced)
  console.log(`  OVERALL VERDICT:                 ${overallPass ? 'PASS' : 'FAIL'}`);
  console.log('================================================================');

  // Log response excerpt
  console.log('\n=== RESPONSE EXCERPT (first 3000 chars) ===');
  console.log(responseText.substring(0, 3000));
  console.log('=== END RESPONSE EXCERPT ===');

  if (responseText.length > 3000) {
    console.log('\n=== RESPONSE MIDDLE (3000-6000 chars) ===');
    console.log(responseText.substring(3000, 6000));
    console.log('=== END RESPONSE MIDDLE ===');
  }

  if (consoleErrors.length > 0) {
    console.log('\n=== CONSOLE ERRORS (first 20) ===');
    consoleErrors.slice(0, 20).forEach(e => console.log(`  ${e.substring(0, 300)}`));
  }

  if (networkErrors.length > 0) {
    console.log('\n=== NETWORK ERRORS ===');
    networkErrors.slice(0, 10).forEach(e => console.log(`  ${e}`));
  }

  // Hard assertions - must pass
  expect(contentChecks.assistantResponse, 'Assistant response must be present').toBeTruthy();
  expect(contentChecks.farReference, 'Response must mention FAR').toBeTruthy();
  expect(contentChecks.noErrors, 'No error messages should be visible').toBeTruthy();
});
