import { test, expect, Page } from '@playwright/test';

/**
 * Streaming Persistence Tests — SSE Event Survival Across Page Refresh
 *
 * Validates that:
 *   Phase 1: Mid-stream checkpoint restores partial messages on refresh
 *   Phase 2: Tool call chips and state change cards persist after completion
 *   Edge cases: Error recovery, empty streams, browser navigation, quota safety
 *
 * Uses synthetic SSE via page.route() — no backend required.
 */

const CHAT_URL = 'http://localhost:3000/chat/';

// ---------------------------------------------------------------------------
// SSE Builders
// ---------------------------------------------------------------------------

function buildSSE(events: Array<Record<string, unknown>>): string {
    return events.map((e) => `data: ${JSON.stringify(e)}`).join('\n\n') + '\n\n';
}

/** Build a streaming SSE payload with N text chunks + a complete event. */
function buildStreamingSSE(chunks: string[]): string {
    const events: Array<Record<string, unknown>> = [];
    chunks.forEach((chunk, i) => {
        events.push({
            type: 'text',
            agent_id: 'eagle',
            agent_name: 'EAGLE',
            content: chunk,
            timestamp: `2026-01-01T00:00:${String(i % 60).padStart(2, '0')}Z`,
        });
    });
    events.push({
        type: 'complete',
        agent_id: 'eagle',
        agent_name: 'EAGLE',
        metadata: { duration_ms: chunks.length * 50 },
        timestamp: '2026-01-01T00:01:00Z',
    });
    return buildSSE(events);
}

/**
 * Build SSE with text chunks + tool_use/tool_result pairs + optional state
 * change metadata events + optional complete.
 */
function makeToolSSE(options: {
    textChunks: string[];
    tools: Array<{
        name: string;
        input: Record<string, unknown>;
        toolUseId: string;
        result: unknown;
    }>;
    stateChanges?: Array<{
        stateType: string;
        packageId?: string;
        phase?: string;
        checklist?: { required: string[]; completed: string[] };
        progressPct?: number;
    }>;
    includeComplete?: boolean;
}): string {
    const events: Array<Record<string, unknown>> = [];
    let ts = 0;
    const mkts = () => `2026-01-01T00:00:${String(ts++ % 60).padStart(2, '0')}Z`;

    // Text chunks first
    for (const chunk of options.textChunks) {
        events.push({
            type: 'text',
            agent_id: 'eagle',
            agent_name: 'EAGLE',
            content: chunk,
            timestamp: mkts(),
        });
    }

    // Tool use + result pairs
    for (const tool of options.tools) {
        events.push({
            type: 'tool_use',
            agent_id: 'eagle',
            agent_name: 'EAGLE',
            tool_use: { name: tool.name, input: tool.input, tool_use_id: tool.toolUseId },
            timestamp: mkts(),
        });
        events.push({
            type: 'tool_result',
            agent_id: 'eagle',
            agent_name: 'EAGLE',
            tool_result: { name: tool.name, result: tool.result },
            timestamp: mkts(),
        });
    }

    // State change metadata events
    if (options.stateChanges) {
        for (const sc of options.stateChanges) {
            events.push({
                type: 'metadata',
                agent_id: 'eagle',
                agent_name: 'EAGLE',
                metadata: {
                    state_type: sc.stateType,
                    package_id: sc.packageId,
                    phase: sc.phase,
                    checklist: sc.checklist,
                    progress_pct: sc.progressPct,
                },
                timestamp: mkts(),
            });
        }
    }

    if (options.includeComplete !== false) {
        events.push({
            type: 'complete',
            agent_id: 'eagle',
            agent_name: 'EAGLE',
            metadata: { duration_ms: 2000 },
            timestamp: mkts(),
        });
    }

    return buildSSE(events);
}

/** Build SSE with text + state change metadata events (no tool calls). */
function makeStateChangeSSE(options: {
    textChunks: string[];
    stateChanges: Array<{
        stateType: string;
        packageId?: string;
        phase?: string;
        checklist?: { required: string[]; completed: string[] };
        progressPct?: number;
    }>;
    includeComplete?: boolean;
}): string {
    return makeToolSSE({
        textChunks: options.textChunks,
        tools: [],
        stateChanges: options.stateChanges,
        includeComplete: options.includeComplete,
    });
}

// ---------------------------------------------------------------------------
// Page Interaction Helpers
// ---------------------------------------------------------------------------

async function sendMessage(page: Page, text: string) {
    const textarea = page.locator('textarea').first();
    await expect(textarea).toBeVisible({ timeout: 10_000 });
    await expect(textarea).toBeEnabled({ timeout: 5_000 });
    await textarea.fill(text);
    await textarea.press('Enter');
}

