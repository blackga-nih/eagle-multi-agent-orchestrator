import { test, expect } from '@playwright/test';

/**
 * Activity Panel — Event Count Consistency & User Input Badge
 *
 * Tests two fixes:
 *   1. Tab badge and header show merged display-entry count (not raw SSE chunk count)
 *   2. User messages show a distinct "user" badge, not "agent"
 *
 * Uses synthetic SSE via page.route() so no backend is needed.
 */

// ---------------------------------------------------------------------------
// Helper: build a synthetic SSE payload
// ---------------------------------------------------------------------------

function buildSSE(events: Array<Record<string, unknown>>): string {
  return events.map((e) => `data: ${JSON.stringify(e)}`).join('\n\n') + '\n\n';
}

// ---------------------------------------------------------------------------
// 1. Event count consistency
// ---------------------------------------------------------------------------

test.describe('Activity Panel Event Counts', () => {

  test('tab badge matches displayed timeline row count after text-chunk merging', async ({ page }) => {
    test.setTimeout(45_000);

    // 10 text chunks from same agent (will merge into 1 display entry)
    // + 1 tool_use + 1 tool_result + 1 complete = 13 raw events → 4 display entries
    const events: Array<Record<string, unknown>> = [];
    for (let i = 0; i < 10; i++) {
      events.push({
        type: 'text',
        agent_id: 'eagle',
        agent_name: 'EAGLE',
        content: `chunk${i} `,
        timestamp: `2026-01-01T00:00:${String(i).padStart(2, '0')}Z`,
      });
    }
    events.push({
      type: 'tool_use',
      agent_id: 'eagle',
      agent_name: 'EAGLE',
      tool_use: { name: 'search_far', input: { query: 'test' }, tool_use_id: 'tu1' },
      timestamp: '2026-01-01T00:00:10Z',
    });
    events.push({
      type: 'tool_result',
      agent_id: 'eagle',
      agent_name: 'EAGLE',
      tool_result: { name: 'search_far', result: { clauses: [], results_count: 0 } },
      timestamp: '2026-01-01T00:00:11Z',
    });
    events.push({
      type: 'complete',
      agent_id: 'eagle',
      agent_name: 'EAGLE',
      metadata: { duration_ms: 5000 },
      timestamp: '2026-01-01T00:00:12Z',
    });

    await page.route('**/api/invoke', async (route) => {
      await route.fulfill({
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
        body: buildSSE(events),
      });
    });

    await page.goto('http://localhost:3000/chat/', { waitUntil: 'domcontentloaded', timeout: 15_000 });

    // Send a message to trigger SSE
    const textarea = page.locator('textarea').first();
    await expect(textarea).toBeVisible({ timeout: 5_000 });
    await textarea.fill('test query');
    await textarea.press('Enter');
    await page.waitForTimeout(5_000);

    // Agent Logs tab is active by default — find it by partial text (badge is inside the button)
    const logsTab = page.locator('button', { hasText: 'Agent Logs' });
    await expect(logsTab).toBeVisible({ timeout: 5_000 });
    await logsTab.click();
    await page.waitForTimeout(1_000);

    // --- Tab badge ---
    const badge = logsTab.locator('span.rounded-full');
    await expect(badge).toBeVisible({ timeout: 5_000 });
    const badgeText = await badge.textContent();
    const badgeCount = parseInt(badgeText?.trim() ?? '0', 10);

    // --- Header event count ---
    // The sub-header shows "N EVENTS" in uppercase
    const header = page.locator('text=/\\d+ event/i').first();
    await expect(header).toBeVisible({ timeout: 5_000 });
    const headerText = await header.textContent();
    const headerCount = parseInt(headerText?.match(/(\d+)/)?.[1] ?? '0', 10);

    // --- Timeline rows ---
    // Each row has a border-l-[3px] style and a type badge
    const timelineRows = page.locator('[class*="border-l-"][class*="cursor-pointer"]');
    const rowCount = await timelineRows.count();

    // All three numbers must match: badge = header = rows
    expect(badgeCount).toBe(headerCount);
    expect(badgeCount).toBe(rowCount);

    // 13 raw SSE events merge to 5 display entries:
    //   1 user_input (the message we typed) + 1 merged text + tool_use + tool_result + complete
    // The key assertion: count is much less than the 13 raw events
    expect(badgeCount).toBeLessThan(13);
    expect(badgeCount).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// 2. User input badge
// ---------------------------------------------------------------------------

test.describe('User Input Badge', () => {

  test('user message shows "user" badge, not "agent"', async ({ page }) => {
    test.setTimeout(45_000);

    // Simple response: just a text reply + complete
    await page.route('**/api/invoke', async (route) => {
      await route.fulfill({
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
        body: buildSSE([
          { type: 'text', agent_id: 'eagle', agent_name: 'EAGLE', content: 'Hello!', timestamp: '2026-01-01T00:00:01Z' },
          { type: 'complete', agent_id: 'eagle', agent_name: 'EAGLE', metadata: { duration_ms: 1000 }, timestamp: '2026-01-01T00:00:02Z' },
        ]),
      });
    });

    await page.goto('http://localhost:3000/chat/', { waitUntil: 'domcontentloaded', timeout: 15_000 });

    const textarea = page.locator('textarea').first();
    await expect(textarea).toBeVisible({ timeout: 5_000 });
    await textarea.fill('hi there');
    await textarea.press('Enter');
    await page.waitForTimeout(5_000);

    // Agent Logs tab is active by default — click to ensure
    const logsTab = page.locator('button', { hasText: 'Agent Logs' });
    await expect(logsTab).toBeVisible({ timeout: 5_000 });
    await logsTab.click();
    await page.waitForTimeout(1_000);

    // Collect all badge labels in the timeline
    // Badges are uppercase <span> elements inside timeline rows
    const timelineRows = page.locator('[class*="border-l-"][class*="cursor-pointer"]');
    const rowCount = await timelineRows.count();
    const labels: string[] = [];
    for (let i = 0; i < rowCount; i++) {
      const badgeSpan = timelineRows.nth(i).locator('span[class*="uppercase"]').first();
      const text = await badgeSpan.textContent();
      if (text) labels.push(text.trim().toLowerCase());
    }

    // Must have at least one "user" badge (from the message we typed)
    expect(labels).toContain('user');

    // Must also have "agent" badges (from the SSE text response)
    expect(labels).toContain('agent');

    // The "user" badge should use the user_input color scheme (bg-[#E3F2FD])
    const userRow = timelineRows.filter({ hasText: /^user/i }).first();
    const userBadge = userRow.locator('span[class*="uppercase"]').first();
    const classes = await userBadge.getAttribute('class');
    expect(classes).toContain('#E3F2FD');

    // The "agent" badge should use a different color (bg-[#E8F0FE])
    const agentRow = timelineRows.filter({ hasText: /^agent/i }).first();
    const agentBadge = agentRow.locator('span[class*="uppercase"]').first();
    const agentClasses = await agentBadge.getAttribute('class');
    expect(agentClasses).toContain('#E8F0FE');
  });

  test('user message content appears in timeline summary', async ({ page }) => {
    test.setTimeout(45_000);

    await page.route('**/api/invoke', async (route) => {
      await route.fulfill({
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
        body: buildSSE([
          { type: 'text', agent_id: 'eagle', agent_name: 'EAGLE', content: 'Response text', timestamp: '2026-01-01T00:00:01Z' },
          { type: 'complete', agent_id: 'eagle', agent_name: 'EAGLE', metadata: {}, timestamp: '2026-01-01T00:00:02Z' },
        ]),
      });
    });

    await page.goto('http://localhost:3000/chat/', { waitUntil: 'domcontentloaded', timeout: 15_000 });

    const textarea = page.locator('textarea').first();
    await expect(textarea).toBeVisible({ timeout: 5_000 });
    await textarea.fill('my specific test message');
    await textarea.press('Enter');
    await page.waitForTimeout(5_000);

    // Agent Logs tab is active by default
    const logsTab = page.locator('button', { hasText: 'Agent Logs' });
    await expect(logsTab).toBeVisible({ timeout: 5_000 });
    await logsTab.click();
    await page.waitForTimeout(1_000);

    // The user's message text should appear in a timeline row
    const userRow = page.locator('[class*="border-l-"][class*="cursor-pointer"]', { hasText: 'my specific test message' });
    await expect(userRow).toBeVisible({ timeout: 5_000 });

    // That row should have the "user" badge
    const badge = userRow.locator('span[class*="uppercase"]').first();
    const badgeText = await badge.textContent();
    expect(badgeText?.trim().toLowerCase()).toBe('user');
  });
});
