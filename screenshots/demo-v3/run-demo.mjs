/**
 * EAGLE Demo V3 - Browser automation script
 * Runs the 3-step intake demo transcript and captures screenshots.
 * Usage: npx playwright test --config=... or node --experimental-modules run-demo.mjs
 */
import { chromium } from 'playwright';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SCREENSHOT_DIR = __dirname;
const BASE_URL = 'http://localhost:3000';

async function screenshot(page, name) {
  const filePath = path.join(SCREENSHOT_DIR, name);
  await page.screenshot({ path: filePath, fullPage: false });
  console.log(`  [screenshot] ${name}`);
}

async function screenshotFullPage(page, name) {
  const filePath = path.join(SCREENSHOT_DIR, name);
  await page.screenshot({ path: filePath, fullPage: true });
  console.log(`  [screenshot-full] ${name}`);
}

async function waitForResponseComplete(page, timeoutMs) {
  console.log(`  Waiting up to ${timeoutMs / 1000}s for response to complete...`);
  const start = Date.now();

  // Wait for SSE streaming to finish - look for the response to stabilize
  // Strategy: wait for the send button to become enabled again (not loading)
  // or wait for the specified timeout
  try {
    // Wait for any loading indicator to appear first (give it 5s)
    await page.waitForTimeout(5000);

    // Now poll until the response seems done (textarea is enabled / send button is ready)
    // or until timeout
    const pollInterval = 3000;
    let lastTextLength = 0;
    let stableCount = 0;

    while (Date.now() - start < timeoutMs) {
      // Check if there's a loading/streaming indicator
      const isStreaming = await page.evaluate(() => {
        // Look for common streaming indicators
        const stopBtn = document.querySelector('[aria-label="Stop generating"]');
        const loadingDots = document.querySelector('.animate-pulse, .animate-bounce');
        return !!(stopBtn || loadingDots);
      }).catch(() => false);

      // Also check message content length for stability
      const currentTextLength = await page.evaluate(() => {
        const messages = document.querySelectorAll('[class*="message"], [class*="Message"], [data-role="assistant"]');
        let total = 0;
        messages.forEach(m => total += m.textContent.length);
        return total;
      }).catch(() => 0);

      if (!isStreaming && currentTextLength > 0 && currentTextLength === lastTextLength) {
        stableCount++;
        if (stableCount >= 3) {
          console.log(`  Response stabilized after ${((Date.now() - start) / 1000).toFixed(1)}s`);
          break;
        }
      } else {
        stableCount = 0;
      }
      lastTextLength = currentTextLength;
      await page.waitForTimeout(pollInterval);
    }
  } catch (e) {
    console.log(`  Wait completed (${((Date.now() - start) / 1000).toFixed(1)}s): ${e.message}`);
  }

  // Extra buffer for any final rendering
  await page.waitForTimeout(2000);
  console.log(`  Total wait: ${((Date.now() - start) / 1000).toFixed(1)}s`);
}

async function typeAndSend(page, message) {
  // Find the chat input textarea
  const textarea = page.locator('textarea').first();
  await textarea.waitFor({ state: 'visible', timeout: 10000 });
  await textarea.click();
  await textarea.fill(message);
  await page.waitForTimeout(500);

  // Try pressing Enter to send, or find and click the send button
  // Check if there's a send button
  const sendButton = page.locator('button[type="submit"], button[aria-label="Send message"], button[aria-label="Send"]').first();
  const sendExists = await sendButton.count();
  if (sendExists > 0) {
    await sendButton.click();
  } else {
    // Try keyboard shortcut
    await textarea.press('Enter');
  }
  console.log(`  Message sent: "${message.substring(0, 60)}..."`);
}