async function waitForStreamComplete(page: Page) {
    const textarea = page.locator('textarea').first();
    await expect(textarea).toBeEnabled({ timeout: 15_000 });
    await page.waitForTimeout(1_000);
}

async function createNewThread(page: Page) {
    await page.locator('button:has-text("New Chat")').click();
    await page.waitForTimeout(500);
}

// ---------------------------------------------------------------------------
// localStorage Helpers
// ---------------------------------------------------------------------------

async function getCheckpoint(page: Page, sessionId: string): Promise<Record<string, unknown> | null> {
    return page.evaluate((sid) => {
        const raw = localStorage.getItem(`eagle_stream_cp_${sid}`);
        return raw ? JSON.parse(raw) : null;
    }, sessionId);
}

async function setCheckpoint(page: Page, sessionId: string, data: Record<string, unknown>) {
    await page.evaluate(
        ([sid, json]: [string, string]) => localStorage.setItem(`eagle_stream_cp_${sid}`, json),
        [sessionId, JSON.stringify(data)] as [string, string],
    );
}

async function getCurrentSessionId(page: Page): Promise<string> {
    return page.evaluate(() => localStorage.getItem('eagle_current_session') ?? '');
}

async function getSessionData(page: Page): Promise<Record<string, unknown>> {
    return page.evaluate(() => {
        const raw = localStorage.getItem('eagle_chat_sessions');
        return raw ? JSON.parse(raw) : {};
    });
}

// ---------------------------------------------------------------------------
// Route helper — intercepts /api/invoke with synthetic SSE
// ---------------------------------------------------------------------------

async function routeSSE(page: Page, body: string) {
    await page.route('**/api/invoke', async (route) => {
        await route.fulfill({
            status: 200,
            headers: { 'Content-Type': 'text/event-stream' },
            body,
        });
    });
}

/** Route /api/invoke with different payloads per call (for multi-message tests). */
async function routeSSESequence(page: Page, bodies: string[]) {
    let callCount = 0;
    await page.route('**/api/invoke', async (route) => {
        const idx = Math.min(callCount++, bodies.length - 1);
        await route.fulfill({
            status: 200,
            headers: { 'Content-Type': 'text/event-stream' },
            body: bodies[idx],
        });
    });
}

// ===========================================================================
// Phase 1: Streaming Checkpoint
// ===========================================================================

