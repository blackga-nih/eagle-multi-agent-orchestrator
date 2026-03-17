import { chromium } from 'playwright';

const SCREENSHOT_DIR = 'C:/Users/blackga/Desktop/eagle/eagle-multi-agent-orchestrator/screenshots/demo-transcript';
const BASE_URL = 'http://localhost:3000';

async function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Wait until the chat textarea is enabled (not disabled and not showing "Waiting for response...")
 * This means the agent has finished streaming its response.
 */
async function waitForResponseComplete(page, timeoutMs = 180000) {
  const startTime = Date.now();
  console.log(`  Waiting for response to complete (timeout: ${timeoutMs/1000}s)...`);

  while (Date.now() - startTime < timeoutMs) {
    const textareaState = await page.evaluate(() => {
      const ta = document.querySelector('textarea');
      if (!ta) return { found: false };
      return {
        found: true,
        disabled: ta.disabled,
        placeholder: ta.placeholder,
        readOnly: ta.readOnly,
      };
    });

    if (textareaState.found && !textareaState.disabled &&
        !textareaState.placeholder.toLowerCase().includes('waiting')) {
      const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
      console.log(`  Response complete after ${elapsed}s`);
      return true;
    }

    await sleep(2000);
  }

  console.log(`  WARNING: Timed out waiting for response after ${timeoutMs/1000}s`);
  return false;
}

async function sendMessage(page, message) {
  // Find enabled textarea
  const chatInput = await page.$('textarea:not([disabled])');
  if (!chatInput) {
    // Maybe it's currently disabled from a previous response, wait a bit
    console.log('  Textarea not found or disabled, waiting...');
    await waitForResponseComplete(page, 60000);
    const retry = await page.$('textarea:not([disabled])');
    if (!retry) {
      console.log('  ERROR: Cannot find enabled textarea');
      return false;
    }
    await retry.click();
    await retry.fill(message);
  } else {
    await chatInput.click();
    await chatInput.fill(message);
  }

  await sleep(500);

  // Press Enter to send
  const ta = await page.$('textarea');
  await ta.press('Enter');
  await sleep(2000);

  // Verify message was sent: check if textarea is now disabled or placeholder changed
  const afterState = await page.evaluate(() => {
    const ta = document.querySelector('textarea');
    return ta ? { disabled: ta.disabled, placeholder: ta.placeholder, value: ta.value } : null;
  });

  if (afterState && !afterState.disabled && afterState.value === message) {
    // Enter may have just added a newline, try send button
    console.log('  Enter did not send, looking for send button...');
    const sendBtn = await page.$('button[type="submit"], button:has([class*="Send" i]), button:last-of-type');
    if (sendBtn) {
      await ta.fill(message);
      // Find the actual send button (the arrow/play button next to textarea)
      const btns = await page.$$('button');
      for (const btn of btns) {
        const ariaLabel = await btn.getAttribute('aria-label');
        const text = await btn.textContent();
        if (ariaLabel?.toLowerCase().includes('send') || text?.includes('Send')) {
          await btn.click();
          break;
        }
      }
    }
    await sleep(2000);
  }

  return true;
}