(async () => {
  console.log('=== EAGLE Demo V3 - Browser Automation ===\n');

  const browser = await chromium.launch({
    headless: false,  // Use headed mode so we can see what's happening
    args: ['--window-size=1920,1080']
  });

  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    ignoreHTTPSErrors: true,
  });

  const page = await context.newPage();

  try {
    // ============================================
    // STEP 1: Navigate to chat and start fresh
    // ============================================
    console.log('STEP 1: Navigate to chat page');
    await page.goto(`${BASE_URL}/chat`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(3000);

    // Look for "New Chat" button and click it
    const newChatBtn = page.locator('button:has-text("New Chat"), button:has-text("New chat"), a:has-text("New Chat"), [aria-label*="new chat" i], [aria-label*="New Chat"]').first();
    const newChatExists = await newChatBtn.count();
    if (newChatExists > 0) {
      console.log('  Clicking "New Chat" button');
      await newChatBtn.click();
      await page.waitForTimeout(2000);
    } else {
      console.log('  No "New Chat" button found - may already be on fresh chat');
    }

    await screenshot(page, 'step0-new-chat.png');

    // ============================================
    // STEP 2: Send intake message
    // ============================================
    console.log('\nSTEP 2: Send intake message');
    const intakeMsg = 'I need to procure cloud hosting services for our research data platform. Estimated value around $750,000.';
    await typeAndSend(page, intakeMsg);
    await waitForResponseComplete(page, 60000);
    await screenshot(page, 'step2-response.png');

    // ============================================
    // STEP 3: Answer clarifying questions
    // ============================================
    console.log('\nSTEP 3: Answer clarifying questions');
    const clarifyMsg = '3-year base period plus 2 option years, starting October 2026. No existing vehicles \u2014 new standalone contract. We need FedRAMP High for PII and genomics research data. Full and open competition preferred. Fixed-price.';
    await typeAndSend(page, clarifyMsg);
    await waitForResponseComplete(page, 90000);
    await screenshot(page, 'step3-response.png');

    // Scroll down to see more of the response
    await page.evaluate(() => {
      const chatContainer = document.querySelector('[class*="chat"], [class*="messages"], main, [role="main"]');
      if (chatContainer) {
        chatContainer.scrollTop = chatContainer.scrollHeight;
      } else {
        window.scrollTo(0, document.body.scrollHeight);
      }
    });
    await page.waitForTimeout(1000);
    await screenshot(page, 'step3-response-bottom.png');

    // Check the right panel - Package tab
    console.log('\n  Checking right panel (Package tab)...');

    // Try to find and click the Package tab
    const packageTab = page.locator('button:has-text("Package"), [role="tab"]:has-text("Package"), a:has-text("Package")').first();
    const packageTabExists = await packageTab.count();
    if (packageTabExists > 0) {
      console.log('  Found Package tab - clicking it');
      await packageTab.click();
      await page.waitForTimeout(2000);
    } else {
      console.log('  No explicit Package tab found - checking if panel is already visible');
    }

    await screenshot(page, 'step3-right-panel.png');

    // Check what the right panel says
    const rightPanelText = await page.evaluate(() => {
      // Look for the right panel content
      const panels = document.querySelectorAll('[class*="panel"], [class*="sidebar"], [class*="aside"], aside');
      let text = '';
      panels.forEach(p => {
        if (p.getBoundingClientRect().x > 500) { // right side of the screen
          text += p.textContent + '\n';
        }
      });
      return text;
    });
    console.log(`  Right panel content (first 500 chars): ${rightPanelText.substring(0, 500)}`);

    if (rightPanelText.includes('No active package') || rightPanelText.includes('no active package')) {
      console.log('  WARNING: Right panel still shows "No active package yet"');
    } else if (rightPanelText.includes('phase') || rightPanelText.includes('Phase') || rightPanelText.includes('progress') || rightPanelText.includes('checklist') || rightPanelText.includes('SOW') || rightPanelText.includes('IGCE')) {
      console.log('  SUCCESS: Right panel appears to show package data!');
    }

    // ============================================
    // STEP 4: Generate SOW
    // ============================================
    console.log('\nSTEP 4: Generate Statement of Work');
    const sowMsg = 'Generate the Statement of Work';
    await typeAndSend(page, sowMsg);
    await waitForResponseComplete(page, 90000);
    await screenshot(page, 'step4-response.png');

    // Check right panel again
    if (packageTabExists > 0) {
      await packageTab.click();
      await page.waitForTimeout(2000);
    }
    await screenshot(page, 'step4-right-panel.png');

    const rightPanelTextAfterSOW = await page.evaluate(() => {
      const panels = document.querySelectorAll('[class*="panel"], [class*="sidebar"], [class*="aside"], aside');
      let text = '';
      panels.forEach(p => {
        if (p.getBoundingClientRect().x > 500) {
          text += p.textContent + '\n';
        }
      });
      return text;
    });
    console.log(`  Right panel after SOW (first 500 chars): ${rightPanelTextAfterSOW.substring(0, 500)}`);

    // ============================================
    // FINAL REPORT
    // ============================================
    console.log('\n=== DEMO V3 REPORT ===');
    console.log(`1. Right panel after step 3: ${rightPanelText.includes('No active package') ? 'Still shows "No active package"' : 'Shows package data'}`);
    console.log(`2. Package tab content: ${rightPanelText.substring(0, 200)}`);
    console.log(`3. Right panel after SOW: ${rightPanelTextAfterSOW.substring(0, 200)}`);
    console.log('4. Screenshots saved to: ' + SCREENSHOT_DIR);

  } catch (err) {
    console.error('ERROR:', err.message);
    await screenshot(page, 'error-state.png');
  } finally {
    await browser.close();
    console.log('\nDone.');
  }
})();