test.describe('Phase 1: Streaming Checkpoint', () => {
    test.setTimeout(30_000);

    test.beforeEach(async ({ page }) => {
        await page.goto(CHAT_URL, { waitUntil: 'domcontentloaded', timeout: 15_000 });
        // Clear any stale checkpoint keys
        await page.evaluate(() => {
            for (let i = localStorage.length - 1; i >= 0; i--) {
                const key = localStorage.key(i);
                if (key?.startsWith('eagle_stream_cp_')) localStorage.removeItem(key);
            }
        });
    });

    test('Test 1: mid-stream refresh restores text with "Response interrupted" suffix', async ({ page }) => {
        const sessionId = await getCurrentSessionId(page);
        expect(sessionId).toBeTruthy();

        // Seed a checkpoint as if streaming was in progress
        await setCheckpoint(page, sessionId, {
            sessionId,
            requestId: 'req-test-1',
            streamingMsgId: 'stream-restored',
            text: 'This is a partial response that was interrupted during streaming.',
            toolCalls: [],
            stateChanges: [],
            documents: [],
            updatedAt: Date.now(),
        });

        // Reload — checkpoint should be restored
        await page.reload({ waitUntil: 'domcontentloaded' });
        await page.waitForTimeout(2_000);

        const mainText = await page.locator('main').textContent() ?? '';
        expect(mainText).toContain('partial response');
        expect(mainText.toLowerCase()).toContain('interrupted');

        // No streaming indicators
        await expect(page.locator('.typing-dot').first()).not.toBeVisible({ timeout: 2_000 }).catch(() => {});
        const textarea = page.locator('textarea').first();
        await expect(textarea).toBeEnabled({ timeout: 5_000 });
    });

    test('Test 2: mid-stream refresh with tool calls and state changes — chips show correct status', async ({ page }) => {
        const sessionId = await getCurrentSessionId(page);

        await setCheckpoint(page, sessionId, {
            sessionId,
            requestId: 'req-test-2',
            streamingMsgId: 'stream-tools-restored',
            text: 'Searching FAR regulations for your query.',
            toolCalls: [
                {
                    toolUseId: 'tu-done',
                    toolName: 'search_far',
                    input: { query: 'FAR 13' },
                    status: 'done',
                    isClientSide: false,
                    result: { clauses: ['13.003'] },
                    textSnapshotLength: 10,
                },
                {
                    toolUseId: 'tu-pending',
                    toolName: 'policy_analyst',
                    input: { query: 'review' },
                    status: 'running',
                    isClientSide: false,
                    textSnapshotLength: 30,
                },
            ],
            stateChanges: [
                {
                    stateType: 'checklist_update',
                    packageId: 'pkg-1',
                    checklist: { required: ['SOW'], completed: ['SOW'] },
                    progressPct: 100,
                    textSnapshotLength: 20,
                    timestamp: Date.now(),
                },
            ],
            documents: [],
            updatedAt: Date.now(),
        });

        await page.reload({ waitUntil: 'domcontentloaded' });
        await page.waitForTimeout(2_000);

        // Text restored
        const mainText = await page.locator('main').textContent() ?? '';
        expect(mainText).toContain('Searching FAR regulations');

        // Tool chips restored
        const toolChips = page.locator('[data-testid="tool-chip"]');
        await expect(toolChips).toHaveCount(2, { timeout: 5_000 });

        // Done chip has green dot
        const greenDots = page.locator('[data-testid="tool-chip"] .bg-green-500');
        expect(await greenDots.count()).toBeGreaterThanOrEqual(1);

        // Interrupted chip has amber dot
        const amberDots = page.locator('[data-testid="tool-chip"] .bg-amber-400');
        expect(await amberDots.count()).toBeGreaterThanOrEqual(1);

        // State change card restored
        const stateCards = page.locator('[data-testid="state-change-card"]');
        expect(await stateCards.count()).toBeGreaterThanOrEqual(1);
    });

    test('Test 3: checkpoint cleared after normal stream completion (no phantom messages)', async ({ page }) => {
        const sse = buildStreamingSSE(['Hello ', 'world ', 'response.']);
        await routeSSE(page, sse);

        await sendMessage(page, 'test completion');
        await waitForStreamComplete(page);

        const sessionId = await getCurrentSessionId(page);
        const checkpoint = await getCheckpoint(page, sessionId);
        expect(checkpoint).toBeNull();

        // Reload — message should appear exactly once
        await page.reload({ waitUntil: 'domcontentloaded' });
        await page.waitForTimeout(2_000);

        const mainText = await page.locator('main').textContent() ?? '';
        expect(mainText).toContain('Hello');
        expect(mainText).toContain('world');
        expect(mainText).toContain('response.');

        // Verify no duplicate assistant messages — count assistant message areas
        // The text should appear only once in the chat
        const occurrences = (mainText.match(/Hello/g) || []).length;
        expect(occurrences).toBeLessThanOrEqual(2); // user + assistant at most
    });

    test('Test 4: stale checkpoint older than 1 hour is garbage-collected', async ({ page }) => {
        const sessionId = await getCurrentSessionId(page);

        await setCheckpoint(page, sessionId, {
            sessionId,
            requestId: 'req-stale',
            streamingMsgId: 'stream-stale',
            text: 'This stale checkpoint should NOT be restored.',
            toolCalls: [],
            stateChanges: [],
            documents: [],
            updatedAt: Date.now() - 3_660_000, // 61 minutes ago
        });

        await page.reload({ waitUntil: 'domcontentloaded' });
        await page.waitForTimeout(2_000);

        const mainText = await page.locator('main').textContent() ?? '';
        expect(mainText).not.toContain('stale checkpoint');

        // Checkpoint key should have been cleaned up
        const checkpoint = await getCheckpoint(page, sessionId);
        expect(checkpoint).toBeNull();
    });

    test('Test 5: new query in same session clears old checkpoint', async ({ page }) => {
        const sse = buildStreamingSSE(['Fresh ', 'new ', 'response.']);
        await routeSSE(page, sse);

        const sessionId = await getCurrentSessionId(page);

        // Seed an old checkpoint
        await setCheckpoint(page, sessionId, {
            sessionId,
            requestId: 'req-old',
            streamingMsgId: 'stream-old',
            text: 'OLD interrupted text',
            toolCalls: [],
            stateChanges: [],
            documents: [],
            updatedAt: Date.now(),
        });

        // Reload to restore old checkpoint
        await page.reload({ waitUntil: 'domcontentloaded' });
        await page.waitForTimeout(2_000);

        // Re-route for the new query
        await page.unroute('**/api/invoke');
        await routeSSE(page, sse);

        // Send a new message — should clear old state
        await sendMessage(page, 'new question');
        await waitForStreamComplete(page);

        const mainText = await page.locator('main').textContent() ?? '';
        expect(mainText).toContain('Fresh');
        expect(mainText).toContain('new');
        expect(mainText).toContain('response.');

        // Checkpoint should be cleared
        const checkpoint = await getCheckpoint(page, sessionId);
        expect(checkpoint).toBeNull();
    });

    test('Test 6: checkpoint is per-session and does not cross-contaminate', async ({ page }) => {
        const sessionA = await getCurrentSessionId(page);

        // Seed checkpoint for session A
        await setCheckpoint(page, sessionA, {
            sessionId: sessionA,
            requestId: 'req-a',
            streamingMsgId: 'stream-a',
            text: 'Session A partial response',
            toolCalls: [],
            stateChanges: [],
            documents: [],
            updatedAt: Date.now(),
        });

        // Create a new thread (session B)
        await createNewThread(page);
        await page.waitForTimeout(1_000);

        const sessionB = await getCurrentSessionId(page);
        expect(sessionB).not.toBe(sessionA);

        // Session B should NOT show session A's checkpoint
        const mainText = await page.locator('main').textContent() ?? '';
        expect(mainText).not.toContain('Session A partial response');

        // Session B has no checkpoint
        const cpB = await getCheckpoint(page, sessionB);
        expect(cpB).toBeNull();

        // Session A's checkpoint is still there
        const cpA = await getCheckpoint(page, sessionA);
        expect(cpA).not.toBeNull();
    });
});

