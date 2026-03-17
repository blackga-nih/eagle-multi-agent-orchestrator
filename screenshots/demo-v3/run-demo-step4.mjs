/**
 * EAGLE Demo V3 - Step 4 continuation
 * Re-opens the existing session and sends the SOW generation request.
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
        const messages = document.querySelectorAll('[class*="message"], [class*="Message"], [data-role="assistant"]');
        let total = 0;
        messages.forEach(m => total += m.textContent.length);
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
    console.log(`  Wait completed: ${e.message}`);
  }
  await page.waitForTimeout(2000);
  console.log(`  Total wait: ${((Date.now() - start) / 1000).toFixed(1)}s`);
}

(async () => {
  console.log('=== EAGLE Demo V3 - Step 4 Continuation ===\n');

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
    // Navigate to chat page
    console.log('Navigating to chat page...');
    await page.goto(`${BASE_URL}/chat`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(3000);

    // Click on the existing session in the left sidebar
    const sessionLink = page.locator('text=Session 3/17/2026').first();
    const sessionExists = await sessionLink.count();
    if (sessionExists > 0) {
      console.log('  Found existing session - clicking it');
      await sessionLink.click();
      await page.waitForTimeout(3000);
    } else {
      console.log('  No existing session found - looking for most recent chat');
      // Try clicking first conversation in sidebar
      const firstConvo = page.locator('.cursor-pointer, [class*="conversation"], [class*="session"]').first();
      if (await firstConvo.count() > 0) {
        await firstConvo.click();
        await page.waitForTimeout(3000);
      }
    }

    // Take a screenshot showing current state with right panel visible
    await screenshot(page, 'step4-pre-state.png');

    // Now scroll down in chat to see the conversation so far
    await page.evaluate(() => {
      const containers = document.querySelectorAll('[class*="scroll"], [class*="chat"], main');
      containers.forEach(c => {
        if (c.scrollHeight > c.clientHeight) {
          c.scrollTop = c.scrollHeight;
        }
      });
    });
    await page.waitForTimeout(1000);

    // First, let's capture the right panel state BEFORE sending SOW
    // The right-panel Package tab is in the area on the right side
    // Take a screenshot focused on the right panel
    console.log('\n  Capturing right panel state before SOW generation...');

    // Click the Package tab in the RIGHT PANEL (not the top nav)
    // The right panel tabs are the ones that say "Package", "Docs", "Alerts", "Activity"
    // These are small tabs in the upper-right area of the chat view
    const rightPanelPackageTab = page.locator('[class*="right"] button:has-text("Package"), [class*="panel"] button:has-text("Package")').first();
    const rightTabExists = await rightPanelPackageTab.count();
    if (rightTabExists > 0) {
      console.log('  Found right panel Package tab');
      await rightPanelPackageTab.click();
      await page.waitForTimeout(1000);
    }

    await screenshot(page, 'step4-right-panel-before.png');

    // Now send the SOW generation message
    console.log('\nSTEP 4: Generate Statement of Work');
    const textarea = page.locator('textarea').first();
    await textarea.waitFor({ state: 'visible', timeout: 10000 });
    await textarea.click();
    await textarea.fill('Generate the Statement of Work');
    await page.waitForTimeout(500);

    // Find and click the send button (the arrow button)
    const sendButton = page.locator('button[type="submit"]').first();
    const sendExists = await sendButton.count();
    if (sendExists > 0) {
      await sendButton.click();
    } else {
      await textarea.press('Enter');
    }
    console.log('  Message sent: "Generate the Statement of Work"');

    // Wait for response
    await waitForResponseComplete(page, 90000);

    // Screenshot the response
    await screenshot(page, 'step4-response.png');

    // Scroll to bottom of chat
    await page.evaluate(() => {
      const containers = document.querySelectorAll('[class*="scroll"], [class*="chat"], main');
      containers.forEach(c => {
        if (c.scrollHeight > c.clientHeight) {
          c.scrollTop = c.scrollHeight;
        }
      });
    });
    await page.waitForTimeout(1000);
    await screenshot(page, 'step4-response-bottom.png');

    // Now check the right panel
    console.log('\n  Checking right panel after SOW generation...');

    // Read what the right panel shows
    const rightPanelContent = await page.evaluate(() => {
      // The right panel area is roughly the right 300px of the viewport
      const allElements = document.querySelectorAll('*');
      let rightContent = '';
      for (const el of allElements) {
        const rect = el.getBoundingClientRect();
        if (rect.x > 1100 && rect.width > 50 && rect.width < 400 && el.textContent.trim().length > 0 && el.children.length < 3) {
          rightContent += el.textContent.trim() + '\n';
        }
      }
      return rightContent;
    });
    console.log(`  Right panel text:\n${rightPanelContent.substring(0, 800)}`);

    await screenshot(page, 'step4-right-panel.png');

    // Also scroll within the right panel to see if there's a checklist below
    await page.evaluate(() => {
      const panels = document.querySelectorAll('[class*="panel"], [class*="sidebar"], aside');
      panels.forEach(p => {
        const rect = p.getBoundingClientRect();
        if (rect.x > 800) {
          p.scrollTop = p.scrollHeight;
        }
      });
    });
    await page.waitForTimeout(500);
    await screenshot(page, 'step4-right-panel-scrolled.png');

    console.log('\n=== Step 4 Complete ===');

  } catch (err) {
    console.error('ERROR:', err.message);
    await screenshot(page, 'step4-error.png');
  } finally {
    await browser.close();
    console.log('Done.');
  }
})();
