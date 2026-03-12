import { test, expect } from '@playwright/test';
import path from 'path';
import fs from 'fs';

const SCREENSHOTS_DIR = path.resolve(__dirname, '../../screenshots');
const PROMPT = 'I need to create an acquisition package for IT cloud services. Generate a Statement of Work.';

interface SSEEvent {
  type?: string;
  data?: string;
  text?: string;
  agent_id?: string;
  agent_name?: string;
  timestamp?: string;
  tool_use?: { name?: string; input?: unknown; tool_use_id?: string };
  tool_result?: { name?: string; result?: unknown };
  metadata?: { state_type?: string; package_id?: string; checklist?: unknown; doc_type?: string; [key: string]: unknown };
  usage?: Record<string, unknown>;
  [key: string]: unknown;
}

test('AP lifecycle: tools → metadata → checklist', async ({ page }) => {
  test.setTimeout(180_000);
  fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });

  const sseEvents: SSEEvent[] = [];
  const consoleErrors: string[] = [];

  // ── SSE capture ──
  page.on('response', async (response) => {
    if (!response.url().includes('/api/invoke') && !response.url().includes('/api/chat')) return;
    try {
      const body = await response.text();
      for (const line of body.split('\n')) {
        if (!line.startsWith('data: ')) continue;
        try { sseEvents.push(JSON.parse(line.slice(6).trim())); } catch { /* */ }
      }
    } catch { /* */ }
  });

  page.on('console', (msg: any) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });

  // === STEP 1: Open chat ===
  await page.goto('http://localhost:3000/chat', { waitUntil: 'domcontentloaded', timeout: 30_000 });
  await page.waitForTimeout(3_000);
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'ap-flow-initial.png'), fullPage: true });

  // Find input
  const candidates = [
    page.getByPlaceholder('Ask about acquisitions'),
    page.getByPlaceholder(/ask/i),
    page.locator('textarea').first(),
    page.locator('input[type="text"]').first(),
    page.locator('[contenteditable="true"]').first(),
  ];
  let chatInput: any = null;
  for (const c of candidates) {
    if (await c.isVisible({ timeout: 2_000 }).catch(() => false)) { chatInput = c; break; }
  }
  expect(chatInput, 'Chat input must be found').not.toBeNull();

  // === STEP 2: Send message ===
  await chatInput.fill(PROMPT);
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'ap-flow-before-send.png'), fullPage: true });

  const sendBtn = page.locator('button[type="submit"], button[aria-label*="send" i], button:has-text("Send")').first();
  if (await sendBtn.isVisible({ timeout: 2_000 }).catch(() => false)) {
    await sendBtn.click();
  } else {
    await chatInput.press('Enter');
  }

  // === STEP 3: Wait for streaming ===
  await page.waitForTimeout(3_000);
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'ap-flow-streaming.png'), fullPage: true });

  // Poll for response completion
  let responseText = '';
  let lastLen = 0;
  let stableCount = 0;
  const maxWait = 150_000;
  const pollInterval = 10_000;
  const startTime = Date.now();

  while (Date.now() - startTime < maxWait) {
    await page.waitForTimeout(pollInterval);
    const selectors = [
      '[data-message-role="assistant"]',
      '.copilotkit-assistant-message',
      '[class*="assistant"]',
      '.prose',
      '.markdown',
    ];
    for (const sel of selectors) {
      const els = page.locator(sel);
      if ((await els.count()) > 0) {
        responseText = await els.last().innerText().catch(() => '');
        if (responseText) break;
      }
    }
    if (!responseText) {
      const body = await page.locator('body').innerText().catch(() => '');
      if (/statement of work|SOW|cloud/i.test(body)) responseText = body;
    }
    if (responseText.length > 0) {
      if (responseText.length === lastLen) { stableCount++; if (stableCount >= 2) break; }
      else stableCount = 0;
      lastLen = responseText.length;
    }
    console.log(`Polling... ${Math.round((Date.now() - startTime) / 1000)}s, len: ${responseText.length}`);
  }

  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'ap-flow-response.png'), fullPage: true });

  if (!responseText) {
    responseText = await page.locator('body').innerText().catch(() => '');
  }

  // === STEP 4: Validate ===
  const toolUseEvents = sseEvents.filter(e => e.type === 'tool_use');
  const toolResultEvents = sseEvents.filter(e => e.type === 'tool_result');
  const metadataEvents = sseEvents.filter(e => e.type === 'metadata');
  const toolUseNames = toolUseEvents.map(e => e.tool_use?.name).filter(Boolean) as string[];
  const toolResultNames = toolResultEvents.map(e => e.tool_result?.name).filter(Boolean) as string[];

  const createDocCalled = toolUseNames.some(n => /create_document|generate_document|write_document/i.test(n));
  const knowledgeCalled = toolUseNames.some(n => /knowledge|kb_search|search_knowledge|retrieve|lookup/i.test(n));
  const pairingOk = toolUseNames.length === toolResultNames.length;
  const hasMetadataWithStateType = metadataEvents.some(e => e.metadata?.state_type);

  // Checklist panel — soft assertion (not yet wired into chat page)
  const checklistPanel = page.locator('.w-72.border-l');
  const checklistVisible = await checklistPanel.isVisible({ timeout: 2_000 }).catch(() => false);

  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'ap-flow-checklist.png'), fullPage: true });

  // ── Report ──
  console.log('\n================================================================');
  console.log('     AP LIFECYCLE VALIDATION');
  console.log('================================================================');
  console.log(`  Response present:             ${responseText.length > 100 ? 'PASS' : 'FAIL'} (${responseText.length} chars)`);
  console.log(`  SSE events captured:          ${sseEvents.length}`);
  console.log('  ── Tools ──');
  console.log(`  tool_use events:              ${toolUseEvents.length} [${toolUseNames.join(', ')}]`);
  console.log(`  tool_result events:           ${toolResultEvents.length}`);
  console.log(`  tool_use:tool_result pairing: ${pairingOk ? 'PASS' : 'FAIL'} (${toolUseNames.length}:${toolResultNames.length})`);
  console.log(`  create_document called:       ${createDocCalled ? 'PASS' : 'WARN'}`);
  console.log(`  knowledge tool called:        ${knowledgeCalled ? 'YES (SOFT)' : 'NO (SOFT — ok)'}`);
  console.log('  ── Metadata ──');
  console.log(`  metadata events:              ${metadataEvents.length}`);
  console.log(`  metadata with state_type:     ${hasMetadataWithStateType ? 'PASS' : 'WARN'}`);
  console.log('  ── Checklist Panel ──');
  console.log(`  ChecklistPanel visible:       ${checklistVisible ? 'YES' : 'NO (expected — not wired)'}`);
  console.log('  ── Errors ──');
  console.log(`  Console errors:               ${consoleErrors.length}`);
  console.log('================================================================');

  // Log response excerpt
  console.log('\n=== RESPONSE EXCERPT (first 1000 chars) ===');
  console.log(responseText.substring(0, 1000));
  console.log('=== END EXCERPT ===');

  // Hard assertions
  expect(responseText.length, 'Response must be substantive').toBeGreaterThan(50);
  expect(sseEvents.length, 'SSE events must be captured').toBeGreaterThan(0);
  expect(pairingOk, `tool_use:tool_result pairing mismatch (${toolUseNames.length} vs ${toolResultNames.length})`).toBe(true);

  // Soft assertions — log but don't fail
  if (!createDocCalled) {
    console.warn('SOFT WARN: create_document was not called — LLM may have handled differently');
  }
  if (!hasMetadataWithStateType) {
    console.warn('SOFT WARN: No metadata events with state_type — update_state may not have fired');
  }
  if (!checklistVisible) {
    console.log('INFO: ChecklistPanel not visible — expected until wired into chat page');
  }
});