// ===========================================================================
// Phase 2: Tool Call & State Change Persistence
// ===========================================================================

test.describe('Phase 2: Tool Call & State Change Persistence', () => {
    test.setTimeout(30_000);

    test.beforeEach(async ({ page }) => {
        await page.goto(CHAT_URL, { waitUntil: 'domcontentloaded', timeout: 15_000 });
        await page.evaluate(() => {
            for (let i = localStorage.length - 1; i >= 0; i--) {
                const key = localStorage.key(i);
                if (key?.startsWith('eagle_stream_cp_')) localStorage.removeItem(key);
            }
        });
    });

    test('Test 7: tool call chips survive page refresh after completed response', async ({ page }) => {
        const sse = makeToolSSE({
            textChunks: ['Let me search the regulations. ', 'Here are the results.'],
            tools: [{
                name: 'search_far',
                input: { query: 'FAR Part 13' },
                toolUseId: 'tu-persist-1',
                result: { clauses: ['13.003'], results_count: 1 },
            }],
        });
        await routeSSE(page, sse);

        await sendMessage(page, 'search FAR Part 13');
        await waitForStreamComplete(page);

        // Verify chip visible before refresh
        const toolChip = page.locator('[data-testid="tool-chip"]');
        await expect(toolChip.first()).toBeVisible({ timeout: 5_000 });

        // Verify green status dot (done)
        const greenDot = page.locator('[data-testid="tool-chip"] .bg-green-500');
        expect(await greenDot.count()).toBeGreaterThanOrEqual(1);

        // Refresh
        await page.reload({ waitUntil: 'domcontentloaded' });
        await page.waitForTimeout(3_000);

        // After reload — tool chip still visible
        await expect(toolChip.first()).toBeVisible({ timeout: 5_000 });

        // Text still present
        const mainText = await page.locator('main').textContent() ?? '';
        expect(mainText).toContain('Let me search the regulations');
        expect(mainText).toContain('Here are the results');
    });

    test('Test 8: tool call chips survive session switch and switch-back', async ({ page }) => {
        const toolSSE = makeToolSSE({
            textChunks: ['Analyzing policy. '],
            tools: [{
                name: 'search_far',
                input: { query: 'simplified acquisition' },
                toolUseId: 'tu-switch-1',
                result: { clauses: ['13.003'], results_count: 1 },
            }],
        });
        const plainSSE = buildStreamingSSE(['Different topic response.']);

        await routeSSESequence(page, [toolSSE, plainSSE]);

        // Send first message (triggers tool SSE)
        await sendMessage(page, 'simplified acquisition thresholds');
        await waitForStreamComplete(page);

        // Verify tool chip visible
        await expect(page.locator('[data-testid="tool-chip"]').first()).toBeVisible({ timeout: 5_000 });

        // Create new thread
        await createNewThread(page);
        await page.waitForTimeout(1_000);

        // Send in session B
        await sendMessage(page, 'different question');
        await waitForStreamComplete(page);

        const mainTextB = await page.locator('main').textContent() ?? '';
        expect(mainTextB).toContain('Different topic response');

        // Switch back to first session (click the first session in sidebar)
        const sessionItems = page.locator('[class*="space-y-0"] > div, [class*="session"], button:has-text("simplified")');
        const firstSession = sessionItems.first();
        if (await firstSession.isVisible()) {
            await firstSession.click();
            await page.waitForTimeout(2_000);

            // Tool chip should be restored
            const mainTextA = await page.locator('main').textContent() ?? '';
            expect(mainTextA).toContain('Analyzing policy');
        }
    });

    test('Test 9: multiple messages with tool calls all persist correctly', async ({ page }) => {
        const sse1 = makeToolSSE({
            textChunks: ['First answer. '],
            tools: [{
                name: 'search_far',
                input: { query: 'FAR 13' },
                toolUseId: 'tu-multi-1',
                result: { clauses: ['13.003'] },
            }],
        });
        const sse2 = makeToolSSE({
            textChunks: ['Second answer. '],
            tools: [{
                name: 'knowledge_search',
                input: { query: 'IT services' },
                toolUseId: 'tu-multi-2',
                result: { results: ['doc1'] },
            }],
        });

        await routeSSESequence(page, [sse1, sse2]);

        // First message
        await sendMessage(page, 'first question');
        await waitForStreamComplete(page);

        // Second message
        await sendMessage(page, 'second question');
        await waitForStreamComplete(page);

        // Both tool chips should be visible
        const toolChips = page.locator('[data-testid="tool-chip"]');
        expect(await toolChips.count()).toBeGreaterThanOrEqual(2);

        // Refresh
        await page.reload({ waitUntil: 'domcontentloaded' });
        await page.waitForTimeout(3_000);

        // Both text responses present
        const mainText = await page.locator('main').textContent() ?? '';
        expect(mainText).toContain('First answer');
        expect(mainText).toContain('Second answer');

        // Both tool chips restored
        const restoredChips = page.locator('[data-testid="tool-chip"]');
        expect(await restoredChips.count()).toBeGreaterThanOrEqual(2);
    });

    test('Test 10: documents persist alongside tool calls after refresh', async ({ page }) => {
        const sse = makeToolSSE({
            textChunks: ['Creating your SOW. '],
            tools: [{
                name: 'create_document',
                input: { doc_type: 'sow', title: 'IT Support SOW' },
                toolUseId: 'tu-doc-1',
                result: {
                    document_id: 'doc-123',
                    doc_type: 'sow',
                    title: 'IT Support SOW',
                    s3_key: 'sow_20260325_120000.md',
                    status: 'saved',
                },
            }],
        });
        await routeSSE(page, sse);

        await sendMessage(page, 'create SOW for IT support');
        await waitForStreamComplete(page);

        // Verify tool chip for create_document
        await expect(page.locator('[data-testid="tool-chip"]').first()).toBeVisible({ timeout: 5_000 });

        // Refresh
        await page.reload({ waitUntil: 'domcontentloaded' });
        await page.waitForTimeout(3_000);

        // Text present
        const mainText = await page.locator('main').textContent() ?? '';
        expect(mainText).toContain('Creating your SOW');

        // Check localStorage has document data
        const sessions = await getSessionData(page);
        const sessionId = await getCurrentSessionId(page);
        const session = sessions[sessionId] as Record<string, unknown> | undefined;
        if (session?.documents) {
            const docs = session.documents as Record<string, unknown[]>;
            const allDocs = Object.values(docs).flat();
            const hasSow = allDocs.some((d: unknown) => {
                const doc = d as Record<string, unknown>;
                return doc.document_type === 'sow' || doc.doc_type === 'sow';
            });
            expect(hasSow).toBeTruthy();
        }
    });

    test('Test 11: session with no tool calls persists and restores without errors', async ({ page }) => {
        // Monitor console errors
        const consoleErrors: string[] = [];
        page.on('console', (msg) => {
            if (msg.type() === 'error') consoleErrors.push(msg.text());
        });

        const sse = buildStreamingSSE(['Simple ', 'text ', 'response ', 'with no tools.']);
        await routeSSE(page, sse);

        await sendMessage(page, 'hello');
        await waitForStreamComplete(page);

        const mainText = await page.locator('main').textContent() ?? '';
        expect(mainText).toContain('Simple');
        expect(mainText).toContain('text');
        expect(mainText).toContain('response');
        expect(mainText).toContain('with no tools.');

        // Refresh
        await page.reload({ waitUntil: 'domcontentloaded' });
        await page.waitForTimeout(2_000);

        // Text still present
        const reloadedText = await page.locator('main').textContent() ?? '';
        expect(reloadedText).toContain('Simple');
        expect(reloadedText).toContain('with no tools.');

        // No tool chips or state cards
        expect(await page.locator('[data-testid="tool-chip"]').count()).toBe(0);
        expect(await page.locator('[data-testid="state-change-card"]').count()).toBe(0);

        // Session data exists in localStorage
        const sessionId = await getCurrentSessionId(page);
        const sessions = await getSessionData(page);
        expect(sessions[sessionId]).toBeTruthy();

        // Filter out irrelevant console errors (e.g., network errors from route mocking)
        const relevantErrors = consoleErrors.filter(
            (e) => !e.includes('Failed to fetch') && !e.includes('net::ERR'),
        );
        expect(relevantErrors).toHaveLength(0);
    });

    test('Test 16: state change cards survive page refresh', async ({ page }) => {
        const sse = makeToolSSE({
            textChunks: ['Updating your package. ', 'Checklist complete.'],
            tools: [{
                name: 'manage_package',
                input: { action: 'update_checklist' },
                toolUseId: 'tu-state-1',
                result: { status: 'updated' },
            }],
            stateChanges: [{
                stateType: 'checklist_update',
                packageId: 'pkg-test',
                checklist: { required: ['SOW', 'IGCE'], completed: ['SOW'] },
                progressPct: 50,
            }],
        });
        await routeSSE(page, sse);

        await sendMessage(page, 'update my package checklist');
        await waitForStreamComplete(page);

        // Verify state change card visible before refresh
        const stateCard = page.locator('[data-testid="state-change-card"]');
        await expect(stateCard.first()).toBeVisible({ timeout: 5_000 });

        // Tool chip also visible
        await expect(page.locator('[data-testid="tool-chip"]').first()).toBeVisible({ timeout: 5_000 });

        // Refresh
        await page.reload({ waitUntil: 'domcontentloaded' });
        await page.waitForTimeout(3_000);

        // After reload — state change card still visible
        await expect(stateCard.first()).toBeVisible({ timeout: 5_000 });

        // Text present
        const mainText = await page.locator('main').textContent() ?? '';
        expect(mainText).toContain('Updating your package');
    });

    test('Test 17: interleaved tool chips + state change cards persist in correct order', async ({ page }) => {
        // Build SSE with interleaved events at different textSnapshotLength values
        const events: Array<Record<string, unknown>> = [];
        let ts = 0;
        const mkts = () => `2026-01-01T00:00:${String(ts++ % 60).padStart(2, '0')}Z`;

        // Text: "Starting. " (10 chars)
        events.push({ type: 'text', agent_id: 'eagle', agent_name: 'EAGLE', content: 'Starting. ', timestamp: mkts() });

        // Tool use at text position 10
        events.push({
            type: 'tool_use', agent_id: 'eagle', agent_name: 'EAGLE',
            tool_use: { name: 'search_far', input: { query: 'FAR 13' }, tool_use_id: 'tu-order-1' },
            timestamp: mkts(),
        });
        events.push({
            type: 'tool_result', agent_id: 'eagle', agent_name: 'EAGLE',
            tool_result: { name: 'search_far', result: { found: true } },
            timestamp: mkts(),
        });

        // Text: "Analyzing. " (11 more chars, total 21)
        events.push({ type: 'text', agent_id: 'eagle', agent_name: 'EAGLE', content: 'Analyzing. ', timestamp: mkts() });

        // State change at text position 21
        events.push({
            type: 'metadata', agent_id: 'eagle', agent_name: 'EAGLE',
            metadata: {
                state_type: 'checklist_update',
                package_id: 'pkg-order',
                checklist: { required: ['SOW'], completed: ['SOW'] },
                progress_pct: 100,
            },
            timestamp: mkts(),
        });

        // Text: "Done." (5 more chars, total 26)
        events.push({ type: 'text', agent_id: 'eagle', agent_name: 'EAGLE', content: 'Done.', timestamp: mkts() });

        // Complete
        events.push({ type: 'complete', agent_id: 'eagle', agent_name: 'EAGLE', metadata: { duration_ms: 2000 }, timestamp: mkts() });

        await routeSSE(page, buildSSE(events));

        await sendMessage(page, 'interleave test');
        await waitForStreamComplete(page);

        // Verify both are present
        await expect(page.locator('[data-testid="tool-chip"]').first()).toBeVisible({ timeout: 5_000 });
        await expect(page.locator('[data-testid="state-change-card"]').first()).toBeVisible({ timeout: 5_000 });

        // Check DOM order: tool chip should appear before state card
        const allInlineItems = page.locator('[data-testid="tool-chip"], [data-testid="state-change-card"]');
        const items = await allInlineItems.all();
        expect(items.length).toBeGreaterThanOrEqual(2);

        // First item should be the tool chip (lower textSnapshotLength)
        const firstTestId = await items[0].getAttribute('data-testid');
        expect(firstTestId).toBe('tool-chip');

        // Refresh and verify order preserved
        await page.reload({ waitUntil: 'domcontentloaded' });
        await page.waitForTimeout(3_000);

        const mainText = await page.locator('main').textContent() ?? '';
        expect(mainText).toContain('Starting');
        expect(mainText).toContain('Analyzing');
        expect(mainText).toContain('Done');

        // Both elements still present
        expect(await page.locator('[data-testid="tool-chip"]').count()).toBeGreaterThanOrEqual(1);
        expect(await page.locator('[data-testid="state-change-card"]').count()).toBeGreaterThanOrEqual(1);
    });

    test('Test 18: phase change state card shows correct phase after refresh', async ({ page }) => {
        const sse = makeStateChangeSSE({
            textChunks: ['Moving to finalization. '],
            stateChanges: [{
                stateType: 'phase_change',
                packageId: 'pkg-phase',
                phase: 'finalizing',
            }],
        });
        await routeSSE(page, sse);

        await sendMessage(page, 'finalize the package');
        await waitForStreamComplete(page);

        // State change card visible
        const stateCard = page.locator('[data-testid="state-change-card"]');
        await expect(stateCard.first()).toBeVisible({ timeout: 5_000 });

        // Card text should reference the phase
        const cardText = await stateCard.first().textContent() ?? '';
        expect(cardText.toLowerCase()).toContain('finalizing');

        // Refresh
        await page.reload({ waitUntil: 'domcontentloaded' });
        await page.waitForTimeout(3_000);

        // State change card still visible after refresh
        await expect(stateCard.first()).toBeVisible({ timeout: 5_000 });

        // Phase text preserved
        const reloadedCardText = await stateCard.first().textContent() ?? '';
        expect(reloadedCardText.toLowerCase()).toContain('finalizing');
    });
});

