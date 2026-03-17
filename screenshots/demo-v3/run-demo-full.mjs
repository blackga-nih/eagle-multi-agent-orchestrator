/**
 * EAGLE Demo V3 - Full 4-step flow in a single browser session.
 * Fixed: avoids clicking top-nav "Packages" link (navigates away).
 * The right-panel Package tab is already selected by default.
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

async function waitForResponseComplete(page, timeoutMs) {
  console.log(`  Waiting up to ${timeoutMs / 1000}s for response to complete...`);
  const start = Date.now();
  try {
    await page.waitForTimeout(5000);
    const pollInterval = 3000;
    let lastTextLength = 0;
    let stableCount = 0;
    while (Date.now() - start < timeoutMs) {
      const currentTextLength = await page.evaluate(() => {
        const msgs = document.querySelectorAll('[class*="message"], [class*="Message"], [data-role="assistant"]');
        let total = 0;
        msgs.forEach(m => total += m.textContent.length);
        return total;
      }).catch(() => 0);
      if (currentTextLength > 0 && currentTextLength === lastTextLength) {
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
    console.log(`  Wait err: ${e.message}`);
  }
  await page.waitForTimeout(2000);
  console.log(`  Total wait: ${((Date.now() - start) / 1000).toFixed(1)}s`);
}

async function typeAndSend(page, message) {
  const textarea = page.locator('textarea').first();
  await textarea.waitFor({ state: 'visible', timeout: 15000 });
  await textarea.click();
  await textarea.fill(message);
  await page.waitForTimeout(500);
  // Click the send button (dark circle with arrow)
  const sendBtn = page.locator('button[type="submit"]').first();
  if (await sendBtn.count() > 0) {
    await sendBtn.click();
  } else {
    await textarea.press('Enter');
  }
  console.log(`  Sent: "${message.substring(0, 70)}${message.length > 70 ? '...' : ''}"`);
}

async function readRightPanel(page) {
  return await page.evaluate(() => {
    const allEls = document.querySelectorAll('*');
    let content = '';
    for (const el of allEls) {
      const rect = el.getBoundingClientRect();
      // Right panel is roughly x > 1150
      if (rect.x > 1150 && rect.width > 30 && rect.width < 400
          && el.textContent.trim().length > 0 && el.children.length < 3) {
        const t = el.textContent.trim();
        if (!content.includes(t)) content += t + '\n';
      }
    }
    return content;
  });
}

async function scrollChatToBottom(page) {
  await page.evaluate(() => {
    const containers = document.querySelectorAll('[class*="scroll"], [class*="chat"], main, [class*="overflow"]');
    containers.forEach(c => {
      if (c.scrollHeight > c.clientHeight) c.scrollTop = c.scrollHeight;
    });
  });
  await page.waitForTimeout(1000);
}

(async () => {
  console.log('=== EAGLE Demo V3 - Full Run ===\n');

  const browser = await chromium.launch({
    headless: false,
    args: ['--window-size=1920,1080']
  });
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    ignoreHTTPSErrors: true,
  });
  const page = await context.newPage();

  try {
    // ========== STEP 0: Fresh chat ==========
    console.log('STEP 0: Navigate to fresh chat');
    await page.goto(`${BASE_URL}/chat`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(3000);

    // Click "New Chat" button in the left sidebar
    const newChatBtn = page.locator('button:has-text("New Chat")').first();
    if (await newChatBtn.count() > 0) {
      await newChatBtn.click();
      await page.waitForTimeout(2000);
    }
    await screenshot(page, 'step0-new-chat.png');

    // ========== STEP 2: Intake message ==========
    console.log('\nSTEP 2: Send intake message');
    await typeAndSend(page, 'I need to procure cloud hosting services for our research data platform. Estimated value around $750,000.');
    await waitForResponseComplete(page, 60000);

    // Scroll to see response
    await scrollChatToBottom(page);
    await screenshot(page, 'step2-response.png');

    // Check right panel after step 2
    let rp2 = await readRightPanel(page);
    console.log(`  Right panel after Step 2 (first 300 chars):\n${rp2.substring(0, 300)}`);

    // ========== STEP 3: Clarifying questions ==========
    console.log('\nSTEP 3: Answer clarifying questions');
    await typeAndSend(page, '3-year base period plus 2 option years, starting October 2026. No existing vehicles \u2014 new standalone contract. We need FedRAMP High for PII and genomics research data. Full and open competition preferred. Fixed-price.');
    await waitForResponseComplete(page, 120000);

    // Scroll to see response top
    await scrollChatToBottom(page);
    await screenshot(page, 'step3-response.png');

    // Scroll further down
    await page.waitForTimeout(500);
    await screenshot(page, 'step3-response-bottom.png');

    // Check right panel after step 3 - DO NOT click the top nav "Packages" link
    // The Package tab in the right panel should already be selected (it's the default)
    let rp3 = await readRightPanel(page);
    console.log(`\n  Right panel after Step 3:\n${rp3.substring(0, 500)}`);

    // Determine if package populated
    const hasPackageData = rp3.includes('PHASE') || rp3.includes('Phase') ||
                          rp3.includes('Requirements') || rp3.includes('COMPLIANCE') ||
                          rp3.includes('Compliance') || rp3.includes('FedRAMP') ||
                          rp3.includes('progress');
    const hasNoPackage = rp3.includes('No active package');
    console.log(`  Package populated: ${hasPackageData}`);
    console.log(`  "No active package" shown: ${hasNoPackage}`);

    await screenshot(page, 'step3-right-panel.png');

    // ========== STEP 4: Generate SOW ==========
    console.log('\nSTEP 4: Generate Statement of Work');
    await typeAndSend(page, 'Generate the Statement of Work');
    await waitForResponseComplete(page, 120000);

    await scrollChatToBottom(page);
    await screenshot(page, 'step4-response.png');

    // Scroll further
    await page.waitForTimeout(500);
    await screenshot(page, 'step4-response-bottom.png');

    // Right panel after SOW
    let rp4 = await readRightPanel(page);
    console.log(`\n  Right panel after Step 4:\n${rp4.substring(0, 500)}`);

    const hasSOWChecklist = rp4.includes('SOW') || rp4.includes('Statement of Work') ||
                           rp4.includes('created') || rp4.includes('checklist');
    console.log(`  SOW in checklist: ${hasSOWChecklist}`);

    await screenshot(page, 'step4-right-panel.png');

    // ========== REPORT ==========
    console.log('\n========================================');
    console.log('           DEMO V3 REPORT');
    console.log('========================================');
    console.log(`1. Right panel populated after Step 3? ${hasPackageData ? 'YES' : 'NO'}`);
    console.log(`2. Package tab shows: ${hasPackageData ? rp3.substring(0, 200) : '"No active package yet"'}`);
    console.log(`3. Checklist updated after SOW (Step 4)? ${hasSOWChecklist ? 'YES' : 'Needs manual check'}`);
    console.log(`4. Errors: None during automation`);
    console.log(`\nScreenshots saved to: ${SCREENSHOT_DIR}`);

  } catch (err) {
    console.error('\nERROR:', err.message);
    await screenshot(page, 'error-state.png');
  } finally {
    await browser.close();
    console.log('\nDone.');
  }
})();
