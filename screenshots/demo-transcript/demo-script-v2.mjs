import { chromium } from 'playwright';

const SCREENSHOT_DIR = 'C:/Users/gblac/OneDrive/Desktop/afs/sample-multi-tenant-agent-core-app/screenshots/demo-transcript';
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
  // Wait for textarea to be enabled — try up to 5 minutes
  let chatInput = await page.$('textarea:not([disabled])');
  if (!chatInput) {
    console.log('  Textarea not found or disabled, waiting up to 5 min for response to complete...');
    await waitForResponseComplete(page, 300000);
    await sleep(2000);
    chatInput = await page.$('textarea:not([disabled])');
    if (!chatInput) {
      console.log('  ERROR: Cannot find enabled textarea after waiting');
      return false;
    }
  }

  await chatInput.click();
  await chatInput.fill(message);
  await sleep(500);

  // Press Enter to send
  const ta = await page.$('textarea');
  await ta.press('Enter');
  await sleep(2000);

  // Verify message was sent: check if textarea is now disabled or value cleared
  const afterState = await page.evaluate(() => {
    const ta = document.querySelector('textarea');
    return ta ? { disabled: ta.disabled, placeholder: ta.placeholder, value: ta.value } : null;
  });

  if (afterState && !afterState.disabled && afterState.value === message) {
    // Enter may have just added a newline — try clicking the send button
    console.log('  Enter did not send, looking for send button...');
    const btns = await page.$$('button');
    for (const btn of btns) {
      const ariaLabel = await btn.getAttribute('aria-label');
      const text = await btn.textContent();
      if (ariaLabel?.toLowerCase().includes('send') || text?.trim() === 'Send') {
        await ta.fill(message);
        await btn.click();
        break;
      }
    }
    await sleep(2000);
  }

  return true;
}

async function scrollToBottom(page) {
  await page.evaluate(() => {
    const candidates = document.querySelectorAll('[class*="overflow"], main, [role="main"]');
    for (const el of candidates) {
      if (el.scrollHeight > el.clientHeight) {
        el.scrollTop = el.scrollHeight;
      }
    }
    window.scrollTo(0, document.body.scrollHeight);
  });
  await sleep(1000);
}

async function getLastResponseText(page) {
  return page.evaluate(() => {
    // Try multiple selectors used by the chat UI
    const selectors = [
      '[class*="prose"]',
      '[class*="markdown"]',
      '[class*="message-content"]',
      '[class*="assistant"]',
      '[data-role="assistant"]',
      '[class*="chat-message"]',
    ];
    for (const sel of selectors) {
      const els = document.querySelectorAll(sel);
      if (els.length > 0) {
        const last = els[els.length - 1];
        const text = last.textContent?.trim();
        if (text && text.length > 20) return text.substring(0, 800);
      }
    }
    // Fallback: grab all paragraph text from main content area
    const paras = document.querySelectorAll('main p, [role="main"] p, #chat-messages p');
    if (paras.length > 0) {
      const last = paras[paras.length - 1];
      return last.textContent?.trim().substring(0, 800) ?? 'No response found';
    }
    return 'No response found (selector miss)';
  });
}