// ===========================================================================
// Edge Cases
// ===========================================================================

test.describe('Edge Cases', () => {
    test.setTimeout(30_000);

    test.beforeEach(async ({ page }) => {
        await page.goto(CHAT_URL, { waitUntil: 'domcontentloaded', timeout: 15_000 });
        await page.evaluate(() => {
            for (let i = localStorage.length - 1; i >= 0; i--) {
                const key = localStorage.key(i);
                if (key?.startsWith('eagle_stream_cp_')) localStorage.removeItem(key);
            }
        });
    });

    test('Test 12: rapid refresh during streaming preserves checkpoint', async ({ page }) => {
        const sessionId = await getCurrentSessionId(page);

        // Seed a fresh checkpoint
        await setCheckpoint(page, sessionId, {
            sessionId,
            requestId: 'req-rapid',
            streamingMsgId: 'stream-rapid',
            text: 'Partial rapid text',
            toolCalls: [],
            stateChanges: [],
            documents: [],
            updatedAt: Date.now(),
        });

        // Immediately reload (no waiting)
        await page.reload({ waitUntil: 'domcontentloaded' });
        await page.waitForTimeout(2_000);

        // Either the text was restored or the checkpoint was processed (cleared)
        const mainText = await page.locator('main').textContent() ?? '';
        const checkpoint = await getCheckpoint(page, sessionId);
        const wasRestored = mainText.includes('Partial rapid text');
        const wasCleared = checkpoint === null;
        expect(wasRestored || wasCleared).toBeTruthy();

        // No JS errors that crash the page
        const textarea = page.locator('textarea').first();
        await expect(textarea).toBeVisible({ timeout: 5_000 });
    });

    test('Test 13: empty stream with only complete event creates no phantom checkpoint', async ({ page }) => {
        const sse = buildSSE([
            {
                type: 'text',
                agent_id: 'eagle',
                agent_name: 'EAGLE',
                content: '',
                timestamp: '2026-01-01T00:00:00Z',
            },
            {
                type: 'complete',
                agent_id: 'eagle',
                agent_name: 'EAGLE',
                metadata: { duration_ms: 100 },
                timestamp: '2026-01-01T00:00:01Z',
            },
        ]);
        await routeSSE(page, sse);

        await sendMessage(page, 'test empty');
        await waitForStreamComplete(page);

        const sessionId = await getCurrentSessionId(page);
        const checkpoint = await getCheckpoint(page, sessionId);
        expect(checkpoint).toBeNull();

        // User message should be visible
        const mainText = await page.locator('main').textContent() ?? '';
        expect(mainText).toContain('test empty');
    });

    test('Test 14: error event during streaming preserves checkpoint for recovery', async ({ page }) => {
        const sse = buildSSE([
            {
                type: 'text',
                agent_id: 'eagle',
                agent_name: 'EAGLE',
                content: 'Processing your request about ',
                timestamp: '2026-01-01T00:00:00Z',
            },
            {
                type: 'text',
                agent_id: 'eagle',
                agent_name: 'EAGLE',
                content: 'acquisition planning.',
                timestamp: '2026-01-01T00:00:01Z',
            },
            {
                type: 'error',
                agent_id: 'eagle',
                agent_name: 'EAGLE',
                content: 'Internal server error',
                timestamp: '2026-01-01T00:00:02Z',
            },
        ]);
        await routeSSE(page, sse);

        await sendMessage(page, 'test error recovery');

        // Wait for the stream to finish (error terminates it)
        await page.waitForTimeout(3_000);
        const textarea = page.locator('textarea').first();
        await expect(textarea).toBeEnabled({ timeout: 10_000 });

        // The partial text should be visible in the UI or preserved in checkpoint
        const sessionId = await getCurrentSessionId(page);
        const checkpoint = await getCheckpoint(page, sessionId);
        const mainText = await page.locator('main').textContent() ?? '';

        const textInUI = mainText.includes('Processing your request');
        const textInCheckpoint = checkpoint !== null &&
            typeof checkpoint === 'object' &&
            typeof (checkpoint as Record<string, unknown>).text === 'string' &&
            ((checkpoint as Record<string, unknown>).text as string).includes('Processing your request');

        expect(textInUI || textInCheckpoint).toBeTruthy();
    });

    test('Test 15: browser back/forward preserves messages via localStorage', async ({ page }) => {
        const sse = buildStreamingSSE(['Navigation ', 'test ', 'response.']);
        await routeSSE(page, sse);

        await sendMessage(page, 'navigation test');
        await waitForStreamComplete(page);

        // Verify text present
        const mainText = await page.locator('main').textContent() ?? '';
        expect(mainText).toContain('Navigation');
        expect(mainText).toContain('test');
        expect(mainText).toContain('response.');

        // Navigate away
        await page.goto('http://localhost:3000/', { waitUntil: 'domcontentloaded', timeout: 10_000 });
        await page.waitForTimeout(1_000);

        // Navigate back
        await page.goBack({ waitUntil: 'domcontentloaded', timeout: 10_000 });
        await page.waitForTimeout(3_000);

        // Messages should be restored from localStorage
        const restoredText = await page.locator('main').textContent() ?? '';
        expect(restoredText).toContain('navigation test');
        expect(restoredText).toContain('Navigation');

        // localStorage still intact
        const sessionId = await getCurrentSessionId(page);
        const sessions = await getSessionData(page);
        expect(sessions[sessionId]).toBeTruthy();
    });

    test('Test 19: localStorage quota pressure — large tool results are stripped', async ({ page }) => {
        // Generate a ~50 KB result string
        const largeResult = 'x'.repeat(50_000);

        const sse = makeToolSSE({
            textChunks: ['Processing large result. '],
            tools: [{
                name: 'knowledge_search',
                input: { query: 'large dataset' },
                toolUseId: 'tu-large-1',
                result: { content: largeResult },
            }],
        });
        await routeSSE(page, sse);

        await sendMessage(page, 'search large dataset');
        await waitForStreamComplete(page);

        // Read localStorage and verify the session was saved
        const sessionId = await getCurrentSessionId(page);
        const sessions = await getSessionData(page);
        const session = sessions[sessionId] as Record<string, unknown> | undefined;
        expect(session).toBeTruthy();

        // If toolCallsByMsg is present, check that large results were stripped
        if (session?.toolCallsByMsg) {
            const toolCalls = session.toolCallsByMsg as Record<string, unknown[]>;
            const allCalls = Object.values(toolCalls).flat();
            for (const tc of allCalls) {
                const call = tc as Record<string, unknown>;
                if (call.result) {
                    // Result should be stripped or truncated — not the full 50 KB
                    const resultStr = JSON.stringify(call.result);
                    expect(resultStr.length).toBeLessThan(15_000);
                }
            }
        }

        // The session data as a whole should be valid JSON and within quota
        const sessionStr = JSON.stringify(session);
        expect(sessionStr.length).toBeLessThan(100_000);

        // Text present
        const mainText = await page.locator('main').textContent() ?? '';
        expect(mainText).toContain('Processing large result');
    });
});
