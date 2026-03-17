import { chromium } from 'playwright';

const SCREENSHOT_DIR = 'C:/Users/blackga/Desktop/eagle/eagle-multi-agent-orchestrator/screenshots/demo-transcript';
const BASE_URL = 'http://localhost:3000';

async function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  // Collect console errors
  const consoleErrors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });

  try {
    // ===== STEP 0: Navigate and handle login =====
    console.log('--- STEP 0: Navigate to app and handle login ---');
    await page.goto(BASE_URL, { waitUntil: 'networkidle', timeout: 30000 });
    await sleep(3000);

    let currentUrl = page.url();
    console.log(`Current URL after navigation: ${currentUrl}`);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/00-initial-load.png`, fullPage: true });

    // Check if we're on a login page
    const loginForm = await page.$('input[type="email"], input[type="password"], input[name="email"]');
    if (loginForm || currentUrl.includes('/login')) {
      console.log('Login page detected. Looking for demo credentials...');
      await page.screenshot({ path: `${SCREENSHOT_DIR}/00a-login-page.png`, fullPage: true });

      // Try demo credentials from the smoke test docs
      const emailInput = await page.$('input[type="email"], input[name="email"], input[placeholder*="email" i], input[placeholder*="nih.gov" i]');
      const passwordInput = await page.$('input[type="password"], input[name="password"]');

      if (emailInput && passwordInput) {
        // Try testuser@example.com first (from login test doc)
        console.log('Trying testuser@example.com / EagleTest2024!');
        await emailInput.fill('testuser@example.com');
        await passwordInput.fill('EagleTest2024!');
        await page.screenshot({ path: `${SCREENSHOT_DIR}/00b-login-filled.png`, fullPage: true });

        // Click sign in
        const signInBtn = await page.$('button:has-text("Sign in"), button[type="submit"]');
        if (signInBtn) {
          await signInBtn.click();
          await sleep(5000);
          currentUrl = page.url();
          console.log(`URL after login attempt: ${currentUrl}`);

          // If still on login, try dev@example.com
          if (currentUrl.includes('/login')) {
            console.log('First login failed, trying dev@example.com / Password123!');
            await emailInput.fill('dev@example.com');
            await passwordInput.fill('Password123!');
            await signInBtn.click();
            await sleep(5000);
            currentUrl = page.url();
            console.log(`URL after second login attempt: ${currentUrl}`);
          }

          // If still on login, try demo@example.com
          if (currentUrl.includes('/login')) {
            console.log('Second login failed, trying demo@example.com / demo');
            await emailInput.fill('demo@example.com');
            await passwordInput.fill('demo');
            await signInBtn.click();
            await sleep(5000);
            currentUrl = page.url();
            console.log(`URL after third login attempt: ${currentUrl}`);
          }
        }
      }

      // Last resort: try navigating directly to /chat (dev mode may auto-auth)
      if (page.url().includes('/login')) {
        console.log('Login attempts exhausted. Trying direct navigation to /chat...');
        await page.goto(`${BASE_URL}/chat`, { waitUntil: 'networkidle', timeout: 15000 });
        await sleep(3000);
        currentUrl = page.url();
        console.log(`URL after direct /chat navigation: ${currentUrl}`);
      }
    }

    await page.screenshot({ path: `${SCREENSHOT_DIR}/00c-post-login.png`, fullPage: true });
    console.log(`Post-login URL: ${page.url()}`);

    // ===== STEP 1: Open Chat =====
    console.log('\n--- STEP 1: Open Chat ---');

    // Navigate to chat if not already there
    if (!page.url().includes('/chat')) {
      // Look for a Chat card or link
      const chatLink = await page.$('a[href*="/chat"], a:has-text("Chat"), [data-testid="chat-link"]');
      if (chatLink) {
        await chatLink.click();
        await sleep(3000);
      } else {
        await page.goto(`${BASE_URL}/chat`, { waitUntil: 'networkidle', timeout: 15000 });
        await sleep(3000);
      }
    }

    console.log(`Chat page URL: ${page.url()}`);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/01-chat-initial.png`, fullPage: true });

    // Look for New Chat button and click it
    const newChatBtn = await page.$('button:has-text("New Chat"), button:has-text("New"), [data-testid="new-chat"]');
    if (newChatBtn) {
      console.log('Clicking New Chat button...');
      await newChatBtn.click();
      await sleep(2000);
      await page.screenshot({ path: `${SCREENSHOT_DIR}/01a-new-chat.png`, fullPage: true });
    } else {
      console.log('No New Chat button found, proceeding with current state');
    }

    // ===== STEP 2: Send first message (Acquisition Intake) =====
    console.log('\n--- STEP 2: Send first message (Acquisition Intake) ---');

    const msg1 = 'I need to procure cloud hosting services for our research data platform. Estimated value around $750,000.';

    // Find the chat input - try multiple selectors
    let chatInput = await page.$('textarea[placeholder*="Message" i], textarea[placeholder*="Type" i], textarea, input[placeholder*="Message" i], [contenteditable="true"]');
    if (!chatInput) {
      // Try broader search
      chatInput = await page.$('textarea');
    }

    if (!chatInput) {
      console.log('ERROR: Could not find chat input!');
      // Take a diagnostic screenshot
      await page.screenshot({ path: `${SCREENSHOT_DIR}/02-ERROR-no-input.png`, fullPage: true });
      // Log visible elements for debugging
      const textareas = await page.$$('textarea');
      const inputs = await page.$$('input[type="text"]');
      console.log(`Found ${textareas.length} textareas and ${inputs.length} text inputs on page`);
      const bodyText = await page.textContent('body');
      console.log(`Page body snippet: ${bodyText.substring(0, 500)}`);
    } else {
      console.log('Found chat input, typing message...');
      await chatInput.click();
      await chatInput.fill(msg1);
      await sleep(1000);
      await page.screenshot({ path: `${SCREENSHOT_DIR}/02a-message-typed.png`, fullPage: true });

      // Send the message
      console.log('Sending message...');
      // Try pressing Enter
      await chatInput.press('Enter');
      await sleep(2000);

      // Check if message was sent (look for user message bubble)
      const userMessages = await page.$$('[class*="user" i], [data-role="user"]');
      if (userMessages.length === 0) {
        // Maybe need to click a send button instead
        const sendBtn = await page.$('button[type="submit"], button:has-text("Send"), button[aria-label*="send" i], button svg[class*="send" i]');
        if (sendBtn) {
          console.log('Enter did not send, clicking send button...');
          // Retype the message since Enter might have added a newline
          await chatInput.fill(msg1);
          await sendBtn.click();
        }
      }

      // Wait for response to stream in
      console.log('Waiting 35 seconds for response to stream in...');
      await sleep(35000);

      await page.screenshot({ path: `${SCREENSHOT_DIR}/02b-response-step2.png`, fullPage: true });

      // Scroll down to see full response
      const chatArea = await page.$('[class*="chat" i][class*="area" i], [class*="message" i][class*="list" i], [class*="messages" i], main, [role="main"]');
      if (chatArea) {
        await chatArea.evaluate(el => el.scrollTop = el.scrollHeight);
        await sleep(1000);
      } else {
        await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
        await sleep(1000);
      }
      await page.screenshot({ path: `${SCREENSHOT_DIR}/02c-response-step2-scrolled.png`, fullPage: true });

      // Grab response text for summary
      const responseText = await page.evaluate(() => {
        const messages = document.querySelectorAll('[class*="assistant" i], [class*="ai-message" i], [data-role="assistant"], [class*="message-content" i]');
        return Array.from(messages).map(m => m.textContent.trim().substring(0, 200)).join(' | ');
      });
      console.log(`Step 2 response preview: ${responseText.substring(0, 500)}`);
    }

    // ===== STEP 3: Send second message (Clarifying Answers) =====
    console.log('\n--- STEP 3: Send second message (Clarifying Answers) ---');

    const msg2 = '3-year base period plus 2 option years, starting October 2026. No existing vehicles — new standalone contract. We need FedRAMP High for PII and genomics research data. Full and open competition preferred. Fixed-price.';

    // Re-find the chat input (it may have moved after first message)
    chatInput = await page.$('textarea:not([disabled]), input[type="text"]:not([disabled]), [contenteditable="true"]');
    if (!chatInput) {
      chatInput = await page.$('textarea');
    }

    if (chatInput) {
      console.log('Typing second message...');
      await chatInput.click();
      await chatInput.fill(msg2);
      await sleep(500);

      // Send
      await chatInput.press('Enter');
      await sleep(2000);

      // Check if sent, try send button as fallback
      const inputVal = await chatInput.inputValue().catch(() => '');
      if (inputVal === msg2) {
        const sendBtn = await page.$('button[type="submit"], button:has-text("Send"), button[aria-label*="send" i]');
        if (sendBtn) {
          await sendBtn.click();
        }
      }

      console.log('Waiting 50 seconds for response to stream in (may create packages/checklists)...');
      await sleep(50000);

      await page.screenshot({ path: `${SCREENSHOT_DIR}/03a-response-step3.png`, fullPage: true });

      // Scroll down
      const chatArea2 = await page.$('[class*="messages" i], main, [role="main"]');
      if (chatArea2) {
        await chatArea2.evaluate(el => el.scrollTop = el.scrollHeight);
        await sleep(1000);
      } else {
        await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
        await sleep(1000);
      }
      await page.screenshot({ path: `${SCREENSHOT_DIR}/03b-response-step3-scrolled.png`, fullPage: true });

      // Grab response
      const responseText2 = await page.evaluate(() => {
        const messages = document.querySelectorAll('[class*="assistant" i], [class*="ai-message" i], [data-role="assistant"], [class*="message-content" i]');
        const lastMsg = messages[messages.length - 1];
        return lastMsg ? lastMsg.textContent.trim().substring(0, 500) : 'No assistant message found';
      });
      console.log(`Step 3 response preview: ${responseText2.substring(0, 500)}`);
    } else {
      console.log('ERROR: Could not find chat input for step 3!');
      await page.screenshot({ path: `${SCREENSHOT_DIR}/03-ERROR-no-input.png`, fullPage: true });
    }

    // ===== STEP 4: Send third message (Document Generation) =====
    console.log('\n--- STEP 4: Send third message (Document Generation) ---');

    const msg3 = 'Generate the Statement of Work';

    chatInput = await page.$('textarea:not([disabled]), input[type="text"]:not([disabled]), [contenteditable="true"]');
    if (!chatInput) {
      chatInput = await page.$('textarea');
    }

    if (chatInput) {
      console.log('Typing third message...');
      await chatInput.click();
      await chatInput.fill(msg3);
      await sleep(500);

      // Send
      await chatInput.press('Enter');
      await sleep(2000);

      // Check if sent, try send button as fallback
      const inputVal = await chatInput.inputValue().catch(() => '');
      if (inputVal === msg3) {
        const sendBtn = await page.$('button[type="submit"], button:has-text("Send"), button[aria-label*="send" i]');
        if (sendBtn) {
          await sendBtn.click();
        }
      }

      console.log('Waiting 50 seconds for document generation response...');
      await sleep(50000);

      await page.screenshot({ path: `${SCREENSHOT_DIR}/04a-response-step4.png`, fullPage: true });

      // Scroll down
      const chatArea3 = await page.$('[class*="messages" i], main, [role="main"]');
      if (chatArea3) {
        await chatArea3.evaluate(el => el.scrollTop = el.scrollHeight);
        await sleep(1000);
      } else {
        await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
        await sleep(1000);
      }
      await page.screenshot({ path: `${SCREENSHOT_DIR}/04b-response-step4-scrolled.png`, fullPage: true });

      // Grab response
      const responseText3 = await page.evaluate(() => {
        const messages = document.querySelectorAll('[class*="assistant" i], [class*="ai-message" i], [data-role="assistant"], [class*="message-content" i]');
        const lastMsg = messages[messages.length - 1];
        return lastMsg ? lastMsg.textContent.trim().substring(0, 800) : 'No assistant message found';
      });
      console.log(`Step 4 response preview: ${responseText3.substring(0, 800)}`);
    } else {
      console.log('ERROR: Could not find chat input for step 4!');
      await page.screenshot({ path: `${SCREENSHOT_DIR}/04-ERROR-no-input.png`, fullPage: true });
    }

    // ===== Final: Grab all message content for summary =====
    console.log('\n--- FINAL: Collecting all messages ---');
    const allMessages = await page.evaluate(() => {
      // Try to get all messages with role indicators
      const allElements = document.querySelectorAll('[data-role], [class*="message" i]');
      const results = [];
      allElements.forEach(el => {
        const role = el.getAttribute('data-role') ||
                     (el.className.match(/user/i) ? 'user' :
                      el.className.match(/assistant|ai/i) ? 'assistant' : 'unknown');
        const text = el.textContent.trim().substring(0, 300);
        if (text.length > 10) {
          results.push({ role, text });
        }
      });
      return results;
    });
    console.log(`Total message elements found: ${allMessages.length}`);
    allMessages.forEach((m, i) => {
      console.log(`  [${i}] ${m.role}: ${m.text.substring(0, 150)}...`);
    });

    // Take a final full-page screenshot
    await page.screenshot({ path: `${SCREENSHOT_DIR}/05-final-state.png`, fullPage: true });

    if (consoleErrors.length > 0) {
      console.log('\n--- Console Errors ---');
      consoleErrors.forEach(e => console.log(`  ERROR: ${e}`));
    }

    console.log('\n--- DONE ---');

  } catch (error) {
    console.error(`Script error: ${error.message}`);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/ERROR-crash.png`, fullPage: true }).catch(() => {});
  } finally {
    await browser.close();
  }
}

main();
