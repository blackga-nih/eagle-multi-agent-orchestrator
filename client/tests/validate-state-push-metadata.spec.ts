import { test, expect } from '@playwright/test';
import path from 'path';
import fs from 'fs';

const SCREENSHOTS_DIR = path.resolve(__dirname, '../../screenshots');
const PROMPT = 'Check the compliance requirements for a sole-source IT acquisition above the simplified acquisition threshold. What documents am I missing?';

/** Known state_type values from use-package-state.ts switch cases */
const VALID_STATE_TYPES = ['checklist_update', 'phase_change', 'document_ready', 'compliance_alert'];

interface SSEEvent {
  type?: string;
  data?: string;
  text?: string;
  agent_id?: string;
  agent_name?: string;
  timestamp?: string;
  tool_use?: { name?: string; input?: unknown; tool_use_id?: string };
  tool_result?: { name?: string; result?: unknown };
  metadata?: {
    state_type?: string;
    package_id?: string;
    checklist?: { required?: string[]; completed?: string[]; missing?: string[] };
    doc_type?: string;
    severity?: string;
    items?: unknown[];
    phase?: string;
    previous?: string;
    [key: string]: unknown;
  };
  usage?: Record<string, unknown>;
  [key: string]: unknown;
}

test('SSE METADATA events: structure and types', async ({ page }) => {
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
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'state-push-initial.png'), fullPage: true });

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

  // === STEP 2: Send query ===
  await chatInput.fill(PROMPT);
  const sendBtn = page.locator('button[type="submit"], button[aria-label*="send" i], button:has-text("Send")').first();
  if (await sendBtn.isVisible({ timeout: 2_000 }).catch(() => false)) {
    await sendBtn.click();
  } else {
    await chatInput.press('Enter');
  }
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'state-push-sent.png'), fullPage: true });

  // === STEP 3: Wait for response ===
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
      if (/sole.?source|compliance|justification|J&A/i.test(body)) responseText = body;
    }
    if (responseText.length > 0) {
      if (responseText.length === lastLen) { stableCount++; if (stableCount >= 2) break; }
      else stableCount = 0;
      lastLen = responseText.length;
    }
    console.log(`Polling... ${Math.round((Date.now() - startTime) / 1000)}s, len: ${responseText.length}`);
  }

  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'state-push-response.png'), fullPage: true });

  if (!responseText) {
    responseText = await page.locator('body').innerText().catch(() => '');
  }

  // === STEP 4: Analyze SSE events ===
  const toolUseEvents = sseEvents.filter(e => e.type === 'tool_use');
  const toolResultEvents = sseEvents.filter(e => e.type === 'tool_result');
  const metadataEvents = sseEvents.filter(e => e.type === 'metadata');
  const toolUseNames = toolUseEvents.map(e => e.tool_use?.name).filter(Boolean) as string[];
  const toolResultNames = toolResultEvents.map(e => e.tool_result?.name).filter(Boolean) as string[];

  const pairingOk = toolUseNames.length === toolResultNames.length;

  // Metadata analysis
  const metadataWithStateType = metadataEvents.filter(e => e.metadata?.state_type);
  const stateTypes = metadataWithStateType.map(e => e.metadata!.state_type!);
  const unknownStateTypes = stateTypes.filter(st => !VALID_STATE_TYPES.includes(st));

  // Schema validation per state_type
  const schemaErrors: string[] = [];
  for (const evt of metadataWithStateType) {
    const st = evt.metadata!.state_type!;
    const md = evt.metadata!;
    switch (st) {
      case 'document_ready':
        if (!md.doc_type) schemaErrors.push(`document_ready missing doc_type`);
        break;
      case 'checklist_update':
        if (!md.checklist) {
          schemaErrors.push(`checklist_update missing checklist`);
        } else {
          const cl = md.checklist as Record<string, unknown>;
          if (!cl.required || !cl.completed || !cl.missing) {
            schemaErrors.push(`checklist_update.checklist missing required/completed/missing`);
          }
        }
        break;
      case 'phase_change':
        if (!md.phase) schemaErrors.push(`phase_change missing phase`);
        break;
      case 'compliance_alert':
        if (!md.severity) schemaErrors.push(`compliance_alert missing severity`);
        break;
    }
  }

  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'state-push-final.png'), fullPage: true });

  // ── Report ──
  console.log('\n================================================================');
  console.log('     SSE METADATA EVENT VALIDATION');
  console.log('================================================================');
  console.log(`  Response present:             ${responseText.length > 50 ? 'PASS' : 'FAIL'} (${responseText.length} chars)`);
  console.log(`  SSE events captured:          ${sseEvents.length}`);
  console.log('  ── Tool Pairing ──');
  console.log(`  tool_use events:              ${toolUseEvents.length} [${toolUseNames.join(', ')}]`);
  console.log(`  tool_result events:           ${toolResultEvents.length}`);
  console.log(`  Pairing match:                ${pairingOk ? 'PASS' : 'FAIL'}`);
  console.log('  ── Metadata Events ──');
  console.log(`  Total metadata events:        ${metadataEvents.length}`);
  console.log(`  With state_type:              ${metadataWithStateType.length}`);
  console.log(`  state_types seen:             [${stateTypes.join(', ')}]`);
  console.log(`  Unknown state_types:          ${unknownStateTypes.length === 0 ? 'PASS (none)' : `FAIL [${unknownStateTypes.join(', ')}]`}`);
  console.log(`  Schema errors:                ${schemaErrors.length === 0 ? 'PASS (none)' : `FAIL [${schemaErrors.join('; ')}]`}`);
  console.log('  ── Errors ──');
  console.log(`  Console errors:               ${consoleErrors.length}`);
  console.log('================================================================');

  // Dump metadata events for debugging
  if (metadataEvents.length > 0) {
    console.log('\n=== METADATA EVENTS ===');
    for (const evt of metadataEvents) {
      console.log(JSON.stringify(evt.metadata, null, 2));
    }
    console.log('=== END METADATA ===');
  }

  // Hard assertions
  expect(sseEvents.length, 'SSE events must be captured').toBeGreaterThan(0);
  expect(pairingOk, `tool_use:tool_result pairing mismatch (${toolUseNames.length} vs ${toolResultNames.length})`).toBe(true);

  // If metadata events exist, validate structure
  if (metadataWithStateType.length > 0) {
    expect(unknownStateTypes, `Unknown state_types: ${unknownStateTypes.join(', ')}`).toHaveLength(0);
    expect(schemaErrors, `Schema errors: ${schemaErrors.join('; ')}`).toHaveLength(0);

    // At least one state_type must be valid
    const hasValidStateType = stateTypes.some(st => VALID_STATE_TYPES.includes(st));
    expect(hasValidStateType, 'At least one metadata event must have a valid state_type').toBe(true);
  } else {
    // Soft — metadata may not fire depending on LLM behavior
    console.warn('SOFT WARN: No metadata events with state_type captured — LLM may not have called update_state');
  }

  expect(responseText.length, 'Response must be substantive').toBeGreaterThan(50);
});
