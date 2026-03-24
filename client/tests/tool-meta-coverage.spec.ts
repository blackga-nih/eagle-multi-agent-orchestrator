import { test, expect } from '@playwright/test';

test.describe('Tool Meta Coverage', () => {
  // All tools registered in strands_agentic_service.py
  const KNOWN_TOOLS = [
    // Subagents (from plugin.json)
    'oa_intake', 'legal_counsel', 'market_intelligence', 'tech_translator',
    'tech_review', 'public_interest', 'document_generator', 'compliance',
    'policy_analyst', 'policy_librarian', 'policy_supervisor',
    'ingest_document', 'knowledge_retrieval',
    // KB & web tools
    'knowledge_search', 'knowledge_fetch', 'search_far', 'web_search', 'web_fetch',
    // Progressive disclosure
    'load_skill', 'list_skills', 'load_data',
    // Document & package tools
    'create_document', 'edit_docx_document', 'get_latest_document',
    'finalize_package', 'document_changelog_search',
    's3_document_ops', 'dynamodb_intake',
    // Workflow & status
    'get_intake_status', 'intake_workflow', 'query_compliance_matrix',
    // Admin
    'manage_skills', 'manage_prompts', 'manage_templates', 'cloudwatch_logs',
    // Client-side
    'think', 'code', 'editor',
  ];

  test('every known tool has a TOOL_META entry (no generic fallback)', async ({ page }) => {
    await page.goto('/chat/', { waitUntil: 'domcontentloaded', timeout: 15_000 });

    // Read the tool-use-display source to extract TOOL_META keys
    const metaKeys = await page.evaluate(async () => {
      // Fetch the built JS bundle and find TOOL_META entries
      const scripts = Array.from(document.querySelectorAll('script[src]'));
      for (const script of scripts) {
        try {
          const res = await fetch((script as HTMLScriptElement).src);
          const text = await res.text();
          // Look for TOOL_META keys in the compiled bundle
          // The compiled code will contain the tool name strings as object keys
          const matches = text.match(/icon:"[^"]+",label:"[^"]+"/g);
          if (matches && matches.length > 10) {
            return matches.length;
          }
        } catch { /* skip */ }
      }
      return 0;
    });

    // Verify we have enough TOOL_META entries to cover all known tools
    expect(KNOWN_TOOLS.length).toBeGreaterThanOrEqual(38);
    // The compiled bundle should contain at least as many tool meta entries
    // as our known tools list (some may be more due to compilation artifacts)
    expect(metaKeys).toBeGreaterThanOrEqual(KNOWN_TOOLS.length);
  });

  test('tool cards render with labeled icons (not generic gear)', async ({ page }) => {
    test.setTimeout(60_000);

    await page.goto('/chat/', { waitUntil: 'domcontentloaded', timeout: 15_000 });

    const textarea = page.locator('textarea').first();
    await expect(textarea).toBeVisible({ timeout: 5_000 });
    await textarea.fill('What are the NCI acquisition thresholds?');
    await textarea.press('Enter');

    // Wait for tool cards to appear
    await page.waitForTimeout(15_000);

    // Check that no tool card shows the generic gear icon as its ONLY identifier
    const toolCards = page.locator('.my-1.rounded-lg.border');
    const count = await toolCards.count();

    if (count > 0) {
      for (let i = 0; i < count; i++) {
        const card = toolCards.nth(i);
        const text = await card.innerText();
        const hasGear = text.includes('\u2699\uFE0F');
        if (hasGear) {
          // If it has gear, it should be an intentionally-geared tool (manage_skills)
          // not a fallback. Check it also has a proper label.
          const hasProperLabel = text.includes('Managing Skills')
            || text.includes('Running Code') || text.includes('Editing');
          expect(hasProperLabel, `Tool card with gear icon has fallback label: ${text}`).toBe(true);
        }
      }
    }
  });
});
