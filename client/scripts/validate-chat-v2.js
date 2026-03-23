const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1400, height: 900 },
  });
  const page = await context.newPage();

  // Log all network requests to /api/copilotkit
  page.on('request', req => {
    if (req.url().includes('copilotkit')) {
      console.log(`[NET] ${req.method()} ${req.url()}`);
      if (req.postData()) {
        console.log(`[NET] Body: ${req.postData().substring(0, 200)}`);
      }
    }
  });

  page.on('response', async res => {
    if (res.url().includes('copilotkit') && res.url().includes('info')) {
      try {
        const body = await res.text();
        console.log(`[NET] Response ${res.status()} from ${res.url()}: ${body.substring(0, 500)}`);
      } catch (e) {
        console.log(`[NET] Response ${res.status()} from ${res.url()} (could not read body: ${e.message})`);
      }
    }
  });

  // Log console messages from the page
  page.on('console', msg => {
    if (msg.type() === 'error' || msg.text().includes('agent') || msg.text().includes('Agent') || msg.text().includes('copilot') || msg.text().includes('EAGLE')) {
      console.log(`[CONSOLE ${msg.type()}] ${msg.text()}`);
    }
  });

  // Log page errors
  page.on('pageerror', err => {
    console.log(`[PAGE ERROR] ${err.message}`);
  });

  // Step 1: Navigate
  console.log('Navigating to http://localhost:3000/chat-v2...');
  try {
    await page.goto('http://localhost:3000/chat-v2', { waitUntil: 'networkidle', timeout: 20000 });
  } catch (e) {
    console.log('Initial load warning:', e.message);
  }
  await page.waitForTimeout(8000);

  // Step 2: Check for error
  let bodyText = await page.textContent('body');
  const hasError = bodyText.includes('Something went wrong');
  console.log('Error visible:', hasError);

  if (hasError) {
    console.log('Error text found in page. Extracting error details...');
    const errorText = bodyText.match(/useAgent.*?\./) || bodyText.match(/Something went wrong.*?\./);
    if (errorText) console.log('Error detail:', errorText[0]);

    // Try clicking "Try Again"
    console.log('Clicking Try Again button...');
    const tryAgainBtn = await page.$('button:has-text("Try Again")');
    if (tryAgainBtn) {
      await tryAgainBtn.click();
      await page.waitForTimeout(10000);
      bodyText = await page.textContent('body');
      console.log('After Try Again - Error visible:', bodyText.includes('Something went wrong'));
    }
  }

  // Step 3: Screenshot
  await page.screenshot({ path: 'C:/Users/blackga/Desktop/eagle/sm_eagle/screenshots/validate-chat-v2-final-initial.png', fullPage: false });
  console.log('Initial screenshot saved.');

  // Report
  bodyText = await page.textContent('body');
  console.log('--- Page Load Report ---');
  console.log('EAGLE header present:', bodyText.includes('EAGLE'));
  console.log('CopilotKit/AG-UI badge present:', bodyText.includes('CopilotKit') || bodyText.includes('AG-UI'));
  console.log('Events panel present:', bodyText.includes('AG-UI Events') || bodyText.includes('Events'));
  console.log('Error visible:', bodyText.includes('Something went wrong'));

  if (!bodyText.includes('Something went wrong')) {
    // Step 5: Chat test
    console.log('Looking for chat input...');
    const selectors = ['textarea', 'input[type="text"]', '[role="textbox"]', 'input[placeholder]'];
    let inputEl = null;
    for (const sel of selectors) {
      const el = await page.$(sel);
      if (el) {
        inputEl = el;
        console.log('Found input with selector:', sel);
        break;
      }
    }

    if (inputEl) {
      await inputEl.click();
      await inputEl.fill('What is EAGLE?');
      console.log('Typed message. Sending...');
      await page.keyboard.press('Enter');
      console.log('Pressed Enter. Waiting 30 seconds...');
      await page.waitForTimeout(30000);

      await page.screenshot({ path: 'C:/Users/blackga/Desktop/eagle/sm_eagle/screenshots/validate-chat-v2-final-events.png', fullPage: false });
      console.log('Events screenshot saved.');

      const afterText = await page.textContent('body');
      const hasResponse = afterText.length > bodyText.length + 50;
      const eventBadges = await page.$$('[class*="badge"], [class*="event"], [class*="Event"]');
      console.log('--- Chat Response Report ---');
      console.log('Response streamed:', hasResponse);
      console.log('Event badge elements found:', eventBadges.length);

      const eventMatches = afterText.match(/RUN_STARTED|TEXT_MESSAGE|TOOL_CALL|STATE_SNAPSHOT|RUN_FINISHED|STEP_STARTED|STEP_FINISHED/g);
      if (eventMatches) {
        console.log('AG-UI event types:', [...new Set(eventMatches)].join(', '));
        console.log('Total AG-UI events:', eventMatches.length);
      } else {
        console.log('No AG-UI event types found in page text');
      }
    } else {
      console.log('ERROR: Could not find chat input element');
    }
  }

  await browser.close();
  console.log('Done.');
})().catch(e => { console.error('FATAL:', e.message); process.exit(1); });