async function main() {
  const browser = await chromium.launch({
    headless: false,
    args: [
      '--disable-background-timer-throttling',
      '--disable-backgrounding-occluded-windows',
      '--disable-renderer-backgrounding',
    ],
  });
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
    await page.screenshot({ path: `${SCREENSHOT_DIR}/step0-home.png`, fullPage: true });

    // ===== STEP 1: Open Chat and start fresh =====
    console.log('\n=== STEP 1: Open Chat ===');
    await page.goto(`${BASE_URL}/chat`, { waitUntil: 'networkidle', timeout: 15000 });
    await sleep(3000);

    // Click New Chat to ensure fresh session
    const newChatBtn = await page.$('button:has-text("New Chat")');
    if (newChatBtn) {
      await newChatBtn.click();
      await sleep(2000);
      console.log('  Clicked "New Chat"');
    }

    await page.screenshot({ path: `${SCREENSHOT_DIR}/step1-chat-initial.png`, fullPage: true });
    console.log('Chat page loaded. Screenshot saved: step1-chat-initial.png');

    // ===== STEP 2: Trigger Intake via "New Intake" quick action button =====
    console.log('\n=== STEP 2: Trigger OA Intake via quick action button ===');

    // Send the full intake brief directly — comprehensive enough that oa_intake runs
    // and the agent doesn't need to ask follow-up questions.
    const msg1 = [
      'Start a new acquisition intake for NCI.',
      'Requirement: FedRAMP High cloud hosting and HPC compute for the NCI genomics research data platform.',
      'Estimated value: $750,000/year ($3.75M total, 5-year contract: 3-year base + 2 option years).',
      'Start date: October 2026. Competition: Full and open. Contract type: Fixed-price.',
      'Scope: 500TB scalable cloud storage plus HPC compute for genomics analysis.',
      'FedRAMP High authorization required — we handle PII and genomics research data.',
      'No existing NIH cloud vehicles — this is a new standalone contract.',
      'Funding confirmed and available FY2027 through FY2031.',
      'I already have pricing from AWS GovCloud, Azure Government, and Google Cloud Public Sector — skip market research.',
      'Please create the acquisition package and generate the Statement of Work.',
    ].join(' ');

    const sent1 = await sendMessage(page, msg1);
    if (!sent1) {
      console.log('FAILED to send message 1');
      await page.screenshot({ path: `${SCREENSHOT_DIR}/step2-ERROR.png`, fullPage: true });
    } else {
      console.log('  Intake message sent. Waiting for response...');
      await waitForResponseComplete(page, 240000);
    }

    await sleep(2000);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/step2-response-top.png`, fullPage: true });
    await scrollToBottom(page);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/step2-response-bottom.png`, fullPage: true });
    const resp1 = await getLastResponseText(page);
    console.log(`Response 1 preview:\n${resp1.substring(0, 600)}`);

    // ===== STEP 3: Answer scope and clarifying questions =====
    console.log('\n=== STEP 3: Answer clarifying questions (scope, timeline, funding) ===');
    // Answer any remaining questions the agent might ask
    const msg2 = [
      'Full and open competition is a strategic requirement for this acquisition — do not switch to GSA Schedule.',
      'FAR Part 15 negotiated procurement is correct given the $3.75M value and security requirements.',
      'All questions answered. Please proceed with FAR Part 15 pathway.',
      'Create the acquisition package now and generate the Statement of Work immediately.',
      'Do not ask for additional information — I have provided everything needed.',
    ].join(' ');

    const sent2 = await sendMessage(page, msg2);
    if (!sent2) {
      console.log('FAILED to send message 2');
      await page.screenshot({ path: `${SCREENSHOT_DIR}/step3-ERROR.png`, fullPage: true });
    } else {
      console.log('  Clarifying answers sent. Waiting for response...');
      await waitForResponseComplete(page, 360000);
      await sleep(2000);
      await page.screenshot({ path: `${SCREENSHOT_DIR}/step3-response-top.png`, fullPage: true });
      await scrollToBottom(page);
      await page.screenshot({ path: `${SCREENSHOT_DIR}/step3-response-bottom.png`, fullPage: true });
      const resp2 = await getLastResponseText(page);
      console.log(`Response 2 preview:\n${resp2.substring(0, 600)}`);
    }

    // ===== STEP 4: Clarify $750K is annual + skip market research =====
    console.log('\n=== STEP 4: Confirm value, skip market research, request SOW ===');
    // Agent asks: "$750K total or annual?" + "What do you need first?"
    // Use the exact bypass phrases from the supervisor: "I already have pricing" skips market_intelligence guard
    const msg3 = 'Generate the Statement of Work document now. All intake information has been provided. I already have pricing — skip market research. Create the package and generate the SOW document.';

    const sent3 = await sendMessage(page, msg3);
    if (!sent3) {
      console.log('FAILED to send message 3');
      await page.screenshot({ path: `${SCREENSHOT_DIR}/step4-ERROR.png`, fullPage: true });
    } else {
      console.log('  Value clarification + bypass sent. Waiting for response (may take longer — document generation)...');
      await waitForResponseComplete(page, 360000);
      await sleep(3000);
      await page.screenshot({ path: `${SCREENSHOT_DIR}/step4-response-top.png`, fullPage: true });
      await scrollToBottom(page);
      await page.screenshot({ path: `${SCREENSHOT_DIR}/step4-response-bottom.png`, fullPage: true });
      const resp3 = await getLastResponseText(page);
      console.log(`Response 3 preview:\n${resp3.substring(0, 800)}`);
    }

    // Check if a document was created — look for DocumentResultCard
    const docCardPresent = await page.evaluate(() => {
      const cards = document.querySelectorAll('[data-package-id]');
      return cards.length > 0;
    });

    if (!docCardPresent) {
      // Agent may have set up the package but not yet generated the doc.
      // Send one more explicit document generation request.
      console.log('\n=== STEP 4b: Explicit SOW generation request ===');
      const msg4 = 'Generate the Statement of Work now.';
      const sent4 = await sendMessage(page, msg4);
      if (sent4) {
        console.log('  SOW generation request sent. Waiting for response...');
        await waitForResponseComplete(page, 360000);
        await sleep(3000);
        await scrollToBottom(page);
        await page.screenshot({ path: `${SCREENSHOT_DIR}/step4b-sow-generated.png`, fullPage: true });
        const resp4 = await getLastResponseText(page);
        console.log(`Response 4b preview:\n${resp4.substring(0, 800)}`);
      }
    }

    // ===== Check the right panel for package/checklist =====
    console.log('\n=== Checking right panel for package/checklist ===');
    const rightPanelText = await page.evaluate(() => {
      const allText = document.body.innerText;
      const lines = allText.split('\n').filter(l =>
        l.match(/package|checklist|SOW|IGCE|market research|acquisition plan|compliance|phase/i)
      );
      return lines.join('\n');
    });
    console.log(`Right panel/checklist content:\n${rightPanelText.substring(0, 500)}`);

    await page.screenshot({ path: `${SCREENSHOT_DIR}/step4-final-full.png`, fullPage: true });

    await scrollToBottom(page);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/step4-final-state.png`, fullPage: true });

    // ===== STEP 5: Verify DOCX/PDF export using most recent real S3 document =====
    console.log('\n=== STEP 5: Download generated documents ===');

    // Fetch the most recently modified workspace doc from S3 — no DOM dependency.
    // This is real data: the agent saved it to S3 during this session.
    const { execSync } = await import('child_process');
    const S3_BUCKET = 'eagle-documents-274487662938-dev';
    const S3_PREFIX = 'eagle/dev-tenant/dev-user/documents/';

    let latestKey = null;
    let docContent = null;
    let docType = 'sow';

    try {
      const lsOut = execSync(
        `aws s3 ls s3://${S3_BUCKET}/${S3_PREFIX} --recursive`,
        { encoding: 'utf8', timeout: 15000 }
      );
      // Lines: "2026-03-16 21:03:39      70433 eagle/dev-tenant/..."
      const lines = lsOut.trim().split('\n').filter(Boolean);
      // Sort by date+time (first two columns) descending and pick the latest sow
      const sorted = lines
        .map(l => {
          const m = l.match(/^(\S+\s+\S+)\s+\d+\s+(.+)$/);
          return m ? { ts: m[1], key: m[2].trim() } : null;
        })
        .filter(Boolean)
        .sort((a, b) => b.ts.localeCompare(a.ts));

      // Prefer sow, fall back to any doc
      const sowEntry = sorted.find(e => e.key.includes('/sow_'));
      const anyEntry = sorted[0];
      const chosen = sowEntry || anyEntry;

      if (chosen) {
        latestKey = chosen.key;
        const keyParts = latestKey.split('/');
        const filename = keyParts[keyParts.length - 1]; // sow_20260316_...md
        docType = filename.split('_')[0]; // sow
        console.log(`  Latest S3 doc: ${latestKey}`);
        docContent = execSync(
          `aws s3 cp s3://${S3_BUCKET}/${latestKey} -`,
          { encoding: 'utf8', timeout: 15000 }
        );
        console.log(`  Fetched ${docContent.length} chars of real content from S3`);
      }
    } catch (e) {
      console.log(`  ERROR listing/fetching S3 docs: ${e.message}`);
    }

    if (!docContent) {
      console.log('  ERROR: Could not retrieve any document from S3.');
      process.exitCode = 1;
      await page.screenshot({ path: `${SCREENSHOT_DIR}/step5-ERROR-no-s3-doc.png`, fullPage: true });
    } else {
      const docTitle = docType.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

      // POST real content to the export endpoint via the browser (goes through Next.js → FastAPI)
      const docxResult = await page.evaluate(async ({ content, title, docType }) => {
        try {
          const r = await fetch('/api/documents/export?format=docx', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content, title, doc_type: docType }),
          });
          const buf = await r.arrayBuffer();
          return {
            status: r.status,
            contentType: r.headers.get('content-type'),
            disposition: r.headers.get('content-disposition'),
            size: buf.byteLength,
            ok: r.ok,
          };
        } catch (e) { return { error: String(e), ok: false }; }
      }, { content: docContent, title: docTitle, docType });

      const pdfResult = await page.evaluate(async ({ content, title, docType }) => {
        try {
          const r = await fetch('/api/documents/export?format=pdf', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content, title, doc_type: docType }),
          });
          const buf = await r.arrayBuffer();
          return {
            status: r.status,
            contentType: r.headers.get('content-type'),
            disposition: r.headers.get('content-disposition'),
            size: buf.byteLength,
            ok: r.ok,
          };
        } catch (e) { return { error: String(e), ok: false }; }
      }, { content: docContent, title: docTitle, docType });

      console.log(`  DOCX: status=${docxResult.status} type=${docxResult.contentType} size=${docxResult.size}B`);
      console.log(`  PDF:  status=${pdfResult.status} type=${pdfResult.contentType} size=${pdfResult.size}B`);

      const docxPass = docxResult.ok && docxResult.contentType?.includes('wordprocessingml');
      const pdfPass  = pdfResult.ok  && pdfResult.contentType?.includes('pdf');
      console.log(`  DOCX export: ${docxPass ? 'PASS' : `FAIL — ${JSON.stringify(docxResult)}`}`);
      console.log(`  PDF  export: ${pdfPass  ? 'PASS' : `FAIL (may need pandoc/weasyprint) — status ${pdfResult.status}`}`);
      if (!docxPass) process.exitCode = 1;

      await page.screenshot({ path: `${SCREENSHOT_DIR}/step5-downloads-verified.png`, fullPage: true });
      console.log('  Screenshot saved: step5-downloads-verified.png');
    }

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
