import { test, expect } from '@playwright/test';
import path from 'path';

const SCREENSHOTS_DIR = path.resolve(__dirname, '../../screenshots');
const PROMPT = 'What is the simplified acquisition threshold and what procurement methods can I use below it?';

test('UC: Simple Acquisition - Simplified Acquisition Threshold', async ({ page }) => {
    test.setTimeout(180_000);

    const consoleErrors: string[] = [];
    const allLogs: string[] = [];

    page.on('console', (msg) => {
        const text = msg.text();
        allLogs.push(`[${msg.type()}] ${text}`);
        if (msg.type() === 'error') consoleErrors.push(text);
    });

    // === STEP 1: Open chat page ===
    console.log('=== STEP 1: Opening http://localhost:3000/chat ===');
    await page.goto('http://localhost:3000/chat', { waitUntil: 'networkidle', timeout: 30_000 });
    await page.waitForTimeout(2_000);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'uc-validate-sa-initial.png'), fullPage: true });
    console.log('Screenshot: uc-validate-sa-initial.png');

    // === STEP 2: Start a new chat ===
    console.log('=== STEP 2: Looking for New Chat button ===');
    // Check if there are existing messages
    const existingMessages = await page.locator('[data-message-role="assistant"], [data-message-role="user"]').count();
    if (existingMessages > 0) {
        console.log(`Found ${existingMessages} existing messages, looking for New Chat button`);
        const newChatBtn = page.locator('button:has-text("New"), button[title*="new" i], button[aria-label*="new" i]');
        if (await newChatBtn.first().isVisible({ timeout: 3_000 }).catch(() => false)) {
            await newChatBtn.first().click();
            await page.waitForTimeout(2_000);
            console.log('Clicked New Chat button');
        }
    }

    // === STEP 3: Find input and send message ===
    console.log('=== STEP 3: Finding chat input ===');
    const inputCandidates = [
        page.locator('textarea[placeholder*="EAGLE" i]'),
        page.locator('textarea[placeholder*="acquisition" i]'),
        page.locator('textarea').first(),
        page.locator('input[type="text"]').first(),
    ];

    let chatInput: any = null;
    for (const c of inputCandidates) {
        if (await c.isVisible({ timeout: 3_000 }).catch(() => false)) {
            chatInput = c;
            console.log('Found chat input');
            break;
        }
    }

    if (!chatInput) {
        console.log('ERROR: No chat input found');
        const bodyText = await page.locator('body').innerText().catch(() => '');
        console.log(`Body text (first 2000 chars): ${bodyText.substring(0, 2000)}`);
        await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'uc-validate-sa-ERROR.png'), fullPage: true });
        expect(chatInput).not.toBeNull();
        return;
    }

    // Check input is enabled
    const isDisabled = await chatInput.isDisabled();
    console.log(`Input disabled: ${isDisabled}`);

    await chatInput.fill(PROMPT);
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'uc-validate-sa-before-send.png'), fullPage: true });
    console.log('Screenshot: uc-validate-sa-before-send.png');

    // Send message
    await chatInput.press('Enter');
    console.log('Message sent via Enter key');

    // === STEP 4: Monitor streaming ===
    console.log('=== STEP 4: Monitoring streaming response ===');
    await page.waitForTimeout(2_000);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'uc-validate-sa-streaming.png'), fullPage: true });
    console.log('Screenshot: uc-validate-sa-streaming.png');

    // Poll for response completion (up to 120s)
    let responseText = '';
    let completed = false;
    for (let i = 0; i < 12; i++) {
        await page.waitForTimeout(10_000);
        console.log(`Polling for response... (${(i + 1) * 10}s elapsed)`);

        // Check if textarea is re-enabled (streaming done)
        const inputDisabled = await chatInput.isDisabled().catch(() => true);
        const placeholder = await chatInput.getAttribute('placeholder').catch(() => '');

        if (!inputDisabled && !placeholder?.includes('Waiting')) {
            console.log('Input re-enabled, streaming appears complete');
            completed = true;
            break;
        }
    }

    await page.waitForTimeout(2_000); // Extra buffer
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'uc-validate-sa-response.png'), fullPage: true });
    console.log('Screenshot: uc-validate-sa-response.png');

    // === STEP 5: Validate response ===
    console.log('=== STEP 5: Validating response content ===');
    const bodyText = await page.locator('body').innerText().catch(() => '');

    // Check for assistant response
    const hasResponse = bodyText.length > PROMPT.length + 200; // Should have substantial content beyond the prompt
    console.log(`Body text length: ${bodyText.length}`);

    // Extract keywords
    const has350k = bodyText.includes('350,000') || bodyText.includes('$350,000');
    const hasMicroPurchase = bodyText.toLowerCase().includes('micro-purchase') || bodyText.toLowerCase().includes('micro purchase');
    const has15k = bodyText.includes('15,000') || bodyText.includes('$15,000');
    const hasFAR = bodyText.includes('FAR');
    const hasPart13 = bodyText.includes('Part 13') || bodyText.includes('part 13');

    // Check for errors
    const errorBanner = await page.locator('.bg-red-50, .text-red-700, [role="alert"]').count();
    const hasErrorText = bodyText.toLowerCase().includes('error') && bodyText.toLowerCase().includes('failed');

    // Check input is re-enabled
    const inputReEnabled = !(await chatInput.isDisabled().catch(() => true));

    console.log('--- VALIDATION RESULTS ---');
    console.log(`Has assistant response: ${hasResponse}`);
    console.log(`Mentions $350,000 (SAT): ${has350k}`);
    console.log(`Mentions micro-purchase: ${hasMicroPurchase}`);
    console.log(`Mentions $15,000: ${has15k}`);
    console.log(`Mentions FAR: ${hasFAR}`);
    console.log(`Mentions Part 13: ${hasPart13}`);
    console.log(`Error banners visible: ${errorBanner}`);
    console.log(`Error text in body: ${hasErrorText}`);
    console.log(`Input re-enabled: ${inputReEnabled}`);

    // === STEP 6: Check for tool cards ===
    console.log('=== STEP 6: Checking for tool cards ===');
    const toolCardSelectors = [
        '[data-tool-card]',
        '[class*="tool-card"]',
        '[class*="tool-use"]',
        'text=query_compliance_matrix',
        'text=search_far',
        'text=Tool',
    ];

    let toolCardsFound = false;
    const toolNames: string[] = [];
    for (const sel of toolCardSelectors) {
        const count = await page.locator(sel).count();
        if (count > 0) {
            toolCardsFound = true;
            console.log(`Tool indicator found via "${sel}" (${count} elements)`);
        }
    }

    // Also check for tool names in the activity panel / logs area
    const knownTools = ['query_compliance_matrix', 'search_far', 'intake_specialist', 'compliance_specialist', 'document_specialist'];
    for (const tool of knownTools) {
        if (bodyText.includes(tool)) {
            toolNames.push(tool);
            console.log(`Tool found in body text: ${tool}`);
        }
    }

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'uc-validate-sa-tools.png'), fullPage: true });
    console.log('Screenshot: uc-validate-sa-tools.png');

    // === STEP 7: Session persistence ===
    console.log('=== STEP 7: Testing session persistence ===');
    await page.reload({ waitUntil: 'networkidle', timeout: 30_000 });
    await page.waitForTimeout(3_000);

    const bodyAfterReload = await page.locator('body').innerText().catch(() => '');
    const messagesPersistedUser = bodyAfterReload.includes('simplified acquisition threshold');
    const messagesPersistedAssistant = bodyAfterReload.length > 500;

    console.log(`User message persisted: ${messagesPersistedUser}`);
    console.log(`Assistant response persisted: ${messagesPersistedAssistant}`);

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'uc-validate-sa-reload.png'), fullPage: true });
    console.log('Screenshot: uc-validate-sa-reload.png');

    // === FINAL REPORT ===
    console.log('\n');
    console.log('================================================================');
    console.log('   UC SIMPLE ACQUISITION - VALIDATION REPORT');
    console.log('================================================================');
    console.log(`  Assistant response rendered:     ${hasResponse ? 'PASS' : 'FAIL'}`);
    console.log(`  Mentions $350,000 (SAT):         ${has350k ? 'PASS' : 'FAIL'}`);
    console.log(`  Mentions micro-purchase:          ${hasMicroPurchase ? 'PASS' : 'FAIL'}`);
    console.log(`  Mentions $15,000:                 ${has15k ? 'PASS' : 'FAIL'}`);
    console.log(`  Mentions FAR:                     ${hasFAR ? 'PASS' : 'FAIL'}`);
    console.log(`  Mentions Part 13:                 ${hasPart13 ? 'PASS' : 'FAIL'}`);
    console.log(`  No error banners:                 ${errorBanner === 0 ? 'PASS' : 'FAIL'}`);
    console.log(`  Input re-enabled:                 ${inputReEnabled ? 'PASS' : 'FAIL'}`);
    console.log(`  Tool cards visible:               ${toolCardsFound ? 'YES' : 'NO'}`);
    console.log(`  Tools detected:                   ${toolNames.length > 0 ? toolNames.join(', ') : 'none visible'}`);
    console.log(`  Session persistence (user msg):   ${messagesPersistedUser ? 'PASS' : 'FAIL'}`);
    console.log(`  Session persistence (assistant):  ${messagesPersistedAssistant ? 'PASS' : 'FAIL'}`);
    console.log(`  Console errors:                   ${consoleErrors.length}`);
    console.log('================================================================');

    // Print relevant body text excerpt (response portion)
    const promptIdx = bodyText.indexOf('simplified acquisition threshold');
    if (promptIdx > -1) {
        const responseExcerpt = bodyText.substring(promptIdx, promptIdx + 3000);
        console.log('\n=== RESPONSE EXCERPT (first 3000 chars from prompt match) ===');
        console.log(responseExcerpt);
        console.log('=== END EXCERPT ===');
    }

    // Log console errors
    if (consoleErrors.length > 0) {
        console.log('\n=== CONSOLE ERRORS ===');
        consoleErrors.slice(0, 20).forEach(e => console.log(`  ${e}`));
    }

    // Assertions (soft — report passes/fails)
    expect(hasResponse, 'Assistant response should be rendered').toBe(true);
    expect(hasFAR, 'Response should mention FAR').toBe(true);
    expect(inputReEnabled, 'Input should be re-enabled after response').toBe(true);
});
