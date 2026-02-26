import { chromium, FullConfig } from '@playwright/test';

/**
 * Global setup: log in once with Cognito test credentials and save
 * the browser storage state (localStorage tokens) to .auth/user.json.
 * All tests then load this state via `storageState` in playwright.config.ts,
 * so they start already authenticated.
 *
 * Credentials are read from environment variables with test defaults.
 * On the dev box / CI, set TEST_EMAIL and TEST_PASSWORD if needed.
 */
export default async function globalSetup(config: FullConfig) {
  const baseURL = config.projects[0]?.use?.baseURL ?? 'http://localhost:3000';
  const email = process.env.TEST_EMAIL ?? 'testuser@example.com';
  const password = process.env.TEST_PASSWORD ?? 'EagleTest2024!';

  const browser = await chromium.launch();
  const page = await browser.newPage();

  // Navigate to login page
  await page.goto(`${baseURL}/login`);

  // Wait for the form to appear
  await page.waitForSelector('#login-email', { timeout: 15000 });

  // Fill credentials and submit
  await page.fill('#login-email', email);
  await page.fill('#login-password', password);
  await page.click('button[type="submit"]');

  // Wait for redirect away from /login — Cognito auth + redirect takes a moment
  await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 30000 });

  // Save storage state (includes Cognito localStorage tokens)
  await page.context().storageState({ path: 'tests/.auth/user.json' });

  await browser.close();
}
