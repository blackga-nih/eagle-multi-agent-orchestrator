import { test, expect } from '@playwright/test';

/**
 * ThinkingChip — extended-thinking SSE chip rendering.
 *
 * Verifies that the `reasoning` SSE event with `metadata.block_id` produces
 * one purple "Thinking" chip per Bedrock contentBlockIndex, that consecutive
 * deltas with the same block_id aggregate into one chip (not multiple), and
 * that clicking a chip opens a modal with the accumulated reasoning text.
 *
 * Mocks the SSE response via page.route() so this test is independent of
 * Bedrock thinking enablement.
 */

function buildSSE(events: Array<Record<string, unknown>>): string {
  return events.map((e) => `data: ${JSON.stringify(e)}`).join('\n\n') + '\n\n';
}

test.describe('ThinkingChip', () => {
  test('renders one chip per Bedrock block, modal shows aggregated reasoning', async ({
    page,
  }) => {
    test.setTimeout(45_000);

    const events: Array<Record<string, unknown>> = [
      // Block 0 — first thought, two deltas
      {
        type: 'reasoning',
        agent_id: 'eagle',
        agent_name: 'EAGLE',
        reasoning: 'Let me work through this step by step. ',
        metadata: { block_id: '0' },
        timestamp: '2026-01-01T00:00:00Z',
      },
      {
        type: 'reasoning',
        agent_id: 'eagle',
        agent_name: 'EAGLE',
        reasoning: 'First, I need to identify the FAR threshold.',
        metadata: { block_id: '0' },
        timestamp: '2026-01-01T00:00:01Z',
      },
      // Block 2 — second thought, single delta (block 1 was a tool_use)
      {
        type: 'reasoning',
        agent_id: 'eagle',
        agent_name: 'EAGLE',
        reasoning: 'After the tool call, I now know the answer is $250k.',
        metadata: { block_id: '2' },
        timestamp: '2026-01-01T00:00:03Z',
      },
      {
        type: 'text',
        agent_id: 'eagle',
        agent_name: 'EAGLE',
        content: 'The simplified-acquisition threshold is $250,000.',
        timestamp: '2026-01-01T00:00:04Z',
      },
      {
        type: 'complete',
        agent_id: 'eagle',
        agent_name: 'EAGLE',
        metadata: { duration_ms: 4000 },
        timestamp: '2026-01-01T00:00:05Z',
      },
    ];

    await page.route('**/api/invoke', async (route) => {
      await route.fulfill({
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
        body: buildSSE(events),
      });
    });

    await page.goto('http://localhost:3000/chat/', {
      waitUntil: 'domcontentloaded',
      timeout: 15_000,
    });

    const textarea = page.locator('textarea').first();
    await expect(textarea).toBeVisible({ timeout: 5_000 });
    await textarea.fill('What is the simplified acquisition threshold?');
    await textarea.press('Enter');
    await page.waitForTimeout(4_000);

    // Two chips — one per block_id (0 and 2). Block 0 aggregates two deltas;
    // block 2 has a single delta. The chip label flips from "Thinking" to
    // "Thought" once the stream completes.
    const chips = page.locator('button', { hasText: /Thought|Thinking/ });
    await expect(chips).toHaveCount(2, { timeout: 8_000 });

    // Click the first chip — modal should display the aggregated reasoning text
    await chips.first().click();
    const modal = page.locator('[role="dialog"], div').filter({
      hasText: 'Let me work through this step by step',
    }).first();
    await expect(modal).toBeVisible({ timeout: 5_000 });
    await expect(modal).toContainText('First, I need to identify the FAR threshold');
  });

  test('legacy reasoning events without block_id collapse to a single chip', async ({
    page,
  }) => {
    test.setTimeout(45_000);

    // No metadata.block_id — chat-stream-manager falls back to a single rolling block
    const events: Array<Record<string, unknown>> = [
      {
        type: 'reasoning',
        agent_id: 'eagle',
        agent_name: 'EAGLE',
        reasoning: 'untagged thought one. ',
        timestamp: '2026-01-01T00:00:00Z',
      },
      {
        type: 'reasoning',
        agent_id: 'eagle',
        agent_name: 'EAGLE',
        reasoning: 'untagged thought two.',
        timestamp: '2026-01-01T00:00:01Z',
      },
      {
        type: 'text',
        agent_id: 'eagle',
        agent_name: 'EAGLE',
        content: 'done',
        timestamp: '2026-01-01T00:00:02Z',
      },
      {
        type: 'complete',
        agent_id: 'eagle',
        agent_name: 'EAGLE',
        metadata: { duration_ms: 2000 },
        timestamp: '2026-01-01T00:00:03Z',
      },
    ];

    await page.route('**/api/invoke', async (route) => {
      await route.fulfill({
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
        body: buildSSE(events),
      });
    });

    await page.goto('http://localhost:3000/chat/', {
      waitUntil: 'domcontentloaded',
      timeout: 15_000,
    });

    const textarea = page.locator('textarea').first();
    await expect(textarea).toBeVisible({ timeout: 5_000 });
    await textarea.fill('test legacy reasoning');
    await textarea.press('Enter');
    await page.waitForTimeout(3_000);

    const chips = page.locator('button', { hasText: /Thought|Thinking/ });
    await expect(chips).toHaveCount(1, { timeout: 8_000 });
  });
});
