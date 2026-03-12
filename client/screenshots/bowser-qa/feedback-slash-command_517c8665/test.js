const { chromium } = require('playwright');

(async () => {
  const screenshotsDir = 'C:/Users/blackga/Desktop/eagle/eagle-multi-agent-orchestrator/client/screenshots/bowser-qa/feedback-slash-command_517c8665';
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  const results = [];

  // Collect console errors
  const consoleErrors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });

  // Step 1: Navigate to localhost:3000
  try {
    console.log('Step 1: Navigating to http://localhost:3000...');
    await page.goto('http://localhost:3000', { timeout: 15000, waitUntil: 'networkidle' });
    results.push({ step: 1, name: 'Navigate to homepage', status: 'PASS' });
  } catch (e) {
    console.log('FAIL Step 1:', e.message);
    results.push({ step: 1, name: 'Navigate to homepage', status: 'FAIL', error: e.message });
    await page.screenshot({ path: screenshotsDir + '/00_navigate-homepage.png' });
    console.log(JSON.stringify({ results, stopped: 1, consoleErrors }));
    await browser.close();
    return;
  }

  // Step 2: Screenshot initial state and click Chat card
  await page.screenshot({ path: screenshotsDir + '/00_initial-state.png' });
  console.log('Step 2: Clicking Chat card to enter chat...');
  try {
    // Click the Chat link/card
    await page.click('text=Chat');
    await page.waitForTimeout(2000);
    // Wait for the chat page to load
    await page.waitForURL('**/chat**', { timeout: 10000 }).catch(() => {});
    await page.waitForTimeout(1000);
    await page.screenshot({ path: screenshotsDir + '/01_chat-page.png' });
    results.push({ step: 2, name: 'Navigate to Chat page', status: 'PASS' });
  } catch (e) {
    console.log('FAIL Step 2:', e.message);
    results.push({ step: 2, name: 'Navigate to Chat page', status: 'FAIL', error: e.message });
    await page.screenshot({ path: screenshotsDir + '/01_chat-page-fail.png' });
    console.log(JSON.stringify({ results, stopped: 2, consoleErrors }));
    await browser.close();
    return;
  }

  // Step 3: Find the chat input
  let input;
  try {
    console.log('Step 3: Finding chat input...');
    // Try textarea first, then other selectors
    input = await page.waitForSelector('textarea', { timeout: 10000 }).catch(() => null);
    if (!input) {
      input = await page.waitForSelector('input[type="text"]', { timeout: 5000 }).catch(() => null);
    }
    if (!input) {
      input = await page.waitForSelector('[contenteditable="true"]', { timeout: 5000 }).catch(() => null);
    }
    if (!input) {
      // Dump the page HTML to find the input
      const html = await page.content();
      console.log('Page HTML snippet:', html.substring(0, 3000));
      throw new Error('No chat input found');
    }
    results.push({ step: 3, name: 'Find chat input', status: 'PASS' });
  } catch (e) {
    console.log('FAIL Step 3:', e.message);
    results.push({ step: 3, name: 'Find chat input', status: 'FAIL', error: e.message });
    await page.screenshot({ path: screenshotsDir + '/02_find-input-fail.png' });
    console.log(JSON.stringify({ results, stopped: 3, consoleErrors }));
    await browser.close();
    return;
  }

  // Step 4: Type the feedback command
  try {
    console.log('Step 4: Typing /feedback command...');
    await input.click();
    await input.fill('/feedback This is a test bug - the research command is broken');
    await page.waitForTimeout(500);
    await page.screenshot({ path: screenshotsDir + '/02_typed-feedback-command.png' });
    results.push({ step: 4, name: 'Type /feedback command', status: 'PASS' });
  } catch (e) {
    console.log('FAIL Step 4:', e.message);
    results.push({ step: 4, name: 'Type /feedback command', status: 'FAIL', error: e.message });
    await page.screenshot({ path: screenshotsDir + '/02_type-fail.png' });
    console.log(JSON.stringify({ results, stopped: 4, consoleErrors }));
    await browser.close();
    return;
  }

  // Step 5: Press Enter to send
  try {
    console.log('Step 5: Pressing Enter...');
    await input.press('Enter');
    await page.waitForTimeout(2000);
    await page.screenshot({ path: screenshotsDir + '/03_after-enter.png' });
    results.push({ step: 5, name: 'Press Enter to send', status: 'PASS' });
  } catch (e) {
    console.log('FAIL Step 5:', e.message);
    results.push({ step: 5, name: 'Press Enter to send', status: 'FAIL', error: e.message });
    await page.screenshot({ path: screenshotsDir + '/03_enter-fail.png' });
    console.log(JSON.stringify({ results, stopped: 5, consoleErrors }));
    await browser.close();
    return;
  }

  // Step 6: Check for feedback banner
  console.log('Step 6: Checking for feedback banner...');
  const bodyText = await page.textContent('body');
  const greenBanner = bodyText.includes('Feedback received') || bodyText.includes('feedback received') || bodyText.includes('Thank you');
  const submittingBanner = bodyText.includes('Submitting feedback');
  console.log('Green banner found:', greenBanner);
  console.log('Submitting banner found:', submittingBanner);

  await page.screenshot({ path: screenshotsDir + '/04_result-check.png' });

  if (greenBanner || submittingBanner) {
    results.push({ step: 6, name: 'Check feedback banner', status: 'PASS', detail: greenBanner ? 'Green banner visible' : 'Submitting banner visible' });
  } else {
    results.push({ step: 6, name: 'Check feedback banner', status: 'FAIL', detail: 'No feedback banner found in body text' });
  }

  // Step 7: Wait and take final screenshot
  console.log('Step 7: Waiting 4 seconds for final state...');
  await page.waitForTimeout(4000);
  await page.screenshot({ path: screenshotsDir + '/05_final-state.png' });

  const finalText = await page.textContent('body');
  const greenBannerFinal = finalText.includes('Feedback received') || finalText.includes('feedback received') || finalText.includes('Thank you');

  // Check if AI was NOT invoked - look for assistant message containers
  const assistantMessages = await page.$$('[data-role="assistant"], .assistant-message');
  const noAiResponse = assistantMessages.length === 0;
  console.log('AI response elements found:', assistantMessages.length);
  console.log('Green banner in final state:', greenBannerFinal);

  // Check for visible errors
  const errorElements = await page.$$('[role="alert"]');
  const errorTexts = [];
  for (const el of errorElements) {
    const t = await el.textContent();
    if (t && t.trim()) errorTexts.push(t.trim());
  }
  console.log('Alert elements:', JSON.stringify(errorTexts));
  console.log('Console errors:', JSON.stringify(consoleErrors));

  results.push({ step: 7, name: 'Final state verification', status: 'PASS' });

  console.log('\n=== RESULTS ===');
  console.log(JSON.stringify({ results, greenBannerFinal, noAiResponse, errorTexts, consoleErrors }, null, 2));

  await browser.close();
})();
