import { test, expect } from '@playwright/test';
import path from 'path';
import fs from 'fs';

const OUT_DIR = path.resolve(__dirname, '../../screenshots/sse-pipeline');

/**
 * SSE Pipeline Validation — schema, pairing, and rendering.
 *
 * Sends a query that triggers multiple tools, captures the raw SSE stream,
 * then validates:
 *   1. Every SSE event matches the StreamEvent schema
 *   2. Every tool_use has a matching tool_result (1:1 pairing)
 *   3. Tool cards render with chevrons and expand to formatted content
 */
test('SSE pipeline: schema match, tool pairing, and card rendering', async ({ page }) => {
  test.setTimeout(180_000);
  fs.mkdirSync(OUT_DIR, { recursive: true });

  // ── SSE event capture ──────────────────────────────────────────────
  interface SSEEvent {
    type?: string;
    agent_id?: string;
    agent_name?: string;
    timestamp?: string;
    content?: string;
    tool_use?: { name?: string; input?: unknown; tool_use_id?: string };
    tool_result?: { name?: string; result?: unknown };
    metadata?: Record<string, unknown>;
  }

  const allEvents: SSEEvent[] = [];
  const schemaErrors: string[] = [];

  page.on('response', async (response) => {
    if (!response.url().includes('/api/invoke')) return;
    const ct = response.headers()['content-type'] || '';
    if (!ct.includes('text/event-stream') && !ct.includes('application/json')) return;

    try {
      const body = await response.text();
      for (const line of body.split('\n')) {
        if (!line.startsWith('data: ')) continue;
        const raw = line.slice(6).trim();
        if (!raw) continue;
        try {
          const evt: SSEEvent = JSON.parse(raw);
          allEvents.push(evt);
        } catch { /* skip non-JSON */ }
      }
    } catch { /* body unavailable */ }
  });

  const consoleErrors: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });

  // ── Step 1: Navigate ───────────────────────────────────────────────
  await page.goto('http://localhost:3000/chat', { waitUntil: 'domcontentloaded', timeout: 30_000 });
  await page.waitForTimeout(3_000);
  await page.screenshot({ path: path.join(OUT_DIR, '01-initial.png'), fullPage: true });

  // ── Step 2: Send query that triggers multiple tools ────────────────
  const query = 'What are the NCI thresholds for simplified acquisitions and what FAR clauses apply?';

  const chatInput = page.locator('textarea').first();
  await expect(chatInput).toBeVisible({ timeout: 5_000 });
  await chatInput.fill(query);
  await chatInput.press('Enter');

  // ── Step 3: Wait for response to complete ──────────────────────────
  const startTime = Date.now();
  const maxWait = 120_000;
  let complete = false;

  while (Date.now() - startTime < maxWait) {
    await page.waitForTimeout(5_000);
    const hasComplete = allEvents.some((e) => e.type === 'complete');
    const pulsing = await page.locator('.animate-pulse').count();
    if (hasComplete && pulsing === 0) {
      complete = true;
      break;
    }
  }

  // Give UI time to settle after stream ends
  await page.waitForTimeout(3_000);
  await page.screenshot({ path: path.join(OUT_DIR, '02-response-complete.png'), fullPage: true });

  // ── Step 4: Schema validation ──────────────────────────────────────
  const toolUseEvents = allEvents.filter((e) => e.type === 'tool_use');
  const toolResultEvents = allEvents.filter((e) => e.type === 'tool_result');
  const textEvents = allEvents.filter((e) => e.type === 'text');
  const completeEvents = allEvents.filter((e) => e.type === 'complete');

  // 4a: Every event must have base fields
  for (let i = 0; i < allEvents.length; i++) {
    const evt = allEvents[i];
    if (!evt.type) schemaErrors.push(`Event[${i}]: missing "type"`);
    if (!evt.agent_id) schemaErrors.push(`Event[${i}]: missing "agent_id" (type=${evt.type})`);
    if (!evt.agent_name) schemaErrors.push(`Event[${i}]: missing "agent_name" (type=${evt.type})`);
    if (!evt.timestamp) schemaErrors.push(`Event[${i}]: missing "timestamp" (type=${evt.type})`);
  }

  // 4b: text events must have content
  for (let i = 0; i < textEvents.length; i++) {
    const evt = textEvents[i];
    if (evt.content === undefined && evt.content !== '') {
      schemaErrors.push(`text[${i}]: missing "content"`);
    }
  }

  // 4c: tool_use events must have nested tool_use object with name
  for (let i = 0; i < toolUseEvents.length; i++) {
    const evt = toolUseEvents[i];
    if (!evt.tool_use) {
      schemaErrors.push(`tool_use[${i}]: missing "tool_use" object`);
    } else {
      if (!evt.tool_use.name) schemaErrors.push(`tool_use[${i}]: missing tool_use.name`);
      if (evt.tool_use.input === undefined) schemaErrors.push(`tool_use[${i}]: missing tool_use.input`);
    }
  }

  // 4d: tool_result events must have nested tool_result object with name + result
  for (let i = 0; i < toolResultEvents.length; i++) {
    const evt = toolResultEvents[i];
    if (!evt.tool_result) {
      schemaErrors.push(`tool_result[${i}]: missing "tool_result" object`);
    } else {
      if (!evt.tool_result.name) schemaErrors.push(`tool_result[${i}]: missing tool_result.name`);
      if (evt.tool_result.result === undefined) schemaErrors.push(`tool_result[${i}]: missing tool_result.result`);
    }
  }

  // 4e: exactly 1 complete event
  if (completeEvents.length !== 1) {
    schemaErrors.push(`Expected 1 complete event, got ${completeEvents.length}`);
  }

  // ── Step 5: Tool pairing validation ────────────────────────────────
  const toolUseNames = toolUseEvents.map((e) => e.tool_use?.name).filter(Boolean);
  const toolResultNames = toolResultEvents.map((e) => e.tool_result?.name).filter(Boolean);

  const pairingErrors: string[] = [];
  if (toolUseNames.length !== toolResultNames.length) {
    pairingErrors.push(
      `tool_use count (${toolUseNames.length}) != tool_result count (${toolResultNames.length})`
    );
  }

  // Check that every tool_result name has a matching tool_use name
  const useNameBag = [...toolUseNames];
  for (const resultName of toolResultNames) {
    const idx = useNameBag.indexOf(resultName);
    if (idx === -1) {
      pairingErrors.push(`tool_result "${resultName}" has no matching tool_use`);
    } else {
      useNameBag.splice(idx, 1); // consume the match
    }
  }
  for (const unmatched of useNameBag) {
    pairingErrors.push(`tool_use "${unmatched}" has no matching tool_result`);
  }

  // Check no empty-name tool_result leaked through
  const emptyNameResults = toolResultEvents.filter((e) => !e.tool_result?.name);
  if (emptyNameResults.length > 0) {
    pairingErrors.push(`${emptyNameResults.length} tool_result event(s) with empty name leaked through`);
  }

  // ── Step 6: Tool card rendering validation ─────────────────────────
  const toolCards = page.locator('.my-1.rounded-lg.border');
  const cardCount = await toolCards.count();

  const renderingErrors: string[] = [];
  const cardDetails: Array<{ label: string; hasChevron: boolean; expandable: boolean; contentFormatted: boolean }> = [];

  for (let i = 0; i < cardCount; i++) {
    const card = toolCards.nth(i);
    const cardText = await card.innerText().catch(() => '');
    const label = cardText.split('\n')[0]?.trim() || `Card ${i}`;
    const hasChevron = cardText.includes('\u25BE'); // ▾

    // Check for green status dot
    const greenDot = await card.locator('.bg-green-500').count();
    if (greenDot === 0) {
      renderingErrors.push(`Card "${label}": missing green status dot`);
    }

    let expandable = false;
    let contentFormatted = true;

    if (hasChevron) {
      // Click to expand
      const button = card.locator('button').first();
      await button.click();
      await page.waitForTimeout(500);

      // Check expanded content exists
      const expandedPanel = card.locator('.overflow-auto, .whitespace-pre-wrap, .prose');
      const panelCount = await expandedPanel.count();
      expandable = panelCount > 0;

      if (expandable) {
        const panelText = await expandedPanel.first().innerText().catch(() => '');

        // Content should NOT be raw SSE event JSON (no "agent_id" or "timestamp" leak)
        if (panelText.includes('"agent_id"') && panelText.includes('"timestamp"')) {
          contentFormatted = false;
          renderingErrors.push(`Card "${label}": expanded content contains raw SSE event JSON`);
        }

        // Content should have actual data (not empty)
        if (panelText.trim().length < 5) {
          renderingErrors.push(`Card "${label}": expanded content is empty or too short`);
        }
      }

      // Collapse it back
      await button.click();
      await page.waitForTimeout(300);
    } else {
      renderingErrors.push(`Card "${label}": missing chevron — tool_result not received`);
    }

    cardDetails.push({ label, hasChevron, expandable, contentFormatted });
  }

  // Take screenshot with one card expanded
  if (cardCount > 0) {
    const firstExpandable = cardDetails.findIndex((c) => c.hasChevron);
    if (firstExpandable >= 0) {
      await toolCards.nth(firstExpandable).locator('button').first().click();
      await page.waitForTimeout(500);
      await page.screenshot({ path: path.join(OUT_DIR, '03-card-expanded.png'), fullPage: true });
      // collapse
      await toolCards.nth(firstExpandable).locator('button').first().click();
    }
  }

  // ── Step 7: Save dump + report ─────────────────────────────────────
  const report = [
    '# SSE Pipeline Validation Report',
    `Date: ${new Date().toISOString()}`,
    `Query: ${query}`,
    `Response complete: ${complete}`,
    '',
    '## Event Counts',
    `  text:        ${textEvents.length}`,
    `  tool_use:    ${toolUseEvents.length}`,
    `  tool_result: ${toolResultEvents.length}`,
    `  complete:    ${completeEvents.length}`,
    `  total:       ${allEvents.length}`,
    '',
    '## Schema Errors',
    schemaErrors.length === 0 ? '  None' : schemaErrors.map((e) => `  - ${e}`).join('\n'),
    '',
    '## Pairing Errors',
    pairingErrors.length === 0 ? '  None' : pairingErrors.map((e) => `  - ${e}`).join('\n'),
    '',
    '## Rendering Errors',
    renderingErrors.length === 0 ? '  None' : renderingErrors.map((e) => `  - ${e}`).join('\n'),
    '',
    '## Tool Cards',
    `  Total cards: ${cardCount}`,
    ...cardDetails.map(
      (c) =>
        `  ${c.hasChevron ? '[OK]' : '[!!]'} ${c.label} — chevron: ${c.hasChevron}, expandable: ${c.expandable}, formatted: ${c.contentFormatted}`
    ),
    '',
    '## Tool Names',
    `  tool_use:    ${toolUseNames.join(', ')}`,
    `  tool_result: ${toolResultNames.join(', ')}`,
  ].join('\n');

  fs.writeFileSync(path.join(OUT_DIR, 'report.md'), report, 'utf-8');

  // Save raw events
  fs.writeFileSync(
    path.join(OUT_DIR, 'events.json'),
    JSON.stringify(allEvents, null, 2),
    'utf-8'
  );

  // ── Console report ─────────────────────────────────────────────────
  console.log('\n' + '='.repeat(60));
  console.log('  SSE PIPELINE VALIDATION REPORT');
  console.log('='.repeat(60));
  console.log(`  Events: ${allEvents.length} total (${textEvents.length} text, ${toolUseEvents.length} tool_use, ${toolResultEvents.length} tool_result)`);
  console.log(`  Schema errors:    ${schemaErrors.length}`);
  console.log(`  Pairing errors:   ${pairingErrors.length}`);
  console.log(`  Rendering errors: ${renderingErrors.length}`);
  console.log(`  Tool cards:       ${cardCount} (${cardDetails.filter((c) => c.hasChevron).length} with chevron)`);
  console.log(`  Response complete: ${complete}`);
  console.log('='.repeat(60));

  // ── Step 8: FIFO ordering validation ──────────────────────────────
  const fifoErrors: string[] = [];

  // 8a: tool_use must appear before its matching tool_result
  for (const resultEvt of toolResultEvents) {
    const resultName = resultEvt.tool_result?.name;
    if (!resultName) continue;
    const useIdx = allEvents.findIndex(
      (e) => e.type === 'tool_use' && e.tool_use?.name === resultName,
    );
    const resultIdx = allEvents.indexOf(resultEvt);
    if (useIdx === -1) {
      fifoErrors.push(`tool_result "${resultName}" has no preceding tool_use`);
    } else if (useIdx > resultIdx) {
      fifoErrors.push(
        `tool_use "${resultName}" (idx=${useIdx}) appears AFTER tool_result (idx=${resultIdx})`,
      );
    }
  }

  // 8b: complete event must be the last typed event
  if (completeEvents.length === 1) {
    const completeIdx = allEvents.indexOf(completeEvents[0]);
    const laterEvents = allEvents.slice(completeIdx + 1).filter((e) => e.type);
    if (laterEvents.length > 0) {
      fifoErrors.push(
        `${laterEvents.length} event(s) after complete: ${laterEvents.map((e) => e.type).join(', ')}`,
      );
    }
  }

  // 8c: first event should be text (metadata/handshake)
  if (allEvents.length > 0 && allEvents[0].type !== 'text') {
    fifoErrors.push(`First event is "${allEvents[0].type}", expected "text" (metadata handshake)`);
  }

  console.log(`  FIFO errors: ${fifoErrors.length}`);
  if (fifoErrors.length > 0) {
    fifoErrors.forEach((e) => console.log(`    - ${e}`));
  }

  // ── Step 9: Session persistence — reload and verify messages survive ──
  const sessionErrors: string[] = [];

  await page.reload({ waitUntil: 'domcontentloaded', timeout: 30_000 });
  await page.waitForTimeout(5_000);
  await page.screenshot({ path: path.join(OUT_DIR, '04-after-reload.png'), fullPage: true });

  const afterReloadBody = await page.locator('body').innerText().catch(() => '');

  // User message should persist
  const userMsgSurvived =
    afterReloadBody.toLowerCase().includes('thresholds') ||
    afterReloadBody.toLowerCase().includes('simplified acquisition');
  if (!userMsgSurvived) {
    sessionErrors.push('User message not found after reload');
  }

  // Assistant response should persist (look for domain-specific content)
  const assistantSurvived =
    /\$?350[,.]?000/i.test(afterReloadBody) ||
    /FAR/i.test(afterReloadBody) ||
    /simplified/i.test(afterReloadBody);
  if (!assistantSurvived) {
    sessionErrors.push('Assistant response not found after reload');
  }

  // Tool cards should re-render from persisted state
  const reloadCardCount = await toolCards.count();
  console.log(`  Session persistence — user msg: ${userMsgSurvived}, assistant: ${assistantSurvived}, cards after reload: ${reloadCardCount}`);
  if (sessionErrors.length > 0) {
    sessionErrors.forEach((e) => console.log(`    - ${e}`));
  }

  // Update report with new sections
  const fullReport = [
    report,
    '',
    '## FIFO Ordering',
    fifoErrors.length === 0 ? '  None' : fifoErrors.map((e) => `  - ${e}`).join('\n'),
    '',
    '## Session Persistence',
    `  User message survived reload:      ${userMsgSurvived}`,
    `  Assistant response survived reload: ${assistantSurvived}`,
    `  Tool cards after reload:            ${reloadCardCount}`,
    sessionErrors.length === 0 ? '  Errors: None' : sessionErrors.map((e) => `  - ${e}`).join('\n'),
  ].join('\n');

  fs.writeFileSync(path.join(OUT_DIR, 'report.md'), fullReport, 'utf-8');

  // ── Assertions ─────────────────────────────────────────────────────
  expect(complete, 'Response should complete within timeout').toBe(true);
  expect(allEvents.length, 'Should receive SSE events').toBeGreaterThan(0);
  expect(toolUseEvents.length, 'Should have at least 1 tool_use').toBeGreaterThan(0);
  expect(schemaErrors, `Schema errors: ${schemaErrors.join('; ')}`).toHaveLength(0);
  expect(pairingErrors, `Pairing errors: ${pairingErrors.join('; ')}`).toHaveLength(0);
  expect(renderingErrors, `Rendering errors: ${renderingErrors.join('; ')}`).toHaveLength(0);
  expect(cardCount, 'Should have tool cards in DOM').toBeGreaterThan(0);
  expect(fifoErrors, `FIFO errors: ${fifoErrors.join('; ')}`).toHaveLength(0);
  expect(userMsgSurvived, 'User message should survive page reload').toBe(true);
  expect(assistantSurvived, 'Assistant response should survive page reload').toBe(true);
});