async function scrollToBottom(page) {
  // Try to scroll the chat messages container to the bottom
  await page.evaluate(() => {
    // Look for scrollable containers
    const candidates = document.querySelectorAll('[class*="overflow"], main, [role="main"]');
    for (const el of candidates) {
      if (el.scrollHeight > el.clientHeight) {
        el.scrollTop = el.scrollHeight;
      }
    }
    // Also try window scroll
    window.scrollTo(0, document.body.scrollHeight);
  });
  await sleep(1000);
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  const consoleErrors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });

  try {
    // ===== STEP 0: Navigate and handle login =====
    console.log('=== STEP 0: Navigate to app ===');
    await page.goto(BASE_URL, { waitUntil: 'networkidle', timeout: 30000 });
    await sleep(2000);
    console.log(`URL: ${page.url()}`);

    // No login needed in dev mode (confirmed from previous run)
    await page.screenshot({ path: `${SCREENSHOT_DIR}/step0-home.png`, fullPage: true });

    // ===== STEP 1: Open Chat =====
    console.log('\n=== STEP 1: Open Chat ===');
    await page.goto(`${BASE_URL}/chat`, { waitUntil: 'networkidle', timeout: 15000 });
    await sleep(3000);

    // Click New Chat to ensure fresh session
    const newChatBtn = await page.$('button:has-text("New Chat")');
    if (newChatBtn) {
      await newChatBtn.click();
      await sleep(2000);
    }

    await page.screenshot({ path: `${SCREENSHOT_DIR}/step1-chat-initial.png`, fullPage: true });
    console.log('Chat page loaded. Screenshot saved: step1-chat-initial.png');

    // ===== STEP 2: First message (Acquisition Intake) =====
    console.log('\n=== STEP 2: Send first message (Acquisition Intake) ===');
    const msg1 = 'I need to procure cloud hosting services for our research data platform. Estimated value around $750,000.';

    const sent1 = await sendMessage(page, msg1);
    if (!sent1) {
      console.log('FAILED to send message 1');
      await page.screenshot({ path: `${SCREENSHOT_DIR}/step2-ERROR.png`, fullPage: true });
    } else {
      console.log('Message 1 sent. Waiting for response...');
      await waitForResponseComplete(page, 180000);
      await sleep(2000);

      // Take screenshot at top of response
      await page.screenshot({ path: `${SCREENSHOT_DIR}/step2-response-top.png`, fullPage: true });

      // Scroll to bottom to see full response
      await scrollToBottom(page);
      await page.screenshot({ path: `${SCREENSHOT_DIR}/step2-response-bottom.png`, fullPage: true });

      // Capture response text
      const resp1 = await page.evaluate(() => {
        const msgs = document.querySelectorAll('[class*="prose"], [class*="markdown"], [class*="message-content"]');
        return Array.from(msgs).map(m => m.textContent.trim().substring(0, 300)).join('\n---\n');
      });
      console.log(`Response 1 preview:\n${resp1.substring(0, 600)}`);
    }

    // ===== STEP 3: Second message (Clarifying Answers) =====
    console.log('\n=== STEP 3: Send second message (Clarifying Answers) ===');
    const msg2 = '3-year base period plus 2 option years, starting October 2026. No existing vehicles — new standalone contract. We need FedRAMP High for PII and genomics research data. Full and open competition preferred. Fixed-price.';

    const sent2 = await sendMessage(page, msg2);
    if (!sent2) {
      console.log('FAILED to send message 2');
      await page.screenshot({ path: `${SCREENSHOT_DIR}/step3-ERROR.png`, fullPage: true });
    } else {
      console.log('Message 2 sent. Waiting for response...');
      await waitForResponseComplete(page, 180000);
      await sleep(2000);

      await page.screenshot({ path: `${SCREENSHOT_DIR}/step3-response-top.png`, fullPage: true });
      await scrollToBottom(page);
      await page.screenshot({ path: `${SCREENSHOT_DIR}/step3-response-bottom.png`, fullPage: true });

      const resp2 = await page.evaluate(() => {
        const msgs = document.querySelectorAll('[class*="prose"], [class*="markdown"], [class*="message-content"]');
        const lastMsg = msgs[msgs.length - 1];
        return lastMsg ? lastMsg.textContent.trim().substring(0, 600) : 'No response found';
      });
      console.log(`Response 2 preview:\n${resp2.substring(0, 600)}`);
    }

    // ===== STEP 4: Third message (Document Generation) =====
    console.log('\n=== STEP 4: Send third message (Document Generation) ===');
    const msg3 = 'Generate the Statement of Work';

    const sent3 = await sendMessage(page, msg3);
    if (!sent3) {
      console.log('FAILED to send message 3');
      await page.screenshot({ path: `${SCREENSHOT_DIR}/step4-ERROR.png`, fullPage: true });
    } else {
      console.log('Message 3 sent. Waiting for response...');
      await waitForResponseComplete(page, 180000);
      await sleep(2000);

      await page.screenshot({ path: `${SCREENSHOT_DIR}/step4-response-top.png`, fullPage: true });
      await scrollToBottom(page);
      await page.screenshot({ path: `${SCREENSHOT_DIR}/step4-response-bottom.png`, fullPage: true });

      const resp3 = await page.evaluate(() => {
        const msgs = document.querySelectorAll('[class*="prose"], [class*="markdown"], [class*="message-content"]');
        const lastMsg = msgs[msgs.length - 1];
        return lastMsg ? lastMsg.textContent.trim().substring(0, 800) : 'No response found';
      });
      console.log(`Response 3 preview:\n${resp3.substring(0, 800)}`);
    }

    // ===== Check the right panel for package/checklist =====
    console.log('\n=== Checking right panel for package/checklist ===');
    const rightPanelText = await page.evaluate(() => {
      // The right panel has Package, Docs, Alerts, Activity tabs
      const rightPanel = document.querySelector('[class*="right" i], [class*="panel" i], [class*="sidebar" i]');
      // Just get all text from the right side of the page
      const allText = document.body.innerText;
      // Look for checklist-related content
      const lines = allText.split('\n').filter(l =>
        l.match(/package|checklist|SOW|IGCE|market research|acquisition plan|compliance/i)
      );
      return lines.join('\n');
    });
    console.log(`Right panel/checklist content:\n${rightPanelText.substring(0, 500)}`);

    // Final full page screenshot
    await page.screenshot({ path: `${SCREENSHOT_DIR}/step4-final-full.png`, fullPage: true });

    // Report console errors
    if (consoleErrors.length > 0) {
      console.log(`\n=== Console Errors (${consoleErrors.length}) ===`);
      consoleErrors.slice(0, 10).forEach(e => console.log(`  ${e.substring(0, 200)}`));
    } else {
      console.log('\nNo console errors detected.');
    }

    console.log('\n=== DEMO TRANSCRIPT COMPLETE ===');

  } catch (error) {
    console.error(`Script error: ${error.message}`);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/ERROR-crash-v2.png`, fullPage: true }).catch(() => {});
  } finally {
    await browser.close();
  }
}

main();
