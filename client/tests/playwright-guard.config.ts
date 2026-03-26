import { defineConfig } from '@playwright/test';

/**
 * Minimal Playwright config for guard tests that don't need a browser or server.
 * Usage: npx playwright test --config=tests/playwright-guard.config.ts tests/no-mock-data.spec.ts
 */
export default defineConfig({
  testDir: '.',
  use: {},
});
